# Task 10 — General evidence localization quality repair

Use a fresh Claude Code Sonnet 4.6 session. Read the current product brief,
build directive, `APP_README.md`, Task 09 report, and the completed version 3
evaluation report/summary. Version 3 is development evidence now because its
failures are being used for this repair. Do not read, inspect, search for, or
modify `out/evaluation-v4` or its generator. Do not delegate.

The current app finds all 16 answerable source pages and abstains correctly on
4/4 absent questions, but evidence localization is 9/16 and visual localization
is 5/8. General defects observed on development data:

- Tight text boxes clip the visible glyph envelope or leave too little readable
  margin. Add a small bounded padding policy for ordinary text evidence. It must
  remain far below the 3x allowed evidence area and must not turn a line into a
  paragraph or page selection.
- A chart relationship can be accepted while omitting a named legend item or
  the axis label needed to establish high/low direction. Strengthen locate,
  repair-locate and check behavior so chart relationship evidence includes the
  plot plus the relevant legend and axis labels. Keep 1–3 boxes and do not select
  the whole page.
- A repeated-object heading can be semantically correct but have coordinates so
  tight that part of the identifier falls outside the marked region. Preserve
  the existing deterministic PDF identifier guard and ensure bounded padding
  makes the full printed identifier visible.
- Repair call accounting must count attempted calls even when transport fails.

Make a general implementation with deterministic tests. Do not hard-code any
fixture question, text, ID, page, expected box or answer. Do not weaken the 80%
coverage or 3x area thresholds and do not alter any frozen evaluation suite or
report. Keep `gemma-4-26b-a4b-it` and the configured free path. Run the full
backend suite, TypeScript check and frontend build if permitted. Use at most
four synthetic development probes from version 3 if live calls are needed.
Write `out/rapid-build/10-report.md` with changes, commands, results and gaps.
Report and stop. Do not deploy, push, spend money, reveal keys or change model
providers.
