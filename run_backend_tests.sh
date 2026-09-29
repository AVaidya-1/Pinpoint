#!/usr/bin/env bash
# Run backend tests using the project venv
set -e
ROOT="C:/Users/vaidy/Documents/Pinpoint/visual-evidence"
VENV="$ROOT/backend/.venv/Scripts/python.exe"
"$VENV" -m pytest "$ROOT/backend/tests/" --tb=short -q 2>&1
