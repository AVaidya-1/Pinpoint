# Round 010 context: Import and viewer vertical slice

## Goal
Deliver the first vertical slice of Visual Evidence: upload PDF/image,
select pages, render canonical rasters, persist documents and pages in SQLite,
and display them in a zoomable React viewer with a deterministic test overlay.

This round revises round-009 to address F2's ninth REVISE verdict
(message `20260914073100017_c62a76a29e3246669d23313783f2453d`)
and the Director's focused-revision briefing in `director_plan.md`.

## Changes from round-009
1. **Server lifecycle: no Playwright webServer**: Removed top-level `webServer`
   from playwright.config.ts entirely. The "main" project's e2e.spec.ts starts
   dev.py in `test.beforeAll()` via child_process.spawn, captures PIDs, waits
   for health, and kills by PIDs in `test.afterAll()`. The "restart" project's
   restart.spec.ts manages its own independent server lifecycle as before.
   No competing process ownership: each test file that needs a server starts
   and stops one explicitly. Shutdown targets the dev.py launcher PID, which
   stops its children on exit.
2. **All 13 screenshots required**: The validator requires all 13 named
   screenshots, not a minimum of 3. The manifest gates `screenshot_count = 13`.
   No optional screenshots in the exact-output contract.
3. **Receipt verifies exact command record and artifact set**: The verification
   receipt checks that command-results.json has exactly 8 entries with the
   exact expected names in the required order. It also compares report.json's
   artifacts list against a known expected file set and gates set equality.
   Receipt schema adds `command_count_valid`, `command_order_valid`,
   `artifacts_set_valid`, and `artifacts_set_count`.
