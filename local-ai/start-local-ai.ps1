# local-ai :: start-local-ai.ps1  (ASCII only, PowerShell 5.1 compatible)
#
# Portable llama.cpp pair on the stick:
#   chat      : Qwen3-4B-Q4_K_M.gguf            -> http://127.0.0.1:18080  (built-in Web UI)
#   embedding : Qwen3-Embedding-0.6B-Q8_0.gguf  -> http://127.0.0.1:18082  (OpenAI /v1/embeddings)
#
# Backend: Vulkan (GPU offload) when a Vulkan loader + driver is present, else pure CPU.
#          If the Vulkan launch does not become healthy in time, it is retried once on the CPU build.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File start-local-ai.ps1
#   ... -Backend cpu        force CPU build
#   ... -NoChat / -NoEmbed  start only one endpoint
#   ... -NoBrowser          do not open the chat UI
#   ... -Stop               stop both servers started earlier (reads state\pids.json)
param(
  [ValidateSet('auto','vulkan','cpu')][string]$Backend = 'auto',
  [int]$ChatPort = 18080,
  [int]$EmbedPort = 18082,
  [switch]$NoChat,
  [switch]$NoEmbed,
  [switch]$NoBrowser,
  [switch]$Stop
)

$ErrorActionPreference = 'Stop'
$root  = Split-Path -Parent $MyInvocation.MyCommand.Path
$state = Join-Path $root 'state'
$logs  = Join-Path $state 'logs'
$pidFile = Join-Path $state 'pids.json'
New-Item -ItemType Directory -Force -Path $logs | Out-Null

$chatModel = Join-Path $root 'models\Qwen3-4B-Q4_K_M.gguf'
$embModel  = Join-Path $root 'models\Qwen3-Embedding-0.6B-Q8_0.gguf'

function Get-Health([int]$port) {
  try {
    $r = Invoke-WebRequest -Uri ("http://127.0.0.1:{0}/health" -f $port) -UseBasicParsing -TimeoutSec 2
    return ($r.StatusCode -eq 200)
  } catch { return $false }
}

