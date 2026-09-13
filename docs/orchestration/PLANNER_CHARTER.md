# Planner charter

## Authority and termination
OWNER_BRIEF.md and docs/product/PRODUCT_BRIEF.md define scope and acceptance.
Agents cannot change them. Director supplies strategy; F1 owns bounded planning;
F2 independently approves the plan and memory before any worker dispatch.
Complete only the stated goal, then propose DONE. No automatic next product.

## Every planning call
Read the supplied packet, current round CONTEXT.md and relevant primary evidence.
Write runtime/memory/candidate.json according to CONTEXT_PROTOCOL.md, regardless
of outcome. Under out/orchestration/runtime write exactly one signal:
- CONTINUE: next_round.txt containing a project-relative manifest path.
- DONE candidate: COMPLETION_REPORT.md with acceptance and regression evidence.
- STUCK: director_request.md with failed approaches and needed technical guidance.
- BLOCKED: OWNER_QUESTIONS.md with the indispensable owner decision and evidence.
F2 reviews the candidate and outcome. Director alone accepts DONE or BLOCKED.

## New rounds
Create a new docs/tasks/<unique-round>/ directory with CONTEXT.md, one to eight
task Markdown files and manifest.json (see ../tasks/initial/manifest.json).
Do not rewrite existing task documents. Each task states allowed writes,
prohibitions, bounded steps, exact outputs, independent validation commands,
Done-when, escape hatch, and ends with "Report, then STOP."
Task docs remain under docs/. Gate files remain under out/orchestration/.
Timeout is 1-480 minutes. Use continue_on_fail=false unless a failure is explicitly
nonblocking. The manifest JSON schema is documented in ../SETUP.md.
Diagnosis is read-only. Implementation tasks edit only authorized product paths.
Do not modify orchestration, policy, prior evidence, credentials, or Git metadata.

## Reviews and escalation
F2 responds VERDICT: APPROVE, REVISE or BLOCKED on its first line. APPROVE covers
both plan/outcome and memory. Revisions retain all material disagreements.
Technical impasses return to Director; routine failure does not require an owner.
F1's emergency hold is available only for concrete safety/coordinator integrity
problems while persisted OpenAI quota proves Director unavailable. Use
scripts/foreman1_hold.ps1, never forge a Director pause or terminal record.


## Visual Evidence P0 execution contract
Read docs/product/PRODUCT_BRIEF.md in full. Its fixed A1-A12 software checks and
20-question holdout thresholds control completion. No generated answer text.
Use React/TypeScript/Vite, react-zoom-pan-pinch, Python 3.12/FastAPI,
pypdfium2/Pillow, SQLite/files, official google-genai and preflight-selected Gemma.
No P1 integrations, deployment, paid fallback, pushes or external notifications.
Budget 480 minutes: preflight/contracts 30; import/viewer 75; model/search 100;
states/errors 65; verification/handoff 80; independent reviews 90; repair 40.
This is an allocation, not an enforced wall-clock deadline. Use supported pause.
Plan bounded serial tasks starting with IMPORT_VIEWER_SLICE. Establish a real
model rectangle early, then source-only search, failure/persistence behavior,
browser and frozen live evaluation, and APP_README.md handoff.
Track mocked software evidence separately from real provider evidence. Do not
prepopulate PASS reports, tune on holdout truth or weaken quality thresholds.
If a required preflight is unavailable, record the exact dependency; do not
spend the build budget fabricating a successful visual demo.
Product utilities live under app_tools/, and backend environment in backend/.venv.
Generated fixtures/data/logs go to ignored paths; track generators and JSON truth.
