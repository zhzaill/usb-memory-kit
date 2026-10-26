# memory-kit :: pipeline.ps1  (ASCII only, PowerShell 5.1)
# ONE-SHOT ABSORB: plug the stick into any Windows machine, run this, and the logs of THAT
# machine are archived, chunked, embedded and clustered into the on-stick index.
#
#   collect  -> corpus\<MACHINE>\        (sha256 idempotent archive)
#   chunk    -> index\chunks.jsonl       (rebuild, ~1 s per 100 files)
#   embed    -> index\vectors.jsonl      (incremental, sha-identified chunks only)
#   organize -> index\organization.json  (kNN + Louvain communities, in RAM)
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File pipeline.ps1
#   ... -Roots 'C:\Logs','D:\Projects\Logs'   # explicit, no discovery
#   ... -Yes            # non-interactive: register the single best candidate without asking
#   ... -Sparse         # allow finishing without embeddings (keyword-only index)
#   ... -Serve          # also start the HTTP UI afterwards
param(
  [string[]]$Roots,
  [switch]$Yes,
  [switch]$Sparse,
  [switch]$Serve
)
$ErrorActionPreference = 'Stop'
$kit = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$usbRoot = Split-Path -Parent $kit
$bin = Join-Path $kit 'bin'
$py = Join-Path $kit 'runtime\venv\Scripts\python.exe'
$cfgFile = Join-Path $kit 'config\machines.json'
$kitCfg = Get-Content (Join-Path $kit 'config\kit.json') -Raw | ConvertFrom-Json
$me = $env:COMPUTERNAME
$t0 = Get-Date

function Say($msg) { Write-Host $msg }
function Step($n, $msg) { Write-Host ""; Write-Host ("[{0}/5] {1}" -f $n, $msg) }

# ---------------- 1. roots ----------------
Step 1 "resolve log roots for $me"

$registeredRoots = @()
$registeredFiles = @()
$cfg = Get-Content $cfgFile -Raw | ConvertFrom-Json
$entry = $cfg.PSObject.Properties[$me]
if ($entry) {
  foreach ($r in $entry.Value.roots) {
    $rootPath = if ($r -is [string]) { $r } else { $r.path }
    if ($rootPath -and (Test-Path -LiteralPath $rootPath)) { $registeredRoots += $r }
  }
  foreach ($f in @($entry.Value.files)) {
    if ($f -and (Test-Path -LiteralPath $f -PathType Leaf)) { $registeredFiles += $f }
  }
}

if ($Roots -and $Roots.Count -gt 0) {
  $use = @()
  foreach ($r in $Roots) {
    if (Test-Path -LiteralPath $r) { $use += (Get-Item -LiteralPath $r).FullName }
    else { Say ("  WARN root not found, ignored: {0}" -f $r) }
  }
  if ($use.Count -eq 0) { throw 'none of the given -Roots exists on this machine' }
  Say ("  using explicit roots: {0}" -f ($use -join ', '))
  if (-not $entry -or -not $entry.Value.roots) {
    Say '  registering them for this hostname'
    $cfg | Add-Member -NotePropertyName $me -NotePropertyValue ([pscustomobject]@{ roots = $use; note = ('auto-registered ' + (Get-Date -Format 'yyyy-MM-dd')) }) -Force
    [IO.File]::WriteAllText($cfgFile, (ConvertTo-Json $cfg -Depth 6), (New-Object System.Text.UTF8Encoding($false)))
  }
} elseif ($registeredRoots.Count -gt 0) {
  $use = $registeredRoots
  $rootLabels = @($use | ForEach-Object { if ($_ -is [string]) { $_ } else { "{0}={1}" -f $_.id, $_.path } })
  Say ("  registered roots: {0}" -f ($rootLabels -join ', '))
  if ($registeredFiles.Count -gt 0) {
    Say ("  registered extra files: {0}" -f $registeredFiles.Count)
  }
} else {
  Say ("  {0} is not registered (or its roots vanished) -> discovering ..." -f $me)
  $json = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $bin 'discover-roots.ps1') -Json
  $cands = @()
  try { $cands = @($json | ConvertFrom-Json) } catch { $cands = @() }
  $cands = @($cands | Where-Object { $_ -and $_.path })
  if ($cands.Count -eq 0) {
    throw "no log root found. Re-run with -Roots 'X:\your\Logs' (multiple roots separated by comma)."
  }
  Say '  candidates:'
  $i = 0
  foreach ($c in $cands) { $i++; Say ("   {0,2}. {1,-44} {2,4} md  [{3}]" -f $i, $c.path, $c.count, $c.source) }

  $pick = @()
  if ($cands.Count -eq 1 -or $Yes) {
    $pick = @($cands[0].path)
    Say ("  chosen: {0}" -f $pick[0])
  } else {
    $ans = Read-Host "  register which? (number, comma-separated numbers, or 'a' for all; Enter = 1)"
    if (-not $ans) { $pick = @($cands[0].path) }
    elseif ($ans.Trim().ToLower() -eq 'a') { $pick = @($cands | ForEach-Object { $_.path }) }
    else {
      foreach ($tok in ($ans -split ',')) {
        $n = 0
        if ([int]::TryParse($tok.Trim(), [ref]$n) -and $n -ge 1 -and $n -le $cands.Count) { $pick += $cands[$n - 1].path }
      }
    }
    if ($pick.Count -eq 0) { throw 'no selection made' }
  }

  $cfg | Add-Member -NotePropertyName $me -NotePropertyValue ([pscustomobject]@{ roots = @($pick); note = ('auto-registered ' + (Get-Date -Format 'yyyy-MM-dd')) }) -Force
  [IO.File]::WriteAllText($cfgFile, (ConvertTo-Json $cfg -Depth 6), (New-Object System.Text.UTF8Encoding($false)))
  Say ("  registered {0} root(s) in config\machines.json" -f $pick.Count)
  $use = @($pick)
}

