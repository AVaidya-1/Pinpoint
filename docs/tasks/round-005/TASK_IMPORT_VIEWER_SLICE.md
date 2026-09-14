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

   **Pixel-decodable page signatures**: Every generated page embeds a unique
   4x4 pixel color signature at position (0,0) in the rendered output.
   Each page uses a distinct RGB value:
   - P1: (255, 0, 0) red
   - P2: (0, 255, 0) green
   - P3: (0, 0, 255) blue
   - P4: (255, 255, 0) yellow
   - P5: (255, 0, 255) magenta
   - P6: (0, 255, 255) cyan
   - P7: (128, 0, 0) dark red
   - P8: (0, 128, 0) dark green
   - PORTRAIT: (128, 128, 0) olive
   - LANDSCAPE: (0, 128, 128) teal
   - CROPBOX: (128, 0, 128) purple

   For PDFs, draw a filled rectangle at the top-left corner of the PDF page
   at coordinates that map to the (0,0)-(3,3) pixel range at canonical
   rendering resolution. For images, set pixels directly.
   Record each signature RGB in development.json.

   **Development pages (pages 1-5)** - used for geometry testing and iteration:
   - Page 1: A specification table with a known target row AND at least
     two plausible distractor rows with similar labels/units (section 15B).
   - Page 2: A chart/plot with labeled axes, legend, and a target curve
     region (section 15B).
   - Page 3: A raster-only flowchart with decision nodes and branches,
     no searchable text layer (section 15B).
   - Page 4: A connector/schematic diagram with repeated labels appearing
     on different sub-diagrams (section 15B).
   - Page 5: A simple geometric shapes page with known overlay targets
     at exact coordinates for geometry testing.

   **Holdout pages (pages 6-8)** - frozen evaluation content, disjoint from
   development pages:
   - Page 6: A specification table with a target row and distractor rows
     (distinct content from page 1).
   - Page 7: A chart with legend and a raster diagram region
     (distinct content from pages 2-3).
   - Page 8: A schematic with repeated labels and an absent-answer region
     (distinct content from page 4).

   **Orientation fixtures** (separate files, all development):
   - A portrait PDF page with known overlay target at documented coordinates.
   - A Rotate=90 landscape PDF page with known overlay target.
   - A PDF with non-default CropBox and known overlay target.
   - An EXIF-oriented JPEG image with a known target region.
   - A standard PNG image with a known target region.

2. Create fixtures/development.json with ground-truth for development pages
   (pages 1-5) and orientation fixtures only:
   - Fixture filename, page index, page marker RGB signature
     (e.g., `"signature_rgb": [255, 0, 0]`).
   - Expected overlay target as `[x0, y0, x1, y1]` normalized 0-1 coords.
   - Expected rendered dimensions (width_px, height_px) for each page.
   - A stable `fixture_id` string for each entry (e.g., `"dev_p1"`,
     `"orientation_portrait"`) matching the IDs used in dom-bounds.json.

3. Create fixtures/holdout.json with 20 frozen evaluation questions per
   PRODUCT_BRIEF.md section 15B:
   - 4 text lookups targeting pages 6-8.
   - 4 table/label-and-unit lookups with nearby distractor rows on pages 6-8.
   - 8 genuinely visual questions on pages 6-8: flow direction, spatial
     relation, graphical branch, chart curve, unlabeled component.
   - 4 absent-answer questions with plausible distractors present on pages 6-8.
   Each answerable question includes expected page ID (by marker RGB),
   expected evidence region, and notes on what distinguishes the
   correct target from distractors. Truth derives from construction.
   Development page IDs (P1-P5) and holdout page IDs (P6-P8) must be
   strictly disjoint.

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
   The SVG overlay must contain a `<rect>` element with `data-testid="highlight-rect"`
   for Playwright measurement. The `<rect>` uses the normalized coordinates
   from a test overlay (loaded from development.json fixture data) converted
   to the SVG viewBox coordinate space (0-1000).
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
     correctly records physical page numbers and pixel signatures are present
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
   - **Highlight rect DOM-bounds export**: For each view (Fit, 100%, 200%,
     pan, resize), use `element.boundingClientRect()` on the page `<img>`
     element and on the highlight `<rect>` element
     (`[data-testid="highlight-rect"]`) to measure their actual rendered
     positions and dimensions. Write all measurements to
     `out/orchestration/import-viewer/dom-bounds.json` with schema:
     ```json
     [
       {
         "fixture_id": "dev_p5",
         "view_name": "fit",
         "image_bounds": {"x": 0, "y": 0, "width": 800, "height": 600},
         "highlight_bounds": {"x": 120, "y": 180, "width": 200, "height": 150},
         "viewport_size": {"width": 1280, "height": 720}
       }
     ]
     ```
     Required `view_name` values: `fit`, `zoom100`, `zoom200`, `pan`, `resize`.
     Each `fixture_id` must match a key in `fixtures/development.json`.
   - Zoom (Fit, 100%, 200%) preserves overlay alignment (visual screenshot).
   - Pan preserves overlay alignment.
   - Delete a document, verify removal.
   - Restart persistence: use test-internal server stop/start to verify
     documents survive.
   - Rotation/CropBox/EXIF fixtures render correctly with aligned overlays.
     Export highlight DOM bounds for each orientation case using fixture_id
     values matching development.json (e.g., `orientation_portrait`).
   - Physical-page identity: import noncontiguous pages, verify correct
     page numbers displayed and correct page content rendered.
