<#
.SYNOPSIS
  Overnight runner: 4-tier autonomous supervisor for product task rounds.
.DESCRIPTION
  Tier 1 - Director  (gpt-6-astra, low):   reads project docs, sets strategic direction
  Tier 2 - Foreman 1 (configured model, med): breaks Director plan into tasks, reviews worker output
  Tier 3 - Foreman 2 (gpt-5.6-sol, high):   verifies Foreman 1 outputs against Director goals
  Tier 4 - Worker    (opencode/muse-spark-1.3-contributor-free, high): executes one task at a time

  Phase 1: Director briefing -> execute predefined tasks (worker -> gates -> Opus review -> Sol verify)
  Phase 2 (-EnableRoundLoop): Opus plans -> Sol verifies -> worker -> both reviews.
  Director is consulted only at initial setup, technical impasse, and completion.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\run_team.ps1 -Tasks DEMO
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\run_team.ps1
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\run_team.ps1 -EnableRoundLoop -MaxRounds 10
#>
[CmdletBinding()]
param(
    [string]$Tasks = '',
    [string]$WorkerModel = 'opencode/muse-spark-1.3-contributor-free',
    [string]$Foreman1Model = 'opencode/muse-spark-1.3-contributor-free',
    [string]$Foreman2Model = 'gpt-5.6-sol',
    [string]$DirectorModel = 'gpt-6-astra',
    [switch]$SkipReview,
    [switch]$SkipDirector,
    [switch]$DryRun,
    [ValidateRange(0, 8760)][int]$MaxHours = 10,
    [string]$NotifyUrl = '',
    [ValidateRange(0, 10)][int]$MaxRevisions = 1,
    [int]$RetryWaitMinutes = 70,
    [switch]$EnableRoundLoop,
    [switch]$PlanFirst,
    [switch]$LibraryOnly,
    [ValidateRange(0, 1000)][int]$MaxRounds = 2,
    [string]$Manifest = '',
    [string]$WorkerCmd = ''
)

Set-StrictMode -Version 2
$ErrorActionPreference = 'Stop'

# -- Paths --------------------------------------------------------------

$ProjectRoot  = Split-Path $PSScriptRoot -Parent
. (Join-Path $PSScriptRoot 'team_config.ps1')
$TeamConfig = Get-TeamConfig
foreach ($roleName in @('Worker','Foreman1','Foreman2','Director')) {
    $parameterName = $roleName + 'Model'
    if (-not $PSBoundParameters.ContainsKey($parameterName)) {
        Set-Variable -Name $parameterName -Value ([string]$TeamConfig.models.$roleName)
    }
}
$ArtifactRoot          = Join-Path $ProjectRoot 'out\orchestration'
$OvernightDir = Join-Path $ArtifactRoot 'runtime'
$LogDir       = Join-Path $OvernightDir 'logs'
$DigestPath   = Join-Path $OvernightDir 'digest.md'
$StatePath    = Join-Path $OvernightDir 'state.json'
$StopFile     = Join-Path $OvernightDir 'STOP.txt'
$DirectorPlanPath   = Join-Path $OvernightDir 'director_plan.md'
$NextRoundFile      = Join-Path $OvernightDir 'next_round.txt'
$CompletionReportPath = Join-Path $OvernightDir 'COMPLETION_REPORT.md'
$OwnerQuestionsPath   = Join-Path $OvernightDir 'OWNER_QUESTIONS.md'
$QuotaPattern = 'usage limit|rate limit|limit reached|out of credits|overloaded'
$RunStart     = Get-Date
$DirectorRequestPath = Join-Path $OvernightDir 'director_request.md'
$script:TerminalStatus = 'STARTING'
$script:GitManaged = $false
$script:TerminalAction = 'Loading strategy'
$script:ResolvingForeman1Hold = $false
. (Join-Path $PSScriptRoot 'orchestration_runtime.ps1')

Set-Location $ProjectRoot

# -- Ensure directories -------------------------------------------------

foreach ($d in @($OvernightDir, $LogDir)) {
    if (-not (Test-Path $d)) {
        New-Item -ItemType Directory -Path $d -Force | Out-Null
    }
}

# -- Hardcoded task table (Phase 1) -------------------------------------

function Build-DefaultTaskTable {
    return (Load-Manifest (Join-Path $ProjectRoot 'docs/tasks/initial/manifest.json')).Tasks
}

# -- Small helpers ------------------------------------------------------

$RunnerLogPath = Join-Path $OvernightDir 'runner.log'

function Write-Log {
    param([string]$Msg)
    $ts = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $line = "[$ts] $Msg"
    Write-Host $line
    Add-Content -Path $RunnerLogPath -Value $line -Encoding UTF8
}

function Append-Digest {
    param([string]$Text)
    Add-Content -Path $DigestPath -Value $Text -Encoding UTF8
}

function Get-ElapsedHours {
    ((Get-Date) - $RunStart).TotalHours
}

function Test-ShouldStop {
    if (Test-DirectorTerminalAuthorized) { return $true }
    if (Test-DirectorPauseAuthorized) {
        Write-Log 'Director-authorized pause detected -- stopping gracefully at the safe boundary.'
        return $true
    }
    if ((Test-Foreman1EmergencyHoldAuthorized) -and -not $script:ResolvingForeman1Hold) {
        Write-Log 'Foreman1 emergency hold detected -- checkpointing before Director review.'
        return $true
    }
    if ((Test-Path $StopFile) -or (Test-Path (Join-Path $OvernightDir 'hard-stop.json'))) {
        Write-Log 'Ignoring an unauthorised stop marker because it has no valid Director record.'
    }
    return $false
}

function Send-Notification {
    param([string]$Status, [string]$Detail)
    if (-not $NotifyUrl) { return }
    $body = "Agent Orchestration overnight: $Status"
    if ($Detail) { $body += " - $Detail" }
    try {
        Invoke-RestMethod -Uri $NotifyUrl -Method Post -Body $body -ContentType 'text/plain' | Out-Null
    }
    catch {
        Write-Log "Notification POST failed: $_"
    }
}

# -- State management --------------------------------------------------

function Load-State {
    if (-not (Test-Path $StatePath)) { return }
    $raw = Get-Content $StatePath -Raw -Encoding UTF8
    if (-not $raw -or $raw.Trim().Length -eq 0) { return }
    $parsed = $raw | ConvertFrom-Json
    return $parsed
}

function Save-TaskState {
    param([string]$TaskName, [string]$Round, [string]$Status, [string]$Verdict, [hashtable]$Task)
    $state = @(Load-State)
    $filtered = @()
    foreach ($entry in $state) {
        if (-not ($entry.task -eq $TaskName -and $entry.round -eq $Round)) {
            $filtered += $entry
        }
    }
    $newEntry = @{
        task      = $TaskName
        round     = $Round
        status    = $Status
        verdict   = $Verdict
        timestamp = (Get-Date).ToString('o')
        fingerprint = (Get-TaskFingerprint $Task)
    }
    $filtered += $newEntry
    $temporaryState = "$StatePath.$PID.tmp"
    ConvertTo-Json -InputObject @($filtered) -Depth 5 | Set-Content $temporaryState -Encoding UTF8
    Move-Item -LiteralPath $temporaryState -Destination $StatePath -Force
}

function Test-TaskPassed {
    param([string]$TaskName, [string]$Round, [hashtable]$Task)
    $state = @(Load-State)
    foreach ($entry in $state) {
        if ($entry.task -eq $TaskName -and $entry.round -eq $Round -and $entry.status -eq 'PASS') {
            if (-not $entry.PSObject.Properties['fingerprint']) { return $false }
            $current = Get-TaskFingerprint $Task
            return ($current -and $entry.fingerprint -eq $current)
        }
    }
    return $false
}

# -- Gate checking ------------------------------------------------------

function Find-GateFile {
    param([string]$Expected)
    if (Test-Path -LiteralPath $Expected -PathType Leaf) { return $Expected }
    return $null
}

function Get-ObjectProperty {
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    if ($Object -is [Collections.IDictionary]) {
        if ($Object.Contains($Name)) { return $Object[$Name] }
        return $null
    }
    $property = $Object.PSObject.Properties[$Name]
    if ($property) { return $property.Value }
    return $null
}

function Test-ObjectProperty {
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $false }
    if ($Object -is [Collections.IDictionary]) { return $Object.Contains($Name) }
    return ($null -ne $Object.PSObject.Properties[$Name])
}

