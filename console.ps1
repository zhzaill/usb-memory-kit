$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$kit = Join-Path $root 'memory-kit'
$cfg = Get-Content (Join-Path $kit 'config\kit.json') -Raw | ConvertFrom-Json
$machine = $env:COMPUTERNAME
$corpus = Join-Path (Join-Path $kit 'corpus') $machine
$index = Join-Path $kit 'index'
$port = [int]$cfg.search.port

function Get-LineCount([string]$path) {
  if (Test-Path $path) { return (Get-Content $path | Measure-Object -Line).Lines }
  return 0
}

function Show-Status {
  $machines = Get-Content (Join-Path $kit 'config\machines.json') -Raw | ConvertFrom-Json
  $entry = $machines.PSObject.Properties[$machine]
  if ($entry) {
    $roots = @($entry.Value.roots | ForEach-Object { if ($_ -is [string]) { $_ } else { "{0}={1}" -f $_.id, $_.path } })
    Write-Host ("  SOURCE  {0}" -f ($roots -join '; ')) -ForegroundColor Gray
  }
  $files = if (Test-Path $corpus) { @(Get-ChildItem $corpus -Recurse -File | Where-Object Name -ne 'manifest.json').Count } else { 0 }
  $status = & (Join-Path $kit 'runtime\venv\Scripts\python.exe') (Join-Path $kit 'bin\index_status.py') | ConvertFrom-Json
  $chunks = $status.chunks
  $vectors = $status.vectors
  $healthy = $false
  try { $healthy = (Invoke-WebRequest -Uri $cfg.embed.endpoints[0].health -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch {}
  Write-Host ("  ARCHIVE {0}  files={1}" -f $corpus, $files) -ForegroundColor Cyan
  $coverage = if ($chunks) { [Math]::Floor(100 * ($chunks - $status.missing) / $chunks) } else { 0 }
  $indexColor = if ($status.complete) { 'Cyan' } else { 'Red' }
  Write-Host ("  INDEX   {0}  chunks={1} vectors={2} missing={3} coverage={4}%" -f $index, $chunks, $vectors, $status.missing, $coverage) -ForegroundColor $indexColor
  Write-Host ("  EMBED   {0}" -f $(if ($healthy) { 'ONLINE / 18082' } else { 'OFFLINE' })) -ForegroundColor $(if ($healthy) { 'Green' } else { 'DarkYellow' })
  Write-Host ("  MODE    {0}" -f $(if ($entry) { 'registered machine' } else { 'new machine - sync will ask you to select log roots' })) -ForegroundColor Gray
}

while ($true) {
  Clear-Host
  Write-Host '+--------------------------------------------------------------+' -ForegroundColor DarkGreen
  Write-Host '|  CORTICO FIELD CONSOLE                                      |' -ForegroundColor Green
  Write-Host '|  PORTABLE MEMORY SYSTEM - LOCAL OPS                          |' -ForegroundColor DarkGreen
  Write-Host '+--------------------------------------------------------------+' -ForegroundColor DarkGreen
  Write-Host ("  HOST {0}   USB {1}   {2}" -f $machine, (Split-Path -Qualifier $root), (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')) -ForegroundColor Gray
  Write-Host ''
  Show-Status
  Write-Host ''
  Write-Host '  [1] SYNC + VECTORIZE    collect -> chunk -> embed -> organize' -ForegroundColor Green
  Write-Host '  [2] OPEN MEMORY         launch portable Firefox' -ForegroundColor Cyan
  Write-Host '  [3] OPEN ARCHIVE        browse copied source logs on USB' -ForegroundColor Cyan
  Write-Host '  [4] OPEN CORPUS         inspect raw copies in Explorer' -ForegroundColor Gray
  Write-Host '  [5] REFRESH STATUS' -ForegroundColor Gray
  Write-Host '  [Q] EXIT' -ForegroundColor Gray
  Write-Host ''
  $choice = (Read-Host '  OPERATION').Trim()
  switch ($choice.ToUpperInvariant()) {
    '1' {
      Write-Host ("  source logs -> {0}" -f $corpus) -ForegroundColor Cyan
      Write-Host ("  vectors     -> {0}" -f (Join-Path $index 'vectors.jsonl')) -ForegroundColor Cyan
      & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $kit 'bin\pipeline.ps1') -Serve
      if ($LASTEXITCODE -eq 0) { & (Join-Path $root 'browser\open-kit.ps1') }
      Write-Host '  Pipeline finished. Press a key to return to console.' -ForegroundColor Green
      $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
    }
    '2' { & (Join-Path $root 'browser\open-kit.ps1'); Start-Sleep -Seconds 1 }
    '3' { & (Join-Path $root 'browser\open-kit.ps1') -View 'archive'; Start-Sleep -Seconds 1 }
    '4' { New-Item -ItemType Directory -Force -Path $corpus | Out-Null; Start-Process explorer.exe -ArgumentList @($corpus) }
    '5' { Start-Sleep -Seconds 1 }
    'Q' { break }
    default { Write-Host '  Unknown operation.' -ForegroundColor Red; Start-Sleep -Seconds 1 }
  }
  if ($choice.ToUpperInvariant() -eq 'Q') { break }
}
