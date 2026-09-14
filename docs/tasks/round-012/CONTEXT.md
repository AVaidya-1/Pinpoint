# Round-012 context: search and source-region highlighting

Authoritative specification: docs/product/PRODUCT_BRIEF.md.
Product path: C:/Users/vaidy/Documents/Pinpoint/visual-evidence.

## Current state

Round-011 IMPORT_VIEWER_SLICE is PASS (state.json, F1 review at
out/orchestration/runtime/logs/IMPORT_VIEWER_SLICE_f1review0_cf8d21aedaaf4afea404eea1ee676b9d.md).

Working vertical slice exists: PDF/image upload with page selection, rendering
via pypdfium2, canonical/model rasters, zoomable PageViewer with
react-zoom-pan-pinch, persistence in SQLite, capacity enforcement, restart
resilience, document deletion, 13 screenshots, 62 verified artifacts.

Backend has: FastAPI app with /api/health, /api/uploads, /api/documents,
/api/pages/{id}/image, /api/documents/{id}/original. DB schema version 1 with
tables: documents, pages, jobs, schema_version. Geometry module converts
provider [ymin,xmin,ymax,xmax] 0-1000 to app [x0,y0,x1,y1] 0-1. Config reads
all EVIDENCE_* env vars. google-genai is already a dependency.

Frontend has: App.tsx layout with header (capacity, model status), sidebar
(QuestionBar placeholder, DocumentList, EvidenceList placeholder), and
PageViewer. QuestionBar and EvidenceList are stubs awaiting this slice.

Fixtures: 7 generated files in fixtures/generated/ including test_pages.pdf.
fixtures/holdout.json has 20 frozen questions with [4,4,8,4] split.
fixtures/development.json exists.

Backend tests: test_geometry.py, test_upload.py, test_lifecycle.py all pass.
Frontend tests: e2e.spec.ts passes.

## What this round adds

The search path: question input, Gemma page inspection, evidence checking,
result display with rectangular highlight overlays on the existing viewer.
This is PRODUCT_BRIEF.md sections 9, 10, 12 (search endpoints), and section 7
(question/results UI, outcome wording).

## Environment

Three free-tier API keys in .env: GEMINI_API_KEY, OPENROUTER_KEY, NVIDIA_API_KEY.
Setup preflight passed for gemma-4-31b-it via Gemini API
(out/setup/gemma-20260913T192947078057Z/report.json).
uv at C:\Users\vaidy\.local\bin\uv.exe. Node v24.14.1.
