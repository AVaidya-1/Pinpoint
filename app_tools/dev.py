"""Dev server launcher for the Visual Evidence P0 slice.

Starts the backend (uvicorn) on 127.0.0.1:8000 and the frontend (vite) on
127.0.0.1:5173 using absolute paths, so it works from any working directory.
The e2e harness is the sole owner of this launcher's lifecycle during tests.

On Windows the launcher prints `PID:<backend_pid>,<frontend_pid>` within the
first lines of stdout so the harness can track and stop the exact processes.

`--check` starts both servers, waits for health, then shuts down cleanly and
exits 0 on success.
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
LOG_DIR = ROOT / "out" / "orchestration" / "import-viewer" / "logs"

BACKEND_URL = "http://127.0.0.1:8000/api/health"
FRONTEND_URL = "http://127.0.0.1:5173/"


def venv_python() -> Path:
    if os.name == "nt":
        return BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
    return BACKEND_DIR / ".venv" / "bin" / "python"


def wait_http(url: str, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as res:
                if res.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(1.0)
    return False


def spawn_all(env: dict, log_files: bool = True):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    backend_log = open(LOG_DIR / "backend.log", "ab") if log_files else None
    frontend_log = open(LOG_DIR / "frontend.log", "ab") if log_files else None
    backend = subprocess.Popen(
        [str(venv_python()), "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", "8000"],
        cwd=str(BACKEND_DIR),
        env=env,
        stdout=backend_log,
        stderr=subprocess.STDOUT,
    )
    node = shutil.which("node")
    if node is None:
        backend.terminate()
        raise RuntimeError("node not found on PATH")
    vite_js = FRONTEND_DIR / "node_modules" / "vite" / "bin" / "vite.js"
    frontend = subprocess.Popen(
        [node, str(vite_js), "--host", "127.0.0.1", "--port", "5173", "--strictPort"],
        cwd=str(FRONTEND_DIR),
        env=env,
        stdout=frontend_log,
        stderr=subprocess.STDOUT,
    )
    return backend, frontend


def shutdown(backend, frontend, timeout_s: float = 30.0) -> None:
    for proc in (backend, frontend):
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
    deadline = time.monotonic() + timeout_s
    for proc in (backend, frontend):
        if proc is None:
            continue
        remaining = max(0.1, deadline - time.monotonic())
        try:
            proc.wait(timeout=remaining)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    print("visual-evidence dev launcher", flush=True)
    print(f"root: {ROOT}", flush=True)

    env = dict(os.environ)
    env.setdefault("EVIDENCE_DATA_DIR", str(ROOT / "data"))

    try:
        backend, frontend = spawn_all(env)
    except Exception as e:
        print(f"spawn failed: {e}", flush=True)
        return 1
    print(f"PID:{backend.pid},{frontend.pid}", flush=True)

    if args.check:
        ok_backend = wait_http(BACKEND_URL, 90.0)
        ok_frontend = wait_http(FRONTEND_URL, 90.0)
        shutdown(backend, frontend)
        if ok_backend and ok_frontend:
            print("check: both servers healthy", flush=True)
            return 0
        print(f"check failed: backend={ok_backend} frontend={ok_frontend}", flush=True)
        return 1

    # Serve until killed (the harness owns this process) or a child exits.
    try:
        while True:
            be = backend.poll()
            fe = frontend.poll()
            if be is not None or fe is not None:
                print(f"child exit: backend={be} frontend={fe}", flush=True)
                shutdown(backend, frontend)
                return 1 if (be not in (None, 0) or fe not in (None, 0)) else 0
            time.sleep(1.0)
    except KeyboardInterrupt:
        shutdown(backend, frontend)
        return 0


if __name__ == "__main__":
    sys.exit(main())
