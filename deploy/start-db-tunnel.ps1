param(
    [int]$LocalPort = 13306,
    [string]$RemoteDbHost = "127.0.0.1",
    [int]$RemoteDbPort = 3306,
    [string]$SshHost = "",
    [int]$SshPort = 29453,
    [string]$SshUser = "",
    [string]$SshPassword = "",
    [switch]$ForceRestart
)

$ErrorActionPreference = "Stop"

function Get-EnvMap {
    param([string]$Path)
    $result = @{}
    if (-not (Test-Path $Path)) { return $result }
    foreach ($line in Get-Content $Path) {
        if ([string]::IsNullOrWhiteSpace($line) -or $line.TrimStart().StartsWith("#")) { continue }
        $parts = $line.Split("=", 2)
        if ($parts.Count -eq 2) {
            $result[$parts[0].Trim()] = $parts[1].Trim()
        }
    }
    return $result
}

function Get-TunnelProcesses {
    param([int]$Port)
    $pattern = "-L $Port`:$RemoteDbHost`:$RemoteDbPort"
    Get-CimInstance Win32_Process -Filter "Name='ssh.exe'" |
        Where-Object { $_.CommandLine -like "*$pattern*" }
}

function Test-Port {
    param([int]$Port)
    try {
        return (Test-NetConnection 127.0.0.1 -Port $Port -WarningAction SilentlyContinue).TcpTestSucceeded
    } catch {
        return $false
    }
}

function Test-MySql {
    param([hashtable]$EnvMap)
    $python = Join-Path $root ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) { return Test-Port -Port $LocalPort }
    foreach ($key in "MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE") {
        if (-not $EnvMap.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($EnvMap[$key])) {
            return Test-Port -Port $LocalPort
        }
    }
    $env:TUNNEL_MYSQL_HOST = $EnvMap["MYSQL_HOST"]
    $env:TUNNEL_MYSQL_PORT = $EnvMap["MYSQL_PORT"]
    $env:TUNNEL_MYSQL_USER = $EnvMap["MYSQL_USER"]
    $env:TUNNEL_MYSQL_PASSWORD = $EnvMap["MYSQL_PASSWORD"]
    $env:TUNNEL_MYSQL_DATABASE = $EnvMap["MYSQL_DATABASE"]
    try {
        & $python -c "import os,pymysql; conn=pymysql.connect(host=os.environ['TUNNEL_MYSQL_HOST'], port=int(os.environ['TUNNEL_MYSQL_PORT']), user=os.environ['TUNNEL_MYSQL_USER'], password=os.environ['TUNNEL_MYSQL_PASSWORD'], database=os.environ['TUNNEL_MYSQL_DATABASE'], charset='utf8mb4', connect_timeout=8); cur=conn.cursor(); cur.execute('select database(), @@hostname, @@port'); print(cur.fetchone()); conn.close()"
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    } finally {
        Remove-Item Env:TUNNEL_MYSQL_HOST, Env:TUNNEL_MYSQL_PORT, Env:TUNNEL_MYSQL_USER, Env:TUNNEL_MYSQL_PASSWORD, Env:TUNNEL_MYSQL_DATABASE -ErrorAction SilentlyContinue
    }
}

function Stop-TunnelProcesses {
    param([object[]]$Processes)
    foreach ($process in $Processes) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 1
}

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$envMap = Get-EnvMap -Path (Join-Path $root ".env")

if (-not $SshHost) { $SshHost = $env:KMT_SSH_HOST }
if (-not $SshUser) { $SshUser = $env:KMT_SSH_USER }
if (-not $SshPassword) { $SshPassword = $env:KMT_SSH_PASSWORD }
if (-not $SshHost) { $SshHost = "103.236.98.149" }
if (-not $SshUser) { $SshUser = "root" }
if ([string]::IsNullOrWhiteSpace($SshPassword)) {
    throw "Missing SSH password. Pass -SshPassword or set KMT_SSH_PASSWORD first."
}

$existing = @(Get-TunnelProcesses -Port $LocalPort)
if (-not $ForceRestart -and $existing.Count -gt 0 -and (Test-MySql -EnvMap $envMap)) {
    Write-Output "MySQL tunnel already healthy on 127.0.0.1:${LocalPort}"
    $existing | Select-Object ProcessId, CommandLine
    exit 0
}

if ($existing.Count -gt 0) {
    Stop-TunnelProcesses -Processes $existing
}

$logsDir = Join-Path $root "logs"
if (-not (Test-Path $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir | Out-Null
}
$askpass = "C:\Windows\Temp\kmt-ssh-askpass-$PID.cmd"
$stdoutLog = Join-Path $logsDir "mysql-tunnel.out.log"
$stderrLog = Join-Path $logsDir "mysql-tunnel.err.log"
Set-Content -Path $askpass -Value @("@echo off", "echo $SshPassword") -Encoding Ascii

try {
    $env:SSH_ASKPASS = $askpass
    $env:SSH_ASKPASS_REQUIRE = "force"
    $env:DISPLAY = "codex"
    $ssh = (Get-Command ssh -ErrorAction Stop).Source
    $args = @(
        "-N",
        "-L", "$LocalPort`:$RemoteDbHost`:$RemoteDbPort",
        "-p", "$SshPort",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=3",
        "-o", "StrictHostKeyChecking=accept-new",
        "$SshUser@$SshHost"
    )
    $process = Start-Process -FilePath $ssh -ArgumentList $args -WorkingDirectory $root -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog -WindowStyle Hidden -PassThru
    $healthy = $false
    for ($i = 0; $i -lt 12; $i++) {
        Start-Sleep -Seconds 1
        if ($process.HasExited) { break }
        if (Test-MySql -EnvMap $envMap) {
            $healthy = $true
            break
        }
    }
    if (-not $healthy) {
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
        $tail = if (Test-Path $stderrLog) { (Get-Content $stderrLog -Tail 40) -join [Environment]::NewLine } else { "" }
        throw "MySQL tunnel failed on 127.0.0.1:${LocalPort}`n$tail"
    }
    Write-Output "MySQL tunnel ready on 127.0.0.1:${LocalPort}"
    Get-CimInstance Win32_Process -Filter "ProcessId=$($process.Id)" | Select-Object ProcessId, Name, CommandLine
} finally {
    Remove-Item $askpass -ErrorAction SilentlyContinue
    Remove-Item Env:SSH_ASKPASS, Env:SSH_ASKPASS_REQUIRE, Env:DISPLAY -ErrorAction SilentlyContinue
}
