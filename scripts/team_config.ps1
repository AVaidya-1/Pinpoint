# Shared configuration. Provider routing is implemented in orchestration_runtime.ps1.
function Get-TeamConfig {
    $root = Split-Path $PSScriptRoot -Parent
    $value = Get-Content (Join-Path $root 'orchestration.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $value.fingerprint_roots -or @($value.fingerprint_roots).Count -eq 0) { throw 'Configure fingerprint_roots for product source, tests and configuration.' }
    foreach ($role in @('Director','Foreman1','ForemanFallback','Worker')) {
        if ([string]$value.models.$role -notmatch '^[a-zA-Z0-9_./:-]+$') { throw "Invalid configured model for $role" }
    }
    return $value
}
