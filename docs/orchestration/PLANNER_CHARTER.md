# Foreman task decomposition

Read docs/product/PRODUCT_BRIEF.md and the Director implementation plan supplied
by the runner. Inspect existing implementation and preserve completed work.
Create one ordered queue of Markdown tasks covering the remaining MVP, including
focused tests and final acceptance. Use docs/tasks/build/manifest.json and a
CONTEXT.md alongside the task files. Follow the initial manifest schema; 1-32 tasks.
Each task specifies useful implementation, allowed paths, outputs, and focused tests.
Task evidence stays under out/orchestration/. Do not weaken product acceptance.

Finish decomposition in one call. A malformed manifest gets one format repair.
There are no planning rounds, plan approvals, memory candidates or second reviewers.
OpenCode executes the queue serially. Check progress after two tasks and at the end.
A concrete failure gets one focused worker repair, not another planning cycle.
Opus 4.6 medium is the Foreman; Sol 5.6 high takes over only on Opus usage limits.
Product constraints and scope are in OWNER_BRIEF.md and PRODUCT_BRIEF.md.