3. Run `npm --prefix frontend run test:e2e` and capture screenshots to
   out/orchestration/import-viewer/screenshots/.

### Step 8: Evidence report skeleton
1. Create out/orchestration/import-viewer/report.json with the schema below,
   populated from the results of Steps 1-7. Record all command exit codes.
   The `artifacts` array must list every tracked and generated output file.
   This file must exist before the validator runs in Step 9.

### Step 9: Independent validator
1. Create app_tools/validate_slice.py that independently verifies:
   - **Artifact existence**: every file listed in the artifacts array of
     report.json exists on disk. Produces `artifacts_complete: bool` and
     `artifacts_missing: []`. Also `artifacts_count: N`.
   - **Byte preservation**: for each imported document, independently compute
     SHA-256 of the stored original file AND of the original fixture input;
     compare. Produces `hash_pairs: [{fixture, stored, match: bool}]` and
     `hash_all_match: bool`, `hash_match_count: N`, `hash_total: N`.
   - **Overlay alignment from highlight measurements**: read
     `out/orchestration/import-viewer/dom-bounds.json` (emitted by Playwright
     in Step 7). For each entry, independently derive expected highlight
     pixel coordinates from:
     (a) the fixture's normalized target box in `fixtures/development.json`,
     (b) the measured `image_bounds` from the same dom-bounds entry.
     Expected highlight position:
     `expected_x = image_bounds.x + target_x0 * image_bounds.width`
     `expected_y = image_bounds.y + target_y0 * image_bounds.height`
     `expected_w = (target_x1 - target_x0) * image_bounds.width`
     `expected_h = (target_y1 - target_y0) * image_bounds.height`
     Compare against the measured `highlight_bounds`. Alignment error is
     max absolute pixel offset across x, y, width, height.
     Produces `alignment_results: [{fixture_id, view_name, expected_px,
     actual_px, error_px, pass: bool}]` with tolerance of 2px.
     Also `alignment_all_pass: bool`, `alignment_view_count: N`.
     Required view_names: fit, zoom100, zoom200, pan, resize.
   - **Rotation/CropBox/EXIF**: read orientation fixture entries from
     dom-bounds.json (by fixture_id prefix `orientation_*`). Verify rendered
     image dimensions match expected orientation-corrected dimensions within
     1px using image_bounds width/height. For page-signature verification,
     load the rendered canonical raster image from disk and sample the 4x4
     pixel grid at position (0,0). Compare each pixel's RGB to the expected
     signature from development.json with tolerance <= 10 per channel.
     Produces `orientation_results: [{fixture_id, expected_dims, actual_dims,
     signature_verified, pass: bool}]` and `orientation_all_pass: bool`,
     `orientation_case_count: N`.
     Required cases: portrait, landscape, cropbox, exif-jpeg, standard-png.
   - **Physical-page identity**: for a noncontiguous page import (e.g.,
     selecting pages 2 and 4 from the 8-page PDF), verify that stored
     metadata records correct physical page numbers AND that rendered
     canonical raster images contain the correct pixel signatures via
     4x4 grid sampling at (0,0) with RGB tolerance <= 10.
     Produces `page_identity_results: [{doc, selected_pages, stored_pages,
     signatures_verified, pass: bool}]` and `page_identity_all_pass: bool`,
     `page_identity_case_count: N`.
   - **Holdout structure**: verify fixtures/holdout.json contains exactly
     20 questions with the 4/4/8/4 split. Verify each answerable question
     has expected_page (referencing only holdout signature RGBs for P6-P8)
     and expected_region. Verify development page set {P1-P5} and holdout
     page set {P6-P8} are strictly disjoint. Verify actual fixture content:
     check that pages with distractor-table content exist, chart/legend
     pages exist, raster-flowchart pages exist, and repeated-label pages
     exist (by checking fixture file existence and development.json metadata).
     Produces `holdout_valid: bool`, `holdout_errors: []`,
     `holdout_question_count: 20`, `holdout_split: [4,4,8,4]`.
   - **DOM bounds completeness**: verify dom-bounds.json contains entries
     for all required view_names (fit, zoom100, zoom200, pan, resize) and
     all required orientation cases. Produces `dom_bounds_entry_count: N`,
     `dom_bounds_complete: bool`.
   - Overall: `validator_pass: bool` (true iff all subsections pass).
   Write results to `out/orchestration/import-viewer/validation.json`.
