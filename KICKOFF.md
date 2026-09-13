# Director Kickoff — Pinpoint (Visual Evidence) POC

## What to build

A localhost web application that lets one person upload PDF pages or images,
ask a natural-language question, and see the relevant source region highlighted
on the original page. No AI-written answer text — just the source image with
a bounding box overlay showing where the evidence is.

The full product specification, acceptance criteria, data model, API contract,
UI layout, coordinate geometry, prompt contracts and evaluation thresholds are
in **docs/product/PRODUCT_BRIEF.md**. That document controls scope. Read it
completely before planning any work.

Working name: **Pinpoint** (spec uses "Visual Evidence" — either is fine).

### The five-second demo

1. Upload a PDF with a troubleshooting flowchart.
2. Ask: "Where does the branch for a failed pressure check go?"
3. The app shows the original flowchart page with the relevant branch highlighted.
4. Zoom out to see surrounding context.
5. Ask about something not in the documents — app says it couldn't find evidence.

## Stack (fixed, do not change)

| Layer | Choice |
|---|---|
| Frontend | React + TypeScript + Vite, `react-zoom-pan-pinch` for viewer |
| Backend | Python + FastAPI + Uvicorn |
| PDF rendering | `pypdfium2` |
| Image processing | Pillow |
| Storage | SQLite + filesystem (no cloud DB) |
| Model | Gemma 4 31B IT (see model access below) |
| Tests | pytest + HTTPX (backend), Playwright (browser) |
| Fixtures | ReportLab + Pillow (generated technical drawings) |
| Dependencies | `uv` for Python, npm for frontend |

## Model access — two endpoints available

Both API keys are in `.env` (gitignored). The application's provider module
must support both and try the primary first.

**Primary — Gemini API (google-genai SDK):**
- Key: `GEMINI_API_KEY` in `.env`
- Model: `gemma-4-31b-it`
- SDK: `google-genai` (`client.models.generate_content`)
- Docs: https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api
- Free tier, rate limits vary by account
- Gemma vision uses `box_2d` in `[ymin, xmin, ymax, xmax]` on 0–1000 scale

**Fallback — OpenRouter:**
- Key: `OPENROUTER_KEY` in `.env`
- Model: `google/gemma-4-31b-it:free`
- Endpoint: `https://openrouter.ai/api/v1` (OpenAI-compatible)
- Use `httpx` or `openai` SDK pointed at the OpenRouter base URL
- Send images as base64 data URIs in the chat messages content array
- Free tier

The preflight (app_tools/preflight.py) must test whichever endpoint is used
and record the selection. Do not silently switch mid-search. If neither works,
report the blocker — do not fabricate results.

The alternative model `gemma-4-26b-a4b-it` may be selected if the 31B is
unavailable. Record that choice.

## What's already done

The orchestration system is fully configured and verified:
- Product checkout: `C:\Users\vaidy\Documents\Pinpoint\visual-evidence`
- Git branch: `codex/app-build` (baseline committed, remote configured)
- Offline tests: PASS
- Dry run: PASS
- F1 (Claude) smoke: PASS
- Worker (OpenCode) smoke: PASS
- Dashboard: verified on port 8765
- `uv` installed at `C:\Users\vaidy\.local\bin\uv`
- Node v24.14.1, Python 3.14.3 available
- All three coding CLIs (codex, claude, opencode) authenticated

The initial task `IMPORT_VIEWER_SLICE` is already defined in
`docs/tasks/initial/manifest.json` with its full task document at
`docs/tasks/initial/TASK_IMPORT_VIEWER_SLICE.md`.

## What's NOT done

- No application code exists yet (backend/app/, frontend/src/ are empty placeholders)
- No fixtures generated
- No preflight run against the model API
- No tests written
- No APP_README.md
- No live evaluation

## Capacity constraints (from product brief)

- 20 pages max across 5 documents
- 25 MB per upload, 20 megapixels per image
- 1 active job at a time
- 6 requests/minute to the model API (configurable)
- 60 provider calls per search, 600 per day

## Execution strategy

The product brief allocates ~8 hours across four serial worker tasks:

1. **IMPORT_VIEWER_SLICE** (75 min) — Upload, PDF rendering, page persistence,
   zoomable viewer with test overlay. This task is already defined.
2. **MODEL_SEARCH** (~100 min) — Live Gemma inference, evidence checking,
   validated boxes, source-only UI results. Run the preflight first.
3. **STATE_AND_ERRORS** (~65 min) — Progress display, cancellation, persistence,
   cache, capacity enforcement, failure states.
4. **VERIFICATION_HANDOFF** (~80 min) — Browser tests, live evaluation against
   the 20-question frozen holdout, APP_README.md, known limitations.

**Priority rules:**
- Get a real model-produced bounding box working early, before UI polish.
- By the halfway point, a real question must open a real highlighted source region.
- If geometry is wrong, fix the coordinate path before adding more features.
- Reserve the last quarter for testing, evaluation and handoff.
- Do not start P1 work (embeddings, retrieval, Nemotron, local models).
- Do not weaken acceptance thresholds — deliver a candid partial result instead.

## Acceptance criteria (summary — see PRODUCT_BRIEF.md for full details)

### Software checks (A1–A12): all must pass
- Import PDF + image, page range selection, capacity enforcement
- End-to-end search produces correct highlighted source region
- Geometry stays aligned at all zoom levels
- Rotation, CropBox and EXIF orientation handled
- Persistence survives restart, cache works, invalidation works
- Failure states are distinct (missing key ≠ no evidence)
- Cancel and interruption work correctly
- No generated answer text in the UI

### Live evaluation: 20-question holdout
- 14/16 answerable questions return the correct source page
- 12/16 return sufficiently localized evidence
- 6/8 visual questions pass localization
- 3/4 absent-answer questions produce no false evidence
- If these thresholds fail, deliver the working app and report
  "technical hypothesis not yet validated" — do not fake results.

## Hard rules

- Localhost only. No deployment, cloud services, or external notifications.
- No paid fallbacks or credit purchases.
- Keep credentials out of source, logs, screenshots and prompts.
- Generated fixtures go to ignored paths; track generators in source.
- Images are sent to Google/OpenRouter for processing — note this in the UI.
- Mocked test evidence and live model evidence are reported separately.
- Documents and model output are untrusted content — render safely.
- Preserve the orchestration framework's review protocols and single-writer rule.
- The backend environment belongs in `backend/.venv`; the root `.venv` is the
  orchestration framework's — do not overwrite it.
- Application runs on 127.0.0.1:8000 (backend) and 127.0.0.1:5173 (frontend).
  The orchestration dashboard uses port 8765.