4. **Hash claim corrected**: Hash presence proves format, not write order.
   Hash equality (verified independently by the receipt's SHA-256 recomputation)
   proves that report.json references the current validation.json bytes.
   No temporal ordering claim.

## Prior evidence
Key facts cite `out/orchestration/state-inventory-20260914.json` as the
consolidated primary evidence source. That file was captured before
round-008 planning; its git.untracked field lists rounds 001-007 only.
Rounds 008, 009 and 010 plan files are expected additional untracked items
not covered by the snapshot.

- **Git baseline**: Commit `20a8ed4` on branch `codex/app-build`. No tracked
  diff. Untracked at inventory time: `docs/tasks/round-001/` through
  `round-007/` (plan files). Current untracked also includes round-008/,
  round-009/ and round-010/. Origin: `C:/Users/vaidy/Documents/Pinpoint/visual-evidence-remote.git`.
  Evidence: `out/orchestration/state-inventory-20260914.json` field `git`.
- **No application runtime code**: `backend/app/` does not exist.
  `out/orchestration/import-viewer/` does not exist.
  `app_tools/preflight.py` is a setup utility.
  Evidence: `out/orchestration/state-inventory-20260914.json` field
  `application_state`.
- **No Worker dispatch**: No worker dispatch for IMPORT_VIEWER_SLICE found.
  Evidence: `out/orchestration/state-inventory-20260914.json` field
  `worker_dispatch`.
- **Setup preflight**: Gemma locate + full-page-plus-crop passed.
  Evidence: `out/setup/gemma-20260913T192947078057Z/report.json` (cited in
  state inventory). Preflight proves only the Gemini key; OpenRouter and
  NVIDIA key functionality is unverified by any preflight.
- **Role smoke tests**: All four roles exit 0.
  Evidence: `out/setup/smoke-results.json` (cited in state inventory).
  Note: verifies CLI availability, not host tool versions.
- **Pilot**: PILOT-PASS with F2 acceptance and Director acceptance.
  Evidence: `out/orchestration_pilot/a972fef9b8604a88a62a1fa4527b75e8/runtime.json`,
  `out/orchestration_pilot/a972fef9b8604a88a62a1fa4527b75e8/f2_review.md`,
  `out/orchestration_pilot/a972fef9b8604a88a62a1fa4527b75e8/logs/pilot_director_dd08c8179c10449aa68c0350ca63f6dc.md`.
- **Host tools**: `C:/Python314/python.exe` = 3.14.3. WindowsApps `python`
  shim = intermittent/inaccessible. Not used by app. Node v24.14.1.
  uv 0.12.13 at `C:/Users/vaidy/.local/bin/uv.exe`. App targets Python 3.12 via uv.
  Evidence: `out/orchestration/state-inventory-20260914.json` field `host_tools`.
- **API keys**: GEMINI_API_KEY, OPENROUTER_KEY, NVIDIA_API_KEY all present
  in `.env` (gitignored). Only Gemini key verified by preflight.
  Evidence: `out/orchestration/state-inventory-20260914.json` field `api_keys`.
- **Fixture documents**: Five real test PDFs in `fixtures/documents/`.
  Evidence: `out/orchestration/state-inventory-20260914.json` field
  `fixture_documents`.
- **No product-task execution evidence was found**.
  Evidence: `out/orchestration/state-inventory-20260914.json` field
  `worker_dispatch` (0 matches for worker dispatch in communications.md).
- **Archived TEST-round escalation**:
  `out/orchestration/runtime/logs/f22548ac8d444131936b3bba4642d108_director_request.md`
  records an escalation citing "three unsuccessful rounds" with task TEST.
  Director dissent at
  `out/orchestration/runtime/logs/director_INITIAL_3d4fb232b72749678fb8dc0322668863.md`
  instructed establishing provenance before carrying the failure count.
  Preserved as unverified history.
- **Planning rounds 001-009**: Nine planning iterations refining this task,
  each producing plan files under `docs/tasks/round-NNN/`.
  Evidence: `docs/tasks/round-001/` through `docs/tasks/round-009/` (untracked).

## Director guidance
From `out/orchestration/runtime/director_plan.md`:
- Use one external harness to own test-server startup, restart and teardown
  by captured process IDs. Remove competing Playwright server ownership.
- Require the exact ordered eight-command record and exact pre-receipt
  artifact inventory, including all 13 required screenshots. Verify equality,
  not merely existence of whatever the report lists.
- Keep receipt generation after report finalization. Hash equality establishes
  integrity, not execution order.
- Cite current checkout evidence accurately; preserve historical inventories
  unchanged.

## Active owner requirements
All requirements below remain active until the corresponding deliverable
is verified. Evidence citations are to the originating messages.

- Use all five real PDFs in `fixtures/documents/` for live evaluation
  (deferred to model-integration round; this round builds the infrastructure).
  Evidence: messages `20260913210255043` and `20260913210334520`.
- Check actual physical pages and evidence targets; do not assume readme
  page references are correct.
  Evidence: message `20260913210334520`.
- Bounded selections within 20-page workspace limit.
  Evidence: message `20260913210334520`.
- Preserve frozen 20-question holdout and its acceptance thresholds:
  14/16 correct source pages, 12/16 sufficiently localized,
  6/8 visual localizations, 3/4 correct abstentions.
  Evidence: `docs/product/PRODUCT_BRIEF.md` section 15B;
  messages `20260913210255043` and `20260913210334520`.
- Report software results and live localization quality separately,
  including failures or incomplete evaluation.
  Evidence: message `20260913210334520`.
- No paid fallback, silent model switch, push, deployment, or optional
  integrations.
  Evidence: messages `20260913210334520` and `20260913212654926`.
- Maximize use of OpenCode/Muse (free) for implementation.
  Evidence: messages `20260913212638717` and `20260913212654926`.
- Build instruction supersedes earlier safe pause.
  Evidence: messages `20260913210255043` and `20260913210334520`
  supersede `20260913204753184`.
- The application shows source pixels and metadata with no AI-written
  answer paragraph (PRODUCT_BRIEF.md section 1, A10).
  Evidence: `docs/product/PRODUCT_BRIEF.md` sections 1, 9, 12.

## Dependencies and constraints
- Product spec: docs/product/PRODUCT_BRIEF.md (controls scope and acceptance).
- Python 3.12 compatibility target for app env (separate from orchestration).
- Must use `backend/.venv`; preserve root `.venv` for orchestration.
- Fixture generation requires ReportLab + Pillow.
- Ports: backend 8000, frontend 5173, dashboard 8765.
- No paid services, deployment, pushes, or Git commands from worker.

## What this round does NOT include
- Live model inference (next round).
- Live evaluation with real test PDFs (requires model integration).
- State/error behavior beyond basic document storage (A6-A9).
- APP_README.md finalization.
