# Execution policy (current default)

This policy supersedes conflicting dual-approval instructions below. The owner
requires autonomous delivery with minimal management overhead.

- One concise plan, then Worker implementation and focused tests. A structurally
  valid manifest dispatches immediately without F2 approval.
- F1 reviews a task once, within ten minutes, using existing evidence. Repeat a
  check only after relevant code/input changes or a concrete failing observation.
  Do not turn a slice review into a full-product audit. One repair attempt is allowed.
- F2 is reserved for explicitly requested thorough review (`-ThoroughReview`).
  It is not a routine plan or review-of-review gate.
- Memory updates are optional bookkeeping. Planner-authored summaries are labeled
  as such, not independently approved. Invalid memory cannot block valid work.
- The Director owns outcomes and may author task details directly. After a planning
  impasse, the runner dispatches the Director as task author, bypassing the foremen.
- Continue to the next unfinished product slice after a pass. No repeated validation
  of unchanged successful work. Preserve existing work and evidence across restarts.
- Owner scope, credentials, spending constraints and actual product acceptance still
  apply. Only the Director accepts final completion based on product evidence.

The remaining document describes the legacy thorough-review protocol where it conflicts.

# Autonomous team operating protocol

The Director is consulted sparingly. Foremen own the ordinary plan / execute / review loop.
Model IDs below are inherited defaults; orchestration.json controls runtime routing.

| Role | Model | Effort | Responsibility |
|---|---|---|---|
| Director / project manager | gpt-6-astra | low | Initial strategy, resolve technical impasses, independently accept completion |
| Foreman 1 | claude-opus-4-6 | medium | Develop bounded tasks and subtasks, review worker evidence, plan the next round |
| Foreman 2 | gpt-5.6-sol | high | Independently review F1 plans, results, and completion/impasse claims |
| Worker | opencode/muse-spark-1.3-contributor-free | high | Execute one approved task, report evidence and questions |

## Loop

Reuse the saved Director briefing until an actual escalation changes it.
F1 plans; F2 approves or returns concrete corrections; only an approved plan
may reach the worker. Worker output goes through F1 and F2. A rejected task
gets bounded revision; exhausted technical failures return to the foremen
for a new approach. No routine Director call between rounds.

When F1 proposes DONE, F2 first checks the completion evidence. The Director
then independently checks the goal and returns DONE or CONTINUE. Foremen
cannot declare final project completion themselves.

Foreman 1 has a narrow emergency-hold capability, not terminal-stop authority.
When a concrete safety or coordinator-integrity problem is discovered and a
persisted OpenAI quota record shows the Director is unavailable, F1 may record
`FOREMAN1-HOLD` with a reason and evidence using `scripts/foreman1_hold.ps1`.
The current bounded call finishes and checkpoints; the launcher then waits for
the Director and automatically routes the hold for review. F1 cannot create a
Director pause, DONE, or BLOCKED, and cannot use the hold for its own quota or an
ordinary technical failure.

When the foremen cannot determine a sound next step, or cannot resolve a
plan disagreement, call the Director with evidence and attempted approaches.
The Director returns technical direction, not worker-sized tasks. F1 turns
that direction into another plan; F2 still must approve it. Owner-only
scope, spending, and authorization decisions remain BLOCKED.
The owner escalation threshold in `OWNER_BRIEF.md` is controlling: ordinary
technical choices and orchestration recovery never become owner questions.

## Open communication on disk

All paths below are under `out/orchestration/runtime/`.
Every role starts from the bounded context packet and
[CONTEXT_PROTOCOL.md](CONTEXT_PROTOCOL.md). The packet contains owner policy,
approved memory, a paged inbox and current task status. Read linked evidence
when relevant; search history selectively rather than loading entire logs.

- `communications.md`: append-only shared handoff ledger, available to all
  roles. The supervisor records each call, outcome, and exact log paths.
  This is the supervisor's handoff history, not the open-question queue.
  Agents send messages using `scripts/team_message.ps1`; unresolved messages
  live under `memory/messages/` until explicitly resolved through F1 and F2.
- `notes.md`: observations and hypotheses; never silently promote to fact.
- `director_plan.md`: current technical strategy, retained across rounds.
- `director_request.md`: F1's technical impasse, attempted approaches,
  evidence, and the specific guidance needed.
- `COMPLETION_REPORT.md`: completion candidate until F2 and Director accept.
- `OWNER_QUESTIONS.md`: concrete owner-only decisions with recommendations.
- `logs/`: unique prompt, output, error, and review files for every call.
- `runtime.json`: supervisor-owned current role, action, heartbeat, log path,
  and terminal status; the dashboard reads it instead of guessing from processes.
- `memory/current.json`: pointer to the approved immutable summary revision.
- `memory/candidate.json`: F1's proposed update, awaiting F2 review.
- `memory/packets/`: exact bounded context supplied to each fresh session.

Agents communicate findings and concise reasoning, not private chain of
thought. Messages do not authorize scope changes. Disagreements must remain
visible; the worker receives both reviews, including the controlling F2 verdict.

## Running

`powershell -ExecutionPolicy Bypass -File scripts/run_team.ps1 -PlanFirst -MaxRounds 5 -MaxHours 10`

For an overnight run, double-click `scripts/start_autonomous_team.cmd`:
it plans first, has no round-count cap, and uses continuous mode. It stops only
for a Director pause or terminal decision. A Foreman1 emergency hold ends only
the current supervisor session; the launcher remains alive and automatically
waits for Director review. Individual agent calls retain their task-specific timeouts.
This launcher executes real project work; it is separate from the test pilot.

PlanFirst evaluates the saved project evidence before running any inherited
task. It enables the round loop and requires both reviews and a Director.
The existing task-only mode remains available for supervised diagnostics.

Quick view:
`powershell -ExecutionPolicy Bypass -File scripts/overnight_status.ps1 -Watch`

Or double-click `scripts/open_team_dashboard.cmd`. For an isolated pilot, pass
its output folder with `-RuntimeDirectory` to the dashboard script.

The dashboard is local and includes a writable owner-to-Director message console.
Its Director model call uses a read-only sandbox; queued directions can launch work. A Director-authorized STOP.txt requests a
stop after the current agent call; quota waits check Director pause authority
every second. FOREMAN1-HOLD.txt is temporary and valid only with its evidence
record and a persisted Director-provider quota. Timeouts terminate the launched
process tree. No model substitutions or paid fallback are allowed.

Tests exercise the control flow with fake agents; they do not establish that
the configured model IDs are available to the installed CLIs. A live pilot
must establish that separately before calling the system overnight-ready.

The inherited Codex adapter reads final-answer files via `codex exec --output-last-message`.
Verify installed CLI flags and account model availability before live use.
Every call has its own timeout, output/error files and bounded error retry.
Saved task passes are reused only while task documents, gate artifacts and
pipeline Python files retain their recorded fingerprints. Missing gates cannot
be satisfied by searching for similarly named files in an earlier run.
