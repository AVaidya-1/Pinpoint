<# Quick view of the supervisor's own state; -Watch refreshes every five seconds. #>
[CmdletBinding()]
param(
    [switch]$Watch,
    [int]$OutputLines = 12,
    [string]$RuntimeDirectory = (Join-Path (Split-Path $PSScriptRoot -Parent) 'out/orchestration/runtime')
)

function Read-JsonFile {
    param([string]$Name)
    $path = Join-Path $RuntimeDirectory $Name
    if (Test-Path -LiteralPath $path) {
        try { return (Get-Content $path -Raw -Encoding UTF8 | ConvertFrom-Json) }
        catch { Write-Host "  Cannot read $Name; update may be in progress." -ForegroundColor Yellow }
    }
}

function Show-Dashboard {
    if ($Watch) { Clear-Host }
    Write-Host "`n  AUTONOMOUS TEAM | $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
    Write-Host '  Astra low: direction / impasse / completion'
    Write-Host '  Opus 4.6 medium: plan + review | Sol 5.6 high: verify | Muse 1.3 high: work'
    Write-Host ('  ' + ('=' * 76)) -ForegroundColor DarkGray
    $runtime = Read-JsonFile 'runtime.json'
    if ($runtime) {
        $process = Get-Process -Id $runtime.supervisor_pid -ErrorAction SilentlyContinue
        $alive = $false
        if ($process) {
            try { $alive = ($process.StartTime -le [datetime]$runtime.run_started) } catch {}
        }
        $status = [string]$runtime.status
        if (-not $alive -and $status -in @('RUNNING','STARTING','QUOTA-WAIT','RETRY-WAIT')) { $status = 'INTERRUPTED (supervisor is no longer running)' }
        $color = 'Cyan'
        if ($status -match 'ERROR|BLOCKED|STALLED|INTERRUPTED') { $color='Red' }
        elseif ($status -eq 'DONE') { $color='Green' }
        Write-Host "  Status: $status" -ForegroundColor $color
        Write-Host "  Current role: $($runtime.role)"
        Write-Host "  Action: $($runtime.action)"
        $age = [math]::Round(((Get-Date) - [datetime]$runtime.updated).TotalSeconds)
        Write-Host "  Last update: $($runtime.updated) ($age seconds ago)"
        if ($alive -and $runtime.status -eq 'RUNNING' -and $age -gt 30) {
            Write-Host '  Heartbeat is stale; inspect runner.log.' -ForegroundColor Yellow
        }
    }
    else {
        Write-Host '  No runtime record yet. The revised supervisor has not run.' -ForegroundColor Yellow
        $oldLog = Join-Path $RuntimeDirectory 'runner.log'
        if (Test-Path $oldLog) { Get-Content $oldLog -Tail 3 | ForEach-Object { Write-Host "  $_" } }
    }
    if (Test-Path (Join-Path $RuntimeDirectory 'STOP.txt')) {
        Write-Host '  Stop requested: finish current agent call, then stop.' -ForegroundColor Yellow
    }
    Write-Host "`n  PROVIDER USAGE" -ForegroundColor Yellow
    Write-Host '  No automatic model fallback or billing changes. Remaining allowance: unknown.'
    foreach ($provider in @('anthropic','openai','opencode')) {
        $usage = Read-JsonFile "usage-$provider.json"
        if ($usage) {
            $timing = 'reset unknown'
            if ($usage.reset_source -eq 'provider reported' -and $usage.retry_at) { $timing = "provider reset: $($usage.retry_at)" }
            Write-Host "  $provider $timing; consecutive limits: $($usage.consecutive_limits)"
            if ($usage.PSObject.Properties['next_check_at']) { Write-Host "    Next availability check (not reset): $($usage.next_check_at)" }
        }
    }
    $pending = Read-JsonFile 'pending-operation.json'
    if ($pending) { Write-Host "  Saved attempt: $($pending.role) / $($pending.label) / $($pending.status)" }
    Write-Host "`n  CONTEXT AND COMMUNICATION" -ForegroundColor Yellow
    $contextPacket = Read-JsonFile 'memory/last_packet.json'
    if ($contextPacket) {
        Write-Host "  Memory revision: $($contextPacket.revision) | stale: $($contextPacket.stale)"
        Write-Host "  Last packet: $($contextPacket.role), $($contextPacket.characters) characters"
        Write-Host "  Inbox at dispatch: $($contextPacket.open_messages) open; $($contextPacket.shown_messages) in packet"
        Write-Host "  Packet: $($contextPacket.path)"
    }
    else { Write-Host '  No context packet yet; first planning call will bootstrap memory.' }
    Write-Host "`n  TASK RESULTS" -ForegroundColor Yellow
    $entries = @(Read-JsonFile 'state.json')
    if ($entries.Count) {
        $entries | Select-Object round, task, status, timestamp | Format-Table -AutoSize | Out-Host
    }
    else { Write-Host '  No completed tasks recorded.' }
    Write-Host '  RECENT HANDOFFS' -ForegroundColor Yellow
    $ledger = Join-Path $RuntimeDirectory 'communications.md'
    if (Test-Path $ledger) { Get-Content $ledger -Tail 14 -Encoding UTF8 | ForEach-Object { Write-Host "  $_" } }
    else { Write-Host '  No shared handoffs recorded yet.' }
    if ($runtime -and $runtime.log_file -and (Test-Path -LiteralPath $runtime.log_file)) {
        Write-Host "`n  AGENT OUTPUT: $($runtime.log_file)" -ForegroundColor Cyan
        Get-Content -LiteralPath $runtime.log_file -Tail $OutputLines -Encoding UTF8 | ForEach-Object { Write-Host "  $_" }
    }
    $questions = Join-Path $RuntimeDirectory 'OWNER_QUESTIONS.md'
    if (Test-Path $questions) {
        Write-Host "`n  OWNER QUESTIONS (candidate until reviewed; check status above)" -ForegroundColor Yellow
        Get-Content $questions -TotalCount 10 -Encoding UTF8 | ForEach-Object { Write-Host "  $_" }
    }
    Write-Host "`n  Shared records: $RuntimeDirectory"
    Write-Host '  memory/ | communications.md | director_plan.md | digest.md | runner.log'
}

do {
    Show-Dashboard
    if ($Watch) { Start-Sleep -Seconds 5 }
} while ($Watch)
