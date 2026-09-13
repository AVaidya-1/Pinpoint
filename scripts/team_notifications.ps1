# ntfy sends short operational summaries, never prompts or project logs.
function Send-TeamPing {
    param([string]$Status, [string]$Role = 'Supervisor', [string]$Detail = '', [switch]$Force)
    $configPath = Join-Path $OvernightDir 'notifications.json'
    if (-not (Test-Path $configPath)) { return }
    $config = $null
    try {
        $config = Get-Content $configPath -Raw | ConvertFrom-Json
        if (-not $config.enabled) { return }
        $messages = @{
            DONE='Both reviewers and the Director confirmed completion. Review the result when convenient.'
            BLOCKED='The team needs a decision. Open the laptop dashboard to see the question.'
            STALLED='The Director exhausted the available technical recovery paths. A scope decision may be required.'
            'CLEANUP-ERROR'='An agent could not be stopped cleanly. Do not restart the team yet.'
            TEST='Phone notifications are connected. This is a test; no agents were started.'
        }
        $statePath = Join-Path $OvernightDir 'notification-state.json'
        $attemptPath = Join-Path $OvernightDir 'notification-attempt.json'
        $key = "$Status/$Role"
        $last = $null
        if (Test-Path $statePath) { $last = Get-Content $statePath -Raw | ConvertFrom-Json }
        $observedKey = ''
        if ($last) {
            if ($last.PSObject.Properties['observed_key']) { $observedKey = [string]$last.observed_key }
            elseif ($last.PSObject.Properties['key']) { $observedKey = [string]$last.key }
        }
        if (-not $messages.ContainsKey($Status)) {
            # Remember silent states so a later recurrence of the same alerting
            # state is a new transition, without sending heartbeat noise.
            if ($observedKey -ne $key) {
                Write-TeamJson $statePath @{observed_key=$key;updated=(Get-Date).ToString('o')}
            }
            return
        }
        if (-not $Force -and $observedKey -eq $key) { return }
        if (-not $Force -and (Test-Path $attemptPath)) {
            $attempt = Get-Content $attemptPath -Raw | ConvertFrom-Json
            # Old installations wrote {time} only. Missing fields must not make
            # every operational notification fail under StrictMode.
            $attemptStatus = ''
            $attemptTime = $null
            if ($attempt.PSObject.Properties['status']) { $attemptStatus = [string]$attempt.status }
            if ($attempt.PSObject.Properties['time']) { $attemptTime = [datetime]$attempt.time }
            if ($attemptStatus -eq $Status -and $attemptTime -and ((Get-Date)-$attemptTime).TotalSeconds -lt 60) { return }
        }
        $body = [string]$messages[$Status]
        if ($Status -eq 'QUOTA-WAIT') {
            $cooldown = Read-UsageCooldown $Role
            if ($cooldown) { $body += " Retry: $($cooldown.retry_at) ($($cooldown.reset_source))." }
        }
        $priority = 'default'
        if ($Status -match 'ERROR|BLOCKED|STALLED') { $priority = 'high' }
        Write-TeamJson $attemptPath @{time=(Get-Date).ToString('o');status=$Status}
        Invoke-RestMethod -Uri $config.url -Method Post -TimeoutSec 8 -ContentType 'text/plain; charset=utf-8' `
            -Headers @{Title="Agent Orchestration: $Status"; Priority=$priority} -Body ([Text.Encoding]::UTF8.GetBytes($body)) | Out-Null
        Write-TeamJson $statePath @{observed_key=$key;key=$key;sent=(Get-Date).ToString('o')}
    }
    catch {
        # Do not leak the topic URL through exception text or block model work.
        $safe = [string]$_.Exception.Message
        if ($config -and $config.url) {
            $safe = $safe -replace [regex]::Escape([string]$config.url), '[configured ntfy endpoint]'
            try {
                $topic = ([uri][string]$config.url).Segments[-1].Trim('/')
                if ($topic) { $safe = $safe -replace [regex]::Escape($topic), '[private topic]' }
            } catch {}
        }
        Add-Content (Join-Path $OvernightDir 'notification-errors.log') "$(Get-Date -Format o) Notification delivery failed ($($_.Exception.GetType().Name)): $safe"
    }
}
