"""Task 06 — Targeted locate probes for h12 and one page-7 question.

Validates that the updated locate prompt causes the model to propose boxes
that include disambiguating context (Loop 1 label + V2 symbol for h12) and
that the checker accepts those boxes.

Pass criteria for h12:
  1. The locate model returns status=found.
  2. The union bounding box of proposed boxes is larger than the isolated
     symbol box [x0=0.179, y0=0.305, x1=0.243, y1=0.346] — specifically,
     it covers a meaningfully wider y-range (loop-label area above the
     symbol), or there are 2+ boxes.
  3. The checker returns accepted.

A "mere page match" (the model locates something on the page but the checker
rejects it) does NOT count as a pass.

Usage (from repo root):
    backend\\.venv\\Scripts\\python.exe app_tools\\probe_locate_h12.py

Output: out/rapid-build/06-locate-probes.json
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
from app.providers.gemma import inspect_page, check_evidence  # noqa: E402
from app.search import make_evidence_crop  # noqa: E402
from app.geometry import provider_to_app  # noqa: E402

# Original symbol-only locate box from the frozen h12 run (app coords).
# The new prompt must produce boxes that cover a meaningfully larger area.
H12_ORIGINAL_BOX = [0.179, 0.305, 0.243, 0.346]

PROBES = [
    {
        "id": "h12_disambiguate",
        "question": "Where is the V2 valve symbol in Loop 1?",
        "page_id": "page-cee09a261b85",
        "notes": (
            "Loop 1 and Loop 2 both have a V2 symbol. The locate model must "
            "propose at least 2 boxes, or a box substantially larger than the "
            "isolated symbol box, so the checker can identify which instance."
        ),
    },
    {
        "id": "h09_curve_direction",
        "question": "Which way does the rated torque curve fall at high load?",
        "page_id": "page-b2e39d4a570d",
        "notes": (
            "Directional question requiring the curve region with axis context "
            "at the high-load (right) end. Checker must accept the located region."
        ),
    },
]


def _union_box(boxes: list[list[float]]) -> list[float]:
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes)
    y1 = max(b[3] for b in boxes)
    return [x0, y0, x1, y1]


def _h12_has_context(boxes_app: list[list[float]]) -> tuple[bool, str]:
    """Return (passes, reason) for h12 context-inclusion check."""
    if len(boxes_app) >= 2:
        return True, f"{len(boxes_app)} boxes proposed — context box expected"

    union = _union_box(boxes_app)
    orig_area = (
        (H12_ORIGINAL_BOX[2] - H12_ORIGINAL_BOX[0])
        * (H12_ORIGINAL_BOX[3] - H12_ORIGINAL_BOX[1])
    )
    new_area = (union[2] - union[0]) * (union[3] - union[1])
    ratio = new_area / orig_area if orig_area > 0 else 0.0

    # Union box must cover significantly more area (≥2x the original symbol box)
    # OR extend meaningfully above the symbol (y0 < original y0 - 0.05).
    y_extended = union[1] < H12_ORIGINAL_BOX[1] - 0.05
    area_larger = ratio >= 2.0

    if area_larger or y_extended:
        return True, (
            f"single box covers {ratio:.1f}x original area, "
            f"y-extended={y_extended}"
        )
    return False, (
        f"single box area only {ratio:.1f}x original; "
        "no Loop 1 context — checker will likely reject"
    )


def run_probe(probe: dict, settings) -> dict:
    page_id = probe["page_id"]
    model_path = EVAL_PAGES / page_id / "model.png"
    canonical_path = EVAL_PAGES / page_id / "canonical.png"

    for p in (model_path, canonical_path):
        if not p.exists():
            return {**probe, "locate_status": "ERROR", "check_verdict": None,
                    "context_pass": False, "check_pass": False,
                    "error": f"missing {p.name}", "elapsed_s": 0.0}

    start = time.monotonic()
    question = probe["question"]
    try:
        locate_result = inspect_page(question, model_path, settings)
    except Exception as exc:
        return {
            **probe,
            "locate_status": "ERROR",
            "locate_boxes_provider": None,
            "boxes_app": None,
            "check_verdict": None,
            "context_pass": False,
            "check_pass": False,
            "error": f"inspect_page: {type(exc).__name__}: {exc}",
            "elapsed_s": round(time.monotonic() - start, 1),
        }

    status = locate_result.get("status")
    boxes_provider = locate_result.get("boxes_2d", [])

    if status != "found" or not boxes_provider:
        return {
            **probe,
            "locate_status": status,
            "locate_boxes_provider": boxes_provider,
            "boxes_app": [],
            "check_verdict": None,
            "context_pass": False,
            "check_pass": False,
            "error": f"locate returned {status!r}, no boxes to check",
            "elapsed_s": round(time.monotonic() - start, 1),
        }

    boxes_app = [provider_to_app(b) for b in boxes_provider]

    # h12-specific context check.
    if probe["id"] == "h12_disambiguate":
        context_ok, context_reason = _h12_has_context(boxes_app)
    else:
        context_ok, context_reason = True, "context check not applied for this probe"

    try:
        crop_bytes, _, _ = make_evidence_crop(canonical_path, boxes_app)
        check_verdict = check_evidence(
            question, model_path, crop_bytes, boxes_app, settings,
        )
    except Exception as exc:
        return {
            **probe,
            "locate_status": status,
            "locate_boxes_provider": boxes_provider,
            "boxes_app": boxes_app,
            "check_verdict": "ERROR",
            "context_pass": context_ok,
            "context_reason": context_reason,
            "check_pass": False,
            "error": f"check_evidence: {type(exc).__name__}: {exc}",
            "elapsed_s": round(time.monotonic() - start, 1),
        }

    check_pass = check_verdict == "accepted"
    overall_pass = context_ok and check_pass

    return {
        **probe,
        "locate_status": status,
        "locate_boxes_provider": boxes_provider,
        "boxes_app": boxes_app,
        "check_verdict": check_verdict,
        "context_pass": context_ok,
        "context_reason": context_reason,
        "check_pass": check_pass,
        "overall_pass": overall_pass,
        "error": None,
        "elapsed_s": round(time.monotonic() - start, 1),
    }


def main() -> int:
    settings = get_settings()
    if not settings.key_present:
        print("ERROR: GEMINI_API_KEY not set", file=sys.stderr)
        return 1

    print(f"Model: {settings.model}")
    print(f"Probes: {len(PROBES)}")
    print()

    results = []
    for probe in PROBES:
        print(f"[{probe['id']}] running locate...", flush=True)
        result = run_probe(probe, settings)
        results.append(result)

        locate_s = result.get("locate_status", "ERROR")
        boxes = result.get("boxes_app") or []
        verdict = result.get("check_verdict")
        ctx = result.get("context_pass")
        ctx_reason = result.get("context_reason", "")
        overall = result.get("overall_pass", False)
        err = result.get("error")

        print(f"  locate: {locate_s!r}  boxes_app={boxes}")
        print(f"  context_pass: {ctx}  ({ctx_reason})")
        print(f"  checker: {verdict!r}  check_pass: {result.get('check_pass')}")
        if err:
            print(f"  ERROR: {err}")
        print(f"  OVERALL: {'PASS' if overall else 'FAIL'}  ({result['elapsed_s']}s)")
        print()

    h12_result = next((r for r in results if r["id"] == "h12_disambiguate"), None)
    h12_pass = h12_result is not None and h12_result.get("overall_pass", False)

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": settings.model,
        "probes": results,
        "h12_pass": h12_pass,
        "total_pass": sum(1 for r in results if r.get("overall_pass", False)),
        "total": len(results),
    }
    out_path = OUT / "06-locate-probes.json"
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Report: {out_path}")
    print(f"h12 (disambiguate) PASS: {h12_pass}")
    print(f"Total pass: {report['total_pass']}/{report['total']}")

    # Task requires h12 to pass; other probes are informational.
    return 0 if h12_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
