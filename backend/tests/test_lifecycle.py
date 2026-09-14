"""Document import lifecycle tests: upload -> commit -> ready, capacity,
persistence across restart, byte preservation, physical-page identity."""

import hashlib
import io
from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app.main import app


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("EVIDENCE_DATA_DIR", str(tmp_path / "data"))
    client = TestClient(app)
    client.__enter__()
    return client


def _teardown(client: TestClient) -> None:
    client.__exit__(None, None, None)


def _make_pdf(n_pages: int) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    for i in range(n_pages):
        c.drawString(100, 700, f"Test page {i + 1}")
        c.showPage()
    c.save()
    return buf.getvalue()


def _upload(client: TestClient, data: bytes, name: str, ctype: str) -> dict:
    r = client.post("/api/uploads", files={"file": (name, data, ctype)})
    assert r.status_code == 201, r.text
    return r.json()


def test_import_lifecycle_and_byte_preservation(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    try:
        pdf = _make_pdf(3)
        up = _upload(client, pdf, "three.pdf", "application/pdf")
        assert up["page_count"] == 3
        r = client.post("/api/documents", json={"upload_id": up["upload_id"], "pages": [1, 2, 3]})
        assert r.status_code == 202, r.text
        doc_id = r.json()["document_id"]
        docs = client.get("/api/documents").json()
        doc = next(d for d in docs["documents"] if d["id"] == doc_id)
        assert doc["status"] == "ready"
        assert [p["physical_page_number"] for p in doc["pages"]] == [1, 2, 3]
        # Original preserved byte-for-byte (original_path is relative to the
        # project root; the test data dir stands in for ./data).
        stored = Path(tmp_path) / "data" / Path(*Path(doc["original_path"]).parts[1:])
        assert stored.exists()
        assert hashlib.sha256(stored.read_bytes()).hexdigest() == hashlib.sha256(pdf).hexdigest()
        # Canonical raster served.
        page_id = doc["pages"][0]["id"]
        img = client.get(f"/api/pages/{page_id}/image")
        assert img.status_code == 200
        assert img.headers["content-type"] == "image/png"
        # Stored original served.
        orig = client.get(f"/api/documents/{doc_id}/original")
        assert orig.status_code == 200
        assert hashlib.sha256(orig.content).hexdigest() == hashlib.sha256(pdf).hexdigest()
    finally:
        _teardown(client)


def test_noncontiguous_pages_record_physical_numbers(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    try:
        pdf = _make_pdf(4)
        up = _upload(client, pdf, "four.pdf", "application/pdf")
        r = client.post("/api/documents", json={"upload_id": up["upload_id"], "pages": [2, 4]})
        assert r.status_code == 202, r.text
        doc_id = r.json()["document_id"]
        docs = client.get("/api/documents").json()
        doc = next(d for d in docs["documents"] if d["id"] == doc_id)
        assert [p["physical_page_number"] for p in doc["pages"]] == [2, 4]
    finally:
        _teardown(client)


def test_capacity_enforced_409(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    try:
        pdf = _make_pdf(21)
        up = _upload(client, pdf, "long.pdf", "application/pdf")
        assert up["page_count"] == 21
        r = client.post(
            "/api/documents", json={"upload_id": up["upload_id"], "pages": list(range(1, 22))}
        )
        assert r.status_code == 409, r.text
        detail = r.json()["detail"]
        assert "capacity" in detail, detail
        assert detail["capacity"]["max_pages"] == 20
    finally:
        _teardown(client)


def test_persistence_across_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("EVIDENCE_DATA_DIR", str(tmp_path / "data"))
    with TestClient(app) as client:
        pdf = _make_pdf(2)
        up = _upload(client, pdf, "two.pdf", "application/pdf")
        r = client.post("/api/documents", json={"upload_id": up["upload_id"], "pages": [1, 2]})
        doc_id = r.json()["document_id"]
    # Simulate a restart with a fresh client/process state.
    with TestClient(app) as client2:
        docs = client2.get("/api/documents").json()
        ids = [d["id"] for d in docs["documents"]]
        assert doc_id in ids
        doc = next(d for d in docs["documents"] if d["id"] == doc_id)
        assert doc["status"] == "ready"
        # Interrupted-job handling: a job left queued becomes interrupted.
        data_dir = tmp_path / "data"
        conn = db.get_connection(data_dir)
        try:
            from app.jobs import create_job

            jid = create_job(conn, "import", 1)
        finally:
            conn.close()
        db.init_db(data_dir)
        conn = db.get_connection(data_dir)
        try:
            row = conn.execute("SELECT state FROM jobs WHERE id = ?", (jid,)).fetchone()
            assert row["state"] == "interrupted"
        finally:
            conn.close()
