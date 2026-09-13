[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$RuntimeDirectory,
    [ValidateRange(1,2)][int]$Attempt = 1
)
$ErrorActionPreference='Stop'
$ProjectRoot=Split-Path $PSScriptRoot -Parent
$OvernightDir=[IO.Path]::GetFullPath($RuntimeDirectory)
$LogDir=Join-Path $OvernightDir 'logs'
$RunStart=Get-Date
$MaxHours=0
$WorkerCmd=''
$RunnerLogPath=Join-Path $OvernightDir 'runner.log'
. (Join-Path $PSScriptRoot 'team_context.ps1')
. (Join-Path $PSScriptRoot 'orchestration_runtime.ps1')

function Write-Log([string]$Message) {
    Add-Content -LiteralPath $RunnerLogPath -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message" -Encoding UTF8
}

function Test-ShouldStop {
    return ((Test-DirectorPauseAuthorized) -or (Test-DirectorTerminalAuthorized) -or (Test-Foreman1EmergencyHoldAuthorized))
}

function Write-RepairRuntime([string]$Status,[string]$Action,[string]$LogFile='') {
    Write-TeamJson (Join-Path $OvernightDir 'runtime.json') @{
        status=$Status;role='Director';action=$Action;log_file=$LogFile
        supervisor_pid=$PID;run_started=$RunStart.ToString('o');updated=(Get-Date).ToString('o')
    }
}

function Test-RepairAllowedPath([string]$Path) {
    return $Path -match '^(scripts/(team_[^/]+|director_control\.ps1|supervisor_repair\.ps1|orchestration_runtime\.ps1|run_team\.ps1|usage_limits\.ps1|dashboard/.*|tests/.*)|docs/orchestration/.*|TEAM_COMMANDS\.txt)$'
}

