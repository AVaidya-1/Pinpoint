# Agent manual: adapt this system for a new product

This is a setup runbook. Execute it in order. Do not treat the shipped DEMO goal
as the owner's new product request. Do not run a live supervisor in the framework
source checkout merely because the repository was opened.

## Inputs

Read the owner's request, target checkout, exact Git remote, core journey,
acceptance criteria, exclusions, stack constraints and external permissions.
Resolve genuinely required missing inputs. Choose routine implementation details
within existing authorization. Never copy old runtime state or approvals from
another project. Record assumptions explicitly in the product brief.

Read USER_MANUAL.md, SETUP.md, ARCHITECTURE.md, orchestration/AGENT_PROTOCOL.md,
orchestration/CONTEXT_PROTOCOL.md and any existing product AGENTS.md/CLAUDE.md.
The supplied runtime is Windows PowerShell 5.1 plus three provider CLIs.

## Prepare a concrete product configuration

1. Create/use the authorized product checkout. Copy framework source without
   `.git`, `.venv`, `out`, local credentials or history. Preserve existing source;
   resolve filename collisions deliberately. Keep scripts directly under scripts/.
2. Create `.venv` with Python. Verify Git/PowerShell and CLI availability using
   local help. Authenticate through ordinary vendor flows; never store secrets
   in project documents. Live calls require the owner's authorization.
3. Set `orchestration.json.expected_remote` to the exact product origin. Set all
   four supported model IDs explicitly; provider routing is fixed by role unless
   you deliberately adapt and test transport plus quota handling.
4. Set `fingerprint_roots` to all relevant existing product source, tests,
   configuration, dependency lockfiles and framework code. Do not include outputs,
   environments, `.git` or large dependency trees. Missing roots disable cache reuse.
5. Replace docs/product/PRODUCT_BRIEF.md with the actual product scope and
   machine/browser acceptance criteria. Replace OWNER_BRIEF.md and adapt the
   planner charter to express authorization. Preserve review and stop authority.
   Keep owner policy under 5,000 characters; put detailed requirements in the brief.
6. Replace initial CONTEXT.md, task docs and manifest. Default task names are
   discovered from the initial manifest. Keep task docs under docs/ and gate
   artifacts under out/orchestration/. A CONTEXT.md must accompany each task group.
   Use fresh round directories; do not rewrite earlier evidence or task contracts.
7. Review the checkpoint extension allowlist in scripts/team_git.py against your
   stack BEFORE starting. For TypeScript/TSX/Rust/etc., deliberately add required
   text extensions and tests or choose a supported stack. Keep file-size, secret,
   symlink, deletion, staging and destination safeguards. Merge ignore patterns
   for node_modules, build output, databases and local secrets as appropriate.
8. Add product validation commands and evidence format. A passing report boolean
   cannot replace running real tests. Include app startup, persistence, core
   journey and error-state checks. Browser tooling is not bundled: arrange a
   compatible local browser test tool (e.g. the product's test harness) within
   permission, or report browser verification unavailable. Do not claim it ran.

## Verify and launch

Run scripts/test_all.ps1, then run_team.ps1 -DryRun with the initial manifest.
Read failures and fix setup; never bypass reviewers to make a dry run look good.
Run the four live role smoke checks and isolated pilot when authorized. These
validate provider integration, not the product. Read docs/VALIDATION.md to avoid
confusing the extraction's offline results with live account verification.

Review and commit a baseline, create/use a codex/ branch, and run team_git.py check.
The supervisor must begin with a clean checkout and exact origin. Git identity
must be valid. Optional push approval belongs in the ignored runtime policy only
when the owner has authorized automatic pushes to that exact remote.

Bootstrap memory through refresh_team_memory.ps1 or let PlanFirst propose and
review its first candidate. Never hand-author an approval/current pointer.
Start `team_control.ps1 -Action resume`; it invokes PlanFirst with continuous
mode. If launching it as a background helper, use a hidden window and redirect
stdout/stderr to ignored files. Retain process/log paths. Verify runtime.json
and lock ownership show the supervisor actually started. Opening a dashboard is
not proof of dispatch. Do not keep editing once it owns the checkout.

Provide the owner the dashboard address, product checkout and pause command.
Make `Start Agent App.cmd` the primary owner entrypoint. Verify its Director,
Dashboard and Guide views. The owner talks only to Director; never require them
to route messages between foremen and workers. The Pause team button must remain
usable without a provider response. Routine operation should not require a terminal.
Do not launch extra agents outside this supervisor. Do not change subscriptions,
buy credits, enable fallbacks, deploy, or merge main without authorization.

## Required task design

Each worker assignment must include:
- exact allowed source paths and output paths;
- hard prohibitions and relevant prior evidence;
- one bounded deliverable with ordered steps;
- real acceptance commands with observable expected results;
- regression requirements and an escape hatch;
- "Report, then STOP."

For a localhost MVP, plan through a runnable vertical slice, core journey,
persistence, UI/error states, tests and browser validation, then handoff. Include
APP_README.md, known limitations, sample data and start/stop instructions as actual
deliverables. Keep the framework README distinct from the app's operating manual.

## Review and completion contracts

Use exact response prefixes in ARCHITECTURE.md; the supervisor parses them.
F1 authors candidate memory on EVERY planning outcome, with exact six headings
and primary evidence. F2 approves both plan/outcome and candidate before publication.
Workers do not publish memory or manipulate Git. Reviewers inspect complete diffs,
untracked source, gate artifacts and actual test output.

A task PASS is not project DONE. For completion, F1 writes COMPLETION_REPORT.md,
F2 checks it with the memory candidate, and Director independently checks the
original goal. Report missing checks honestly and do not invent follow-on work.
If continued work is needed, supply a specific bounded next hypothesis and test.

The system has cooperative file-based role authority, not a security sandbox
between agents. Follow all host permission rules. Quota and recovery waits can
outlast task limits. Do not promise a hard wall-clock cap that the code does not
enforce. Preserve runtime evidence and use the supported pause path.

## Final setup handoff checklist

- [ ] Product request translated into controlling files; demo scope replaced.
- [ ] Models/CLIs available or exact unverified dependency reported.
- [ ] Correct remote, codex/ branch and clean baseline.
- [ ] Fingerprint roots, source extension allowlist and ignores fit the stack.
- [ ] Offline tests and dry run passed; live checks reported separately.
- [ ] Supervisor startup verified, or exact blocker recorded without claiming success.
- [ ] Owner has dashboard, status/pause commands and location of evidence.
