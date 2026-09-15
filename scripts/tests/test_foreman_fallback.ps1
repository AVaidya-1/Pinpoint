$ErrorActionPreference='Stop'
$repo=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
. "$repo/scripts/run_team.ps1" -LibraryOnly
$OvernightDir=Join-Path $repo ('out/foreman_tests/'+[guid]::NewGuid().ToString('N'))
$LogDir=Join-Path $OvernightDir 'logs'
New-Item -ItemType Directory $LogDir -Force | Out-Null
$StatePath=Join-Path $OvernightDir 'state.json'
$RunnerLogPath=Join-Path $OvernightDir 'runner.log'
$StopFile=Join-Path $OvernightDir 'STOP.txt'
function Assert($v,$m) {if (-not $v) {throw $m}; Write-Host "PASS: $m"}
$python=Join-Path $repo '.venv/Scripts/python.exe'
$fake=Join-Path $OvernightDir 'fake.py'
@"
import sys,pathlib
mode=pathlib.Path(__file__).with_name('mode.txt').read_text().strip()
prompt=sys.stdin.read()
if '--output-last-message' in sys.argv:
    assert 'gpt-5.6-sol' in sys.argv, sys.argv
    assert 'model_reasoning_effort="high"' in sys.argv, sys.argv
    pathlib.Path(sys.argv[sys.argv.index('--output-last-message')+1]).write_text('VERDICT: PASS\\nSol completed the same assignment.')
    print('codex transport')
else:
    assert 'claude-opus-4-6' in sys.argv and 'medium' in sys.argv, sys.argv
    if mode=='quota':
        print('Error: 429 rate limit exceeded. Try again in 1 hour')
        sys.exit(1)
    if mode=='auth':
        print('Error: 401 unauthorized')
        sys.exit(1)
    print('VERDICT: PASS - Opus')
"@ | Set-Content $fake
$oldPath=$env:PATH
try {
    foreach ($cli in @('claude','codex')) { "@echo off`r`n`"$python`" `"$fake`" %*" | Set-Content (Join-Path $OvernightDir "$cli.cmd") -Encoding ASCII }
    $env:PATH="$OvernightDir;$oldPath"
    Set-Content (Join-Path $OvernightDir 'mode.txt') 'ok'
    $r=Invoke-AgentProcess 'Foreman1' $Foreman1Model 'medium' 'Build the assigned slice' 'primary' 1
    Assert ($r.Status -eq 'OK' -and $r.Output -match 'Opus') 'Available Opus runs at medium effort'
    Set-Content (Join-Path $OvernightDir 'mode.txt') 'quota'
    $r=Invoke-AgentProcess 'Foreman1' $Foreman1Model 'medium' 'Build the assigned slice' 'quota-fallback' 1
    Assert ($r.Status -eq 'OK' -and $r.Output -match 'Sol completed') 'Live Opus quota switches the same assignment to Sol high without waiting'
    Assert ((Read-UsageCooldown 'Foreman1').provider -eq 'anthropic') 'Sol success preserves the Anthropic cooldown'
    $route=Resolve-ForemanRoute
    Assert ($route.Model -eq 'gpt-5.6-sol') 'Persisted Opus limit routes subsequent Foreman calls to Sol'
    $r=Invoke-AgentProcess 'Foreman1' $Foreman1Model 'medium' 'Build next slice' 'persisted-fallback' 1
    Assert ($r.Status -eq 'OK' -and $r.Output -match 'Sol completed') 'Persisted cooldown skips the unavailable primary'
    $record=Read-UsageCooldown 'Foreman1';$record.retry_at=[datetimeoffset]::UtcNow.AddSeconds(-1).ToString('o')
    Write-TeamJson (Join-Path $OvernightDir 'usage-anthropic.json') $record
    Set-Content (Join-Path $OvernightDir 'mode.txt') 'ok'
    $r=Invoke-AgentProcess 'Foreman1' $Foreman1Model 'medium' 'Build next slice' 'return-primary' 1
    Assert ($r.Status -eq 'OK' -and $r.Output -match 'Opus') 'Opus is preferred again after reset'
    Set-Content (Join-Path $OvernightDir 'mode.txt') 'auth'
    $r=Invoke-AgentProcess 'Foreman1' $Foreman1Model 'medium' 'Build next slice' 'auth-failure' 1
    Assert ($r.Status -eq 'ERROR') 'Authentication errors do not silently trigger quota fallback'
} finally {$env:PATH=$oldPath}
