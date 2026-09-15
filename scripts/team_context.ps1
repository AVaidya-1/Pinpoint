# Durable, bounded context. Supervisor publishes; agents only propose/send.

# Windows background sessions can inherit a module path that does not expose
# Microsoft.PowerShell.Utility. Keep integrity checks independent of module
# auto-loading by using the framework's SHA-256 implementation directly.
function Get-TeamFileHash {
    param([Parameter(Position=0,Mandatory)][string]$Path)
    $stream=$null
    $sha=$null
    try {
        $stream=[IO.File]::OpenRead($Path)
        $sha=[Security.Cryptography.SHA256]::Create()
        return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-','')
    }
    finally {
        if ($sha) { $sha.Dispose() }
        if ($stream) { $stream.Dispose() }
    }
}

function Initialize-TeamContext {
    foreach ($name in @('memory','memory/snapshots','memory/messages','memory/packets')) {
        $dir = Join-Path $OvernightDir $name
        if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    }
}

function Write-TeamJson {
    param([string]$Path, $Value)
    $tmp = "$Path.$([Guid]::NewGuid().ToString('N')).tmp"
    $backup = "$Path.$([Guid]::NewGuid().ToString('N')).bak"
    [IO.File]::WriteAllText($tmp, (ConvertTo-Json -InputObject $Value -Depth 15), [Text.UTF8Encoding]::new($false))
    try {
        for ($attempt=0; $attempt -lt 20; $attempt++) {
            try {
                if ([IO.File]::Exists($Path)) {
                    [IO.File]::Replace($tmp, $Path, $backup, $true)
                    if ([IO.File]::Exists($backup)) { [IO.File]::Delete($backup) }
                }
                else {
                    [IO.File]::Move($tmp, $Path)
                }
                return
            }
            catch [IO.IOException] {
                if ($attempt -ge 19) { throw }
                Start-Sleep -Milliseconds 50
            }
            catch [UnauthorizedAccessException] {
                if ($attempt -ge 19) { throw }
                Start-Sleep -Milliseconds 50
            }
        }
    }
    finally {
        if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
        if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue }
    }
}

function Read-TeamSnapshot {
    $pointer = Join-Path $OvernightDir 'memory/current.json'
    if (-not (Test-Path -LiteralPath $pointer)) { return $null }
    $ref = Get-Content $pointer -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($ref.revision -notmatch '^[a-f0-9]{32}$') { throw 'Invalid memory revision.' }
    $path = Join-Path $OvernightDir "memory/snapshots/$($ref.revision).json"
    if ((Get-TeamFileHash $path) -ne $ref.sha256) { throw 'Published memory changed after approval.' }
    $snapshot = Get-Content $path -Raw -Encoding UTF8 | ConvertFrom-Json
    $plannerAuthored = $snapshot.PSObject.Properties['provenance'] -and $snapshot.provenance -eq 'planner-authored; not independently reviewed'
    if (-not $plannerAuthored -and (Get-TeamFileHash $snapshot.review) -ne $snapshot.review_sha256) { throw 'Memory approval record changed after publication.' }
    return $snapshot
}

function Get-TeamMessages {
    param([string]$Role = 'Team', [switch]$IncludeClosed)
    $snapshot = Read-TeamSnapshot
    $closed = @()
    if ($snapshot) { $closed = @($snapshot.closed_ids) }
    $dir = Join-Path $OvernightDir 'memory/messages'
    if (-not (Test-Path $dir)) { return }
    foreach ($file in (Get-ChildItem $dir -Filter '*.json' -File | Sort-Object Name)) {
        $m = Get-Content $file.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $IncludeClosed -and $m.id -in $closed) { continue }
        if ($Role -notin @('Team','Foreman1','Foreman2') -and $m.to -notin @($Role,'Team')) { continue }
        $m
    }
}

