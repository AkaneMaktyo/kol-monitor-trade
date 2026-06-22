$ErrorActionPreference = "Stop"

$rootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$logDir = Join-Path $rootDir "logs"
$tunnelScript = Join-Path $rootDir "deploy\start-db-tunnel.ps1"
$python = Join-Path $rootDir ".venv\Scripts\python.exe"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Test-UrlReady {
  param([string]$Url)
  try {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 8
    return $response.StatusCode -ge 200 -and $response.StatusCode -lt 400
  } catch {
    return $false
  }
}

function Wait-UrlReady {
  param([string]$Url, [int]$TimeoutSeconds)
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    if (Test-UrlReady -Url $Url) { return $true }
    Start-Sleep -Seconds 1
  }
  return $false
}

function Get-ListeningProcess {
  param([int]$Port)
  $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $connection) { return $null }
  return Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
}

function Get-TunnelMonitorProcess {
  Get-CimInstance Win32_Process |
    Where-Object {
      ($_.Name -eq "powershell.exe" -or $_.Name -eq "pwsh.exe") -and
      $_.CommandLine -like "*monitor-db-tunnel.ps1*" -and
      $_.CommandLine -like "*-LocalPort 13306*"
    } |
    Select-Object -First 1
}

function Ensure-DbTunnel {
  & powershell -ExecutionPolicy Bypass -File $tunnelScript
  if ($LASTEXITCODE -ne 0) { throw "DB tunnel bootstrap failed." }
  $monitor = Get-TunnelMonitorProcess
  if ($monitor) { Write-Host "DB tunnel self-heal monitor active: PID $($monitor.ProcessId)" }
}

function Ensure-Backend {
  $healthUrl = "http://127.0.0.1:8000/api/health"
  $statusUrl = "http://127.0.0.1:8000/api/status"
  if (Test-UrlReady -Url $healthUrl) {
    if (Wait-UrlReady -Url $statusUrl -TimeoutSeconds 20) {
      Write-Host "Backend already running: $statusUrl"
      return
    }
  }
  $process = Get-ListeningProcess -Port 8000
  if ($process) {
    throw "Port 8000 is already used by $($process.ProcessName), but the DB-backed backend API is not ready."
  }
  if (-not (Test-Path $python)) {
    throw "Missing Python runtime: $python"
  }
  Start-Process -FilePath $python `
    -ArgumentList "run.py" `
    -WorkingDirectory $rootDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logDir "uvicorn.out.log") `
    -RedirectStandardError (Join-Path $logDir "uvicorn.err.log") | Out-Null
  if (-not (Wait-UrlReady -Url $healthUrl -TimeoutSeconds 60)) {
    throw "Backend health start timed out. See logs\\uvicorn.err.log"
  }
  if (-not (Wait-UrlReady -Url $statusUrl -TimeoutSeconds 60)) {
    throw "Backend DB-backed API start timed out. See logs\\uvicorn.err.log"
  }
  Write-Host "Backend ready: $statusUrl"
}

Ensure-DbTunnel
Ensure-Backend

Write-Host "Project ready: http://127.0.0.1:8000/  |  http://127.0.0.1:8000/api/status"
