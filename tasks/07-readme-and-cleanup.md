# Task 7: APP_README, Cleanup & Final Validation

## Goal
Write the APP_README.md, clean up the project, verify the .gitignore, and do a final validation pass.

## Context
This is a localhost proof-of-concept for finding source regions in technical documentation — engineering manuals, datasheets, flowcharts, wiring diagrams, specification tables. Upload PDF/image pages, ask a question, see the relevant region highlighted on the original page.

Working name was "Visual Evidence" but the UI uses "Pinpoint" as the brand name.

## Steps

### 1. Write `APP_README.md` at the project root

Include:

```markdown
# Pinpoint — Visual Evidence Finder

Find the exact place in your technical documents. Upload PDF pages or images,
ask a natural-language question, and see the source region highlighted on the
original page. No AI-written answers — just the source, highlighted.

## What it does

- Upload PDF, PNG, and JPEG files (up to 20 pages across 5 documents)
- Select specific page ranges from large PDFs
- Ask questions about diagrams, tables, flowcharts, charts, and photos
- See the original page with the relevant region highlighted
- Zoom, pan, and inspect the full source context

Designed for technical documentation: engineering manuals, datasheets,
installation drawings, troubleshooting guides, specification tables.

## Quick start

### Prerequisites
- Python 3.12+
- Node.js (LTS)
- uv (Python package manager): `pip install uv`
- A Gemini API key (free tier): https://aistudio.google.com/app/apikey

### Setup
```bash
# Backend
cd backend
uv sync --python 3.12

# Frontend
cd ../frontend
npm install

# Environment
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

### Generate test fixtures
```bash
cd backend && .venv/Scripts/python.exe ../fixtures/generate.py
```

### Run
```bash
cd backend && .venv/Scripts/python.exe ../app_tools/dev.py
```
Open http://127.0.0.1:5173 in your browser.

### Test
```bash
# Backend tests
cd backend && .venv/Scripts/python.exe -m pytest tests/ -v

# Frontend build check
cd frontend && npx vite build

# E2E tests (requires dev server)
cd frontend && npx playwright test

# API preflight
cd backend && .venv/Scripts/python.exe ../app_tools/preflight.py

# Live evaluation (requires API key)
cd backend && .venv/Scripts/python.exe ../app_tools/evaluate.py --suite ../fixtures/holdout.json --live
```

## How it works

1. **Upload** → validates file, renders PDF pages via pypdfium2, saves canonical rasters
2. **Search** → sends each page image + question to Gemma VLM via Gemini API
3. **Locate** → model returns bounding boxes for relevant regions
4. **Check** → second pass verifies the evidence with a contextual crop
5. **Display** → original page with SVG highlight overlay, zoomable viewer

## Architecture

- **Backend**: Python 3.12, FastAPI, SQLite, pypdfium2, Pillow, google-genai
- **Frontend**: React 18, TypeScript, Vite, react-zoom-pan-pinch
- **Model**: gemma-4-31b-it via Gemini API (free tier, images sent to Google)
- **Storage**: Local SQLite + filesystem (no cloud database)

## Limitations

- 20-page workspace limit (POC constraint, not model limit)
- 5-document limit per workspace
- 25 MB per upload
- 6 API calls/minute rate limit (configurable)
- Search is synchronous — each page inspected sequentially
- No authentication, multi-user, or deployment support
- Images are sent to Google for processing (not kept locally only)
- Model may select wrong regions — always inspect the source
- No DOCX/PPTX/XLSX support
- No password-protected PDF support
```

### 2. Verify `.gitignore`

Ensure these are ignored:
```
data/
out/
.env
*.db
backend/.venv/
frontend/node_modules/
frontend/dist/
frontend/test-results/
__pycache__/
*.pyc
.DS_Store
fixtures/generated/
fixtures/documents/
```

### 3. Clean up stale files

- Remove any empty README.md files in subdirectories that just say "placeholder"
- Remove any orchestration-system files that don't belong (the `scripts/`, `docs/orchestration/`, `orchestration.json`, `Start Agent App.cmd` are from the agent orchestration system — leave them for now but they should eventually be removed)

### 4. Final validation run

Run everything in sequence and verify:
```bash
# 1. Generate fixtures
cd backend && .venv/Scripts/python.exe ../fixtures/generate.py

# 2. Backend tests
cd backend && .venv/Scripts/python.exe -m pytest tests/ -v

# 3. Frontend build
cd frontend && npx vite build

# 4. Dev server check
cd backend && .venv/Scripts/python.exe ../app_tools/dev.py --check
```

All must pass. Document any failures.

## Success Criteria
- `APP_README.md` exists with complete setup, run, and test instructions
- `.gitignore` covers all generated/sensitive files
- Final validation passes all 4 checks
- No secrets (API keys, credentials) in any tracked file
