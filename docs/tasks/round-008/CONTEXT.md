# Round 008 context: Import and viewer vertical slice

## Goal
Deliver the first vertical slice of Visual Evidence: upload PDF/image,
select pages, render canonical rasters, persist documents and pages in SQLite,
and display them in a zoomable React viewer with a deterministic test overlay.

This round revises round-007 to address F2's seventh REVISE verdict
(message `20260914065423890_e4f53b4f21454a12ba34fcf842076be1`)
and the Director's CONTINUE briefing in `director_plan.md`.

## Changes from round-007
1. **Finalization and hash equality**: The report finalizer (Step 9) now
   reads `validation.json` as raw bytes, computes SHA-256, and stores
   the digest as `validation_hash` in `report.json`. The manifest gates
   `validation_hash_present` (true only for 64-char hex). Additionally,
   a post-report verification receipt `app_tools/validate_slice.py --verify-report`
   independently re-reads `validation.json`, recomputes its SHA-256, reads
   `report.json`, compares the hashes, verifies captured command results
   against report claims, and writes
   `out/orchestration/import-viewer/verification-receipt.json`. The manifest
   gates `verification-receipt.json /hash_match` and `/all_verified`. This
   breaks circularity: the receipt is produced by an independent re-execution,
   not the same code path that wrote report.json.
2. **Finite evidence inventory**: The artifact list in report.json and
   validator enumerate only finite named evidence files (report.json,
   validation.json, dom-bounds.json, e2e-evidence.json, screenshots,
   fixtures/generated/* by name). Directory-existence checks for `.venv`,
   `node_modules`, and `data` are separate boolean fields, not part of the
   artifact inventory.
3. **Restart process ownership**: The Playwright e2e test owns restart
   testing. It does NOT use Playwright's `webServer` config for the restart
   test. Instead, the restart test spawns its own server subprocess using
   `app_tools/dev.py`, performs the persistence check, then kills it. The
   main `webServer` config handles all other tests. This avoids the conflict
   of trying to restart a server controlled by Playwright's own lifecycle.
4. **Complete frontend dependencies**: `frontend/package.json` explicitly
   requires `react`, `react-dom`, `@vitejs/plugin-react`,
   `@types/react`, `@types/react-dom`, and `typescript` alongside the
   existing dependencies.
5. **Durable state inventory**: `out/orchestration/state-inventory-20260914.json`
   is a credential-free primary artifact documenting Git state, host tools,
   key presence, fixture inventory, application absence, dispatch state,
   preflight/smoke/pilot evidence with exact file paths. All CONTEXT.md
   facts cite this file or the specific primary evidence paths within it.

## Prior evidence
All verified facts cite `out/orchestration/state-inventory-20260914.json`
as the consolidated primary evidence source. Key facts:
- **Git baseline**: Commit `20a8ed4` on branch `codex/app-build`. No tracked
  diff. Untracked: `docs/tasks/round-001/` through `round-008/` (plan files).
  Origin: `C:/Users/vaidy/Documents/Pinpoint/visual-evidence-remote.git`.
  Evidence: `out/orchestration/state-inventory-20260914.json` fields
  `git.head_commit`, `git.tracked_diff`, `git.untracked`, `git.origin`.
- **No application runtime code**: `backend/app/` does not exist.
  `out/orchestration/import-viewer/` does not exist.
  Evidence: `out/orchestration/state-inventory-20260914.json` field
  `application_state`.
- **No Worker dispatch**: No worker dispatch for IMPORT_VIEWER_SLICE found.
  Evidence: `out/orchestration/state-inventory-20260914.json` field
  `worker_dispatch`.
- **Setup preflight**: Gemma locate + full-page-plus-crop passed.
  Evidence: `out/setup/gemma-20260913T192947078057Z/report.json` (cited in
  `out/orchestration/state-inventory-20260914.json` field `preflight`).
  Preflight proves only the Gemini key; OpenRouter and NVIDIA key
  functionality is unverified by any preflight.
- **Role smoke tests**: All four roles exit 0.
  Evidence: `out/setup/smoke-results.json` (cited in state inventory).
  Note: verifies CLI availability, not host tool versions.
- **Pilot**: PILOT-PASS with F2 acceptance and Director acceptance.
  Evidence: `out/orchestration_pilot/a972fef9b8604a88a62a1fa4527b75e8/runtime.json`,
  `out/orchestration_pilot/a972fef9b8604a88a62a1fa4527b75e8/f2_review.md`,
  `out/orchestration_pilot/a972fef9b8604a88a62a1fa4527b75e8/logs/pilot_director_dd08c8179c10449aa68c0350ca63f6dc.md`.
- **Host tools**: `C:/Python314/python.exe` = 3.14.3. WindowsApps `python`
  shim = intermittent (3.13.14 or access denied). Not used by app.
  Node v24.14.1. uv 0.12.13 at `C:/Users/vaidy/.local/bin/uv.exe`.
  App targets Python 3.12 via uv.
  Evidence: `out/orchestration/state-inventory-20260914.json` field `host_tools`.
- **API keys**: GEMINI_API_KEY, OPENROUTER_KEY, NVIDIA_API_KEY all present
  in `.env` (gitignored). Only Gemini key verified by preflight.
  Evidence: `out/orchestration/state-inventory-20260914.json` field `api_keys`.
- **Fixture documents**: Five real test PDFs in `fixtures/documents/`.
  Evidence: `out/orchestration/state-inventory-20260914.json` field
  `fixture_documents`.
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
- Use all five real PDFs for live evaluation (deferred to model round).
  Evidence: messages `20260913210255043` and `20260913210334520`.
- Check actual physical pages; do not assume readme page references.
- Bounded selections within 20-page workspace limit.
- Preserve frozen 20-question holdout and its acceptance thresholds.
- Report software and live quality separately; include failures.
- No paid fallback, silent model switch, push, deployment, optional integrations.
- Maximize use of OpenCode/Muse (free) for implementation.
  Evidence: messages `20260913212638717` and `20260913212654926`.
- Build instruction supersedes earlier safe pause.
  Evidence: messages `20260913210255043` and `20260913210334520`
  supersede `20260913204753184`.

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
