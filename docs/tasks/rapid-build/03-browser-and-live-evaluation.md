# Task 3 — Browser and real-model verification

Read `docs/product/BUILD_DIRECTIVE_2026-09-23.md` and prior rapid-build reports. Use a fresh Claude Code Sonnet 4.6 session. Do not use further agent delegation. Preserve previous results and do not weaken frozen holdout thresholds.

Run backend tests, strict TypeScript check, frontend build and Playwright browser tests. Fix actual integration failures. Exercise upload of PDF/image, long PDF page jump, question submission, result click with automatic scroll/focus and visible highlight, zoom alignment, reload persistence, absent question and provider error. Save browser screenshots where useful. Use mocks for deterministic software behavior and label them as mocks.

Run one real configured Gemma preflight and a small real diagram question first. If the endpoint or quota is unavailable, document the exact blocker and skip additional paid/alternate provider work. If available, run the frozen 20-question holdout via `app_tools/evaluate.py` against the current real pipeline, without exposing truth to prompts. Keep results and denominators. Report performance and failures honestly. Do not tune against the holdout. Add a separate small real-world document observation if time permits.

Write `out/rapid-build/03-report.md` with commands, test counts, real model results, timing, screenshots and known failures. Report, then STOP.