function Get-JsonGateValue {
    param($Json, [hashtable]$Gate)
    $value = $Json
    if ($Gate.Mode -eq 'Expected') {
        if (-not $Gate.JsonPointer.StartsWith('/')) { throw "JSON pointer must start with /: $($Gate.JsonPointer)" }
        foreach ($encodedPart in @($Gate.JsonPointer.Substring(1) -split '/')) {
            $part = $encodedPart.Replace('~1','/').Replace('~0','~')
            if ($value -is [Array]) {
                $index = 0
                if (-not [int]::TryParse($part, [ref]$index) -or $index -lt 0 -or $index -ge $value.Count) {
                    throw "JSON pointer element not found: $part"
                }
                $value = $value[$index]
            }
            elseif (-not (Test-ObjectProperty $value $part)) { throw "JSON pointer property not found: $part" }
            else { $value = Get-ObjectProperty $value $part }
        }
        return $value
    }
    foreach ($part in ($Gate.JsonPath -split '\.')) {
        if (-not (Test-ObjectProperty $value $part)) { throw "JSON path property not found: $part" }
        $value = Get-ObjectProperty $value $part
    }
    return $value
}


function Test-Gates {
    param([hashtable]$Task)
    $missing = @()
    foreach ($gf in $Task.GateFiles) {
        $loc = Find-GateFile $gf
        if (-not $loc) { $missing += $gf }
    }
    if ($missing.Count -gt 0) {
        return @{ Pass = $false; Missing = $missing; Escalate = $false; Reason = '' }
    }
    foreach ($jg in $Task.JsonGates) {
        $filePath = Find-GateFile $jg.File
        if (-not $filePath) {
            return @{ Pass = $false; Missing = @($jg.File); Escalate = $false; Reason = '' }
        }
        try {
            $json = Get-Content $filePath -Raw -Encoding UTF8 | ConvertFrom-Json
            $val = Get-JsonGateValue $json $jg
            if ($jg.Mode -eq 'Expected' -and $val -ne $jg.Expected) {
                $reason = "$($jg.JsonPointer) = $val; expected $($jg.Expected) in $(Split-Path $filePath -Leaf)"
                return @{ Pass = $false; Missing = @(); Escalate = $true; Reason = $reason }
            }
            if ($jg.Mode -eq 'EscalateIf' -and $val -eq $jg.EscalateIf) {
                $reason = "$($jg.JsonPath) = $val in $(Split-Path $filePath -Leaf)"
                return @{ Pass = $false; Missing = @(); Escalate = $true; Reason = $reason }
            }
        }
        catch {
            return @{ Pass = $false; Missing = @(); Escalate = $false
                      Reason = "JSON gate parse error: $_" }
        }
    }
    return @{ Pass = $true; Missing = @(); Escalate = $false; Reason = '' }
}

# -- Codex helper (for Astra + Sol calls) --------------------------------

function Invoke-Codex {
    param([string]$Model, [string]$Effort, [string]$Prompt, [string]$Label)
    $role = 'Foreman2'
    if ($Model -eq $DirectorModel) { $role = 'Director' }
    $result = Invoke-AgentProcess $role $Model $Effort $Prompt $Label
    if ($result.Status -ne 'OK') { throw "$Label failed: $($result.Status). See $($result.LogFile)" }
    return $result
}


# -- Tier 1: Director (Astra) -------------------------------------------

function Invoke-Director {
    param([array]$TaskList, [string]$RoundName, [string]$Reason = 'INITIAL')
    if (Test-ShouldStop) { return @{Status='STOPPED'; Plan=''} }
    $prompt = @"
You are Director / project manager, $DirectorModel on low. Reason for consultation: $Reason.
Read docs/orchestration/AGENT_PROTOCOL.md, docs/orchestration/PLANNER_CHARTER.md,
Use the current context packet and the specific director_request.md,
OWNER_QUESTIONS.md or COMPLETION_REPORT.md under the overnight directory when present.
For INITIAL strategy, consult docs/product/PRODUCT_BRIEF.md as needed.
For later consultations, retrieve only relevant changes and evidence; do not reread
the full project history. Preserve the owner's standing constraints.
Read the relevant task reports and both foremen's findings. Round: $RoundName.
You are called only for initial strategy, a technical impasse, or completion.
Independently verify a completion claim against the goal's validator and regression
artifacts; a foreman's assertion is insufficient. DONE is allowed only for a
completion consultation with all north-star gates met. Otherwise give a concise
technical direction for F1 to turn into tasks and F2 to review. You do not write
code, author task details, weaken gates, or decide owner-only scope/spending.
If you cannot identify a justified, testable next step, exhaust bounded repair and
available technical alternatives before BLOCKED. Contact the owner only for a
required external input or access, or a major path decision
that substantially changes scope, acceptance criteria, cost, or intended outcome.
Routine orchestration repair, provider waits, Git checkpoints, plan revisions,
review disagreements, and implementation choices stay inside this team. State
exactly why either exceptional threshold is met. CONTINUE requires a concrete next hypothesis, available inputs, a bounded
test and a success/failure criterion. Never weaken the goal to declare completion.
First line exactly DECISION: CONTINUE or DECISION: DONE or DECISION: BLOCKED.
Then give evidence paths and concise direction. Do not edit any files.
"@
    $result = Invoke-Codex $DirectorModel 'low' $prompt "Director-$Reason-$RoundName"
    if ($result.Output -notmatch '\A\s*DECISION:\s*(CONTINUE|DONE|BLOCKED)\s*(?:\r?\n|$)') {
        throw 'Director returned no valid decision; briefing not replaced.'
    }
    $decision = $Matches[1]
    if ($decision -eq 'DONE' -and $Reason -ne 'COMPLETION') {
        throw 'Director cannot declare DONE without a reviewed completion candidate.'
    }
    $replyFile = Save-AgentReply "director_$Reason" $result.Output
    if ($decision -in @('DONE','BLOCKED')) {
        Write-TeamJson (Join-Path $OvernightDir 'hard-stop.json') @{
            status=$decision; role='Director'; reason=$result.Output; evidence=$replyFile; created=(Get-Date).ToString('o')
        }
    }
    Add-Handoff 'Director' 'Foreman1, Foreman2' $decision $replyFile
    if ($decision -eq 'CONTINUE') {
        [IO.File]::WriteAllText($DirectorPlanPath, $result.Output, [Text.UTF8Encoding]::new($false))
    }
    if ($decision -eq 'BLOCKED') {
        [IO.File]::WriteAllText($OwnerQuestionsPath, $result.Output, [Text.UTF8Encoding]::new($false))
    }
    Append-Digest "## Director ($Reason): $decision`r`n- Evidence: $replyFile"
    return @{Status=$decision; Plan=$result.Output}
}


# -- Worker prompts -----------------------------------------------------

function Build-WorkerPrompt {
    param([string]$TaskDoc, [string]$Revision, [string]$DirectorBriefing)
    $contextDoc = Join-Path (Split-Path $TaskDoc -Parent) 'CONTEXT.md'
    $lines = @()
    if ($DirectorBriefing) {
        $lines += '=== DIRECTOR BRIEFING (from project manager) ==='
        $lines += $DirectorBriefing
        $lines += '=== END DIRECTOR BRIEFING ==='
        $lines += ''
    }
    $lines += 'You are an autonomous agent executing exactly ONE bounded task in the'
    $lines += "Product repository at $ProjectRoot."
    $lines += "1. Read $contextDoc fully - every hard constraint applies."
    $lines += "2. Execute $TaskDoc exactly as written. Obey every hard prohibition."
    $lines += '   Use .venv\Scripts\python.exe -X utf8 for all Python.'
    $lines += '3. Write all outputs to the exact paths the task specifies.'
    $lines += '4. Stop at the task''s Done when. Do NOT begin any other task.'
    $lines += '   If you hit the task''s escape'
    $lines += '   hatch or cannot meet the gate within the prescribed attempts, write'
    $lines += '   the report saying so honestly and stop - an honest FAIL report is a'
    $lines += '   valid outcome; a fabricated PASS is not.'
    $lines += '5. Use the supplied inbox and bounded context packet. Send questions or'
    $lines += '   out-of-scope findings through team_message.ps1 with task ID and evidence.'
    $lines += '   A message does not expand your scope. Never rewrite published memory.'
    if ($Revision) {
        $lines += ''
        $lines += 'You previously executed this task. An independent reviewer found'
        $lines += 'these problems:'
        $lines += $Revision
        $lines += 'Address ONLY these findings, within the task''s constraints, and'
        $lines += 'update the outputs.'
    }
    return ($lines -join "`r`n")
}

