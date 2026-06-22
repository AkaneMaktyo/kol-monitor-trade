param(
    [int]$LocalPort = 13306,
    [string]$RemoteDbHost = "127.0.0.1",
    [int]$RemoteDbPort = 3306,
    [string]$SshHost = "",
    [int]$SshPort = 29453,
    [string]$SshUser = "",
    [string]$SshPassword = "",
    [switch]$ForceRestart,
    [switch]$SkipMonitor
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "db-tunnel-common.ps1")

$settings = Resolve-TunnelSettings `
    -ScriptRoot $PSScriptRoot `
    -LocalPort $LocalPort `
    -RemoteDbHost $RemoteDbHost `
    -RemoteDbPort $RemoteDbPort `
    -SshHost $SshHost `
    -SshPort $SshPort `
    -SshUser $SshUser `
    -SshPassword $SshPassword

if (-not $SkipMonitor) {
    Ensure-TunnelMonitor -Settings $settings
}

$existing = @(Get-TunnelProcesses -Settings $settings)
if (-not $ForceRestart -and $existing.Count -gt 0 -and (Test-MySqlReady -Settings $settings)) {
    Write-Output "MySQL tunnel already healthy on 127.0.0.1:$($settings.LocalPort)"
    $existing | Select-Object ProcessId, CommandLine
    exit 0
}
if ($existing.Count -gt 0) {
    Stop-TunnelProcesses -Processes $existing
}

$askpass = "C:\Windows\Temp\kmt-ssh-askpass-$PID.cmd"
$stdoutLog = Join-Path $settings.LogDir "mysql-tunnel.out.log"
$stderrLog = Join-Path $settings.LogDir "mysql-tunnel.err.log"
Set-Content -Path $askpass -Value @("@echo off", "echo $($settings.SshPassword)") -Encoding Ascii

try {
    $env:SSH_ASKPASS = $askpass
    $env:SSH_ASKPASS_REQUIRE = "force"
    $env:DISPLAY = "codex"
    $ssh = (Get-Command ssh -ErrorAction Stop).Source
    $args = @(
        "-N",
        "-L", "$($settings.LocalPort):$($settings.RemoteDbHost):$($settings.RemoteDbPort)",
        "-p", "$($settings.SshPort)",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ConnectTimeout=10",
        "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=2",
        "-o", "TCPKeepAlive=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "$($settings.SshUser)@$($settings.SshHost)"
    )
    $process = Start-Process `
        -FilePath $ssh `
        -ArgumentList $args `
        -WorkingDirectory $settings.Root `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -WindowStyle Hidden `
        -PassThru
    $healthy = $false
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Seconds 1
        if ($process.HasExited) {
            break
        }
        if (Test-MySqlReady -Settings $settings) {
            $healthy = $true
            break
        }
    }
    if (-not $healthy) {
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
        $tail = Read-LogTail -Path $stderrLog
        throw "MySQL tunnel failed on 127.0.0.1:$($settings.LocalPort)`n$tail"
    }
    Write-Output "Tunnel ready for $($settings.DatabaseLabel)"
    Get-CimInstance Win32_Process -Filter "ProcessId=$($process.Id)" |
        Select-Object ProcessId, Name, CommandLine
} finally {
    Remove-Item $askpass -ErrorAction SilentlyContinue
    Remove-Item Env:SSH_ASKPASS, Env:SSH_ASKPASS_REQUIRE, Env:DISPLAY -ErrorAction SilentlyContinue
}
