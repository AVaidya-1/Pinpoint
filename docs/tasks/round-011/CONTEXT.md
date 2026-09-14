# Round 011 context: Import and viewer vertical slice

## Goal
Deliver the first vertical slice of Visual Evidence: upload PDF/image,
select pages, render canonical rasters, persist documents and pages in SQLite,
and display them in a zoomable React viewer with a deterministic test overlay.

This round revises round-009 to address F2's ninth REVISE verdict
(message `20260914073100017_c62a76a29e3246669d23313783f2453d`)
and the Director's focused-revision briefing in
`out/orchestration/runtime/director_plan.md`
(recorded at `out/orchestration/runtime/logs/director_STUCK_2f76d44ae3e1481bacf1cd492f6b68a1.md`).
It supersedes the round-010 draft approach (`docs/tasks/round-010/CONTEXT.md`
only; no task doc or manifest was ever written for round-010).

## Changes from round-009
1. **One external harness owns all server lifecycle; no Playwright
   `webServer`**: New tracked file `app_tools/e2e_harness.py` is the sole
   owner of test-server startup, restart and teardown. `playwright.config.ts`
   MUST NOT contain a `webServer` key (the validator text-searches the config
   and fails if `webServer` is present, since Playwright exposes it only on
   top-level `TestConfig`). `e2e.spec.ts` performs no spawn/kill and assumes
   the harness-started server. `restart.spec.ts` is removed from the contract;
   the harness performs the restart check itself (docs_before, kill by PID
   with confirmed child exit, fresh start, docs_after) and writes
   `restart-evidence.json`. Shutdown targets the dev.py launcher PID, polls
   the two printed child PIDs to confirmed exit (taskkill fallback), and
   preserves the Playwright exit code separately.
2. **Exact ordered eight-command record, machine-gated**: The validator owns
   `EXPECTED_COMMANDS` (the eight names in order) and gates
   `command_count_valid` (exactly 8 entries) and `command_order_valid`
   (names match in order). Missing, duplicated or reordered entries fail
   validation. The receipt re-checks count/order and gates its own
   `command_count_valid` / `command_order_valid`.
3. **Exact pre-receipt artifact inventory, machine-gated**: The validator owns
   the expected set (union of the three Exact-outputs sections minus
   `verification-receipt.json`: 36 tracked + 6 evidence + 13 screenshots +
   7 fixtures = 62 files) and gates `artifacts_set_valid` (set equality) and
   `artifacts_set_count` (= 62). The receipt re-checks set equality against
   the same expected set. An incomplete `artifacts` list in `report.json`
   can no longer pass.
4. **All 13 screenshots required**: The validator requires every named
   screenshot; `screenshot_count` must equal 13. No optional screenshots
   remain in the contract.
5. **Hash claim corrected**: Hash equality between recomputed
   `validation.json` SHA-256 and `report.json["validation_hash"]` proves the
   report references the current validation bytes (integrity). No claim is
   made that any boolean proves execution order.

## Prior evidence
Historical facts cite `out/orchestration/state-inventory-20260914.json`
(preserved unchanged; covers rounds through 007). Current checkout facts cite
the durable F1 capture
`out/orchestration/runtime/logs/context_review_round011_f1.json`, verified
2026-09-14 by direct inspection (`git status`, `git log`, `git remote -v`,
`Test-Path`, fixture listing).

- **Git**: Branch `codex/app-build`, HEAD `91a61df`, 2 commits ahead of
  `origin/codex/app-build`. Baseline `20a8ed4` is HEAD~2. Working tree clean
  (previously untracked round plan files were checkpointed in `d7910e5`).
  Origin: `C:/Users/vaidy/Documents/Pinpoint/visual-evidence-remote.git`
  (local). Evidence: `context_review_round011_f1.json` field `git`.
- **No application runtime code**: `backend/app/` absent.
  `out/orchestration/import-viewer/` absent. `app_tools/preflight.py` is a
  setup utility. Evidence: `context_review_round011_f1.json` field
  `application_state`.
- **No Worker dispatch**: no product-task execution evidence was found for
  IMPORT_VIEWER_SLICE. Evidence: `context_review_round011_f1.json` field
  `worker_dispatch`.
- **Setup preflight**: Gemma locate + full-page-plus-crop PASS, model
  `gemma-4-31b-it`. Proves only the Gemini key; OpenRouter and NVIDIA keys
  unverified. Evidence: `out/setup/gemma-20260913T192947078057Z/report.json`.
- **Role smoke tests**: all four roles exit 0 (CLI availability, not tool
  versions). Evidence: `out/setup/smoke-results.json`.
- **Pilot**: PILOT-PASS with F2 acceptance and Director acceptance.
  Evidence: `out/orchestration_pilot/a972fef9b8604a88a62a1fa4527b75e8/runtime.json`,
  `out/orchestration_pilot/a972fef9b8604a88a62a1fa4527b75e8/f2_review.md`,
  `out/orchestration_pilot/a972fef9b8604a88a62a1fa4527b75e8/logs/pilot_director_dd08c8179c10449aa68c0350ca63f6dc.md`.
- **Host tools**: `C:/Python314/python.exe` = 3.14.3 (orchestration only).
  Node v24.14.1. uv 0.12.13 at `C:/Users/vaidy/.local/bin/uv.exe` (absolute
  path; not on default PATH). App targets Python 3.12 via uv.
  Evidence: `context_review_round011_f1.json` field `host_tools`.
- **API keys**: GEMINI_API_KEY, OPENROUTER_KEY, NVIDIA_API_KEY present in
  `.env` (gitignored, names only). Evidence: `context_review_round011_f1.json`
  field `api_keys`.
- **Fixture documents**: five real test PDFs in `fixtures/documents/`.
  Evidence: `context_review_round011_f1.json` field `fixture_documents`.
- **Planning rounds 001-010**: ten planning iterations refining this slice;
  rounds 001-009 each hold CONTEXT + task + manifest, round-010 holds
  CONTEXT only. Evidence: `docs/tasks/round-001/` through
  `docs/tasks/round-010/`; F2 verdicts at
  `out/orchestration/runtime/memory/messages/20260914071314454_fabdd73086944590923b23bbf6d5fe0b.md`
  and `.../20260914073100017_c62a76a29e3246669d23313783f2453d.md`.
- **Archived TEST-round escalation**:
  `out/orchestration/runtime/logs/f22548ac8d444131936b3bba4642d108_director_request.md`
  with Director dissent at
  `out/orchestration/runtime/logs/director_INITIAL_3d4fb232b72749678fb8dc0322668863.md`.
  Preserved as unverified history.

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
