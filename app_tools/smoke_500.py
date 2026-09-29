"""Live smoke test: 500-page PDF question-to-highlight journey.

Generates a 500-page PDF with a unique equipment datum on physical page 500,
imports it through the real API, asks a standalone question, waits for search
completion, and asserts evidence on page 500 with a valid visible box.

Pages 1-499: generic inspection records — no keyword overlap with the question.
Page 500: "VALVE-X7Q-500 pressure reading 142.7 PSI" — all question keywords present.
The text candidate stage screens all 499 distractor pages and passes only page 500
to the VLM, so at most 2 API calls are made (inspect + check).

Usage:
    backend\\.venv\\Scripts\\python.exe app_tools\\smoke_500.py
        Full live smoke (requires GEMINI_API_KEY in .env or environment)
    backend\\.venv\\Scripts\\python.exe app_tools\\smoke_500.py --generate-only
        Generate fixture PDF only; skip search

Output:
    out/rapid-build/fixtures/five-hundred.pdf  — generated fixture (gitignored)
    out/rapid-build/07-smoke.json              — full smoke report
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "rapid-build"
FIXTURE_DIR = OUT / "fixtures"
FIXTURE_PDF = FIXTURE_DIR / "five-hundred.pdf"

OUT.mkdir(parents=True, exist_ok=True)
FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

# Unique datum on page 500 — no overlap with distractor page keywords
UNIQUE_ID = "VALVE-X7Q-500"
UNIQUE_PRESSURE = "142.7"
QUESTION = f"What is the pressure reading for {UNIQUE_ID}?"


def generate_fixture(n_pages: int = 500) -> bytes:
    """Return bytes for an n-page PDF.

    Pages 1..(n-1): generic inspection text — no keywords shared with QUESTION.
    Page n: unique datum readable by text extraction and the VLM.
    Vector-only content keeps the file to ~100 KB at 500 pages.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas as rl_canvas

    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=letter)
    pw, ph = letter  # 612 x 792 pt

    for i in range(1, n_pages + 1):
        # White background
        c.setFillColorRGB(1, 1, 1)
        c.rect(0, 0, pw, ph, fill=1, stroke=0)
        c.setFillColorRGB(0, 0, 0)

        if i < n_pages:
            # Distractor: generic words, no overlap with {pressure,reading,valve,x7q}
            c.setFont("Helvetica", 11)
            c.drawString(72, 700, f"Document page {i}.")
            c.drawString(72, 680, "General inspection record.")
            c.drawString(72, 660, "Component checks: nominal. Status: nominal.")
            c.drawString(72, 640, f"Reference: GEN-PROC-{i:03d}.")
        else:
            # Page 500: unique target — large, readable text for the VLM
            c.setFont("Helvetica-Bold", 18)
            c.drawString(72, 700, "INSTRUMENT RECORD — FINAL PAGE")
            c.setFont("Helvetica-Bold", 14)
            c.drawString(72, 648, UNIQUE_ID)
            c.setFont("Helvetica", 12)
            c.drawString(72, 624, f"Pressure reading: {UNIQUE_PRESSURE} PSI")
            c.drawString(72, 604, "Rated capacity: PROC-QKZ")
            c.drawString(72, 584, "Status: active. Maintenance cycle: 6 months.")
            c.drawString(72, 564, f"Physical page: {i} of {n_pages}.")

        c.showPage()

    c.save()
    return buf.getvalue()


def ensure_fixture() -> Path:
    """Generate fixture PDF if absent. Returns its path."""
    if not FIXTURE_PDF.exists():
        data = generate_fixture(500)
        FIXTURE_PDF.write_bytes(data)
        print(f"Generated {FIXTURE_PDF} ({len(data):,} bytes)")
    else:
        print(f"Using cached fixture {FIXTURE_PDF} ({FIXTURE_PDF.stat().st_size:,} bytes)")
    return FIXTURE_PDF


