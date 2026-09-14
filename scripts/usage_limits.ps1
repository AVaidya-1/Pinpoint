# Durable provider cooldowns. No billing changes or model substitutions.
function Get-UsageProvider {
    param([string]$Role)
    $model = ''
    $modelVariable = Get-Variable -Name ($Role + 'Model') -Scope Script -ErrorAction SilentlyContinue
    if ($modelVariable) { $model = [string]$modelVariable.Value }
    if (-not $model) {
        try { $model = [string](Get-TeamConfig).models.$Role } catch { $model = '' }
    }
    if ($model -match '^opencode/') { return 'opencode' }
    switch ($Role) {
        'Foreman1' { return 'anthropic' }
        'Worker' { return 'opencode' }
        default { return 'openai' }
    }
}

function Get-UsageFailure {
    param([string]$Diagnostics, [int]$ExitCode, [datetimeoffset]$Now = [datetimeoffset]::UtcNow)
    # Successful prose is never a transport failure. Require a diagnostic prefix
    # or a provider's standalone limit message, rather than matching echoed tasks.
    $lines = @($Diagnostics -split "`r?`n" | Where-Object {
        $_ -match '(?i)^\s*(error\b|fatal\b|HTTP\s+[45]\d\d\b|API Error\b|you.ve hit your (?:usage|session) limit|you.ve reached your (?:usage|session) limit|you.re out of extra usage|(?:usage|session) limit reached|rate limit exceeded|\{.*"error"\s*:)'
    })
    $text = $lines -join "`n"
    $kind = 'OTHER'
    if ($text -match '(?i)(?:usage|session).?limit|rate.?limit|limit reached|out of (credits|extra usage)|insufficient_quota|quota.exceeded|\b429\b') { $kind = 'QUOTA' }
    elseif ($ExitCode -ne 0 -and $text -match '(?i)overloaded|\b50[234]\b|temporarily unavailable|connection reset|timed out|ECONNRESET') { $kind = 'TRANSIENT' }
    elseif ($ExitCode -ne 0 -and $text -match '(?i)\b40[13]\b|unauthorized|authentication|invalid.api.key|model.not.found') { $kind = 'TERMINAL' }
    $reset = $null
    if ($kind -eq 'QUOTA') {
        # Only machine-readable or explicitly relative times; never guess timezone.
        if ($Diagnostics -match '(?im)^\s*retry-after:\s*(\d+)\s*$') {
            $reset = $Now.AddSeconds([math]::Min(2592000, [double]$Matches[1]))
        }
        elseif ($text -match '(?i)(?:retry|try again) (?:in|after) (\d+) (seconds?|minutes?|hours?)') {
            $amount = [double]$Matches[1]; $unit = $Matches[2]
            if ($unit -match '^minute') { $amount *= 60 }
            if ($unit -match '^hour') { $amount *= 3600 }
            $reset = $Now.AddSeconds([math]::Min(2592000, $amount))
        }
        elseif ($text -match '(?i)(?:reset_at|resets? at)["\s:=]+(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d))') {
            $parsed = [datetimeoffset]::MinValue
            if ([datetimeoffset]::TryParse($Matches[1], [ref]$parsed) -and $parsed -gt $Now) { $reset = $parsed }
        }
        elseif ($text -match '(?i)resets?\s+(\d{1,2}:\d{2}\s*(?:am|pm))\s*\(America/New_York\)') {
            # Claude CLI reports an explicit IANA zone. Windows uses the
            # corresponding system-zone identifier; preserve DST correctly.
            $zone = [TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')
            $clock = [datetime]::ParseExact(($Matches[1] -replace '\s','').ToUpperInvariant(), 'h:mmtt', [Globalization.CultureInfo]::InvariantCulture)
            $localNow = [TimeZoneInfo]::ConvertTime($Now, $zone)
            $localReset = [datetime]::SpecifyKind($localNow.Date.Add($clock.TimeOfDay), [DateTimeKind]::Unspecified)
            $candidate = [datetimeoffset]([TimeZoneInfo]::ConvertTimeToUtc($localReset, $zone))
            if ($candidate -le $Now) {
                $localReset = $localReset.AddDays(1)
                $candidate = [datetimeoffset]([TimeZoneInfo]::ConvertTimeToUtc($localReset, $zone))
            }
            $reset = $candidate
        }
    }
    return @{ Kind=$kind; Reset=$reset }
}

function Read-UsageCooldown {
    param([string]$Role)
    $path = Join-Path $OvernightDir ('usage-' + (Get-UsageProvider $Role) + '.json')
    if (Test-Path -LiteralPath $path) {
        # Corrupt state must stop dispatch, not silently bypass the cooldown.
        return (Get-Content -LiteralPath $path -Raw | ConvertFrom-Json)
    }
    return $null
}

function Set-UsageCooldown {
    param([string]$Role, [hashtable]$Failure, [string]$Evidence)
    $old = Read-UsageCooldown $Role
    $count = 1
    if ($old) { $count = [int]$old.consecutive_limits + 1 }
    $now = [datetimeoffset]::UtcNow
    $source = 'reset unknown'
    $until = $null
    if ($Failure.Reset) { $until = $Failure.Reset.AddSeconds(5); $source = 'provider reported' }
    $provider = Get-UsageProvider $Role
    $nextCheck = $(if ($until) {$until} else {$now.AddMinutes(5)})
    $record = @{ provider=$provider; retry_at=$(if ($until) {$until.ToString('o')} else {$null}); reset_source=$source; next_check_at=$nextCheck.ToString('o'); consecutive_limits=$count; evidence=$Evidence; updated=$now.ToString('o') }
    Write-TeamJson (Join-Path $OvernightDir "usage-$provider.json") $record
    Add-Handoff $Role 'Supervisor' "Usage limit: $provider; $source $until. Availability checks are not reset estimates." $Evidence
}

function Get-CodexAccountUsage {
    $reply = & (Join-Path $ProjectRoot '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'codex_usage.py')
    if ($LASTEXITCODE -ne 0) { return $null }
    try { return ($reply | ConvertFrom-Json) } catch { return $null }
}

function Wait-UsageCooldown {
    param([string]$Role, [string]$Label)
    $record = Read-UsageCooldown $Role
    if (-not $record) { return (-not (Test-ShouldStop)) }
    # Discard legacy estimates; they must never delay a fresh account check.
    $until = $null
    if ($record.reset_source -eq 'provider reported' -and $record.retry_at) { $until = [datetimeoffset]$record.retry_at }
    $nextCheck = [datetimeoffset]::UtcNow
    if ($record.PSObject.Properties['next_check_at'] -and $record.next_check_at) { $nextCheck = [datetimeoffset]$record.next_check_at }
    if ($record.reset_source -eq 'estimated backoff') { $nextCheck = [datetimeoffset]::UtcNow }
    $heartbeat = [datetime]::MinValue
    while ($true) {
        if (Test-ShouldStop) { return $false }
        $now = [datetimeoffset]::UtcNow
        if ($now -ge $nextCheck) {
            if ($record.provider -eq 'openai') {
                $account = Get-CodexAccountUsage
                if ($account -and $account.available -eq $true) {
                    Clear-UsageCooldown $Role
                    return (-not (Test-ShouldStop))
                }
                if ($account -and $account.available -eq $false -and $account.reset_at) {
                    $until = ([datetimeoffset]$account.reset_at).AddSeconds(5)
                    if ($until -le $now) { $until = $null }
                }
                # Read-only checks detect early/manual resets too. No model probe.
                $nextCheck = $now.AddMinutes(1)
            }
            else {
                # Without a provider availability API, a bounded real retry is
                # the availability check. Explicit reset timing avoids probes.
                if (-not $until) { return (-not (Test-ShouldStop)) }
                $nextCheck = $until
            }
            $record.retry_at = $(if ($until) {$until.ToString('o')} else {$null})
            $record.reset_source = $(if ($until) {'provider reported'} else {'reset unknown'})
            $record | Add-Member -NotePropertyName next_check_at -NotePropertyValue $nextCheck.ToString('o') -Force
            Write-TeamJson (Join-Path $OvernightDir "usage-$($record.provider).json") $record
        }
        if ($until -and $now -ge $until) { return (-not (Test-ShouldStop)) }
        if (((Get-Date)-$heartbeat).TotalSeconds -ge 5) {
            $target = $(if ($until) {$until} else {$nextCheck})
            $remaining = [math]::Max(0, [math]::Ceiling(($target - $now).TotalSeconds))
            $timing = $(if ($until) {"reset $($until.ToLocalTime())"} else {"next check $($nextCheck.ToLocalTime())"})
            $action = 'Waiting for usage limit reset ' + [char]0x2014 + " automatic retry scheduled | $Label | $($record.provider) | $timing | ${remaining}s remaining"
            Write-Runtime 'QUOTA-WAIT' $Role $action $record.evidence
            $heartbeat = Get-Date
        }
        Start-Sleep -Seconds 1
    }
}

function Clear-UsageCooldown {
    param([string]$Role)
    $path = Join-Path $OvernightDir ('usage-' + (Get-UsageProvider $Role) + '.json')
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path }
}
