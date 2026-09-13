$ErrorActionPreference='Stop'
$repo=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
. (Join-Path $repo 'scripts/run_team.ps1') -LibraryOnly

$OvernightDir=Join-Path $repo ('out/context_tests/' + [Guid]::NewGuid().ToString('N'))
$LogDir=Join-Path $OvernightDir 'logs'
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$StatePath=Join-Path $OvernightDir 'state.json'
$RunnerLogPath=Join-Path $OvernightDir 'runner.log'
$StopFile=Join-Path $OvernightDir 'STOP.txt'
$checks=0
function Assert($Condition,$Message) {
    if (-not $Condition) { throw "ASSERTION FAILED: $Message" }
    $script:checks++
    Write-Host "PASS: $Message"
}
function Must-Fail([scriptblock]$Action,[string]$Message) {
    $failed=$false
    try { & $Action | Out-Null } catch { $failed=$true }
    Assert $failed $Message
}
# The context layer must retain integrity checks in background sessions where
# Microsoft.PowerShell.Utility is unavailable. Exercise the same SHA-256 shape.
$hashProbe=Join-Path $OvernightDir 'hash-probe.txt'
New-Item -ItemType Directory -Path $OvernightDir -Force | Out-Null
[IO.File]::WriteAllText($hashProbe,'portable hash',[Text.UTF8Encoding]::new($false))
$expectedSha=[Security.Cryptography.SHA256]::Create()
try {
    $expectedHash=([BitConverter]::ToString($expectedSha.ComputeHash([Text.Encoding]::UTF8.GetBytes('portable hash')))).Replace('-','')
}
finally { $expectedSha.Dispose() }
Assert ((Get-TeamFileHash $hashProbe) -eq $expectedHash) 'Context SHA-256 integrity helper works'
$replaceProbe=Join-Path $OvernightDir 'atomic-replace.json'
Write-TeamJson $replaceProbe @{iteration=0}
foreach ($iteration in 1..100) { Write-TeamJson $replaceProbe @{iteration=$iteration} }
$replaceResult=Get-Content $replaceProbe -Raw -Encoding UTF8 | ConvertFrom-Json
Assert ($replaceResult.iteration -eq 100 -and -not @(Get-ChildItem "$replaceProbe.*.tmp" -ErrorAction SilentlyContinue).Count) 'Repeated state replacement is atomic and leaves no colliding temp file'
Initialize-TeamContext
$evidence=Join-Path $OvernightDir 'evidence.md'
Set-Content $evidence 'The exact fixture result is FAIL; loss of real surfaces is unproven.'
$q=Send-TeamMessage 'Worker' 'Foreman1' 'B1' 'QUESTION' 'Were discarded points actually part surface?' @($evidence)
$a=Send-TeamMessage 'Foreman1' 'Worker' 'B1' 'ANSWER' 'Not established. Retain this uncertainty.' @($evidence) $q
Assert (@(Get-TeamMessages).Count -eq 2) 'An answer alone does not close the question'
$packet=Get-TeamContextPacket 'Foreman1' 'bootstrap'
Assert ($packet.Text -match 'No approved summary yet' -and $packet.Text -match [regex]::Escape($q)) 'Fresh bootstrap exposes missing memory and pending question'
Set-Content (Join-Path $OvernightDir 'communications.md') ('HISTORY_MUST_NOT_BE_INJECTED' * 10000)
$packet=Get-TeamContextPacket 'Foreman1' 'bounded'
Assert ($packet.Text.Length -lt 24000 -and $packet.Text -notmatch 'HISTORY_MUST_NOT_BE_INJECTED') 'Full history is not injected into a fresh session'
$summary="## Goal`nVerify fixture.`n## Verified facts`nFixture failed; evidence.md.`n## Decisions`nKeep evidence gates.`n## Hypotheses`nSurface loss unproven.`n## Open questions`nNeed component attribution.`n## Next steps`nDiagnose without fixes."
$candidate=@{base_revision=''; summary_md=$summary; evidence=@($evidence); resolutions=@()}
$candidatePath=Join-Path $OvernightDir 'memory/candidate.json'
Write-TeamJson $candidatePath $candidate
$bundle=Get-ContextReviewBundle
$review=Join-Path $LogDir 'f2.md'
Set-Content $review "VERDICT: REVISE`n- Unsupported inference."
Must-Fail { Publish-TeamContext $bundle $review } 'F2 rejection cannot publish memory'
Assert ($null -eq (Read-TeamSnapshot)) 'Rejected bootstrap leaves no falsely verified memory'
Set-Content $review "VERDICT: APPROVE`n- Evidence and open uncertainty checked."
$revision=Publish-TeamContext $bundle $review
Assert ((Read-TeamSnapshot).revision -eq $revision) 'Approval publishes an immutable revision'
Assert (@(Get-TeamMessages).Count -eq 2) 'Omitted questions remain open after summary publication'

