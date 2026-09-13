# A live integration exercise, not a product run or a project-completion claim.
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
. (Join-Path $repo 'scripts/run_team.ps1') -LibraryOnly
$OvernightDir = Join-Path $repo ('out/orchestration_pilot/' + [Guid]::NewGuid().ToString('N'))
$LogDir = Join-Path $OvernightDir 'logs'
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$RunnerLogPath = Join-Path $OvernightDir 'runner.log'
$StopFile = Join-Path $OvernightDir 'STOP.txt'
$MaxHours = 1
$RetryWaitMinutes = 1
$artifact = Join-Path $OvernightDir 'worker_result.txt'
$planFile = Join-Path $OvernightDir 'plan.md'
$f1File = Join-Path $OvernightDir 'f1_review.md'
$f2File = Join-Path $OvernightDir 'f2_review.md'
$pilotPrompt = @"
This is an isolated orchestration integration exercise, not Agent Orchestration work.
Only write under $OvernightDir. Do not run product scripts, change source files,
read credentials, spawn agents, or claim the product/project is complete.
Your assigned role overrides old CLAUDE.md model workflows. The supervisor owns
all model routing. Shared communication ledger: $OvernightDir/communications.md.
Read it before your assignment; you may append concise questions or findings there.
The sole pilot goal is that worker_result.txt contains exactly AUTONOMY_PILOT_OK
after trimming whitespace, supported by independent reviews. No other deliverable.
When your assignment specifies a response prefix, begin your response with that
exact plain-text line. Never wrap VERDICT, TASK_VERDICT or DECISION lines in
Markdown bold, backticks, headings or code fences, and put no preamble before them.
"@
function Get-CommunicationPrompt { return $pilotPrompt }
function Call-PilotAgent {
    param($Role, $Model, $Effort, $Prompt, $Label)
    $r = Invoke-AgentProcess $Role $Model $Effort $Prompt $Label 5
    if ($r.Status -ne 'OK') { throw "$Label failed: $($r.Status); $($r.LogFile)" }
    return $r.Output
}
try {
    Write-Host "Pilot directory: $OvernightDir"
    $feedback = ''
    $approved = $false
    for ($cycle=0; $cycle -lt 3; $cycle++) {
        $plan = Call-PilotAgent 'Foreman1' $Foreman1Model 'medium' "Develop ONE bounded worker task to create $artifact containing exactly AUTONOMY_PILOT_OK. State exact allowed path and PowerShell-only acceptance check using Trim (never remove internal whitespace). The supervisor runs both independent reviews after the worker. Output the full task as Markdown in your response; do not create files. Address any F2 feedback: $feedback" "pilot-plan-$cycle"
        [IO.File]::WriteAllText($planFile, $plan)
        $planHistory = Save-AgentReply "pilot_plan_$cycle" $plan
        Add-Handoff 'Foreman1' 'Foreman2' 'Plan ready for independent review' $planHistory
        $approval = Call-PilotAgent 'Foreman2' $Foreman2Model 'high' "Read $planFile. Check the plan against the pilot goal and isolated write scope. The supervisor separately runs F1 and F2 reviews, so the worker must not spawn them. First line exactly VERDICT: APPROVE or VERDICT: REVISE, followed by brief findings. Do not execute it." "pilot-plan-review-$cycle"
        $approvedFile = Save-AgentReply 'pilot_plan_review' $approval
        if ($approval -match '\A\s*VERDICT:\s*APPROVE\s*(?:\r?\n|$)') { $approved=$true; break }
        $feedback = $approval
        Add-Handoff 'Foreman2' 'Foreman1' 'Revise the plan using these findings' $approvedFile
    }
    if (-not $approved) { throw "Pilot plan still rejected after bounded revisions: $approvedFile" }
    Add-Handoff 'Foreman2' 'Worker' 'Plan approved' $approvedFile
    $worker = Call-PilotAgent 'Worker' $WorkerModel 'high' "Execute exactly the approved task at $planFile. Write only the target artifact and optional shared message. Report the actual file path and verification, then stop." 'pilot-worker'
    $workerReport = Save-AgentReply 'pilot_worker' $worker
    if (-not (Test-Path $artifact) -or (Get-Content $artifact -Raw).Trim() -ne 'AUTONOMY_PILOT_OK') { throw 'Pilot worker artifact failed its machine gate.' }
    Add-Handoff 'Worker' 'Foreman1' 'Artifact passes machine gate; independently review' $workerReport
    $f1 = Call-PilotAgent 'Foreman1' $Foreman1Model 'medium' "Review $planFile and the actual artifact $artifact. Verify exact content rather than trusting the worker. First line VERDICT: PASS or VERDICT: FAIL, then evidence. Do not modify the artifact." 'pilot-f1-review'
    [IO.File]::WriteAllText($f1File, $f1)
    Add-Handoff 'Foreman1' 'Foreman2' 'Result review ready' $f1File
    if ($f1 -notmatch '\A\s*VERDICT:\s*PASS\s*(?:\r?\n|$)') { throw 'F1 rejected pilot result.' }
    $f2 = Call-PilotAgent 'Foreman2' $Foreman2Model 'high' "Independently check $f1File against $planFile and actual $artifact. First line VERDICT: AGREE or VERDICT: DISAGREE. Second line TASK_VERDICT: PASS or TASK_VERDICT: FAIL. Then evidence. This is a pilot completion candidate only." 'pilot-f2-review'
    [IO.File]::WriteAllText($f2File, $f2)
    if ($f2 -notmatch '\A\s*VERDICT:\s*AGREE\s*\r?\nTASK_VERDICT:\s*PASS\s*(?:\r?\n|$)') { throw 'F2 rejected pilot result.' }
    Add-Handoff 'Foreman2' 'Director' 'Both foremen propose pilot completion; independently inspect' $f2File
    $director = Call-PilotAgent 'Director' $DirectorModel 'low' "The foremen propose completion of this isolated pilot. Independently inspect $artifact and reviews $f1File and $f2File. Does the sole pilot goal hold? First line DECISION: DONE or DECISION: CONTINUE. Then concise evidence. Be explicit this does not establish product completion or long-duration reliability." 'pilot-director-acceptance'
    $acceptance = Save-AgentReply 'pilot_director' $director
    if ($director -notmatch '\A\s*DECISION:\s*DONE\s*(?:\r?\n|$)') { throw 'Director did not accept pilot completion.' }
    Add-Handoff 'Director' 'Team' 'Pilot accepted; product work remains paused' $acceptance
    Write-Runtime 'PILOT-PASS' 'Supervisor' 'Live plan / approval / worker / F1 / F2 / Director chain passed' $acceptance
    Write-Host "PILOT PASS: $OvernightDir"
}
catch {
    Write-Runtime 'PILOT-FAIL' 'Supervisor' ([string]$_) $RunnerLogPath
    throw
}
