# Technical setup and product adoption

## 1. Execution environment

Use a Windows checkout with Windows PowerShell 5.1 (`powershell.exe`), Git and
Python 3.9 or newer. The extraction's offline suites were exercised with Python
3.14. The Python helpers use only the standard library; no pip packages are
required. Create `.venv` at the repository root because scripts intentionally
invoke `.venv/Scripts/python.exe`. The `.cmd` launchers, `cmd.exe` pipes, process
cleanup and Windows file locks make this a Windows implementation. PowerShell
7 alone does not make it portable to Linux/macOS.

Install and authenticate Codex CLI, Claude Code CLI and OpenCode through their
normal vendor flows. Check `codex exec --help`, `claude --help`, and
`opencode run --help` locally. This repository contains inherited adapters, not
pinned vendor dependencies. Model identifiers and permission flags may differ
by account and installed CLI version. Never substitute a model silently.

The account running the supervisor needs source/output write access, permission
to launch child processes, Git commit identity, and appropriate model access.
GitHub pushes additionally need authentication. Keep credentials in the vendor
CLIs and Git credential helper, never in task documents or `orchestration.json`.

## 2. Choose the product checkout

For a new product, clone/fork this repository into its own directory and point
`origin` at that product's repository. For an existing product, copy the explicit
framework paths (`scripts/`, `docs/orchestration/`, these technical docs and
`orchestration.json`) after checking filename collisions. Merge `.gitignore`;
do not overwrite existing product instructions blindly. The scripts derive
the root from their own parent, so they must live directly under `<product>/scripts`.

Use one checkout and one runtime per running product. For simultaneous products,
use separate directories, ports and independent output state. Never share one
checkout between autonomous writers or edit it manually while the team runs.

## 3. Configure routing and repository identity

Edit `orchestration.json`:

```json
{
  "expected_remote": "https://github.com/OWNER/PRODUCT.git",
  "fingerprint_roots": ["scripts", "docs", "orchestration.json", "src", "tests"],
  "models": {
    "Director": "gpt-6-astra",
    "Foreman1": "claude-opus-4-6",
    "Foreman2": "gpt-5.6-sol",
    "Worker": "opencode/muse-spark-1.3-contributor-free"
  }
}
```

Replace OWNER/PRODUCT with the exact output of `git remote get-url origin`,
including URL scheme and `.git` suffix. The placeholder is explicitly rejected.
The distributed config points to this framework's repository; change it for
each adopted product. Local checkpoints are allowed without standing push
approval, but even local runs validate the destination to avoid a wrong checkout.

Set fingerprint roots to existing, project-relative source/test/configuration
paths for the actual stack. Include lockfiles and relevant schemas/assets.
Do not include `out`, `.git`, environments or large dependency/generated trees.
Missing roots disable PASS reuse. The recursive scan excludes `.git`, `.venv`,
`node_modules`, `__pycache__` and `.pyc`. This list must cover every input whose
change should invalidate an old task approval. Hashes include absolute paths,
so moving a checkout also invalidates cached passes.

Model configuration selects provider routing from the model ID: models beginning
with `opencode/` use OpenCode; Director/F2 otherwise use Codex, F1 otherwise uses
Claude. Runner
`-DirectorModel`, `-Foreman1Model`, `-Foreman2Model`, `-WorkerModel` overrides apply
to that runner invocation; the dashboard and repair helper use the saved config.
Efforts are fixed by role: low, medium, high, high respectively; Director repair
uses high. `-WorkerCmd` is an advanced trusted shell-command override, not data.

## 4. Write the product contract

Replace `docs/product/PRODUCT_BRIEF.md` with the intended users, concrete goal,
deliverables, exclusions, chosen stack, available inputs, allowed source paths,
validation commands, regression baseline, and measurable acceptance thresholds.
Record spending, publishing and external-service authorization explicitly.
Replace `docs/orchestration/OWNER_BRIEF.md` with the owner's controlling policy
(maximum 5,000 characters). Adapt `PLANNER_CHARTER.md` without weakening the
review/authority model. Resolve conflicts with existing AGENTS.md/CLAUDE.md
before launch. Do not inherit a prior product's approvals or completion criteria.

Replace `docs/tasks/initial/CONTEXT.md`, task document(s), and manifest. Each
task must name its allowed writes, hard prohibitions, bounded procedure,
exact evidence paths, independent acceptance check, failure escape hatch and STOP.
Keep `CONTEXT.md` beside task documents because prompts compute that location.

## 5. Manifest contract

```json
{
  "round": "initial",
  "tasks": [{
    "name": "BUILD_API",
    "doc": "docs/tasks/initial/TASK_BUILD_API.md",
    "timeout_min": 60,
    "continue_on_fail": false,
    "gate_files": ["out/orchestration/build-api/report.json"],
    "json_gates": [{
      "file": "out/orchestration/build-api/report.json",
      "pointer": "/checks/all_pass",
      "expect": true
    }]
  }]
}
```

