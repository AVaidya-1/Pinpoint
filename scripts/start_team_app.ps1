[CmdletBinding()]
param([ValidateRange(1024,65535)][int]$Port=8765)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
try {
    $python=Join-Path $root '.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        $systemPython=Get-Command python.exe -ErrorAction Stop
        $bootstrapLog=Join-Path $root 'out/app-bootstrap.log'
        New-Item -ItemType Directory -Path (Split-Path $bootstrapLog -Parent) -Force | Out-Null
        & $systemPython.Source -m venv (Join-Path $root '.venv') *> $bootstrapLog
        if ($LASTEXITCODE -ne 0) { throw "Python setup failed. See $bootstrapLog" }
    }
    $pythonw=Join-Path $root '.venv/Scripts/pythonw.exe'
    Start-Process -FilePath $pythonw -ArgumentList @('"' + (Join-Path $PSScriptRoot 'team_app.py') + '"','--port',"$Port") -WorkingDirectory $root -WindowStyle Hidden | Out-Null
}
catch {
    Add-Type -AssemblyName System.Windows.Forms
    [Windows.Forms.MessageBox]::Show("Could not open Agent Orchestration.`n$($_.Exception.Message)`nInstall Python 3.9+ and retry, or consult docs/USER_MANUAL.md.",'Agent Orchestration') | Out-Null
}
