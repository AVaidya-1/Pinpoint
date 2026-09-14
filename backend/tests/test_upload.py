"""Upload validation and API error-response tests."""

import io

from fastapi.testclient import TestClient

from app.main import app


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("EVIDENCE_DATA_DIR", str(tmp_path / "data"))
    client = TestClient(app)
    client.__enter__()
    return client


def _teardown(client: TestClient) -> None:
    client.__exit__(None, None, None)


def _minimal_png() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (16, 16), (1, 2, 3)).save(buf, format="PNG")
    return buf.getvalue()


def test_upload_png_ok(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    try:
        r = client.post("/api/uploads", files={"file": ("a.png", _minimal_png(), "image/png")})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["page_count"] == 1
        assert body["mime_type"] == "image/png"
    finally:
        _teardown(client)


def test_upload_unsupported_type_415(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    try:
        r = client.post("/api/uploads", files={"file": ("a.txt", b"hello", "text/plain")})
        assert r.status_code == 415, r.text
    finally:
        _teardown(client)


def test_upload_mismatched_signature_415(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    try:
        r = client.post("/api/uploads", files={"file": ("a.png", b"not a png", "image/png")})
        assert r.status_code == 415, r.text
    finally:
        _teardown(client)


def test_upload_too_large_413(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    try:
        big = _minimal_png() + bytes(25 * 1024 * 1024)
        r = client.post("/api/uploads", files={"file": ("big.png", big, "image/png")})
        assert r.status_code == 413, r.status_code
    finally:
        _teardown(client)


def test_commit_invalid_page_range_422(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    try:
        r = client.post("/api/uploads", files={"file": ("a.png", _minimal_png(), "image/png")})
        upload_id = r.json()["upload_id"]
        r2 = client.post("/api/documents", json={"upload_id": upload_id, "pages": [2]})
        assert r2.status_code == 422, r2.text
    finally:
        _teardown(client)


def test_unknown_ids_404(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    try:
        assert client.get("/api/pages/page-nope/image").status_code == 404
        assert client.get("/api/documents/doc-nope/original").status_code == 404
        assert client.delete("/api/documents/doc-nope").status_code == 404
    finally:
        _teardown(client)
