# Task 4 — Runnable handoff and final repair

Read `docs/product/BUILD_DIRECTIVE_2026-09-23.md` and all rapid-build reports. Use a fresh Claude Code Sonnet 4.6 session. Do not use further agent delegation. Fix only concrete remaining blockers that prevent the core upload → ask → auto-scroll/highlight journey or a reproducible start. Do not erase failed test/evaluation evidence.

Write `APP_README.md` with exact install, start, stop and test commands; ports; configured model; where originals/results live; how 500-page import and search coverage work; required key setup without revealing the key; and limitations, including any failure of live diagram localization. Ensure a one-command launcher for localhost works and is checked. Start the app on localhost, verify its health and browser UI, and leave it running if the host permits so the owner can open it directly. Run final deterministic checks and a browser smoke test, recording actual results in `out/rapid-build/04-report.md`.

Write `out/rapid-build/final-status.json` containing `status` (`complete`, `partial`, or `blocked`), `software_checks`, `live_evaluation`, `five_hundred_page_proof`, `app_url`, and `remaining_issues`. Use `complete` only if the core journey and all required checks truly pass; report quality separately even if software is runnable. Report, then STOP.
