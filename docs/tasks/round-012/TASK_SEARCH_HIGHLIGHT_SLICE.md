# SEARCH_HIGHLIGHT_SLICE

## Bounded deliverable and prior evidence
Read CONTEXT.md and docs/product/PRODUCT_BRIEF.md sections 6, 8 (coordinate
convention), 9, 10, 11, 12, 13. In at most 100 minutes implement the search
and source-region highlighting path on the existing import/viewer slice.

Round-011 delivered the import/viewer vertical slice (PASS in state.json).
Setup preflight for gemma-4-31b-it passed
(out/setup/gemma-20260913T192947078057Z/report.json). google-genai is already
in backend/pyproject.toml. The geometry module already converts provider
[ymin,xmin,ymax,xmax] 0-1000 to app [x0,y0,x1,y1] 0-1.

## Allowed writes
Only these paths may be created or modified by this task:

Backend (modify existing):
- `backend/app/db.py`
- `backend/app/schemas.py`
- `backend/app/main.py`
- `backend/app/jobs.py`
- `backend/app/config.py`

Backend (new files):
- `backend/app/providers/__init__.py`
- `backend/app/providers/gemma.py`
- `backend/app/prompts/locate.txt`
- `backend/app/prompts/check.txt`
- `backend/app/search.py`
- `backend/tests/test_search.py`

Frontend (modify existing):
- `frontend/src/api.ts`
- `frontend/src/App.tsx`
- `frontend/src/App.css`
- `frontend/src/components/QuestionBar.tsx`
- `frontend/src/components/EvidenceList.tsx`
- `frontend/src/components/PageViewer.tsx`

Generated/ignored outputs:
- `data/` (gitignored)
- `out/orchestration/search-highlight/` (evidence directory)

## Prohibitions
- No git commands, branch switches, commits or pushes.
- No paid provider calls, billing changes or credit purchases.
- No model other than gemma-4-31b-it (or gemma-4-26b-a4b-it as documented
  fallback if primary is unavailable during this task).
- No silent model switch. Record any fallback selection before using it.
- No modifications to orchestration scripts, docs/orchestration/, prior task
  docs, fixtures/holdout.json, or the existing fixture generator.
- No WebSocket implementation. Polling is sufficient for P0.
- No generated answer text in search results. Source-only output.
- No credential values in source, logs, prompts, or evidence files.
- No web search, tool execution, URL fetching, or grounding tools in inference.
- Do not weaken existing test assertions or remove existing passing tests.
- Do not start a web server or background process that outlives the task.
- Do not modify files outside allowed writes.

## Steps

### Step 1: Extend database schema

Update `backend/app/db.py` to add schema version 2 with migration. Add tables
from PRODUCT_BRIEF.md section 11: `searches`, `page_checks`, `evidence`,
`usage_events`. Use the exact field lists from the spec. Add an ON DELETE
CASCADE from evidence to searches and from page_checks to pages. On startup,
run migration from v1 to v2 if needed; leave v1 tables untouched. Mark
previously running search jobs as interrupted on restart.

### Step 2: Create Gemma provider

Create `backend/app/providers/__init__.py` (empty) and
`backend/app/providers/gemma.py`.

The provider module must:
- Use `google.genai` client with the configured GEMINI_API_KEY.
- Implement `inspect_page(question: str, page_image_path: Path, settings) -> dict`
  that sends the locate prompt + full page image and returns validated JSON.
- Implement `check_evidence(question: str, page_image_path: Path, crop_image: bytes, proposed_boxes: list, settings) -> str`
  that sends the check prompt + page image + crop and returns accepted|rejected|uncertain.
  If two-image input fails, fall back to single-image check with box coordinates
  and record the reduced mode.
- Parse JSON from model response, stripping markdown code fences if present.
- Validate response against the schema in PRODUCT_BRIEF.md section 9.
- Use low temperature, bounded output length, finite HTTP timeout from settings.
- Rate limit: respect settings.requests_per_minute with a simple token-bucket or
  sleep-based pacer.