def main(generate_only: bool = False) -> int:
    fixture_path = ensure_fixture()
    if generate_only:
        print("--generate-only: fixture ready, skipping live search.")
        return 0

    # Set data dir before importing the app so get_settings() reads it correctly.
    data_dir = OUT / "smoke-500-data"
    os.environ["EVIDENCE_DATA_DIR"] = str(data_dir)
    os.environ["EVIDENCE_MAX_PAGES"] = "600"
    sys.path.insert(0, str(ROOT / "backend"))

    from fastapi.testclient import TestClient  # noqa: E402
    from app.main import app  # noqa: E402
    from app.config import get_settings  # noqa: E402

    started = time.monotonic()
    report: dict = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fixture": str(FIXTURE_PDF),
        "question": QUESTION,
        "unique_id": UNIQUE_ID,
        "expected_page": 500,
    }

    try:
        with TestClient(app) as client:
            settings = get_settings()
            report["model"] = settings.model
            report["key_present"] = settings.key_present

            # 1. Upload -------------------------------------------------------
            t0 = time.monotonic()
            with fixture_path.open("rb") as fh:
                up_resp = client.post(
                    "/api/uploads",
                    files={"file": (fixture_path.name, fh, "application/pdf")},
                )
            report["upload_http"] = up_resp.status_code
            up_resp.raise_for_status()
            up_body = up_resp.json()

            assert up_body["page_count"] == 500, (
                f"Expected 500 pages, got {up_body['page_count']}"
            )
            report["upload_page_count"] = up_body["page_count"]
            report["upload_elapsed_s"] = round(time.monotonic() - t0, 1)

            # 2. Import all 500 pages -----------------------------------------
            t0 = time.monotonic()
            commit_resp = client.post("/api/documents", json={
                "upload_id": up_body["upload_id"],
                "pages": list(range(1, 501)),
            })
            report["import_http"] = commit_resp.status_code
            commit_resp.raise_for_status()
            commit_body = commit_resp.json()
            doc_id = commit_body["document_id"]
            report["document_id"] = doc_id
            report["import_elapsed_s"] = round(time.monotonic() - t0, 1)

            # Verify all 500 stubs and status == ready
            docs_resp = client.get("/api/documents")
            docs_resp.raise_for_status()
            doc = next(
                (d for d in docs_resp.json()["documents"] if d["id"] == doc_id),
                None,
            )
            assert doc is not None, "Document not found after import"
            assert doc["status"] == "ready", f"Status: {doc['status']}"
            assert len(doc["pages"]) == 500, (
                f"Expected 500 pages, got {len(doc['pages'])}"
            )
            page500 = next(
                (p for p in doc["pages"] if p["physical_page_number"] == 500),
                None,
            )
            assert page500 is not None, "Page 500 record missing"
            report["import_page_count"] = len(doc["pages"])
            report["page_500_id"] = page500["id"]

            # 3. On-demand render of page 500 ---------------------------------
            img_resp = client.get(f"/api/pages/{page500['id']}/image")
            report["page_500_image_http"] = img_resp.status_code
            assert img_resp.status_code == 200, (
                f"Page 500 image endpoint returned {img_resp.status_code}"
            )
            assert img_resp.content[:4] == b"\x89PNG", "Response is not PNG"
            report["page_500_image_ok"] = True

            # 4. Search (requires API key) ------------------------------------
            if not settings.key_present:
                report["search_skipped"] = (
                    "GEMINI_API_KEY not set — run with the key to complete the search"
                )
                report["outcome"] = "skipped"
                report["pass"] = False
                report["elapsed_seconds"] = round(time.monotonic() - started, 1)
                _write_report(report)
                return 1  # incomplete without key

            t0 = time.monotonic()
            search_resp = client.post("/api/searches", json={
                "question": QUESTION,
                "document_ids": [doc_id],
            })
            report["search_http"] = search_resp.status_code
            search_resp.raise_for_status()
            search_id = search_resp.json()["search_id"]

            # TestClient runs background tasks synchronously — result is ready now
            result_resp = client.get(f"/api/searches/{search_id}")
            result_resp.raise_for_status()
            result = result_resp.json()
            report["search_elapsed_s"] = round(time.monotonic() - t0, 1)

            report["outcome"] = result["outcome"]
            report["coverage"] = result.get("coverage", {})
            report["evidence"] = [
                {
                    "physical_page_number": ev["physical_page_number"],
                    "kind": ev["kind"],
                    "boxes": ev["boxes"],
                }
                for ev in result.get("evidence", [])
            ]
            report["errors"] = result.get("errors", [])

            # 5. Assert evidence on page 500 with visible box -----------------
            ev_500 = [e for e in report["evidence"] if e["physical_page_number"] == 500]
            valid_box = False
            if ev_500:
                for box in ev_500[0].get("boxes", []):
                    if (
                        len(box) == 4
                        and 0 <= box[0] < box[2] <= 1
                        and 0 <= box[1] < box[3] <= 1
                    ):
                        valid_box = True
                        break

            report["evidence_on_page_500"] = len(ev_500) > 0
            report["valid_box_on_page_500"] = valid_box
            # Keyword-screened pages remain unchecked, so an accepted source
            # can correctly carry outcome=incomplete. The proof here is the
            # accepted page-500 box, with partial coverage reported above.
            report["pass"] = len(ev_500) > 0 and valid_box

    except Exception as exc:
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc)[:1000]
        report["pass"] = False

    report["elapsed_seconds"] = round(time.monotonic() - started, 1)
    _write_report(report)
    return 0 if report.get("pass") else 1


def _write_report(report: dict) -> None:
    report_path = OUT / "07-smoke.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    outcome = report.get("outcome", report.get("error_type", "error"))
    print(
        f"Smoke-500: outcome={outcome} "
        f"pass={report.get('pass')} "
        f"page_500_evidence={report.get('evidence_on_page_500', '?')} "
        f"valid_box={report.get('valid_box_on_page_500', '?')} "
        f"elapsed={report.get('elapsed_seconds', '?')}s"
    )
    print(f"Report written: {report_path}")


if __name__ == "__main__":
    _generate_only = "--generate-only" in sys.argv
    raise SystemExit(main(_generate_only))
