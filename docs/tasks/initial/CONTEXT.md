# Initial context: Visual Evidence

Authoritative inputs: docs/product/PRODUCT_BRIEF.md and SETUP_HANDOFF.md.
Product path: C:/Users/vaidy/Documents/Pinpoint/visual-evidence.
Framework source remains separate at ../agent-orchestration-system.
New adoption has no prior approvals, reviewed memory, tasks or app implementation.
Windows PowerShell 5.1 and Python 3.14 are installed for orchestration.
Python 3.12 and uv are not yet installed. Node/npm and all three coding CLIs exist.
Inherited role model IDs remain explicit in orchestration.json; availability
requires live smoke tests and pilot. No provider/model substitutions authorized.
Product origin: C:/Users/vaidy/Documents/Pinpoint/visual-evidence-remote.git (local).
GEMINI_API_KEY is present in .env. OPENROUTER_KEY is also present for
google/gemma-4-31b-it:free via OpenRouter (https://openrouter.ai/api/v1).
Planned model gemma-4-31b-it. The application provider module should attempt
the Gemini API first and fall back to OpenRouter if unavailable.
Image/geometry/schema preflight remains unverified and must run before search work.
Capacity: 20 pages across five documents, 25 MB/upload, 20 MP/image, one job.
Real test PDFs are at fixtures/documents/ (gitignored large binaries).
Read fixtures/documents/Testing documents readme.md for the full test plan:
5 documents (Raspberry Pi Pico datasheet, TI NE555 timer, Lippert electric step
diagnostics flowchart, Prusa MK3S+ handbook, FAA Pilot's Handbook excerpt) with
specific page ranges, sample questions and expected evidence targets per document.
Use these for live evaluation. Also generate synthetic fixtures under
fixtures/generated/ with known coordinates for deterministic geometry tests.
uv is installed at C:\Users\vaidy\.local\bin\uv. All smoke tests passed.
Exact geometry, state, API and evaluation contracts are in the product brief.
No reports or passing gates have been created. See out/setup for setup evidence.
