# IMPORT_VIEWER_SLICE

## Bounded deliverable and prior evidence
Read CONTEXT.md and docs/product/PRODUCT_BRIEF.md sections 5, 7, 8, 11, 12, 14, 15B.
In at most 75 minutes implement an import-to-viewer vertical slice.
No backend or frontend application code exists yet; `app_tools/preflight.py`
is a setup utility. Setup preflight evidence is at
out/setup/gemma-20260913T192947078057Z/report.json.

## Allowed writes
Only these paths may be created or modified by this task:
- `backend/pyproject.toml`
- `backend/uv.lock`
- `backend/app/__init__.py`
- `backend/app/config.py`
- `backend/app/db.py`
- `backend/app/schemas.py`
- `backend/app/geometry.py`
- `backend/app/ingestion.py`
- `backend/app/jobs.py`
- `backend/app/main.py`
- `backend/tests/__init__.py`
- `backend/tests/test_geometry.py`
- `backend/tests/test_upload.py`
- `backend/tests/test_lifecycle.py`
- `fixtures/generate.py`
- `fixtures/development.json`
- `fixtures/holdout.json`
- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/tsconfig.json`
- `frontend/vite.config.ts`
- `frontend/index.html`
- `frontend/src/main.tsx`
- `frontend/src/App.tsx`
- `frontend/src/App.css`
- `frontend/src/api.ts`
- `frontend/src/components/DocumentList.tsx`
- `frontend/src/components/PageViewer.tsx`
- `frontend/src/components/QuestionBar.tsx`
- `frontend/src/components/EvidenceList.tsx`
- `frontend/tests/e2e.spec.ts`
- `frontend/playwright.config.ts`
- `app_tools/dev.py`
- `app_tools/validate_slice.py`
- `.env.example`

Generated/ignored outputs (not committed but allowed to create):
- `backend/.venv/` (generated, gitignored)
- `frontend/node_modules/` (generated, gitignored)
- `fixtures/generated/` (generated, gitignored)
- `data/` (runtime data, gitignored)
- `out/orchestration/import-viewer/**` (evidence output)

Do not modify scripts/, orchestration.json, owner/product policy, prior task
contracts, review/memory/stop records, Git metadata or credentials. No Git
commands, hidden agents, pushes, paid services, deployment or external messaging.

## Prohibitions
- Do not call any model API or insert fixture answers into a live provider path.
- Do not modify root .venv, scripts/, orchestration.json or docs/orchestration/.
- Do not run Git commands or push.
- Do not weaken acceptance criteria or fabricate PASS results.
- Do not install paid dependencies or services.
- Do not write to `APP_README.md` (deferred to later round).
- Do not write to any `app_tools/` path other than `dev.py` and `validate_slice.py`.

## Ordered procedure

### Step 1: Environment and dependencies
1. Create backend/pyproject.toml with Python >=3.12 dependencies: fastapi,
   uvicorn[standard], python-multipart, python-dotenv, pypdfium2, Pillow,
   pydantic, google-genai (for later use), httpx, reportlab, pytest,
   pytest-asyncio.
2. Create frontend/package.json with React 18, TypeScript, Vite,
   react-zoom-pan-pinch, Playwright, and @playwright/test as dependencies.
   Include `"test:e2e": "npx playwright test --config playwright.config.ts"`
   and `"build": "vite build"` in scripts.
3. Run `C:/Users/vaidy/.local/bin/uv.exe sync --project backend --python 3.12`
   to create backend/.venv and backend/uv.lock.
4. Run `npm --prefix frontend install` to generate frontend/package-lock.json,
   then `npm --prefix frontend ci` to verify clean install.
5. Run `npx --prefix frontend playwright install chromium` to install Playwright
   browser (required by PRODUCT_BRIEF.md section 14).
6. Verify backend/.venv exists and root .venv is untouched.

Expected outputs from this step:
- backend/pyproject.toml (tracked)
- backend/uv.lock (tracked)
- frontend/package.json (tracked)
- frontend/package-lock.json (tracked)
- backend/.venv/ (generated, gitignored)
- frontend/node_modules/ (generated, gitignored)

### Step 2: Fixture generation
1. Create fixtures/generate.py that produces fixtures/generated/ containing:

   **Development pages (pages 1–5)** — used for geometry testing and iteration:
   - Page 1: A specification table with a known target row AND at least
     two plausible distractor rows with similar labels/units (section 15B).
     Page marker: `PAGE_MARKER_P1`.
   - Page 2: A chart/plot with labeled axes, legend, and a target curve
     region (section 15B). Page marker: `PAGE_MARKER_P2`.
   - Page 3: A raster-only flowchart with decision nodes and branches,
     no searchable text layer (section 15B). Page marker: `PAGE_MARKER_P3`.
   - Page 4: A connector/schematic diagram with repeated labels appearing
     on different sub-diagrams (section 15B). Page marker: `PAGE_MARKER_P4`.
   - Page 5: A simple geometric shapes page with known overlay targets
     at exact coordinates for geometry testing. Page marker: `PAGE_MARKER_P5`.

   **Holdout pages (pages 6–8)** — frozen evaluation content, disjoint from
   development pages:
   - Page 6: A specification table with a target row and distractor rows
     (distinct content from page 1). Page marker: `PAGE_MARKER_P6`.
   - Page 7: A chart with legend and a raster diagram region
     (distinct content from pages 2–3). Page marker: `PAGE_MARKER_P7`.
   - Page 8: A schematic with repeated labels and an absent-answer region
     (distinct content from page 4). Page marker: `PAGE_MARKER_P8`.

   **Orientation fixtures** (separate files, all development):
   - A portrait PDF page with page marker `PAGE_MARKER_PORTRAIT` and a
     known overlay target at documented coordinates.
   - A Rotate=90 landscape PDF page with page marker `PAGE_MARKER_LANDSCAPE`
     and a known overlay target at documented coordinates.
   - A PDF with non-default CropBox, page marker `PAGE_MARKER_CROPBOX`,
     and a known overlay target at documented coordinates.
   - An EXIF-oriented JPEG image with a known target region.
   - A standard PNG image with a known target region.

   Each page marker must be rendered at a fixed, documented pixel location
   (e.g., top-left corner, 50x50px area) so that pixel sampling can verify
   the marker without OCR. Use high-contrast text on a white background.
   Record the marker bounding box in development.json.

2. Create fixtures/development.json with ground-truth for development pages
   (pages 1–5) and orientation fixtures only:
   - Fixture filename, page index, page marker string, marker pixel location
     (x, y, width, height in rendered pixels at canonical resolution).
   - Expected overlay target as `[x0, y0, x1, y1]` normalized 0–1 coords.
   - Expected rendered dimensions (width_px, height_px) for each page.

3. Create fixtures/holdout.json with 20 frozen evaluation questions per
   PRODUCT_BRIEF.md section 15B:
   - 4 text lookups targeting pages 6–8.
   - 4 table/label-and-unit lookups with nearby distractor rows on pages 6–8.
   - 8 genuinely visual questions on pages 6–8: flow direction, spatial
     relation, graphical branch, chart curve, unlabeled component.
   - 4 absent-answer questions with plausible distractors present on pages 6–8.
   Each answerable question includes expected page ID (by marker),
   expected evidence region, and notes on what distinguishes the
   correct target from distractors. Truth derives from construction.
   Development page IDs (P1–P5) and holdout page IDs (P6–P8) must be
   strictly disjoint — no holdout question may reference a development page.

4. Run `C:/Users/vaidy/.local/bin/uv.exe run --project backend python fixtures/generate.py`
   and verify outputs exist in fixtures/generated/.

### Step 3: Backend implementation
1. Create backend/app/__init__.py (empty).
2. Create backend/app/config.py reading .env with defaults from .env.example.
3. Create backend/app/db.py with SQLite schema (documents, pages, jobs tables).
   Use migrations or explicit schema version. Parameterized SQL, foreign keys.
4. Create backend/app/schemas.py with Pydantic models for API requests/responses.
5. Create backend/app/geometry.py with coordinate conversion and validation:
   - Provider [ymin,xmin,ymax,xmax] 0-1000 to app [x0,y0,x1,y1] 0-1 normalized.
   - Validate finite numbers, proper ordering, reject zero-area/out-of-range.
6. Create backend/app/ingestion.py:
   - Validate file signature and extension (PDF, PNG, JPEG).
   - SHA-256 content identity.
   - PDF page count inspection and page selection validation.
   - Serialized pypdfium2 rendering respecting CropBox and Rotate.
   - EXIF orientation for images.
   - Canonical display raster (long edge <= 3000px) and model input (long edge <= 2048px, <= 4MB).
   - Persist originals byte-for-byte.
7. Create backend/app/jobs.py with a simple in-process job worker for imports.
8. Create backend/app/main.py with FastAPI routes:
   - GET /api/health
   - POST /api/uploads (multipart, returns upload ID, type, page count)
   - POST /api/documents (commit upload with page ranges, enqueue import, 202)
   - GET /api/documents (list with readiness and capacity)
   - DELETE /api/documents/{id}
   - GET /api/pages/{id}/image (canonical raster)
   - GET /api/documents/{id}/original
9. Create .env.example with safe defaults per PRODUCT_BRIEF.md section 14.
10. Create backend/tests/__init__.py (empty).

### Step 4: Frontend implementation
1. Create frontend/tsconfig.json with standard React+TypeScript configuration.
2. Create frontend/vite.config.ts with React plugin and proxy /api to localhost:8000.
3. Create frontend/index.html as the HTML entry point.
4. Create frontend/src/main.tsx as the React entry point.
5. Create frontend/src/App.css with plain CSS layout per PRODUCT_BRIEF section 7.
6. Create frontend/src/App.tsx as the single-screen layout per section 7.
7. Create frontend/src/api.ts with typed fetch wrappers for all API routes.
8. Create frontend/src/components/DocumentList.tsx: document list with add/remove,
   page ranges, capacity indicator (X/20 pages).
9. Create frontend/src/components/PageViewer.tsx: zoomable page viewer using
   react-zoom-pan-pinch with SVG overlay sharing the transform. Controls:
   Fit, 100%, 200%, pan. Highlight toggle. viewBox="0 0 1000 1000" overlay.
10. Create frontend/src/components/QuestionBar.tsx: question input (stub for now).
11. Create frontend/src/components/EvidenceList.tsx: result cards (stub for now).

### Step 5: Backend tests
1. Create backend/tests/test_geometry.py with pytest tests covering:
   - Geometry conversion and validation (valid, invalid, zero-area, out-of-range).
2. Create backend/tests/test_upload.py with pytest tests covering:
   - Upload validation (supported/unsupported types, size limits).
   - API error responses (413, 415, 422, 409, 404).
3. Create backend/tests/test_lifecycle.py with pytest tests covering:
   - Document import lifecycle (upload -> commit -> ready).
   - Page range validation and capacity enforcement (20 page limit).
   - Persistence: documents survive simulated restart.
   - Original file byte preservation (SHA-256 before/after).
   - Physical-page identity: importing noncontiguous pages (e.g., pages 2,4)
     correctly records physical page numbers and page markers are present
     in rendered output.
4. Run `C:/Users/vaidy/.local/bin/uv.exe run --project backend pytest backend/tests`.

### Step 6: Dev server launcher
1. Create app_tools/dev.py that starts backend on 127.0.0.1:8000 and
   frontend dev server on 127.0.0.1:5173, passes backend environment,
   stops owned children on exit. Must support a `--check` flag that starts
   both servers, waits for health check, and exits 0 on success.
2. Verify startup and clean shutdown.

### Step 7: Browser tests and DOM-bounds export
1. Create frontend/playwright.config.ts with:
   - `webServer` config that runs `app_tools/dev.py` via the backend venv
     Python (`backend/.venv/Scripts/python.exe app_tools/dev.py`), starting
     both backend and frontend, waiting for health.
   - Chromium-only project.
   - Screenshot output to out/orchestration/import-viewer/screenshots/.
   - Server teardown on test completion.
2. Create frontend/tests/e2e.spec.ts with Playwright tests covering:
   - Upload a generated PDF, verify pages appear in document list.
   - Upload an image, verify it appears.
   - Page range selection for a multi-page PDF.
   - Capacity limit enforcement.
   - Viewer displays imported page with test overlay.
   - **DOM-bounds export for each view**: For Fit, 100%, 200%, pan, and resize,
     use `element.boundingClientRect()` on the page image element and the SVG
     overlay element to measure their actual rendered positions and dimensions.
     Write all measurements to `out/orchestration/import-viewer/dom-bounds.json`
     with schema:
     ```json
     [
       {
         "fixture": "technical.pdf",
         "page": 1,
         "view": "fit",
         "image_bounds": {"x": 0, "y": 0, "width": 800, "height": 600},
         "overlay_bounds": {"x": 0, "y": 0, "width": 800, "height": 600},
         "viewport_size": {"width": 1280, "height": 720}
       }
     ]
     ```
   - Zoom (Fit, 100%, 200%) preserves overlay alignment (visual check via screenshot).
   - Pan preserves overlay alignment.
   - Delete a document, verify removal.
   - Restart persistence: use test-internal server stop/start to verify
     documents survive.
   - Rotation/CropBox/EXIF fixtures render correctly with aligned overlays.
     Export DOM bounds for each orientation case.
   - Physical-page identity: import noncontiguous pages, verify correct
     page numbers displayed and correct page content rendered.
3. Run `npm --prefix frontend run test:e2e` and capture screenshots to
   out/orchestration/import-viewer/screenshots/.

### Step 8: Independent validator
1. Create app_tools/validate_slice.py that independently verifies:
   - **Artifact existence**: every file listed in the artifacts array of
     report.json exists on disk. Produces `artifacts_complete: bool` and
     `artifacts_missing: []` or a list. Also `artifacts_count: N`.
   - **Byte preservation**: for each imported document, independently compute
     SHA-256 of the stored original file AND of the original fixture input;
     compare. Produces `hash_pairs: [{fixture, stored, match: bool}]` and
     `hash_all_match: bool`, `hash_match_count: N`, `hash_total: N`.
   - **Overlay alignment from browser measurements**: read
     `out/orchestration/import-viewer/dom-bounds.json` (emitted by Playwright
     in Step 7). For each entry, compute expected overlay position from
     fixture truth in `fixtures/development.json` and the measured image bounds.
     Compare against the measured overlay bounds. Measure alignment error as
     max absolute pixel offset. Produces
     `alignment_results: [{fixture, view, expected_px, actual_px, error_px, pass: bool}]`
     with tolerance of 2px per zoom level. Also `alignment_all_pass: bool`,
     `alignment_view_count: N` (must be >= 5: fit, 100%, 200%, pan, resize).
   - **Rotation/CropBox/EXIF**: load each orientation fixture from dom-bounds.json,
     verify rendered dimensions match expected orientation-corrected dimensions
     within 1px. Verify page marker by sampling pixels at the documented marker
     location in the rendered image and checking for the expected high-contrast
     pattern. Produces `orientation_results: [{fixture, expected_dims, actual_dims,
     marker_verified, pass: bool}]` and `orientation_all_pass: bool`,
     `orientation_case_count: N` (must be >= 5: portrait, landscape, cropbox,
     exif-jpeg, standard-png).
   - **Physical-page identity**: for a noncontiguous page import (e.g.,
     selecting pages 2 and 4 from the 8-page PDF), verify that stored metadata
     records correct physical page numbers AND that rendered images contain
     the correct page markers via pixel sampling. Produces
     `page_identity_results: [{doc, selected_pages, stored_pages,
     markers_verified, pass: bool}]` and `page_identity_all_pass: bool`,
     `page_identity_case_count: N` (must be >= 1).
   - **Holdout structure**: verify fixtures/holdout.json contains exactly
     20 questions with the 4/4/8/4 split. Verify each answerable question
     has expected_page (referencing only holdout markers P6–P8) and
     expected_region. Verify development page set {P1–P5} and holdout page
     set {P6–P8} are strictly disjoint. Verify actual fixture content:
     check that pages with distractor-table markers exist, chart/legend pages
     exist, raster-flowchart pages exist, and repeated-label pages exist.
     Produces `holdout_valid: bool`, `holdout_errors: []`,
     `holdout_question_count: 20`, `holdout_split: [4,4,8,4]`.
   - Overall: `validator_pass: bool` (true iff all subsections pass).
   Write results to `out/orchestration/import-viewer/validation.json`.
2. Run `C:/Users/vaidy/.local/bin/uv.exe run --project backend python app_tools/validate_slice.py`.

### Step 9: Evidence report
1. Create out/orchestration/import-viewer/report.json with the schema below.
2. Run the independent validator and record its results.
3. Record all validation command exit codes.

## Exact outputs (tracked source files)
- backend/pyproject.toml
- backend/uv.lock
- backend/app/__init__.py
- backend/app/config.py
- backend/app/db.py
- backend/app/schemas.py
- backend/app/geometry.py
- backend/app/ingestion.py
- backend/app/jobs.py
- backend/app/main.py
- backend/tests/__init__.py
- backend/tests/test_geometry.py
- backend/tests/test_upload.py
- backend/tests/test_lifecycle.py
- fixtures/generate.py
- fixtures/development.json
- fixtures/holdout.json
- frontend/package.json
- frontend/package-lock.json
- frontend/tsconfig.json
- frontend/vite.config.ts
- frontend/index.html
- frontend/src/main.tsx
- frontend/src/App.tsx
- frontend/src/App.css
- frontend/src/api.ts
- frontend/src/components/DocumentList.tsx
- frontend/src/components/PageViewer.tsx
- frontend/src/components/QuestionBar.tsx
- frontend/src/components/EvidenceList.tsx
- frontend/tests/e2e.spec.ts
- frontend/playwright.config.ts
- app_tools/dev.py
- app_tools/validate_slice.py
- .env.example

## Exact outputs (generated/ignored, not committed)
- out/orchestration/import-viewer/report.json
- out/orchestration/import-viewer/validation.json
- out/orchestration/import-viewer/dom-bounds.json
- out/orchestration/import-viewer/screenshots/*.png
- fixtures/generated/*
- backend/.venv/
- frontend/node_modules/
- data/

## Report schema

```json
{
  "checks": {
    "all_pass": true,
    "uv_sync_exit": 0,
    "npm_ci_exit": 0,
    "playwright_install_exit": 0,
    "fixture_gen_exit": 0,
    "pytest_exit": 0,
    "vite_build_exit": 0,
    "validator_exit": 0,
    "playwright_exit": 0,
    "validator_pass": true,
    "artifacts_complete": true,
    "hash_all_match": true,
    "alignment_all_pass": true,
    "orientation_all_pass": true,
    "page_identity_all_pass": true,
    "holdout_valid": true
  },
  "counts": {
    "artifacts_count": 0,
    "hash_match_count": 0,
    "hash_total": 0,
    "alignment_view_count": 0,
    "orientation_case_count": 0,
    "page_identity_case_count": 0,
    "holdout_question_count": 20,
    "holdout_split": [4, 4, 8, 4]
  },
  "commands": [
    {"command": "...", "exit_code": 0, "output_summary": "..."}
  ],
  "source_revision": "20a8ed4",
  "screenshots": ["out/orchestration/import-viewer/screenshots/..."],
  "artifacts": [
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
    "app_tools/validate_slice.py",
    ".env.example"
  ],
  "observations": ["..."],
  "failures": ["..."]
}
```

## Independent validation commands
All commands use the absolute path to uv since it is not on the default PATH.
```
C:/Users/vaidy/.local/bin/uv.exe sync --project backend --python 3.12
npm --prefix frontend ci
npx --prefix frontend playwright install chromium
C:/Users/vaidy/.local/bin/uv.exe run --project backend python fixtures/generate.py
C:/Users/vaidy/.local/bin/uv.exe run --project backend pytest backend/tests
npm --prefix frontend run build
C:/Users/vaidy/.local/bin/uv.exe run --project backend python app_tools/validate_slice.py
npm --prefix frontend run test:e2e
```

## Done-when
1. All eight validation commands exit 0 (recorded in report.json checks).
2. report.json exists with checks.all_pass = true.
3. validation.json exists with validator_pass = true.
4. validation.json artifacts_complete = true and artifacts_missing is empty.
5. validation.json hash_all_match = true and hash_total >= 1.
6. validation.json alignment_all_pass = true and alignment_view_count >= 5
   (covering Fit, 100%, 200%, pan, resize).
7. validation.json orientation_all_pass = true and orientation_case_count >= 5
   (portrait, landscape, cropbox, exif-jpeg, standard-png).
8. validation.json page_identity_all_pass = true and page_identity_case_count >= 1.
9. validation.json holdout_valid = true and holdout_question_count = 20
   and holdout_split = [4,4,8,4].
10. Capacity enforcement (20 pages) is tested and works (pytest assertion).
11. Documents persist through application restart (Playwright test).
12. All artifacts listed in report.json artifacts array exist on disk.
13. Screenshots in out/orchestration/import-viewer/screenshots/ show overlay
    alignment at Fit, 100%, and 200% zoom levels.
14. dom-bounds.json exists with entries for Fit, 100%, 200%, pan, resize views.

## Escape hatch
If dependencies or core geometry block progress within 60 minutes, preserve all
work and failure evidence. Write report.json with checks.all_pass = false and
a specific diagnosis of the blocking issue. Write validation.json with
validator_pass = false and the specific failing assertions. Report the exact
bounded next hypothesis to F1.

Report, then STOP.
