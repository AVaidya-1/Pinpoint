# Round 002 context: Import and viewer vertical slice (revised)

## Goal
Deliver the first vertical slice of Visual Evidence: upload PDF/image,
select pages, render canonical rasters, persist documents and pages in SQLite,
and display them in a zoomable React viewer with a deterministic test overlay.

This round revises round-001 to address F2 review findings
(message `20260913211503225_0c057663a82c474ca5c16f1324d5318d`).

## Prior evidence
- Tracked baseline is clean at commit `20a8ed4` on `codex/app-build`.
  Only expected untracked plan files exist under `docs/tasks/round-001/`
  and `docs/tasks/round-002/` (confirmed via `git status`).
- No backend or frontend application code exists yet. `app_tools/preflight.py`
  exists as a setup utility; backend/frontend runtime implementation is pending.
  Evidence: `app_tools/preflight.py` header and `glob app_tools/*`.
- Setup preflight passed: `out/setup/gemma-20260913T192947078057Z/report.json`
  records successful Gemma locate + full-page-plus-crop checking with
  coverage 0.99, area ratio 1.0033 on a synthetic image.
  Evidence: `out/setup/gemma-20260913T192947078057Z/report.json`.
- All four role smoke tests passed.
  Evidence: `out/setup/smoke-results.json`.
- Orchestration pilot passed with worker artifact and both foremen reviews.
  Evidence: `out/orchestration_pilot/a972fef9b8604a88a62a1fa4527b75e8/`.
- Python 3.14.3, Node v24.14.1 available. `uv` installed at
  `C:/Users/vaidy/.local/bin/uv.exe` (not on default PATH).
  Three API keys in .env: GEMINI_API_KEY, OPENROUTER_KEY, NVIDIA_API_KEY.
- Five real test PDFs in `fixtures/documents/` (gitignored):
  Raspberry Pi Pico (18MB), NE555 (2.3MB), Lippert diagnostics (864KB),
  Prusa MK3S+ (2.7MB), FAA Handbook (1.7MB).
  Evidence: `fixtures/documents/Testing documents readme.md`.

## Director guidance
From `out/orchestration/runtime/director_plan.md`:
- Plan bounded IMPORT_VIEWER_SLICE first.
- Success requires selected-page import, preserved originals, correct
  physical-page identity, and inspected overlay alignment through zoom,
  pan, rotation and crop cases.
- Failure should produce a specific coordinate or ingestion diagnosis.
- Establish a real model-produced region early in a subsequent round.

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
