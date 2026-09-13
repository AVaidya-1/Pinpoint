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
    $packet = Get-TeamContextPacket $Role $Label
    $foremanHold = ''
    if ($Role -eq 'Foreman1') {
        $foremanHold = @"
Emergency hold authority: if and only if you identify a concrete safety or
coordinator-integrity problem and the Director is currently unreachable because
usage-openai.json records an active provider limit, write the reason and evidence
to a file inside $OvernightDir, then run:
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/foreman1_hold.ps1 -RuntimeDirectory "$OvernightDir" -ReasonFile <absolute-evidence-file>
This creates a temporary Foreman1 hold, not a terminal stop. Finish your current
response after invoking it. Do not use it for ordinary technical disagreement,
your own provider limit, slow work, failed tests, or a substitute for escalation.
"@
    }
    return @"
Read docs/orchestration/AGENT_PROTOCOL.md first. Your explicitly assigned role
in this request supersedes old default model workflows in CLAUDE.md.
The supervisor owns Git commits and GitHub pushes. Do not commit, switch branches,
reset, clean, merge, force-push, or modify Git metadata yourself. Only one writer
may edit this checkout. Foremen must inspect the complete git diff and untracked
source files before approving a task; unexpected changes require rejection.
Use the bounded packet below and read docs/orchestration/CONTEXT_PROTOCOL.md.
Do not load entire communications, digest, notes or transcript histories.
Search exact task/message IDs and inspect relevant primary evidence as needed.
Send questions, answers, findings or decisions with scripts/team_message.ps1
-RuntimeDirectory "$OvernightDir" -From $Role -To <role> -Task <task-id>
-Kind QUESTION|ANSWER|FINDING|DECISION -BodyFile <markdown-file> [-ReplyTo <id>].
Every unanswered question remains in the inbox across fresh sessions. F1 proposes
resolutions and memory updates; F2 verifies them. Do not edit published memory,
old messages or history. Do not spawn
other models yourself: the supervisor owns role routing and reviews. Report
concise evidence and decisions, not private chain of thought.
$foremanHold
Packet source: $($packet.Path)
$($packet.Text)
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
        if ((Test-ShouldStop) -or -not (Wait-UsageCooldown $Role $Label)) {
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
        if ($Role -eq 'Worker') {
            $command = "opencode run --model $Model --auto --variant $Effort"
            if ($WorkerCmd) { $command = $WorkerCmd }
            # OpenCode needs a pipe rather than Start-Process's stdin redirect.
            $command = "type `"$promptFile`" | $command"
        }
        elseif ($Role -eq 'Foreman1') {
            $command = "claude -p --permission-mode auto --model $Model --effort $Effort < `"$promptFile`""
        }
        else {
            # Automatic review is the non-interactive Codex permission mode.
            # It implies workspace-write, so never add an explicit --sandbox.
            $command = "codex exec --model $Model -c model_reasoning_effort=\`"$Effort\`" --approve-for-me -C `"$ProjectRoot`" --output-last-message `"$finalFile`" - < `"$promptFile`""
        }
        Write-Log "$Label -- $Role ($Model, $Effort)"
        Add-Handoff 'Supervisor' $Role $Label $promptFile
        Write-Runtime 'RUNNING' $Role $Label $outFile
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
                    Write-Runtime 'RUNNING' $Role $Label $outFile
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
        if ($Role -in @('Director','Foreman2')) {
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
            Set-UsageCooldown $Role $failure $quotaEvidence
            $recovery = "`r`nRECOVERY: The previous attempt ended at a provider usage limit. Inspect existing task artifacts and previous output ($outFile and $errFile) before continuing. Preserve completed work; validate partial writes. Do not repeat external side effects. If their outcome is uncertain, report a blocker. Complete the original assignment and required review response."
            if (Wait-QuotaWindow $Role $Label) { continue }
            return @{Status='STOPPED'; Output=$output; LogFile=$outFile; ExitCode=$exitCode; QuotaHit=$false}
        }
        if ($status -eq 'OK' -and -not [string]::IsNullOrWhiteSpace($output)) {
            Clear-UsageCooldown $Role
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