Use unique nonempty task names, one to eight tasks, timeouts 1-480 minutes,
at least one gate file, task docs under `docs/`, and every gate path under
`out/orchestration/`. Paths are relative to the product root. Two supported
JSON gate forms are mutually exclusive: `pointer` + `expect` (JSON Pointer,
starting `/`, with `~0`/`~1` escapes), or `path` + `escalate_if` (dotted object
path, e.g. `checks.all_pass` with `escalate_if:false`). Explicit boolean false
is meaningful. Include `json_gates:[]` for artifact-only checks.

File gates only test exact file existence. JSON gates compare values; they do
not execute product tests or prove report authenticity. Task instructions must
run real validation, and both reviewers must inspect primary evidence and the
full diff. Reports should capture command, exit status, inputs/revision and
results. Avoid a self-reported boolean as the sole real-product acceptance gate.

The default task table loads `docs/tasks/initial/manifest.json`. With no `-Tasks` argument, all task names are discovered from that manifest. Pass `-Tasks BUILD_API` to select a subset in task-only mode, or pass `-Manifest` explicitly. PlanFirst uses the selected task list to locate the initial CONTEXT.md; it asks the foremen to plan before executing inherited tasks.

## 6. Validate before live work

```powershell
python -m venv .venv
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test_all.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_team.ps1 -DryRun -Manifest docs/tasks/initial/manifest.json
```

The offline test launcher uses fake agents and local subprocesses. It does not
call model providers, create ntfy subscriptions or push GitHub. A successful dry
run does not validate model access, the Git baseline or a product's correctness.
Run each live connectivity test only when model calls are authorized:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/smoke_orchestration_model.ps1 -Role Director
# Repeat for Foreman1, Foreman2 and Worker.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/pilot_orchestration.ps1
```

The live pilot tests plan -> F2 approval -> worker artifact -> F1 -> F2 ->
Director acceptance in a unique ignored folder. It is not the product goal.
Quota recovery can wait beyond an individual call timeout, so supervise the
pilot. Archive pilot evidence locally. Do not mark a product ready solely from it.

## 7. Save baseline and start

Review all source changes, configure Git identity, and save a clean baseline.
Create a `codex/` branch for autonomous work:

```powershell
git switch -c codex/product-work
.venv/Scripts/python.exe scripts/team_git.py check
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/refresh_team_memory.ps1
```

Memory refresh invokes F1 and F2, validates a candidate and publishes its reviewed
revision without executing product tasks. Fresh PlanFirst runs can also bootstrap
memory during planning; never fabricate `memory/current.json` to bypass review.

For the first bounded task without the planning loop:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_team.ps1 -Manifest docs/tasks/initial/manifest.json
```

For continuous operation:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/team_control.ps1 -Action resume
```

This executes real product work and may run indefinitely. `MaxRounds` is a
Director strategy-review boundary, not a total-round stop. `MaxHours` is checked
while a child process runs; it is not a comprehensive wall-clock budget over
quota/recovery waits. `resume` explicitly sets both to zero. Use the pause command
to stop gracefully and keep the machine awake until safety is confirmed.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/team_control.ps1 -Action pause
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/team_control.ps1 -Action status
```

Pause records a deterministic Director control-plane action and needs no live
model. It waits for the current bounded operation, lock/PID/pending-operation
checks and checkpoint. An error or timeout is not confirmation of a safe pause.
Ordinary resume clears an authorized pause, but refuses Director DONE/BLOCKED.
For a new goal, preserve/archive the previous runtime evidence and establish a
new goal/strategy explicitly; no automatic command is provided to erase hard stops.

## 8. Dashboard, notifications and backup

Run `scripts/open_team_dashboard.cmd` or:

```powershell
.venv/Scripts/python.exe scripts/team_dashboard.py --port 8765 --open
```

The dashboard binds loopback only. Its owner console persists messages, invokes
a read-only Director and can start the supervisor after accepted directions.
Closing a browser tab does not stop work. Do not expose the server publicly.
`--runtime-directory <path>` views an isolated runtime; custom-runtime production
resume is intentionally unsupported. Use separate ports for separate products.

Optional `team_control.ps1 -Action phone-setup`, `phone-test`, `phone-off` controls
ntfy. Setup creates a local random topic; keep it private. Notifications are
external POSTs. Routine progress/quota waits stay in the dashboard.

Automatic GitHub backup is opt-in per product. After owner authorization, write
`out/orchestration/runtime/github-backup.json` with
`{"approved":true,"remote":"<exact configured origin>"}`. Reviewed checkpoints
use `--push-if-approved`. This extraction's one-time publication does not grant
standing push approval to future products. There is no auto-merge to main.
Git checks reject pre-staging, deletion, symlinks, unfamiliar file extensions,
files over 2 MB, and recognized secret patterns. Add product extensions to
`team_git.py` only deliberately and with tests (e.g. TS/TSX/Rust are not in the
inherited allowlist). A regex is not a comprehensive secret scanner.

Back up ignored `out/orchestration/` separately if memory, messages and evidence
must survive a move or disk failure. Source-only GitHub backups cannot reconstruct
the exact prior runtime. Do not copy credentials, topics or old push approvals
into a different product.
