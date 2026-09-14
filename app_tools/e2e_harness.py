"""External E2E harness: SOLE owner of test-server startup, restart and
teardown for browser evidence. No Playwright config or spec file may start or
stop servers.

Behavior of `... python app_tools/e2e_harness.py run` (cwd = project root):
  (a) spawn dev.py, read PID:<backend>,<frontend> from its stdout;
  (b) poll backend health until 200;
  (c) run the single Playwright invocation, preserving its exit code;
  (d) record docs_before; (e) shut down by PID with confirmed exit;
  (f) fresh start, record docs_after, shut down again;
  (g) write restart-evidence.json; (h) exit 0/4/5.

Test-environment note: the task-mandated E2E matrix needs six live documents
at once (one multi-page PDF subset plus five orientation fixtures), while the
product default stays at five documents (see .env.example; default enforced
and covered by backend pytest). The harness therefore raises only the spawned
test servers' document cap to eight via the existing EVIDENCE_MAX_DOCUMENTS
setting. The gated 20-page workspace capacity runs at its true default.
"""

import ctypes
import json
import os
import queue
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_VENV_PY = ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
DEV_PY = ROOT / "app_tools" / "dev.py"
EVIDENCE_DIR = ROOT / "out" / "orchestration" / "import-viewer"
HEALTH_URL = "http://127.0.0.1:8000/api/health"
DOCS_URL = "http://127.0.0.1:8000/api/documents"

# Document cap for harness-spawned test servers only (see module docstring).
HARNESS_MAX_DOCUMENTS = "8"


def pid_alive(pid: int) -> bool:
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x0400, False, pid)  # QUERY_INFORMATION
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    except Exception:
        pass
    # Fallback: tasklist inspection.
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, timeout=15,
        ).stdout
        return str(pid) in out
    except Exception:
        return False


def wait_pid_exit(pid: int, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            return True
        time.sleep(1.0)
    return not pid_alive(pid)


def taskkill(pid: int) -> None:
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True, timeout=30)
    except Exception:
        pass


def spawn_dev(env: dict, timeout_s: float = 30.0):
    """Start dev.py; return (Popen, backend_pid, frontend_pid)."""
    proc = subprocess.Popen(
        [str(BACKEND_VENV_PY), str(DEV_PY)],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    lines: queue.Queue[str] = queue.Queue()

    def _reader() -> None:
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                lines.put(line)
        except Exception:
            pass

    thread = threading.Thread(target=_reader, daemon=True)
    thread.start()
    deadline = time.monotonic() + timeout_s
    output: list[str] = []
    while time.monotonic() < deadline:
        try:
            line = lines.get(timeout=1.0)
        except queue.Empty:
            if proc.poll() is not None:
                raise RuntimeError(f"dev.py exited early with code {proc.returncode}")
            continue
        output.append(line)
        if line.startswith("PID:"):
            _, _, rest = line.partition("PID:")
            parts = rest.strip().split(",")
            return proc, int(parts[0]), int(parts[1])
    raise RuntimeError("PID line not received from dev.py within timeout:\n" + "".join(output))


def wait_health(timeout_s: float = 120.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=5) as res:
                if res.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(1.0)
    return False


def get_doc_ids() -> list[str]:
    with urllib.request.urlopen(DOCS_URL, timeout=15) as res:
        body = json.loads(res.read().decode("utf-8"))
    return sorted(d["id"] for d in body.get("documents", []))


def shutdown_by_pid(launcher, child_pids: list[int]) -> bool:
    """Terminate the launcher, then confirm both children exited (taskkill
    fallback). Returns True iff everything exited cleanly."""
    try:
        launcher.terminate()
    except Exception:
        pass
    try:
        launcher.wait(timeout=30)
        launcher_ok = True
    except Exception:
        launcher_ok = False
    children_ok = True
    for pid in child_pids:
        if not wait_pid_exit(pid, 30.0):
            taskkill(pid)
            if not wait_pid_exit(pid, 15.0):
                children_ok = False
    return bool(launcher_ok and children_ok)


def run_playwright() -> int:
    result = subprocess.run(
        "npx --prefix frontend playwright test --config frontend/playwright.config.ts",
        cwd=str(ROOT),
        shell=True,
    )
    return int(result.returncode)


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] != "run":
        print("usage: e2e_harness.py run", flush=True)
        return 2
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env["EVIDENCE_MAX_DOCUMENTS"] = HARNESS_MAX_DOCUMENTS
    env.setdefault("EVIDENCE_DATA_DIR", str(ROOT / "data"))

    # (a)+(b): first server generation.
    try:
        launcher1, be1, fe1 = spawn_dev(env)
    except Exception as e:
        print(f"spawn failed: {e}", flush=True)
        return 3
    if not wait_health(120.0):
        print("backend health timeout", flush=True)
        shutdown_by_pid(launcher1, [be1, fe1])
        return 3

    # (c): single Playwright invocation.
    playwright_exit = run_playwright()

    # (d): record documents before restart.
    try:
        docs_before = get_doc_ids()
    except Exception as e:
        print(f"docs_before failed: {e}", flush=True)
        docs_before = []

    # (e): shutdown generation 1 by PID.
    shutdown1_clean = shutdown_by_pid(launcher1, [be1, fe1])

    # (f): fresh server generation + docs_after + shutdown.
    try:
        launcher2, be2, fe2 = spawn_dev(env)
    except Exception as e:
        print(f"respawn failed: {e}", flush=True)
        return 5
    if not wait_health(120.0):
        print("backend re-health timeout", flush=True)
        shutdown_by_pid(launcher2, [be2, fe2])
        return 5
    try:
        docs_after = get_doc_ids()
    except Exception as e:
        print(f"docs_after failed: {e}", flush=True)
        docs_after = []
    shutdown2_clean = shutdown_by_pid(launcher2, [be2, fe2])

    # (g): restart evidence.
    passed = (
        playwright_exit == 0
        and len(docs_before) > 0
        and docs_before == docs_after
        and shutdown1_clean
        and shutdown2_clean
    )
    with open(EVIDENCE_DIR / "restart-evidence.json", "w", encoding="utf-8") as f:
        json.dump({"docs_before": docs_before, "docs_after": docs_after, "pass": passed}, f, indent=2)
        f.write("\n")

    # (h): exit status.
    if passed:
        return 0
    if playwright_exit != 0:
        return 4
    return 5


if __name__ == "__main__":
    sys.exit(main())
