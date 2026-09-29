# Task 4: Playwright End-to-End Tests

## Goal
Write and run Playwright browser tests that verify the full upload → search → highlight cycle works. These tests use mocked provider responses (no real API calls) to verify the software, not the model quality.

## Context
Frontend is at `frontend/`. The package.json already has `@playwright/test` as a devDependency and a test script: `"test:e2e": "npx playwright test --config playwright.config.ts"`. But no playwright.config.ts or test files exist yet.

The dev server launcher is at `app_tools/dev.py` — it starts backend on 8000 and frontend on 5173. The backend reads `EVIDENCE_DATA_DIR` for data storage.

Technical documentation is the primary use case: PDFs with diagrams, flowcharts, specification tables, and raster-only pages. The generated test fixtures in `fixtures/generated/` include:
- test_pages.pdf (8 pages with tables, charts, flowcharts, schematics)
- portrait.pdf, landscape.pdf (Rotate=90), cropbox.pdf (non-default CropBox)
- exif_oriented.jpg (EXIF rotation 6)
- standard.png

## Steps

### 1. Install Playwright browsers

```
cd frontend && npx playwright install chromium
```

### 2. Create `frontend/playwright.config.ts`

```typescript
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 60_000,
  retries: 0,
  use: {
    baseURL: 'http://127.0.0.1:5173',
    headless: true,
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'cd .. && backend\\.venv\\Scripts\\python.exe app_tools/dev.py',
    url: 'http://127.0.0.1:8000/api/health',
    timeout: 120_000,
    reuseExistingServer: true,
  },
});
```

### 3. Create test files in `frontend/tests/`

**`frontend/tests/upload.spec.ts`** — Upload and document management:
```
- Test: upload a PNG file → appears in document list with 1 page
- Test: upload a multi-page PDF with page range "1-3" → only those pages imported
- Test: capacity display updates after upload (shows "X/20 pages")
- Test: remove a document → disappears from list, capacity updates
- Test: reject unsupported file type → error message shown
- Test: page chips are clickable → viewer shows selected page
```

**`frontend/tests/search.spec.ts`** — Search workflow:
```
- Test: type a question and click Find → search starts, progress shows
- Test: search results appear as evidence cards with crop previews
- Test: clicking evidence card opens page with highlight overlay
- Test: outcome wording matches spec for "found" case
- Test: cancel button stops search and shows cancelled message
- Test: empty question shows validation error
- Test: no documents shows "Add a document first" error
```

**`frontend/tests/viewer.spec.ts`** — Page viewer and highlights:
```
- Test: page image loads and displays
- Test: Fit button scales image to viewport
- Test: 100% and 200% buttons set correct zoom
- Test: highlight rectangle renders at correct position (use ?box=0.1,0.2,0.5,0.6 URL param)
- Test: Hide Highlight button removes overlay, Show Highlight restores it
- Test: highlight overlay SVG has correct viewBox matching image dimensions
```

**`frontend/tests/persistence.spec.ts`** — Data survives reload:
```
- Test: upload a document, reload page → document still listed
- Test: completed search results survive page reload
```

### 4. Handle the mock provider problem

For e2e tests that hit `/api/searches`, the backend needs a GEMINI_API_KEY and a real provider. For software-only tests:

Option A (preferred): Set up the tests to upload the generated fixture PDF, use the viewer geometry tests with `?box=` URL params, and skip live search tests. The search engine tests are covered by backend pytest mocks.

Option B: Create a test that uploads a fixture, initiates search (which will fail without a key), and verifies the error message "Add a Gemini API key to the backend environment, then restart."

### 5. Run the tests

```
cd frontend && npx playwright test
```

Fix any failures. Save test results.

## Success Criteria
- Playwright is installed with chromium
- At least 6 passing e2e tests covering upload, viewer, and highlight overlay
- Tests handle the dev server lifecycle correctly
- Failed test screenshots are saved to `frontend/test-results/`
- No flaky tests (tests pass consistently on re-run)

## Important Notes
- Use `data-testid` attributes that already exist in the components (e.g., `file-input`, `page-viewer`, `highlight-rect`, `question-input`, `ask-button`)
- The app uses `pp-` CSS class prefix (Pinpoint)
- Generated fixtures are in `fixtures/generated/` relative to project root
- The backend creates its own `data/` directory for SQLite and page images
