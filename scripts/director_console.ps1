[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$RuntimeDirectory,
    [Parameter(Mandatory)][ValidatePattern('^\d{17}_[a-f0-9]{32}$')][string]$MessageId
)
$ErrorActionPreference='Stop'
$ProjectRoot=Split-Path $PSScriptRoot -Parent
$OvernightDir=[IO.Path]::GetFullPath($RuntimeDirectory)
$expected=[IO.Path]::GetFullPath((Join-Path $ProjectRoot 'out'))
if (-not ($OvernightDir + [IO.Path]::DirectorySeparatorChar).StartsWith($expected + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
    throw 'Director console runtime must remain under the project output directory.'
}
. (Join-Path $PSScriptRoot 'orchestration_runtime.ps1')
$OvernightDir=[IO.Path]::GetFullPath($RuntimeDirectory)
$LogDir=Join-Path $OvernightDir 'logs'
$RunnerLogPath=Join-Path $OvernightDir 'runner.log'
$DigestPath=Join-Path $OvernightDir 'digest.md'
$StatePath=Join-Path $OvernightDir 'state.json'
$DirectorPlanPath=Join-Path $OvernightDir 'director_plan.md'
$NextRoundFile=Join-Path $OvernightDir 'next_round.txt'
$CompletionReportPath=Join-Path $OvernightDir 'COMPLETION_REPORT.md'
$OwnerQuestionsPath=Join-Path $OvernightDir 'OWNER_QUESTIONS.md'
$DirectorRequestPath=Join-Path $OvernightDir 'director_request.md'
$DirectorModel=[string](Get-TeamConfig).models.Director
$consolePath=Join-Path $OvernightDir 'director-console.json'
$messagePath=Join-Path $OvernightDir "memory/messages/$MessageId.json"
$consoleLock=$null

# The Director console is a separate control plane. Provider waits must be
# visible here without replacing the active worker's runtime.json, and a paused
# project must never make the owner lose access to the Director.
function Test-ShouldStop { return $false }
function Write-Runtime([string]$Status,[string]$Role,[string]$Action,[string]$LogFile='') {
    Write-TeamJson $consolePath @{
        status=$Status; message_id=$MessageId; role=$Role; action=$Action
        log_file=$LogFile; updated=(Get-Date).ToString('o')
    }
}
try {
    # Owner-to-Director conversation is independent of the worker/supervisor
    # lock. It is read-only from the model's perspective and may run while a
    # task is active; directions remain queued until the supervisor is idle.
    try { $consoleLock=[IO.File]::Open((Join-Path $OvernightDir 'director-console.lock'),'OpenOrCreate','ReadWrite','None') }
    catch [IO.IOException] { exit 75 }
    if (-not (Test-Path -LiteralPath $messagePath)) { throw 'Owner message no longer exists.' }
    $message=Get-Content -LiteralPath $messagePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($message.from -ne 'Owner' -or $message.to -ne 'Director' -or $message.id -ne $MessageId) {
        throw 'Message is not a valid Owner-to-Director request.'
    }
    $existing=@(Get-TeamMessages -IncludeClosed | Where-Object { $_.from -eq 'Director' -and $_.to -eq 'Owner' -and $_.reply_to -eq $MessageId })
    if ($existing.Count) { return }
    $label="owner-console-$MessageId"
    $packet=Get-TeamContextPacket -Role 'Director' -Label $label
    $prompt=$packet.Text + "`r`n`r`n" + @"
You are the Agent Orchestration Director speaking directly with the owner through the
local dashboard. Answer the owner's message below in at most 2,400 characters.
Use the supplied bounded context packet and inspect only directly relevant saved
evidence. This response itself does not edit files, launch workers, or change Git.
If the owner gives direction, acknowledge it clearly and translate it into the
next concrete supervisor action. After your reply, the dashboard will start the
supervisor automatically when the team is idle; do not ask the owner to resume it
and do not claim it has started before your response is complete.
For a QUESTION, answer directly without an action prefix. For a DECISION, make
the first line exactly DIRECTION: QUEUE when it can enter the current plan at the
next safe boundary, DIRECTION: REPLAN when it invalidates or replaces the pending
plan, or DIRECTION: PAUSE when the owner asks work to pause. PAUSE and REPLAN
finish the active bounded operation and prevent the next dispatch; neither kills
an active process mid-operation.

OWNER MESSAGE ($($message.kind)):
$($message.body)
"@
    $promptPath=Join-Path $LogDir "$label.prompt.txt"
    $outputPath=Join-Path $LogDir "$label.out.log"
    $finalPath=Join-Path $LogDir "$label.final.md"
    [IO.File]::WriteAllText($promptPath,$prompt,[Text.UTF8Encoding]::new($false))
    Write-TeamJson $consolePath @{status='RUNNING';message_id=$MessageId;log_file=$outputPath;updated=(Get-Date).ToString('o')}
    $arguments=Get-CodexExecArguments -Model $DirectorModel -Effort 'low' -ProjectDirectory $ProjectRoot -FinalFile $finalPath -ReadOnly
    $errorPath="$outputPath.stderr.log"
    while ($true) {
        Wait-UsageCooldown 'Director' $label | Out-Null
        if (Test-Path -LiteralPath $finalPath) { Remove-Item -LiteralPath $finalPath }
        $savedPreference=$ErrorActionPreference
        $ErrorActionPreference='Continue'
        try {
            $prompt | & codex @arguments 1> $outputPath 2> $errorPath
            $exitCode=$LASTEXITCODE
        }
        finally { $ErrorActionPreference=$savedPreference }
        $diagnostics=([string](Get-Content -LiteralPath $errorPath -Raw -ErrorAction SilentlyContinue)) + "`n" + ([string](Get-Content -LiteralPath $outputPath -Raw -ErrorAction SilentlyContinue))
        # Windows PowerShell wraps native stderr as "command : Error: ...".
        # Restore the provider diagnostic boundary before quota classification.
        $diagnostics=$diagnostics -replace '(?im)^[^\r\n]{1,200}\s:\s(?=(?:error|fatal)\b)',''
        $failure=Get-UsageFailure $diagnostics $exitCode
        if ($failure.Kind -ne 'QUOTA') { break }
        Set-UsageCooldown 'Director' $failure $errorPath
        Write-TeamJson $consolePath @{status='QUOTA-WAIT';message_id=$MessageId;role='Director';action='Director is waiting in place for its provider limit to reset; automatic retry remains scheduled.';log_file=$errorPath;updated=(Get-Date).ToString('o')}
    }
    if ($exitCode -ne 0 -or -not (Test-Path -LiteralPath $finalPath)) { throw "Director response failed with exit $exitCode. See $outputPath" }
    Clear-UsageCooldown 'Director'
    $output=[string](Get-Content -LiteralPath $finalPath -Raw -Encoding UTF8)
    if ([string]::IsNullOrWhiteSpace($output)) { throw "Director response was empty. See $outputPath" }
    if ($message.kind -eq 'DECISION') {
        if ($output -notmatch '\A\s*DIRECTION:\s*(QUEUE|REPLAN|PAUSE)\s*(?:\r?\n|$)') { throw 'Director did not classify the owner direction as QUEUE, REPLAN, or PAUSE.' }
        if ($Matches[1] -in @('REPLAN','PAUSE')) {
            Request-DirectorPause -Directive $Matches[1] -Reason "Owner direction $MessageId accepted by the Director." -OwnerMessageId $MessageId | Out-Null
        }
    }
    $replyFile=Save-AgentReply "owner_console_$MessageId" $output
    $body=$output.Trim()
    if ($body.Length -gt 2950) { $body=$body.Substring(0,2900) + "`r`n`r`nFull response saved in $replyFile" }
    $replyId=Send-TeamMessage 'Director' 'Owner' 'OWNER-CONSOLE' 'ANSWER' $body @($replyFile) $MessageId
    Add-Handoff 'Director' 'Owner' 'Dashboard response ready.' $replyFile
    Write-TeamJson $consolePath @{status='REPLIED';message_id=$MessageId;reply_id=$replyId;updated=(Get-Date).ToString('o')}
}
catch {
    Write-TeamJson $consolePath @{status='ERROR';message_id=$MessageId;error=[string]$_;updated=(Get-Date).ToString('o')}
    Add-Handoff 'Supervisor' 'Owner' "Director dashboard response failed: $_"
}
finally {
    if ($consoleLock) { $consoleLock.Dispose() }
}
