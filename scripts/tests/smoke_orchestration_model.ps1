param([ValidateSet('Director','Foreman1','Foreman2','Worker')][string]$Role)
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
. (Join-Path $repo 'scripts/run_team.ps1') -LibraryOnly
$OvernightDir = Join-Path $repo ('out/orchestration_smoke/' + $Role + '_' + [Guid]::NewGuid().ToString('N'))
$LogDir = Join-Path $OvernightDir 'logs'
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$RunnerLogPath = Join-Path $OvernightDir 'runner.log'
$StopFile = Join-Path $OvernightDir 'STOP.txt'
$MaxHours = 0.025
$RetryWaitMinutes = 1
$model = $DirectorModel
$effort = 'low'
if ($Role -eq 'Foreman1') { $model=$Foreman1Model; $effort='medium' }
if ($Role -eq 'Foreman2') { $model=$Foreman2Model; $effort='high' }
if ($Role -eq 'Worker') { $model=$WorkerModel; $effort='high' }
# Connectivity only: do not read project files, run tools, or change product state.
function Get-CommunicationPrompt { return 'This is a connection test only. Do not use tools, read files, or edit anything.' }
$result = Invoke-AgentProcess $Role $model $effort 'Respond with exactly READY.' "smoke-$Role" 1
$result | ConvertTo-Json
if ($result.Status -ne 'OK' -or $result.Output -notmatch '\bREADY\b') { exit 1 }
