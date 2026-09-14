# Round 009 context: Import and viewer vertical slice

## Goal
Deliver the first vertical slice of Visual Evidence: upload PDF/image,
select pages, render canonical rasters, persist documents and pages in SQLite,
and display them in a zoomable React viewer with a deterministic test overlay.

This round revises round-008 to address F2's eighth REVISE verdict
(message `20260914071314454_fabdd73086944590923b23bbf6d5fe0b`).

## Changes from round-008
1. **Command recording**: command-results.json now has exactly 8 entries
   (uv_sync, npm_ci, playwright_install, fixture_gen, pytest, vite_build,
   playwright_test, validator). The validator appends its own exit code.
   The verification receipt (Step 10) runs AFTER report.json and is NOT
   recorded in command-results.json. Its success is gated by the receipt
   file's own content, not by report.json.
2. **No circular artifact inventory**: report.json's artifacts array
   excludes verification-receipt.json (created after the report). The
   report's `checks.final_artifacts_verified` checks only pre-receipt
   artifacts. Screenshots and fixtures/generated files are enumerated
   by exact name (no glob patterns in the artifact list).
3. **Restart test process ownership**: Playwright config defines two
   projects: "main" (uses `webServer`) and "restart" (no `webServer`,
   depends on "main"). The restart project manages its own server
   subprocess with exact PID tracking. Kill by PID, never by port scan.
4. **Raw-evidence schema for validator**: e2e-evidence.json expanded to
   include `import_evidence` array with fixture paths, stored-original
   paths, document IDs, per-page metadata (physical page numbers,
   canonical raster paths, expected signature RGBs). The validator reads
   this to independently compute SHA-256 pairs and verify page identity
   without querying the database.
5. **State inventory description corrected**: The inventory at
   `out/orchestration/state-inventory-20260914.json` was captured before
   round-008 planning and covers untracked files through round-007 only.
   Rounds 008 and 009 plan files are expected additional untracked items.
6. **Fixture and screenshot enumeration**: All fixtures/generated files
   have deterministic names enumerated in the task doc. All screenshot
   filenames are specified by the Playwright tests and enumerated.

## Prior evidence
Key facts cite `out/orchestration/state-inventory-20260914.json` as the
consolidated primary evidence source. That file was captured before
round-008 planning; its git.untracked field lists rounds 001-007 only.
Rounds 008 and 009 plan files are expected additional untracked items
not covered by the snapshot.

- **Git baseline**: Commit `20a8ed4` on branch `codex/app-build`. No tracked
  diff. Untracked at inventory time: `docs/tasks/round-001/` through
  `round-007/` (plan files). Current untracked also includes round-008/
  and round-009/. Origin: `C:/Users/vaidy/Documents/Pinpoint/visual-evidence-remote.git`.
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
  shim = intermittent. Not used by app. Node v24.14.1.
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

## Director guidance
From `out/orchestration/runtime/director_plan.md`:
- Use captured command results and independently recomputed artifact hashes.
- Remove claims that a boolean proves execution order. Permit a post-report
  verification receipt.
- Separate finite evidence-file inventories from dependency/runtime directories.
- Give one test harness ownership of server startup, restart and teardown.
- Complete React/Vite dependencies and preserve current-state observations
  in a credential-free primary artifact.
- Dispatch OpenCode/Muse Worker after F2 approval.

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
