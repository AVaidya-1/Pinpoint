# Round 004 context: Import and viewer vertical slice

## Goal
Deliver the first vertical slice of Visual Evidence: upload PDF/image,
select pages, render canonical rasters, persist documents and pages in SQLite,
and display them in a zoomable React viewer with a deterministic test overlay.

This round revises round-003 to address F2's third REVISE verdict
(message `20260913214432584_a4d735abdb2e476883fc13a18685d547`)
and the Director's focused-revision briefing in `director_plan.md`.

## Changes from round-003
1. **Lockfiles as tracked outputs**: `backend/uv.lock` and
   `frontend/package-lock.json` moved from "generated/ignored" to tracked
   allowed-writes and exact-outputs. `.gitignore` excludes neither;
   `PRODUCT_BRIEF.md` section 14 lists them in the committed tree.
2. **Distinct development and holdout pages**: Fixture generator creates
   pages 1–5 for development and pages 6–8 for frozen holdout. All 8 pages
   fit within 20-page capacity. Holdout questions reference only pages 6–8;
   development coordinates reference only pages 1–5. Validator checks
   disjoint page sets, actual content markers, distractor table, chart/legend,
   repeated labels, and raster flowchart — not just JSON counts.
3. **Playwright emits actual DOM bounds before validation**: E2E tests export
   `out/orchestration/import-viewer/dom-bounds.json` with measured image and
   overlay element coordinates for each view (Fit, 100%, 200%, pan, resize).
   The independent validator reads this artifact and compares it against
   independently derived expected geometry from fixture truth. Validator
   does not repeat fixture data — it uses the Playwright-measured actuals.
   Page-marker verification uses pixel sampling at marker locations, not OCR.
4. **Individual manifest gates per Done-when**: Each Done-when criterion
   (artifact completeness, hash match count, view-level alignment, orientation
   cases, page-identity cases) is individually gated via JSON pointer in
   manifest.json, not aggregated behind `/validator_pass` alone.
5. **Durable primary evidence citations**: Every verified fact below cites a
   specific file path that can be inspected.

## Prior evidence
- **Git baseline**: Commit `20a8ed4` on branch `codex/app-build`. No tracked
  diff (`git diff HEAD` is empty). Untracked: `docs/tasks/round-001/`,
  `round-002/`, `round-003/`, `round-004/` (plan files only).
  Evidence: `git log --oneline -1` = `20a8ed4`; `git status --short` shows
  only `?? docs/tasks/round-*` entries.
- **Product origin**: `C:/Users/vaidy/Documents/Pinpoint/visual-evidence-remote.git`.
  Evidence: `orchestration.json` field `expected_remote`.
- **No application code**: `backend/app/` does not exist. `app_tools/preflight.py`
  is a setup utility.
  Evidence: directory listing; `app_tools/preflight.py` exists.
- **Setup preflight**: Gemma locate + full-page-plus-crop check passed with
  coverage 0.99, area ratio 1.0033.
  Evidence: `out/setup/gemma-20260913T192947078057Z/report.json`.
- **Role smoke tests**: All four roles (Director, Foreman1, Foreman2, Worker)
  recorded exit code 0.
  Evidence: `out/setup/smoke-results.json`.
- **Pilot passed**: Status PILOT-PASS with worker artifact and both reviews.
  Evidence: `out/orchestration_pilot/a972fef9b8604a88a62a1fa4527b75e8/runtime.json`
  (status=PILOT-PASS), `out/orchestration_pilot/a972fef9b8604a88a62a1fa4527b75e8/f2_review.md`.
- **Host tools**: Python 3.13.14, Node v24.14.1, uv 0.12.13 at
  `C:/Users/vaidy/.local/bin/uv.exe` (not on default PATH).
  Evidence: `docs/tasks/initial/CONTEXT.md` records these versions.
  Note: CONTEXT.md says Python 3.14; actual `python --version` returns 3.13.14.
  The application targets Python 3.12 via uv, independent of system Python.
- **API keys**: GEMINI_API_KEY, OPENROUTER_KEY, NVIDIA_API_KEY present in `.env`.
  Evidence: `docs/tasks/initial/CONTEXT.md` line 14.
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
