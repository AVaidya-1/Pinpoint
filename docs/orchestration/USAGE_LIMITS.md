# Usage limit handling

The supervisor waits automatically and retries the interrupted assignment with
the same role, model and effort. A fresh context packet includes recovery
instructions pointing to the previous attempt logs; the agent must inspect
partial artifacts before continuing. A quota failure never advances a review gate.

Provider cooldowns are atomically saved as `usage-<provider>.json` in the runtime
directory. Director and F2 conservatively share OpenAI's bucket. F1 uses
Anthropic; the worker uses OpenCode. Every dispatch checks its bucket, including
after a supervisor restart. Success clears the bucket's consecutive-limit count.

Unambiguous Retry-After seconds, relative seconds/minutes/hours and ISO reset
timestamps with timezone are supported, with a five-second buffer. No guessed
reset or exponential quota delay is used. For Codex, codex_usage.py uses the
documented account/rateLimits/read app-server method, without creating a model
turn, to check actual availability every minute while waiting. An available
account clears obsolete waits immediately; exhausted windows use server Unix
reset timestamps (the later reset if both windows are exhausted). Missing data
means unknown, never zero usage. Read failures keep waiting for another status
check. The helper has bounded timeouts and never consumes a reset credit.
Other providers with unknown reset timing wait until the persisted next check
(initially five minutes), then retry the original call as an availability probe.
An explicit provider reset time delays retry until that reset plus its buffer.
Director-authorized pause interrupts waits. STOP.txt alone does not authorize a
pause, and MaxHours is not a total budget over quota and recovery waits.

Overload, temporary service failures and selected connection errors receive one
short retry. Authentication/model errors stop immediately; other errors retain
the existing single retry. Detection requires recognizable diagnostic lines,
and exact echoed prompt lines are excluded. Unknown provider error formats may
stop as ordinary errors instead of automatically waiting. Logs preserve evidence.

The dashboard separates provider-reported resets from the next availability
check. Unknown reset times are explicitly labeled unknown. Legacy estimated
cooldowns are discarded on the next account check.
No model fallback, credit purchase or billing configuration change is performed.
Existing account-side extra-usage settings are not inspected or changed here.
No alternate provider fallback is configured.

`pending-operation.json` records each dispatched attempt and its prompt/log paths.
Previous records are preserved when a new invocation starts. Cooldown recovery
across restarts is supported; exact restoration of the caller's planning/review
stack after a crash is not. Do not interpret this checkpoint as exactly-once
execution or reboot recovery. Automatic same-assignment continuation is supported
while the supervisor remains running, including fresh agent sessions after limits.

Validation: `scripts/tests/test_usage_limits.ps1` uses only local synthetic agents
and checks parsing, shared buckets, obsolete-wait recovery, stop handling, and recovery
of partial work. It does not consume subscription quota or launch product tasks.

The inherited helper invokes Codex app-server account/rateLimits/read. This extraction tested response interpretation with mocks; live provider availability must be verified separately.
