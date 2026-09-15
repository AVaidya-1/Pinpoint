$ErrorActionPreference='Stop'
. (Join-Path (Split-Path $PSScriptRoot -Parent) 'run_team.ps1') -LibraryOnly
$OvernightDir=Join-Path $ProjectRoot ('out/hard_stop_tests/'+[guid]::NewGuid().ToString('N'))
$LogDir=Join-Path $OvernightDir 'logs'
New-Item -ItemType Directory $LogDir -Force | Out-Null
$StopFile=Join-Path $OvernightDir 'STOP.txt'
$OwnerQuestionsPath=Join-Path $OvernightDir 'OWNER_QUESTIONS.md'
$RunnerLogPath=Join-Path $OvernightDir 'runner.log'
$DigestPath=Join-Path $OvernightDir 'digest.md'
$DirectorPlanPath=Join-Path $OvernightDir 'director_plan.md'
function Assert($value,$message) { if (-not $value) { throw $message }; Write-Host "PASS: $message" }
Write-Runtime 'BLOCKED' 'Supervisor' 'A worker claims a new scan is required.'
Assert (-not (Test-ShouldStop)) 'Supervisor runtime status cannot create a project stop'
Assert (-not (Test-Path (Join-Path $OvernightDir 'hard-stop.json'))) 'Runtime reporting never grants terminal authority'
Write-TeamJson (Join-Path $OvernightDir 'hard-stop.json') @{status='BLOCKED';role='Worker';reason='Unreviewed claim'}
Assert (-not (Test-ShouldStop)) 'Non-Director hard stop is ignored'
Remove-Item -LiteralPath (Join-Path $OvernightDir 'hard-stop.json')
function Invoke-Codex { return @{Output="DECISION: BLOCKED`nA new scan of the underside is necessary."} }
$r=Invoke-Director @() 'TEST' 'STUCK'
Assert ($r.Status -eq 'BLOCKED' -and (Test-ShouldStop)) 'Director can stop immediately for missing input'
Write-Runtime 'BLOCKED' 'Supervisor' 'Generic final summary'
Assert ((Get-Content (Join-Path $OvernightDir 'hard-stop.json') -Raw) -match 'new scan') 'Original blocker reason is preserved'
$r=Invoke-AgentProcess 'Worker' $WorkerModel 'high' 'Must never dispatch' 'blocked'
Assert ($r.Status -eq 'STOPPED') 'Blocked team cannot call another model'
Remove-Item -LiteralPath (Join-Path $OvernightDir 'hard-stop.json')
function Invoke-Codex { return @{Output="DECISION: DONE`nAll goal evidence checked."} }
$r=Invoke-Director @() 'TEST' 'COMPLETION'
Assert ($r.Status -eq 'DONE' -and (Test-ShouldStop)) 'Confirmed goal completion blocks future dispatch'
Remove-Item -LiteralPath (Join-Path $OvernightDir 'hard-stop.json')
# Queue failures are bounded and tested in test_simple_queue.ps1.
$holdDenied=$false
$incidentPath=Join-Path $OvernightDir 'incident.md'
[IO.File]::WriteAllText($incidentPath,'Synthetic coordinator safety evidence.',[Text.UTF8Encoding]::new($false))
try { Request-Foreman1EmergencyHold -Reason 'Synthetic coordinator safety problem.' -Evidence @($incidentPath) | Out-Null }
catch { $holdDenied=$true }
Assert ($holdDenied -and -not (Test-Path (Join-Path $OvernightDir 'FOREMAN1-HOLD.txt'))) 'Foreman1 cannot hold when no Director quota is recorded'
Write-TeamJson (Join-Path $OvernightDir 'usage-openai.json') @{provider='openai';consecutive_limits=1;reset_source='provider reported';retry_at=[datetimeoffset]::UtcNow.AddMinutes(5).ToString('o');next_check_at=[datetimeoffset]::UtcNow.AddMinutes(5).ToString('o')}
Request-Foreman1EmergencyHold -Reason 'Synthetic coordinator safety problem.' -Evidence @($incidentPath) | Out-Null
Assert ((Test-Foreman1EmergencyHoldAuthorized) -and -not (Test-Path $StopFile)) 'Foreman1 creates a temporary hold without Director STOP authority'
Assert (-not (Test-Path (Join-Path $OvernightDir 'hard-stop.json'))) 'Foreman1 hold cannot create a terminal hard stop'
$script:ResolvingForeman1Hold=$false
Assert (Test-ShouldStop) 'Foreman1 hold checkpoints the active supervisor session at its safe boundary'
$script:ResolvingForeman1Hold=$true
Assert (-not (Test-ShouldStop)) 'Director resolver can operate while the Foreman1 hold remains active'
$script:ResolvingForeman1Hold=$false
Clear-Foreman1EmergencyHold
Assert (-not (Test-Foreman1EmergencyHoldAuthorized)) 'Only the resolver path clears the temporary hold record'
Write-Host '16 hard-stop and hold checks passed; no live models used.'
