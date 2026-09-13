$ErrorActionPreference='Stop'
$repo=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$testRoot=Join-Path $repo ('out/director_console_tests/' + [Guid]::NewGuid().ToString('N'))
$messageDir=Join-Path $testRoot 'memory/messages'
$bin=Join-Path $testRoot 'bin'
New-Item -ItemType Directory -Path $messageDir,$bin,(Join-Path $testRoot 'logs') -Force | Out-Null
$messageId=(Get-Date -Format 'yyyyMMddHHmmssfff') + '_' + [Guid]::NewGuid().ToString('N')
$message=@{id=$messageId;from='Owner';to='Director';task='OWNER-CONSOLE';kind='QUESTION';body='What is active?';evidence=@();reply_to='';created=(Get-Date).ToString('o')}
$message | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $messageDir "$messageId.json") -Encoding UTF8
$runtimePath=Join-Path $testRoot 'runtime.json'
$runtimeText=(@{status='RUNNING';role='Worker';action='synthetic active task';supervisor_pid=1234;run_started=(Get-Date).ToString('o');updated=(Get-Date).ToString('o')} | ConvertTo-Json)
[IO.File]::WriteAllText($runtimePath,$runtimeText,[Text.UTF8Encoding]::new($false))
$mock=Join-Path $testRoot 'fake_codex.py'
@'
import pathlib, sys
assert '--sandbox' in sys.argv and 'read-only' in sys.argv, repr(sys.argv)
assert '--approve-for-me' not in sys.argv, repr(sys.argv)
i=sys.argv.index('--output-last-message')
marker=pathlib.Path(__file__).with_suffix('.marker')
if not marker.exists():
    marker.write_text('quota-seen')
    print('Error: rate limit exceeded', file=sys.stderr)
    print('Retry-After: 0', file=sys.stderr)
    sys.stdin.read()
    raise SystemExit(1)
pathlib.Path(sys.argv[i+1]).write_text('The worker is active. Your question did not stop it.')
print("WARN: harmless diagnostic on stderr", file=sys.stderr)
sys.stdin.read()
'@ | Set-Content $mock -Encoding UTF8
$python=Join-Path $repo '.venv/Scripts/python.exe'
"@echo off`r`n`"$python`" `"$mock`" %*" | Set-Content (Join-Path $bin 'codex.cmd') -Encoding ASCII
$oldPath=$env:PATH
$runnerLock=$null
try {
    $env:PATH="$bin;$oldPath"
    $runnerLock=[IO.File]::Open((Join-Path $testRoot 'runner.lock'),'OpenOrCreate','ReadWrite','None')
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repo 'scripts/director_console.ps1') -RuntimeDirectory $testRoot -MessageId $messageId
    if ($LASTEXITCODE -ne 0) { throw 'Director console process failed.' }
}
finally {
    if ($runnerLock) { $runnerLock.Dispose() }
    $env:PATH=$oldPath
}
$console=Get-Content (Join-Path $testRoot 'director-console.json') -Raw | ConvertFrom-Json
if ($console.status -ne 'REPLIED') { throw "Director did not reply while runner.lock was held: $($console.error)" }
if ([IO.File]::ReadAllText($runtimePath) -ne $runtimeText) { throw 'Director console replaced the active supervisor runtime.' }
$replies=@(Get-ChildItem $messageDir -Filter '*.json' | Where-Object { $_.BaseName -ne $messageId })
if ($replies.Count -ne 1) { throw 'Director reply was not persisted exactly once.' }
if (-not (Test-Path ([IO.Path]::ChangeExtension($mock,'.marker')))) { throw 'Director console did not exercise the provider wait path.' }
Write-Host "PASS: Director waits through quota, tolerates stderr warnings, answers while runner.lock is held, and preserves runtime. Artifacts: $testRoot"
