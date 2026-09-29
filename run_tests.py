#!/usr/bin/env python
"""Helper script to run backend tests and frontend builds from project root."""
import subprocess
import sys
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(ROOT, 'backend', '.venv', 'Scripts', 'python.exe')
BACKEND_DIR = os.path.join(ROOT, 'backend')
FRONTEND_DIR = os.path.join(ROOT, 'frontend')

def run(cmd, cwd=None, env=None):
    print(f"\n>>> {' '.join(cmd)}", flush=True)
    r = subprocess.run(cmd, cwd=cwd or ROOT, text=True, capture_output=False, env=env)
    return r.returncode

if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'pytest'
    rc = 0
    if mode == 'pytest':
        rc = run([VENV_PYTHON, '-m', 'pytest', 'tests/', '--tb=short', '-q'], cwd=BACKEND_DIR)
    elif mode == 'tsc':
        node = subprocess.run(['which', 'node'], capture_output=True, text=True).stdout.strip() or 'node'
        rc = run([node, 'node_modules/.bin/tsc', '--noEmit'], cwd=FRONTEND_DIR)
    elif mode == 'build':
        node = subprocess.run(['which', 'node'], capture_output=True, text=True).stdout.strip() or 'node'
        rc = run([node, 'node_modules/.bin/vite', 'build'], cwd=FRONTEND_DIR)
    sys.exit(rc)
