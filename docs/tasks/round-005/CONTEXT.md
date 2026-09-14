# Round 005 context: Import and viewer vertical slice

## Goal
Deliver the first vertical slice of Visual Evidence: upload PDF/image,
select pages, render canonical rasters, persist documents and pages in SQLite,
and display them in a zoomable React viewer with a deterministic test overlay.

This round revises round-004 to address F2's fourth REVISE verdict
(message `20260914015419333_e0cfaa659ba545dbbb0db627a32a0db0`)
and the Director's focused-revision briefing in `director_plan.md`.

## Changes from round-004
1. **Validator ordering fixed**: Independent validation commands now run
   Playwright (`test:e2e`) before the validator. The validator reads
   `dom-bounds.json` (produced by Playwright) and `report.json` (produced
   in Step 9 before the validator runs in Step 10). Step sequence:
   env setup -> fixtures -> backend -> frontend -> pytest -> dev launcher ->
   report skeleton -> Playwright -> validator. No circular dependency.
2. **Highlight rect measurement**: Playwright exports the actual highlight
   `<rect>` element's `getBoundingClientRect()` (not the whole SVG overlay).
   Each entry in `dom-bounds.json` records `image_bounds` (the `<img>` element),
   `highlight_bounds` (the specific `<rect>` element mapped through SVG
   client transforms), `fixture_id` (matching development.json key), and
   `view_name` (one of `fit`, `zoom100`, `zoom200`, `pan`, `resize`). The
   validator compares `highlight_bounds` against independently derived
   expected pixel coordinates from `development.json` ground truth and
   `image_bounds`.
3. **Pixel-decodable page signatures**: Each fixture page embeds a unique
   binary color signature in a fixed 4x4 pixel grid at position (0,0).
   Each page gets a unique RGB value tuple (e.g., P1=(255,0,0), P2=(0,255,0),
   P3=(0,0,255), P4=(255,255,0), P5=(255,0,255), P6=(0,255,255),
   P7=(128,0,0), P8=(0,128,0)). The validator reads the rendered canonical
   raster, samples the 4x4 grid at (0,0), and compares to the expected RGB
   with a tolerance of <=10 per channel. This uniquely identifies each page
   without OCR. `development.json` records each page's signature RGB triple.
4. **Manifest count/set gates**: Added equality gates for exact expected
   counts: `hash_total` = number of imported fixtures, `alignment_view_count`
   = 5 (fit/zoom100/zoom200/pan/resize), `orientation_case_count` = 5
   (portrait/landscape/cropbox/exif-jpeg/standard-png),
   `page_identity_case_count` = 1, `holdout_question_count` = 20.
   Also gates `dom_bounds_entry_count` = expected number of measured entries.
5. **Python version corrected**: System Python is 3.13.14 (confirmed by
   `python --version`). `docs/tasks/initial/CONTEXT.md` records "Python 3.14"
   which is imprecise; the actual version is 3.13.14. The application targets
   Python 3.12 via uv, independent of system Python version.

## Prior evidence
- **Git baseline**: Commit `20a8ed4` on branch `codex/app-build`. No tracked
  diff. Untracked: `docs/tasks/round-001/` through `round-005/` (plan files).
  Evidence: `git log --oneline -1` = `20a8ed4`; `git status --short` shows
  only `?? docs/tasks/round-*` entries. Verified at round-005 planning time.
- **Product origin**: `C:/Users/vaidy/Documents/Pinpoint/visual-evidence-remote.git`.
  Evidence: `orchestration.json` field `expected_remote`.
- **No application code**: `backend/app/` does not exist. `app_tools/preflight.py`
  is a setup utility.
  Evidence: directory listing; `app_tools/preflight.py` exists.
- **Setup preflight**: Gemma locate + full-page-plus-crop check passed with
  coverage 0.99, area ratio 1.0033, model `gemma-4-31b-it`.
  Evidence: `out/setup/gemma-20260913T192947078057Z/report.json`.
