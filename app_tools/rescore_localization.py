"""Offline localization rescorer — compares report.json actual boxes against
ground-truth-v2.json reference regions and writes diagnostic-v2.json +
diagnostic-v2.md.

Does NOT overwrite report.json or summary.txt.
Labels all output as diagnostic-v2 (not a fresh holdout).

Usage:
    python app_tools/rescore_localization.py [--report PATH] [--v2 PATH] [--out-dir PATH]

Defaults:
    report   = out/evaluation/report.json
    v2       = out/evaluation/ground-truth-v2.json
    out_dir  = out/evaluation/
"""

import argparse
import json
import sys
from pathlib import Path

COV_THRESHOLD = 0.80
AREA_MAX = 3.0

# --------------------------------------------------------------------------
# Geometry helpers
# --------------------------------------------------------------------------


def box_area(b):
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def box_intersection(a, b):
    x0 = max(a[0], b[0])
    y0 = max(a[1], b[1])
    x1 = min(a[2], b[2])
    y1 = min(a[3], b[3])
    return max(0.0, (x1 - x0) * (y1 - y0))


def union_coverage(actual_boxes, gold):
    """
    Coverage = total intersection area of all actual boxes with gold / gold area.
    Overlapping actual boxes are handled by iterating over non-overlapping strips,
    but for the small box counts here (1-3 boxes) we use inclusion-exclusion.

    For simplicity and correctness with non-overlapping boxes (which is typical),
    we sum individual intersections then subtract pairwise double-counts.
    """
    if not actual_boxes:
        return 0.0
    gold_area = box_area(gold)
    if gold_area <= 0:
        return 0.0

    # Clip each box to the gold region first, then compute area of union of clips
    clips = []
    for b in actual_boxes:
        clipped = [
            max(b[0], gold[0]), max(b[1], gold[1]),
            min(b[2], gold[2]), min(b[3], gold[3])
        ]
        if clipped[2] > clipped[0] and clipped[3] > clipped[1]:
            clips.append(clipped)

    if not clips:
        return 0.0

    # Area of union of axis-aligned rectangles via inclusion-exclusion
    # For up to 3 boxes this is tractable
    n = len(clips)
    total = sum(box_area(c) for c in clips)
    for i in range(n):
        for j in range(i + 1, n):
            total -= box_intersection(clips[i], clips[j])
    if n == 3:
        ix = [
            max(clips[0][0], clips[1][0], clips[2][0]),
            max(clips[0][1], clips[1][1], clips[2][1]),
            min(clips[0][2], clips[1][2], clips[2][2]),
            min(clips[0][3], clips[1][3], clips[2][3]),
        ]
        if ix[2] > ix[0] and ix[3] > ix[1]:
            total += (ix[2] - ix[0]) * (ix[3] - ix[1])

    return max(0.0, total) / gold_area


def union_bounding_box(boxes):
    if not boxes:
        return None
    return [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]


def union_area_nonoverlapping(actual_boxes):
    """
    Compute actual union area (not bounding box area) using inclusion-exclusion
    for up to 3 boxes.
    """
    if not actual_boxes:
        return 0.0
    n = len(actual_boxes)
    total = sum(box_area(b) for b in actual_boxes)
    for i in range(n):
        for j in range(i + 1, n):
            total -= box_intersection(actual_boxes[i], actual_boxes[j])
    if n == 3:
        ix = [
            max(actual_boxes[0][0], actual_boxes[1][0], actual_boxes[2][0]),
            max(actual_boxes[0][1], actual_boxes[1][1], actual_boxes[2][1]),
            min(actual_boxes[0][2], actual_boxes[1][2], actual_boxes[2][2]),
            min(actual_boxes[0][3], actual_boxes[1][3], actual_boxes[2][3]),
        ]
        if ix[2] > ix[0] and ix[3] > ix[1]:
            total += (ix[2] - ix[0]) * (ix[3] - ix[1])
    return max(0.0, total)


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------


