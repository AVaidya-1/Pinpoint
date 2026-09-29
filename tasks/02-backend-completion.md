# Task 2: Backend Completion & Robustness

## Goal
Ensure the backend handles all edge cases from the product spec, add missing backend tests, and verify the search pipeline works end-to-end with mocked provider responses.

## Context
The backend is in `backend/app/`. It has: main.py (FastAPI routes), db.py (SQLite), schemas.py (Pydantic), config.py, geometry.py, ingestion.py (PDF/image processing), jobs.py, search.py (bounded scan engine), providers/gemma.py (Gemini API client). Prompts are in `backend/app/prompts/`.

This app handles **technical documentation** — engineering manuals, datasheets, flowcharts, wiring diagrams, specification tables. The content has tons of diagrams and images. The search engine inspects each page image with a VLM and returns rectangular highlight coordinates.

## Steps

### 1. Add comprehensive backend tests

Create `backend/tests/test_search.py` with tests for the search engine:

```python
# Test search with mocked provider that returns "found" with valid boxes
# Test search with mocked provider that returns "not_found"
# Test search with mocked provider that returns "uncertain"
# Test search with provider that returns invalid/extra fields (must be rejected)
# Test search with provider that returns an "answer" field (injection attempt — must be rejected)
# Test search cache: identical question+page reuses cached result without calling provider again
# Test search cancellation: cancel_requested stops scheduling new pages
# Test search with mixed results: some pages found, some not_found
# Test determine_outcome() with all combinations
# Test evidence_crop_bounds() padding and clipping
```

Create `backend/tests/test_ingestion.py`:
```python
# Test PDF page count extraction
# Test PDF rendering produces expected dimensions
# Test image EXIF orientation is applied
# Test model image derivative respects 2048px and 4MB limits
# Test oversized image rejection (>20 megapixels)
# Test SHA-256 content identity
```

Create `backend/tests/test_api_integration.py`:
```python
# Test full upload -> commit -> list -> delete cycle
# Test capacity limits (exceed 20 pages)
# Test document limit (exceed 5 documents)
# Test busy rejection (job active during new request)
# Test persistence: documents survive TestClient recreation
# Test deletion invalidates related searches
# Test page image endpoint returns valid PNG
# Test original file endpoint returns the uploaded bytes
# Test health endpoint returns expected fields
# Test search endpoint with mocked provider
```

Create `backend/tests/test_provider.py`:
```python
# Test validate_inspect() accepts valid found response
# Test validate_inspect() accepts valid not_found response
# Test validate_inspect() rejects extra fields
# Test validate_inspect() rejects invalid status values
# Test validate_inspect() rejects boxes for non-found status
# Test validate_inspect() rejects zero-area boxes
# Test validate_inspect() rejects out-of-range coordinates
# Test _parse_check_verdict() accepts valid verdicts
# Test _parse_check_verdict() rejects invalid text
# Test _strip_fences() removes markdown code fences
# Test _is_transient() classifies errors correctly
```

### 2. Fix any issues found

Run all tests:
```
cd backend && .venv/Scripts/python.exe -m pytest tests/ -v
```

Fix any failures. Common issues to watch for:
- Import paths (tests need `app.` prefix)
- Monkeypatching environment variables for test isolation
- SQLite connection cleanup
- Temporary directory handling on Windows

### 3. Verify API contract matches spec

Check all endpoints against Section 12 of the spec:
- `GET /api/health` — status, model, key_present, db_ok
- `POST /api/uploads` — 413 for too large, 415 for unsupported
- `POST /api/documents` — 422 for bad pages, 409 for capacity/busy
- `GET /api/documents` — includes capacity info
- `DELETE /api/documents/{id}` — invalidates searches, removes files
- `GET /api/pages/{id}/image` — returns PNG
- `GET /api/documents/{id}/original` — returns original file
- `POST /api/searches` — 422 for empty question, missing key
- `GET /api/jobs/{id}` — state, progress
- `POST /api/jobs/{id}/cancel` — cooperative cancellation
- `GET /api/searches` — recent searches list
- `GET /api/searches/{id}` — outcome, coverage, evidence

### 4. Verify provider integration structure

Check `backend/app/providers/gemma.py`:
- Pacing (rate limiting) works
- Retry logic handles transient errors
- Schema validation rejects malformed responses
- One schema-repair attempt is allowed
- Evidence checking supports both two-image and single-image modes

## Success Criteria
- All new and existing tests pass
- No import errors or missing modules
- API contract matches the spec
- Provider validation rejects injection attempts (extra fields, answer text)
