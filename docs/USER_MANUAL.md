# User manual: from an app idea to a supervised build

## What you are getting

This repository is the reusable orchestration system. It supplies the planning,
worker, independent reviews, durable context, dashboard and Git checkpoints.
It does not contain your future app, model subscriptions or account credentials.
The shipped task creates a tiny JSON demonstration artifact only.

To build an app, give an agent access to this repository and your specification.
That setup agent follows ADOPT_AGENT.md, configures a separate product checkout,
then starts the existing supervisor. Once running, the supervisor owns routing.
You talk to the Director through the dashboard or pause through PowerShell.

The normal team is:
- Director: decides strategy, resolves technical impasses, accepts completion.
- Foreman 1: turns strategy into bounded tasks and reviews worker results.
- Foreman 2: independently checks plans, shared-memory updates and results.
- Worker: implements exactly one approved task at a time.

Each role starts fresh and reconstructs context from files. They do not all edit
simultaneously. The saved review chain is the main reason to use this framework.

## Before your first project

You need a Windows machine with Git, Python, Windows PowerShell, and authenticated
Codex, Claude Code and OpenCode CLIs. The configured model IDs must be available
to your accounts. The setup agent checks this rather than assuming access.
Technical details and the exact command contracts are in [SETUP.md](SETUP.md).

Decide these things before an unattended build:
1. Who uses the app, and what problem does it solve?
2. What is the one essential journey through the app?
3. Which screens and data must exist?
4. What is explicitly excluded from the MVP?
5. What may the agent install, access, spend, publish or push?
6. What observed behavior will count as finished?

For example, "build a CRM" leaves important choices unresolved. "A localhost
CRM where I can create contacts, assign stages, search them, and retain changes
after restart; no login, email or external integrations" supplies a testable scope.

## Copy and paste this into your setup agent

Replace the bracketed text. This is a request to the setup agent, not a string
passed directly to run_team.ps1. That script consumes files and manifests.

```text
Use https://github.com/AVaidya-1/agent-orchestration-system as the orchestration source.
Read README.md, docs/USER_MANUAL.md, docs/ADOPT_AGENT.md, docs/SETUP.md and
docs/ARCHITECTURE.md before configuring this project.

Build this app:
- Name: [name]
- Target user and problem: [description]
- Essential user journey: [start -> action -> observable result]
- Required screens: [list]
- Data to persist: [entities/fields]
- Required stack: [specific choice, or choose a simple stack]
- Visual direction: [description]
- Inputs and assets available: [paths or none]
- Explicit exclusions: [payments, auth, email, integrations, etc.]

Acceptance criteria:
1. [Concrete action and expected result]
2. [Concrete action and expected result]
3. Data survives restarting the application.
4. The application starts with the documented commands on localhost.
5. Validate the main journey in a browser; record commands and results.

Project location: [new absolute checkout path]
GitHub repository: [exact URL, or create a private repository named ...]
Autonomous work branch: codex/app-build
Permissions: [allowed dependency installs, network services and data access]
Spending: [no new paid services, or explicit budget]
Publishing: localhost only; no external deployment.
GitHub: [local commits only, or standing push approval for this exact repository]
Model substitutions: [not allowed, or exact permitted alternatives]

Follow docs/ADOPT_AGENT.md. Convert this request into the product brief, owner
policy, planner charter, initial context and bounded manifest. Preserve the
four-role review chain and evidence gates. Make routine implementation choices
within this scope. Do not expand the product to avoid finishing it.

Run the offline tests and dry run; establish model access before unattended
operation. Save a clean baseline, use a codex/ branch, then start PlanFirst
through team_control.ps1 resume. Do not launch a second writer or a separate
agent hierarchy outside the supervisor. If setup cannot complete, report the
exact missing prerequisite and do not claim that work has started.

At completion, deliver the working code, APP_README.md with setup/start/test
commands and localhost URL, actual verification evidence, and known limitations.
The Director must independently accept completion. Do not declare success only
because compilation passes or the worker says it is done.
```

Leave optional choices to the agent explicitly. If an external account, secret,
physical input or essential product decision is missing, the team may still need
you. Never place passwords or tokens in this prompt, briefs or messages.

## Example request for a small localhost app

```text
Build DeskNotes, a personal customer-call notebook running on localhost.
I can add a customer (name and company), record dated notes, edit/delete notes,
and search by customer name or note text. Use a simple stack you can verify on
this machine. Persist data locally. Provide a clean two-column interface and
empty/error states. Seed three fictional customers for the demo.

No login, cloud sync, AI API, email, payments or external deployment. Install
ordinary open-source dependencies through the standard package registry.
No paid services. Use local Git checkpoints; do not enable automatic pushes.

Acceptance: create a customer and note, find it by search, edit it, restart the
app and verify persistence, delete it and verify removal. Validate this in a
browser. Include documented start/test commands and known limitations.
```

Append the setup instructions from the full prompt above. The setup agent must
turn acceptance into actual validation tasks and evidence; it must not prefill
reports with passing values.

## Your daily controls

