# Round 001 context: Import and viewer vertical slice

## Goal
Deliver the first vertical slice of Visual Evidence: upload PDF/image,
select pages, render canonical rasters, persist documents and pages in SQLite,
and display them in a zoomable React viewer with a deterministic test overlay.

## Prior evidence
- No application code exists. Git is clean on `codex/app-build`.
- Setup preflight passed: `out/setup/gemma-20260913T192947078057Z/report.json`
  records successful Gemma locate + full-page-plus-crop checking with
  coverage 0.99, area ratio 1.0033 on a synthetic image.
- All four role smoke tests passed: `out/setup/smoke-results.json`.
- Orchestration pilot passed: `out/orchestration_pilot/a972fef9b8604a88a62a1fa4527b75e8/`.
- Python 3.14.3, Node v24.14.1, uv available. Three API keys in .env.
- Five real test PDFs in `fixtures/documents/` (gitignored).

## Director guidance
From `out/orchestration/runtime/director_plan.md`:
- Plan bounded IMPORT_VIEWER_SLICE first.
- Success requires selected-page import, preserved originals, correct
  physical-page identity, and inspected overlay alignment through zoom,
  pan, rotation and crop cases.
- Failure should produce a specific coordinate or ingestion diagnosis.
- Establish a real model-produced region early in a subsequent round.

## Dependencies and constraints
- Product spec: docs/product/PRODUCT_BRIEF.md (controls scope and acceptance).
- Python 3.12 compatibility target for app env (separate from orchestration).
- Must use `backend/.venv`; preserve root `.venv` for orchestration.
- Ports: backend 8000, frontend 5173, dashboard 8765.
- No paid services, deployment, pushes, or Git commands from worker.
- Worker preference: OpenCode (free model) for implementation.

## What this round does NOT include
- Live model inference (deferred to round-002).
- Persistence/cache/error behavior beyond basic document storage.
- Live evaluation with real test PDFs.
- APP_README.md finalization.
