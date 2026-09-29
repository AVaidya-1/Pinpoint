"""One-page real-model smoke check on the generated raster flowchart.

Uses the configured free model and stores only status/evidence metadata under
out/rapid-build. No fixture truth is sent to the provider.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "rapid-build"
OUT.mkdir(parents=True, exist_ok=True)
DATA = OUT / "live-smoke-data"
os.environ["EVIDENCE_DATA_DIR"] = str(DATA)
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.config import get_settings  # noqa: E402


def main() -> int:
    started = time.monotonic()
    report: dict = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": get_settings().model,
        "question": "Where does the No branch from Pass? go?",
        "input": "fixtures/generated/test_pages.pdf, physical page 3",
    }
    try:
        with TestClient(app) as client:
            path = ROOT / "fixtures" / "generated" / "test_pages.pdf"
            with path.open("rb") as handle:
                up = client.post("/api/uploads", files={
                    "file": (path.name, handle, "application/pdf"),
                })
            report["upload_http"] = up.status_code
            up.raise_for_status()
            commit = client.post("/api/documents", json={
                "upload_id": up.json()["upload_id"], "pages": [3],
            })
            report["import_http"] = commit.status_code
            commit.raise_for_status()
            doc_id = commit.json()["document_id"]
            search = client.post("/api/searches", json={
                "question": report["question"], "document_ids": [doc_id],
            })
            report["search_http"] = search.status_code
            search.raise_for_status()
            result = client.get(f"/api/searches/{search.json()['search_id']}")
            result.raise_for_status()
            body = result.json()
            report["outcome"] = body["outcome"]
            report["coverage"] = body["coverage"]
            report["evidence"] = [{
                "physical_page_number": item["physical_page_number"],
                "kind": item["kind"], "boxes": item["boxes"],
            } for item in body["evidence"]]
            report["errors"] = body["errors"]
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc)[:500]
    report["elapsed_seconds"] = round(time.monotonic() - started, 1)
    (OUT / "live-smoke.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Live smoke: {report.get('outcome', report.get('error_type', 'unknown'))}; "
          f"report={OUT / 'live-smoke.json'}")
    return 0 if report.get("outcome") == "found" and report.get("evidence") else 1


if __name__ == "__main__":
    raise SystemExit(main())
