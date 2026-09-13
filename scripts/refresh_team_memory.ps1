# Bootstrap/refresh shared memory through F1 + F2 without executing project tasks.
[CmdletBinding()]
param([switch]$ReviewExistingCandidate)
. (Join-Path $PSScriptRoot 'run_team.ps1') -LibraryOnly
$memoryLock=$null
try {
    $memoryLock=[IO.File]::Open((Join-Path $OvernightDir 'runner.lock'),'OpenOrCreate','ReadWrite','None')
    Initialize-TeamContext
    $candidatePath=Join-Path $OvernightDir 'memory/candidate.json'
    $feedback=''
    for ($attempt=0; $attempt -lt 3; $attempt++) {
        if (Test-ShouldStop) { throw 'Memory refresh stopped.' }
        if (-not ($ReviewExistingCandidate -and $attempt -eq 0)) {
        if (Test-Path $candidatePath) {
            Move-Item -LiteralPath $candidatePath -Destination (Join-Path $LogDir ('memory_refresh_prior_' + [Guid]::NewGuid().ToString('N') + '.json'))
        }
        $prompt=@"
You are Foreman1. Bootstrap or refresh shared project memory ONLY; do not plan or
execute product tasks. Read CONTEXT_PROTOCOL.md and write $candidatePath in its
schema, using the packet's current base revision.
Use the exact headings ## Goal, ## Verified facts, ## Decisions, ## Hypotheses,
## Open questions, ## Next steps. Put qualifiers in body text, not headings.
Every resolution must include id, a nonempty resolution, and evidence paths.
Before returning, call Get-ContextReviewBundle in a LibraryOnly local session
to validate your candidate; correct format errors before handing it off.
Read docs/orchestration/OWNER_BRIEF.md, docs/product/PRODUCT_BRIEF.md,
and current state.json if present. No prior runtime or approved memory is assumed.
Inspect relevant linked evidence selectively. Distinguish historical product
findings, implemented orchestration, tested behavior, and remaining validation.
Keep unverified claims labeled and product execution paused. Do not claim DONE.
Handle the supplied inbox batch; leave other messages queued. Write only the candidate and optional
new messages through team_message.ps1. Do not alter source, reports or policy.
Preserve prior material decisions and open questions. Cite evidence beside facts.
Print a brief handoff when done. Feedback from prior review: $feedback
"@
        $r=Invoke-AgentProcess 'Foreman1' $Foreman1Model 'medium' $prompt "memory-refresh-$attempt" 10
        if ($r.Status -ne 'OK') { throw "Memory author failed: $($r.Status); $($r.LogFile)" }
        }
        try { $bundle=Get-ContextReviewBundle }
        catch { $feedback="Candidate validation failed: $_"; continue }
        $reviewPrompt='Independently review the proposed shared-memory update. This is memory maintenance only, not project completion or approval to resume product work. ' + (Get-ContextReviewInstruction $bundle) + ' First line exactly VERDICT: APPROVE or VERDICT: REVISE, then evidence and corrections.'
        $review=Invoke-Codex $Foreman2Model 'high' $reviewPrompt "memory-review-$attempt"
        $reviewFile=Save-AgentReply 'memory_review' $review.Output
        if ($review.Output -match '\A\s*VERDICT:\s*APPROVE\s*(?:\r?\n|$)') {
            try { $revision=Publish-TeamContext $bundle $reviewFile }
            catch { $feedback="Publication validation failed: $_"; continue }
            Get-TeamContextPacket 'Director' 'memory-ready-preview' | Out-Null
            Write-Runtime 'READY' 'Supervisor' "Verified context ready: $revision; product execution paused" $reviewFile
            Write-Host "MEMORY READY: $revision"
            return
        }
        $feedback=$review.Output
        Add-Handoff 'Foreman2' 'Foreman1' 'Shared-memory candidate needs revision' $reviewFile
    }
    throw "Memory refresh exhausted three attempts. Last findings: $feedback"
}
catch {
    if ($memoryLock) { Write-Runtime 'MEMORY-ERROR' 'Supervisor' ([string]$_) $RunnerLogPath }
    throw
}
finally { if ($memoryLock) { $memoryLock.Dispose() } }