# -- Worker invocation --------------------------------------------------

function Invoke-SingleWorker {
    param([hashtable]$Task, [int]$Attempt, [string]$Revision, [string]$DirectorBriefing)
    $prompt = Build-WorkerPrompt $Task.Doc $Revision $DirectorBriefing
    $r = Invoke-AgentProcess 'Worker' $WorkerModel 'high' $prompt "$($Task.Name)-worker-$Attempt" $Task.TimeoutMin
    return @{ExitCode=$r.ExitCode; Timeout=($r.Status -eq 'TIMEOUT'); QuotaHit=$false;
        LogFile=$r.LogFile; Status=$r.Status}
}


function Invoke-WorkerWithRetry {
    param([hashtable]$Task, [string]$Revision, [string]$DirectorBriefing)
    $r = Invoke-SingleWorker $Task 1 $Revision $DirectorBriefing
    return @{Status=$r.Status; Attempt=1; LogFile=$r.LogFile}
}


# -- Tier 2: Foreman 1 reviews worker output ---------------------------

function Build-Foreman1ReviewPrompt {
    param([hashtable]$Task, [string]$DirectorBriefing)
    $contextDoc = Join-Path (Split-Path $Task.Doc -Parent) 'CONTEXT.md'
    $outputDir = Split-Path $Task.GateFiles[0]
    if ($outputDir.StartsWith($ProjectRoot)) {
        $outputDir = $outputDir.Substring($ProjectRoot.Length + 1)
    }
    $parts = @()
    $parts += 'You are Foreman 1, reviewing a worker''s output for one task.'
    if ($DirectorBriefing) {
        $parts += 'The Director''s strategic briefing for this round:'
        $parts += $DirectorBriefing
        $parts += '---'
    }
    $parts += "Read $contextDoc, $($Task.Doc), and the task outputs under $outputDir."
    $parts += 'Decide whether the task met its OWN Done-when with real evidence:'
    $parts += 'check the claimed numbers against the artifact files;'
    $parts += 'distrust any claim you cannot verify on disk;'
    $parts += 'a task that honestly reports hitting its documented escape hatch is ESCALATE, not FAIL.'
    $parts += 'First line of your reply must be exactly VERDICT: PASS or VERDICT: FAIL or VERDICT: ESCALATE,'
    $parts += 'followed by bullet reasons with file paths.'
    return ($parts -join ' ')
}

function Invoke-Foreman1Review {
    param([hashtable]$Task, [int]$ReviewNum, [string]$DirectorBriefing)
    $prompt = Build-Foreman1ReviewPrompt $Task $DirectorBriefing
    $r = Invoke-AgentProcess 'Foreman1' $Foreman1Model 'medium' $prompt "$($Task.Name)-f1review-$ReviewNum"
    if ($r.Status -ne 'OK') { throw "F1 review failed: $($r.Status); $($r.LogFile)" }
    $file = Save-AgentReply "$($Task.Name)_f1review$ReviewNum" $r.Output
    $verdict = 'FAIL'
    if ($r.Output -match '\A\s*VERDICT:\s*(PASS|FAIL|ESCALATE)\s*(?:\r?\n|$)') { $verdict = $Matches[1] }
    Add-Handoff 'Foreman1' 'Foreman2' "$($Task.Name): $verdict" $file
    return @{Verdict=$verdict; ReviewFile=$file; TopReason=(Get-TopReason $r.Output); FullReview=$r.Output}
}


# -- Tier 3: Foreman 2 (Sol) verifies Foreman 1 output -----------------

function Invoke-Foreman2Verify {
    param([hashtable]$Task, [string]$F1ReviewFile, [string]$DirectorBriefing, [int]$VerifyNum)

    $verifyFile = Join-Path $LogDir ("$($Task.Name)_f2verify$VerifyNum`_" + [Guid]::NewGuid().ToString('N') + '.md')
    $outputDir = Split-Path $Task.GateFiles[0]
    if ($outputDir.StartsWith($ProjectRoot)) {
        $outputDir = $outputDir.Substring($ProjectRoot.Length + 1)
    }

    $parts = @()
    $parts += 'You are Foreman 2, the independent verifier.'
    $parts += 'The Director set this strategic goal:'
    if ($DirectorBriefing) {
        $firstLines = ($DirectorBriefing -split "`n" | Select-Object -First 5) -join ' '
        $parts += $firstLines
    }
    $parts += '---'
    $parts += "Foreman 1 reviewed the worker output for task $($Task.Name) and wrote a verdict."
    $parts += "Read Foreman 1''s review at: $F1ReviewFile"
    $parts += "Read the task doc: $($Task.Doc)"
    $parts += "Read the worker output under: $outputDir"
    $parts += 'Your job: verify Foreman 1''s verdict is correct. Check that:'
    $parts += '1. The evidence Foreman 1 cites actually exists in the output files'
    $parts += '2. The verdict matches what the evidence shows'
    $parts += '3. Nothing important was missed'
    $parts += 'First line: VERDICT: AGREE or VERDICT: DISAGREE'
    $parts += 'Second line exactly TASK_VERDICT: PASS or TASK_VERDICT: FAIL or TASK_VERDICT: ESCALATE. If DISAGREE, explain the correction. Put the controlling failure reason first.'
    $parts += 'Bullet your findings with file paths.'

    $prompt = $parts -join ' '

    $result = Invoke-Codex -Model $Foreman2Model -Effort 'high' -Prompt $prompt -Label "$($Task.Name) F2-verify $VerifyNum"

    [System.IO.File]::WriteAllText($verifyFile, $result.Output, [System.Text.UTF8Encoding]::new($false))

    $verdict = 'DISAGREE'
    if ($result.Output -match '\A\s*VERDICT:\s*(AGREE|DISAGREE)\s*(?:\r?\n|$)') {
        $verdict = $Matches[1]
    }

    Write-Log "$($Task.Name) F2-verify $VerifyNum -- verdict: $verdict"
    Add-Handoff 'Foreman2' 'Foreman1, Worker' "$($Task.Name): $verdict" $verifyFile
    return @{ Verdict = $verdict; VerifyFile = $verifyFile; Output = $result.Output }
}

# -- Per-task execution (full 4-tier pipeline) --------------------------

