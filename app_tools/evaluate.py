"""Task 6: live holdout evaluation against the frozen suite.

Runs the real backend in-process (starlette TestClient over app.main:app)
with a dedicated data dir under out/evaluation/data, uploads the generated
holdout fixture PDF, executes every holdout question through the real search
API (live Gemini calls; never stubbed), and scores the returned evidence
against the frozen expected pages and regions.

Usage (from the repo root):
    backend/.venv/Scripts/python.exe app_tools/evaluate.py \
        --suite fixtures/holdout.json --live

Output:
    out/evaluation/report.json  - structured per-question results
    out/evaluation/summary.txt  - human-readable threshold summary

Honesty rules (spec section 15B): a live call failure counts against the
question (never dropped); if execution is quota-blocked the evaluation is
marked incomplete; a threshold miss reports "technical hypothesis not yet
validated"; fixture answers are never substituted for real results.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
OUT_DIR = ROOT / "out" / "evaluation"
DATA_DIR = OUT_DIR / "data"

THRESHOLDS = {
    "correct_page": 14,       # of 16 answerable
    "localized": 12,          # of 16 answerable
    "visual_localized": 6,    # of 8 visual
    "absent_correct": 3,      # of 4 absent
}
COVERAGE_MIN = 0.8
AREA_RATIO_MAX = 3.0
GRID = 200  # raster-mask resolution for the localization metric


def _resolve(path_str: str) -> Path:
    p = Path(path_str)
    if p.is_absolute() and p.exists():
        return p
    for base in (Path.cwd(), ROOT):
        cand = base / path_str
        if cand.exists():
            return cand
    return (ROOT / path_str).resolve()


def _mask(box: list[float]) -> set[tuple[int, int]]:
    """Grid cells covered by a normalized [x0, y0, x1, y1] box."""
    x0, y0, x1, y1 = box
    cx0 = max(0, min(GRID - 1, int(x0 * GRID)))
    cy0 = max(0, min(GRID - 1, int(y0 * GRID)))
    # Cells whose index is < x1*GRID are inside (ceil boundary).
    cx1 = max(0, min(GRID, int(-(-x1 * GRID // 1))))
    cy1 = max(0, min(GRID, int(-(-y1 * GRID // 1))))
    return {(cx, cy) for cx in range(cx0, cx1) for cy in range(cy0, cy1)}


def localization(expected_region: list[float],
                 boxes: list[list[float]]) -> tuple[float, float, bool]:
    """Raster-mask localization metric.

    Returns (coverage_ratio, area_ratio, passed): the union of the returned
    boxes must cover >= 80% of the expected region while occupying <= 3x its
    area. A whole-page box on a small target fails the area bound.
    """
    expected = _mask(expected_region)
    if not expected:
        return 0.0, float("inf"), False
    union: set[tuple[int, int]] = set()
    for b in boxes:
        union |= _mask(b)
    coverage = len(union & expected) / len(expected)
    area_ratio = (len(union) / len(expected)) if union else 0.0
    return coverage, area_ratio, bool(coverage >= COVER_MIN and area_ratio <= AREA_RATIO_MAX)


def localization_regions(expected_regions: list[list[float]],
                         boxes: list[list[float]]) -> tuple[float, float, bool, list[float]]:
    """Require each distinct evidence component while counting union area once."""
    required = [_mask(region) for region in expected_regions]
    if not required or any(not region for region in required):
        return 0.0, float("inf"), False, []
    gold_union = set().union(*required)
    actual_union = set().union(*(_mask(box) for box in boxes)) if boxes else set()
    per_region = [len(actual_union & region) / len(region) for region in required]
    coverage = min(per_region)
    area_ratio = len(actual_union) / len(gold_union) if gold_union else float("inf")
    return coverage, area_ratio, bool(coverage >= COVERAGE_MIN and area_ratio <= AREA_RATIO_MAX), per_region


COVER_MIN = COVERAGE_MIN  # alias kept next to use site


def sample_signature(png_bytes: bytes, tol: int = 10) -> tuple[int, int, int]:
    """Top-left 4x4 signature color of a canonical page raster."""
    from PIL import Image

    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    rs = gs = bs = n = 0
    for x in range(4):
        for y in range(4):
            r, g, b = img.getpixel((x, y))
            rs += r
            gs += g
            bs += b
            n += 1
    mean = (round(rs / n), round(gs / n), round(bs / n))
    return mean


def signature_matches(observed: tuple[int, int, int], expected: list[int],
                      tol: int = 10) -> bool:
    return all(abs(o - e) <= tol for o, e in zip(observed, expected))


def main() -> int:
    global OUT_DIR, DATA_DIR
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", required=True, help="Holdout suite JSON")
    parser.add_argument("--pdf", default=str(ROOT / "fixtures" / "generated" / "test_pages.pdf"),
                        help="Fixture PDF (default: fixtures/generated/test_pages.pdf)")
    parser.add_argument("--out-dir", default=str(OUT_DIR),
                        help="Separate output directory for a new evaluation run")
    parser.add_argument("--manifest", help="Optional frozen SHA-256 manifest for PDF and suite")
    parser.add_argument("--live", action="store_true",
                        help="Required: permits live Gemini API calls")
    args = parser.parse_args()
    OUT_DIR = Path(args.out_dir).resolve()
    DATA_DIR = OUT_DIR / "data"
    if not args.live:
        print("refusing to run without --live (real model calls)"); return 2

    suite_path = _resolve(args.suite)
    pdf_path = _resolve(args.pdf)
    if args.manifest:
        manifest = json.loads(_resolve(args.manifest).read_text(encoding="utf-8"))
        for actual_path, key in ((suite_path, "suite_sha256"), (pdf_path, "pdf_sha256")):
            observed = hashlib.sha256(actual_path.read_bytes()).hexdigest()
            if observed != manifest.get(key):
                print(f"Frozen input hash mismatch: {actual_path} ({key})")
                return 2
    holdout = json.loads(suite_path.read_text(encoding="utf-8"))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": None,
        "fixture": str(suite_path.relative_to(ROOT) if suite_path.is_relative_to(ROOT) else suite_path),
        "fixture_pdf": str(pdf_path.relative_to(ROOT) if pdf_path.is_relative_to(ROOT) else pdf_path),
        "backend": f"in-process TestClient (uvicorn-equivalent ASGI), dedicated data dir {DATA_DIR}",
        "status": "incomplete",
        "thresholds": {},
        "questions": [],
        "totals": {},
    }

    def finish(exit_code: int) -> int:
        (OUT_DIR / "report.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8")
        write_summary(report)
        print(f"report: {OUT_DIR / 'report.json'}")
        print(f"summary: {OUT_DIR / 'summary.txt'}")
        return exit_code

    # Dedicated data dir; start from an EMPTY one each run so the evaluation
    # always measures current backend code without reusing previous results.
    from dotenv import load_dotenv  # noqa: E402

    load_dotenv(ROOT / ".env", override=False)  # GEMINI_API_KEY
    import shutil  # noqa: E402

    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)
    os.environ["EVIDENCE_DATA_DIR"] = str(DATA_DIR)
    sys.path.insert(0, str(BACKEND_DIR))

    from app.config import get_settings  # noqa: E402

    settings = get_settings()
    report["model"] = settings.model
    report["pipeline"] = ("PDF text extraction at import for candidate "
                          "screening; per-search Gemma visual inspection "
                          "and evidence checking on page images")
    if not settings.key_present:
        report["status"] = "incomplete"
        report["blocker"] = "missing GEMINI_API_KEY; live evaluation skipped per task 6"
        print("BLOCKED: no GEMINI_API_KEY")
        return finish(1)

    from starlette.testclient import TestClient  # noqa: E402
    from app.main import app  # noqa: E402
    from app.providers import gemma  # noqa: E402

    # --- live-call accounting -------------------------------------------------
    state = {"current": None}
    call_counts: Counter[str] = Counter()
    failures: dict[str, list[dict]] = {}

    def _wrap(module, name, stage):
        real = getattr(module, name, None)
        if real is None:
            return

        def counting(*a, **kw):
            qid = state["current"] or "<setup>"
            call_counts[qid] += 1
            try:
                result = real(*a, **kw)
            except Exception as e:  # noqa: BLE001 - recorded, then re-raised
                failures.setdefault(qid, []).append(
                    {"stage": stage, "kind": type(e).__name__,
                     "code": getattr(e, "code", None)})
                raise
            # Providers that return [] on any error (e.g. Nemotron's parse)
            # must surface failures; an empty parse is recorded as degraded.
            if stage.startswith("parse") and result == []:
                failures.setdefault(qid, []).append(
                    {"stage": stage, "kind": "empty_parse",
                     "code": "provider_returned_no_elements"})
            return result

        setattr(module, name, counting)
        return counting

    _wrap(gemma, "inspect_page", "inspect")
    _wrap(gemma, "check_evidence", "check")

    # Clear stale 'running'/'queued' job rows left by previously killed
    # evaluator processes; they would otherwise 409 every new search.
    import sqlite3  # noqa: E402

    db_file = DATA_DIR / "evidence.db"
    if db_file.exists():
        conn = sqlite3.connect(db_file)
        conn.execute(
            "UPDATE jobs SET state = 'failed', error_code = 'evaluator_restarted' "
            "WHERE state IN ('queued', 'running')")
        conn.commit()
        conn.close()

    quota_blocked = False
    started = time.monotonic()
    with TestClient(app) as client:
        health = client.get("/api/health").json()
        report["health"] = health
        if not health.get("key_present"):
            report["blocker"] = "backend reports missing API key"
            return finish(1)

        # --- upload + commit the fixture PDF --------------------------------
        # Reuse an already-committed identical document when present (the
        # evaluation data dir persists across resumed runs; the 20-page
        # workspace capacity would otherwise be exhausted by re-commits).
        pdf_bytes = pdf_path.read_bytes()
        doc_id = None
        docs = client.get("/api/documents").json()
        for d in docs.get("documents", []):
            if d["status"] != "ready" or d["page_count"] == 0:
                continue
            orig = client.get(f"/api/documents/{d['id']}/original")
            if orig.status_code == 200 and orig.content == pdf_bytes:
                doc_id = d["id"]
                break
        if doc_id is None:
            up = client.post("/api/uploads",
                             files={"file": (pdf_path.name, pdf_bytes, "application/pdf")})
            if up.status_code != 201:
                report["blocker"] = f"upload failed: {up.status_code} {up.text[:200]}"
                return finish(1)
            upload = up.json()
            commit = client.post("/api/documents", json={
                "upload_id": upload["upload_id"],
                "pages": list(range(1, upload["page_count"] + 1)),
            })
            if commit.status_code != 202:
                report["blocker"] = f"commit failed: {commit.status_code} {commit.text[:200]}"
                return finish(1)
            doc_id = commit.json()["document_id"]
        pages = next(d for d in client.get("/api/documents").json()["documents"]
                     if d["id"] == doc_id)["pages"]

        # Extracted-element coverage per page, used for candidate screening.
        import sqlite3 as _sqlite3  # noqa: E402

        _conn = _sqlite3.connect(str(DATA_DIR / "evidence.db"))
        try:
            parsed_map = {
                r[0]: int(r[1])
                for r in _conn.execute("SELECT id, parsed FROM pages").fetchall()
            }
            elem_counts = dict(
                _conn.execute(
                    "SELECT page_id, COUNT(*) FROM page_elements GROUP BY page_id"
                ).fetchall()
            )
        except _sqlite3.Error:
            parsed_map, elem_counts = {}, {}
        finally:
            _conn.close()
        report["parsed_pages"] = sum(1 for p in pages if parsed_map.get(p["id"]))
        report["total_pages"] = len(pages)
        report["elements_per_page"] = {
            p["id"]: elem_counts.get(p["id"], 0) for p in pages}
        report["import_live_calls"] = call_counts.get("<setup>", 0)
        if failures.get("<setup>"):
            report["import_failures"] = failures["<setup>"]

        # --- map page signature -> page_id -----------------------------------
        sig_pages: dict[tuple[int, int, int], str] = {}
        for p in pages:
            img = client.get(f"/api/pages/{p['id']}/image")
            sig = sample_signature(img.content)
            sig_pages[sig] = p["id"]
        report["page_signatures"] = {str(k): v for k, v in sig_pages.items()}

        # --- run every question ----------------------------------------------
        results: dict[str, dict] = {}
        for q in holdout:
            qid = q["id"]
            qtype = q["type"]
            entry = {
                "id": qid,
                "type": qtype,
                "question": q["question"],
                "expected_page_sig": q.get("expected_page"),
                "expected_region": q.get("expected_region"),
                "expected_regions": q.get("expected_regions"),
                "actual_page_correct": None,
                "actual_boxes": [],
                "localization_pass": None,
                "coverage_ratio": None,
                "area_ratio": None,
                "api_calls": 0,
                "latency_ms": 0,
                "error": None,
            }
            results[qid] = entry  # assignment before work: never duplicated
            state["current"] = qid
            t0 = time.monotonic()
            try:
                created = client.post("/api/searches", json={
                    "question": q["question"],
                    "document_ids": [doc_id],
                    # No force_refresh: the provider cache key includes the
                    # question, model and page raster, so reuse across runs
                    # is exact and lets an interrupted run resume.
                    "force_refresh": False,
                })
                entry["latency_ms"] = int((time.monotonic() - t0) * 1000)
                if created.status_code != 202:
                    raise RuntimeError(
                        f"search create failed: {created.status_code} "
                        f"{created.text[:200]}")
                search_id = created.json()["search_id"]
                res = client.get(f"/api/searches/{search_id}").json()
                entry["outcome"] = res.get("outcome")
                entry["search_id"] = search_id
                evidence = res.get("evidence", [])
                entry["evidence_groups"] = len(evidence)

                if qtype == "absent":
                    # Correct behavior: no accepted evidence anywhere.
                    entry["actual_page_correct"] = len(evidence) == 0
                    entry["absent_correct"] = len(evidence) == 0
                    entry["actual_boxes"] = [
                        {"page_id": e["page_id"], "boxes": e["boxes"]} for e in evidence
                    ]
                else:
                    expected_page_id = next(
                        (pid for sig, pid in sig_pages.items()
                         if signature_matches(sig, q["expected_page"])), None)
                    entry["expected_page_id"] = expected_page_id
                    on_page = [e for e in evidence if e["page_id"] == expected_page_id]
                    boxes = [b for e in on_page for b in e["boxes"]]
                    entry["actual_boxes"] = boxes
                    entry["actual_page_correct"] = bool(on_page)
                    if boxes:
                        required_regions = q.get("expected_regions")
                        if required_regions:
                            cov, ar, passed, per_region = localization_regions(required_regions, boxes)
                            entry["per_region_coverage"] = [round(value, 4) for value in per_region]
                        else:
                            cov, ar, passed = localization(q["expected_region"], boxes)
                        entry["coverage_ratio"] = round(cov, 4)
                        entry["area_ratio"] = round(ar, 4)
                        entry["localization_pass"] = bool(passed)
                    else:
                        entry["localization_pass"] = False
                if failures.get(qid):
                    kinds = {f["kind"] for f in failures[qid]}
                    codes = {f.get("code") for f in failures[qid]}
                    entry["error"] = "live call failure(s): " + ", ".join(
                        sorted(kinds | {str(c) for c in codes if c}))
                    if "quota" in codes:
                        quota_blocked = True
            except Exception as e:  # noqa: BLE001 - never drop a question
                entry["latency_ms"] = int((time.monotonic() - t0) * 1000)
                entry["error"] = f"evaluator error: {e}"
            entry["api_calls"] = call_counts[qid]
            print(f"[{qid}] outcome={entry.get('outcome')} "
                  f"calls={entry['api_calls']} err={entry['error']}", flush=True)
            if quota_blocked:
                report["abort_reason"] = "quota-blocked; remaining questions not attempted"
                break
        for q in holdout:
            if q["id"] not in results:
                results[q["id"]] = {
                    "id": q["id"], "type": q["type"], "question": q["question"],
                    "expected_page_sig": q.get("expected_page"),
                    "expected_region": q.get("expected_region"),
                    "actual_page_correct": None, "actual_boxes": [],
                    "localization_pass": None, "coverage_ratio": None,
                    "area_ratio": None, "api_calls": 0, "latency_ms": 0,
                    "error": "not attempted: " + report.get("abort_reason", "aborted"),
                }
        report["questions"] = [results[q["id"]] for q in holdout]

    # --- scoring ---------------------------------------------------------------
    answerable = [e for e in report["questions"] if e["type"] != "absent"]
    absent = [e for e in report["questions"] if e["type"] == "absent"]
    visual = [e for e in answerable if e["type"] == "visual"]

    correct_page = sum(1 for e in answerable if e["actual_page_correct"])
    localized = sum(1 for e in answerable if e["localization_pass"])
    visual_loc = sum(1 for e in visual if e["localization_pass"])
    absent_ok = sum(1 for e in absent if e.get("absent_correct"))

    report["thresholds"] = {
        "correct_page": {"required": THRESHOLDS["correct_page"],
                         "actual": correct_page,
                         "pass": correct_page >= THRESHOLDS["correct_page"]},
        "localized": {"required": THRESHOLDS["localized"], "actual": localized,
                      "pass": localized >= THRESHOLDS["localized"]},
        "visual_localized": {"required": THRESHOLDS["visual_localized"],
                             "actual": visual_loc,
                             "pass": visual_loc >= THRESHOLDS["visual_localized"]},
        "absent_correct": {"required": THRESHOLDS["absent_correct"],
                           "actual": absent_ok,
                           "pass": absent_ok >= THRESHOLDS["absent_correct"]},
    }
    report["answerable_evaluated"] = len(answerable)
    report["absent_evaluated"] = len(absent)
    report["visual_evaluated"] = len(visual)

    q_by_id = {q["id"]: q for q in holdout}
    false_pos = 0
    total_groups = 0
    for e in report["questions"]:
        q = q_by_id[e["id"]]
        groups = e.get("evidence_groups")
        if groups is None:  # absent entries store boxes differently
            groups = len(e["actual_boxes"]) if q["type"] == "absent" else 0
        total_groups += groups
        if q["type"] == "absent":
            false_pos += len(e["actual_boxes"])
        else:
            fp_boxes_groups = max(0, groups - (1 if e["actual_page_correct"] else 0))
            false_pos += fp_boxes_groups
    report["totals"] = {
        "total_api_calls": sum(call_counts.values()),
        "total_latency_ms": sum(e["latency_ms"] for e in report["questions"]),
        "evaluation_wall_seconds": round(time.monotonic() - started, 1),
        "false_positive_groups": false_pos,
        "total_evidence_groups": total_groups,
        "live_call_failures": sum(len(v) for v in failures.values()),
    }

    attempted = sum(1 for e in report["questions"]
                    if e["error"] is None or "not attempted" not in e["error"])
    clean_errors = [e for e in report["questions"]
                    if e["error"] and "not attempted" not in e["error"]]
    if quota_blocked:
        report["status"] = "incomplete"
        report["blocker"] = "quota-blocked"
    elif len(report["questions"]) < len(holdout):
        report["status"] = "incomplete"
        report["blocker"] = report.get("abort_reason", "aborted early")
    else:
        # All questions evaluated. Questions whose scans had live call
        # failures carry a per-question error and their partial results count
        # against the thresholds (failures are never dropped), per spec.
        report["status"] = "complete"
        if clean_errors:
            report["notes"] = (
                f"{len(clean_errors)} question(s) had live call failures; "
                "reported per-question and counted in the denominators")
    _ = attempted
    all_pass = all(t["pass"] for t in report["thresholds"].values())
    report["verdict"] = ("thresholds met" if (report["status"] == "complete" and all_pass)
                         else "technical hypothesis not yet validated")
    return finish(0 if report["status"] == "complete" else 1)


def write_summary(report: dict) -> None:
    lines = []
    lines.append("Holdout live evaluation summary")
    lines.append(f"timestamp: {report.get('timestamp')}")
    lines.append(f"model: {report.get('model')}")
    if report.get("pipeline"):
        lines.append(f"pipeline: {report['pipeline']}")
    if report.get("parsed_pages") is not None:
        lines.append(f"pages with extracted elements: {report['parsed_pages']}/{report.get('total_pages')}")
    if report.get("import_failures"):
        lines.append(f"import-stage issues: {len(report['import_failures'])} "
                     f"({ {f['kind'] for f in report['import_failures']} })")
    lines.append(f"import live calls: {report.get('import_live_calls')}")
    lines.append(f"status: {report.get('status')}")
    if report.get("blocker"):
        lines.append(f"blocker: {report['blocker']}")
    lines.append(f"verdict: {report.get('verdict', 'n/a')}")
    lines.append("")
    th = report.get("thresholds", {})
    labels = {
        "correct_page": "Correct source page (answerable)",
        "localized": "Sufficiently localized (answerable)",
        "visual_localized": "Visual questions localized",
        "absent_correct": "Absent questions with no evidence",
    }
    for key, label in labels.items():
        t = th.get(key)
        if not t:
            lines.append(f"{label}: not evaluated")
            continue
        lines.append(f"{label}: {t['actual']} (need >= {t['required']}) "
                     f"-> {'PASS' if t['pass'] else 'FAIL'}")
    lines.append("")
    lines.append("Per-question:")
    for e in report.get("questions", []):
        bits = [e["id"], e["type"]]
        if e["type"] == "absent":
            bits.append("absent_ok=" + str(e.get("absent_correct")))
        else:
            bits.append(f"page_ok={e.get('actual_page_correct')}")
            bits.append(f"loc_ok={e.get('localization_pass')}")
            if e.get("coverage_ratio") is not None:
                bits.append(f"cov={e['coverage_ratio']}")
                bits.append(f"area={e['area_ratio']}")
        bits.append(f"calls={e.get('api_calls')}")
        bits.append(f"ms={e.get('latency_ms')}")
        if e.get("error"):
            bits.append("ERROR: " + str(e["error"]))
        lines.append("  " + " | ".join(str(b) for b in bits))
    tot = report.get("totals", {})
    lines.append("")
    lines.append(f"total live API calls: {tot.get('total_api_calls')}")
    lines.append(f"live call failures: {tot.get('live_call_failures')}")
    lines.append(f"false-positive evidence groups: {tot.get('false_positive_groups')}")
    lines.append(f"total evidence groups: {tot.get('total_evidence_groups')}")
    (OUT_DIR / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
