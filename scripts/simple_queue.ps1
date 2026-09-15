# One persisted plan, sequential workers, one Foreman check per two tasks.
function Invoke-QueueCheck {
    param([array]$Batch, [string]$DirectorBriefing, [switch]$Final)
    $docs = ($Batch | ForEach-Object { $_.Doc }) -join "`n"
    $prompt = @"
Check whether these completed tasks are on track against the product spec and Director implementation plan.
Read docs/product/PRODUCT_BRIEF.md, docs/product/IMPLEMENTATION_PLAN.md if present, and $DirectorPlanPath as needed.
Tasks:
$docs
Inspect their actual changes and focused test evidence. Spend at most ten minutes.
Do not replan, create rounds, review reviews, demand memory updates, or repeat unchanged passing tests.
Final queue check: $Final. On the final check, distinguish completed software from any missing live acceptance evidence.
Reply with VERDICT: PASS or VERDICT: FAIL on its own line, followed by concise evidence and concrete fixes.
Write no files. Do not expand the MVP scope.
"@
    $r = Invoke-AgentProcess 'Foreman1' $Foreman1Model 'medium' $prompt 'queue-progress-check' 10
    if ($r.Status -ne 'OK') { return @{Status=$r.Status; Output=$r.Output} }
    $verdicts = @([regex]::Matches($r.Output, '(?m)^\s*VERDICT:\s*(PASS|FAIL)\s*$'))
    if ($verdicts.Count -ne 1) { return @{Status='ERROR'; Output=$r.Output} }
    Save-AgentReply 'queue-check' $r.Output | Out-Null
    return @{Status=$verdicts[0].Groups[1].Value; Output=$r.Output}
}

