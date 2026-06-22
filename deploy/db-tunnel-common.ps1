function Get-EnvMap {
    param([string]$Path)
    $result = @{}
    if (-not (Test-Path $Path)) { return $result }
    foreach ($line in Get-Content $Path) {
        if ([string]::IsNullOrWhiteSpace($line) -or $line.TrimStart().StartsWith("#")) { continue }
        $parts = $line.Split("=", 2)
        if ($parts.Count -eq 2) { $result[$parts[0].Trim()] = $parts[1].Trim() }
    }
    return $result
}

function Get-ServerNoteMap {
    param([string]$Path)
    $result = @{}
    if (-not (Test-Path $Path)) { return $result }
    foreach ($line in Get-Content $Path) {
        $trimmed = $line.Trim()
        if ($trimmed -match '^- Host:\s*`?([^`]+)`?$' -and -not $result.ContainsKey("Host")) { $result["Host"] = $matches[1].Trim() }
        elseif ($trimmed -match '^- SSH Port:\s*`?([^`]+)`?$' -and -not $result.ContainsKey("SshPort")) { $result["SshPort"] = $matches[1].Trim() }
        elseif ($trimmed -match '^- SSH User:\s*`?([^`]+)`?$' -and -not $result.ContainsKey("SshUser")) { $result["SshUser"] = $matches[1].Trim() }
        elseif ($trimmed -match '^- SSH Password:\s*`?([^`]+)`?$' -and -not $result.ContainsKey("SshPassword")) { $result["SshPassword"] = $matches[1].Trim() }
    }
    return $result
}

function Resolve-TunnelSettings {
    param([string]$ScriptRoot, [int]$LocalPort, [string]$RemoteDbHost, [int]$RemoteDbPort, [string]$SshHost, [int]$SshPort, [string]$SshUser, [string]$SshPassword)
    $root = (Resolve-Path (Join-Path $ScriptRoot "..")).Path
    $envMap = Get-EnvMap -Path (Join-Path $root ".env")
    $noteMap = Get-ServerNoteMap -Path (Join-Path $root "..\_local_notes\cloud-server-access.md")
    if (-not $SshHost) { $SshHost = $env:KMT_SSH_HOST }
    if (-not $SshUser) { $SshUser = $env:KMT_SSH_USER }
    if (-not $SshPassword) { $SshPassword = $env:KMT_SSH_PASSWORD }
    if (-not $SshHost) { $SshHost = $noteMap["Host"] }
    if (-not $SshUser) { $SshUser = $noteMap["SshUser"] }
    if (-not $SshPassword) { $SshPassword = $noteMap["SshPassword"] }
    if ($noteMap.ContainsKey("SshPort")) { $SshPort = [int]$noteMap["SshPort"] }
    if (-not $SshHost) { $SshHost = "103.236.98.149" }
    if (-not $SshUser) { $SshUser = "root" }
    if ([string]::IsNullOrWhiteSpace($SshPassword)) { throw "Missing SSH password. Set KMT_SSH_PASSWORD or maintain ..\_local_notes\cloud-server-access.md." }
    $logDir = Join-Path $root "logs"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    return @{
        Root = $root
        LogDir = $logDir
        EnvMap = $envMap
        LocalPort = $LocalPort
        RemoteDbHost = $RemoteDbHost
        RemoteDbPort = $RemoteDbPort
        SshHost = $SshHost
        SshPort = $SshPort
        SshUser = $SshUser
        SshPassword = $SshPassword
        DatabaseLabel = "127.0.0.1:$LocalPort/$($envMap['MYSQL_DATABASE'])"
    }
}

function Test-Port {
    param([int]$Port)
    try { return (Test-NetConnection 127.0.0.1 -Port $Port -WarningAction SilentlyContinue).TcpTestSucceeded } catch { return $false }
}

function Test-MySqlReady {
    param([hashtable]$Settings)
    if (-not (Test-Port -Port $Settings.LocalPort)) { return $false }
    $python = Join-Path $Settings.Root ".venv\Scripts\python.exe"
    foreach ($key in "MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE") {
        if (-not $Settings.EnvMap.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($Settings.EnvMap[$key])) {
            return Test-Port -Port $Settings.LocalPort
        }
    }
    if (-not (Test-Path $python)) { return Test-Port -Port $Settings.LocalPort }
    $env:TUNNEL_MYSQL_HOST = "127.0.0.1"
    $env:TUNNEL_MYSQL_PORT = "$($Settings.LocalPort)"
    $env:TUNNEL_MYSQL_USER = $Settings.EnvMap["MYSQL_USER"]
    $env:TUNNEL_MYSQL_PASSWORD = $Settings.EnvMap["MYSQL_PASSWORD"]
    $env:TUNNEL_MYSQL_DATABASE = $Settings.EnvMap["MYSQL_DATABASE"]
    try {
        & $python -c "import os,pymysql; conn=pymysql.connect(host=os.environ['TUNNEL_MYSQL_HOST'], port=int(os.environ['TUNNEL_MYSQL_PORT']), user=os.environ['TUNNEL_MYSQL_USER'], password=os.environ['TUNNEL_MYSQL_PASSWORD'], database=os.environ['TUNNEL_MYSQL_DATABASE'], charset='utf8mb4', connect_timeout=8); cur=conn.cursor(); cur.execute('select 1'); cur.fetchone(); conn.close()"
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    } finally {
        Remove-Item Env:TUNNEL_MYSQL_HOST, Env:TUNNEL_MYSQL_PORT, Env:TUNNEL_MYSQL_USER, Env:TUNNEL_MYSQL_PASSWORD, Env:TUNNEL_MYSQL_DATABASE -ErrorAction SilentlyContinue
    }
}

function Get-TunnelProcesses {
    param([hashtable]$Settings)
    $pattern = "-L $($Settings.LocalPort):$($Settings.RemoteDbHost):$($Settings.RemoteDbPort)"
    Get-CimInstance Win32_Process -Filter "Name='ssh.exe'" |
        Where-Object { $_.CommandLine -like "*$pattern*" }
}

function Stop-TunnelProcesses {
    param([object[]]$Processes)
    foreach ($process in $Processes) { Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
}

function Read-LogTail {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return "" }
    return (Get-Content $Path -Tail 40) -join [Environment]::NewLine
}

function Ensure-TunnelMonitor {
    param([hashtable]$Settings)
    $monitorScript = Join-Path $PSScriptRoot "monitor-db-tunnel.ps1"
    $existing = Get-CimInstance Win32_Process |
        Where-Object {
            ($_.Name -eq "powershell.exe" -or $_.Name -eq "pwsh.exe") -and
            $_.CommandLine -like "*monitor-db-tunnel.ps1*" -and
            $_.CommandLine -like "*-LocalPort $($Settings.LocalPort)*"
        }
    if ($existing) { return }
    Start-Process `
        -FilePath "powershell" `
        -ArgumentList @("-ExecutionPolicy", "Bypass", "-File", $monitorScript, "-LocalPort", $Settings.LocalPort) `
        -WorkingDirectory $Settings.Root `
        -RedirectStandardOutput (Join-Path $Settings.LogDir "mysql-tunnel-monitor.out.log") `
        -RedirectStandardError (Join-Path $Settings.LogDir "mysql-tunnel-monitor.err.log") `
        -WindowStyle Hidden | Out-Null
}
