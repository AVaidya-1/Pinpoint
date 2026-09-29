#!/usr/bin/env bash
# run-tasks.sh - Feed task files to opencode agent
#
# Usage: bash run-tasks.sh
#
# Tasks 2+3 run in parallel (backend and frontend are independent).
# All other tasks run sequentially.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
TASK_DIR="$PROJECT_DIR/tasks"
LOG_DIR="$PROJECT_DIR/out/task-logs"

mkdir -p "$LOG_DIR"

# Source env vars (NVIDIA_API_KEY etc.) for opencode provider auth
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

run_task() {
    local task_file="$1"
    local log_file="$2"
    local task_path="$TASK_DIR/$task_file"
    local log_path="$LOG_DIR/$log_file"

    if [ ! -f "$task_path" ]; then
        echo "ERROR: Task file not found: $task_path"
        return 1
    fi

    echo ""
    echo "========================================"
    echo "  TASK: $task_file"
    echo "  Started: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "  Log: $log_path"
    echo "========================================"

    local msg="You are building the Pinpoint Visual Evidence app. It is a localhost tool for finding source regions in technical documentation including diagrams, flowcharts, tables, and schematics. Complete ALL steps in the attached task file. Verify every success criterion. Fix any issues you find. Do not skip steps."

    opencode run -m nvidia/moonshotai/kimi-k3 --dir "$PROJECT_DIR" --auto -f "$task_path" -- "$msg" 2>&1 | tee "$log_path"
    local exit_code=${PIPESTATUS[0]}

    echo "  Finished: $(date '+%Y-%m-%d %H:%M:%S') (exit: $exit_code)"
    return $exit_code
}

run_task_bg() {
    local task_file="$1"
    local log_file="$2"
    local task_path="$TASK_DIR/$task_file"
    local log_path="$LOG_DIR/$log_file"

    if [ ! -f "$task_path" ]; then
        echo "ERROR: Task file not found: $task_path"
        return 1
    fi

    echo ""
    echo "========================================"
    echo "  TASK: $task_file (background)"
    echo "  Started: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "  Log: $log_path"
    echo "========================================"

    local msg="You are building the Pinpoint Visual Evidence app. It is a localhost tool for finding source regions in technical documentation including diagrams, flowcharts, tables, and schematics. Complete ALL steps in the attached task file. Verify every success criterion. Fix any issues you find. Do not skip steps."

    opencode run -m nvidia/moonshotai/kimi-k3 --dir "$PROJECT_DIR" --auto -f "$task_path" -- "$msg" > "$log_path" 2>&1 &
    echo $!
}

echo ""
echo "============================================================"
echo "  Pinpoint / Visual Evidence - Task Runner"
echo "  Project: $PROJECT_DIR"
echo "  Tasks:   $TASK_DIR"
echo "  Logs:    $LOG_DIR"
echo "============================================================"

START_TIME=$(date +%s)

# Phase 1: Setup (must complete first)
echo ""
echo ">>> Phase 1: Environment Setup"
run_task "01-setup-and-verify.md" "01-setup.log" || true

# Phase 2: Backend + Frontend in parallel
echo ""
echo ">>> Phase 2: Backend and Frontend (parallel)"

BACKEND_PID=$(run_task_bg "02-backend-completion.md" "02-backend.log")
FRONTEND_PID=$(run_task_bg "03-frontend-polish.md" "03-frontend.log")

echo "  Backend PID: $BACKEND_PID, Frontend PID: $FRONTEND_PID"
echo "  Waiting for parallel tasks..."

wait $BACKEND_PID 2>/dev/null || true
wait $FRONTEND_PID 2>/dev/null || true
echo "  Both parallel tasks finished."

# Phase 3: E2E Tests
echo ""
echo ">>> Phase 3: E2E Tests"
run_task "04-e2e-tests.md" "04-e2e.log" || true

# Phase 4: API Preflight
echo ""
echo ">>> Phase 4: API Preflight"
run_task "05-preflight-and-api.md" "05-preflight.log" || true

# Phase 5: Live Evaluation
echo ""
echo ">>> Phase 5: Live Evaluation"
run_task "06-live-evaluation.md" "06-evaluation.log" || true

# Phase 6: README and Cleanup
echo ""
echo ">>> Phase 6: README and Final Cleanup"
run_task "07-readme-and-cleanup.md" "07-readme.log" || true

# Summary
END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))
HOURS=$((ELAPSED / 3600))
MINS=$(( (ELAPSED % 3600) / 60 ))
SECS=$((ELAPSED % 60))

echo ""
echo "============================================================"
echo "  All tasks completed"
echo "  Total elapsed: ${HOURS}h ${MINS}m ${SECS}s"
echo "  Logs in: $LOG_DIR"
echo "============================================================"
