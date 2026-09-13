$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
. (Join-Path $repo 'scripts/run_team.ps1') -LibraryOnly
$OvernightDir = Join-Path $repo ('out/usage_tests/' + [guid]::NewGuid().ToString('N'))
$LogDir = Join-Path $OvernightDir 'logs'
New-Item -ItemType Directory $LogDir -Force | Out-Null
$StopFile = Join-Path $OvernightDir 'STOP.txt'
$RunnerLogPath = Join-Path $OvernightDir 'runner.log'
$checks = 0
function Assert($condition, $message) {
    if (-not $condition) { throw $message }
    $script:checks++; Write-Host "PASS: $message"
}
$now = [datetimeoffset]'2026-09-06T12:00:00Z'
Assert ((Get-UsageFailure 'Please implement usage limit handling' 1).Kind -eq 'OTHER') 'Task prose does not trigger cooldown'
Assert ((Get-UsageFailure 'Error: server overloaded' 1).Kind -eq 'TRANSIENT') 'Overload gets short transient retry'
Assert ((Get-UsageFailure 'Error: 401 unauthorized' 1).Kind -eq 'TERMINAL') 'Authentication fails without quota wait'
$f = Get-UsageFailure "Error: 429 rate limit exceeded`nRetry-After: 120" 1 $now
Assert ($f.Reset -eq $now.AddSeconds(120)) 'Retry-After seconds parsed'
$f = Get-UsageFailure "You've hit your usage limit. Try again in 2 hours" 1 $now
Assert ($f.Reset -eq $now.AddHours(2)) 'Relative reset parsed'
$f = Get-UsageFailure "You've hit your session limit · resets 7:40pm (America/New_York)" 1 ([datetimeoffset]'2026-09-07T20:05:00Z')
Assert ($f.Kind -eq 'QUOTA' -and $f.Reset -eq [datetimeoffset]'2026-09-07T23:40:00Z') 'Claude session limit and America/New_York reset are parsed exactly'
$f = Get-UsageFailure 'Error: usage limit; resets at 2026-09-07T12:00:00Z' 1 $now
Assert ($f.Reset -eq $now.AddDays(1)) 'Explicit timezone reset parsed'
$f = Get-UsageFailure 'Error: usage limit; resets at 2pm' 1 $now
Assert ($null -eq $f.Reset) 'Ambiguous local reset remains unknown'
Set-UsageCooldown 'Foreman2' $f 'synthetic.log'
$first = Read-UsageCooldown 'Director'
Assert ($first.provider -eq 'openai' -and $first.reset_source -eq 'reset unknown' -and $null -eq $first.retry_at) 'Shared cooldown never invents a reset'
Assert ($null -eq (Read-UsageCooldown 'Foreman1')) 'Claude cooldown remains independent'
Set-UsageCooldown 'Director' $f 'synthetic.log'
$second = Read-UsageCooldown 'Foreman2'
Assert ($second.consecutive_limits -eq 2 -and $null -eq $second.retry_at) 'Repeated quota errors do not invent later reset times'
. (Join-Path $repo 'scripts/usage_limits.ps1')
Assert ((Read-UsageCooldown 'Director').consecutive_limits -eq 2) 'Reload preserves provider state'
[IO.File]::WriteAllText($StopFile,'unauthorised',[Text.UTF8Encoding]::new($false))
Assert (-not (Test-ShouldStop)) 'Worker or stray stop marker cannot pause the pipeline'
Remove-Item -LiteralPath $StopFile
Request-DirectorPause -Directive PAUSE -Reason 'Synthetic owner pause during provider wait.' | Out-Null
Assert (-not (Wait-UsageCooldown 'Director' 'test')) 'Director pause interrupts persisted cooldown at its current boundary'
Clear-DirectorPause
Clear-UsageCooldown 'Director'
Assert ($null -eq (Read-UsageCooldown 'Foreman2')) 'Success clears shared cooldown'

$shortReset = [datetimeoffset]::UtcNow.AddSeconds(1)
Write-TeamJson (Join-Path $OvernightDir 'usage-anthropic.json') @{provider='anthropic';retry_at=$shortReset.ToString('o');reset_source='provider reported';next_check_at=$shortReset.ToString('o');consecutive_limits=1;evidence='claude-session-limit.log';updated=[datetimeoffset]::UtcNow.ToString('o')}
Assert (Wait-UsageCooldown 'Foreman1' 'planner-B') 'Claude wait returns automatically at the reported reset'
$waitRuntime = Get-Content (Join-Path $OvernightDir 'runtime.json') -Raw | ConvertFrom-Json
Assert ($waitRuntime.status -eq 'QUOTA-WAIT') 'Quota heartbeat retains QUOTA-WAIT status'
Assert (([string]$waitRuntime.action) -match 'Waiting for usage limit reset .* automatic retry scheduled.*planner-B.*\d+s remaining') 'Quota heartbeat shows automatic retry, role action, and countdown'
Clear-UsageCooldown 'Foreman1'

function Get-CodexAccountUsage { return @{available=$true;reset_at=$null} }
Write-TeamJson (Join-Path $OvernightDir 'usage-openai.json') @{provider='openai';retry_at=[datetimeoffset]::UtcNow.AddHours(6).ToString('o');reset_source='estimated backoff';consecutive_limits=3;evidence='mock'}
Assert (Wait-UsageCooldown 'Foreman2' 'obsolete-estimate') 'Real availability overrides legacy future estimate immediately'
Assert ($null -eq (Read-UsageCooldown 'Director')) 'Authoritative availability clears shared wait'

# Real local process: a partial artifact is created before quota; second call
# must see recovery instructions and continue, rather than repeat the write.
$mock = Join-Path $OvernightDir 'fake.py'
@'
import pathlib, sys
prompt = sys.stdin.read()
marker = pathlib.Path(__file__).with_suffix('.marker')
if not marker.exists():
    marker.write_text('partial')
    print('Error: usage limit reached', file=sys.stderr)
    print('Retry-After: 0', file=sys.stderr)
    sys.exit(1)
assert 'RECOVERY:' in prompt
assert marker.read_text() == 'partial'
marker.write_text('complete')
print('RESUMED_OK')
'@ | Set-Content $mock -Encoding UTF8
$WorkerCmd = '"' + (Join-Path $repo '.venv/Scripts/python.exe') + '" "' + $mock + '"'
$r = Invoke-AgentProcess 'Worker' $WorkerModel 'high' 'Complete the synthetic artifact' 'quota-recovery' 1
Assert ($r.Status -eq 'OK' -and $r.Output -match 'RESUMED_OK') 'Quota retry continues partial work in fresh session'
Assert (-not (Test-Path (Join-Path $OvernightDir 'pending-operation.json'))) 'Successful recovery clears pending attempt'
Assert ($null -eq (Read-UsageCooldown 'Worker')) 'Successful recovery clears cooldown'
Write-Host "$checks checks passed. Evidence: $OvernightDir"
