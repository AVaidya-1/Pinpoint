"""Run and record the three acceptance searches against the imported NASA handbook."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "public-doc"
BASE_URL = "http://127.0.0.1:8000"
SOURCE_URL = (
    "https://ntrs.nasa.gov/api/citations/20170001761/downloads/"
    "20170001761.pdf?attachment=true"
)
QUESTIONS = [
    {
        "id": "nasa-01",
        "question": "Where is the Technical Assessment Process relative to the Technical Planning Process?",
        "expected_physical_page": 19,
    },
    {
        "id": "nasa-02",
        "question": "Where is Capture Work Products from Technical Planning Activities in the process?",
        "expected_physical_page": 146,
    },
    {
        "id": "nasa-03",
        "question": "Where is the robust ranking comparison decision in the risk analysis flow?",
        "expected_physical_page": 208,
    },
]


def request_json(method: str, path: str, body: dict | None = None) -> dict:
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        BASE_URL + path,
        data=payload,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def save(report: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )


def completed_search(question: str, document_id: str) -> dict | None:
    """Reuse a just-completed acceptance search after reporter interruption."""
    for item in request_json("GET", "/api/searches")["searches"]:
        if item["question"] != question:
            continue
        result = request_json("GET", f"/api/searches/{item['id']}")
        if result["state"] != "completed":
            continue
        if result["evidence"] and any(
            evidence["document_id"] != document_id for evidence in result["evidence"]
        ):
            continue
        return {"search_id": item["id"], "job_id": item["job_id"], "result": result}
    return None


def main() -> int:
    documents = request_json("GET", "/api/documents")["documents"]
    document = next(
        item for item in documents
        if item["filename"] == "nasa-systems-engineering-handbook-rev2.pdf"
    )
    imported_pages = [item["physical_page_number"] for item in document["pages"]]
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_url": SOURCE_URL,
        "document_id": document["id"],
        "filename": document["filename"],
        "imported_physical_pages": imported_pages,
        "questions": [],
        "status": "running",
    }
    save(report)

    for spec in QUESTIONS:
        started = time.monotonic()
        entry = dict(spec)
        try:
            existing = completed_search(spec["question"], document["id"])
            if existing:
                created = {"search_id": existing["search_id"], "job_id": existing["job_id"]}
                result = existing["result"]
                entry["reused_completed_search"] = True
            else:
                created = request_json("POST", "/api/searches", {
                    "question": spec["question"],
                    "document_ids": [document["id"]],
                    "force_refresh": True,
                })
                result = None
            entry.update(created)
            deadline = time.monotonic() + 900
            if result is None:
                while True:
                    result = request_json("GET", f"/api/searches/{created['search_id']}")
                    if result["state"] in {"completed", "failed", "cancelled", "interrupted"}:
                        break
                    if time.monotonic() >= deadline:
                        raise TimeoutError("search did not finish within 15 minutes")
                    time.sleep(2)
            entry.update({
                "state": result["state"],
                "outcome": result["outcome"],
                "coverage": result["coverage"],
                "evidence": result["evidence"],
                "errors": result["errors"],
            })
            actual_pages = sorted({item["physical_page_number"] for item in result["evidence"]})
            entry["actual_physical_pages"] = actual_pages
            entry["page_reviewer_pass"] = spec["expected_physical_page"] in actual_pages
            entry["boxes_present"] = bool(result["evidence"]) and all(
                bool(item["boxes"]) for item in result["evidence"]
            )
        except (urllib.error.URLError, TimeoutError, KeyError, StopIteration) as exc:
            entry["error_type"] = type(exc).__name__
            entry["error"] = str(exc)[:500]
        entry["elapsed_seconds"] = round(time.monotonic() - started, 1)
        report["questions"].append(entry)
        save(report)

    report["status"] = "complete"
    report["all_page_checks_pass"] = all(
        item.get("page_reviewer_pass") and item.get("boxes_present")
        for item in report["questions"]
    )
    save(report)
    print(OUT / "report.json")
    return 0 if report["all_page_checks_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
