# browser :: open-kit.ps1  (ASCII only, PowerShell 5.1)
# Start the memory-kit service if it is not already answering, then open the on-stick
# Firefox (own profile, no install, no Local Network Access gating) at the kit page.
param([string]$View = '')
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$usb  = Split-Path -Parent $here
$url  = 'http://127.0.0.1:18200/'
if ($View) { $url += '?view=' + [Uri]::EscapeDataString($View) }

function Test-Kit {
  try { (Invoke-WebRequest -Uri ($url + 'api/health') -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200 }
  catch { return $false }
}

if (-not (Test-Kit)) {
  $start = Join-Path $usb 'memory-kit\start.ps1'
  if (Test-Path $start) {
    Write-Host 'memory-kit is not answering -> starting it (a separate window is created)'
    Start-Process powershell -WindowStyle Minimized -ArgumentList @(
      '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $start)
    $deadline = (Get-Date).AddSeconds(150)
    while ((Get-Date) -lt $deadline) {
      if (Test-Kit) { Write-Host 'service is up'; break }
      Start-Sleep -Seconds 2
    }
  } else {
    Write-Host ('WARN start script not found: ' + $start)
  }
} else {
  Write-Host 'service already running'
}

$ff   = Join-Path $here 'firefox\firefox.exe'
$prof = Join-Path $here 'profile'
if (-not (Test-Path $ff)) { throw ('Firefox not found: ' + $ff) }
if (-not (Test-Path $prof)) { throw ('profile not found: ' + $prof) }

# -no-remote keeps this copy from attaching to an installed Firefox, -profile pins the
# on-stick profile so bookmarks, saved logins and cookies travel with the stick.
Write-Host 'opening the memory-kit page in the on-stick Firefox'
Start-Process -FilePath $ff -ArgumentList @('-profile', $prof, '-no-remote', $url)