# ---------------- stop ----------------
if ($Stop) {
  if (Test-Path $pidFile) {
    $pids = Get-Content $pidFile -Raw | ConvertFrom-Json
    foreach ($p in $pids) {
      $proc = Get-Process -Id $p -ErrorAction SilentlyContinue
      if ($proc) { Write-Output ("stopping pid {0} ({1})" -f $p, $proc.ProcessName); Stop-Process -Id $p -Force -ErrorAction SilentlyContinue }
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    Write-Output 'local-ai stopped'
  } else { Write-Output 'no state\pids.json -> nothing recorded as running' }
  return
}

# ---------------- backend detection ----------------
# Ground truth: ask the Vulkan build itself which devices it can talk to.
function Test-VulkanDevices {
  $exe = Join-Path $root 'llama\llama-server.exe'
  if (-not (Test-Path $exe)) { return $false }
  try {
    $out = & $exe --list-devices 2>&1
    return (($out -join "`n") -match 'Vulkan\d')
  } catch { return $false }
}

$vulkanOk = Test-VulkanDevices
if ($Backend -eq 'auto') { if ($vulkanOk) { $Backend = 'vulkan' } else { $Backend = 'cpu' } }
Write-Output ("backend    : {0}  (vulkan devices detected: {1})" -f $Backend, $vulkanOk)

function Get-Bin([string]$b) {
  if ($b -eq 'vulkan') { return (Join-Path $root 'llama') }
  return (Join-Path $root 'llama-cpu')
}
function Get-Ngl([string]$b) { if ($b -eq 'vulkan') { return '99' } else { return '0' } }

$started = @()

function Start-Server([string]$tag, [string]$exeDir, [string]$ngl, [string[]]$extra, [int]$port, [int]$timeoutSec) {
  $exe = Join-Path $exeDir 'llama-server.exe'
  if (-not (Test-Path $exe)) { throw ("missing " + $exe) }
  $outLog = Join-Path $logs ($tag + '.out.log')
  $errLog = Join-Path $logs ($tag + '.err.log')
  $argv = @('--host','127.0.0.1','--port',"$port",'-ngl',$ngl) + $extra
  $p = Start-Process -FilePath $exe -ArgumentList $argv -WorkingDirectory $exeDir -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $outLog -RedirectStandardError $errLog
  Write-Host ("{0,-6}: pid {1} launching (port {2}, ngl {3}, dir {4})" -f $tag, $p.Id, $port, $ngl, (Split-Path -Leaf $exeDir))
  $deadline = (Get-Date).AddSeconds($timeoutSec)
  while ((Get-Date) -lt $deadline) {
    if ($p.HasExited) {
      $tail = ''
      if (Test-Path $errLog) { $tail = (Get-Content $errLog -Tail 6 -ErrorAction SilentlyContinue) -join ' | ' }
      Write-Host ("{0,-6}: EXITED code {1} :: {2}" -f $tag, $p.ExitCode, $tail)
      return $null
    }
    if (Get-Health $port) {
      Write-Host ("{0,-6}: healthy on {1}  (load {2:N1}s)" -f $tag, $port, ((Get-Date) - $p.StartTime).TotalSeconds)
      return $p
    }
    Start-Sleep -Milliseconds 700
  }
  Write-Host ("{0,-6}: TIMEOUT after {1}s on port {2}" -f $tag, $timeoutSec, $port)
  try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch {}
  return $null
}

$threads = [string][Math]::Max(4, [int]([Environment]::ProcessorCount / 2))

# ---------------- embedding ----------------
if (-not $NoEmbed) {
  if (Get-Health $EmbedPort) {
    Write-Output ("embed : already healthy on {0}" -f $EmbedPort)
  } else {
    if (-not (Test-Path $embModel)) { throw ("missing " + $embModel) }
    $extra = @('-m', $embModel, '--embedding', '-t','4','-c','4096','-b','4096','-ub','4096')
    $p = Start-Server 'embed' (Get-Bin $Backend) (Get-Ngl $Backend) $extra $EmbedPort 180
    if (-not $p -and $Backend -eq 'vulkan') {
      Write-Output 'embed : vulkan failed -> retry on CPU build'
      $p = Start-Server 'embed' (Get-Bin 'cpu') '0' $extra $EmbedPort 180
    }
    if ($p) { $started += $p.Id }
  }
}

# ---------------- chat ----------------
if (-not $NoChat) {
  if (Get-Health $ChatPort) {
    Write-Output ("chat  : already healthy on {0}" -f $ChatPort)
  } else {
    if (-not (Test-Path $chatModel)) { throw ("missing " + $chatModel) }
    $extra = @('-m', $chatModel, '-t', $threads, '-c','8192','--jinja')
    $p = Start-Server 'chat' (Get-Bin $Backend) (Get-Ngl $Backend) $extra $ChatPort 300
    if (-not $p -and $Backend -eq 'vulkan') {
      Write-Output 'chat  : vulkan failed -> retry on CPU build'
      $p = Start-Server 'chat' (Get-Bin 'cpu') '0' $extra $ChatPort 300
    }
    if ($p) { $started += $p.Id }
  }
}

if ($started.Count -gt 0) {
  # merge with still-alive pids recorded earlier (a -NoChat / -NoEmbed run must not forget the other server)
  $keep = @()
  if (Test-Path $pidFile) {
    try {
      foreach ($old in (Get-Content $pidFile -Raw | ConvertFrom-Json)) {
        if ($old -and (Get-Process -Id $old -ErrorAction SilentlyContinue)) { $keep += [int]$old }
      }
    } catch {}
  }
  $all = @($keep + $started | Sort-Object -Unique)
  ('[' + ($all -join ',') + ']') | Out-File -FilePath $pidFile -Encoding ascii
  Write-Host ("recorded pids in {0}: {1}" -f $pidFile, ($all -join ','))
}

Write-Output ''
Write-Output ("chat  UI  : http://127.0.0.1:{0}" -f $ChatPort)
Write-Output ("embed API : http://127.0.0.1:{0}/v1/embeddings" -f $EmbedPort)
Write-Output 'stop with: powershell -ExecutionPolicy Bypass -File start-local-ai.ps1 -Stop'

if (-not $NoBrowser -and -not $NoChat) { Start-Process ("http://127.0.0.1:{0}" -f $ChatPort) }
