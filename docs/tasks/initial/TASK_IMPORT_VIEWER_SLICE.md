# IMPORT_VIEWER_SLICE

## Bounded deliverable and prior evidence
Read CONTEXT.md, docs/product/PRODUCT_BRIEF.md and its setup handoff. In at most
75 minutes implement an import-to-viewer vertical slice; product/model preflight
must be resolved before the unattended run. No existing application is assumed.

## Allowed writes
backend/** except backend/.venv source commits; frontend/** except dependency/build
outputs in source commits; fixtures/generate.py, fixtures/development.json,
fixtures/holdout.json; app_tools/**; APP_README.md; .env.example with safe values.
Runtime/dependencies may be generated only in ignored backend/.venv, node_modules,
data, fixtures/generated, and out/. Evidence: out/orchestration/import-viewer/**.
Do not modify scripts/, orchestration.json, owner/product policy, prior task
contracts, review/memory/stop records, Git metadata or credentials. No Git
commands, hidden agents, pushes, paid services, deployment or external messaging.

## Ordered procedure
1. Resolve the selected P0 dependencies and lockfiles; preserve root .venv.
2. Generate a technical PDF and raster image with known overlay coordinates.
3. Implement bounded upload, page selection, serialized PDFium rendering,
   EXIF orientation, canonical raster persistence and document/page API routes.
4. Show documents and original pixels in a React viewer with image/SVG sharing
   the zoom/pan transform. Add Fit, 100%, 200%, pan and highlight controls.
5. Exercise a clearly labeled deterministic TEST overlay only for this slice.
   Do not claim inference or insert fixture answers into a live provider path.
6. Verify capacity, invalid selections, rotation/crop and restart persistence.
7. Document install/start/stop/test commands in APP_README.md.

## Acceptance commands from product root
uv sync --project backend --python 3.12
npm --prefix frontend ci
uv run --project backend python fixtures/generate.py
uv run --project backend pytest backend/tests
npm --prefix frontend run build
npm --prefix frontend run test:e2e
uv run --project backend python app_tools/dev.py

Define and execute the browser command with Playwright. Inspect screenshots of
the actual imported page with overlay at Fit, 100%, 200%, pan and resize. Confirm
PDF CropBox/Rotate=90 and EXIF fixtures; assert original bytes stay unchanged.
Startup must bind 127.0.0.1:8000 and 127.0.0.1:5173; stop must end owned children.
Reopen persisted imports after a real application restart. Invalid range and
capacity failures must be visible. Tests must check observable behavior, not just
assert a report flag. Existing orchestration regressions must remain intact.

## Evidence and escape hatch
Write out/orchestration/import-viewer/report.json from executed checks, including
checks.all_pass, commands, exit codes, input hashes/source revision, screenshots,
observations and all remaining failures. Retain raw logs beside it. all_pass can
be true only if these slice checks pass; this is not final product acceptance.
If dependencies/access or core geometry block progress, preserve work and failure
evidence and report the exact bounded next hypothesis to F1. Never lower criteria.
F1 and F2 independently inspect the full diff and primary evidence.

Report, then STOP.