function Send-TeamMessage {
    param([string]$From, [string]$To, [string]$Task, [string]$Kind,
          [string]$Body, [string[]]$Evidence = @(), [string]$ReplyTo = '')
    Initialize-TeamContext
    $roles = @('Owner','Director','Foreman1','Foreman2','Worker','Supervisor','Team')
    if ($From -notin $roles -or $To -notin $roles) { throw 'Unknown message role.' }
    if ($Kind -notin @('QUESTION','ANSWER','FINDING','DECISION')) { throw 'Unknown message kind.' }
    if ([string]::IsNullOrWhiteSpace($Task) -or $Task.Length -gt 100) { throw 'Message requires a short task identifier.' }
    if ([string]::IsNullOrWhiteSpace($Body) -or $Body.Length -gt 3000) { throw 'Message body must contain 1-3000 characters.' }
    if ($Evidence.Count -gt 10 -or ($Evidence -join '').Length -gt 2000) { throw 'Too many evidence references.' }
    if ($ReplyTo) {
        if ($ReplyTo -notmatch '^[0-9]{17}_[a-f0-9]{32}$' -or -not (Test-Path (Join-Path $OvernightDir "memory/messages/$ReplyTo.json"))) {
            throw 'Reply-To must identify an existing message.'
        }
    }
    $id = (Get-Date -Format 'yyyyMMddHHmmssfff') + '_' + [Guid]::NewGuid().ToString('N')
    $m = @{id=$id; from=$From; to=$To; task=$Task; kind=$Kind; body=$Body;
        evidence=@($Evidence); reply_to=$ReplyTo; created=(Get-Date).ToString('o')}
    Write-TeamJson (Join-Path $OvernightDir "memory/messages/$id.json") $m
    $md = "# $Kind | $id`r`nFrom: $From`r`nTo: $To`r`nTask: $Task`r`nReply-To: $ReplyTo`r`n`r`n$Body`r`n`r`nEvidence: $($Evidence -join '; ')"
    [IO.File]::WriteAllText((Join-Path $OvernightDir "memory/messages/$id.md"), $md, [Text.UTF8Encoding]::new($false))
    return $id
}

function Get-TeamInbox {
    param([string]$Role='Team', [string]$Label='')
    Get-TeamMessages $Role | Sort-Object @{Expression={
        if ($_.task -and $Label -match ('(?<![a-zA-Z0-9])' + [regex]::Escape($_.task) + '(?![a-zA-Z0-9])')) { 0 } else { 1 }
    }}, created, id
}

function Get-ContextReviewBundle {
    Initialize-TeamContext
    $path = Join-Path $OvernightDir 'memory/candidate.json'
    if (-not (Test-Path $path)) { throw 'F1 must provide memory/candidate.json before review.' }
    if ((Get-Item $path).Length -gt 40000) { throw 'Context candidate exceeds 40000 bytes.' }
    $candidate = Get-Content $path -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($key in @('base_revision','summary_md','evidence','resolutions')) {
        if (-not $candidate.PSObject.Properties[$key]) { throw "Context candidate missing $key." }
    }
    if ($candidate.summary_md.Length -gt 8000 -or $candidate.summary_md.Length -lt 20) { throw 'Summary must contain 20-8000 characters.' }
    foreach ($heading in @('Goal','Verified facts','Decisions','Hypotheses','Open questions','Next steps')) {
        if ($candidate.summary_md -notmatch "(?m)^## $heading\s*$") { throw "Summary missing heading: $heading" }
    }
    $prior = Read-TeamSnapshot
    $revision = ''
    if ($prior) { $revision = $prior.revision }
    if ([string]$candidate.base_revision -ne $revision) { throw 'Context candidate is based on a stale memory revision.' }
    $messages = @(Get-TeamMessages -IncludeClosed)
    if (@($candidate.resolutions).Count -gt 20) { throw 'Resolve at most 20 messages per review.' }
    foreach ($r in $candidate.resolutions) {
        if (-not ($messages | Where-Object { $_.id -eq $r.id })) { throw "Cannot resolve unknown message $($r.id)" }
        if ([string]::IsNullOrWhiteSpace($r.resolution) -or $r.resolution.Length -gt 1000 -or @($r.evidence).Count -eq 0) {
            throw 'Every resolution needs a concise disposition and evidence.'
        }
    }
    $paths = @($candidate.evidence) + @($candidate.resolutions | ForEach-Object { $_.evidence })
    if ($paths.Count -eq 0 -or $paths.Count -gt 50) { throw 'Context requires 1-50 evidence paths.' }
    $hashes = @{}
    foreach ($rel in $paths) {
        $full = $rel
        if (-not [IO.Path]::IsPathRooted($full)) { $full = Join-Path $ProjectRoot $full }
        if (-not (Test-ContainedPath $full $ProjectRoot) -or -not (Test-Path -LiteralPath $full -PathType Leaf)) {
            throw "Context evidence is missing or outside the project: $rel"
        }
        $hashes[$full] = Get-TeamFileHash $full
    }
    $candidateHash = Get-TeamFileHash $path
    # Reviewer reads a frozen copy, not a mutable candidate file.
    $reviewPath = Join-Path $LogDir ("context_review_" + [Guid]::NewGuid().ToString('N') + '.json')
    Copy-Item -LiteralPath $path -Destination $reviewPath
    return @{Path=$path; ReviewPath=$reviewPath; Hash=$candidateHash; Candidate=$candidate; Prior=$prior; EvidenceHashes=$hashes}
}

