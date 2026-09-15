. (Join-Path $PSScriptRoot 'team_config.ps1')
# Shared process transport and observable handoffs. Windows PowerShell 5.1.
. (Join-Path $PSScriptRoot 'team_context.ps1')
. (Join-Path $PSScriptRoot 'director_control.ps1')
. (Join-Path $PSScriptRoot 'usage_limits.ps1')
. (Join-Path $PSScriptRoot 'team_notifications.ps1')

function Get-CodexExecArguments {
    param(
        [Parameter(Mandatory)][string]$Model,
        [Parameter(Mandatory)][ValidateSet('low','medium','high')][string]$Effort,
        [Parameter(Mandatory)][string]$ProjectDirectory,
        [Parameter(Mandatory)][string]$FinalFile,
        [switch]$ReadOnly
    )
    $arguments = @('exec','--model',$Model,'-c',("model_reasoning_effort=`"$Effort`""))
    if ($ReadOnly) {
        $arguments += @('--sandbox','read-only')
    }
    else {
        # --approve-for-me already selects the workspace-write sandbox. Codex
        # rejects combining it with an explicit --sandbox argument.
        $arguments += '--approve-for-me'
    }
    $arguments += @('-C',$ProjectDirectory,'--output-last-message',$FinalFile,'-')
    return $arguments
}

function Test-ContainedPath {
    param([string]$Path, [string]$Root)
    try {
        $full = [IO.Path]::GetFullPath($Path)
        $prefix = [IO.Path]::GetFullPath($Root).TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar
        return $full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
    }
    catch { return $false }
}

function Get-TaskFingerprint {
    param([hashtable]$Task)
    if (-not $Task) { return '' }
    $paths = @((Join-Path $ProjectRoot $Task.Doc)) + @($Task.GateFiles)
    # Include the product's actual language/stack, not just top-level Python.
    foreach ($relative in @((Get-TeamConfig).fingerprint_roots)) {
        $root = Join-Path $ProjectRoot $relative
        if (-not (Test-ContainedPath $root $ProjectRoot)) { throw 'Fingerprint roots must remain within the project.' }
        if (-not (Test-Path -LiteralPath $root)) { return '' }
        if (Test-Path -LiteralPath $root -PathType Leaf) { $paths += $root }
        else {
            $paths += @(Get-ChildItem -LiteralPath $root -File -Recurse | Where-Object {
                $_.FullName -notmatch '[\\/](?:__pycache__|node_modules|\.git|\.venv|dist|build|playwright-report|test-results|coverage|\.pytest_cache|\.mypy_cache|\.ruff_cache)[\\/]' -and
                $_.FullName -notmatch '[\\/]fixtures[\\/]generated[\\/]' -and $_.Extension -ne '.pyc'
            } | ForEach-Object { $_.FullName })
        }
    }
    $hashes = @()
    foreach ($path in ($paths | Sort-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return '' }
        $hashes += "$path=$(Get-TeamFileHash $path)"
    }
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes(($hashes -join "`n"))))).Replace('-','') }
    finally { $sha.Dispose() }
}

function Write-Runtime {
    param([string]$Status, [string]$Role, [string]$Action, [string]$LogFile = '')
    $record = @{
        status = $Status; role = $Role; action = $Action; log_file = $LogFile
        supervisor_pid = $PID; run_started = $RunStart.ToString('o')
        updated = (Get-Date).ToString('o')
    }
    $path = Join-Path $OvernightDir 'runtime.json'
    Write-TeamJson $path $record
    # Runtime reporting never grants stop authority. Only an explicit Director
    # decision may create hard-stop.json through Invoke-Director.
    Send-TeamPing $Status $Role
}

function Add-Handoff {
    param([string]$From, [string]$To, [string]$Message, [string]$Evidence = '')
    $entry = "`r`n## $(Get-Date -Format o) | $From -> $To | HANDOFF`r`n$Message`r`n"
    if ($Evidence) { $entry += "Evidence: $Evidence`r`n" }
    Add-Content -LiteralPath (Join-Path $OvernightDir 'communications.md') -Value $entry -Encoding UTF8
}

function Get-CommunicationPrompt {
    param([string]$Role, [string]$Label)
    return @"
You are $Role in a simple sequential MVP build. Follow the current assignment.
Read docs/orchestration/OWNER_BRIEF.md for product constraints.
The Director supplies the implementation plan; one Foreman writes task Markdown;
OpenCode executes tasks in order; the Foreman briefly checks every two tasks.
Opus 4.6 medium is the Foreman, with Sol 5.6 high only on Opus usage limits.
No nested agents, planning rounds, secondary reviewers, memory approval, or inbox ceremony.
Preserve completed product work. Report concrete results and honest test evidence.
Only the supervisor makes Git checkpoints. Do not change Git metadata, policy,
orchestration scripts, credentials, or acceptance thresholds. Do not send external messages.
"@
}

function Wait-QuotaWindow {
    param([string]$Role, [string]$Label)
    return (Wait-UsageCooldown $Role $Label)
}

function Invoke-AgentProcess {
    param([string]$Role, [string]$Model, [string]$Effort, [string]$Prompt,
          [string]$Label, [double]$TimeoutMin = 60)
    if ($Model -notmatch '^[a-zA-Z0-9_./:-]+$' -or $Effort -notin @('low','medium','high')) {
        throw 'Invalid model or effort argument.'
    }
    $failures = 0
    $recovery = ''
    $operationId = [Guid]::NewGuid().ToString('N')
    $operationFile = Join-Path $OvernightDir 'pending-operation.json'
    if (Test-Path -LiteralPath $operationFile) {
        # Keep interrupted/failed attempt evidence when a later invocation starts.
        Copy-Item -LiteralPath $operationFile -Destination (Join-Path $LogDir ("prior-operation-$operationId.json"))
    }
    while ($true) {
        $usageRole = $Role
        if ($Role -eq 'Foreman1') {
            $route = Resolve-ForemanRoute
            $Model = $route.Model; $Effort = $route.Effort; $usageRole = $route.UsageRole
        }
        if ((Test-ShouldStop) -or -not (Wait-UsageCooldown $usageRole $Label)) {
            return @{ Status='STOPPED'; Output=''; LogFile=''; ExitCode=-1; QuotaHit=$false }
        }
        $prefix = (($Label -replace '[^a-zA-Z0-9_-]', '_') + '_' + [Guid]::NewGuid().ToString('N'))
        $promptFile = Join-Path $LogDir "$prefix.prompt.txt"
        $outFile = Join-Path $LogDir "$prefix.out.log"
        $errFile = Join-Path $LogDir "$prefix.err.log"
        $finalFile = Join-Path $LogDir "$prefix.final.md"
        if ($Prompt.Length -gt 24000) { throw 'Assignment exceeds 24000 characters; split the task or reference specific evidence files.' }
        $fullPrompt = (Get-CommunicationPrompt -Role $Role -Label $Label) + "`r`n" + $Prompt + $recovery
        if ($fullPrompt.Length -gt 52000) { throw 'Initial request exceeds the context budget.' }
        [IO.File]::WriteAllText($promptFile, $fullPrompt, [Text.UTF8Encoding]::new($false))
        Write-TeamJson $operationFile @{ id=$operationId; role=$Role; model=$Model; effort=$Effort; label=$Label; status='DISPATCHED'; prompt=$promptFile; stdout=$outFile; stderr=$errFile; updated=(Get-Date).ToString('o') }
        if ($Model -match '^opencode/') {
            $command = "opencode run --model $Model --auto --variant $Effort"
            if ($Role -eq 'Worker' -and $WorkerCmd) { $command = $WorkerCmd }
            # OpenCode needs a pipe rather than Start-Process's stdin redirect.
            $command = "type `"$promptFile`" | $command"
        }
        elseif ($Model -match '^claude-') {
            $command = "claude -p --permission-mode auto --model $Model --effort $Effort < `"$promptFile`""
        }
        else {
            # Automatic review is the non-interactive Codex permission mode.
            # It implies workspace-write, so never add an explicit --sandbox.
            $command = "codex exec --model $Model -c model_reasoning_effort=\`"$Effort\`" --approve-for-me -C `"$ProjectRoot`" --output-last-message `"$finalFile`" - < `"$promptFile`""
        }
        Write-Log "$Label -- $Role ($Model, $Effort)"
        Add-Handoff 'Supervisor' $Role $Label $promptFile
        Write-Runtime 'RUNNING' $Role "$Label | $Model | $Effort" $outFile
        $proc = $null
        $processId = 0
        $status = 'ERROR'
        $exitCode = -1
        try {
            $proc = Start-Process cmd.exe -ArgumentList "/d /s /c `"$command`"" -WorkingDirectory $ProjectRoot `
                -RedirectStandardOutput $outFile -RedirectStandardError $errFile -PassThru -WindowStyle Hidden
            $processId = $proc.Id
            Write-TeamJson $operationFile @{ id=$operationId; role=$Role; model=$Model; effort=$Effort; label=$Label; status='RUNNING'; process_id=$processId; prompt=$promptFile; stdout=$outFile; stderr=$errFile; updated=(Get-Date).ToString('o') }
            # Retain the native handle so ExitCode remains available after Refresh.
            $handle = $proc.Handle
            $deadline = (Get-Date).AddMinutes($TimeoutMin)
            $heartbeat = Get-Date
            while (-not $proc.WaitForExit(1000)) {
                if ((Get-Date) -ge $deadline -or ($MaxHours -gt 0 -and (Get-ElapsedHours) -ge $MaxHours)) {
                    $status = 'CLEANUP-ERROR'
                    $savedPreference = $ErrorActionPreference
                    try {
                        $ErrorActionPreference = 'Continue'
                        & taskkill /PID $proc.Id /T /F *> "$errFile.kill.log"
                        $killExit = $LASTEXITCODE
                    }
                    finally { $ErrorActionPreference = $savedPreference }
                    if ($killExit -eq 0 -and $proc.WaitForExit(5000)) { $status = 'TIMEOUT' }
                    break
                }
                if (((Get-Date) - $heartbeat).TotalSeconds -ge 5) {
                    Write-Runtime 'RUNNING' $Role "$Label | $Model | $Effort" $outFile
                    $heartbeat = Get-Date
                }
            }
            if ($status -notin @('TIMEOUT','CLEANUP-ERROR')) {
                $proc.WaitForExit()
                $exitCode = $proc.ExitCode
                if ($exitCode -eq 0) { $status = 'OK' }
            }
        }
        catch { [IO.File]::WriteAllText("$errFile.transport.log", [string]$_) }
        finally { if ($proc) { $proc.Dispose() } }
        $output = ''
        $errors = ''
        if (Test-Path $outFile) { $output = [string](Get-Content $outFile -Raw -Encoding UTF8) }
        if (Test-Path $errFile) { $errors = [string](Get-Content $errFile -Raw -Encoding UTF8) }
        if ($Model -notmatch '^(claude-|opencode/)') {
            $output = ''
            if (Test-Path $finalFile) { $output = [string](Get-Content $finalFile -Raw -Encoding UTF8) }
        }
        $rawOutput = [string](Get-Content -LiteralPath $outFile -Raw -ErrorAction SilentlyContinue)
        # Remove exact echoed assignment lines before interpreting diagnostics.
        $promptLines = @{}
        foreach ($line in ($fullPrompt -split "`r?`n")) { $promptLines[$line.Trim()] = $true }
        $diagnostics = ((($errors + "`n" + $rawOutput) -split "`r?`n" | Where-Object { -not $promptLines.ContainsKey($_.Trim()) }) -join "`n")
        $failure = Get-UsageFailure $diagnostics $exitCode
        $quota = $failure.Kind -eq 'QUOTA'
        Write-TeamJson $operationFile @{ id=$operationId; role=$Role; model=$Model; effort=$Effort; label=$Label; status=$(if ($quota) {'QUOTA-WAIT'} else {$status}); process_id=$processId; prompt=$promptFile; stdout=$outFile; stderr=$errFile; updated=(Get-Date).ToString('o') }
        Add-Handoff $Role 'Team' "$Label finished: $status (exit $exitCode)." "$outFile ; $errFile ; $finalFile"
        if ($status -in @('TIMEOUT','CLEANUP-ERROR')) {
            return @{Status=$status; Output=$output; LogFile=$outFile; ExitCode=$exitCode; QuotaHit=$false}
        }
        if ($quota) {
            $quotaEvidence = $errFile
            if ((Test-Path -LiteralPath $outFile) -and (Get-Item -LiteralPath $outFile).Length -gt 0) { $quotaEvidence = $outFile }
            Set-UsageCooldown $usageRole $failure $quotaEvidence
            $recovery = "`r`nRECOVERY: The previous attempt ended at a provider usage limit. Inspect existing task artifacts and previous output ($outFile and $errFile) before continuing. Preserve completed work; validate partial writes. Do not repeat external side effects. If their outcome is uncertain, report a blocker. Complete the original assignment and required review response."
            if ($Role -eq 'Foreman1' -and $usageRole -eq 'Foreman1') {
                Add-Handoff 'Foreman1' 'Team' 'Opus usage limit: continuing the same Foreman assignment with GPT-5.6 Sol high.' $quotaEvidence
                continue
            }
            if (Wait-QuotaWindow $usageRole $Label) { continue }
            return @{Status='STOPPED'; Output=$output; LogFile=$outFile; ExitCode=$exitCode; QuotaHit=$false}
        }
        if ($status -eq 'OK' -and -not [string]::IsNullOrWhiteSpace($output)) {
            Clear-UsageCooldown $usageRole
            Remove-Item -LiteralPath $operationFile
            return @{Status='OK'; Output=$output; LogFile=$outFile; ExitCode=$exitCode; QuotaHit=$false}
        }
        $failures++
        if ($failure.Kind -eq 'TERMINAL' -or $failures -ge 2) {
            Write-Runtime 'AGENT-ERROR' $Role "Failed or empty response: $Label; see error log" $errFile
            return @{Status='ERROR'; Output=$output; LogFile=$errFile; ExitCode=$exitCode; QuotaHit=$false}
        }
        if ($failure.Kind -eq 'TRANSIENT') {
            Write-Runtime 'RETRY-WAIT' $Role "$Label; transient provider failure; retry in 5 seconds" $errFile
            for ($wait = 0; $wait -lt 5; $wait++) {
                if (Test-ShouldStop) { return @{Status='STOPPED';Output=$output;LogFile=$errFile;ExitCode=$exitCode;QuotaHit=$false} }
                Start-Sleep -Seconds 1
            }
        }
        Write-Log "$Label -- failed/empty response; retrying once. See $errFile"
    }
}

function Save-AgentReply {
    param([string]$Label, [string]$Output)
    $name = ($Label -replace '[^a-zA-Z0-9_-]', '_') + '_' + [Guid]::NewGuid().ToString('N') + '.md'
    $path = Join-Path $LogDir $name
    [IO.File]::WriteAllText($path, $Output, [Text.UTF8Encoding]::new($false))
    return $path
}

function Get-TopReason {
    param([string]$Output)
    $line = $Output -split "`n" | Where-Object { $_ -match '^\s*[-*]' } | Select-Object -First 1
    if (-not $line) { $line = $Output.Trim() }
    return $line.Substring(0, [Math]::Min(300, $line.Length))
}

function Archive-PlannerSignals {
    foreach ($path in @($NextRoundFile, $CompletionReportPath, $OwnerQuestionsPath, $DirectorRequestPath)) {
        if (Test-Path -LiteralPath $path) {
            $dest = Join-Path $LogDir (([Guid]::NewGuid().ToString('N')) + '_' + (Split-Path $path -Leaf))
            Move-Item -LiteralPath $path -Destination $dest
            Add-Handoff 'Supervisor' 'Team' "Archived previous signal: $path" $dest
        }
    }
}