**Use the GUI for ordinary operation.** Double-click `Start Agent App.cmd` in
the product checkout. The launcher creates `.venv` if necessary (Python must
already be installed) and opens a dedicated app window through Edge or Chrome.
It reuses the matching local server if already running. Without either browser,
it opens a normal browser tab. There is no separate Electron installation.

- **Director:** your only conversation channel. Use the full message box to ask
  questions or give direction; quick actions insert drafts for you to send.
- **Dashboard:** task results, role activity, provider waits, handoffs and memory.
- **Guide:** the short operating manual, available inside the app.
- **Pause team:** deterministic pause control, independent of model availability.
  Wait for `Safe pause confirmed`. A failure never claims shutdown safety.
- **Resume work:** inserts a direction to the Director; send it to continue the
  authorized product goal through the normal control/review path.

The launcher opens the control app, not the app your agents are building. Configure
the product once using the setup-agent prompt. It cannot configure missing model
accounts or turn the demonstration goal into a SaaS merely by opening the window.

Closing the app window leaves the local service and team running. Pause before
shutdown. The local server itself can remain idle until Windows shuts down.
For another product on the same machine, use a different configured launch port
through `scripts/start_team_app.ps1 -Port 8766` or have the setup agent create a
product-specific launcher/shortcut. Do not point two products at one port.

The commands below are advanced/manual alternatives; they are not required for
everyday GUI use.

Open PowerShell in the PRODUCT checkout (not the framework source checkout).

| Need | Command |
|---|---|
| Start or resume | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/team_control.ps1 -Action resume` |
| See status | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/team_control.ps1 -Action status` |
| Pause safely | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/team_control.ps1 -Action pause` |
| Open dashboard | `scripts/open_team_dashboard.cmd` |
| Watch text status | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/overnight_status.ps1 -Watch` |

The dashboard normally opens at http://127.0.0.1:8765. This is the team's control
dashboard, not the product app's URL. The product should use a different port.
Its owner channel distinguishes questions from directions. A question gets an
answer. A direction may queue work, request replanning or pause and can start the
supervisor once it is idle. Messages persist when you close the page.

The dashboard Director can answer while a worker is busy, using a read-only
model session. Messages do not appear in an already-running worker conversation;
the supervisor applies context at later boundaries. Do not manually edit the
same checkout while a worker is writing.

## Going to bed, shutting down and returning

Continuous resume has no total time cap. Keep the computer powered, awake and
connected while it works. Laptop sleep suspends computation. Closing the dashboard
does not stop the supervisor. A restart/power loss does not automatically relaunch it.

To shut down, run pause and wait for `SAFE TO SHUT DOWN`. Pause lets the active
bounded operation finish and checkpoints unfinished work as unapproved. A timeout,
error, or closed terminal is not equivalent to that confirmation. The default
pause wait is four hours and can be changed with `-WaitMinutes`.

`MaxRounds` is a strategy review boundary, not a total-round budget. `MaxHours`
does not cover all waits and recovery paths. Do not promise yourself a precise
overnight duration based on those parameters. Individual worker calls do have
timeouts, and ordinary task revisions are bounded.

On return, inspect the dashboard, read APP_README.md and try the app yourself.
Look at the completion evidence, not only the newest commit. `COMPLETE` can mean
a task round finished; Director `DONE` is the final product acceptance decision.

## If work pauses or appears stuck

| State or symptom | Meaning and response |
|---|---|
| QUOTA-WAIT | Provider allowance is exhausted; the system retains work and waits. Check provider access/reset information. |
| STOPPED | Authorized pause. Use resume when ready. |
| FOREMAN1-HOLD | Temporary integrity/safety hold while Director provider is limited; routed for Director review. |
| BLOCKED | Director recorded an indispensable owner decision. Read OWNER_QUESTIONS.md and supply the missing information. |
| DONE | Director accepted the goal. Verify the app and handoff. A new goal needs deliberate setup. |
| SUPERVISOR-ERROR / REPAIRING | Coordinator fault; launcher can attempt reviewed infrastructure repair. |
| DIRECTOR-RECOVERY-WAIT | Repair batches keep retrying. Inspect logs or pause; this can continue indefinitely. |
| Git safety error | Unsaved, pre-staged, deleted, unsupported or sensitive files need inspection. Never reset/clean to silence it. |
| CLEANUP-ERROR | Process termination was not confirmed. Inspect the recorded process before starting another writer. |

Terminal records are not removed by ordinary resume. Do not delete hard-stop.json
to hide a blocker. Preserve evidence, resolve the decision and explicitly prepare
the next goal/runtime. For a wholly new app, use another checkout.

## What is saved where

Product code and documents are committed to Git. Automatic pushes require
separate standing approval for the exact product remote; none is shipped here.
`out/orchestration/runtime/` stores strategy, messages, reviewed memory, task
status, prompts, logs and control records. `out/orchestration/` also holds gate
artifacts. All of `out/` is ignored by Git. Back it up separately when needed.

Phone notifications are optional ntfy POSTs configured with `phone-setup` and
tested with `phone-test`. Keep the generated topic private. Logs and review
evidence may contain proprietary product context; treat them accordingly.