$lock=$null
$recordPath=Join-Path $OvernightDir 'supervisor-repair.json'
$sourceRuntimeText=''
$signature=''
try {
    $lock=[IO.File]::Open((Join-Path $OvernightDir 'runner.lock'),'OpenOrCreate','ReadWrite','None')
    $runtimeText=Get-Content (Join-Path $OvernightDir 'runtime.json') -Raw -Encoding UTF8
    $runtime=$runtimeText | ConvertFrom-Json
    if ($runtime.status -notin @('SUPERVISOR-ERROR','REPAIR-ERROR')) { return }
    $preexisting=@(& git -C $ProjectRoot status --porcelain --untracked-files=normal | ForEach-Object { $_.Substring(3).Replace('\','/') })
    if ($preexisting.Count) {
        $unexpectedPreexisting=@($preexisting | Where-Object { -not (Test-RepairAllowedPath $_) })
        if ($Attempt -le 1 -or $unexpectedPreexisting.Count -or (& git -C $ProjectRoot diff --cached --name-only)) {
            throw 'Repair requires a clean recovery checkpoint; only a later repair may continue allowlisted partial maintenance edits.'
        }
    }
    else {
        & (Join-Path $ProjectRoot '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'team_git.py') check
        if ($LASTEXITCODE -ne 0) { throw 'Repair requires the supervisor recovery checkpoint to leave a clean worktree.' }
    }

    $prior=$null
    if (Test-Path $recordPath) { $prior=Get-Content $recordPath -Raw -Encoding UTF8 | ConvertFrom-Json }
    if ($runtime.status -eq 'REPAIR-ERROR' -and $prior -and $prior.PSObject.Properties['source_runtime']) {
        $sourceRuntimeText=[string]$prior.source_runtime
        $signature=[string]$prior.signature
    }
    else {
        $sourceRuntimeText=$runtimeText
        $signature=Get-TeamFileHash (Join-Path $OvernightDir 'runtime.json')
    }
    if ($prior -and $prior.signature -eq $signature -and [int]$prior.attempt -ge 2 -and $Attempt -le [int]$prior.attempt) {
        throw 'Two bounded repairs already failed for this exact supervisor error.'
    }
    $promptPath=Join-Path $LogDir ("supervisor-repair-$signature-$Attempt.prompt.md")
    $outputPath=Join-Path $LogDir ("supervisor-repair-$signature-$Attempt.out.log")
    $finalPath=Join-Path $LogDir ("supervisor-repair-$signature-$Attempt.final.md")
    $runnerTail=(Get-Content (Join-Path $OvernightDir 'runner.log') -Tail 80) -join "`n"
    $prompt=@"
You are the Director's bounded orchestration-maintenance executor for Agent Orchestration.
The autonomous supervisor stopped on a routine coordinator defect. Diagnose and
repair it without owner input. Reproduce the failure when practical and add a
regression test. Preserve all product gates, model routing, data, and pending
work. You may edit only orchestration infrastructure under scripts/ (team_*,
director_control.ps1, supervisor_repair.ps1, orchestration_runtime.ps1, run_team.ps1,
usage_limits.ps1, dashboard/, tests/) and docs/orchestration or TEAM_COMMANDS.txt.
Do not edit product source, chapter task plans, outputs, credentials,
Git metadata, or commits. Do not restart the team. Finish with a concise summary.

ORIGINAL SUPERVISOR FAILURE:
$sourceRuntimeText

PRIOR REPAIR FAILURE (when present):
$runtimeText

RECENT SUPERVISOR LOG:
$runnerTail
"@
    [IO.File]::WriteAllText($promptPath,$prompt,[Text.UTF8Encoding]::new($true))
    Write-TeamJson $recordPath @{status='RUNNING';signature=$signature;source_runtime=$sourceRuntimeText;attempt=$Attempt;prompt=$promptPath;updated=(Get-Date).ToString('o')}
    Write-RepairRuntime 'REPAIRING' "Director is repairing a routine supervisor fault (attempt $Attempt/2)" $outputPath
    $beforeHead=(& git -C $ProjectRoot rev-parse HEAD).Trim()
    $repairResult=Invoke-AgentProcess 'Director' ([string](Get-TeamConfig).models.Director) 'high' $prompt "supervisor-repair-$signature-$Attempt" 120
    if ($repairResult.Status -ne 'OK') { throw "Director maintenance process failed: $($repairResult.Status); see $($repairResult.LogFile)" }
    [IO.File]::WriteAllText($finalPath,[string]$repairResult.Output,[Text.UTF8Encoding]::new($false))
    $outputPath=$repairResult.LogFile
    if ((& git -C $ProjectRoot rev-parse HEAD).Trim() -ne $beforeHead) { throw 'Maintenance agent changed Git history; automatic acceptance refused.' }
    if (& git -C $ProjectRoot diff --cached --name-only) { throw 'Maintenance agent staged changes; automatic acceptance refused.' }
    $changed=@(& git -C $ProjectRoot status --porcelain --untracked-files=normal | ForEach-Object { $_.Substring(3).Replace('\','/') })
    if (-not $changed.Count) { throw 'Maintenance agent produced no repair.' }
    $unexpected=@($changed | Where-Object { -not (Test-RepairAllowedPath $_) })
    if ($unexpected.Count) { throw "Maintenance changed files outside its allowlist: $($unexpected -join ', ')" }

    $tests=@('test_team_context.ps1','test_team_notifications.ps1','test_usage_limits.ps1','test_director_console.ps1','test_orchestration.ps1')
    foreach ($test in $tests) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "tests/$test") *> (Join-Path $LogDir "supervisor-repair-$signature-$test.log")
        if ($LASTEXITCODE -ne 0) { throw "Repair regression failed: $test" }
    }
    & (Join-Path $ProjectRoot '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'tests/test_team_dashboard.py') *> (Join-Path $LogDir "supervisor-repair-$signature-dashboard.log")
    if ($LASTEXITCODE -ne 0) { throw 'Repair regression failed: test_team_dashboard.py' }

    $reviewPrompt="You are Foreman 2 reviewing an orchestration-only self-repair. Read docs/orchestration/OWNER_BRIEF.md and inspect the complete git diff and untracked files. Reject scope expansion, product changes, weakened gates, missing regression coverage, or a fix that does not address the recorded supervisor error in $($runtime.action). First line exactly VERDICT: APPROVE or VERDICT: REJECT. Do not edit files."
    $reviewPath=Join-Path $LogDir "supervisor-repair-$signature-review.md"
    $reviewResult=Invoke-AgentProcess 'Foreman2' ([string](Get-TeamConfig).models.Foreman2) 'high' $reviewPrompt "supervisor-repair-review-$signature" 60
    if ($reviewResult.Status -eq 'OK') {
        [IO.File]::WriteAllText($reviewPath,[string]$reviewResult.Output,[Text.UTF8Encoding]::new($false))
    }
    if ($reviewResult.Status -ne 'OK' -or $reviewResult.Output -notmatch '\A\s*VERDICT:\s*APPROVE\s*(?:\r?\n|$)') {
        throw 'Foreman 2 rejected or failed to approve the automatic repair.'
    }
    & (Join-Path $ProjectRoot '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'team_git.py') checkpoint --label "Reviewed supervisor self-repair $signature"
    if ($LASTEXITCODE -ne 0) { throw 'Reviewed repair could not be checkpointed.' }
    Write-TeamJson $recordPath @{status='COMPLETE';signature=$signature;source_runtime=$sourceRuntimeText;attempt=$Attempt;review=$reviewPath;updated=(Get-Date).ToString('o')}
    Write-RepairRuntime 'REPAIR-COMPLETE' 'Routine supervisor fault repaired and reviewed; restarting automatically' $finalPath
}
catch {
    Write-TeamJson $recordPath @{status='ERROR';signature=$signature;source_runtime=$sourceRuntimeText;attempt=$Attempt;error=[string]$_;updated=(Get-Date).ToString('o')}
    Write-RepairRuntime 'REPAIR-ERROR' "Automatic supervisor repair failed: $($_.Exception.Message)" ''
    exit 1
}
finally {
    if ($lock) { $lock.Dispose() }
}