function Execute-Task {
    param([hashtable]$Task, [string]$RoundName, [string]$DirectorBriefing)

    $taskStart = Get-Date
    $revisionCount = 0
    $revisionFeedback = ''
    $totalAttempts = 0

    while ($true) {
        $workerResult = Invoke-WorkerWithRetry -Task $Task -Revision $revisionFeedback -DirectorBriefing $DirectorBriefing
        $totalAttempts += $workerResult.Attempt

        if ($workerResult.Status -ne 'OK') {
            $duration = [math]::Round(((Get-Date) - $taskStart).TotalMinutes, 1)
            return @{
                Status   = $workerResult.Status
                Attempts = $totalAttempts
                Start    = $taskStart
                Duration = $duration
                Reason   = "Worker $($workerResult.Status) on attempt $($workerResult.Attempt)"
                LogFile  = $workerResult.LogFile
            }
        }

        $gateResult = Test-Gates -Task $Task
        if (-not $gateResult.Pass) {
            $duration = [math]::Round(((Get-Date) - $taskStart).TotalMinutes, 1)
            if ($gateResult.Escalate) {
                return @{
                    Status = 'ESCALATE'; Attempts = $totalAttempts
                    Start = $taskStart; Duration = $duration
                    Reason = $gateResult.Reason; LogFile = $workerResult.LogFile
                }
            }
            return @{
                Status = 'GATE-FAIL'; Attempts = $totalAttempts
                Start = $taskStart; Duration = $duration
                Reason = "Gate failure: $($gateResult.Reason) Missing: $($gateResult.Missing -join ', ')"
                LogFile = $workerResult.LogFile
            }
        }

        if ($SkipReview) {
            $duration = [math]::Round(((Get-Date) - $taskStart).TotalMinutes, 1)
            return @{
                Status = 'PASS'; Attempts = $totalAttempts
                Start = $taskStart; Duration = $duration
                Reason = ''; LogFile = $workerResult.LogFile
            }
        }

        # Foreman 1 reviews worker output
        $f1Result = Invoke-Foreman1Review -Task $Task -ReviewNum $revisionCount -DirectorBriefing $DirectorBriefing

        # Foreman 2 (Sol) verifies Foreman 1's review
        $f2Result = Invoke-Foreman2Verify -Task $Task -F1ReviewFile $f1Result.ReviewFile `
            -DirectorBriefing $DirectorBriefing -VerifyNum $revisionCount

        # Determine final verdict
        if ($f2Result.Verdict -eq 'AGREE') {
            $finalVerdict = $f1Result.Verdict
            Write-Log "$($Task.Name) -- F2 agrees with F1: $finalVerdict"
        }
        else {
            # Sol disagrees - Sol's judgment overrides
            Write-Log "$($Task.Name) -- F2 DISAGREES with F1 ($($f1Result.Verdict))"
            if ($f2Result.Output -match '(?m)^TASK_VERDICT:\s*(PASS|FAIL|ESCALATE)\s*$') {
                $finalVerdict = $Matches[1]
            }
            else {
                $finalVerdict = 'FAIL'
            }
            Write-Log "$($Task.Name) -- F2 override verdict: $finalVerdict"
        }

        $controllingReason = $f1Result.TopReason
        if ($f2Result.Verdict -ne 'AGREE') { $controllingReason = Get-TopReason $f2Result.Output }
        if ($f2Result.Output -notmatch '(?m)^TASK_VERDICT:\s*(PASS|FAIL|ESCALATE)\s*$') {
            $finalVerdict = 'FAIL'
            $controllingReason = 'F2 omitted the required structured task verdict.'
        }
        elseif ($f2Result.Verdict -eq 'AGREE' -and $Matches[1] -ne $f1Result.Verdict) {
            $finalVerdict = 'FAIL'
            $controllingReason = 'F2 claimed agreement but supplied a conflicting task verdict.'
        }

        if ($finalVerdict -eq 'PASS') {
            $duration = [math]::Round(((Get-Date) - $taskStart).TotalMinutes, 1)
            return @{
                Status = 'PASS'; Attempts = $totalAttempts
                Start = $taskStart; Duration = $duration
                Reason = ''; ReviewFile = $f1Result.ReviewFile
                VerifyFile = $f2Result.VerifyFile
                LogFile = $workerResult.LogFile
            }
        }

        if ($finalVerdict -eq 'ESCALATE') {
            $duration = [math]::Round(((Get-Date) - $taskStart).TotalMinutes, 1)
            return @{
                Status = 'ESCALATE'; Attempts = $totalAttempts
                Start = $taskStart; Duration = $duration
                Reason = $controllingReason; ReviewFile = $f1Result.ReviewFile
                VerifyFile = $f2Result.VerifyFile
                LogFile = $workerResult.LogFile
            }
        }

        $revisionCount++
        if ($revisionCount -gt $MaxRevisions) {
            $duration = [math]::Round(((Get-Date) - $taskStart).TotalMinutes, 1)
            return @{
                Status = 'FAIL'; Attempts = $totalAttempts
                Start = $taskStart; Duration = $duration
                Reason = $controllingReason; ReviewFile = $f1Result.ReviewFile
                VerifyFile = $f2Result.VerifyFile
                LogFile = $workerResult.LogFile
            }
        }

        Write-Log "$($Task.Name) -- FAIL, starting revision $revisionCount/$MaxRevisions"
        $revisionFeedback = $f1Result.FullReview
        if ($f2Result.Verdict -eq 'DISAGREE') {
            $revisionFeedback += "`r`n`r`n--- Foreman 2 (Sol) additional findings ---`r`n" + $f2Result.Output
        }
    }
}

# -- Round execution ----------------------------------------------------

function Invoke-Round {
    param([array]$TaskList, [string]$RoundName, [string]$DirectorBriefing)

    Append-Digest "# Round $RoundName"
    Append-Digest "Started: $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
    Append-Digest "Director: $DirectorModel | Foreman1: $Foreman1Model | Foreman2: $Foreman2Model | Worker: $WorkerModel"
    Append-Digest "Tasks: $(($TaskList | ForEach-Object { $_.Name }) -join ', ')"
    Append-Digest '---'
    Append-Digest ''

    $passCount = 0
    $totalCount = $TaskList.Count
    $finalStatus = 'COMPLETE'
    $lastFailTask = ''
    $lastFailReason = ''

    foreach ($task in $TaskList) {
        if (Test-ShouldStop) {
            $finalStatus = 'STOPPED'
            Append-Digest "## STOPPED before $($task.Name)"
            break
        }

        if (Test-TaskPassed -TaskName $task.Name -Round $RoundName -Task $task) {
            Write-Log "$($task.Name) -- already PASS in state.json, skipping."
            Append-Digest "## $($task.Name) - SKIPPED (prior PASS)"
            Append-Digest ''
            $passCount++
            continue
        }

        Write-Log "=== Starting $($task.Name) ==="
        $result = Execute-Task -Task $task -RoundName $RoundName -DirectorBriefing $DirectorBriefing

        $endTime = Get-Date
        $reviewRef = ''
        if ($result.ContainsKey('ReviewFile') -and $result.ReviewFile) {
            $reviewRef = (Split-Path $result.ReviewFile -Leaf)
        }
        $verifyRef = ''
        if ($result.ContainsKey('VerifyFile') -and $result.VerifyFile) {
            $verifyRef = (Split-Path $result.VerifyFile -Leaf)
        }

        Append-Digest "## $($task.Name) - $($result.Status)"
        Append-Digest "- Attempts: $($result.Attempts)"
        Append-Digest "- Start: $($result.Start.ToString('yyyy-MM-dd HH:mm'))"
        Append-Digest "- End: $($endTime.ToString('yyyy-MM-dd HH:mm'))"
        Append-Digest "- Duration: $($result.Duration) min"
        if ($reviewRef) {
            Append-Digest "- F1 Review: overnight\logs\$reviewRef"
        }
        if ($verifyRef) {
            Append-Digest "- F2 Verify: overnight\logs\$verifyRef"
        }
        if ($result.Status -ne 'PASS' -and $result.Reason) {
            Append-Digest "- Reason: $($result.Reason)"
        }
        Append-Digest ''

        if ($result.Status -eq 'PASS' -and $script:GitManaged) {
                & (Join-Path $ProjectRoot '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'team_git.py') checkpoint --label "Reviewed task: $($task.Name)" --push-if-approved
                if ($LASTEXITCODE -ne 0) { throw 'Git checkpoint or GitHub backup failed; stopping before more work.' }
                Send-TeamPing 'TASK-PASS'
        }
        Save-TaskState -TaskName $task.Name -Round $RoundName `
            -Status $result.Status -Verdict $result.Status -Task $task

        if ($result.Status -eq 'PASS') {
            $passCount++
            Write-Log "$($task.Name) -- PASS"
            continue
        }

        Write-Log "$($task.Name) -- $($result.Status): $($result.Reason)"
        $lastFailTask = $task.Name
        $lastFailReason = $result.Reason

        if ($result.Status -eq 'STOPPED') { $finalStatus = 'STOPPED'; break }
        if ($task.ContinueOnFail) {
            Write-Log "$($task.Name) -- ContinueOnFail set, advancing."
            continue
        }

        $finalStatus = $result.Status
        break
    }

    if ($finalStatus -eq 'COMPLETE' -and $lastFailTask) { $finalStatus = 'FAIL' }
    $elapsed = [math]::Round(((Get-Date) - $RunStart).TotalMinutes, 1)
    Append-Digest '---'
    Append-Digest "## Round $RoundName Summary"
    Append-Digest "- Passed: $passCount / $totalCount"
    Append-Digest "- Final status: $finalStatus"
    Append-Digest "- Elapsed: $elapsed min"
    Append-Digest '- B6 not run - review results, then run it in a supervised session.'
    Append-Digest ''

    Write-Log "Round $RoundName done -- $passCount/$totalCount passed, status: $finalStatus"

    return @{
        Status      = $finalStatus
        PassCount   = $passCount
        TotalCount  = $totalCount
        FailTask    = $lastFailTask
        FailReason  = $lastFailReason
        RoundName   = $RoundName
    }
}

# -- Manifest loading (Phase 2) -----------------------------------------

