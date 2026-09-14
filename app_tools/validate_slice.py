"""Independent validator for the import/viewer slice.

Reads only raw evidence (command-results, configs, dom-bounds, e2e-evidence,
restart-evidence, screenshots, fixtures, canonical rasters). Never reads
report.json except in --verify-report mode.

Exit code reflects the actual check outcome (never predicted). The eighth
command-record entry is appended by the caller from the captured process
exit; afterwards `--finalize-counts` verifies the resulting eight-entry
record and finalizes command_count_valid/command_order_valid BEFORE the
report hashes validation.json. `--verify-report` (post-report) writes the
verification receipt.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "out" / "orchestration" / "import-viewer"

EXPECTED_COMMANDS = [
    "uv sync",
    "npm ci",
    "playwright install",
    "fixture generate",
    "pytest",
    "vite build",
    "playwright test",
    "validator",
]

TRACKED_FILES = [
    "backend/pyproject.toml",
    "backend/uv.lock",
    "backend/app/__init__.py",
    "backend/app/config.py",
    "backend/app/db.py",
    "backend/app/schemas.py",
    "backend/app/geometry.py",
    "backend/app/ingestion.py",
    "backend/app/jobs.py",
    "backend/app/main.py",
    "backend/tests/__init__.py",
    "backend/tests/test_geometry.py",
    "backend/tests/test_upload.py",
    "backend/tests/test_lifecycle.py",
    "fixtures/generate.py",
    "fixtures/development.json",
    "fixtures/holdout.json",
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/tsconfig.json",
    "frontend/vite.config.ts",
    "frontend/index.html",
    "frontend/src/main.tsx",
    "frontend/src/App.tsx",
    "frontend/src/App.css",
    "frontend/src/api.ts",
    "frontend/src/components/DocumentList.tsx",
    "frontend/src/components/PageViewer.tsx",
    "frontend/src/components/QuestionBar.tsx",
    "frontend/src/components/EvidenceList.tsx",
    "frontend/tests/e2e.spec.ts",
    "frontend/playwright.config.ts",
    "app_tools/dev.py",
    "app_tools/e2e_harness.py",
    "app_tools/validate_slice.py",
    ".env.example",
]

EVIDENCE_FILES = [
    "out/orchestration/import-viewer/report.json",
    "out/orchestration/import-viewer/validation.json",
    "out/orchestration/import-viewer/dom-bounds.json",
    "out/orchestration/import-viewer/e2e-evidence.json",
    "out/orchestration/import-viewer/restart-evidence.json",
    "out/orchestration/import-viewer/command-results.json",
]

SCREENSHOT_FILES = [
    "out/orchestration/import-viewer/screenshots/upload-pdf.png",
    "out/orchestration/import-viewer/screenshots/upload-image.png",
    "out/orchestration/import-viewer/screenshots/fit.png",
    "out/orchestration/import-viewer/screenshots/zoom100.png",
    "out/orchestration/import-viewer/screenshots/zoom200.png",
    "out/orchestration/import-viewer/screenshots/pan.png",
    "out/orchestration/import-viewer/screenshots/resize.png",
    "out/orchestration/import-viewer/screenshots/orientation-portrait.png",
    "out/orchestration/import-viewer/screenshots/orientation-landscape.png",
    "out/orchestration/import-viewer/screenshots/orientation-cropbox.png",
    "out/orchestration/import-viewer/screenshots/orientation-exif-jpeg.png",
    "out/orchestration/import-viewer/screenshots/orientation-standard-png.png",
    "out/orchestration/import-viewer/screenshots/delete.png",
]

FIXTURE_FILES = [
    "fixtures/generated/test_pages.pdf",
    "fixtures/generated/portrait.pdf",
    "fixtures/generated/landscape.pdf",
    "fixtures/generated/cropbox.pdf",
    "fixtures/generated/exif_oriented.jpg",
    "fixtures/generated/standard.png",
    "fixtures/generated/manifest.json",
]

EXPECTED_PRE_RECEIPT_ARTIFACTS = sorted(
    TRACKED_FILES + EVIDENCE_FILES + SCREENSHOT_FILES + FIXTURE_FILES
)
assert len(EXPECTED_PRE_RECEIPT_ARTIFACTS) == 62, len(EXPECTED_PRE_RECEIPT_ARTIFACTS)

TRANSFORM_VIEWS = ["fit", "zoom100", "zoom200", "pan", "resize"]
ORIENTATION_IDS = [
    "orientation_portrait",
    "orientation_landscape",
    "orientation_cropbox",
    "orientation_exif_jpeg",
    "orientation_standard_png",
]
REQUIRED_CONTENTS = {"spec_table", "chart", "flowchart", "schematic", "shapes"}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def sample_signature(path: Path, expected_rgb: list[int], tol: int = 10) -> bool:
    from PIL import Image

    img = Image.open(path).convert("RGB")
    for x in range(4):
        for y in range(4):
            r, g, b = img.getpixel((x, y))
            if abs(r - expected_rgb[0]) > tol or abs(g - expected_rgb[1]) > tol or abs(b - expected_rgb[2]) > tol:
                return False
    return True


def run_validation() -> tuple[dict, bool]:
    v: dict = {}
    ok = True

    def require(name: str, cond: bool) -> bool:
        nonlocal ok
        v[name] = bool(cond)
        if not cond:
            ok = False
        return bool(cond)

    # --- command record (first 7 entries; the 8th is appended by the caller
    # from this process's actual exit code, then --finalize-counts rechecks).
    cmd_path = EVIDENCE / "command-results.json"
    try:
        commands = load_json(cmd_path)
        names7 = [c.get("command") for c in commands]
        first7_ok = names7 == EXPECTED_COMMANDS[0:7] and len(commands) == 7
    except Exception:
        commands = []
        first7_ok = False
    v["command_entries_observed"] = len(commands)
    v["command_first7_valid"] = bool(first7_ok)
    if not first7_ok:
        ok = False
    # Final count/order fields are set by --finalize-counts against the real
    # eight-entry record; never predicted here.
    v["command_count_valid"] = False
    v["command_order_valid"] = False
    v["command_count_pending_append"] = True

    # --- competing server ownership.
    config_text = (ROOT / "frontend" / "playwright.config.ts").read_text(encoding="utf-8")
    spec_text = (ROOT / "frontend" / "tests" / "e2e.spec.ts").read_text(encoding="utf-8")
    require("no_webserver_key", "webServer" not in config_text)
    require(
        "no_spec_lifecycle",
        all(s not in spec_text for s in ("spawn", "taskkill", "kill(", "webServer")),
    )

    # --- tracked artifacts.
    missing = [p for p in TRACKED_FILES if not (ROOT / p).exists()]
    v["artifacts_missing"] = missing
    v["artifacts_count"] = len(TRACKED_FILES) - len(missing)
    require("artifacts_complete", len(missing) == 0)

    # --- exact pre-receipt artifact set (recorded for the receipt; the
    # report copies this array and the receipt checks set equality).
    v["expected_artifact_set"] = EXPECTED_PRE_RECEIPT_ARTIFACTS
    v["expected_artifact_set_count"] = len(EXPECTED_PRE_RECEIPT_ARTIFACTS)
    v["artifacts_set_count"] = len(EXPECTED_PRE_RECEIPT_ARTIFACTS)

    # --- development + holdout ground truth.
    dev = load_json(ROOT / "fixtures" / "development.json")
    holdout = load_json(ROOT / "fixtures" / "holdout.json")
    dev_by_id = {e["fixture_id"]: e for e in dev}
    dev_by_file = {}
    for e in dev:
        dev_by_file.setdefault(e["fixture_file"], []).append(e)

    # --- byte preservation.
    e2e = load_json(EVIDENCE / "e2e-evidence.json")
    hash_pairs = []
    for entry in e2e.get("import_evidence", []):
        fp = ROOT / entry["fixture_path"]
        sp = ROOT / entry["stored_original_path"]
        fh = sha256_file(fp) if fp.exists() else None
        sh = sha256_file(sp) if sp.exists() else None
        uh = entry.get("sha256_at_upload")
        match = fh is not None and sh is not None and fh == sh == uh
        hash_pairs.append({
            "fixture_path": entry["fixture_path"],
            "stored_path": entry["stored_original_path"],
            "fixture_hash": fh,
            "stored_hash": sh,
            "upload_hash": uh,
            "match": match,
        })
    v["hash_pairs"] = hash_pairs
    v["hash_match_count"] = sum(1 for p in hash_pairs if p["match"])
    v["hash_total"] = len(hash_pairs)
    require("hash_all_match", len(hash_pairs) > 0 and all(p["match"] for p in hash_pairs))
    v["hash_nonempty"] = len(hash_pairs) > 0
    if len(hash_pairs) == 0:
        ok = False

    # --- overlay alignment from highlight measurements.
    dom = load_json(EVIDENCE / "dom-bounds.json")
    alignment_results = []
    for entry in dom:
        fid = entry["fixture_id"]
        view = entry["view_name"]
        target = dev_by_id[fid]["target"]
        ib = entry["image_bounds"]
        hb = entry["highlight_bounds"]
        exp = [
            ib["x"] + target[0] * ib["width"],
            ib["y"] + target[1] * ib["height"],
            (target[2] - target[0]) * ib["width"],
            (target[3] - target[1]) * ib["height"],
        ]
        act = [hb["x"], hb["y"], hb["width"], hb["height"]]
        err = max(abs(a - e) for a, e in zip(act, exp))
        alignment_results.append({
            "fixture_id": fid,
            "view_name": view,
            "expected_px": exp,
            "actual_px": act,
            "error_px": err,
            "pass": err <= 2.0,
        })
    v["alignment_results"] = alignment_results
    v["alignment_transform_count"] = sum(1 for r in alignment_results if r["view_name"] in TRANSFORM_VIEWS)
    v["alignment_orientation_count"] = sum(
        1 for r in alignment_results if r["fixture_id"] in ORIENTATION_IDS
    )
    v["alignment_total_count"] = len(alignment_results)
    require("alignment_all_pass", len(alignment_results) == 10 and all(r["pass"] for r in alignment_results))
    require(
        "alignment_views_ok",
        {r["view_name"] for r in alignment_results if r["fixture_id"] == "dev_p5"} == set(TRANSFORM_VIEWS),
    )

    # --- rotation / CropBox / EXIF.
    orientation_results = []
    for fid in ORIENTATION_IDS:
        entry = dev_by_id[fid]
        dom_entries = [d for d in dom if d["fixture_id"] == fid]
        assert dom_entries, f"no dom-bounds entry for {fid}"
        nat = dom_entries[0]["natural_dimensions"]
        dims_ok = (
            abs(nat["width"] - entry["raster_width_px"]) <= 1
            and abs(nat["height"] - entry["raster_height_px"]) <= 1
        )
        # canonical raster on disk via the matching import_evidence entry.
        inv = next(e for e in e2e["import_evidence"] if e["fixture_path"] == entry["fixture_file"])
        page0 = inv["pages"][0]
        sig_ok = sample_signature(ROOT / page0["canonical_raster_path"], entry["signature_rgb"])
        passed = bool(dims_ok and sig_ok)
        orientation_results.append({
            "fixture_id": fid,
            "expected_raster_dims": [entry["raster_width_px"], entry["raster_height_px"]],
            "actual_raster_dims": [nat["width"], nat["height"]],
            "signature_verified": sig_ok,
            "pass": passed,
        })
    v["orientation_results"] = orientation_results
    v["orientation_case_count"] = len(orientation_results)
    require("orientation_all_pass", len(orientation_results) == 5 and all(r["pass"] for r in orientation_results))

    # --- physical-page identity.
    noncontig = e2e["noncontiguous_import"]
    stored_pages = [p["physical_page"] for p in noncontig["pages"]]
    pages_ok = stored_pages == noncontig["selected_pages"]
    sigs_ok = all(
        sample_signature(ROOT / p["canonical_raster_path"], p["expected_signature_rgb"])
        for p in noncontig["pages"]
    )
    v["page_identity_results"] = [{
        "doc_id": noncontig["document_id"],
        "selected_pages": noncontig["selected_pages"],
        "stored_pages": stored_pages,
        "signatures_verified": sigs_ok,
        "pass": bool(pages_ok and sigs_ok),
    }]
    v["page_identity_case_count"] = 1
    require("page_identity_all_pass", bool(pages_ok and sigs_ok))

    # --- holdout structure.
    holdout_errors = []
    if len(holdout) != 20:
        holdout_errors.append(f"expected 20 questions, found {len(holdout)}")
    from collections import Counter

    counts = Counter(q.get("type") for q in holdout)
    split = [counts.get("text", 0), counts.get("table", 0), counts.get("visual", 0), counts.get("absent", 0)]
    v["holdout_question_count"] = len(holdout)
    v["holdout_split"] = split
    v["holdout_split_valid"] = split == [4, 4, 8, 4]
    if split != [4, 4, 8, 4]:
        holdout_errors.append(f"split {split} != [4,4,8,4]")
    holdout_sigs = {tuple(q["expected_page"]) for q in holdout if q.get("expected_page")}
    dev_sigs_all = {tuple(e["signature_rgb"]) for e in dev}
    p6 = (0, 255, 255)
    p7 = (128, 0, 0)
    p8 = (0, 128, 0)
    if holdout_sigs != {p6, p7, p8}:
        holdout_errors.append(f"holdout pages {sorted(holdout_sigs)} != P6-P8 signatures")
    dev_p = {tuple(dev_by_id[f"dev_p{i}"]["signature_rgb"]) for i in range(1, 6)}
    holdout_p = {tuple(dev_by_id[f]["signature_rgb"]) for f in ()} | holdout_sigs
    if dev_p & holdout_p:
        holdout_errors.append("development/holdout page sets overlap")
    for q in holdout:
        if q.get("type") == "absent":
            if q.get("expected_page") is not None or q.get("expected_region") is not None:
                holdout_errors.append(f"{q['id']}: absent question must have null expectations")
        else:
            if not isinstance(q.get("expected_page"), list) or not isinstance(q.get("expected_region"), list):
                holdout_errors.append(f"{q['id']}: answerable question needs page+region")
    contents = {e.get("content") for e in dev}
    if not REQUIRED_CONTENTS.issubset(contents):
        holdout_errors.append(f"missing content kinds: {REQUIRED_CONTENTS - contents}")
    for name in ("test_pages.pdf",):
        if not (ROOT / "fixtures" / "generated" / name).exists():
            holdout_errors.append(f"missing fixture file {name}")
    v["holdout_errors"] = holdout_errors
    require("holdout_valid", len(holdout_errors) == 0)

    # --- dom-bounds completeness.
    orient_ids_present = {d["fixture_id"] for d in dom}
    v["dom_bounds_entry_count"] = len(dom)
    require(
        "dom_bounds_complete",
        len(dom) == 10 and set(ORIENTATION_IDS).issubset(orient_ids_present),
    )

    # --- restart persistence.
    restart = load_json(EVIDENCE / "restart-evidence.json")
    require(
        "restart_persistence_pass",
        bool(restart.get("pass"))
        and len(restart.get("docs_before", [])) > 0
        and restart.get("docs_before") == restart.get("docs_after"),
    )

    # --- capacity enforcement.
    require("capacity_enforced", e2e.get("capacity_enforced") is True)

    # --- screenshots.
    existing = [p for p in SCREENSHOT_FILES if (ROOT / p).exists()]
    v["screenshot_present"] = len(existing) == 13
    v["screenshot_count"] = len(existing)
    v["screenshot_names"] = [Path(p).name for p in existing]
    if len(existing) != 13:
        ok = False
        v["screenshots_missing"] = [p for p in SCREENSHOT_FILES if not (ROOT / p).exists()]

    # --- generated fixture manifest.
    manifest = load_json(ROOT / "fixtures" / "generated" / "manifest.json")["files"]
    fixtures_ok = True
    for name, digest in manifest.items():
        candidate = ROOT / "fixtures" / "generated" / name
        if name in ("development.json", "holdout.json"):
            candidate = ROOT / "fixtures" / name
        if not candidate.exists() or sha256_file(candidate) != digest:
            fixtures_ok = False
    v["fixtures_verified"] = fixtures_ok
    v["fixtures_count"] = len(manifest)
    if not fixtures_ok:
        ok = False

    v["validator_pass"] = bool(ok)
    return v, ok


def write_validation() -> int:
    v, ok = run_validation()
    with open(EVIDENCE / "validation.json", "w", encoding="utf-8") as f:
        json.dump(v, f, indent=2)
        f.write("\n")
    print(f"validator_pass={v['validator_pass']}")
    return 0 if ok else 1


def finalize_counts() -> int:
    """Verify the real eight-entry command record (written after the
    validator's own exit was captured exactly once) and finalize the
    count/order fields before the report hashes validation.json."""
    from collections import Counter
    path = EVIDENCE / "command-results.json"
    v = load_json(EVIDENCE / "validation.json")
    try:
        commands = load_json(path)
        names = [c.get("command") for c in commands]
        exits = [c.get("exit_code") for c in commands]
    except Exception as e:
        print(f"finalize-counts failed to read command-results: {e}")
        return 1
    count_valid = len(commands) == 8
    order_valid = names == EXPECTED_COMMANDS
    all_zero = all(e == 0 for e in exits) and len(exits) == 8
    v["command_count_valid"] = bool(count_valid)
    v["command_order_valid"] = bool(order_valid)
    v["command_count_pending_append"] = False
    v["command_entries_final"] = len(commands)
    v["command_all_zero"] = bool(all_zero)
    if not (count_valid and order_valid):
        print(f"count/order mismatch: {names}")
    else:
        print("command record finalized: 8 entries in order")
    if Counter(names) != Counter(EXPECTED_COMMANDS) or len(names) != 8:
        print(f"duplicate/missing entries: {names}")
        count_valid = False
        order_valid = False
        v["command_count_valid"] = False
        v["command_order_valid"] = False
    with open(EVIDENCE / "validation.json", "w", encoding="utf-8") as f:
        json.dump(v, f, indent=2)
        f.write("\n")
    return 0 if (count_valid and order_valid) else 1


def verify_report() -> int:
    raw = (EVIDENCE / "validation.json").read_bytes()
    computed = sha256_bytes(raw)
    report = load_json(EVIDENCE / "report.json")
    validation = json.loads(raw.decode("utf-8"))
    report_hash = report.get("validation_hash", "")
    hash_match = computed == report_hash
    commands = load_json(EVIDENCE / "command-results.json")
    names = [c.get("command") for c in commands]
    count_valid = names == EXPECTED_COMMANDS and len(commands) == 8
    order_valid = names == EXPECTED_COMMANDS
    exit_fields = [
        ("uv_sync_exit", 0), ("npm_ci_exit", 1), ("playwright_install_exit", 2),
        ("fixture_gen_exit", 3), ("pytest_exit", 4), ("vite_build_exit", 5),
        ("playwright_exit", 6), ("validator_exit", 7),
    ]
    mismatches = []
    for field, idx in exit_fields:
        if report.get("checks", {}).get(field) != commands[idx].get("exit_code"):
            mismatches.append(field)
    command_results_match = (len(mismatches) == 0) and count_valid
    expected_set = set(validation.get("expected_artifact_set", []))
    reported_set = set(report.get("artifacts", []))
    set_valid = expected_set == reported_set and len(expected_set) == 62
    missing = [p for p in report.get("artifacts", []) if not (ROOT / p).exists()]
    all_exist = len(missing) == 0
    receipt = {
        "hash_match": bool(hash_match),
        "computed_hash": computed,
        "report_hash": report_hash,
        "command_results_match": bool(command_results_match),
        "command_count_valid": bool(count_valid),
        "command_order_valid": bool(order_valid),
        "command_mismatches": mismatches,
        "artifacts_all_exist": bool(all_exist),
        "artifacts_set_valid": bool(set_valid),
        "artifacts_set_count": len(reported_set) if set_valid else len(reported_set),
        "artifacts_missing": missing,
        "all_verified": bool(hash_match and command_results_match and count_valid
                              and order_valid and all_exist and set_valid),
    }
    with open(EVIDENCE / "verification-receipt.json", "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2)
        f.write("\n")
    print(f"all_verified={receipt['all_verified']}")
    return 0 if receipt["all_verified"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-report", action="store_true")
    parser.add_argument("--finalize-counts", action="store_true")
    args = parser.parse_args()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if args.verify_report:
        return verify_report()
    if args.finalize_counts:
        return finalize_counts()
    return write_validation()


if __name__ == "__main__":
    sys.exit(main())
