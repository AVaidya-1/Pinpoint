# Round 003 context: Import and viewer vertical slice (final revision)

## Goal
Deliver the first vertical slice of Visual Evidence: upload PDF/image,
select pages, render canonical rasters, persist documents and pages in SQLite,
and display them in a zoomable React viewer with a deterministic test overlay.

This round revises round-002 to address F2's second REVISE verdict
(message `20260913212805512_0f0b27c1023a4fceb28b94547cbd2c8a`).

## Changes from round-002
1. Added an independent validator (`app_tools/validate_slice.py`) with numeric
   overlay alignment measurements, paired before/after SHA-256 hashes, artifact
   existence checks, and physical-page identity assertions. Its report is gated
   in manifest.json — worker-authored booleans are no longer the sole gate.
2. Reordered steps: dev server (Step 7) now precedes browser tests (Step 8).
   Playwright config is enumerated in outputs. Browser install step is explicit.
   `test:e2e` lifecycle specifies server start/stop.
3. Fixtures now require section 15B content: distractor table, chart with legend,
   repeated labels, raster flowchart, and the 4/4/8/4 development/holdout split.
   Physical-page identity uses distinguishable page markers verified in report.
4. Write boundaries narrowed: `app_tools/dev.py` and `app_tools/validate_slice.py`
   replace broad `app_tools/**`. `APP_README.md` removed (deferred). CSS file and
   Playwright config enumerated in exact outputs.
5. Memory candidate cites durable primary evidence files, not ephemeral commands.

## Prior evidence
- Tracked baseline is clean at commit `20a8ed4` on branch `codex/app-build`.
  Only expected untracked plan files exist under `docs/tasks/round-001/`,
  `docs/tasks/round-002/`, and `docs/tasks/round-003/`.
  Evidence: `git log --oneline -1` yields `20a8ed4`; `git diff HEAD` is empty.
- No backend or frontend application code exists yet. `app_tools/preflight.py`
  exists as a setup utility.
  Evidence: `app_tools/preflight.py` exists; `backend/app/` does not.
- Setup preflight passed: successful Gemma locate + full-page-plus-crop check
  with coverage 0.99, area ratio 1.0033 on a synthetic image.
  Evidence: `out/setup/gemma-20260913T192947078057Z/report.json`.
- All four role smoke tests passed.
  Evidence: `out/setup/smoke-results.json`.
- Orchestration pilot passed with worker artifact and both foremen reviews.
  Evidence: `out/orchestration_pilot/a972fef9b8604a88a62a1fa4527b75e8/`.
- Python 3.14.3, Node v24.14.1 available. `uv` installed at
  `C:/Users/vaidy/.local/bin/uv.exe` (not on default PATH).
  Evidence: `docs/tasks/initial/CONTEXT.md` records these; confirmed by
  `out/setup/smoke-results.json` (which exercises all CLIs).
- Product origin: `C:/Users/vaidy/Documents/Pinpoint/visual-evidence-remote.git`.
  Evidence: `orchestration.json` field `expected_remote`.
- Three API keys in .env: GEMINI_API_KEY, OPENROUTER_KEY, NVIDIA_API_KEY.
  Evidence: `docs/tasks/initial/CONTEXT.md`; `.env` exists and is gitignored.
- Five real test PDFs in `fixtures/documents/` (gitignored):
  Raspberry Pi Pico, NE555, Lippert diagnostics, Prusa MK3S+, FAA Handbook.
  Evidence: `fixtures/documents/Testing documents readme.md`.

## Director guidance
From `out/orchestration/runtime/director_plan.md`:
- Plan bounded IMPORT_VIEWER_SLICE first.
- Success requires selected-page import, preserved originals, correct
  physical-page identity, and inspected overlay alignment through zoom,
  pan, rotation and crop cases.
- Failure should produce a specific coordinate or ingestion diagnosis.
- Establish a real model-produced region early in a subsequent round.
- Owner requested maximizing use of OpenCode/Muse (free model) for
  implementation. Keep planning short and tied to the next concrete task.
  Evidence: messages `20260913212638717` and `20260913212654926`.

## Active owner requirements (from OWNER-CONSOLE and Director QUEUE)
- Use all five real PDFs in `fixtures/documents/` for live evaluation.
  Evidence: messages `20260913210255043` and `20260913210334520`.
- Check actual physical pages and evidence targets; do not assume the
  readme's page references are correct.
- Run bounded selections within the 20-page workspace limit.
- Preserve the separate frozen 20-question holdout and its acceptance
  thresholds (PRODUCT_BRIEF.md section 15B).
- Report software results and live localization quality separately,
  including failures or incomplete evaluation.
- No paid fallback, silent model switch, push, deployment, or
  optional integrations.
- Later build instruction supersedes earlier safe pause.
  Evidence: messages `20260913210255043` and `20260913210334520`
  supersede `20260913204753184` (SAFE-PAUSE).

Note: live evaluation with real PDFs is deferred to a later round
(model integration required first). These requirements are preserved
here for continuity.

## Dependencies and constraints
- Product spec: docs/product/PRODUCT_BRIEF.md (controls scope and acceptance).
- Python 3.12 compatibility target for app env (separate from orchestration).
- Must use `backend/.venv`; preserve root `.venv` for orchestration.
- Fixture generation requires ReportLab + Pillow (PRODUCT_BRIEF.md section 5).
- Ports: backend 8000, frontend 5173, dashboard 8765.
- No paid services, deployment, pushes, or Git commands from worker.
- Worker preference: OpenCode (free model) for implementation.

## What this round does NOT include
- Live model inference (deferred to round after this).
- Live evaluation with real test PDFs (requires model integration).
- Persistence/cache/error behavior beyond basic document storage.
- APP_README.md finalization.
