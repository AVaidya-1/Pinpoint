# run-tasks.ps1 - Feed task files to opencode agent
#
# Usage: powershell -ExecutionPolicy Bypass -File run-tasks.ps1
#
# Tasks 2+3 run in parallel (backend and frontend are independent).
# All other tasks run sequentially.

$ErrorActionPreference = "Continue"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TaskDir = Join-Path $ProjectDir "tasks"
$LogDir = Join-Path $ProjectDir "out" "task-logs"

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force $LogDir | Out-Null }

function Invoke-Task {
    param(
        [string]$TaskFile,
        [string]$LogFile,
        [switch]$Background
    )
    $taskPath = Join-Path $TaskDir $TaskFile
    if (-not (Test-Path $taskPath)) {
        Write-Host "ERROR: Task file not found: $taskPath" -ForegroundColor Red
        return $null
    }
    $logPath = Join-Path $LogDir $LogFile
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  TASK: $TaskFile" -ForegroundColor Cyan
    Write-Host "  Started: $timestamp" -ForegroundColor Gray
    Write-Host "  Log: $logPath" -ForegroundColor Gray
    Write-Host "========================================" -ForegroundColor Cyan

    $message = "You are building the Pinpoint Visual Evidence app. It is a localhost tool for finding source regions in technical documentation including diagrams, flowcharts, tables, and schematics. Complete ALL steps in the attached task file. Verify every success criterion. Fix any issues you find. Do not skip steps."

    if ($Background) {
        $proc = Start-Process -FilePath "opencode" `
            -ArgumentList "run","--dir",$ProjectDir,"--auto","-f",$taskPath,$message `
            -RedirectStandardOutput $logPath `
            -RedirectStandardError "$logPath.err" `
            -NoNewWindow -PassThru
        Write-Host "  Started in background (PID: $($proc.Id))" -ForegroundColor Yellow
        return $proc
    } else {
        opencode run --dir $ProjectDir --auto -f $taskPath $message 2>&1 | Tee-Object -FilePath $logPath
        $exitCode = $LASTEXITCODE
        $endTime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        if ($exitCode -eq 0) {
            Write-Host "  Finished: $endTime (exit: $exitCode)" -ForegroundColor Green
        } else {
            Write-Host "  Finished: $endTime (exit: $exitCode)" -ForegroundColor Yellow
        }
        return $exitCode
    }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor White
Write-Host "  Pinpoint / Visual Evidence - Task Runner" -ForegroundColor White
Write-Host "  Project: $ProjectDir" -ForegroundColor Gray
Write-Host "  Tasks:   $TaskDir" -ForegroundColor Gray
Write-Host "  Logs:    $LogDir" -ForegroundColor Gray
Write-Host "============================================================" -ForegroundColor White

$startAll = Get-Date

# Phase 1: Setup (must complete first)
Write-Host ""
Write-Host ">>> Phase 1: Environment Setup" -ForegroundColor Magenta
Invoke-Task "01-setup-and-verify.md" "01-setup.log"

# Phase 2: Backend + Frontend in parallel
Write-Host ""
Write-Host ">>> Phase 2: Backend and Frontend (parallel)" -ForegroundColor Magenta

$backendProc = Invoke-Task "02-backend-completion.md" "02-backend.log" -Background
$frontendProc = Invoke-Task "03-frontend-polish.md" "03-frontend.log" -Background

Write-Host ""
Write-Host "  Waiting for parallel tasks to complete..." -ForegroundColor Gray
if ($backendProc) { $backendProc.WaitForExit() }
if ($frontendProc) { $frontendProc.WaitForExit() }
Write-Host "  Both parallel tasks finished." -ForegroundColor Green

# Phase 3: E2E Tests
Write-Host ""
Write-Host ">>> Phase 3: E2E Tests" -ForegroundColor Magenta
Invoke-Task "04-e2e-tests.md" "04-e2e.log"

# Phase 4: API Preflight
Write-Host ""
Write-Host ">>> Phase 4: API Preflight" -ForegroundColor Magenta
Invoke-Task "05-preflight-and-api.md" "05-preflight.log"

# Phase 5: Live Evaluation
Write-Host ""
Write-Host ">>> Phase 5: Live Evaluation" -ForegroundColor Magenta
Invoke-Task "06-live-evaluation.md" "06-evaluation.log"

# Phase 6: README and Cleanup
Write-Host ""
Write-Host ">>> Phase 6: README and Final Cleanup" -ForegroundColor Magenta
Invoke-Task "07-readme-and-cleanup.md" "07-readme.log"

# Summary
$elapsed = (Get-Date) - $startAll
Write-Host ""
Write-Host "============================================================" -ForegroundColor White
Write-Host "  All tasks completed" -ForegroundColor Green
$elapsedStr = $elapsed.ToString('hh\:mm\:ss')
Write-Host "  Total elapsed: $elapsedStr" -ForegroundColor Gray
Write-Host "  Logs in: $LogDir" -ForegroundColor Gray
Write-Host "============================================================" -ForegroundColor White
