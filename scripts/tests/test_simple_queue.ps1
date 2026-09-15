$ErrorActionPreference='Stop'
$repo=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
. "$repo/scripts/run_team.ps1" -LibraryOnly
function Assert($value,$message) { if (-not $value) { throw $message }; Write-Host "PASS: $message" }
$ProjectRoot=Join-Path $repo ('out/queue_tests/'+[guid]::NewGuid().ToString('N'))
$ArtifactRoot=Join-Path $ProjectRoot 'out/orchestration'
$OvernightDir=Join-Path $ArtifactRoot 'runtime'
$LogDir=Join-Path $OvernightDir 'logs'
$StatePath=Join-Path $OvernightDir 'state.json'
$RunnerLogPath=Join-Path $OvernightDir 'runner.log'
$DirectorPlanPath=Join-Path $OvernightDir 'director_plan.md'
$CompletionReportPath=Join-Path $OvernightDir 'COMPLETION_REPORT.md'
New-Item -ItemType Directory $LogDir -Force | Out-Null
New-Item -ItemType Directory (Join-Path $ProjectRoot 'docs/tasks/build') -Force | Out-Null
$script:events=@(); $script:stop=$false; $script:failCheck=$false; $script:badPlan=$false
function Test-ShouldStop { return $script:stop }
function Get-TaskFingerprint { return 'test' }
function Test-Gates {return @{Pass=$true}}
function Invoke-AgentProcess {
    param($Role,$Model,$Effort,$Prompt,$Label,$TimeoutMin)
    $script:events += $Label
    if ($Label -eq 'create-task-queue' -and -not $script:badPlan) {
        $tasks=@()
        foreach ($n in 1..3) {
            $doc="docs/tasks/build/TASK_$n.md"
            Set-Content (Join-Path $ProjectRoot $doc) "Implement task $n"
            $tasks+=@{name="T$n";doc=$doc;timeout_min=30;gate_files=@("out/orchestration/t$n.json");json_gates=@();continue_on_fail=$false}
        }
        Write-TeamJson (Join-Path $ProjectRoot 'docs/tasks/build/manifest.json') @{round='build';tasks=$tasks}
    }
    if ($Label -eq 'queue-progress-check') {
        return @{Status='OK';Output=$(if ($script:failCheck) {"VERDICT: FAIL`n- Broken behavior"} else {"VERDICT: PASS`n- Focused evidence checked"})}
    }
    return @{Status='OK';Output='Done';LogFile='fake.log';ExitCode=0}
}
function Invoke-WorkerWithRetry {
    param($Task,$Revision,$DirectorBriefing)
    $script:events += $Task.Name
    if ($script:stopAfterFirst -and $Task.Name -eq 'T1') { $script:stop=$true }
    return @{Status='OK';Attempt=1;LogFile='fake.log'}
}
$script:stopAfterFirst=$false
Invoke-SimpleQueue 'Build MVP'
Assert (($script:events -join ',') -eq 'create-task-queue,T1,T2,queue-progress-check,T3,queue-progress-check') 'One plan, three sequential workers, checks after two tasks and at the end'
Assert ($script:TerminalStatus -eq 'COMPLETE') 'Queue reaches completion'
$script:events=@()
Set-Content (Join-Path $ProjectRoot 'later-source-change.txt') 'Later task changes'
Invoke-SimpleQueue 'Build MVP'
Assert ($script:events.Count -eq 0) 'Resume does not replan or repeat completed work after source changes'
$queuePath=Join-Path $OvernightDir 'task-queue.json'
$q=Get-Content $queuePath -Raw | ConvertFrom-Json
$q.completed=@(); $q.checked=0; $q.status='BUILDING'; Write-TeamJson $queuePath $q
$script:stopAfterFirst=$true
Invoke-SimpleQueue 'Build MVP'
Assert (($script:events -join ',') -eq 'T1' -and $script:TerminalStatus -eq 'STOPPED') 'Pause saves completed work before dispatching another worker'
$script:stop=$false; $script:stopAfterFirst=$false; $script:events=@()
Invoke-SimpleQueue 'Build MVP'
Assert (($script:events -join ',') -eq 'T2,queue-progress-check,T3,queue-progress-check') 'Resume continues pending batch without another planner'
$q.completed=@('T1','T2'); $q.checked=0; $q.repair_attempts=0; Write-TeamJson $queuePath $q
$script:events=@(); $script:failCheck=$true
Invoke-SimpleQueue 'Build MVP'
Assert (($script:events -join ',') -eq 'queue-progress-check,queue-repair,queue-progress-check' -and $script:TerminalStatus -eq 'FAIL') 'Failed check gets exactly one worker repair and never replans'
$script:events=@(); $script:failCheck=$false; $script:badPlan=$true
Remove-Item -LiteralPath $queuePath
Remove-Item -LiteralPath (Join-Path $ProjectRoot 'docs/tasks/build/manifest.json')
Invoke-SimpleQueue 'Build MVP'
Invoke-SimpleQueue 'Build MVP'
Assert (($script:events -join ',') -eq 'create-task-queue,create-task-queue' -and $script:TerminalStatus -eq 'PLAN-ERROR') 'Malformed planning has one repair total, including across restarts'
