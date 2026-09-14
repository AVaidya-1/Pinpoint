# Round 007 context: Import and viewer vertical slice

## Goal
Deliver the first vertical slice of Visual Evidence: upload PDF/image,
select pages, render canonical rasters, persist documents and pages in SQLite,
and display them in a zoomable React viewer with a deterministic test overlay.

This round revises round-006 to address F2's sixth REVISE verdict
(message `20260914023052157_1cb691225f384e379280b4ee91a44dd1`)
and retains the Director's focused-correction briefing in `director_plan.md`.

## Changes from round-006
1. **Gate count corrected**: CONTEXT.md no longer claims a gate count that
   conflicts with the manifest. The manifest contains 30 json_gates (see
   manifest.json). Capacity enforcement has an explicit validator scalar
   `capacity_enforced` and a corresponding manifest gate.
2. **Deterministic finalization contract**: Step 9 (report finalizer) reads
   `validation.json`, computes its SHA-256 hash, and stores it as
   `validation_hash` in `report.json`. The manifest gates
   `checks/validation_hash_present` = true (a derived boolean set true only
   when validation_hash is a nonempty 64-character hex string). This proves
   report.json was written after validation.json. Additionally, the report
   finalizer verifies that every path in its `artifacts` array exists on disk
   before writing, storing `checks/final_artifacts_verified` = true. The
   manifest gates this field. `artifacts_complete` in validation.json checks
   tracked source files; `final_artifacts_verified` in report.json checks
   the full evidence/generated list.
3. **Alignment count contract clarified**: The validator emits three separate
   counts: `alignment_transform_count` (number of alignment results for
   transform views: fit, zoom100, zoom200, pan, resize = 5),
   `alignment_orientation_count` (number of alignment results for
   orientation cases: portrait, landscape, cropbox, exif-jpeg, standard-png
   = 5), and `alignment_total_count` (sum = 10). The manifest gates
   `alignment_total_count` = 10 and `alignment_all_pass` = true. The old
   ambiguous `alignment_view_count` is removed.
4. **Python shim recorded as unreliable**: The WindowsApps `python` shim is
   intermittent (returns 3.13.14 or access denied depending on session
   context). It is not used by the application or orchestration. Only
   `C:/Python314/python.exe` (3.14.3) is authoritative. The app targets
   Python 3.12 via uv.
   Evidence: `python --version` observed returning 3.13.14 in some sessions
   and access denied in others (F2 independently verified access denied).
   `C:/Python314/python.exe --version` consistently returns 3.14.3.
5. **Memory candidate evidence strengthened**: Every verified fact cites a
   durable primary file path. The archived "three failed TEST rounds" signal
   cites `out/orchestration/runtime/logs/f22548ac8d444131936b3bba4642d108_director_request.md`
   (the escalation) and the Director's dissent at
   `out/orchestration/runtime/logs/director_INITIAL_3d4fb232b72749678fb8dc0322668863.md`
   (which instructed establishing its provenance before carrying the failure
   count into planning). Five approved SAFE-PAUSE/status resolutions retained.

## Prior evidence
- **Git baseline**: Commit `20a8ed4` on branch `codex/app-build`. No tracked
  diff. Untracked: `docs/tasks/round-001/` through `round-007/` (plan files).
  Evidence: `git log --oneline -1` verified at round-007 planning time;
  `git status --short` verified at round-007 planning time showing only
  `?? docs/tasks/round-00N/` entries. No unexpected source files.
- **Product origin**: `C:/Users/vaidy/Documents/Pinpoint/visual-evidence-remote.git`.
  Evidence: `orchestration.json` field `expected_remote`.
- **No application runtime code**: `backend/app/` does not exist (Test-Path
  returns False). `app_tools/preflight.py` is a setup utility.
  `out/orchestration/import-viewer/` does not exist (Test-Path returns False).
  Evidence: directory existence checks verified at round-007 planning time.
