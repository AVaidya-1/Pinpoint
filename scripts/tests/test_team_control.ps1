$ErrorActionPreference='Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$testRoot = Join-Path $repo ('out/team_control_tests/' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
$runtime = @{
    status='SUPERVISOR-ERROR'
    role='Supervisor'
    action='Synthetic stopped supervisor'
    supervisor_pid=2147483000
    updated=(Get-Date).ToString('o')
}
[IO.File]::WriteAllText((Join-Path $testRoot 'runtime.json'), (ConvertTo-Json $runtime), [Text.UTF8Encoding]::new($false))
& (Join-Path $repo 'scripts/team_control.ps1') -Action pause -RuntimeDirectory $testRoot
if (-not (Test-Path (Join-Path $testRoot 'STOP.txt'))) { throw 'ASSERTION FAILED: safe pause did not retain STOP.txt' }
$pause=Get-Content (Join-Path $testRoot 'director-pause.json') -Raw | ConvertFrom-Json
if ($pause.role -ne 'Director' -or $pause.directive -ne 'PAUSE') { throw 'ASSERTION FAILED: pause was not authorized by the Director control plane' }
$messages=@(Get-ChildItem (Join-Path $testRoot 'memory/messages') -Filter '*.json' | ForEach-Object { Get-Content $_.FullName -Raw | ConvertFrom-Json })
if (-not ($messages | Where-Object { $_.from -eq 'Owner' -and $_.to -eq 'Director' })) { throw 'ASSERTION FAILED: owner pause request was not persisted' }
if (-not ($messages | Where-Object { $_.from -eq 'Director' -and $_.to -eq 'Supervisor' })) { throw 'ASSERTION FAILED: Director pause decision was not persisted' }
Write-Host "PASS: ended supervisor errors permit a safe pause when no work remains. Artifacts: $testRoot"
$tokens=$null
$parseErrors=$null
[Management.Automation.Language.Parser]::ParseFile((Join-Path $repo 'scripts/supervisor_repair.ps1'),[ref]$tokens,[ref]$parseErrors) | Out-Null
if ($parseErrors.Count) { throw "ASSERTION FAILED: supervisor repair script does not parse: $($parseErrors[0])" }
$controlSource=Get-Content (Join-Path $repo 'scripts/team_control.ps1') -Raw
$repairSource=Get-Content (Join-Path $repo 'scripts/supervisor_repair.ps1') -Raw
if ($controlSource -notmatch 'supervisor_repair\.ps1' -or $controlSource -notmatch 'DIRECTOR-RECOVERY-WAIT' -or $controlSource -notmatch 'Test-Foreman1EmergencyHoldAuthorized' -or $repairSource -notmatch "Invoke-AgentProcess 'Director'") {
    throw 'ASSERTION FAILED: resume does not contain persistent automatic Director maintenance recovery'
}
Write-Host 'PASS: resume includes a parseable, persistent Director maintenance path.'