- Retry transient 429/5xx/timeout at most twice with increasing delay and jitter.
- Record usage events (timestamp, model, status, latency_ms) for each call.
- At most one schema-repair attempt for malformed output.
- Never eval model output. Strip only enclosing markdown fences.

### Step 3: Create prompt files

Create `backend/app/prompts/locate.txt` with the page-inspection prompt from
PRODUCT_BRIEF.md section 9 (the exact contract text). Include the JSON schema
example. Use `{question}` as the placeholder for the user's question.

Create `backend/app/prompts/check.txt` with the evidence-checking prompt. Ask
whether the selected evidence group contains enough visible information and
whether essential labels/units/connections were omitted. Return only
`accepted | rejected | uncertain`.

### Step 4: Implement search engine

Create `backend/app/search.py` implementing the search workflow from
PRODUCT_BRIEF.md sections 9 and 10:

1. Accept question + list of document IDs. Snapshot ready page IDs and hashes.
2. For each page in document order then physical page order:
   a. Check cache (key: page raster hash + trimmed question + model + prompt version).
   b. If not cached, call inspect_page. Persist the page_check.
   c. If status=found, crop the evidence region with 5% padding (clipped to page).
   d. Call check_evidence with question + page + crop + proposed boxes.
   e. Persist the check result. Only accepted groups become evidence.
3. Track checked_pages/total_pages. Respect cancel_requested.
4. Determine search outcome: found, no_evidence, uncertain, incomplete.
5. Persist search record with outcome, coverage, model_id, prompt_version.
6. Respect max_calls_per_search budget. Stop incomplete on budget exhaustion.
7. Cache valid not_found and uncertain as well as found results.
8. Do not cache transport failures as negative evidence.

Use Pillow to create the contextual crop from the canonical raster. The crop
is the union of evidence boxes with 5% padding on each side, clipped to [0,1].

### Step 5: Add search API endpoints

Add to `backend/app/main.py` the search endpoints from PRODUCT_BRIEF.md section 12:

- `POST /api/searches` — question + document_ids, capture page snapshot, create
  job, run search synchronously (same pattern as import), return 202 + IDs.
  Reject if no ready documents, empty question, question > 1000 chars trimmed,
  or another job is active. Validate document IDs exist and are ready.
- `GET /api/searches` — recent searches for reload.
- `GET /api/searches/{id}` — outcome, coverage, evidence with boxes in app coords.
- `GET /api/jobs/{id}` — state, progress, error info.
- `POST /api/jobs/{id}/cancel` — set cancel_requested flag.

Evidence response must match the example payload in PRODUCT_BRIEF.md section 12:
evidence items include document_id, filename, page_id, physical_page_number,
kind, scope, boxes (app coords), image_url. No answer, quotation, chain-of-thought
or confidence field.

### Step 6: Update schemas

Add Pydantic models to `backend/app/schemas.py`: SearchRequest, SearchCreated,
SearchResponse, EvidenceItem, JobResponse, CoverageInfo. Match the API contract.

### Step 7: Wire up frontend

**QuestionBar.tsx**: Accept question text and selected document IDs (from parent).
On Find, POST /api/searches. Poll GET /api/jobs/{id} every 2 seconds for
progress. Show "Checking page X of Y" during search. Show outcome wording
from PRODUCT_BRIEF.md section 7. Disable Find while a job is active. Show
cancel button during active search.

**EvidenceList.tsx**: Display result cards for each evidence item. Each card
shows a contextual crop (use canvas or img with clip), filename, physical page
number, and kind label (Diagram, Table, etc.). Clicking a card calls onSelect
with page_id and boxes to focus the viewer.

**PageViewer.tsx**: Add an SVG overlay for highlight rectangles. Use
`viewBox="0 0 1000 1000"` and `preserveAspectRatio="none"` matching the image
rect. Render boxes as translucent rects with visible border. Transform
app-coord boxes [x0,y0,x1,y1] to SVG rect attributes. Respect the existing
zoom/pan transform. Add a "Toggle Highlight" control.

