# Task 11 — General named-region context guard repair

Use a fresh Claude Code Sonnet 4.6 session. Read the current product brief,
build directive, APP_README, Task 10 report, and version 4 evaluation summary.
Version 4 is development evidence now. Do not read, search for, inspect, or
modify `out/evaluation-v5` or `app_tools/generate_holdout_v5.py`. Do not delegate.

The padding and chart repair worked on every version 4 result that completed:
all text, completed tables, and the completed chart relationship passed geometry.
Nine provider transport failures made that run incomplete as quality evidence.
One real product miss remains: when a repeated diagram is qualified by a
multiword named region such as `Zone North`, the locate/check path can accept the
object body without the region heading. The deterministic PDF identifier guard
currently recognizes numeric/single-letter identifiers such as `Loop 1` and
`Bank B`, but misses descriptive names.

Generalize the deterministic guard conservatively for contextual designators
such as zone, sector, bank, loop, panel, module, channel, bay, side, circuit and
unit followed by an alphanumeric or descriptive label. Only enforce a phrase
when it appears uniquely in extractable PDF text and the question contains it.
Do not require arbitrary capitalized phrases and do not reject raster-only pages
where deterministic text evidence is unavailable. Ensure both words of the
unique phrase are within the marked boxes after bounded padding. Add tests for
descriptive labels, numeric labels, duplicate phrases, missing text, and a
correctly included heading. Do not hard-code any fixture question, ID, answer,
page or box.

Also review why an explicit named boundary question can yield `not_found` on a
visibly outlined repeated region. Improve general locate and repair prompts so a
named boundary/enclosure/section question selects the complete visible boundary
plus its identifying heading, while keeping 1–3 boxes and avoiding whole-page
selection. Do not alter frozen evaluation files or thresholds. Keep the free
`gemma-4-26b-a4b-it` path. Run the full backend suite, TypeScript and frontend
build if permitted. Write `out/rapid-build/11-report.md`, report, and stop. Do
not deploy, push, spend money, expose keys or change providers.