function Load-Manifest {
    param([string]$ManifestPath)
    $raw = Get-Content $ManifestPath -Raw -Encoding UTF8
    $m = $raw | ConvertFrom-Json
    $taskList = @()
    foreach ($t in @(Get-ObjectProperty $m 'tasks')) {
        $gateFiles = @()
        foreach ($gf in @(Get-ObjectProperty $t 'gate_files')) {
            $gateFiles += (Join-Path $ProjectRoot $gf)
        }
        $jsonGates = @()
        foreach ($jg in @(Get-ObjectProperty $t 'json_gates')) {
            $file = [string](Get-ObjectProperty $jg 'file')
            $path = [string](Get-ObjectProperty $jg 'path')
            $pointer = [string](Get-ObjectProperty $jg 'pointer')
            $hasEscalate = Test-ObjectProperty $jg 'escalate_if'
            $hasExpected = Test-ObjectProperty $jg 'expect'
            $gate = @{ File=''; JsonPath=$path; JsonPointer=$pointer; Mode=''; SchemaError='' }
            if ($file) { $gate.File = Join-Path $ProjectRoot $file }
            if ($path -and $hasEscalate -and -not $pointer -and -not $hasExpected) {
                $gate.Mode = 'EscalateIf'
                $gate.EscalateIf = Get-ObjectProperty $jg 'escalate_if'
            }
            elseif ($pointer -and $hasExpected -and -not $path -and -not $hasEscalate) {
                $gate.Mode = 'Expected'
                $gate.Expected = Get-ObjectProperty $jg 'expect'
            }
            else {
                $gate.SchemaError = 'JSON gate must use either path + escalate_if or pointer + expect'
            }
            if (-not $file) { $gate.SchemaError = 'JSON gate is missing file' }
            $jsonGates += $gate
        }
        $contOnFail = $false
        if (Get-ObjectProperty $t 'continue_on_fail') { $contOnFail = $true }
        $taskList += @{
            Name           = Get-ObjectProperty $t 'name'
            Doc            = Get-ObjectProperty $t 'doc'
            TimeoutMin     = Get-ObjectProperty $t 'timeout_min'
            GateFiles      = $gateFiles
            JsonGates      = $jsonGates
            ContinueOnFail = $contOnFail
        }
    }
    return @{ Round = $m.round; Tasks = $taskList }
}

function Validate-Manifest {
    param([hashtable]$ManifestData)
    $errors = @()
    if (-not $ManifestData.Round) { $errors += 'Missing round name' }
    if (-not $ManifestData.Tasks -or $ManifestData.Tasks.Count -eq 0) {
        $errors += 'No tasks defined'
    }
    if ($ManifestData.Tasks.Count -gt 8) {
        $errors += "Too many tasks ($($ManifestData.Tasks.Count) > 8)"
    }
    $taskNames = @{}
    foreach ($t in $ManifestData.Tasks) {
        if (-not $t.Name -or $taskNames.ContainsKey($t.Name)) { $errors += 'Missing or duplicate task name' }
        else { $taskNames[$t.Name] = $true }
        $docFull = Join-Path $ProjectRoot $t.Doc
        if (-not (Test-ContainedPath $docFull (Join-Path $ProjectRoot 'docs'))) { $errors += 'Task doc must remain under project docs' }
        if (-not (Test-Path $docFull)) {
            $errors += "Task $($t.Name): doc not found ($($t.Doc))"
        }
        if ($t.TimeoutMin -le 0 -or $t.TimeoutMin -gt 480) {
            $errors += "Task $($t.Name): timeout must be 1-480 minutes"
        }
        if (@($t.GateFiles).Count -eq 0) { $errors += "Task $($t.Name): no gate files" }
        foreach ($jg in @($t.JsonGates)) {
            if ($jg.SchemaError) { $errors += "Task $($t.Name): $($jg.SchemaError)" }
            elseif ($jg.Mode -eq 'Expected' -and -not $jg.JsonPointer.StartsWith('/')) {
                $errors += "Task $($t.Name): JSON pointer must start with / ($($jg.JsonPointer))"
            }
        }
        foreach ($gf in @($t.GateFiles) + @($t.JsonGates | ForEach-Object { $_.File })) {
            if (-not (Test-ContainedPath $gf $ArtifactRoot)) { $errors += "Task $($t.Name): gate path escapes artifact directory ($gf)" }
        }
    }
    return ,$errors
}

# -- Phase 2: planner (Foreman 1 creates rounds, Foreman 2 verifies) ----

function Build-PlannerPrompt {
    param([string]$RoundName, [string]$RoundContextDir, [string]$DirectorBriefing)
    $lines = @()
    if ($DirectorBriefing) {
        $lines += '=== DIRECTOR BRIEFING ==='
        $lines += $DirectorBriefing
        $lines += '=== END DIRECTOR BRIEFING ==='
        $lines += ''
    }
    $lines += 'You are Foreman 1 (the round planner) for the product repository at'
    $lines += "$ProjectRoot. Your constitution is"
    $lines += 'docs/orchestration/PLANNER_CHARTER.md - read it first and obey it'
    $lines += 'exactly; when uncertain whether something is authorized, it is not.'
    $lines += "Read the charter and $RoundContextDir/CONTEXT.md. Use the supplied context"
    $lines += 'packet, latest round reports, and relevant unresolved messages. Search'
    $lines += 'history by exact task ID only when needed; do not read entire logs.'
    $lines += 'Handle the supplied inbox batch and retrieve additional messages only'
    $lines += 'when relevant to this assignment or a proposed resolution. Other messages'
    $lines += 'remain queued. Completion is blocked by unresolved questions without dispositions.'
    $lines += 'Verify claims against the artifact files before trusting them.'
    $lines += "Also write $(Join-Path $OvernightDir 'memory/candidate.json') using CONTEXT_PROTOCOL.md."
    $lines += 'This is required for every outcome. Propose a complete compact summary'
    $lines += 'based on the current memory revision, cite exact evidence files and'
    $lines += 'explicitly resolve messages only when evidence warrants it. F2 checks'
    $lines += 'both your plan/outcome and this memory candidate before publication.'
    $lines += 'Classify as DONE candidate, STUCK (technical impasse), BLOCKED (owner-only), or CONTINUE and'
    $lines += 'BLOCKED is reserved for a required external input or access, or a major path decision substantially changing scope, acceptance criteria, cost, or intended outcome. Routine orchestration repair, provider waits, Git checkpoints, plan revisions, review disagreements, and implementation choices stay inside the team. Exhaust bounded technical alternatives through the Director first. A completed goal must become DONE candidate; do not invent extra work.'
    $lines += 'produce exactly one signal file: COMPLETION_REPORT.md, director_request.md, OWNER_QUESTIONS.md, or next_round.txt under overnight. STUCK must name the evidence, attempted approaches and guidance needed. Ordinary failed tasks should get a revised evidence-backed plan; do not call the Director each round.'
    $lines += 'If CONTINUE, also write the new manifest path into'
    $lines += 'out/orchestration/runtime/next_round.txt.'
    $lines += 'Do not edit any production script, any existing task doc, the charter,'
    $lines += 'or the supervisor. Then STOP.'
    return ($lines -join "`r`n")
}

function Build-PlanRevisionPrompt {
    param([string]$BasePlannerPrompt, [string]$SolFeedback)
    return ($BasePlannerPrompt + "`r`n`r`nForeman 2 (Sol) reviewed your round and returned these findings:`r`n$SolFeedback`r`nAddress them within the charter.")
}

function Build-PlanReviewPrompt {
    param([string]$NewRoundDir, [string]$PrevContextDir, [string]$DirectorBriefing)
    $parts = @()
    $parts += 'You are Foreman 2, verifying a PLAN created by Foreman 1.'
    if ($DirectorBriefing) {
        $parts += 'The Director''s strategic goal:'
        $firstLines = ($DirectorBriefing -split "`n" | Select-Object -First 3) -join ' '
        $parts += $firstLines
        $parts += '---'
    }
    $parts += "Read docs/orchestration/PLANNER_CHARTER.md, the new round directory at $NewRoundDir,"
    $parts += "the previous round CONTEXT at $PrevContextDir/CONTEXT.md,"
    $parts += 'Use the supplied context packet and latest relevant reports; retrieve history selectively.'
    $parts += 'Verdict APPROVE only if: every claim in the new CONTEXT.md matches the artifacts on disk;'
    $parts += 'every task is bounded with hard prohibitions, exact output paths, a machine-checkable'
    $parts += 'Done-when, and a STOP; nothing violates the charter forbidden list;'
    $parts += 'the manifest matches the docs; and the plan attacks the actual failure the evidence shows.'
    $parts += 'A plan that needs owner input is VERDICT: BLOCKED.'
    $parts += 'First line exactly VERDICT: APPROVE or VERDICT: REVISE or VERDICT: BLOCKED,'
    $parts += 'then bullet findings with paths.'
    return ($parts -join ' ')
}

