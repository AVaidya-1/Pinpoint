# Agent Orchestration

A Windows, file-backed supervisor for a Director, two independent reviewing
foremen, and one implementation worker. Fresh CLI sessions reconstruct context
from durable messages and reviewed memory. The supervisor serializes work,
checks artifacts, routes reviews and manages Git checkpoints.

## Open the app

```powershell
git clone https://github.com/AVaidya-1/agent-orchestration-system.git
cd agent-orchestration-system
& ".\Start Agent App.cmd"
```

Double-click **Start Agent App.cmd** in your product checkout. It creates the
local Python environment if needed and opens a dedicated Edge/Chrome app window.
You get **Director chat**, a **Dashboard** view, an in-app **Guide**, and **Pause
team**. You only converse with the Director; the other roles work behind the scenes.
If Edge/Chrome is unavailable, it falls back to your default browser.

After one-time product/provider setup, no terminal is needed for ordinary chat,
status, resume directions or safe pause. Initial app requirements must still be
configured through the setup-agent runbook below; the launcher does not install
model CLIs, authenticate accounts or invent a product goal.

**For the owner:** [user manual and copy/paste app-build request](docs/USER_MANUAL.md).
**For a setup agent:** [agent adoption runbook](docs/ADOPT_AGENT.md).
**For technical setup:** [configuration, prerequisites and commands](docs/SETUP.md).
For implementation details, read [architecture and runtime contracts](docs/ARCHITECTURE.md).
An agent can follow [the adoption checklist](docs/ADOPT_AGENT.md) to adapt this
repository to another product.

```powershell
python -m venv .venv
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test_all.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_team.ps1 -DryRun
```

Tests are offline. The dry run checks local CLI presence and task configuration;
it does not establish model availability. Live operation requires authenticated
Codex, Claude Code and OpenCode CLIs with compatible flags and configured models.

The shipped goal is a small JSON artifact demonstration. Replace the product
brief, policy, initial tasks, remote and fingerprint roots before building a
different product. Runtime data lives under ignored `out/`; it is not a Git backup.

Extracted from an existing product implementation; see [provenance](docs/PROVENANCE.md)
and [validation status](docs/VALIDATION.md). This is a Windows reference
implementation with cooperative role controls, not an isolated multi-tenant agent service.

## Build an app with this repository

Give your coding agent this repository plus a concrete app specification. The
setup agent prepares a separate product checkout, replaces the demonstration
goal with your requirements, verifies prerequisites, and launches the supervisor.
The supervisor then coordinates the four roles until reviewed completion,
an authorized pause, or an indispensable owner decision.

