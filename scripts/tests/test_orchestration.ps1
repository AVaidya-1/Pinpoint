# No live models or product runs. Execute with Windows PowerShell 5.1.
$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
. (Join-Path $repo 'scripts/run_team.ps1') -LibraryOnly
$testRoot = Join-Path $repo ('out/orchestration_tests/' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
$OvernightDir = $testRoot
$LogDir = Join-Path $testRoot 'logs'
New-Item -ItemType Directory -Path $LogDir | Out-Null
$DigestPath = Join-Path $testRoot 'digest.md'
$RunnerLogPath = Join-Path $testRoot 'runner.log'
$StatePath = Join-Path $testRoot 'state.json'
$StopFile = Join-Path $testRoot 'STOP.txt'
$DirectorPlanPath = Join-Path $testRoot 'director_plan.md'
$NextRoundFile = Join-Path $testRoot 'next_round.txt'
$CompletionReportPath = Join-Path $testRoot 'COMPLETION_REPORT.md'
$OwnerQuestionsPath = Join-Path $testRoot 'OWNER_QUESTIONS.md'
$DirectorRequestPath = Join-Path $testRoot 'director_request.md'
$checks = 0
function Assert($Condition, $Message) {
    if (-not $Condition) { throw "ASSERTION FAILED: $Message" }
    $script:checks++
    Write-Host "PASS: $Message"
}

# The real process boundary: a fake CLI validates argv quoting and stdin.
$mock = Join-Path $testRoot 'fake.py'
@'
import sys, pathlib, time
prompt = sys.stdin.read()
if 'MOCK_TIMEOUT' in prompt:
    time.sleep(30)
if 'MOCK_ERROR' in prompt:
    print('synthetic failure', file=sys.stderr)
    sys.exit(3)
if 'MOCK_EMPTY' in prompt:
    sys.exit(0)
if '--output-last-message' in sys.argv:
    i = sys.argv.index('--output-last-message')
    assert 'model_reasoning_effort="low"' in sys.argv, repr(sys.argv)
    assert '--approve-for-me' in sys.argv, repr(sys.argv)
    assert '--sandbox' not in sys.argv, repr(sys.argv)
    pathlib.Path(sys.argv[i+1]).write_text('DECISION: CONTINUE\n- Mock direction.')
else:
    print('MOCK_OK')
'@ | Set-Content $mock -Encoding UTF8
$python = Join-Path $repo '.venv/Scripts/python.exe'
$WorkerCmd = "`"$python`" `"$mock`""
$r = Invoke-AgentProcess 'Worker' $WorkerModel 'high' 'MOCK_OK' 'transport-success' 1
Assert ($r.Status -eq 'OK' -and $r.Output -match 'MOCK_OK') 'Worker receives piped prompt and exits successfully'
$r = Invoke-AgentProcess 'Worker' $WorkerModel 'high' 'MOCK_EMPTY' 'transport-empty' 1
Assert ($r.Status -eq 'ERROR') 'Empty success is rejected after bounded retry'
$r = Invoke-AgentProcess 'Worker' $WorkerModel 'high' 'MOCK_ERROR' 'transport-error' 1
Assert ($r.Status -eq 'ERROR' -and $r.ExitCode -eq 3) 'Nonzero process exit is preserved'
$r = Invoke-AgentProcess 'Worker' $WorkerModel 'high' 'MOCK_TIMEOUT' 'transport-timeout' 0.02
Assert ($r.Status -eq 'TIMEOUT') 'Timeout terminates the launched process tree'
Request-DirectorPause -Directive PAUSE -Reason 'Synthetic owner pause before another agent call.' | Out-Null
$r = Invoke-AgentProcess 'Worker' $WorkerModel 'high' 'MOCK_OK' 'transport-stop' 1
Assert ($r.Status -eq 'STOPPED') 'Director pause prevents another agent call'
Assert (-not (Wait-QuotaWindow 'Worker' 'mock-quota')) 'Quota wait responds to Director pause request'
Clear-DirectorPause
$originalPath = $env:PATH
try {
    "@echo off`r`n`"$python`" `"$mock`" %*" | Set-Content (Join-Path $testRoot 'codex.cmd') -Encoding ASCII
    $env:PATH = "$testRoot;$originalPath"
    $r = Invoke-AgentProcess 'Director' $DirectorModel 'low' 'MOCK_OK' 'codex-quoting' 1
    Assert ($r.Status -eq 'OK' -and $r.Output -match 'DECISION: CONTINUE') 'Codex effort argument and output-last-message survive cmd quoting'
} finally { $env:PATH = $originalPath }
$runtime = Get-Content (Join-Path $testRoot 'runtime.json') -Raw | ConvertFrom-Json
Assert ($runtime.role -eq 'Director') 'Dashboard receives the actual role'
$writeArgs=@(Get-CodexExecArguments -Model 'gpt-6-astra' -Effort 'high' -ProjectDirectory $repo -FinalFile (Join-Path $testRoot 'write.md'))
$readArgs=@(Get-CodexExecArguments -Model 'gpt-5.6-sol' -Effort 'high' -ProjectDirectory $repo -FinalFile (Join-Path $testRoot 'read.md') -ReadOnly)
Assert ($writeArgs -contains '--approve-for-me' -and $writeArgs -notcontains '--sandbox') 'Automatic Codex mode never combines approve-for-me with sandbox'
Assert ($readArgs -contains '--sandbox' -and $readArgs -contains 'read-only' -and $readArgs -notcontains '--approve-for-me') 'Read-only Codex review uses the explicit sandbox without automatic approval mode'
$f1Prompt=Get-CommunicationPrompt -Role 'Foreman1' -Label 'hold-authority-check'
$workerPrompt=Get-CommunicationPrompt -Role 'Worker' -Label 'hold-authority-check'
Assert ($f1Prompt -notmatch 'foreman1_hold\.ps1' -and $workerPrompt -notmatch 'foreman1_hold\.ps1') 'Simple role prompts omit emergency-hold bureaucracy'
$repairSource=Get-Content (Join-Path $repo 'scripts/supervisor_repair.ps1') -Raw
$controlSource=Get-Content (Join-Path $repo 'scripts/team_control.ps1') -Raw
Assert ($repairSource -notmatch '--sandbox\s+workspace-write\s+--approve-for-me') 'Supervisor repair source cannot recreate the rejected Codex flag combination'
Assert ($controlSource -match "run_team\.ps1'\) -MaxHours 0") 'Production resume invokes the durable queue'
Assert ((Get-Content (Join-Path $testRoot 'communications.md') -Raw) -match 'Supervisor -> Worker') 'Shared ledger records handoffs'
Assert ((@(Get-ChildItem $LogDir -Filter '*.prompt.txt')).Count -eq 7) 'Retries retain separate prompt logs'
Assert (Test-ContainedPath (Join-Path $ArtifactRoot 'new/evaluation.json') $ArtifactRoot) 'Valid gate stays within the output directory'
Assert (-not (Test-ContainedPath (Join-Path $ArtifactRoot '../prior/evaluation.json') $ArtifactRoot)) 'Traversal cannot escape the gate output directory'
$gateFile = Join-Path $testRoot 'gate.txt'
Set-Content $gateFile 'first'
$initialTaskDoc = (Load-Manifest (Join-Path $repo 'docs/tasks/initial/manifest.json')).Tasks[0].Doc
$resumeTask = @{Name='resume'; Doc=$initialTaskDoc; GateFiles=@($gateFile)}
Save-TaskState 'resume' 'test' 'PASS' 'PASS' $resumeTask
Assert (Test-TaskPassed 'resume' 'test' $resumeTask) 'Unchanged task and artifacts can resume from PASS'
Set-Content $gateFile 'changed'
Assert (-not (Test-TaskPassed 'resume' 'test' $resumeTask)) 'Changed evidence invalidates a saved PASS'
Assert ($null -eq (Find-GateFile (Join-Path $testRoot 'missing/gate.txt'))) 'A same-named artifact elsewhere cannot satisfy a missing gate'

# Planner manifests may use either the original dotted-path schema or JSON Pointer + expect.
$pointerManifest = Load-Manifest (Join-Path $repo 'docs/tasks/initial/manifest.json')
$pointerErrors = Validate-Manifest $pointerManifest
Assert ($pointerErrors.Count -eq 0 -and $pointerManifest.Tasks[0].JsonGates[0].Mode -eq 'Expected') 'Planner JSON Pointer gates load and validate without a supervisor exception'
$jsonGateFile = Join-Path $testRoot 'pointer-gate.json'
'{"json_gates":{"oq1_resolved":true}}' | Set-Content $jsonGateFile -Encoding UTF8
$pointerTask = @{GateFiles=@(); JsonGates=@(@{File=$jsonGateFile;Mode='Expected';JsonPointer='/json_gates/oq1_resolved';Expected=$true})}
Assert ((Test-Gates $pointerTask).Pass) 'JSON Pointer expected-value gate passes on the expected value'
$pointerTask.JsonGates[0].Expected = $false
Assert (-not (Test-Gates $pointerTask).Pass) 'JSON Pointer expected-value gate fails closed on a mismatch'
$malformedManifest = Join-Path $testRoot 'malformed-manifest.json'
'{"round":"X","tasks":[{"name":"X1","doc":"docs/tasks/initial/TASK_DEMO.md","timeout_min":1,"gate_files":["out/orchestration/x.txt"],"json_gates":[{"file":"out/orchestration/x.json","expect":true}]}]}' | Set-Content $malformedManifest -Encoding UTF8
$malformedErrors = Validate-Manifest (Load-Manifest $malformedManifest)
Assert (($malformedErrors -join '; ') -match 'path \+ escalate_if or pointer \+ expect') 'Malformed JSON gates become review feedback instead of crashing the supervisor'

# Conflicting planner signals are a technical planning incident, not a supervisor crash.
$realAgentProcess = ${function:Invoke-AgentProcess}
function Invoke-AgentProcess {
    Set-Content $DirectorRequestPath 'technical impasse'
    Set-Content $NextRoundFile "STUCK`nout/mock/director_request.md"
    return @{Status='OK';Output='planner finished';LogFile='mock.log';ExitCode=0}
}
$conflict=Invoke-Planner 'mock' 'docs/tasks/initial' '' 'strategy'
Assert ($conflict.Status -eq 'STUCK' -and (Test-Path $conflict.Evidence)) 'Multiple planner signals route to F2 and Director as a preserved technical incident'
${function:Invoke-AgentProcess} = $realAgentProcess

# Planning, batch reviews and resume are covered by test_simple_queue.ps1.
$realDirector = ${function:Invoke-Director}
# Invalid Director output must never replace a useful saved briefing.
${function:Invoke-Director} = $realDirector
function Invoke-Codex { return @{Output=''} }
Set-Content $DirectorPlanPath 'existing strategy'
$rejected = $false
try { Invoke-Director @() 'mock' 'INITIAL' | Out-Null } catch { $rejected = $true }
Assert ($rejected -and (Get-Content $DirectorPlanPath -Raw) -match 'existing strategy') 'Empty Director decision cannot overwrite saved strategy'

& (Join-Path $repo 'scripts/overnight_status.ps1') -RuntimeDirectory $testRoot -OutputLines 2
Write-Host "`n$checks orchestration checks passed. Artifacts: $testRoot"