- **Role smoke tests**: All four roles (Director, Foreman1, Foreman2, Worker)
  recorded exit code 0.
  Evidence: `out/setup/smoke-results.json`.
- **Pilot passed**: Status PILOT-PASS with worker artifact and both reviews.
  Evidence: `out/orchestration_pilot/a972fef9b8604a88a62a1fa4527b75e8/runtime.json`
  (status=PILOT-PASS), `out/orchestration_pilot/a972fef9b8604a88a62a1fa4527b75e8/f2_review.md`,
  `out/orchestration_pilot/a972fef9b8604a88a62a1fa4527b75e8/logs/pilot_director_dd08c8179c10449aa68c0350ca63f6dc.md`
  (Director acceptance).
- **Host tools**: Python 3.13.14 (`python --version`), Node v24.14.1
  (`node --version`), uv 0.12.13 (`C:/Users/vaidy/.local/bin/uv.exe --version`).
  Evidence: live command output verified at planning time. `docs/tasks/initial/CONTEXT.md`
  records "Python 3.14" imprecisely; actual is 3.13.14. App targets 3.12 via uv.
- **API keys**: GEMINI_API_KEY, OPENROUTER_KEY, NVIDIA_API_KEY present in `.env`.
  Evidence: `docs/tasks/initial/CONTEXT.md` line 14; confirmed by preflight
  at `out/setup/gemma-20260913T192947078057Z/report.json` key_present=true.
- **Fixture documents**: Five real test PDFs in `fixtures/documents/` (gitignored).
  Evidence: `fixtures/documents/Testing documents readme.md`.
- **No product-task execution evidence was found**: No worker implementation
  report, no application artifacts, no product gate files exist.
  Evidence: `out/orchestration/import-viewer/` does not exist.
- **No Worker dispatch**: Communications log shows no worker task dispatch.
  Evidence: `out/orchestration/runtime/communications.md` contains no
  worker-task entries for IMPORT_VIEWER_SLICE.

## Director guidance
From `out/orchestration/runtime/director_plan.md`:
- Plan bounded IMPORT_VIEWER_SLICE first.
- Hypothesis: canonical raster coordinates preserve source identity and overlay
  alignment through selected-page import and viewer transformations.
- Collect actual browser image/overlay bounds before validation; compare against
  independently derived expected geometry; use pixel-decodable page markers.
- Gate artifact completeness, matching hashes, every required viewer
  transformation, orientation case, and physical-page identity explicitly.
- Dispatch OpenCode/Muse Worker immediately after F2 approval.

## Active owner requirements
- Use all five real PDFs for live evaluation (deferred to model round).
  Evidence: messages `20260913210255043` and `20260913210334520`.
- Check actual physical pages; do not assume readme page references.
- Bounded selections within 20-page workspace limit.
- Preserve frozen 20-question holdout and its acceptance thresholds.
- Report software and live quality separately; include failures.
- No paid fallback, silent model switch, push, deployment, optional integrations.
- Maximize use of OpenCode/Muse (free) for implementation.
  Evidence: messages `20260913212638717` and `20260913212654926`.
- Build instruction supersedes earlier safe pause.
  Evidence: messages `20260913210255043` and `20260913210334520`
  supersede `20260913204753184`.

## Dependencies and constraints
- Product spec: docs/product/PRODUCT_BRIEF.md (controls scope and acceptance).
- Python 3.12 compatibility target for app env (separate from orchestration).
- Must use `backend/.venv`; preserve root `.venv` for orchestration.
- Fixture generation requires ReportLab + Pillow.
- Ports: backend 8000, frontend 5173, dashboard 8765.
- No paid services, deployment, pushes, or Git commands from worker.

## What this round does NOT include
- Live model inference (next round).
- Live evaluation with real test PDFs (requires model integration).
- State/error behavior beyond basic document storage (A6-A9).
- APP_README.md finalization.