function Invoke-SimpleQueue {
    param([string]$DirectorBriefing)
    $queuePath = Join-Path $OvernightDir 'task-queue.json'
    if (Test-Path $queuePath) {
        $queue = Get-Content $queuePath -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    else {
        # Persist the planning attempt BEFORE dispatch. Restarts cannot silently
        # purchase another planning session after a bad or interrupted response.
        $queue = [pscustomobject]@{manifest=$(if ($Manifest) {$Manifest} else {'docs/tasks/build/manifest.json'}); planned=$false; planning_attempts=0; completed=@(); checked=0; repair_attempts=0; status='PLANNING'}
        Write-TeamJson $queuePath $queue
    }
    $manifestPath = Join-Path $ProjectRoot $queue.manifest
    if (-not (Test-ContainedPath $manifestPath (Join-Path $ProjectRoot 'docs/tasks'))) { throw 'Queue manifest must stay under docs/tasks.' }
    if (-not $queue.planned) {
        # Recover a complete manifest written before an interrupted planner exit.
        $data = $null
        if (Test-Path $manifestPath) {
            try { $data = Load-Manifest $manifestPath; if ((Validate-Manifest $data).Count) { $data=$null } } catch { $data=$null }
        }
        if (-not $data) {
            if ($queue.planning_attempts -ge 2) {
                $script:TerminalStatus='PLAN-ERROR'; $script:TerminalAction='Task planning exhausted its one format repair. See task-queue.json and planner logs.'; return
            }
            $formatFeedback = [string](Get-ObjectProperty $queue 'plan_error')
            for ($attempt=[int]$queue.planning_attempts; $attempt -lt 2; $attempt++) {
                if (Test-ShouldStop) { $script:TerminalStatus='STOPPED'; return }
                $queue.planning_attempts++; Write-TeamJson $queuePath $queue
                $prompt = @"
Read docs/product/PRODUCT_BRIEF.md and the Director implementation plan at $DirectorPlanPath.
If docs/product/IMPLEMENTATION_PLAN.md exists, read it as the full implementation roadmap.
Inspect existing product code and docs/tasks plus current evidence to preserve completed work.
Create ONE ordered task queue covering ALL remaining MVP implementation, focused tests and final acceptance.
Write $($queue.manifest) and task Markdown files plus CONTEXT.md in docs/tasks/build/.
Use docs/tasks/initial/manifest.json as the JSON schema example. Use 1-32 tasks, unique names,
doc, timeout_min, gate_files, json_gates and continue_on_fail=false. Evidence paths must be
under out/orchestration/. Task documents must give implementation steps, exact outputs and focused tests.
Each task should be a useful build step, usually 30-60 minutes. Finish task decomposition in this call.
No planning rounds, no approval stage, no memory candidate, no signal files, no reviewing old reviews.
Do not implement product code yourself. Do not recreate finished features. Resume partial implementation.
The Worker will execute the files in order, with a short Foreman check after every two tasks.
If this is a format repair, repair the existing manifest rather than revisiting the implementation plan.
Director direction:
$DirectorBriefing
"@
                if ($attempt -gt 0) {
                    $prompt = "Repair only the existing task manifest at $manifestPath. Validation error: $formatFeedback. Preserve task scope and order. Use the existing files; do not reread the product spec, replan, or recreate tasks. Task docs stay under docs; output paths stay within this project. Return once the manifest is valid."
                }
                $r = Invoke-AgentProcess 'Foreman1'  $Foreman1Model 'medium' $prompt 'create-task-queue' 10
                if ($r.Status -ne 'OK') { $script:TerminalStatus=$r.Status; return }
                try {
                    $data = Load-Manifest $manifestPath
                    $errors = Validate-Manifest $data
                    if ($errors.Count) { throw ($errors -join '; ') }
                    break
                } catch {
                    $data=$null; $formatFeedback=$_.Exception.Message
                    $queue | Add-Member -NotePropertyName plan_error -NotePropertyValue $formatFeedback -Force
                    Write-TeamJson $queuePath $queue
                    Write-Log "Task queue format error: $formatFeedback"
                }
            }
        }
        if (-not $data) { $script:TerminalStatus='PLAN-ERROR'; return }
        $queue.planned=$true; $queue.status='BUILDING'; Write-TeamJson $queuePath $queue
    }
    $data = Load-Manifest $manifestPath
    $errors = Validate-Manifest $data
    if ($errors.Count) { throw ($errors -join '; ') }
    # Validate the durable prefix: source changes made by later tasks never reset it.
    if (@($queue.completed).Count -gt $data.Tasks.Count -or $queue.checked -gt @($queue.completed).Count) { throw 'Invalid saved task queue progress.' }
    for ($i=0; $i -lt @($queue.completed).Count; $i++) {
        if ($queue.completed[$i] -ne $data.Tasks[$i].Name) { throw 'Completed queue order changed; preserve the completed prefix.' }
    }
    while ($true) {
        if (Test-ShouldStop) { $script:TerminalStatus='STOPPED'; return }
        if ($MaxHours -gt 0 -and (Get-ElapsedHours) -ge $MaxHours) { $script:TerminalStatus='TIMEOUT'; return }
        $count = @($queue.completed).Count
        $final = $count -eq $data.Tasks.Count
        if (($count - $queue.checked) -ge 2 -or ($final -and $count -gt $queue.checked)) {
            $batch = @($data.Tasks[$queue.checked..($count-1)])
            $check = Invoke-QueueCheck $batch $DirectorBriefing -Final:$final
            if ($check.Status -eq 'FAIL' -and $queue.repair_attempts -lt 1) {
                $queue.repair_attempts++; Write-TeamJson $queuePath $queue
                $repairPrompt = "Fix these concrete findings in the completed task batch. Read these task docs: " + (($batch | ForEach-Object {$_.Doc}) -join ', ') + ". Preserve their constraints, update evidence and run focused tests. Do not replan.`n" + $check.Output
                $repair = Invoke-AgentProcess 'Worker' $WorkerModel 'high' $repairPrompt 'queue-repair' 60
                if ($repair.Status -ne 'OK') { $script:TerminalStatus=$repair.Status; return }
                foreach ($task in $batch) {
                    if (-not (Test-Gates $task).Pass) { $script:TerminalStatus='GATE-FAIL'; return }
                }
                continue
            }
            if ($check.Status -ne 'PASS') { $script:TerminalStatus=$check.Status; $script:TerminalAction=$check.Output; return }
            if ($script:GitManaged) {
                & (Join-Path $ProjectRoot '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'team_git.py') checkpoint --label 'Task batch checked by Foreman' --push-if-approved
                if ($LASTEXITCODE -ne 0) { throw 'Could not checkpoint the completed batch.' }
            }
            if ($final) { [IO.File]::WriteAllText($CompletionReportPath,$check.Output,[Text.UTF8Encoding]::new($false)) }
            $queue.checked=$count; $queue.repair_attempts=0; Write-TeamJson $queuePath $queue
        }
        if ($final) {
            $queue.status='COMPLETE'; Write-TeamJson $queuePath $queue
            $script:TerminalStatus='COMPLETE'; $script:TerminalAction='All queued tasks executed and checked. See COMPLETION_REPORT.md for acceptance evidence and limitations.'; return
        }
        $task = $data.Tasks[$count]
        Write-Log "Queue task $($count+1)/$($data.Tasks.Count): $($task.Name)"
        $feedback=''
        for ($attempt=0; $attempt -le 1; $attempt++) {
            $worker = Invoke-WorkerWithRetry $task $feedback $DirectorBriefing
            if ($worker.Status -ne 'OK') { $script:TerminalStatus=$worker.Status; return }
            $gate = Test-Gates $task
            if ($gate.Pass) { break }
            $feedback="Fix the task's failing outputs and rerun focused tests. " + $gate.Reason
        }
        if (-not $gate.Pass) { $script:TerminalStatus='GATE-FAIL'; $script:TerminalAction=$feedback; return }
        $queue.completed=@($queue.completed) + $task.Name
        Write-TeamJson $queuePath $queue
        Save-TaskState $task.Name $data.Round 'PASS' 'Worker evidence passed; batch check pending' $task
    }
}