# ---------------- 2. embedding endpoint ----------------
Step 2 'ensure an embedding endpoint'
$live = $null
foreach ($ep in $kitCfg.embed.endpoints) {
  try { if ((Invoke-WebRequest -Uri $ep.health -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) { $live = $ep; break } } catch {}
}
if (-not $live) {
  $localStart = Join-Path $usbRoot 'local-ai\start-local-ai.ps1'
  if (Test-Path $localStart) {
    Say '  none up -> launching the on-stick engine (embedding only)'
    # own process, then poll: piping this child or using Start-Process -Wait both block on the daemon it spawns
    Start-Process -FilePath 'powershell' -WindowStyle Hidden -ArgumentList @(
      '-NoProfile','-ExecutionPolicy','Bypass','-File',$localStart,'-NoChat','-NoBrowser') | Out-Null
    $deadline = (Get-Date).AddSeconds(240)
    while ((Get-Date) -lt $deadline) {
      foreach ($ep in $kitCfg.embed.endpoints) {
        try { if ((Invoke-WebRequest -Uri $ep.health -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200) { $live = $ep; break } } catch {}
      }
      if ($live) { break }
      Start-Sleep -Seconds 1
    }
  }
}
if ($live) { Say ("  endpoint: {0}" -f $live.url) }
else {
  if (-not $Sparse) {
    Say ("  WARN no embedding endpoint. Re-run with -Sparse to build a keyword-only index, or start {0} first." -f (Join-Path $usbRoot '启动本地AI.cmd'))
    throw 'embedding endpoint unavailable'
  }
  Say '  WARN continuing without embeddings (-Sparse): search will be keyword-only for the new chunks'
}

# ---------------- 3. collect ----------------
Step 3 'collect (archive new/changed log files into corpus\)'
$colOut = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $bin 'collect.ps1')
$collectExit = $LASTEXITCODE
$colOut | ForEach-Object { Say ("  " + $_) }
if ($collectExit -ne 0) { throw ("collect.ps1 failed with exit code {0}" -f $collectExit) }
$copied = 0
foreach ($line in $colOut) { if ($line -match 'copied=(\d+)') { $copied = [int]$Matches[1] } }

# ---------------- 4. chunk + embed + organize ----------------
if (-not (Test-Path $py)) { throw ("venv python missing: " + $py) }
$env:JIEBA_CACHE_DIR = Join-Path $kit 'runtime\jieba-cache'
# jieba writes its dict cache through tempfile.gettempdir(), which honours TMP/TEMP on Windows
# (JIEBA_CACHE_DIR alone is not read by every jieba build) -> keep it on the stick.
$tmpDir = Join-Path $kit 'runtime\tmp'
New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null
$env:TMP = $tmpDir
$env:TEMP = $tmpDir

Step 4 'chunk'
$chunkOut = & $py (Join-Path $bin 'chunk.py')
$chunkExit = $LASTEXITCODE
$chunkOut | ForEach-Object { Say ("  " + $_) }
if ($chunkExit -ne 0) { throw ("chunk.py failed with exit code {0}" -f $chunkExit) }
$chunks = 0
foreach ($line in $chunkOut) { if ($line -match 'chunks=(\d+)') { $chunks = [int]$Matches[1] } }

Step 5 'embed + organize'
if ($live -or -not $Sparse) {
  $embOut = & $py (Join-Path $bin 'embed.py')
  $embedExit = $LASTEXITCODE
  $embOut | ForEach-Object { Say ("  " + $_) }
  if ($embedExit -ne 0) { throw ("embed.py failed with exit code {0}" -f $embedExit) }
}
if (-not $Sparse) {
  $check = & $py (Join-Path $bin 'index_status.py') --strict | ConvertFrom-Json
  if ($LASTEXITCODE -ne 0) { throw ("vector ID coverage check failed: {0}" -f ($check | ConvertTo-Json -Compress)) }
  Say ("  coverage check : {0}/{1} chunks; missing={2}, duplicates={3}" -f $check.vectors, $check.chunks, $check.missing, $check.duplicate_vectors)
}
$orgOut = & $py (Join-Path $bin 'organize.py')
$organizeExit = $LASTEXITCODE
$orgOut | ForEach-Object { Say ("  " + $_) }
if ($organizeExit -ne 0) { throw ("organize.py failed with exit code {0}" -f $organizeExit) }

# ---------------- summary ----------------
$el = (Get-Date) - $t0
$vpath = Join-Path $kit 'index\vectors.jsonl'
$nv = 0
if (Test-Path $vpath) { $nv = (Get-Content $vpath | Measure-Object -Line).Lines }
$cpath = Join-Path $kit 'index\chunks.jsonl'
$nc = 0
if (Test-Path $cpath) { $nc = (Get-Content $cpath | Measure-Object -Line).Lines }

Say ''
Say '================ absorb summary ================'
Say ("  machine        : {0}" -f $me)
$summaryRoots = @($use | ForEach-Object { if ($_ -is [string]) { $_ } else { "{0}={1}" -f $_.id, $_.path } })
Say ("  roots          : {0}" -f ($summaryRoots -join ' ; '))
Say ("  extra files    : {0}" -f $registeredFiles.Count)
Say ("  new files      : {0}" -f $copied)
Say ("  chunks (total) : {0}" -f $nc)
Say ("  vectors (total): {0}" -f $nv)
if (-not $Sparse -and $nc -ne $nv) { throw ("vector coverage check failed: chunks={0}, vectors={1}" -f $nc, $nv) }
Say ("  archive        : {0}" -f (Join-Path (Join-Path $kit 'corpus') $me))
Say ("  chunk index    : {0}" -f (Join-Path $kit 'index\chunks.jsonl'))
Say ("  vector index   : {0}" -f (Join-Path $kit 'index\vectors.jsonl'))
Say ("  elapsed        : {0:N1}s" -f $el.TotalSeconds)
Say '================================================'
Say ''
Say ("next: {0}   (http://127.0.0.1:18200)" -f (Join-Path $usbRoot '启动检索.cmd'))

# The HTTP server loads the index once at startup, so a running instance still serves the OLD
# counts after an absorb. Restart it (-Serve) or tell the user to, instead of leaving them
# staring at stale numbers.
$servePort = [int]$kitCfg.search.port
$listening = @(Get-NetTCPConnection -State Listen -LocalPort $servePort -ErrorAction SilentlyContinue).Count -gt 0
if ($listening) {
  if ($Serve) {
    Say ("restarting the HTTP UI (it caches the index in memory) ...")
    Get-NetTCPConnection -State Listen -LocalPort $servePort -ErrorAction SilentlyContinue |
      ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
  } else {
    Say ''
    Say ("NOTE: http://127.0.0.1:{0} is ALREADY running and holds the previous index in memory." -f $servePort)
    Say ("      close that window and double-click {0} again, or re-run this with -Serve." -f (Join-Path $usbRoot '启动检索.cmd'))
  }
}
if ($Serve -or -not $listening) {
  if ($Serve) {
    Start-Process -FilePath 'powershell' -WindowStyle Hidden -ArgumentList @(
      '-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $kit 'start.ps1')) | Out-Null
    Say ("HTTP UI launching on http://127.0.0.1:{0}" -f $servePort)
  }
}