2. Run `C:/Users/vaidy/.local/bin/uv.exe run --project backend python app_tools/validate_slice.py`.

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
    "playwright_exit": 0,
    "validator_exit": 0,
    "validator_pass": true,
    "artifacts_complete": true,
    "hash_all_match": true,
    "alignment_all_pass": true,
    "orientation_all_pass": true,
    "page_identity_all_pass": true,
    "holdout_valid": true,
    "dom_bounds_complete": true
  },
  "counts": {
    "artifacts_count": 0,
    "hash_match_count": 0,
    "hash_total": 0,
    "alignment_view_count": 5,
    "orientation_case_count": 5,
    "page_identity_case_count": 1,
    "holdout_question_count": 20,
    "holdout_split": [4, 4, 8, 4],
    "dom_bounds_entry_count": 0
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
Run in this order — Playwright must complete before the validator.
```
C:/Users/vaidy/.local/bin/uv.exe sync --project backend --python 3.12
npm --prefix frontend ci
npx --prefix frontend playwright install chromium
C:/Users/vaidy/.local/bin/uv.exe run --project backend python fixtures/generate.py
C:/Users/vaidy/.local/bin/uv.exe run --project backend pytest backend/tests
npm --prefix frontend run build
npm --prefix frontend run test:e2e
C:/Users/vaidy/.local/bin/uv.exe run --project backend python app_tools/validate_slice.py
```

## Done-when
1. All eight validation commands exit 0 (recorded in report.json checks).
2. report.json exists with checks.all_pass = true.
3. validation.json exists with validator_pass = true.
4. validation.json artifacts_complete = true and artifacts_missing is empty.
5. validation.json hash_all_match = true and hash_total >= 1.
6. validation.json alignment_all_pass = true and alignment_view_count = 5
   (covering fit, zoom100, zoom200, pan, resize by view_name).
7. validation.json orientation_all_pass = true and orientation_case_count = 5
   (portrait, landscape, cropbox, exif-jpeg, standard-png).
8. validation.json page_identity_all_pass = true and page_identity_case_count >= 1.
9. validation.json holdout_valid = true and holdout_question_count = 20
   and holdout_split = [4,4,8,4].
10. validation.json dom_bounds_complete = true and dom_bounds_entry_count >= 10.
11. Capacity enforcement (20 pages) is tested and works (pytest assertion).
12. Documents persist through application restart (Playwright test).
13. All artifacts listed in report.json artifacts array exist on disk.
14. Screenshots in out/orchestration/import-viewer/screenshots/ show overlay
    alignment at Fit, 100%, and 200% zoom levels.
15. dom-bounds.json exists with highlight_bounds entries for fit, zoom100,
    zoom200, pan, resize views and all orientation cases.

## Escape hatch
If dependencies or core geometry block progress within 60 minutes, preserve all
work and failure evidence. Write report.json with checks.all_pass = false and
a specific diagnosis of the blocking issue. Write validation.json with
validator_pass = false and the specific failing assertions. Report the exact
bounded next hypothesis to F1.

Report, then STOP.
