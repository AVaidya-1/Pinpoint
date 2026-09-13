[CmdletBinding()]
param(
    [string]$RuntimeDirectory = (Join-Path (Split-Path $PSScriptRoot -Parent) 'out/orchestration/runtime'),
    [switch]$List, [string]$Role='Team', [string]$Label='', [ValidateRange(0,1000000)][int]$Offset=0,
    [string]$From, [string]$To, [string]$Task, [string]$Kind,
    [string]$Body, [string]$BodyFile, [string[]]$Evidence=@(), [string]$ReplyTo=''
)
$ErrorActionPreference='Stop'
$OvernightDir=[IO.Path]::GetFullPath($RuntimeDirectory)
. (Join-Path $PSScriptRoot 'team_context.ps1')
if ($List) {
    $messages=@(Get-TeamInbox $Role $Label)
    $messages | Select-Object -Skip $Offset -First 8 | ForEach-Object {
        "## $($_.id) | $($_.kind) | $($_.from) -> $($_.to) | $($_.task)"
        $_.body
        "Reply-To: $($_.reply_to) | Evidence: $($_.evidence -join '; ')"
    }
    "Open messages: $($messages.Count). Offset: $Offset. Page size: 8."
}
else {
    if ($BodyFile) { $Body=Get-Content -LiteralPath $BodyFile -Raw -Encoding UTF8 }
    Send-TeamMessage $From $To $Task $Kind $Body $Evidence $ReplyTo
}