function Get-ContextReviewInstruction {
    param($Bundle)
    return "Also review the memory candidate at $($Bundle.ReviewPath). Compare with the current approved snapshot, current task results and supplied inbox batch. Retrieve each message proposed for resolution by ID, plus relevant questions/replies for this assignment; do not load the entire inbox or history. Unhandled messages remain queued independently of the summary. Check every new verified claim against cited evidence; retain material prior decisions, failed approaches and dissent. Hypotheses must stay labeled. Independently verify each proposed message resolution; an answer alone does not close a question. APPROVE only if BOTH this assignment and memory candidate pass. Do not edit memory, evidence or messages."
}

function Publish-TeamContext {
    param($Bundle, [string]$ReviewFile, [switch]$PlannerAuthored)
    $review = ''
    if (-not $PlannerAuthored) { $review = Get-Content $ReviewFile -Raw -Encoding UTF8 }
    if (-not $PlannerAuthored -and $review -notmatch '\A\s*VERDICT:\s*APPROVE\s*(?:\r?\n|$)') { throw 'Reviewed memory publication requires APPROVE.' }
    if ((Get-TeamFileHash $Bundle.Path) -ne $Bundle.Hash -or
        (Get-TeamFileHash $Bundle.ReviewPath) -ne $Bundle.Hash) { throw 'Candidate changed during review.' }
    $current = Read-TeamSnapshot
    $currentRevision = ''
    if ($current) { $currentRevision = $current.revision }
    if ($currentRevision -ne $Bundle.Candidate.base_revision) { throw 'Memory advanced during review.' }
    foreach ($path in $Bundle.EvidenceHashes.Keys) {
        if ((Get-TeamFileHash $path) -ne $Bundle.EvidenceHashes[$path]) { throw "Evidence changed during review: $path" }
    }
    $closed = @()
    if ($current) { $closed = @($current.closed_ids) }
    $closed += @($Bundle.Candidate.resolutions | ForEach-Object { $_.id })
    $revision = [Guid]::NewGuid().ToString('N')
    $snapshot = @{revision=$revision; previous=$currentRevision; approved_at=(Get-Date).ToString('o');
        summary_md=$Bundle.Candidate.summary_md; evidence_hashes=$Bundle.EvidenceHashes;
        resolutions=@($Bundle.Candidate.resolutions); closed_ids=@($closed | Sort-Object -Unique);
        review=$ReviewFile; review_sha256=$(if ($ReviewFile) {Get-TeamFileHash $ReviewFile} else {''});
        provenance=$(if ($PlannerAuthored) {'planner-authored; not independently reviewed'} else {'independently-reviewed'});
        task_state_sha256=''}
    if (Test-Path $StatePath) { $snapshot.task_state_sha256=Get-TeamFileHash $StatePath }
    $path = Join-Path $OvernightDir "memory/snapshots/$revision.json"
    Write-TeamJson $path $snapshot
    [IO.File]::WriteAllText((Join-Path $OvernightDir "memory/snapshots/$revision.md"), $snapshot.summary_md, [Text.UTF8Encoding]::new($false))
    Write-TeamJson (Join-Path $OvernightDir 'memory/current.json') @{revision=$revision; sha256=(Get-TeamFileHash $path)}
    Add-Handoff 'Supervisor' 'Team' "Shared memory published (planner-authored=$PlannerAuthored): $revision" $path
    return $revision
}

