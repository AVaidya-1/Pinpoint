# Task 1: Environment Setup & Dependency Verification

## Goal
Ensure all dependencies are installed and the app can start. This is the foundation for every other task.

## Context
This is a Visual Evidence localhost app: upload technical PDF/image pages, ask a natural-language question, see the relevant region highlighted on the original page. It uses Python 3.12 + FastAPI backend and React + TypeScript + Vite frontend.

The project lives at the current working directory. Backend is in `backend/`, frontend is in `frontend/`.

## Steps

1. **Backend dependencies** — Run from the project root:
   ```
   cd backend
   uv sync --python 3.12
   ```
   If `uv` is not available, use `pip install -e .` inside `backend/.venv`. The backend needs: fastapi, uvicorn, python-multipart, python-dotenv, pypdfium2, Pillow, pydantic, google-genai, httpx, reportlab, pytest, pytest-asyncio.

2. **Frontend dependencies** — Run from the project root:
   ```
   cd frontend
   npm install
   ```
   The frontend needs: react, react-dom, react-zoom-pan-pinch, vite, typescript, @vitejs/plugin-react, @playwright/test.

3. **Verify `.env` exists** — Check that `.env` exists at the project root with at minimum `GEMINI_API_KEY=` (it can be empty for now, but the file must exist). If not, copy from `.env.example`.

4. **Generate fixtures** — Run:
   ```
   cd backend && .venv/Scripts/python.exe ../fixtures/generate.py
   ```
   This should create `fixtures/generated/` with test PDFs, images, and JSON manifests. Verify the output files exist.

5. **Run backend tests** — Run:
   ```
   cd backend && .venv/Scripts/python.exe -m pytest tests/ -v
   ```
   All tests in `test_geometry.py` and `test_upload.py` must pass.

6. **Verify frontend builds** — Run:
   ```
   cd frontend && npx vite build
   ```
   Must complete without TypeScript or build errors.

7. **Verify dev server starts** — Run:
   ```
   cd backend && .venv/Scripts/python.exe ../app_tools/dev.py --check
   ```
   This starts both backend (port 8000) and frontend (port 5173), checks health, then shuts down. Must exit 0.

## Success Criteria
- `fixtures/generated/` contains test_pages.pdf, portrait.pdf, landscape.pdf, cropbox.pdf, exif_oriented.jpg, standard.png
- `fixtures/development.json` and `fixtures/holdout.json` exist
- All pytest tests pass
- Frontend builds without errors
- Dev server health check passes (exit 0)

## If Something Fails
- If `uv` is not found, install it: `pip install uv`
- If node is not found, check PATH
- If pypdfium2 fails to install, try `pip install pypdfium2` directly
- If frontend build fails with TS errors, fix the TypeScript issues in `frontend/src/`
- If dev.py --check fails, check that ports 8000 and 5173 are free
