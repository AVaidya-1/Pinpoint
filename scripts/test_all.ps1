[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$output=Join-Path $root 'out/tests'
New-Item -ItemType Directory -Path $output -Force | Out-Null
$failures=@()
foreach ($name in @('test_team_context.ps1','test_team_notifications.ps1','test_usage_limits.ps1','test_director_console.ps1','test_orchestration.ps1','test_team_control.ps1','test_hard_stops.ps1')) {
    $log=Join-Path $output "$name.log"
    $ErrorActionPreference='Continue'
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "tests/$name") *> $log
    $ErrorActionPreference='Stop'
    if ($LASTEXITCODE -ne 0) { $failures += $name; Get-Content $log -Tail 15 }
    else { Write-Host "PASS $name" }
}
$python=Join-Path $root '.venv/Scripts/python.exe'
foreach ($name in @('test_team_git.py','test_team_dashboard.py','test_config.py','test_team_app.py')) {
    $ErrorActionPreference='Continue'
    & $python (Join-Path $PSScriptRoot "tests/$name")
    $ErrorActionPreference='Stop'
    if ($LASTEXITCODE -ne 0) { $failures += $name }
}
& $python -c "import runpy; n=runpy.run_path(r'$PSScriptRoot/tests/test_codex_usage.py'); tests=[v for k,v in n.items() if k.startswith('test_')]; [t() for t in tests]; print('PASS codex_usage:',len(tests),'checks')"
if ($LASTEXITCODE -ne 0) { $failures += 'test_codex_usage.py' }
if ($failures.Count) { throw "Failed suites: $($failures -join ', ')" }
Write-Host 'All offline suites passed. Live providers were not invoked.'
