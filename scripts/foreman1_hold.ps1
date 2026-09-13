[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$RuntimeDirectory,
    [Parameter(Mandatory)][string]$ReasonFile
)
$ErrorActionPreference='Stop'
$ProjectRoot=Split-Path $PSScriptRoot -Parent
$OvernightDir=[IO.Path]::GetFullPath($RuntimeDirectory)
$expected=[IO.Path]::GetFullPath((Join-Path $ProjectRoot 'out')).TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar
if (-not ($OvernightDir + [IO.Path]::DirectorySeparatorChar).StartsWith($expected,[StringComparison]::OrdinalIgnoreCase)) {
    throw 'Foreman1 hold runtime must remain under the project output directory.'
}
$reasonPath=[IO.Path]::GetFullPath($ReasonFile)
$runtimePrefix=$OvernightDir.TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar
if (-not $reasonPath.StartsWith($runtimePrefix,[StringComparison]::OrdinalIgnoreCase) -or -not (Test-Path -LiteralPath $reasonPath -PathType Leaf)) {
    throw 'Foreman1 hold evidence must be a file inside the runtime directory.'
}
. (Join-Path $PSScriptRoot 'team_context.ps1')
. (Join-Path $PSScriptRoot 'director_control.ps1')
$reason=Get-Content -LiteralPath $reasonPath -Raw -Encoding UTF8
Request-Foreman1EmergencyHold -Reason $reason -Evidence @($reasonPath) | Out-Null
Write-Host 'FOREMAN1 EMERGENCY HOLD RECORDED: finish the current response; the supervisor will checkpoint and wait for Director review.'
