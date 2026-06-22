param(
    [int]$LocalPort = 13306,
    [string]$RemoteDbHost = "127.0.0.1",
    [int]$RemoteDbPort = 3306,
    [int]$IntervalSeconds = 20
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "db-tunnel-common.ps1")

$settings = Resolve-TunnelSettings `
    -ScriptRoot $PSScriptRoot `
    -LocalPort $LocalPort `
    -RemoteDbHost $RemoteDbHost `
    -RemoteDbPort $RemoteDbPort `
    -SshHost "" `
    -SshPort 29453 `
    -SshUser "" `
    -SshPassword ""

$logFile = Join-Path $settings.LogDir "mysql-tunnel-monitor.log"
$startScript = Join-Path $PSScriptRoot "start-db-tunnel.ps1"
$cooldownUntil = [datetime]::MinValue

function Write-MonitorLog { param([string]$Message) Add-Content -Path $logFile -Value "$(Get-Date -Format s) $Message" -Encoding UTF8 }

Write-MonitorLog "monitor started for 127.0.0.1:$($settings.LocalPort)"

while ($true) {
    try {
        $tunnels = @(Get-TunnelProcesses -Settings $settings)
        $healthy = $tunnels.Count -gt 0 -and (Test-MySqlReady -Settings $settings)
        if (-not $healthy -and (Get-Date) -ge $cooldownUntil) {
            Write-MonitorLog "detected tunnel drop, repairing"
            & powershell -ExecutionPolicy Bypass -File $startScript -LocalPort $settings.LocalPort -RemoteDbHost $settings.RemoteDbHost -RemoteDbPort $settings.RemoteDbPort -ForceRestart -SkipMonitor
            if ($LASTEXITCODE -eq 0) { Write-MonitorLog "repair succeeded" } else { Write-MonitorLog "repair failed with exit code $LASTEXITCODE" }
            $cooldownUntil = (Get-Date).AddSeconds([Math]::Max(30, $IntervalSeconds))
        }
    } catch {
        Write-MonitorLog "monitor error: $($_.Exception.Message)"
    }
    Start-Sleep -Seconds $IntervalSeconds
}
