param(
    [string]$SshHost = "103.236.98.149",
    [int]$SshPort = 29453,
    [string]$SshUser = "root",
    [string]$SshPassword = "",
    [string]$ReleaseArchivePath = "",
    [string]$CommitSha = "",
    [switch]$SkipPack
)

$ErrorActionPreference = "Stop"

$rootDir = Split-Path -Parent $PSScriptRoot
$defaultArchivePath = Join-Path $env:TEMP "kol-monitor-trade-release.tar.gz"
$remoteDir = "/root/kol-monitor-deploy"
$resolvedArchivePath = if ($ReleaseArchivePath) { (Resolve-Path $ReleaseArchivePath).Path } else { $defaultArchivePath }
$localReleaseScript = Join-Path $env:TEMP "kmt-apply-release-$PID.sh"
$localMuxScript = Join-Path $PSScriptRoot "ssh_http_mux.py"
$releaseClient = Join-Path $PSScriptRoot "ssh-release.py"

function Find-PythonCommand {
    $commands = @()
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { $commands += ,@($python.Source) }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { $commands += ,@($py.Source, "-3") }
    $windowsAppsPython = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "Microsoft\WindowsApps\python.exe"
    if (Test-Path $windowsAppsPython) { $commands += ,@($windowsAppsPython) }
    foreach ($command in $commands) {
        try {
            & $command[0] @($command | Select-Object -Skip 1) -c "import paramiko" | Out-Null
            if ($LASTEXITCODE -eq 0) { return ,$command }
        } catch {
            continue
        }
    }
    throw "Python with paramiko was not found."
}

function Resolve-CommitSha {
    param([string]$RootDir, [string]$ProvidedSha)
    if (-not [string]::IsNullOrWhiteSpace($ProvidedSha)) { return $ProvidedSha.Trim() }
    try {
        return (git -C $RootDir rev-parse HEAD).Trim()
    } catch {
        return "manual"
    }
}

if ([string]::IsNullOrWhiteSpace($SshPassword)) {
    throw "Missing -SshPassword."
}

if (-not $SkipPack) {
    Push-Location $rootDir
    try {
        if (Test-Path $resolvedArchivePath) { Remove-Item $resolvedArchivePath -Force }
        & tar `
            --exclude='.git' `
            --exclude='.github' `
            --exclude='.venv' `
            --exclude='__pycache__' `
            --exclude='*.pyc' `
            --exclude='.codex-*.log' `
            --exclude='.codex-ssh-askpass.cmd' `
            --exclude='.env' `
            --exclude='data' `
            --exclude='logs' `
            --exclude='.codegraph' `
            --exclude='.codex' `
            --exclude='*.tar.gz' `
            -czf $resolvedArchivePath .
        if ($LASTEXITCODE -ne 0) { throw "Release archive failed." }
    } finally {
        Pop-Location
    }
}

if (-not (Test-Path $resolvedArchivePath)) { throw "Release archive not found: $resolvedArchivePath" }
if (-not (Test-Path $localMuxScript)) { throw "Mux script not found: $localMuxScript" }
if (-not (Test-Path $releaseClient)) { throw "Release client not found: $releaseClient" }

[IO.File]::WriteAllText(
    $localReleaseScript,
    ([IO.File]::ReadAllText((Join-Path $PSScriptRoot "apply-release.sh")) -replace "`r`n", "`n"),
    (New-Object System.Text.UTF8Encoding($false))
)

try {
    $env:MOT_SSH_PASSWORD = $SshPassword
    $pythonCommand = Find-PythonCommand
    $resolvedCommitSha = Resolve-CommitSha -RootDir $rootDir -ProvidedSha $CommitSha
    & $pythonCommand[0] @($pythonCommand | Select-Object -Skip 1) $releaseClient `
        --host $SshHost `
        --port $SshPort `
        --user $SshUser `
        --remote-dir $remoteDir `
        --archive $resolvedArchivePath `
        --script $localReleaseScript `
        --mux-script $localMuxScript `
        --commit $resolvedCommitSha
    if ($LASTEXITCODE -ne 0) { throw "Remote release failed." }
    Write-Output "Release complete: http://$($SshHost):8888/"
} finally {
    Remove-Item $localReleaseScript -ErrorAction SilentlyContinue
    Remove-Item Env:MOT_SSH_PASSWORD -ErrorAction SilentlyContinue
}
