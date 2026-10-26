# memory-kit :: collect.ps1  (ASCII only: PowerShell 5.1 reads BOM-less UTF-8 as ANSI)
# Archive log files from THIS machine's registered roots into corpus\<MACHINE>\r<idx>\<relpath>
# Explicit "files" entries are archived under x<idx> without walking project dependency trees.
# Idempotent: files whose sha256 already matches the manifest are skipped.
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File collect.ps1 -Discover   # probe candidate roots
#   powershell -NoProfile -ExecutionPolicy Bypass -File collect.ps1             # archive
param([switch]$Discover)
$ErrorActionPreference = 'Stop'
$kit = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$cfgFile = Join-Path $kit 'config\machines.json'
$cfg = Get-Content $cfgFile -Raw | ConvertFrom-Json
$machine = $env:COMPUTERNAME

if ($Discover) {
  Write-Output "=== log-root discovery on $machine ==="
  $candidates = @(
    (Join-Path $env:USERPROFILE 'Logs'),
    (Join-Path $env:USERPROFILE 'Documents\Logs'),
    (Join-Path $env:USERPROFILE 'workspace\Logs'),
    (Join-Path $env:USERPROFILE 'basic-memory'),
    'C:\Logs'
  )
  foreach ($c in $candidates) {
    if (Test-Path $c) {
      $n = (Get-ChildItem $c -Filter *.md -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
      Write-Output ("FOUND   {0}   ({1} md files)" -f $c, $n)
    } else {
      Write-Output ("absent  {0}" -f $c)
    }
  }
  Write-Output "Add this machine to config\machines.json, then re-run without -Discover."
  return
}

$entry = $cfg.PSObject.Properties[$machine]
if ($null -eq $entry) {
  throw ("Machine {0} not registered in config\machines.json - run with -Discover first." -f $machine)
}
$destRoot = Join-Path $kit ('corpus\' + $machine)
New-Item -ItemType Directory -Force -Path $destRoot | Out-Null
$manifestPath = Join-Path $destRoot 'manifest.json'
$known = @{}
if (Test-Path $manifestPath) {
  foreach ($m in (Get-Content $manifestPath -Raw | ConvertFrom-Json)) { $known[($m.tag + '|' + $m.relpath)] = $m }
}

$ri = 0; $copied = 0; $skipped = 0; $busy = 0
foreach ($root in $entry.Value.roots) {
  if (-not (Test-Path $root)) { Write-Output ("WARN root not found: {0}" -f $root); continue }
  $tag = 'r' + $ri; $ri++
  $files = Get-ChildItem -LiteralPath $root -Recurse -File -Include *.md,*.log,*.csv,*.txt -ErrorAction SilentlyContinue
  foreach ($f in $files) {
    $rel = $f.FullName.Substring($root.Length).TrimStart('\', '/')
    $key = $tag + '|' + $rel
    $sha = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash
    if ($known.ContainsKey($key) -and $known[$key].sha256 -eq $sha) { $skipped++; continue }
    $dest = Join-Path $destRoot ((Join-Path $tag $rel))
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
    Copy-Item -LiteralPath $f.FullName -Destination $dest -Force
    $known[$key] = [PSCustomObject]@{
      root = $root; tag = $tag; relpath = $rel; sha256 = $sha
      bytes = $f.Length; mtime_utc = $f.LastWriteTimeUtc.ToString('o')
    }
    $copied++
  }
}

$fi = 0
foreach ($filePath in @($entry.Value.files)) {
  if (-not $filePath) { continue }
  if (-not (Test-Path -LiteralPath $filePath -PathType Leaf)) {
    Write-Output ("WARN file not found: {0}" -f $filePath)
    continue
  }
  $f = Get-Item -LiteralPath $filePath
  $root = Split-Path -Parent $f.FullName
  $tag = 'x' + $fi
  $fi++
  $rel = $f.Name
  $key = $tag + '|' + $rel
  $sha = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash
  if ($known.ContainsKey($key) -and $known[$key].sha256 -eq $sha) { $skipped++; continue }
  $dest = Join-Path $destRoot ((Join-Path $tag $rel))
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
  Copy-Item -LiteralPath $f.FullName -Destination $dest -Force
  $known[$key] = [PSCustomObject]@{
    root = $root; tag = $tag; relpath = $rel; sha256 = $sha
    bytes = $f.Length; mtime_utc = $f.LastWriteTimeUtc.ToString('o')
  }
  $copied++
}
$out = @($known.Values | Sort-Object tag, relpath)
$json = if ($out.Count -eq 1) { ConvertTo-Json $out[0] } else { ConvertTo-Json $out }
[IO.File]::WriteAllText($manifestPath, $json, (New-Object System.Text.UTF8Encoding($false)))
Write-Output ("machine={0} copied={1} skipped={2} busy={3} manifest_entries={4}" -f $machine, $copied, $skipped, $busy, $out.Count)
Write-Output ("manifest -> {0}" -f $manifestPath)
