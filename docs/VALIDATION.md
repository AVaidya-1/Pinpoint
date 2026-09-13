# Validation status

Validated on 2026-09-12, with final GUI regression verification on 2026-09-13,
on Windows using Windows PowerShell 5.1 and Python 3.14.

## Passed

- test_team_context.ps1: candidate validation, frozen evidence review, publication,
  message persistence/resolution and bounded context behavior.
- test_team_notifications.ps1: notification selection and deduplication with mocks.
- test_usage_limits.ps1: 23 checks for classification, shared cooldowns, stop
  handling and continuation after a synthetic provider limit.
- test_director_console.ps1: fake Director transport and durable owner communication.
- test_orchestration.ps1: real local fake-process transport, empty/error/timeout
  handling, role routing, gate validation, saved PASS invalidation and review flow.
- test_team_control.ps1: pause control and presence of the repair path.
- test_hard_stops.ps1: 16 checks for Director terminal authority and F1 holds.
- test_team_git.py: 7 tests, including clean checkpoints, branch/remote rejection,
  secret rejection, deletion/pre-staging refusal and optional local-only backup.
- test_team_dashboard.py: 14 tests for HTTP/dashboard, owner control, pause without
  a live model, failed-pause reporting and cross-origin pause rejection.
- test_team_app.py: 2 launcher tests for matching-service reuse and refusal to
  open a wrong/failed service.
- test_config.py: 2 tests for placeholder rejection and exact backup destination.
- test_codex_usage.py: 3 checks of usage response interpretation.
- run_team.ps1 -DryRun -Manifest docs/tasks/initial/manifest.json: installed CLI
  presence, discovered initial tasks and valid manifest.
- GUI JavaScript syntax and PowerShell launcher parsing passed. The actual local
  interface rendered and switched between Director, Dashboard and Guide views.
  The Pause team button reached Safe pause confirmed in an isolated runtime
  without a live model call. Launcher browser-process selection is mock-tested;
  a complete double-click launch on a fresh Windows installation was not tested.

The timeout test initially failed in the host sandbox because taskkill was denied
access to its fake process tree. The same offline suite passed outside that
sandbox with authorized access to terminate its own test child processes. No
timeout check was removed or weakened.

## Not established by this validation

No live model smoke checks or end-to-end provider pilot were run for this extraction.
Model availability, authentication, exact vendor CLI version compatibility,
long-duration reliability, paid-account behavior, product generation and browser
acceptance must be verified in each adopted environment. Self-repair is not proven
to repair arbitrary future defects. No notifications were enabled and no standing
automatic product-push approval was created.

Run `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test_all.ps1`
to repeat the offline suite. Logs are written to ignored out/tests/. Run the live
smoke/pilot procedures in SETUP.md separately when authorized.
