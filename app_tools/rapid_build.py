"""Run the owner's rapid build as fresh, sequential Claude Code sessions.

Usage: python app_tools/rapid_build.py [--status]
Runtime evidence is kept in ignored out/rapid-build. This deliberately does not
use the older Director/F1/F2 supervisor, whose current task state stalled.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "rapid-build"
STATE = OUT / "runner-state.json"
TASKS = [
    "01-restore-visual-search.md",
    "02-large-pdf-and-navigation.md",
    "03-browser-and-live-evaluation.md",
    "04-handoff.md",
]
MODEL = "claude-sonnet-4-6"
MAX_HOURS = 8
SESSION_TIMEOUT_SECONDS = 105 * 60
CHECK_TIMEOUT_SECONDS = 15 * 60
MAX_ATTEMPTS_PER_TASK = 3


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def save(state: dict) -> None:
    state["updated_at"] = stamp()
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary.replace(STATE)


def tail(path: Path, max_chars: int = 6000) -> str:
    if not path.exists():
        return "(no output)"
    return path.read_text(encoding="utf-8", errors="replace")[-max_chars:]


def run_logged(command: list[str], log: Path, timeout: int) -> tuple[int, str]:
    started = time.monotonic()
    with log.open("w", encoding="utf-8", errors="replace") as output:
        try:
            completed = subprocess.run(
                command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, timeout=timeout, check=False,
                env={**os.environ, "PYTEST_ADDOPTS": "-p no:cacheprovider"},
            )
            code = completed.returncode
        except subprocess.TimeoutExpired:
            code = 124
            output.write("\nRunner stopped this process at its timeout.\n")
        except OSError as exc:
            code = 127
            output.write(f"\nCould not start process: {exc}\n")
    return code, f"{time.monotonic() - started:.1f}s"


def checks_for(index: int) -> list[tuple[str, list[str]]]:
    py = str(ROOT / "backend" / ".venv" / "Scripts" / "python.exe")
    # Each run owns a fresh basetemp; a reused pytest-of-{user} directory can
    # have incompatible Windows ACLs between sandboxed and unsandboxed calls.
    base = OUT / f"pytest-{uuid.uuid4().hex}"
    checks = [("pytest", [py, "-m", "pytest", "backend/tests", "-q",
                          "--basetemp", str(base)])]
    if index >= 1:
        checks.append(("typescript", [str(ROOT / "frontend" / "node_modules" / ".bin" / "tsc.cmd"),
                                       "--noEmit", "-p", "frontend/tsconfig.json"]))
        checks.append(("frontend-build", ["npm.cmd", "--prefix", "frontend", "run", "build"]))
    if index >= 2:
        checks.append(("playwright", ["npm.cmd", "--prefix", "frontend", "run", "test:e2e"]))
    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.status:
        print(STATE.read_text(encoding="utf-8") if STATE.exists() else "Not started")
        return 0
    if STATE.exists():
        state = json.loads(STATE.read_text(encoding="utf-8"))
        if state.get("status") == "running":
            # Explicit resume is safe only after the old runner has stopped.
            print("A rapid build is already marked running; inspect its PID and logs.")
            return 2
    else:
        state = {"started_at": stamp(), "tasks": [], "status": "queued"}
    state["pid"] = os.getpid()
    state["status"] = "running"
    state["model"] = MODEL
    save(state)
    initial_start = datetime.fromisoformat(state["started_at"])
    remaining_seconds = MAX_HOURS * 3600 - (datetime.now(timezone.utc) - initial_start).total_seconds()
    deadline = time.monotonic() + max(0, remaining_seconds)

    for index, task_name in enumerate(TASKS):
        if any(t["task"] == task_name and t["status"] == "checks_passed" for t in state["tasks"]):
            continue
        if time.monotonic() >= deadline:
            state["status"] = "time_limit"
            save(state)
            return 3
        task_path = ROOT / "docs" / "tasks" / "rapid-build" / task_name
        report_path = OUT / task_name.replace(".md", "-report.md")
        record = {"task": task_name, "started_at": stamp(), "attempts": [], "status": "running"}
        state["tasks"].append(record)
        save(state)
        failure_context = ""

        attempt = 1
        while attempt <= MAX_ATTEMPTS_PER_TASK:
            remaining = int(deadline - time.monotonic())
            if remaining < 120:
                break
            prompt = (
                "You are executing one bounded implementation task in the Pinpoint Visual Evidence checkout. "
                f"Read the exact task file at {task_path} and the latest build directive. "
                "Complete the task, run its checks, fix failures, and write the requested report. "
                "You have owner authorization for local source edits, dependency installation, "
                "localhost processes, and free configured model tests. Never print or expose API keys, "
                "purchase credits, deploy, push Git, or send messages to other people. "
                "Do not spawn more agents. Work only in this repository. "
                "The model named in this CLI command is your coding model; the app's Gemma model is separate. "
                "Fresh session for this task; do not resume an older conversation. "
                f"Prior attempt failure context: {failure_context or '(none)'}."
            )
            agent_log = OUT / f"task-{index + 1:02d}-attempt-{attempt}-claude.log"
            agent_command = [
                "claude.exe", "-p", "--model", MODEL,
                "--permission-mode", "acceptEdits", "--no-session-persistence",
                prompt,
            ]
            code, elapsed = run_logged(agent_command, agent_log, min(SESSION_TIMEOUT_SECONDS, remaining))
            attempt_record = {
                "number": attempt, "claude_exit": code, "claude_elapsed": elapsed,
                "claude_log": str(agent_log.relative_to(ROOT)), "checks": [],
            }
            record["attempts"].append(attempt_record)
            save(state)
            if code != 0:
                failure_context = f"Claude process exited {code}. Last output: {tail(agent_log, 2500)}"
                if "hit your limit" in tail(agent_log, 2500).lower():
                    local_now = datetime.now().astimezone()
                    reset = local_now.replace(hour=3, minute=0, second=0, microsecond=0)
                    if reset <= local_now:
                        reset += timedelta(days=1)
                    reset += timedelta(minutes=1)
                    wait_seconds = (reset - local_now).total_seconds()
                    if wait_seconds >= deadline - time.monotonic():
                        break
                    state["status"] = "waiting_for_limit"
                    state["next_retry_at"] = reset.isoformat()
                    save(state)
                    while time.monotonic() < deadline and datetime.now().astimezone() < reset:
                        time.sleep(60)
                    state["status"] = "running"
                    state.pop("next_retry_at", None)
                    save(state)
                    continue  # Quota wait does not consume a repair attempt.
                attempt += 1
                continue

            checks_passed = True
            failure_parts = []
            for name, command in checks_for(index):
                check_log = OUT / f"task-{index + 1:02d}-attempt-{attempt}-{name}.log"
                check_code, check_elapsed = run_logged(command, check_log, min(CHECK_TIMEOUT_SECONDS, max(60, int(deadline - time.monotonic()))))
                attempt_record["checks"].append({
                    "name": name, "exit": check_code, "elapsed": check_elapsed,
                    "log": str(check_log.relative_to(ROOT)),
                })
                save(state)
                if check_code != 0:
                    checks_passed = False
                    failure_parts.append(f"{name} exited {check_code}: {tail(check_log, 2200)}")
            expected_report = OUT / f"{index + 1:02d}-report.md"
            if not expected_report.exists():
                checks_passed = False
                failure_parts.append(f"Missing required report {expected_report}")
            if index == 3 and not (OUT / "final-status.json").exists():
                checks_passed = False
                failure_parts.append("Missing final-status.json")
            if checks_passed:
                record["status"] = "checks_passed"
                record["finished_at"] = stamp()
                save(state)
                break
            failure_context = "\n".join(failure_parts)[-5500:]
            attempt += 1

        if record["status"] != "checks_passed":
            record["status"] = "failed"
            record["finished_at"] = stamp()
            state["status"] = "blocked"
            state["blocker"] = failure_context or "Time limit reached during task"
            save(state)
            return 1

    state["status"] = "finished"
    state["finished_at"] = stamp()
    save(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
