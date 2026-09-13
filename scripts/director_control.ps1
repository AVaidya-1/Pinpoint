# Director-owned pause and terminal-stop authority.
# The local owner command is authenticated by access to the project checkout.
# Honoring that command is a deterministic Director control-plane action and
# never depends on model availability or provider quota.

function Get-DirectorPauseRecord {
    $stopPath = Join-Path $OvernightDir 'STOP.txt'
    $recordPath = Join-Path $OvernightDir 'director-pause.json'
    if (-not (Test-Path -LiteralPath $stopPath) -or -not (Test-Path -LiteralPath $recordPath)) { return $null }
    try {
        $record = Get-Content -LiteralPath $recordPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($record.role -ne 'Director' -or $record.directive -notin @('PAUSE','REPLAN')) { return $null }
        return $record
    }
    catch { return $null }
}

function Test-DirectorPauseAuthorized {
    return ($null -ne (Get-DirectorPauseRecord))
}

function Get-DirectorTerminalRecord {
    $path = Join-Path $OvernightDir 'hard-stop.json'
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    try {
        $record = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($record.role -ne 'Director' -or $record.status -notin @('DONE','BLOCKED')) { return $null }
        return $record
    }
    catch { return $null }
}

function Test-DirectorTerminalAuthorized {
    return ($null -ne (Get-DirectorTerminalRecord))
}

function Get-Foreman1EmergencyHoldRecord {
    $markerPath = Join-Path $OvernightDir 'FOREMAN1-HOLD.txt'
    $recordPath = Join-Path $OvernightDir 'foreman1-hold.json'
    if (-not (Test-Path -LiteralPath $markerPath) -or -not (Test-Path -LiteralPath $recordPath)) { return $null }
    try {
        $record = Get-Content -LiteralPath $recordPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($record.role -ne 'Foreman1' -or $record.directive -ne 'EMERGENCY-HOLD') { return $null }
        if ([string]::IsNullOrWhiteSpace([string]$record.reason) -or @($record.evidence).Count -eq 0) { return $null }
        return $record
    }
    catch { return $null }
}

function Test-Foreman1EmergencyHoldAuthorized {
    return ($null -ne (Get-Foreman1EmergencyHoldRecord))
}

function Request-Foreman1EmergencyHold {
    param(
        [Parameter(Mandatory)][string]$Reason,
        [Parameter(Mandatory)][string[]]$Evidence
    )
    $directorUsagePath=Join-Path $OvernightDir 'usage-openai.json'
    if (-not (Test-Path -LiteralPath $directorUsagePath)) {
        throw 'Foreman1 emergency hold requires a persisted Director/OpenAI quota record.'
    }
    $usage=Get-Content -LiteralPath $directorUsagePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($usage.provider -ne 'openai' -or [int]$usage.consecutive_limits -lt 1) {
        throw 'Foreman1 emergency hold requires a valid Director/OpenAI quota record.'
    }
    if ([string]::IsNullOrWhiteSpace($Reason) -or $Reason.Length -gt 2500) {
        throw 'Foreman1 emergency hold requires a concrete reason of 1-2500 characters.'
    }
    if ($Evidence.Count -lt 1 -or $Evidence.Count -gt 10) {
        throw 'Foreman1 emergency hold requires 1-10 evidence references.'
    }
    $runtimePrefix=[IO.Path]::GetFullPath($OvernightDir).TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar
    foreach ($item in $Evidence) {
        $evidencePath=[IO.Path]::GetFullPath($item)
        if (-not $evidencePath.StartsWith($runtimePrefix,[StringComparison]::OrdinalIgnoreCase) -or -not (Test-Path -LiteralPath $evidencePath -PathType Leaf)) {
            throw 'Foreman1 emergency-hold evidence must exist inside the runtime directory.'
        }
    }
    $messageId=Send-TeamMessage 'Foreman1' 'Director' 'EMERGENCY-HOLD' 'DECISION' $Reason $Evidence
    Write-TeamJson (Join-Path $OvernightDir 'foreman1-hold.json') @{
        schema_version=1; role='Foreman1'; directive='EMERGENCY-HOLD'
        reason=$Reason; evidence=@($Evidence | ForEach-Object { [IO.Path]::GetFullPath($_) }); message_id=$messageId
        director_quota_record=$directorUsagePath; created=(Get-Date).ToString('o')
    }
    [IO.File]::WriteAllText(
        (Join-Path $OvernightDir 'FOREMAN1-HOLD.txt'),
        "Foreman1 emergency hold pending Director review: $messageId.",
        [Text.UTF8Encoding]::new($false))
    return @{MessageId=$messageId;Directive='EMERGENCY-HOLD'}
}

function Clear-Foreman1EmergencyHold {
    foreach ($name in @('FOREMAN1-HOLD.txt','foreman1-hold.json')) {
        $path=Join-Path $OvernightDir $name
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path }
    }
}

function Request-DirectorPause {
    param(
        [Parameter(Mandatory)][ValidateSet('PAUSE','REPLAN')][string]$Directive,
        [Parameter(Mandatory)][string]$Reason,
        [string]$OwnerMessageId = ''
    )
    Initialize-TeamContext
    $createdOwnerMessage = -not $OwnerMessageId
    if ($createdOwnerMessage) {
        $OwnerMessageId = Send-TeamMessage 'Owner' 'Director' 'SAFE-PAUSE' 'DECISION' $Reason
    }
    $body = "DIRECTION: $Directive`r`n$Reason"
    $ownerReplyId = ''
    if ($createdOwnerMessage) {
        $ownerReplyId = Send-TeamMessage 'Director' 'Owner' 'SAFE-PAUSE' 'ANSWER' $body @() $OwnerMessageId
    }
    $directorMessageId = Send-TeamMessage 'Director' 'Supervisor' 'SAFE-PAUSE' 'DECISION' $body @() $OwnerMessageId
    Write-TeamJson (Join-Path $OvernightDir 'director-pause.json') @{
        schema_version=1; role='Director'; directive=$Directive
        owner_message_id=$OwnerMessageId; owner_reply_id=$ownerReplyId; director_message_id=$directorMessageId
        reason=$Reason; created=(Get-Date).ToString('o')
    }
    [IO.File]::WriteAllText(
        (Join-Path $OvernightDir 'STOP.txt'),
        "Director authorized $Directive from owner message $OwnerMessageId.",
        [Text.UTF8Encoding]::new($false))
    return @{OwnerMessageId=$OwnerMessageId;OwnerReplyId=$ownerReplyId;DirectorMessageId=$directorMessageId;Directive=$Directive}
}

function Clear-DirectorPause {
    foreach ($name in @('STOP.txt','director-pause.json')) {
        $path = Join-Path $OvernightDir $name
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path }
    }
}