function Invoke-Planner {
    param([string]$RoundName, [string]$RoundContextDir, [string]$Revision, [string]$DirectorBriefing)
    Archive-PlannerSignals
    Initialize-TeamContext
    $candidatePath = Join-Path $OvernightDir 'memory/candidate.json'
    if (Test-Path $candidatePath) {
        Move-Item -LiteralPath $candidatePath -Destination (Join-Path $LogDir ("old_candidate_" + [Guid]::NewGuid().ToString('N') + '.json'))
    }
    $prompt = Build-PlannerPrompt $RoundName $RoundContextDir $DirectorBriefing
    if ($Revision) { $prompt = Build-PlanRevisionPrompt $prompt $Revision }
    $r = Invoke-AgentProcess 'Foreman1' $Foreman1Model 'medium' $prompt "planner-$RoundName"
    if ($r.Status -ne 'OK') { return @{Status='PLANNER-ERROR'; Reason="$($r.Status): $($r.LogFile)"} }
    $signals = @(
        @{Path=$CompletionReportPath; Status='DONE'}, @{Path=$OwnerQuestionsPath; Status='BLOCKED'},
        @{Path=$DirectorRequestPath; Status='STUCK'}, @{Path=$NextRoundFile; Status='CONTINUE'}
    )
    $present = @($signals | Where-Object { Test-Path -LiteralPath $_.Path })
    if ($present.Count -ne 1) {
        # Planner output is untrusted protocol input, not a supervisor defect.
        # Preserve the ambiguity and route it through F2/Director instead of
        # crashing the coordinator and involving the owner.
        $incidentPath=Join-Path $LogDir ("planner-signal-conflict-" + [Guid]::NewGuid().ToString('N') + '.md')
        $detail=@("# Planner signal protocol conflict",'',"Expected exactly one fresh signal; found $($present.Count).",'')
        foreach ($item in $present) {
            $body=[string](Get-Content -LiteralPath $item.Path -Raw -Encoding UTF8)
            if ($body.Length -gt 1600) { $body=$body.Substring(0,1600) + "`r`n[truncated]" }
            $detail += "## $($item.Status): $($item.Path)"
            $detail += $body
            $detail += ''
        }
        if (-not $present.Count) { $detail += 'The planner returned successfully without creating a signal file.' }
        [IO.File]::WriteAllText($incidentPath,($detail -join "`r`n"),[Text.UTF8Encoding]::new($false))
        Add-Handoff 'Supervisor' 'Foreman2, Director' 'Planner signal conflict requires technical resolution; supervisor remains healthy.' $incidentPath
        return @{Status='STUCK'; Evidence=$incidentPath}
    }
    $signal = $present[0]
    if ([string]::IsNullOrWhiteSpace([string](Get-Content $signal.Path -Raw))) {
        return @{Status='PLANNER-ERROR'; Reason='Empty planner signal'}
    }
    Add-Handoff 'Foreman1' 'Foreman2' "Planner proposes $($signal.Status)" $signal.Path
    if ($signal.Status -ne 'CONTINUE') { return @{Status=$signal.Status; Evidence=$signal.Path} }
    $manifestPath = (Get-Content $NextRoundFile -Raw -Encoding UTF8).Trim()
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot $manifestPath))) {
        return @{Status='PLANNER-ERROR'; Reason="Missing manifest: $manifestPath"}
    }
    return @{Status='CONTINUE'; ManifestPath=$manifestPath}
}


function Invoke-PlanReview {
    param([string]$NewRoundDir, [string]$PrevContextDir, [int]$ReviewNum, [string]$DirectorBriefing)

    $reviewFile = Join-Path $LogDir ("plan_review_$ReviewNum`_" + [Guid]::NewGuid().ToString("N") + ".md")
    $prompt = Build-PlanReviewPrompt -NewRoundDir $NewRoundDir -PrevContextDir $PrevContextDir -DirectorBriefing $DirectorBriefing
    try { $bundle = Get-ContextReviewBundle }
    catch { return @{Verdict='REVISE'; ReviewFile=''; FullReview="Memory candidate invalid: $_"} }
    $prompt += ' ' + (Get-ContextReviewInstruction $bundle)

    $result = Invoke-Codex -Model $Foreman2Model -Effort 'high' -Prompt $prompt -Label "Plan review $ReviewNum"

    [System.IO.File]::WriteAllText($reviewFile, $result.Output, [System.Text.UTF8Encoding]::new($false))

    $verdict = 'REVISE'
    if ($result.Output -match '\A\s*VERDICT:\s*(APPROVE|REVISE|BLOCKED)\s*(?:\r?\n|$)') {
        $verdict = $Matches[1]
    }
    if ($verdict -eq 'APPROVE') {
        try { Publish-TeamContext $bundle $reviewFile | Out-Null }
        catch { return @{Verdict='REVISE'; ReviewFile=$reviewFile; FullReview="Memory publication rejected: $_"} }
    }

    Write-Log "Plan review $ReviewNum -- verdict: $verdict"
    return @{ Verdict = $verdict; ReviewFile = $reviewFile; FullReview = $result.Output }
}

# -- Phase 2: round loop -----------------------------------------------

