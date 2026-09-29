"""Four bounded live checks of evidence context on the existing synthetic PDF."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.geometry import provider_to_app  # noqa: E402
from app.providers.gemma import check_evidence, inspect_page, inspect_page_repair  # noqa: E402
from app.search import make_evidence_crop  # noqa: E402


PROBES = [
    ("h08", "Where is the V2 valve in Loop 2?", "page-d8a7187b11b3"),
    ("h12", "Where is the V2 valve symbol in Loop 1?", "page-d8a7187b11b3"),
    ("h01", "Where is the standby current specified?", "page-ea958fc0b716"),
    ("h07", "Where is the trip threshold row?", "page-ea958fc0b716"),
]


def locate_and_check(question, model_path, canonical_path, settings, *, repair=False):
    result = (inspect_page_repair if repair else inspect_page)(question, model_path, settings)
    record = {"locate": result, "boxes_app": [], "check": None}
    if result["status"] != "found":
        return record
    boxes = [provider_to_app(box) for box in result["boxes_2d"]]
    record["boxes_app"] = boxes
    crop, _, _ = make_evidence_crop(canonical_path, boxes)
    record["check"] = check_evidence(question, model_path, crop, boxes, settings)
    return record


def main():
    settings = get_settings()
    if not settings.key_present or settings.model != "gemma-4-26b-a4b-it":
        raise SystemExit("Configured free Gemma provider is unavailable")
    base = ROOT / "out" / "evaluation" / "data" / "pages"
    report = {"timestamp": datetime.now(timezone.utc).isoformat(), "model": settings.model, "probes": []}
    out = ROOT / "out" / "rapid-build" / "09-probes.json"
    for probe_id, question, page_id in PROBES:
        paths = base / page_id
        start = time.monotonic()
        item = {"id": probe_id, "question": question, "page_id": page_id}
        try:
            item["initial"] = locate_and_check(question, paths / "model.png", paths / "canonical.png", settings)
            if item["initial"]["check"] == "rejected":
                item["repair"] = locate_and_check(question, paths / "model.png", paths / "canonical.png", settings, repair=True)
        except Exception as exc:
            item["error"] = f"{type(exc).__name__}: {exc}"
        item["elapsed_s"] = round(time.monotonic() - start, 1)
        report["probes"].append(item)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"{probe_id}: {item.get('error') or item.get('repair', item.get('initial', {})).get('check')} ({item['elapsed_s']}s)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
