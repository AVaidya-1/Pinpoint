# IMPORT_VIEWER_SLICE

## Bounded deliverable and prior evidence
Read CONTEXT.md and docs/product/PRODUCT_BRIEF.md sections 5, 8, 11, 12, 14.
In at most 75 minutes implement an import-to-viewer vertical slice.
No existing application code is assumed. Setup preflight evidence is at
out/setup/gemma-20260913T192947078057Z/report.json.

## Allowed writes
backend/** except backend/.venv source commits; frontend/** except dependency/build
outputs in source commits; fixtures/generate.py, fixtures/development.json,
fixtures/holdout.json; app_tools/**; APP_README.md; .env.example with safe values.
Runtime/dependencies may be generated only in ignored backend/.venv, node_modules,
data, fixtures/generated, and out/. Evidence: out/orchestration/import-viewer/**.
Do not modify scripts/, orchestration.json, owner/product policy, prior task
contracts, review/memory/stop records, Git metadata or credentials. No Git
commands, hidden agents, pushes, paid services, deployment or external messaging.

## Prohibitions
- Do not call any model API or insert fixture answers into a live provider path.
- Do not modify root .venv, scripts/, orchestration.json or docs/orchestration/.
- Do not run Git commands or push.
- Do not weaken acceptance criteria or fabricate PASS results.
- Do not install paid dependencies or services.

## Ordered procedure

### Step 1: Environment and dependencies
1. Create backend/pyproject.toml with Python >=3.12 dependencies: fastapi,
   uvicorn[standard], python-multipart, python-dotenv, pypdfium2, Pillow,
   pydantic, google-genai (for later use), httpx, pytest, pytest-asyncio.
2. Create frontend/package.json with React 18, TypeScript, Vite,
   react-zoom-pan-pinch, and Playwright for testing.
3. Run `uv sync --project backend --python 3.12` and `npm --prefix frontend ci`.
4. Verify backend/.venv exists and root .venv is untouched.

### Step 2: Fixture generation
1. Create fixtures/generate.py that produces:
   - A technical PDF with known shapes at known coordinates (for geometry testing).
   - A raster image (PNG) with known overlay targets.
   - A rotated PDF page (Rotate=90) and a PDF with non-default CropBox.
   - An EXIF-oriented JPEG image.
   - Output to fixtures/generated/ (gitignored).
2. Create fixtures/development.json with ground-truth coordinates for each fixture.
3. Create fixtures/holdout.json with 20 frozen evaluation questions per
   PRODUCT_BRIEF.md section 15B. Include 4 text, 4 table, 8 visual, 4 absent.
   Use fixture page IDs and manually specified acceptable evidence regions.
   Truth derives from construction, not model output.
4. Run `uv run --project backend python fixtures/generate.py` and verify outputs.

### Step 3: Backend implementation
1. Create backend/app/config.py reading .env with defaults from .env.example.
2. Create backend/app/db.py with SQLite schema (documents, pages, jobs tables).
   Use migrations or explicit schema version. Parameterized SQL, foreign keys.
3. Create backend/app/schemas.py with Pydantic models for API requests/responses.
4. Create backend/app/geometry.py with coordinate conversion and validation:
   - Provider [ymin,xmin,ymax,xmax] 0-1000 to app [x0,y0,x1,y1] 0-1 normalized.
   - Validate finite numbers, proper ordering, reject zero-area/out-of-range.
5. Create backend/app/ingestion.py:
   - Validate file signature and extension (PDF, PNG, JPEG).
   - SHA-256 content identity.
   - PDF page count inspection and page selection validation.
   - Serialized pypdfium2 rendering respecting CropBox and Rotate.
   - EXIF orientation for images.
   - Canonical display raster (long edge <= 3000px) and model input (long edge <= 2048px, <= 4MB).
   - Persist originals byte-for-byte.
6. Create backend/app/jobs.py with a simple in-process job worker for imports.
7. Create backend/app/main.py with FastAPI routes:
   - GET /api/health
   - POST /api/uploads (multipart, returns upload ID, type, page count)
   - POST /api/documents (commit upload with page ranges, enqueue import, 202)
   - GET /api/documents (list with readiness and capacity)
   - DELETE /api/documents/{id}
   - GET /api/pages/{id}/image (canonical raster)
   - GET /api/documents/{id}/original
8. Create .env.example with safe defaults per PRODUCT_BRIEF.md section 14.

### Step 4: Frontend implementation
1. Create frontend/src/App.tsx as the single-screen layout per section 7.
2. Create frontend/src/api.ts with typed fetch wrappers for all API routes.
3. Create frontend/src/components/DocumentList.tsx: document list with add/remove,
   page ranges, capacity indicator (X/20 pages).
4. Create frontend/src/components/PageViewer.tsx: zoomable page viewer using
   react-zoom-pan-pinch with SVG overlay sharing the transform. Controls:
   Fit, 100%, 200%, pan. Highlight toggle. viewBox="0 0 1000 1000" overlay.
5. Create frontend/src/components/QuestionBar.tsx: question input (stub for now).
6. Create frontend/src/components/EvidenceList.tsx: result cards (stub for now).
7. Configure Vite proxy for /api to localhost:8000.
8. Use plain CSS, no CSS framework.

### Step 5: Test overlay and geometry verification
1. Exercise a clearly labeled deterministic TEST overlay on generated fixtures:
   - Load a fixture with known coordinates.
   - Display the test overlay rectangle at the known position.
   - Verify alignment at Fit, 100%, 200%, pan and resize visually.
2. Verify PDF CropBox, Rotate=90, and EXIF orientation fixtures render correctly
   with overlay alignment preserved.
3. Assert original uploaded bytes stay unchanged after import.

### Step 6: Backend tests
1. Create backend/tests/ with pytest tests covering:
   - Geometry conversion and validation (valid, invalid, zero-area, out-of-range).
   - Upload validation (supported/unsupported types, size limits).
   - Document import lifecycle (upload -> commit -> ready).
   - Page range validation and capacity enforcement (20 page limit).
   - Persistence: documents survive simulated restart.
   - API error responses (413, 415, 422, 409, 404).
2. Run `uv run --project backend pytest backend/tests`.

### Step 7: Browser tests and evidence
1. Create frontend/tests/ with Playwright tests covering:
   - Upload a generated PDF, verify pages appear in document list.
   - Upload an image, verify it appears.
   - Page range selection for a multi-page PDF.
   - Capacity limit enforcement.
   - Viewer displays imported page with test overlay.
   - Zoom (Fit, 100%, 200%) preserves overlay alignment.
   - Pan preserves overlay alignment.
   - Delete a document, verify removal.
   - Restart persistence (stop/start dev server, verify documents remain).
2. Configure playwright in frontend/package.json with a test:e2e script.
3. Run browser tests and capture screenshots.

### Step 8: Dev server launcher
1. Create app_tools/dev.py that starts backend on 127.0.0.1:8000 and
   frontend on 127.0.0.1:5173, passes backend environment, stops owned
   children on exit.
2. Verify startup and clean shutdown.

## Exact outputs
- All source files listed above under backend/, frontend/, fixtures/, app_tools/.
- .env.example with safe defaults.
- out/orchestration/import-viewer/report.json with:
  - checks.all_pass: boolean
  - commands: list of {command, exit_code, output_summary}
  - input_hashes: SHA-256 of fixture inputs
  - source_revision: current git SHA
  - screenshots: list of screenshot paths
  - observations: list of strings
  - failures: list of remaining failure descriptions
- Raw logs beside report.json.

## Independent validation commands
```
uv sync --project backend --python 3.12
npm --prefix frontend ci
uv run --project backend python fixtures/generate.py
uv run --project backend pytest backend/tests
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

## Done-when
1. All six validation commands exit 0.
2. report.json exists with checks.all_pass = true.
3. Screenshots show correct overlay alignment at Fit, 100%, 200% and pan.
4. Rotation/CropBox/EXIF fixtures render correctly with aligned overlays.
5. Original file bytes are unchanged after import.
6. Capacity enforcement (20 pages) is tested and works.
7. Documents persist through application restart.

## Escape hatch
If dependencies or core geometry block progress within 60 minutes, preserve all
work and failure evidence. Write report.json with checks.all_pass = false and
a specific diagnosis of the blocking issue. Report the exact bounded next
hypothesis to F1.

Report, then STOP.
