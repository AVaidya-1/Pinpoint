# Director implementation plan — finish the P0 MVP

The product spec already exists in PRODUCT_BRIEF.md. Keep its P0 scope and A1–A12
acceptance criteria. Build the localhost upload → question → source highlight
journey. Use the existing free Gemma configuration; no P1 or deployment.

## Starting point

The import/viewer slice has a recorded Foreman PASS in runtime/state.json.
Search/provider/UI code now exists. The search-highlight/report.json records
33 passing backend tests and a successful frontend build, with mocked provider
evidence only. This report is useful prior evidence, not proof of live quality.
Preserve this implementation. Inspect relevant code before deciding what is missing;
do not rebuild the first two slices or repeat old planning/review rounds.

## Remaining implementation in order

1. **Complete the real question-to-highlight journey.** Finish or fix the existing
   provider, search, results and viewer wiring. Establish a real model-produced
   rectangle on a small public/self-created fixture early. Record provider failures
   honestly. Keep source-only output, validated coordinates and visible coverage.
2. **Finish state and failure behavior.** Cover persistence, cache/invalidation,
   cancellation, restart/interruption, deletion, capacity and provider errors.
   Implement only missing behavior. Use focused deterministic tests for A6–A11;
   a missing key or failed call must never look like no evidence.
3. **Complete browser acceptance and fix integration failures.** Exercise upload,
   question, source selection, highlights, zoom/pan/resize, rotation/crop and reload.
   Extend existing Playwright tests and retain inspected screenshots. Verify A1–A12
   with reproducible commands, reusing still-relevant evidence.
4. **Evaluate and hand off the runnable app.** Run the frozen 20-question holdout
   using the real configured provider without exposing truth to it. Preserve the
   spec's denominators and thresholds. Report software results separately from
   live model quality, plus supplemental real-document observations when available.
   Deliver APP_README.md with install/start/test commands and known limitations.
   If live quality fails or free quota prevents finishing it, deliver the working
   software and a candid report; do not spend the night tuning or replanning.

## Execution

Foreman: read this plan and the spec, inspect current implementation, and create
one ordered set of remaining task Markdown files in docs/tasks/build. Prefer
four to six useful tasks; combine steps where already implemented. Include final
acceptance and handoff in the queue. No separate diagnosis or planning tasks.
OpenCode executes those files sequentially. Foreman checks progress after every
two tasks and at the end, with one focused repair for concrete failures.
Do not add approval rounds, memory work, extra reviewers or recursive planning.