- **No Worker dispatch**: `out/orchestration/runtime/communications.md`
  contains no worker-dispatch entries for IMPORT_VIEWER_SLICE. The two
  matches are F2 review findings citing task document paths, not dispatch
  records.
  Evidence: `rg IMPORT_VIEWER_SLICE out/orchestration/runtime/communications.md`
  verified at round-007 planning time (2 matches, both in review context).
- **Setup preflight**: Gemma locate + full-page-plus-crop check passed with
  coverage 0.99, area ratio 1.0033, model `gemma-4-31b-it`, key_present=true.
  Evidence: `out/setup/gemma-20260913T192947078057Z/report.json`.
  Note: preflight proves Gemini key works; it does not prove OpenRouter or
  NVIDIA keys.
- **Role smoke tests**: All four roles (Director, Foreman1, Foreman2, Worker)
  recorded exit code 0.
  Evidence: `out/setup/smoke-results.json`.
- **Pilot passed**: Status PILOT-PASS with worker artifact and both reviews.
  Evidence:
  `out/orchestration_pilot/a972fef9b8604a88a62a1fa4527b75e8/runtime.json`
  (status=PILOT-PASS),
  `out/orchestration_pilot/a972fef9b8604a88a62a1fa4527b75e8/f2_review.md`
  (F2 acceptance),
  `out/orchestration_pilot/a972fef9b8604a88a62a1fa4527b75e8/logs/pilot_director_dd08c8179c10449aa68c0350ca63f6dc.md`
  (Director acceptance).
- **Host tools** (verified at round-007 planning time):
  `C:/Python314/python.exe` = Python 3.14.3.
  WindowsApps `python` shim = unreliable (intermittently 3.13.14 or access
  denied). Not used by application or orchestration.
  Node v24.14.1 (`node --version`).
  uv 0.12.13 (`C:/Users/vaidy/.local/bin/uv.exe --version`).
  App targets Python 3.12 via uv.
- **API keys**: Three keys present in `.env` (gitignored):
  `GEMINI_API_KEY` (line 1), `OPENROUTER_KEY` (line 10), `NVIDIA_API_KEY`
  (line 11). Verified by pattern match on key names at round-007 planning
  time. Preflight at `out/setup/gemma-20260913T192947078057Z/report.json`
  confirms Gemini key works; OpenRouter and NVIDIA key functionality is
  unverified by any preflight.
- **Fixture documents**: Five real test PDFs in `fixtures/documents/`
  (gitignored): ccd-0011565.pdf, FAA excerpt, ne555.pdf, prusa3d manual,
  RP-008307 datasheet.
  Evidence: `fixtures/documents/Testing documents readme.md` describes the
  test plan. Directory listing verified at round-007 planning time shows
  exactly five PDF files.
- **Archived TEST-round escalation**: `out/orchestration/runtime/logs/f22548ac8d444131936b3bba4642d108_director_request.md`
  records an escalation citing "three unsuccessful rounds" with task TEST.
  The Director's response at `out/orchestration/runtime/logs/director_INITIAL_3d4fb232b72749678fb8dc0322668863.md`
  instructed establishing its provenance before carrying that failure count
  into product planning. No supporting product-task evidence was found in
  the supplied packet. The record is preserved as unverified history.

## Director guidance
From `out/orchestration/runtime/director_plan.md`:
- Establish acyclic evidence flow: executed tests → raw evidence → independent
  validation → finalized report. Never initialize successful verdicts.
- Validate orientation using canonical raster dimensions; retain measured DOM
  bounds for overlay alignment.
- Explicitly gate nonempty hash comparisons, page identity, holdout split,
  DOM completeness, restart persistence and screenshot presence.
- Correct launcher working-directory assumptions and unsupported memory claims.
- Preserve unresolved messages until F2 approves their dispositions.
- Dispatch OpenCode/Muse Worker immediately after F2 approval.

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
