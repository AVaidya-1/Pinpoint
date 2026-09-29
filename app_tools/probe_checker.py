"""Targeted checker probes for h07, h12, and a negative control.

Validates whether annotating the full page image with red box outlines
allows the checker to accept previously-rejected correct locate results.
Runs exactly three live probes; uses existing evaluation page images.

Usage (from the repo root):
    backend/.venv/Scripts/python.exe app_tools/probe_checker.py

Output: out/rapid-build/05-checker-probes.json
"""

from __future__ import annotations

import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "rapid-build"
OUT.mkdir(parents=True, exist_ok=True)

EVAL_PAGES = ROOT / "out" / "evaluation" / "data" / "pages"
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.providers.gemma import check_evidence  # noqa: E402
from app.search import make_evidence_crop  # noqa: E402

# Three probes: h07 correct box, h12 correct box, h07 wrong-box control.
PROBES = [
    {
        "id": "h07_correct",
        "question": "Where is the trip threshold row?",
        "page_id": "page-1ba6a47b4f26",
        "boxes": [[0.116, 0.242, 0.891, 0.263]],
        "expect": "accepted",
        "notes": "Exact box from frozen h07 locate output (not the flawed gold rectangle)",
    },
    {
        "id": "h12_correct",
        "question": "Where is the V2 valve symbol in Loop 1?",
        "page_id": "page-cee09a261b85",
        "boxes": [[0.179, 0.305, 0.243, 0.346]],
        "expect": "accepted",
        "notes": "Exact box from frozen h12 locate output (not the flawed gold rectangle)",
    },
    {
        "id": "h07_wrong_box_control",
        "question": "Where is the trip threshold row?",
        "page_id": "page-1ba6a47b4f26",
        "boxes": [[0.6, 0.7, 0.9, 0.95]],
        "expect": "rejected",
        "notes": "Wrong box (bottom-right blank corner on same page); must still reject",
    },
]


def run_probe(probe: dict, settings) -> dict:
    page_id = probe["page_id"]
    model_path = EVAL_PAGES / page_id / "model.png"
    canonical_path = EVAL_PAGES / page_id / "canonical.png"

    for p in (model_path, canonical_path):
        if not p.exists():
            return {**probe, "verdict": f"ERROR: missing {p.name}", "pass": False,
                    "elapsed_s": 0.0}

    start = time.monotonic()
    try:
        crop_bytes, _, _ = make_evidence_crop(canonical_path, probe["boxes"])
        verdict = check_evidence(
            probe["question"], model_path, crop_bytes, probe["boxes"], settings,
        )
    except Exception as exc:
        return {
            **probe,
            "verdict": f"ERROR: {type(exc).__name__}: {exc}",
            "pass": False,
            "elapsed_s": round(time.monotonic() - start, 1),
        }

    passed = verdict == probe["expect"]
    return {
        **probe,
        "verdict": verdict,
        "pass": passed,
        "elapsed_s": round(time.monotonic() - start, 1),
    }


def main() -> int:
    settings = get_settings()
    if not settings.key_present:
        print("ERROR: GEMINI_API_KEY not set", file=sys.stderr)
        return 1

    print(f"Model: {settings.model}")
    print(f"Probes: {len(PROBES)}")

    results = []
    for probe in PROBES:
        print(f"  [{probe['id']}] running...", end=" ", flush=True)
        result = run_probe(probe, settings)
        results.append(result)
        status = "PASS" if result["pass"] else "FAIL"
        print(f"{status}  got={result['verdict']!r}  expect={probe['expect']!r}  "
              f"({result['elapsed_s']}s)")

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": settings.model,
        "probes": results,
        "passed": sum(1 for r in results if r["pass"]),
        "total": len(results),
    }
    out_path = OUT / "05-checker-probes.json"
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nReport written: {out_path}")
    print(f"Result: {report['passed']}/{report['total']} probes passed")
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
