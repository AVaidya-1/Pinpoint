# Director Kickoff — Pinpoint

## What this app does

A localhost web application where one person uploads technical PDF pages or
images, asks a natural-language question, and sees the relevant source region
highlighted on the original page. The result is the source image with a
bounding box — no AI-written answer text, no summary, no generated explanation.

The app must work on diagrams, flowcharts, tables, charts, and raster-only
pages without searchable text. If the model can't find evidence, it says so
honestly — it never invents a location.

Read **docs/product/PRODUCT_BRIEF.md** for the complete specification. That
document controls scope.

## Model access

Two free API keys are in `.env` (gitignored):

- `GEMINI_API_KEY` — Google's Gemini API, model `gemma-4-31b-it`
  (docs: https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api)
- `OPENROUTER_KEY` — OpenRouter, model `google/gemma-4-31b-it:free`
  (endpoint: https://openrouter.ai/api/v1, OpenAI-compatible)

Both are free tier. Use whichever works.

## Test documents — USE THESE

Five real-world PDFs are at `fixtures/documents/` (gitignored binaries).
Read **`fixtures/documents/Testing documents readme.md`** for the full test
plan — it has specific questions and expected evidence targets for each document.

| Document | What it tests |
|---|---|
| Raspberry Pi Pico datasheet | Pinout diagrams, spec tables, mechanical drawings |
| TI NE555 timer datasheet | Block diagrams, spec tables, characteristic curves |
| Lippert electric step diagnostics | Flowchart branches, decision nodes — core demo |
| Prusa i3 MK3S+ handbook | Photos, assembly callouts, text lookup |
| FAA Pilot's Handbook excerpt | Instrument markings, schematic routing |

Use these for live evaluation.

## What's set up

- Product checkout: `C:\Users\vaidy\Documents\Pinpoint\visual-evidence`
- Git branch: `codex/app-build` (baseline committed)
- All smoke tests passed, dashboard verified on port 8765
- `uv`, Node v24.14.1, Python 3.14.3 available
- All three coding CLIs authenticated

## What's NOT built yet

No application code, no tests, no evaluation, no APP_README.md.

## Worker preference

Prefer the Worker role (OpenCode) for implementation tasks — it uses a free
model. Minimize usage of paid-tier roles where possible.

## Acceptance criteria

See PRODUCT_BRIEF.md sections 15 and 18 for the full criteria. Summary:

**Software (A1–A12):** Import works, search produces highlighted source
regions, geometry is correct at all zoom levels, persistence survives restart,
failure states are honest, no generated answer text in the UI.

**Live evaluation:** Test against the real PDFs in fixtures/documents/ using
the questions in the test readme. If quality thresholds aren't met, deliver
the working app and honestly report what failed.

## Hard rules

- Localhost only. No deployment, cloud services, or external notifications.
- No paid fallbacks or credit purchases.
- Credentials stay out of source, logs, screenshots and prompts.
- Note in the UI that images are sent externally for processing.
- Do not fake results or weaken acceptance thresholds.
- The root `.venv` belongs to the orchestration framework — don't touch it.
- App ports: 8000 (backend), 5173 (frontend). Dashboard: 8765.
