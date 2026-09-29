# Task 1 — Restore visual evidence search

Read `docs/product/BUILD_DIRECTIVE_2026-09-23.md`, relevant `PRODUCT_BRIEF.md` sections, the current code, and prior holdout summary. Work only in this checkout. Preserve unrelated uncommitted changes and evidence files. Do not use further agent delegation.

Implement the real question → page image VLM inspection → validated region → contextual check → persisted evidence path. The existing `backend/app/search.py` is a text-only rewrite and currently ignores `inspect_fn`/`check_fn`; it is broken for visual questions. The baseline Git revision `8838a4a` contains the previous VLM engine. Reuse/adapt it as appropriate; do not overwrite current fixes blindly. Stop import-time Nemotron calls from gating or replacing visual search. A missing Gemma key or provider failure must be reported as incomplete/error, never as no evidence. Keep the provider's minimal-thinking setting that was required for the configured 26B model.

Ensure `backend/app/main.py` invokes the VLM path and uses the ignored `.env` safely. Make deterministic backend tests cover found, absent, uncertain, malformed, cache, cancellation, API integration and persistence. Fix the existing 11 test failures caused by the text-only rewrite. Tests should not make network calls. Keep source-only UI output.

Acceptance: `backend/.venv/Scripts/python.exe -m pytest backend/tests -q` passes with `PYTEST_ADDOPTS=-p no:cacheprovider` and a writable temp directory. `npm --prefix frontend run build` should remain viable. Record commands, counts, changes and unresolved issues in `out/rapid-build/01-report.md`. Do not claim live visual quality from mocks. Report, then STOP.

