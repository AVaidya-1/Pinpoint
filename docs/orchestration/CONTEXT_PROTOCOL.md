# Execution policy (current default)

This policy supersedes conflicting dual-approval instructions below. The owner
requires autonomous delivery with minimal management overhead.

- One concise plan, then Worker implementation and focused tests. A structurally
  valid manifest dispatches immediately without F2 approval.
- F1 reviews a task once, within ten minutes, using existing evidence. Repeat a
  check only after relevant code/input changes or a concrete failing observation.
  Do not turn a slice review into a full-product audit. One repair attempt is allowed.
- Exactly one Foreman: Opus 4.6 medium, with Sol 5.6 high taking over only
  on Opus usage limits. No second review role or thorough-review mode exists.
- Memory updates are optional bookkeeping. Planner-authored summaries are labeled
  as such, not independently approved. Invalid memory cannot block valid work.
- The Director owns outcomes and may author task details directly. After a planning
  impasse, the runner dispatches the Director as task author, bypassing the foremen.
- Continue to the next unfinished product slice after a pass. No repeated validation
  of unchanged successful work. Preserve existing work and evidence across restarts.
- Owner scope, credentials, spending constraints and actual product acceptance still
  apply. Only the Director accepts final completion based on product evidence.

The remaining document is historical reference where it conflicts; dual-foreman instructions do not apply.

# Fresh sessions, durable project memory

Every worker, planner, reviewer and Director call starts a fresh conversation.
Never resume the latest session implicitly. The initial context packet is
saved with each call; subsequent investigation may consume additional context.
Character budgets below bound input text, not exact model token usage.

## What each session gets

1. Owner brief (at most 5,000 characters), plus role and task constraints.
2. Latest F2-approved summary (at most 8,000 characters), with revision and
   freshness indicator. A stale summary is historical, not current proof.
3. Role inbox: up to eight messages / 6,500 characters, with a visible remaining
   count and paging instructions. F1 and F2 can see every role's open messages.
4. Latest twelve machine-recorded task statuses and specific assignment.

Packets are capped at 24,000 characters. Assignments have a separate 24,000
character cap; total initial requests are capped at 52,000. Constraints are
never silently truncated. Full task documents, reports and primary artifacts
remain available for selective inspection. Large tasks must be split by F1.
Fresh sessions alone do not prevent a single task from reading too much.

Do not load entire communications.md, digest.md, notes.md or transcripts.
Use `rg -n` with a task/message ID or filename; inspect relevant matches and
linked artifacts. Handle the supplied inbox batch; current-task messages are
prioritized, then older messages. Retrieve additional messages by ID or page only
when relevant to the assignment or a proposed resolution. Unhandled messages
remain queued for future calls, independently of the summary. Completion cannot
pass while any open QUESTION lacks an explicit proposed disposition for F2 review.

## How a message survives

Use `scripts/team_message.ps1` to create an immutable message in
`overnight/memory/messages/`. JSON is authoritative; Markdown is its readable
copy. Each has a unique ID, sender, recipient, task ID, type, body, evidence
and optional Reply-To ID. Types are QUESTION, ANSWER, FINDING and DECISION.

Example (run from project root, prepare body.md with the exact text):

```powershell
powershell -File scripts/team_message.ps1 -From Worker -To Foreman1 -Task DEMO `
  -Kind QUESTION -BodyFile out/body.md -Evidence out/specific_report.json
powershell -File scripts/team_message.ps1 -List -Role Foreman1 -Offset 0
```

For isolated tests pass `-RuntimeDirectory <test-folder>`. Body limit is 3,000
characters; longer evidence belongs in linked artifacts. Do not put credentials
or private reasoning into messages. Never edit old messages. Reply using ANSWER
and Reply-To. Replying, reading, or starting a fresh session does not close a
message. F1 proposes an explicit resolution; F2 must approve it. Dissent and
unresolved questions remain visible independently of what a summary omits.
Messages are read at call boundaries, not streamed into an already-running agent.

## Updating shared memory

F1 writes `overnight/memory/candidate.json` each time it plans/classifies a round.
This is part of the existing planning call, not an extra model invocation.
Use this schema (relative evidence paths are relative to the project root):

```json
{
  "base_revision": "current revision from packet, or empty string for NONE",
  "summary_md": "## Goal\n...\n## Verified facts\n...\n## Decisions\n...\n## Hypotheses\n...\n## Open questions\n...\n## Next steps\n...",
  "evidence": ["out/path/to/report.json"],
  "resolutions": [
    {"id": "existing message ID", "resolution": "Evidence-backed disposition", "evidence": ["out/path/to/answer.md"]}
  ]
}
```

Use `"resolutions": []` when nothing can be closed. Preserve material decisions,
failed approaches and uncertainties from the previous snapshot. Cite sources
beside verified claims; do not promote observations or a worker's PASS to truth.
Never change owner goals or charter gates through a summary.

F2 reviews the candidate along with F1's plan/outcome. APPROVE means both passed.
The supervisor freezes the candidate for review, checks evidence hashes before
publication, saves a new immutable snapshot and atomically switches current.json.
Only then do approved resolutions disappear from the open inbox. Old summaries,
messages and review records remain searchable. A rejected candidate cannot replace
the prior summary or close anything. Changed evidence/task state marks memory stale.

## Ownership

- Owner brief and charter: owner policy, never rewritten by summarization.
- Director strategy: Director; read as scoped technical guidance.
- Candidate: F1; approval: F2; publication/pointer: supervisor.
- Messages: send through helper; closure: F1 proposal plus F2 approval.
- Packets, task state and full handoff ledger: supervisor.

On first use there is intentionally no approved summary. F1 reconstructs it from
current evidence; F2 checks it. Historical notes remain searchable and are explicitly
unverified until cited and reviewed. Context is reconstructed from files after a
crash, not from a vendor session's private conversation history.
