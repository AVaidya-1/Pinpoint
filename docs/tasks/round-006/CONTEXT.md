# Round 006 context: Import and viewer vertical slice

## Goal
Deliver the first vertical slice of Visual Evidence: upload PDF/image,
select pages, render canonical rasters, persist documents and pages in SQLite,
and display them in a zoomable React viewer with a deterministic test overlay.

This round revises round-005 to address F2's fifth REVISE verdict
(message `20260914021010880_a3a716db48484542a78552d07ece3491`)
and the Director's focused-correction briefing in `director_plan.md`.

## Changes from round-005
1. **Acyclic evidence flow**: Reordered so no file is read before it is
   written. Execution sequence: Steps 1-6 (implementation) → Step 7
   (Playwright e2e, produces dom-bounds.json, e2e-evidence.json,
   screenshots) → Step 8 (independent validator, reads raw evidence,
   writes validation.json) → Step 9 (report finalizer, reads command
   exit codes + validation.json, writes report.json with all_pass
   derived from actual results, sets finalized=true). The validator
   never reads report.json. Report.json is the last file written.
   No validation-dependent field is initialized before validation runs.
2. **Orientation: canonical raster dimensions**: Playwright e2e exports
   `natural_dimensions` (naturalWidth, naturalHeight) alongside CSS
   `image_bounds` in dom-bounds.json. The validator checks orientation
   using `natural_dimensions` (actual raster pixel dimensions), not
   CSS layout dimensions. CSS `image_bounds` is retained for overlay
   alignment comparison only.
3. **Explicit manifest gates for all Done-when items**: 37 json_gates
   total. validation.json gates include: `hash_nonempty` (proves
   hash_total > 0), `page_identity_case_count` = 1, `holdout_split_valid`
   (proves [4,4,8,4]), `dom_bounds_entry_count` = 10,
   `restart_persistence_pass`, and `screenshot_present`. report.json
   gates include `checks/finalized` = true (proves report was written
   after validation). Every Done-when item has a corresponding gate.
4. **Python version corrected**: `C:/Python314/python.exe --version`
   reports 3.14.3. The `python` command resolves to a WindowsApps shim
   reporting 3.13.14; it is unreliable. The application targets Python
   3.12 via uv, independent of system Python. Evidence: live command
   output verified at round-006 planning time (2026-09-14).
5. **webServer path fix**: Playwright config `webServer.command` uses
   absolute paths valid from any working directory:
   `C:/Users/vaidy/Documents/Pinpoint/visual-evidence/backend/.venv/Scripts/python.exe`
   and `C:/Users/vaidy/Documents/Pinpoint/visual-evidence/app_tools/dev.py`.
   `webServer.cwd` set to the project root.
6. **CONTEXT.md step numbering aligned**: Step references match the
   actual task document: Step 7 = Playwright, Step 8 = validator,
   Step 9 = report finalizer.

## Prior evidence
- **Git baseline**: Commit `20a8ed4` on branch `codex/app-build`. No tracked
  diff. Untracked: `docs/tasks/round-001/` through `round-006/` (plan files).
  Evidence: `git log --oneline -1` and `git status --short` verified at
  round-006 planning time. No unexpected source files.
- **Product origin**: `C:/Users/vaidy/Documents/Pinpoint/visual-evidence-remote.git`.
  Evidence: `orchestration.json` field `expected_remote`.
- **No application code**: `backend/app/` does not exist. `app_tools/preflight.py`
  is a setup utility. `out/orchestration/import-viewer/` does not exist.
  Evidence: directory listing verified at planning time.
- **No Worker dispatch**: `out/orchestration/runtime/communications.md` contains
  no worker-task entries for IMPORT_VIEWER_SLICE.
  Evidence: searched communications.md at planning time.
- **Setup preflight**: Gemma locate + full-page-plus-crop check passed with
  coverage 0.99, area ratio 1.0033, model `gemma-4-31b-it`, key_present=true.
  Evidence: `out/setup/gemma-20260913T192947078057Z/report.json`.
  Note: preflight proves Gemini key works; it does not prove OpenRouter or NVIDIA keys.
- **Role smoke tests**: All four roles (Director, Foreman1, Foreman2, Worker)
  recorded exit code 0.
  Evidence: `out/setup/smoke-results.json`.
- **Pilot passed**: Status PILOT-PASS with worker artifact and both reviews.
  Evidence: `out/orchestration_pilot/a972fef9b8604a88a62a1fa4527b75e8/runtime.json`
  (status=PILOT-PASS),
  `out/orchestration_pilot/a972fef9b8604a88a62a1fa4527b75e8/f2_review.md` (F2 acceptance),
  `out/orchestration_pilot/a972fef9b8604a88a62a1fa4527b75e8/logs/pilot_director_dd08c8179c10449aa68c0350ca63f6dc.md`
  (Director acceptance).
- **Host tools** (verified at round-006 planning time):
  `C:/Python314/python.exe` = Python 3.14.3.
  `python` shim = 3.13.14 (WindowsApps, unreliable for orchestration).
  Node v24.14.1 (`node --version`).
  uv 0.12.13 (`C:/Users/vaidy/.local/bin/uv.exe --version`).
  App targets Python 3.12 via uv.
- **API keys**: GEMINI_API_KEY, OPENROUTER_KEY, NVIDIA_API_KEY all present
  in `.env` (gitignored). Evidence: verified by reading `.env` key names
  (not values) at planning time. Preflight at
  `out/setup/gemma-20260913T192947078057Z/report.json` confirms Gemini key
  works; OpenRouter and NVIDIA key functionality unverified by preflight.
- **Fixture documents**: Five real test PDFs in `fixtures/documents/` (gitignored):
  ccd-0011565.pdf, FAA excerpt, ne555.pdf, prusa3d manual, RP-008307 datasheet.
  Evidence: `fixtures/documents/Testing documents readme.md` and directory listing.

## Director guidance
From `out/orchestration/runtime/director_plan.md`:
- Establish acyclic evidence flow: executed tests → raw evidence → independent
  validation → finalized report. Never initialize successful verdicts.
- Validate orientation using canonical raster dimensions; retain measured DOM
  bounds for overlay alignment.
- Explicitly gate nonempty hash comparisons, page identity, holdout split,
  DOM completeness, restart persistence and screenshot presence.
- Correct launcher working-directory assumptions and unsupported memory claims.
- Preserve unresolved messages until F2 approves their dispositions.
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
