# Simple MVP build protocol

1. Director (GPT-6 Astra) supplies the product spec and implementation plan once.
2. Foreman (Opus 4.6 medium; Sol 5.6 high on usage-limit fallback) reads that
   direction and writes the remaining ordered tasks as Markdown files, once.
3. OpenCode implements each task and runs its focused tests.
4. After every two tasks, and at the end, Foreman briefly checks actual changes
   and test evidence against the plan. One concrete repair is allowed.
5. Persist task completion and check progress in runtime/task-queue.json.
   Resume that queue after interruption. Later source edits do not reset earlier tasks.

No nested agents, second reviewer, planning rounds, mandatory memory records,
or recursive Director recovery. Report a precise failure if the bounded repair
fails. Provider cooldown waits may resume the same assignment; they do not replan.
Respect owner pause. Only the supervisor owns Git checkpoints. Preserve product
scope, credentials, existing work and honest acceptance evidence.
A completed queue is COMPLETE; read its report for any remaining live limitations.