function Invoke-RoundLoop {
    param([hashtable]$LastRoundResult, [string]$DirectorBriefing)
    $roundsRun = 0
    if (-not $PlanFirst) { $roundsRun = 1 }
    $prevContextDir = Split-Path $taskList[0].Doc -Parent
    $currentRoundName = $LastRoundResult.RoundName
    $feedback = ''
    $planRevisions = 0
    $progressPath = Join-Path $OvernightDir 'no-progress.json'
    $failedRounds = 0
    $directorRecoveries = 0
    if (Test-Path $progressPath) {
        $progress=Get-Content $progressPath -Raw | ConvertFrom-Json
        $failedRounds=[int]$progress.failed_rounds
        if ($progress.PSObject.Properties['director_recoveries']) { $directorRecoveries=[int]$progress.director_recoveries }
    }
    while ($true) {
        if (Test-ShouldStop) { $script:TerminalStatus='STOPPED'; return }
        if ($failedRounds -ge 3) {
            $failureSummary="Three unsuccessful rounds require a new technical strategy. Last round: $currentRoundName. Failed-round count: $failedRounds. Review digest.md, state.json, communications.md, and the latest task/review artifacts. This is a technical impasse, not an owner question."
            [IO.File]::WriteAllText($DirectorRequestPath,$failureSummary,[Text.UTF8Encoding]::new($false))
            $d=Invoke-Director @() $currentRoundName 'STUCK'
            if ($d.Status -in @('BLOCKED','STOPPED')) { $script:TerminalStatus=$d.Status; return }
            $DirectorBriefing=$d.Plan
            $feedback=$d.Plan
            $directorRecoveries++
            $failedRounds=0
            Write-TeamJson $progressPath @{failed_rounds=$failedRounds;director_recoveries=$directorRecoveries;updated=(Get-Date).ToString('o')}
            continue
        }
        $planner = Invoke-Planner $currentRoundName $prevContextDir $feedback $DirectorBriefing
        if ($planner.Status -eq 'PLANNER-ERROR') {
            $feedback="Planner protocol/transport failure: $($planner.Reason)"
            Add-Handoff 'Supervisor' 'Foreman1' 'Planner failure returned for a fresh bounded revision; supervisor remains healthy.' $planner.Reason
            $planRevisions++
            if ($planRevisions -lt 2) { continue }
            [IO.File]::WriteAllText($DirectorRequestPath,$feedback,[Text.UTF8Encoding]::new($false))
            $d=Invoke-Director @() $currentRoundName 'STUCK'
            if ($d.Status -in @('BLOCKED','STOPPED')) { $script:TerminalStatus=$d.Status; return }
            $DirectorBriefing=$d.Plan
            $feedback=$d.Plan
            $planRevisions=0
            $directorRecoveries++
            continue
        }
        if ($planner.Status -ne 'CONTINUE') {
            $check = Invoke-ForemanStateReview $planner
            $checkFile = Save-AgentReply 'f2_state' $check.Output
            Add-Handoff 'Foreman2' 'Foreman1, Director' "Review $($planner.Status)" $checkFile
            if ($check.Output -notmatch '\A\s*VERDICT:\s*APPROVE\s*(?:\r?\n|$)') {
                $feedback = $check.Output
                $planRevisions++
                if ($planRevisions -lt 2) { continue }
                $reason = 'STUCK'
            }
            elseif ($planner.Status -eq 'BLOCKED') { $reason = 'OWNER-CANDIDATE' }
            elseif ($planner.Status -eq 'DONE') { $reason = 'COMPLETION' }
            else { $reason = 'STUCK' }
            $d = Invoke-Director @() $currentRoundName $reason
            if ($d.Status -in @('DONE','BLOCKED','STOPPED')) { $script:TerminalStatus=$d.Status; return }
            $DirectorBriefing = $d.Plan
            $feedback = $d.Plan
            $planRevisions = 0
            $directorRecoveries++
            continue
        }
        $newDir = Split-Path $planner.ManifestPath -Parent
        $data = $null
        $errors = @()
        try {
            $data = Load-Manifest (Join-Path $ProjectRoot $planner.ManifestPath)
            $errors = Validate-Manifest $data
        }
        catch {
            # Agent-authored plans are untrusted input. Return parser/schema failures
            # to the reviewed planning loop instead of terminating the supervisor.
            $errors = @("Manifest could not be loaded: $($_.Exception.Message)")
        }
        if ($errors.Count -gt 0) {
            $review = @{Verdict='REVISE'; FullReview=($errors -join '; ')}
        }
        else { $review = Invoke-PlanReview $newDir $prevContextDir $planRevisions $DirectorBriefing }
        if ($review.Verdict -ne 'APPROVE') {
            $feedback = $review.FullReview
            $planRevisions++
            Add-Handoff 'Foreman2' 'Foreman1' "Plan $($review.Verdict): $feedback"
            if ($review.Verdict -eq 'BLOCKED') {
                [IO.File]::WriteAllText($OwnerQuestionsPath, $feedback, [Text.UTF8Encoding]::new($false))
                [IO.File]::WriteAllText($DirectorRequestPath, $feedback, [Text.UTF8Encoding]::new($false))
                $d = Invoke-Director @() $currentRoundName 'OWNER-CANDIDATE'
                if ($d.Status -in @('BLOCKED','STOPPED')) { $script:TerminalStatus=$d.Status; return }
                $DirectorBriefing = $d.Plan
                $feedback = $d.Plan
                $planRevisions = 0
                $directorRecoveries++
                continue
            }
            if ($planRevisions -ge 2) {
                [IO.File]::WriteAllText($DirectorRequestPath, $feedback, [Text.UTF8Encoding]::new($false))
                $d = Invoke-Director @() $currentRoundName 'STUCK'
                if ($d.Status -in @('BLOCKED','STOPPED')) { $script:TerminalStatus=$d.Status; return }
                $DirectorBriefing = $d.Plan
                $feedback = $d.Plan
                $planRevisions = 0
                $directorRecoveries++
            }
            continue
        }
        # A configured round budget is a Director review boundary, never an
        # autonomous stop authority.
        if ($MaxRounds -gt 0 -and $roundsRun -ge $MaxRounds) {
            [IO.File]::WriteAllText($DirectorRequestPath,"Configured round review boundary reached after $roundsRun rounds. Decide the next bounded technical strategy; this is not owner input.",[Text.UTF8Encoding]::new($false))
            $d = Invoke-Director @() $currentRoundName 'STUCK'
            if ($d.Status -in @('BLOCKED','STOPPED')) { $script:TerminalStatus=$d.Status; return }
            $DirectorBriefing=$d.Plan
            $feedback=$d.Plan
            $roundsRun=0
            $directorRecoveries++
            continue
        }
        $prevContextDir = $newDir
        $currentRoundName = $data.Round
        $roundsRun++
        $feedback = ''
        $planRevisions = 0
        $round = Invoke-Round $data.Tasks $currentRoundName $DirectorBriefing
        if ($round.Status -eq 'COMPLETE') { $failedRounds=0; $directorRecoveries=0 }
        elseif ($round.Status -notin @('STOPPED','CLEANUP-ERROR')) { $failedRounds++ }
        Write-TeamJson $progressPath @{failed_rounds=$failedRounds;director_recoveries=$directorRecoveries;updated=(Get-Date).ToString('o')}
        if ($round.Status -eq 'STOPPED') { $script:TerminalStatus='STOPPED'; return }
        if ($round.Status -eq 'CLEANUP-ERROR') {
            $feedback='An agent process could not be confirmed terminated. Keep all product work paused while the Director chooses and verifies a safe recovery.'
            [IO.File]::WriteAllText($DirectorRequestPath,$feedback,[Text.UTF8Encoding]::new($false))
            $d=Invoke-Director @() $currentRoundName 'STUCK'
            if ($d.Status -in @('BLOCKED','STOPPED')) { $script:TerminalStatus=$d.Status; return }
            $DirectorBriefing=$d.Plan
            $feedback=$d.Plan
            $directorRecoveries++
        }
    }
}


# -- DryRun -------------------------------------------------------------

function Invoke-DryRun {
    Write-Host '=== DRY RUN ==='
    Write-Host ''

    $ok = $true

    Write-Host "Project root: $ProjectRoot"
    Write-Host "Artifact output:   $ArtifactRoot"
    Write-Host "Overnight:    $OvernightDir"
    Write-Host ''

    Write-Host '--- Agent Hierarchy ---'
    Write-Host "  Director  (Tier 1): $DirectorModel  effort: low"
    Write-Host "  Foreman 1 (Tier 2): $Foreman1Model  effort: medium"
    Write-Host "  Foreman 2 (Tier 3): $Foreman2Model  effort: high"
    Write-Host "  Worker    (Tier 4): $WorkerModel  effort: high"
    Write-Host ''

    Write-Host '--- CLI tools ---'
    $claudeCmd = Get-Command claude -ErrorAction SilentlyContinue
    if ($claudeCmd) {
        Write-Host "[OK] claude: $($claudeCmd.Source)"
    }
    else {
        Write-Host '[FAIL] claude not found on PATH'
        $ok = $false
    }

    $codexCmd = Get-Command codex -ErrorAction SilentlyContinue
    if ($codexCmd) {
        Write-Host "[OK] codex: $($codexCmd.Source)"
    }
    else {
        Write-Host '[FAIL] codex not found on PATH'
        $ok = $false
    }
    if (Get-Command opencode -ErrorAction SilentlyContinue) { Write-Host '[OK] opencode found' }
    else { Write-Host '[FAIL] opencode not found on PATH'; $ok = $false }
    Write-Host 'CLI presence does not establish model access; run the model smoke checks.'
    Write-Host ''

    $requestedTasks = $Tasks -split ',' | ForEach-Object { $_.Trim() }
    $allTasks = Build-DefaultTaskTable
    if (-not $Tasks) { $requestedTasks = @($allTasks | ForEach-Object { $_.Name }) }

    Write-Host '--- Task plan ---'
    Write-Host "Tasks: $($requestedTasks -join ', ')"
    Write-Host "MaxHours: $MaxHours | MaxRevisions: $MaxRevisions | SkipReview: $SkipReview"
    Write-Host "EnableRoundLoop: $EnableRoundLoop | MaxRounds: $MaxRounds"
    if ($PlanFirst) { Write-Host 'PlanFirst: F1 evaluates current evidence and F2 reviews before any inherited task executes.' }
    Write-Host ''

    foreach ($name in $requestedTasks) {
        $task = $null
        foreach ($t in $allTasks) {
            if ($t.Name -eq $name) { $task = $t; break }
        }
        if (-not $task) {
            Write-Host "[FAIL] Unknown task: $name"
            $ok = $false
            continue
        }

        $docPath = Join-Path $ProjectRoot $task.Doc
        $docOk = Test-Path $docPath
        if ($docOk) { $status = 'OK' } else { $status = 'FAIL' }
        Write-Host "[$status] $name  doc: $($task.Doc)  timeout: $($task.TimeoutMin)m"
        if (-not $docOk) {
            Write-Host "        doc not found: $docPath"
            $ok = $false
        }
        Write-Host "        gates: $($task.GateFiles -join ', ')"
        if ($task.JsonGates.Count -gt 0) {
            Write-Host "        json-gates: $($task.JsonGates.Count)"
        }
        Write-Host "        continue-on-fail: $($task.ContinueOnFail)"
    }
    Write-Host ''

    if ($Manifest) {
        Write-Host '--- Manifest ---'
        $mPath = Join-Path $ProjectRoot $Manifest
        if (Test-Path $mPath) {
            Write-Host "[OK] Manifest: $Manifest"
            try {
                $mData = Load-Manifest $mPath
                $valErrors = Validate-Manifest $mData
                if ($valErrors.Count -eq 0) {
                    Write-Host "[OK] Manifest valid: round $($mData.Round), $($mData.Tasks.Count) tasks"
                }
                else {
                    foreach ($e in $valErrors) { Write-Host "[FAIL] $e" }
                    $ok = $false
                }
            }
            catch {
                Write-Host "[FAIL] Manifest parse error: $_"
                $ok = $false
            }
        }
        else {
            Write-Host "[FAIL] Manifest not found: $mPath"
            $ok = $false
        }
        Write-Host ''
    }

    if ($ok) {
        Write-Host '=== DRY RUN PASSED ==='
    }
    else {
        Write-Host '=== DRY RUN FAILED ==='
        exit 1
    }
}

