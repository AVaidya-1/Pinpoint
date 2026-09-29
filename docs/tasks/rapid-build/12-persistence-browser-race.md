# Task 12 — Fix the persistent-viewer highlight race

## Context

The exact current app passes 119 backend tests, TypeScript, production build,
and the fresh Version 5 quality holdout. The final standard Playwright run had
one failure and otherwise passed 24 tests with 5 intentional provider skips:

`frontend/tests/persistence.spec.ts:66` — `completed backend state survives page reload`

At line 82, after navigating to `/?box=0.1,0.2,0.5,0.6` and clicking page 1,
`highlight-rect` never appeared within 60 seconds. The failure screenshot showed
the two page image elements with broken-looking placeholders, while the backend
has returned HTTP 200 for page image requests in similar runs. This same test has
passed in isolation before, so diagnose the lifecycle/readiness race rather than
weakening the assertion or adding a blind sleep.

## Goal

Make page image readiness and highlight rendering reliable across navigation,
cached images, document refreshes, and reloads. The product behavior is the
priority; adjust the test only if it is demonstrably asserting before a real
readiness condition.

## Requirements

1. Inspect `frontend/src/components/PageViewer.tsx`, `frontend/src/App.tsx`,
   `frontend/tests/persistence.spec.ts`, and the latest Playwright failure artifact.
2. Identify the concrete race. Prefer a product fix if cached/rapid image loads can
   leave `naturalSizes` unset. A callback ref or effect may record dimensions when
   an image is already complete, while retaining `onLoad` for normal loads.
3. Keep normal search evidence, URL test boxes, zoom, scrolling, and 500-page lazy
   loading behavior intact.
4. Do not replace the meaningful highlight assertion with a superficial DOM check.
   Do not add arbitrary long sleeps.
5. Run TypeScript and the isolated persistence spec if possible. Do not modify
   backend search quality, evaluation inputs, or frozen reports.
6. Write `out/rapid-build/12-report.md` with the root cause, files changed, and
   honest test results. Stop after this bounded fix.

## Reviewer commands

```powershell
frontend\node_modules\.bin\tsc.cmd --noEmit -p frontend\tsconfig.json
frontend\node_modules\.bin\playwright.cmd test frontend\tests\persistence.spec.ts --config frontend\playwright.config.ts
```
