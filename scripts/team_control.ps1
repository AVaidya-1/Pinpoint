[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('status','pause','resume','phone-setup','phone-test','phone-off')][string]$Action,
    [ValidateRange(1,1440)][int]$WaitMinutes=240,
    [string]$RuntimeDirectory = ''
)
$ErrorActionPreference='Stop'
if (-not $RuntimeDirectory) { $RuntimeDirectory = Join-Path (Split-Path $PSScriptRoot -Parent) 'out/orchestration/runtime' }
$OvernightDir=$RuntimeDirectory
New-Item -ItemType Directory -Path $OvernightDir -Force | Out-Null
. (Join-Path $PSScriptRoot 'team_context.ps1')
. (Join-Path $PSScriptRoot 'director_control.ps1')
. (Join-Path $PSScriptRoot 'usage_limits.ps1')
. (Join-Path $PSScriptRoot 'team_notifications.ps1')
function Test-TeamIdle {
    $lock=$null
    try { $lock=[IO.File]::Open((Join-Path $OvernightDir 'runner.lock'),'OpenOrCreate','ReadWrite','None'); return $true }
    catch [IO.IOException] { return $false }
    finally { if ($lock) { $lock.Dispose() } }
}
switch ($Action) {
    'status' { & (Join-Path $PSScriptRoot 'overnight_status.ps1') -RuntimeDirectory $OvernightDir }
    'phone-setup' {
        $path=Join-Path $OvernightDir 'notifications.json'
        if (Test-Path $path) { $config=Get-Content $path -Raw | ConvertFrom-Json; $config.enabled=$true }
        else { $config=@{enabled=$true;url=('https://ntfy.sh/agent-orchestration-'+[guid]::NewGuid().ToString('N'))} }
        Write-TeamJson $path $config
        Write-Host "Install ntfy on your phone. Add a subscription using this topic:"
        Write-Host (($config.url -split '/')[-1])
        Write-Host 'Server: https://ntfy.sh . Keep this random topic private. Then run phone-test.'
    }
    'phone-test' { Send-TeamPing 'TEST' -Force; Write-Host 'Test attempted. Check your phone; delivery failures are in notification-errors.log.' }
    'phone-off' {
        $path=Join-Path $OvernightDir 'notifications.json'
        if (Test-Path $path) { $config=Get-Content $path -Raw | ConvertFrom-Json; $config.enabled=$false; Write-TeamJson $path $config }
        Write-Host 'Phone notifications disabled.'
    }
    'pause' {
        Request-DirectorPause -Directive PAUSE -Reason 'Owner requested a safe pause. Finish the active bounded operation, checkpoint it, and prevent the next dispatch.' | Out-Null
        Write-Host 'Director accepted the pause. Keep the laptop awake while the current bounded operation checkpoints...'
        $deadline=(Get-Date).AddMinutes($WaitMinutes)
        while ($true) {
            $idle=Test-TeamIdle
            $runtimePath=Join-Path $OvernightDir 'runtime.json'
            $runtime=$null
            if (Test-Path $runtimePath) { $runtime=Get-Content $runtimePath -Raw | ConvertFrom-Json }
            $recordedAlive=$false
            if ($runtime -and $runtime.supervisor_pid -and [int]$runtime.supervisor_pid -ne $PID) {
                $recordedAlive = $null -ne (Get-Process -Id ([int]$runtime.supervisor_pid) -ErrorAction SilentlyContinue)
            }
            $pendingPath=Join-Path $OvernightDir 'pending-operation.json'
            $pendingAlive=$false
            if (Test-Path -LiteralPath $pendingPath) {
                try {
                    $pending=Get-Content -LiteralPath $pendingPath -Raw | ConvertFrom-Json
                    if ($pending.PSObject.Properties['process_id'] -and [int]$pending.process_id -gt 0) {
                        $pendingAlive=$null -ne (Get-Process -Id ([int]$pending.process_id) -ErrorAction SilentlyContinue)
                    }
                }
                catch { $pendingAlive=$true }
                if ($idle -and -not $recordedAlive -and -not $pendingAlive) {
                    $archive=Join-Path $OvernightDir ("logs/interrupted-operation-" + (Get-Date -Format 'yyyyMMddHHmmssfff') + '.json')
                    Move-Item -LiteralPath $pendingPath -Destination $archive
                    Send-TeamMessage 'Director' 'Supervisor' 'SAFE-PAUSE' 'DECISION' 'Archived an inactive pending-operation record during safe pause.' @($archive) | Out-Null
                }
            }
            if ($idle -and -not $recordedAlive -and -not $pendingAlive -and -not (Test-Path -LiteralPath $pendingPath)) { break }
            if ((Get-Date) -ge $deadline) { throw 'Still working. NOT confirmed safe to shut down. Run pause again to keep waiting.' }
            Start-Sleep -Seconds 2
        }
        if (Test-Path $runtimePath) {
            $runtime=Get-Content $runtimePath -Raw | ConvertFrom-Json
            if ($runtime.status -notin @('STOPPED','DONE','BLOCKED','STALLED','MEMORY-PENDING','READY','COMPLETE','ROUND-LIMIT')) {
                Write-Warning "The supervisor ended in $($runtime.status); no lock, live recorded PID, or pending operation remains."
            }
        }
        if (-not (Test-DirectorPauseAuthorized)) { throw 'Director pause authorization is missing. Shutdown safety is NOT confirmed.' }
        Write-Host 'SAFE TO SHUT DOWN: the Director paused dispatch, the supervisor is idle, and the current work is checkpointed.' -ForegroundColor Green
    }
    'resume' {
        if (Test-DirectorTerminalAuthorized) { throw 'Director hard stop is active. Resolve the recorded blocker or define a new goal with the Director. Ordinary resume cannot clear this stop.' }
        if (-not (Test-TeamIdle)) { throw 'The team is already running.' }
        if ($OvernightDir -ne (Join-Path (Split-Path $PSScriptRoot -Parent) 'out/orchestration/runtime')) { throw 'Custom runtime resume is not supported.' }
        & git -C (Split-Path $PSScriptRoot -Parent) status --porcelain --untracked-files=normal | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Git check failed. Repair Git before starting.' }
        $changes=@(& git -C (Split-Path $PSScriptRoot -Parent) status --porcelain --untracked-files=normal)
        if ($changes.Count) {
            & (Join-Path (Split-Path $PSScriptRoot -Parent) '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'team_git.py') checkpoint --label 'Preserved work before autonomous resume'
            if ($LASTEXITCODE -ne 0) { throw 'Could not preserve the existing work; see the specific Git checkpoint error.' }
        }
        Clear-DirectorPause
        $runtimePath=Join-Path $OvernightDir 'runtime.json'
        $runtime=$null
        if (Test-Path $runtimePath) { $runtime=Get-Content $runtimePath -Raw -Encoding UTF8 | ConvertFrom-Json }
        $runSupervisor = -not ($runtime -and $runtime.status -in @('SUPERVISOR-ERROR','REPAIR-ERROR'))
        $repairAttempt = 0
        if (-not $runSupervisor -and (Test-Path (Join-Path $OvernightDir 'supervisor-repair.json'))) {
            $repairRecord=Get-Content (Join-Path $OvernightDir 'supervisor-repair.json') -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($runtime.status -eq 'REPAIR-ERROR' -and $repairRecord.PSObject.Properties['attempt']) {
                $repairAttempt=[int]$repairRecord.attempt
            }
        }
        while ($true) {
            if ($runSupervisor) {
                # A production resume has no wall-clock stop. Individual agent calls
                # remain bounded; the supervisor exits only for the owner's pause,
                # verified completion, an owner-only blocker, or exhausted recovery.
                $executionPath=Join-Path $OvernightDir 'resume-execution.json'
                if (Test-Path -LiteralPath $executionPath) {
                    $execution=Get-Content -LiteralPath $executionPath -Raw -Encoding UTF8 | ConvertFrom-Json
                    if ($execution.mode -ne 'execute-existing-plan') { throw 'Unsupported resume execution mode.' }
                    $manifest=[string]$execution.manifest
                    if ($manifest -notmatch '^docs/tasks/round-[0-9]+/manifest\.json$') { throw 'Resume manifest path is not an approved round manifest.' }
                    $manifestPath=[IO.Path]::GetFullPath((Join-Path (Split-Path $PSScriptRoot -Parent) $manifest))
                    $projectPath=[IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent))
                    if (-not $manifestPath.StartsWith($projectPath + [IO.Path]::DirectorySeparatorChar) -or -not (Test-Path -LiteralPath $manifestPath)) { throw 'Resume manifest is missing or outside the project.' }
                    $maxRounds=[int]$execution.max_rounds
                    if ($maxRounds -lt 1 -or $maxRounds -gt 3) { throw 'Resume follow-up round count must be between 1 and 3.' }
                    $archive=Join-Path $OvernightDir ("logs/resume-execution-" + (Get-Date -Format 'yyyyMMddHHmmssfff') + '.json')
                    Move-Item -LiteralPath $executionPath -Destination $archive
                    & (Join-Path $PSScriptRoot 'run_team.ps1') -Manifest $manifest -EnableRoundLoop -MaxRounds $maxRounds -MaxHours 0 -ForceDirectorReview
                }
                else {
                    & (Join-Path $PSScriptRoot 'run_team.ps1') -PlanFirst -MaxRounds 0 -MaxHours 0
                }
                $runtime=$null
                if (Test-Path $runtimePath) { $runtime=Get-Content $runtimePath -Raw -Encoding UTF8 | ConvertFrom-Json }
                if ((Test-Foreman1EmergencyHoldAuthorized) -and -not (Test-DirectorPauseAuthorized) -and -not (Test-DirectorTerminalAuthorized)) {
                    # Restart into a Director-only resolver. A quota-limited
                    # Director waits in place, then releases or converts the hold.
                    $runSupervisor=$true
                    continue
                }
                if (-not $runtime -or $runtime.status -ne 'SUPERVISOR-ERROR') { break }
                $repairAttempt=0
            }
            if ($repairAttempt -ge 2) {
                $reason='Director maintenance retries remain active for the coordinator fault; no worker or supervisor may convert this incident into a project stop.'
                Write-TeamJson $runtimePath @{status='DIRECTOR-RECOVERY-WAIT';role='Director';action=$reason;log_file='';supervisor_pid=$PID;run_started=(Get-Date).ToString('o');updated=(Get-Date).ToString('o')}
                for ($wait=0; $wait -lt 60; $wait++) {
                    if (Test-DirectorPauseAuthorized) { break }
                    Start-Sleep -Seconds 1
                }
                if (Test-DirectorPauseAuthorized) {
                    Write-TeamJson $runtimePath @{status='STOPPED';role='Director';action='Director honored owner pause during maintenance recovery.';log_file='';supervisor_pid=$PID;run_started=(Get-Date).ToString('o');updated=(Get-Date).ToString('o')}
                    break
                }
                $repairAttempt=0
                continue
            }
            $repairAttempt++
            Write-Host "Routine supervisor fault detected. Starting Director repair attempt $repairAttempt..."
            & (Join-Path $PSScriptRoot 'supervisor_repair.ps1') -RuntimeDirectory $OvernightDir -Attempt $repairAttempt
            if ($LASTEXITCODE -eq 0) {
                $runSupervisor=$true
            }
            else {
                # A failed repair is still a routine incident until the Director's
                # second bounded attempt has also failed.
                $runSupervisor=$false
            }
        }
    }
}
