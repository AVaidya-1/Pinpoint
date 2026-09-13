$ErrorActionPreference='Stop'
. (Join-Path (Split-Path $PSScriptRoot -Parent) 'team_context.ps1')
. (Join-Path (Split-Path $PSScriptRoot -Parent) 'team_notifications.ps1')
$OvernightDir=Join-Path ([IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $OvernightDir | Out-Null
Write-TeamJson (Join-Path $OvernightDir 'notifications.json') @{enabled=$true;url='https://example.invalid/topic'}
# Reproduce the production upgrade state that made all non-forced sends throw.
Write-TeamJson (Join-Path $OvernightDir 'notification-attempt.json') @{time=(Get-Date).AddDays(-1).ToString('o')}
$script:calls=0
function Invoke-RestMethod {
    param($Uri,$Method,$TimeoutSec,$ContentType,$Headers,$Body)
    $script:calls++
    if ([Text.Encoding]::UTF8.GetString($Body) -match 'DO_NOT_SEND') { throw 'Private detail leaked' }
}
Send-TeamPing 'STARTING' 'Supervisor' 'DO_NOT_SEND'
Send-TeamPing 'STARTING' 'Supervisor'
if ($script:calls -ne 0) { throw 'Routine startup contacted the owner' }
Send-TeamPing 'BLOCKED' 'Supervisor'
if ($script:calls -ne 1) { throw 'Important owner-only state suppressed' }
Send-TeamPing 'RUNNING' 'Worker'
Send-TeamPing 'SUPERVISOR-ERROR' 'Supervisor'
Send-TeamPing 'QUOTA-WAIT' 'Worker'
if ($script:calls -ne 1) { throw 'Routine recovery state contacted the owner' }
Send-TeamPing 'STALLED' 'Director'
if ($script:calls -ne 2) { throw 'Exhausted Director recovery did not contact the owner' }
Write-TeamJson (Join-Path $OvernightDir 'notifications.json') @{enabled=$false;url='https://example.invalid/topic'}
Send-TeamPing 'TEST' -Force
if ($script:calls -ne 2) { throw 'Mute failed' }
Write-Host 'PASS: routine states stay silent, terminal states alert, no heartbeat spam, mute'