# Restore only from disk, then create a new packet as another fresh role.
$bundle=$null
$packet=Get-TeamContextPacket 'Director' 'fresh-session'
Assert ($packet.Text -match $revision -and $packet.Text -match 'Surface loss unproven') 'Another session recovers approved memory from disk'
$candidate.base_revision=$revision
$candidate.resolutions=@(@{id=$q; resolution='Question answered: attribution remains unproven; follow-up required.'; evidence=@($evidence)})
Write-TeamJson $candidatePath $candidate
$bundle=Get-ContextReviewBundle
Set-Content $evidence 'changed after review began'
Must-Fail { Publish-TeamContext $bundle $review } 'Changed primary evidence prevents publication'
Assert ((Read-TeamSnapshot).revision -eq $revision -and @(Get-TeamMessages).Count -eq 2) 'Failed publication preserves old memory and inbox'
$packet=Get-TeamContextPacket 'Foreman2' 'stale'
Assert ($packet.Text -match 'stale or uninitialized: True') 'Changed evidence marks the prior summary stale'
$bundle=Get-ContextReviewBundle
$candidate.summary_md += "`nNew unreviewed material"
Write-TeamJson $candidatePath $candidate
Must-Fail { Publish-TeamContext $bundle $review } 'Candidate changed during review cannot publish'
$bundle=Get-ContextReviewBundle
$newRevision=Publish-TeamContext $bundle $review
Assert (@(Get-TeamMessages | Where-Object { $_.id -eq $q }).Count -eq 0) 'Only an approved explicit resolution closes the identified message'
Assert (@(Get-TeamMessages -IncludeClosed).Count -eq 2) 'Closed messages stay in searchable history'
Assert (@(Get-TeamMessages | Where-Object { $_.id -eq $a }).Count -eq 1) 'Resolving one message does not implicitly erase its reply'

Write-TeamJson $StatePath @(@{round='B'; task='B2'; status='FAIL'; timestamp=(Get-Date).ToString('o')})
$packet=Get-TeamContextPacket 'Foreman1' 'new-result'
Assert ($packet.Text -match 'stale or uninitialized: True' -and $packet.Text -match 'B/B2: FAIL') 'New task results are visible and invalidate snapshot freshness'
for ($i=0; $i -lt 12; $i++) { Send-TeamMessage 'Worker' 'Foreman1' "Q$i" 'QUESTION' ('Unresolved ' + ('x' * 800)) | Out-Null }
$packet=Get-TeamContextPacket 'Foreman1' 'overflow'
$meta=Get-Content (Join-Path $OvernightDir 'memory/last_packet.json') -Raw | ConvertFrom-Json
Assert ($meta.open_messages -gt $meta.shown_messages -and $meta.characters -le 24000) 'Inbox overflow is counted and bounded, not discarded'
Assert (@(Get-TeamMessages).Count -eq 13) 'All unresolved messages survive packet pagination'
$ordered=@(Get-TeamInbox 'Foreman1' 'Q11-worker')
Assert ($ordered[0].task -eq 'Q11') 'Current-task messages take priority over an older backlog'
$orderedPacket=Get-TeamContextPacket 'Foreman1' 'Q11-worker'
Assert ($orderedPacket.Text -match '-Label "Q11-worker"') 'Inbox paging uses the same ordering as the supplied packet'
$page=& (Join-Path $repo 'scripts/team_message.ps1') -RuntimeDirectory $OvernightDir -List -Role Foreman1 -Offset 8
Assert (($page -join "`n") -match 'Open messages: 13') 'Separate helper retrieves later inbox pages'
Must-Fail { Send-TeamMessage 'Worker' 'Foreman1' 'B1' 'QUESTION' ('x' * 3001) } 'Oversized messages are rejected instead of truncated'
Must-Fail { Send-TeamMessage 'Worker' 'Foreman1' 'B1' 'ANSWER' 'x' @() 'unknown' } 'Replies require a real message ID'
$candidate.base_revision='obsolete'
Write-TeamJson $candidatePath $candidate
Must-Fail { Get-ContextReviewBundle } 'Stale-base summary cannot overwrite a newer revision'
$candidate.base_revision=$newRevision
$candidate.summary_md='x' * 8001
Write-TeamJson $candidatePath $candidate
Must-Fail { Get-ContextReviewBundle } 'Oversized summary cannot enter shared memory'
$candidate.summary_md=$summary
$candidate.resolutions=@()
Write-TeamJson $candidatePath $candidate

# Real plan-review integration with fake model responses: no live calls.
function Invoke-Codex {
    param($Model,$Effort,$Prompt,$Label)
    if ($Prompt -notmatch 'memory candidate' -or $Prompt -notmatch 'proposed message resolution') { throw 'Review did not include memory responsibilities' }
    return @{Output="VERDICT: APPROVE`n- Plan and memory checked."}
}
$result=Invoke-PlanReview 'docs/tasks/initial' 'docs/tasks/initial' 0 'guide'
Assert ($result.Verdict -eq 'APPROVE' -and (Read-TeamSnapshot).revision -ne $newRevision) 'Existing F2 plan review also gates memory publication'
$before=(Read-TeamSnapshot).revision
$candidate.base_revision=$before
Write-TeamJson $candidatePath $candidate
function Invoke-Codex { return @{Output="VERDICT: REVISE`n- Memory unsupported."} }
$result=Invoke-ForemanStateReview @{Status='DONE'; Evidence=$evidence}
Assert ($result.Output -match 'REVISE' -and (Read-TeamSnapshot).revision -eq $before) 'Rejected completion-state memory cannot publish'
Assert ($result.Output -match 'unresolved questions') 'Completion cannot ignore questions beyond the initial inbox page'
$snapshotPath=Join-Path $OvernightDir "memory/snapshots/$before.json"
Add-Content $snapshotPath 'tampered'
Must-Fail { Read-TeamSnapshot } 'Published snapshot tampering fails closed'
Write-Host "$checks context checks passed. Artifacts: $OvernightDir"