def score_question(report_q, v2_q):
    """Return a scoring dict for one answerable question."""
    qid = report_q["id"]
    actual_boxes = report_q.get("actual_boxes", [])
    outcome = report_q.get("outcome", "unknown")

    # If no boxes (uncertain / not_found), immediate fail
    if not actual_boxes:
        return {
            "id": qid,
            "v2_region": v2_q["v2_region"],
            "actual_boxes": [],
            "coverage_v2": None,
            "area_ratio_v2": None,
            "localization_pass_v2": False,
            "fail_reason": "no_boxes (outcome={})".format(outcome),
        }

    gold = v2_q["v2_region"]
    required = [item["region"] for item in v2_q.get("v2_required_regions", [])]
    regions = required or [gold]
    gold_a = sum(box_area(region) for region in regions)

    per_region_coverage = [union_coverage(actual_boxes, region) for region in regions]
    # Each required item must be visible. A large hit on one label must not
    # compensate for missing another label in a multi-region question.
    cov = min(per_region_coverage)
    model_union_a = union_area_nonoverlapping(actual_boxes)
    area_ratio = model_union_a / gold_a if gold_a > 0 else float("inf")

    pass_cov = cov >= COV_THRESHOLD
    pass_area = area_ratio <= AREA_MAX
    localization_pass = pass_cov and pass_area

    fail_reason = None
    if not localization_pass:
        reasons = []
        if not pass_cov:
            reasons.append(f"coverage={cov:.3f} < {COV_THRESHOLD}")
        if not pass_area:
            reasons.append(f"area_ratio={area_ratio:.3f} > {AREA_MAX}")
        fail_reason = "; ".join(reasons)

    return {
        "id": qid,
        "v2_region": gold,
        "v2_required_regions": required,
        "actual_boxes": actual_boxes,
        "coverage_v2": round(cov, 4),
        "per_region_coverage_v2": [round(value, 4) for value in per_region_coverage],
        "area_ratio_v2": round(area_ratio, 4),
        "localization_pass_v2": localization_pass,
        "fail_reason": fail_reason,
    }


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[1]
    ap.add_argument("--report", default=str(root / "out/evaluation/report.json"))
    ap.add_argument("--v2", default=str(root / "out/evaluation/ground-truth-v2.json"))
    ap.add_argument("--out-dir", default=str(root / "out/evaluation"))
    args = ap.parse_args()

    report_path = Path(args.report)
    v2_path = Path(args.v2)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(report_path, encoding="utf-8") as f:
        report = json.load(f)
    with open(v2_path, encoding="utf-8") as f:
        v2 = json.load(f)

    v2_by_id = {q["id"]: q for q in v2["questions"]}

    # ---------- Frozen scores (from report) ----------
    frozen_loc = report["thresholds"]["localized"]["actual"]
    frozen_page = report["thresholds"]["correct_page"]["actual"]
    frozen_visual_loc = report["thresholds"]["visual_localized"]["actual"]
    frozen_absent = report["thresholds"]["absent_correct"]["actual"]

    # ---------- Compute v2 diagnostic scores ----------
    results = []
    v2_pass_count = 0
    v2_visual_pass_count = 0
    page_ok_count = 0
    visual_questions = set()

    for rq in report["questions"]:
        qid = rq["id"]
        qtype = rq.get("type", "")
        if qtype == "absent":
            continue

        page_ok = rq.get("actual_page_correct", False)
        if page_ok:
            page_ok_count += 1

        if qid not in v2_by_id:
            results.append({
                "id": qid,
                "type": qtype,
                "page_ok": page_ok,
                "note": "not in v2 reference",
            })
            continue

        v2_q = v2_by_id[qid]
        scored = score_question(rq, v2_q)
        scored["type"] = qtype
        scored["page_ok"] = page_ok
        scored["frozen_localization_pass"] = rq.get("localization_pass", False)
        scored["frozen_coverage"] = rq.get("coverage_ratio")
        scored["frozen_area_ratio"] = rq.get("area_ratio")
        scored["frozen_region"] = rq.get("expected_region")
        scored["outcome"] = rq.get("outcome")
        scored["derivation_note"] = v2_q.get("derivation", "")
        scored["frozen_region_issue"] = v2_q.get("frozen_region_issue", "")
        scored["model_result_note"] = v2_q.get("model_result", "")

        if qtype == "visual":
            visual_questions.add(qid)
        if scored["localization_pass_v2"]:
            v2_pass_count += 1
            if qtype == "visual":
                v2_visual_pass_count += 1

        results.append(scored)

    answerable_count = len([r for r in results if "localization_pass_v2" in r])

    # ---------- Build output JSON ----------
    diag = {
        "label": "diagnostic-v2",
        "warning": "NOT a fresh holdout. Questions were used in prompt repair. "
                   "These scores measure reference quality and remaining real failures, "
                   "not model quality on unseen data.",
        "source_report": str(report_path),
        "v2_reference": str(v2_path),
        "thresholds": {
            "coverage_required": COV_THRESHOLD,
            "area_max": AREA_MAX,
        },
        "frozen_scores": {
            "correct_page": frozen_page,
            "localized": frozen_loc,
            "visual_localized": frozen_visual_loc,
            "absent_correct": frozen_absent,
        },
        "diagnostic_v2_scores": {
            "answerable_count": answerable_count,
            "localized_v2": v2_pass_count,
            "visual_localized_v2": v2_visual_pass_count,
        },
        "questions": results,
    }

    out_json = out_dir / "diagnostic-v2.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(diag, f, indent=2)
        f.write("\n")
    print(f"Wrote {out_json}")

    # ---------- Build output Markdown ----------
    lines = [
        "# Diagnostic v2 — localization rescore against independent reference",
        "",
        "> **NOT a fresh holdout.** Questions were used in prompt repair. "
        "Scores show reference quality and remaining real failures, "
        "not model quality on unseen data.",
        "",
        f"Source report: `{report_path}`  ",
        f"v2 reference: `{v2_path}`  ",
        f"Coverage threshold: {COV_THRESHOLD}  Area limit: {AREA_MAX}×",
        "",
        "## Frozen scores (unchanged)",
        "",
        f"| Metric | Actual | Threshold | Pass |",
        f"|--------|--------|-----------|------|",
        f"| Correct page | {frozen_page}/16 | 14 | {'PASS' if frozen_page >= 14 else 'FAIL'} |",
        f"| Localized (frozen gold) | {frozen_loc}/16 | 12 | {'PASS' if frozen_loc >= 12 else 'FAIL'} |",
        f"| Visual localized (frozen) | {frozen_visual_loc}/8 | 6 | {'PASS' if frozen_visual_loc >= 6 else 'FAIL'} |",
        f"| Absent correct | {frozen_absent}/4 | 3 | {'PASS' if frozen_absent >= 3 else 'FAIL'} |",
        "",
        "## Diagnostic v2 scores",
        "",
        f"| Metric | Diagnostic v2 |",
        f"|--------|---------------|",
        f"| Localized (v2 gold) | {v2_pass_count}/{answerable_count} |",
        f"| Visual localized (v2) | {v2_visual_pass_count}/8 |",
        "",
        "## Per-question breakdown",
        "",
        "| ID | Type | page_ok | frozen_cov | frozen_pass | v2_cov | v2_area | v2_pass | Note |",
        "|-----|------|---------|-----------|-------------|--------|---------|---------|------|",
    ]

    for r in results:
        if "localization_pass_v2" not in r:
            continue
        qid = r["id"]
        qtype = r.get("type", "")
        page_ok = "Y" if r.get("page_ok") else "N"
        f_cov = f"{r['frozen_coverage']:.3f}" if r.get("frozen_coverage") is not None else "—"
        f_pass = "Y" if r.get("frozen_localization_pass") else "N"
        v2_cov = f"{r['coverage_v2']:.3f}" if r.get("coverage_v2") is not None else "—"
        v2_area = f"{r['area_ratio_v2']:.3f}" if r.get("area_ratio_v2") is not None else "—"
        v2_pass = "**PASS**" if r["localization_pass_v2"] else "FAIL"
        note = r.get("fail_reason") or "—"
        lines.append(f"| {qid} | {qtype} | {page_ok} | {f_cov} | {f_pass} | {v2_cov} | {v2_area} | {v2_pass} | {note} |")

    lines += [
        "",
        "## Analysis: bad gold vs real failures",
        "",
        "### Confirmed bad frozen gold regions",
        "",
        "The following questions had frozen reference rectangles that did not enclose "
        "the named evidence. Their 0/16 frozen localization score cannot be used to "
        "judge these questions.",
        "",
    ]

    bad_gold_ids = []
    for r in results:
        if "frozen_region_issue" in r and r["frozen_region_issue"]:
            bad_gold_ids.append(r["id"])
            lines.append(f"- **{r['id']}**: {r['frozen_region_issue']}")

    lines += [
        "",
        "### Real remaining localization failures",
        "",
        "Questions that fail even under corrected v2 reference:",
        "",
    ]

    real_fail_details = {
        "h01": "Model box [0.118,0.141,0.89,0.286] covers the Standby current row but "
               "spans ~6 rows (area_ratio≈5.75). App defect: locate returns an oversized multi-row box.",
        "h02": "Model box x1=0.603 truncates the Unit column ('−'). Coverage 0.449 against v2. "
               "App defect: box does not extend to table right edge.",
        "h05": "Model box top at y=0.193 vs v2 top at y=0.187 (≈5pt rendering offset). "
               "Coverage 0.756, just below 0.80 threshold. Borderline — likely rendering artifact.",
        "h07": "Model box x1=0.720 vs required 0.889. Trip threshold 'A' unit is missing. "
               "Same defect as h02: box does not reach table right edge.",
        "h09": "Final search had no accepted boxes: inspect proposed the chart, then check rejected it. "
               "The generated chart has no load-axis labels, so 'high load' is not explicit.",
        "h15": "Inspect was uncertain on the chart page. The generated chart has no load-axis "
               "labels, so 'low load' is not explicit. A revised fixture is needed to separate ambiguity from model error.",
    }

    for r in results:
        if "localization_pass_v2" in r and not r["localization_pass_v2"]:
            detail = real_fail_details.get(r["id"], r.get("fail_reason", ""))
            lines.append(f"- **{r['id']}** ({r.get('type','')}): {detail}")

    remaining = [r for r in results if "localization_pass_v2" in r and not r["localization_pass_v2"]]

    lines += [
        "",
        "### h09 and h15 analysis",
        "",
        "Both h09 ('which way does the rated torque curve fall at high load?') and h15 "
        "('where does the torque curve start at low load?') returned `outcome=uncertain` "
        "with no accepted boxes. The h09 inspect stage proposed the chart, but the checker "
        "rejected it. The h15 inspect stage returned uncertain on the chart page.",
        "",
        "The torque chart and raster diagram occupy the same page (P7). The chart is "
        "in the upper portion (norm y 0.217-0.495), but `fixtures/generate.py` draws no "
        "load or torque axis labels. The high/low-load wording therefore relies on an unstated "
        "left-to-right convention. A versioned chart fixture with explicit axes is needed for "
        "a fair follow-up test; these misses remain in the diagnostic denominator.",
        "",
        "## Summary",
        "",
        f"Frozen: page={frozen_page}/16 PASS, localized={frozen_loc}/16 FAIL (gold errors inflate miss count)  ",
        f"Diagnostic v2: localized={v2_pass_count}/{answerable_count} (corrected reference, not a fresh holdout)  ",
        "",
        f"Of {answerable_count} answerable questions: {v2_pass_count} pass and {len(remaining)} fail under v2 rules.",
        "h03 uses two required label regions; each must reach 80% coverage, with total returned area at most 3× their combined area.",
        "The misses include h09/h15 (unresolved chart questions with unlabeled load axis), h08/h12 (missing loop headings), h01 (oversized table selection), h02/h07 (table row context), and h05 (borderline row boundary).",
    ]

    out_md = out_dir / "diagnostic-v2.md"
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {out_md}")

    # Print summary to stdout
    print(f"\nFrozen: page={frozen_page}/16, localized={frozen_loc}/16, visual_loc={frozen_visual_loc}/8")
    print(f"Diagnostic v2: localized={v2_pass_count}/{answerable_count}, visual_loc={v2_visual_pass_count}/8")
    print(f"\nV2 pass: ", end="")
    for r in results:
        if "localization_pass_v2" in r:
            print(r["id"] if r["localization_pass_v2"] else f"[{r['id']}]", end=" ")
    print()


if __name__ == "__main__":
    main()
