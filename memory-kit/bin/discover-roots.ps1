# memory-kit :: discover-roots.ps1  (ASCII only, PowerShell 5.1)
# Find this machine's log roots without being told where they are. Four layers, cheapest first:
#   1. already registered roots for this hostname that still exist
#   2. Everything (es.exe) index query, when Everything is installed
#   3. one bounded pass per fixed drive for files named YYYY-MM-DD-*.md, grouped by parent dir
#   4. AGENTS.md / CLAUDE.md anchors: a sibling Logs\ folder next to a workspace instruction file
# Output: candidates sorted by hit count. -Json prints a machine-readable array.
param(
  [switch]$Json,
  [int]$Depth = 6,
  [int]$MaxSecondsPerDrive = 120,
  [int]$MinHits = 2
)
$ErrorActionPreference = 'SilentlyContinue'

$kit = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$cfgFile = Join-Path $kit 'config\machines.json'
$me = $env:COMPUTERNAME
$found = @{}

function Add-Cand([string]$path, [string]$source, [int]$count) {
  if (-not $path) { return }
  $path = $path.TrimEnd('\')
  if ($found.ContainsKey($path)) {
    $c = $found[$path]
    if ($count -gt $c.count) { $c.count = $count }
    if ($c.source -notlike "*$source*") { $c.source = $c.source + '+' + $source }
  } else {
    $found[$path] = [pscustomobject]@{ path = $path; count = $count; source = $source; registered = $false }
  }
}

# ---------- layer 1: registry ----------
$cfg = Get-Content $cfgFile -Raw | ConvertFrom-Json
$entry = $cfg.PSObject.Properties[$me]
if ($entry) {
  foreach ($r in $entry.Value.roots) {
    if (Test-Path -LiteralPath $r) {
      $n = (Get-ChildItem -LiteralPath $r -Recurse -File -Filter '*.md' | Measure-Object).Count
      Add-Cand $r 'registered' $n
      $found[$r.TrimEnd('\')].registered = $true
    }
  }
}

# ---------- layer 2: Everything index ----------
$esCandidates = @(
  'C:\Program Files\Everything\es.exe',
  'C:\Program Files (x86)\Everything\es.exe',
  (Join-Path $env:LOCALAPPDATA 'Programs\Everything\es.exe')
)
$es = $null
foreach ($p in $esCandidates) { if (Test-Path $p) { $es = $p; break } }
if (-not $es) { $es = (Get-Command es.exe -ErrorAction SilentlyContinue).Source }
if ($es) {
  try {
    $lines = & $es -r '\d{4}-\d{2}-\d{2}-[^\\]*\.md$'
    foreach ($g in ($lines | Where-Object { $_ } | ForEach-Object { Split-Path -Parent $_ } | Group-Object)) {
      if ($g.Count -ge $MinHits) { Add-Cand $g.Name 'everything' $g.Count }
    }
  } catch {}
}

# ---------- layer 3: bounded per-drive scan ----------
$skipNames = @('Windows', 'Program Files', 'Program Files (x86)', 'ProgramData', '$Recycle.Bin',
               'System Volume Information', 'node_modules', '.git', 'AppData', 'WindowsApps',
               'steamapps', 'Cache', 'Backup', 'WinSxS', 'Recovery', 'Users\Public', '$WinREAgent')
$skipPattern = '\\(' + (($skipNames | ForEach-Object { [regex]::Escape($_) }) -join '|') + ')\\'

$drives = Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' |
          Where-Object { $_.Size -gt 0 } | ForEach-Object { $_.DeviceID + '\' }
$truncatedDrives = @()
foreach ($root in $drives) {
  if (-not (Test-Path -LiteralPath $root)) { continue }
  $sw = [Diagnostics.Stopwatch]::StartNew()
  $groups = @{}
  $iter = Get-ChildItem -LiteralPath $root -Recurse -Depth $Depth -File -Filter '*.md' -ErrorAction SilentlyContinue
  $stopped = $false
  foreach ($f in $iter) {
    if ($sw.Elapsed.TotalSeconds -gt $MaxSecondsPerDrive) { $stopped = $true; break }
    if ($f.DirectoryName -match $skipPattern) { continue }
    if ($f.Name -notmatch '^\d{4}-\d{2}-\d{2}-') { continue }
    $d = $f.DirectoryName.ToLower()
    if ($groups.ContainsKey($d)) { $groups[$d]++ } else { $groups[$d] = 1 }
  }
  if ($stopped) { $truncatedDrives += $root; Write-Host ("  scan of {0} hit the {1}s budget" -f $root, $MaxSecondsPerDrive) }
  foreach ($k in $groups.Keys) {
    if ($groups[$k] -ge $MinHits) {
      $real = (Get-Item -LiteralPath $k).FullName
      Add-Cand $real 'scan' $groups[$k]
    }
  }
}

# ---------- layer 4: AGENTS.md anchor ----------
$anchors = @()
$systemDrive = [IO.Path]::GetPathRoot($env:SystemDrive + '\')
foreach ($start in @($env:USERPROFILE, $systemDrive, ([IO.Path]::GetPathRoot($kit)))) {
  if (-not $start -or -not (Test-Path $start)) { continue }
  $anchors += Get-ChildItem -LiteralPath $start -Recurse -Depth 4 -File -Include 'AGENTS.md', 'CLAUDE.md' -ErrorAction SilentlyContinue |
              Select-Object -First 40
}
foreach ($a in $anchors) {
  $sib = Join-Path $a.DirectoryName 'Logs'
  if ((Test-Path $sib) -and ((Get-ChildItem -LiteralPath $sib -Filter '*.md' -Recurse -File | Measure-Object).Count -ge 1)) {
    Add-Cand $sib 'agents-anchor' (Get-ChildItem -LiteralPath $sib -Filter '*.md' -Recurse -File | Measure-Object).Count
  }
}

$result = @($found.Values | Sort-Object -Property @{ Expression = { $_.registered }; Descending = $true },
                                             @{ Expression = { $_.count }; Descending = $true })

if ($Json) {
  Write-Output (ConvertTo-Json @($result) -Depth 4)
} else {
  Write-Host ""
  Write-Host ("=== log-root discovery on {0} ===" -f $me)
  if ($result.Count -eq 0) {
    Write-Host "no candidate found. Pass the root explicitly: pipeline.ps1 -Roots 'X:\path\to\Logs'"
  }
  $i = 0
  foreach ($c in $result) {
    $i++
    Write-Host ("{0,2}. {1,-46} {2,4} md  [{3}]{4}" -f $i, $c.path, $c.count, $c.source, $(if ($c.registered) { ' REGISTERED' } else { '' }))
  }
  if ($truncatedDrives.Count -gt 0) {
    Write-Host ("note: scan of {0} was time-capped; raise -MaxSecondsPerDrive or install Everything (es.exe) for an instant index lookup." -f ($truncatedDrives -join ', '))
  }
  Write-Host ""
}