# -- Entry point --------------------------------------------------------

if ($LibraryOnly) { return }
if ($PlanFirst) {
    $EnableRoundLoop = $true
}
if ($EnableRoundLoop -and ($SkipDirector -or $SkipReview)) { throw 'Autonomous round loop requires Director and both reviews.' }

if ($DryRun) {
    Invoke-DryRun
    return
}

$requestedTasks = $Tasks -split ',' | ForEach-Object { $_.Trim() }
$allTasks = Build-DefaultTaskTable
if (-not $Tasks) { $requestedTasks = @($allTasks | ForEach-Object { $_.Name }) }
$taskList = @()

if ($Manifest) {
    $mPath = Join-Path $ProjectRoot $Manifest
    $mData = Load-Manifest $mPath
    $valErrors = Validate-Manifest $mData
    if ($valErrors.Count -gt 0) {
        Write-Error "Manifest validation failed: $($valErrors -join '; ')"
        return
    }
    $taskList = $mData.Tasks
    $roundName = $mData.Round
}
else {
    foreach ($name in $requestedTasks) {
        $found = $false
        foreach ($t in $allTasks) {
            if ($t.Name -eq $name) {
                $taskList += $t
                $found = $true
                break
            }
        }
        if (-not $found) {
            Write-Error "Unknown task: $name. Valid tasks: $($allTasks | ForEach-Object { $_.Name })"
            return
        }
    }
    $roundName = 'initial'
}

Write-Log "Overnight runner starting -- round $roundName, tasks: $(($taskList | ForEach-Object { $_.Name }) -join ', ')"
Write-Log "Director: $DirectorModel | Foreman1: $Foreman1Model | Foreman2: $Foreman2Model | Worker: $WorkerModel"
Write-Log "MaxHours: $MaxHours | MaxRevisions: $MaxRevisions | SkipReview: $SkipReview"


# Reuse strategy. The Director is not called at every launch or round.
$runnerLock = $null
try {
    $runnerLock = [IO.File]::Open((Join-Path $OvernightDir 'runner.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    $terminalRecord=Get-DirectorTerminalRecord
    if ($terminalRecord) {
        $script:TerminalStatus=[string]$terminalRecord.status
        return
    }
    & (Join-Path $ProjectRoot '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'team_git.py') check
    if ($LASTEXITCODE -ne 0) { throw 'Git safety check failed. Nothing dispatched.' }
    $script:GitManaged = $true
    Write-Runtime 'STARTING' 'Supervisor' 'Loading strategy'
    $foremanHold=Get-Foreman1EmergencyHoldRecord
    if ($foremanHold) {
        $script:ResolvingForeman1Hold=$true
        try {
            [IO.File]::WriteAllText($DirectorRequestPath,("Foreman1 emergency hold requires Director resolution.`r`nReason: " + $foremanHold.reason + "`r`nEvidence: " + (@($foremanHold.evidence) -join '; ')),[Text.UTF8Encoding]::new($false))
            $holdDecision=Invoke-Director @() $roundName 'FOREMAN1-HOLD'
        }
        finally { $script:ResolvingForeman1Hold=$false }
        if ($holdDecision.Status -ne 'CONTINUE') { $script:TerminalStatus=$holdDecision.Status; return }
        Clear-Foreman1EmergencyHold
        Add-Handoff 'Director' 'Supervisor, Foreman1' 'Director reviewed and released the Foreman1 emergency hold.' $DirectorPlanPath
    }
    $directorBriefing = ''
    if (Test-Path $DirectorPlanPath) { $directorBriefing = [string](Get-Content $DirectorPlanPath -Raw -Encoding UTF8) }
    if (-not $SkipDirector -and [string]::IsNullOrWhiteSpace($directorBriefing)) {
        $d = Invoke-Director $taskList $roundName 'INITIAL'
        if ($d.Status -ne 'CONTINUE') { $script:TerminalStatus=$d.Status; return }
        $directorBriefing = $d.Plan
    }
    if ($PlanFirst) {
        $roundResult = @{Status='PENDING'; RoundName=$roundName}
    }
    else {
        $roundResult = Invoke-Round $taskList $roundName $directorBriefing
    }
    if ($EnableRoundLoop -and $roundResult.Status -notin @('STOPPED','CLEANUP-ERROR','ERROR','TIMEOUT')) {
        Invoke-RoundLoop $roundResult $directorBriefing
    }
    else { $script:TerminalStatus=$roundResult.Status }
}
catch {
    if (-not $runnerLock) { throw 'Another supervisor holds runner.lock, or the lock is inaccessible.' }
    $script:TerminalStatus='SUPERVISOR-ERROR'
    if (Test-ShouldStop) { $script:TerminalStatus='STOPPED' }
    $location = [string]$_.InvocationInfo.PositionMessage
    $stack = [string]$_.ScriptStackTrace
    $script:TerminalAction = "Supervisor error: $($_.Exception.GetType().Name): $($_.Exception.Message)"
    Write-Log "Supervisor error: $($_.Exception.GetType().FullName): $($_.Exception.Message) | $location | $stack"
    Append-Digest "## SUPERVISOR-ERROR`r`n$($_.Exception.GetType().FullName): $($_.Exception.Message)`r`n$location`r`n$stack"
}
finally {
    if ($runnerLock) {
        if ((Test-Foreman1EmergencyHoldAuthorized) -and -not (Test-DirectorPauseAuthorized) -and -not (Test-DirectorTerminalAuthorized)) {
            $script:TerminalStatus='FOREMAN1-HOLD'
            $script:TerminalAction='Foreman1 placed a temporary safety hold while the rate-limited Director is unavailable; automatic Director review remains pending.'
        }
        if ($script:GitManaged -and $script:TerminalStatus -in @('STOPPED','FOREMAN1-HOLD','SUPERVISOR-ERROR')) {
            $checkpointLabel = $(if ($script:TerminalStatus -eq 'FOREMAN1-HOLD') {'Foreman1 emergency hold - awaiting Director review'} elseif ($script:TerminalStatus -eq 'STOPPED') {'Paused work - not yet approved'} else {'Recovery checkpoint - supervisor error - not yet approved'})
            & (Join-Path $ProjectRoot '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'team_git.py') checkpoint --label $checkpointLabel
            if ($LASTEXITCODE -ne 0) { $script:TerminalStatus='SUPERVISOR-ERROR' }
        }
        if ($script:TerminalStatus -ne 'SUPERVISOR-ERROR') { $script:TerminalAction = 'See communications.md and digest.md for next action' }
        Write-Runtime $script:TerminalStatus 'Supervisor' $script:TerminalAction
        Write-Log "Supervisor finished -- status: $script:TerminalStatus"
        $runnerLock.Dispose()
    }
}
if ($script:TerminalStatus -in @('DONE','BLOCKED','SUPERVISOR-ERROR')) {
    Send-Notification $script:TerminalStatus
}