**App.tsx**: Thread document selection state to QuestionBar. Pass search results
from QuestionBar/EvidenceList to PageViewer. On evidence card click, set viewer
to the matching page with highlight boxes.

**api.ts**: Add createSearch, getSearch, listSearches, getJob, cancelJob
functions.

### Step 8: Focused backend tests

Create `backend/tests/test_search.py` with:

- Test that inspect_page with a mocked provider double returns valid parsed
  response and persists page_check.
- Test that check_evidence with accepted/rejected/uncertain responses are
  handled correctly.
- Test geometry: provider boxes are converted to app coords in evidence.
- Test that malformed model output (extra fields, invalid boxes, injection
  attempt with answer text) is rejected.
- Test search outcome determination: found, no_evidence, uncertain, incomplete.
- Test cache hit: identical question + same page hash skips provider call.
- Test cancel: setting cancel_requested stops scheduling new pages.
- Test budget: exceeding max_calls_per_search stops with incomplete.
- Use deterministic provider doubles, not real API calls.

### Step 9: Build verification

Run these commands and capture exit codes in
`out/orchestration/search-highlight/command-results.json`:

1. `C:\Users\vaidy\.local\bin\uv.exe sync --project backend --python 3.12`
2. `npm --prefix frontend ci`
3. `C:\Users\vaidy\.local\bin\uv.exe run --project backend pytest backend/tests -v`
4. `npm --prefix frontend run build`

Write `out/orchestration/search-highlight/report.json` with:
```json
{
  "checks": {
    "all_pass": true/false,
    "finalized": true/false,
    "uv_sync_exit": <exit_code>,
    "pytest_exit": <exit_code>,
    "npm_ci_exit": <exit_code>,
    "vite_build_exit": <exit_code>,
    "search_test_count": <number of test_search tests that passed>,
    "existing_tests_pass": true/false
  }
}
```

Set `all_pass = true` only when all four commands exit 0 AND existing tests
(test_geometry, test_upload, test_lifecycle) still pass AND at least 6
test_search tests pass. Set `finalized = true` after writing the report.

## Done-when

All of these must be true in evidence files:
1. `out/orchestration/search-highlight/report.json`: `checks.all_pass = true` AND `checks.finalized = true`
2. `out/orchestration/search-highlight/report.json`: `checks.uv_sync_exit = 0`
3. `out/orchestration/search-highlight/report.json`: `checks.pytest_exit = 0`
4. `out/orchestration/search-highlight/report.json`: `checks.npm_ci_exit = 0`
5. `out/orchestration/search-highlight/report.json`: `checks.vite_build_exit = 0`
6. `out/orchestration/search-highlight/report.json`: `checks.existing_tests_pass = true`
7. `out/orchestration/search-highlight/report.json`: `checks.search_test_count >= 6`
8. `out/orchestration/search-highlight/command-results.json` exists with 4 entries
9. `backend/app/providers/gemma.py` exists
10. `backend/app/prompts/locate.txt` exists
11. `backend/app/prompts/check.txt` exists
12. `backend/app/search.py` exists
13. `backend/tests/test_search.py` exists
14. POST /api/searches endpoint is defined in main.py
15. GET /api/searches/{id} endpoint is defined in main.py
16. GET /api/jobs/{id} endpoint is defined in main.py
17. QuestionBar.tsx contains a working Find button (not permanently disabled)
18. EvidenceList.tsx renders evidence cards (not a placeholder)
19. PageViewer.tsx includes an SVG overlay for highlight rectangles

## Escape hatch

If the Gemini API is unreachable or returns persistent errors during testing,
complete all implementation with the provider double and record the API failure
in the report. Do not fabricate successful API responses. The provider module
must be complete and ready for live calls even if tests use doubles.

If two-image evidence checking fails (model rejects or API doesn't support it),
implement single-image checking with box coordinates overlay and record the mode.

## Timeout
100 minutes.

Report, then STOP.