You do not need to hand-write every worker task. Your input is the product goal,
required behavior, constraints and acceptance criteria. F1 creates bounded tasks;
F2 checks them before a worker starts. The [full prompt](docs/USER_MANUAL.md#copy-and-paste-this-into-your-setup-agent)
includes everything the receiving agent needs to configure the system.

### Short starter prompt

```text
Read this repository's README.md, docs/USER_MANUAL.md, docs/ADOPT_AGENT.md,
docs/SETUP.md and docs/ARCHITECTURE.md. Follow the adoption runbook to configure
a separate product checkout and start the four-role orchestration system.

App: [what it does and who uses it]
Core journey: [actions the user must be able to complete]
Screens and persistent data: [requirements]
Stack: [required stack, or choose a simple stack]
MVP exclusions: [what not to build]
Acceptance: [specific observable checks, including localhost browser behavior]
Product checkout and GitHub destination: [paths and exact repository URL]
Permissions and budget: [installs, external access, spending, GitHub pushes]

Use localhost only unless I explicitly authorize deployment. Make routine
implementation decisions within this scope. Preserve independent reviews,
evidence gates and the owner's acceptance criteria. Do not silently switch models.
Save a clean baseline, verify setup, and start the supervisor; report an exact
blocker if setup cannot finish. Do not claim work started without checking runtime.
Deliver APP_README.md, start/test commands, verification evidence and limitations.
Only the Director can accept final completion after both foremen review it.
```

The shipped example is intentionally a JSON artifact task, not a SaaS template.
Use the manual's expanded prompt for your actual app. Browser test tooling and
the application stack are configured per product; they are not supplied here.

## What happens after launch

1. **Director strategy:** reads the goal and acceptance contract, writes direction.
2. **F1 planning:** authors a small manifest, task documents and candidate memory.
3. **F2 plan review:** checks scope, evidence, tasks and memory; rejects unsupported claims.
4. **Worker execution:** carries out one approved task with a bounded timeout.
5. **Machine gates:** check exact artifact paths and configured JSON values.
6. **Two result reviews:** F1 examines evidence; F2 independently verifies the verdict.
7. **Checkpoint and next round:** accepted work is saved; failures get bounded revision
   or a new technical approach. Important questions survive fresh sessions.
8. **Completion:** F1 proposes it, F2 checks it, Director independently accepts DONE.

The normal worker and reviewers run serially in one checkout. The dashboard's
read-only Director conversation can run while a worker is busy. No role may
launch its own hidden agent hierarchy. The supervisor owns commits and pushes.

## Configure once for each product

| File | What to set |
|---|---|
| orchestration.json | Exact product remote, model IDs and fingerprint roots |
| docs/product/PRODUCT_BRIEF.md | Users, scope, stack, deliverables, acceptance and exclusions |
| docs/orchestration/OWNER_BRIEF.md | Owner policy and authorization, under 5,000 characters |
| docs/orchestration/PLANNER_CHARTER.md | Planning rules and product constraints |
| docs/tasks/initial/CONTEXT.md | Available facts, inputs, unknowns and initial context |
| docs/tasks/initial/manifest.json | Initial bounded task definitions and evidence gates |
| docs/tasks/initial/TASK_*.md | Allowed writes, exact outputs, tests, escape hatch and STOP |
| scripts/team_git.py | Check its conservative source-extension allowlist against the stack |
| .gitignore | Ignore dependencies, generated files, local data and credentials |

Never carry another product's runtime, memory, notification topic, acceptance
report or push approval into a new product. Save the new baseline on a `codex/`
branch and verify the remote before allowing autonomous writes.

## Owner commands

Run these from the product checkout after setup:

```powershell
# Open the local control dashboard (normally port 8765).
scripts/open_team_dashboard.cmd

# Start or continue the supervised planning/build loop.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/team_control.ps1 -Action resume

# Inspect current work.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/team_control.ps1 -Action status

# Finish the current bounded operation and stop safely.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/team_control.ps1 -Action pause
```

The dashboard is a control UI, distinct from the app being built. Ask the Director
questions or send directions there. Directions can queue/replan work and launch
the supervisor when idle. Closing the page does not stop the build. Wait for
`SAFE TO SHUT DOWN` before turning off the machine. Resume does not clear a
Director DONE/BLOCKED record.

## Dependencies and important limits

- Windows PowerShell 5.1, Python 3.9+, Git, and compatible authenticated Codex,
  Claude Code and OpenCode CLIs. No Python package dependencies are required.
- Models in orchestration.json are inherited defaults, not a promise of account
  availability. Run the supplied live smoke checks and pilot before unattended use.
- The launcher is continuous. MaxRounds is a strategy-review boundary; MaxHours
  does not cover every quota/recovery wait. There is no guaranteed overnight deadline.
- Role authority is cooperative and file-based. The framework is not a security
  boundary between malicious agents, and the dashboard must stay on loopback.
- Gate JSON checks do not execute tests. Workers must run product checks and
  reviewers must inspect actual evidence. App usability requires browser validation.
- Git checkpoints are conservative: deletion, pre-staging, unsupported extensions,
  symlinks, large files and recognized secrets stop automated checkpointing.
- Source backups exclude ignored runtime state. Back up out/orchestration separately
  if you need conversations, memory and artifacts after moving machines.

## Documentation index

| Reader/task | Document |
|---|---|
| Give the agent an exact app request; operate the team | [USER_MANUAL.md](docs/USER_MANUAL.md) |
| Configure another product as an agent | [ADOPT_AGENT.md](docs/ADOPT_AGENT.md) |
| Environment, configuration, manifests and CLI procedures | [SETUP.md](docs/SETUP.md) |
| Implementation, state machine and response formats | [ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Role rules and authority | [AGENT_PROTOCOL.md](docs/orchestration/AGENT_PROTOCOL.md) |
| Messages, memory schemas and context budgets | [CONTEXT_PROTOCOL.md](docs/orchestration/CONTEXT_PROTOCOL.md) |
| Provider cooldowns and retries | [USAGE_LIMITS.md](docs/orchestration/USAGE_LIMITS.md) |
| What has actually been tested | [VALIDATION.md](docs/VALIDATION.md) |
| Origin and changes made during extraction | [PROVENANCE.md](docs/PROVENANCE.md) |
