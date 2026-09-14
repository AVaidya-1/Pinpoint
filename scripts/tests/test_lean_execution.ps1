$ErrorActionPreference='Stop'
$repo=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
. "$repo/scripts/run_team.ps1" -LibraryOnly
$OvernightDir=Join-Path $repo ('out/lean_tests/'+[guid]::NewGuid().ToString('N'))
$LogDir=Join-Path $OvernightDir 'logs'
New-Item -ItemType Directory $LogDir -Force | Out-Null
$RunnerLogPath=Join-Path $OvernightDir 'runner.log'
function Assert($value,$message) { if (-not $value) {throw $message}; Write-Host "PASS: $message" }
$script:workerCalls=0
$script:reviewCalls=0
function Invoke-WorkerWithRetry { $script:workerCalls++; return @{Status='OK';Attempt=1;LogFile='worker.log'} }
function Test-Gates { return @{Pass=$true} }
function Invoke-AgentProcess { return @{Status='OK';Output="Progress commentary`nVERDICT: PASS`n- Focused tests pass."} }
function Add-Handoff {}
$task=@{Name='SLICE';Doc='docs/tasks/initial/TASK_IMPORT_VIEWER_SLICE.md';GateFiles=@('out/orchestration/report.json')}
$review=Invoke-Foreman1Review $task 0 ''
Assert ($review.Verdict -eq 'PASS') 'Progress before an unambiguous verdict is accepted'
function Invoke-Foreman1Review { $script:reviewCalls++; return @{Verdict='PASS';TopReason='';ReviewFile='review.md';FullReview='VERDICT: PASS'} }
function Invoke-Foreman2Verify { throw 'Unnecessary second review was dispatched' }
$result=Execute-Task $task 'lean' ''
Assert ($result.Status -eq 'PASS' -and $script:workerCalls -eq 1 -and $script:reviewCalls -eq 1) 'Worker runs once and passes after exactly one review'
function Get-ContextReviewBundle {throw 'Memory candidate is missing'}
function Invoke-Codex {throw 'Plan approval called a model'}
$result=Invoke-PlanReview 'docs/tasks/initial' 'docs/tasks/initial' 0 ''
Assert ($result.Verdict -eq 'APPROVE') 'Missing memory cannot block a structurally valid plan'
function Test-Gates {return @{Pass=$false;Escalate=$false;Reason='Missing evidence';Missing=@('report')}}
$result=Execute-Task $task 'lean' ''
Assert ($result.Status -eq 'GATE-FAIL') 'Actual machine gate failures still stop task acceptance'
function Test-Gates {return @{Pass=$true}}
function Invoke-Foreman1Review { $script:reviewCalls++; return @{Verdict='FAIL';TopReason='Broken feature';ReviewFile='review.md';FullReview='VERDICT: FAIL'} }
$script:workerCalls=0
$result=Execute-Task $task 'lean' ''
Assert ($result.Status -eq 'FAIL' -and $script:workerCalls -eq 2) 'Task repair stops after one revision'
Write-Host 'Lean control-flow tests passed.'
# Direct Director dispatch must create an executable signal without F1/F2 calls.
$CompletionReportPath=Join-Path $OvernightDir 'COMPLETION_REPORT.md'
$OwnerQuestionsPath=Join-Path $OvernightDir 'OWNER_QUESTIONS.md'
$DirectorRequestPath=Join-Path $OvernightDir 'director_request.md'
$NextRoundFile=Join-Path $OvernightDir 'next_round.txt'
function Archive-PlannerSignals {}
function Initialize-TeamContext {}
function Invoke-AgentProcess {
    param($Role,$Model,$Effort,$Prompt,$Label,$TimeoutMin)
    if ($Role -ne 'Director' -or $Prompt -notmatch 'DIRECTOR TAKEOVER') {throw 'Director did not take task authorship'}
    Set-Content $NextRoundFile 'docs/tasks/initial/manifest.json'
    return @{Status='OK';Output='Task authored'}
}
$result=Invoke-Planner 'initial' 'docs/tasks/initial' 'Fix stalled planning' '' -DirectorOwned
Assert ($result.Status -eq 'CONTINUE') 'Director authors the next task directly after an impasse'