function Get-TeamContextPacket {
    param([string]$Role, [string]$Label)
    Initialize-TeamContext
    $snapshot = Read-TeamSnapshot
    $revision = 'NONE'
    $summary = 'No approved summary yet. F1 must bootstrap from the latest task reports and reviewer findings. Historical reports are not automatically verified facts.'
    $stale = $true
    if ($snapshot) {
        $revision = $snapshot.revision
        $summary = $snapshot.summary_md
        $currentHash = ''
        if (Test-Path $StatePath) { $currentHash=Get-TeamFileHash $StatePath }
        $stale = $currentHash -ne $snapshot.task_state_sha256
        foreach ($p in $snapshot.evidence_hashes.PSObject.Properties) {
            if (-not (Test-Path -LiteralPath $p.Name) -or (Get-TeamFileHash $p.Name) -ne $p.Value) { $stale=$true }
        }
    }
    $ownerPath = Join-Path $ProjectRoot 'docs/orchestration/OWNER_BRIEF.md'
    $owner = [string](Get-Content $ownerPath -Raw -Encoding UTF8)
    if ($owner.Length -gt 7000) { throw 'Owner brief exceeds 7000 characters; do not silently truncate constraints.' }
    $messages = @(Get-TeamInbox $Role $Label)
    $lines = @("# Context packet: $Role / $Label", "Memory revision: $revision; stale or uninitialized: $stale", '', $owner,
        '## Saved memory (historical if stale; check evidence for claims)', $(if ($snapshot -and $snapshot.PSObject.Properties['provenance']) { 'Provenance: ' + $snapshot.provenance + "`n" + $summary } else {$summary}), '## Open inbox')
    $included = 0
    $chars = 0
    foreach ($m in $messages) {
        $item = "- [$($m.id)] $($m.kind), $($m.from) -> $($m.to), task=$($m.task), reply-to=$($m.reply_to)`n$($m.body)`nEvidence: $($m.evidence -join '; ')"
        if ($included -ge 8 -or $chars + $item.Length -gt 6500) { break }
        $lines += $item
        $chars += $item.Length
        $included++
    }
    $lines += "Shown $included of $($messages.Count) open messages. Additional messages remain OPEN, not discarded. List the next page using team_message.ps1 -List -Role $Role -Label `"$Label`" -Offset $included."
    $lines += '## Latest recorded task statuses (status is not proof of project completion)'
    if (Test-Path $StatePath) {
        $entries = @(Get-Content $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json)
        foreach ($e in ($entries | Sort-Object timestamp -Descending | Select-Object -First 12)) {
            $lines += "- $($e.round)/$($e.task): $($e.status) at $($e.timestamp)"
        }
    }
    $lines += "## Retrieval`nSearch exact task IDs or filenames in $OvernightDir/communications.md, digest.md, notes.md, logs/ and memory/. Read relevant matches and evidence, not entire histories. Latest task reports override a stale summary. The Foreman checks relevant primary evidence once."
    $packet = $lines -join "`r`n"
    if ($packet.Length -gt 24000) { throw 'Context packet exceeds 24000 characters; do not silently truncate.' }
    $path = Join-Path $OvernightDir ('memory/packets/' + [Guid]::NewGuid().ToString('N') + '.md')
    [IO.File]::WriteAllText($path, $packet, [Text.UTF8Encoding]::new($false))
    Write-TeamJson (Join-Path $OvernightDir 'memory/last_packet.json') @{role=$Role; label=$Label; path=$path;
        revision=$revision; stale=$stale; characters=$packet.Length; open_messages=$messages.Count; shown_messages=$included; created=(Get-Date).ToString('o')}
    return @{Path=$path; Text=$packet}
}
