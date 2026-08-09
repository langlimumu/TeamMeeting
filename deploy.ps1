[CmdletBinding()]
param(
    [ValidateSet("Gray", "Promote", "StartProduction", "Rollback", "StopGray", "StopProduction", "Status")]
    [string]$Action = "Status",
    [string]$HostAddress = "127.0.0.1",
    [int]$ProductionPort = 8000,
    [int]$GrayPort = 8001,
    [string]$PythonPath = "python"
)

$ErrorActionPreference = "Stop"
$environmentVariables = [Environment]::GetEnvironmentVariables()
if ($environmentVariables.Contains("Path") -and $environmentVariables.Contains("PATH")) {
    $combinedPath = @($environmentVariables["Path"], $environmentVariables["PATH"]) -join ";"
    [Environment]::SetEnvironmentVariable("Path", $null, "Process")
    [Environment]::SetEnvironmentVariable("PATH", $null, "Process")
    [Environment]::SetEnvironmentVariable("Path", $combinedPath, "Process")
}
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$DataRoot = Join-Path $Root "data"
$DeployRoot = Join-Path $DataRoot "deploy"
$ReleaseRoot = Join-Path $DeployRoot "releases"
$RuntimeRoot = Join-Path $DeployRoot "runtime"
$GrayRoot = Join-Path $DeployRoot "gray"
$DeployBackupRoot = Join-Path $DeployRoot "backups"
$ProductionDb = Join-Path $DataRoot "weekly_team.db"
$GrayDb = Join-Path $GrayRoot "weekly_team_gray.db"

foreach ($directory in @($ReleaseRoot, $RuntimeRoot, $GrayRoot, $DeployBackupRoot)) {
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
}

function Resolve-Python {
    $command = Get-Command $PythonPath -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    $bundled = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path -LiteralPath $bundled) {
        return $bundled
    }
    throw "Python was not found. Install Python 3 or pass -PythonPath with the full path."
}

$Python = Resolve-Python

function Get-MetadataPath([string]$Name) {
    return Join-Path $RuntimeRoot "$Name.json"
}

function Read-Metadata([string]$Name) {
    $path = Get-MetadataPath $Name
    if (-not (Test-Path -LiteralPath $path)) {
        return $null
    }
    return Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Write-Metadata([string]$Name, $Value) {
    $path = Get-MetadataPath $Name
    $Value | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $path -Encoding UTF8
}

function Get-ReleaseId {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $revision = "local"
    try {
        $revision = (& git -C $Root rev-parse --short HEAD 2>$null).Trim()
        if (& git -C $Root status --porcelain 2>$null) {
            $revision = "$revision-dirty"
        }
    } catch {
        $revision = "local"
    }
    return "$stamp-$revision"
}

function New-Release {
    $releaseId = Get-ReleaseId
    $releasePath = Join-Path $ReleaseRoot $releaseId
    New-Item -ItemType Directory -Force -Path $releasePath | Out-Null
    Copy-Item -LiteralPath (Join-Path $Root "server.py") -Destination $releasePath
    foreach ($folder in @("team_loop", "static", "previews")) {
        $source = Join-Path $Root $folder
        if (Test-Path -LiteralPath $source) {
            Copy-Item -LiteralPath $source -Destination $releasePath -Recurse
        }
    }
    Write-Host "Release snapshot: $releaseId"
    return [pscustomobject]@{ Id = $releaseId; Path = $releasePath }
}

function Invoke-DbSnapshot([string]$Source, [string]$Target) {
    & $Python (Join-Path $Root "scripts\db_snapshot.py") --source $Source --target $Target
    if ($LASTEXITCODE -ne 0) {
        throw "Database snapshot failed."
    }
}

function Invoke-Migration([string]$ReleasePath, [string]$DatabasePath, [string]$Environment, [string]$ReleaseId) {
    $oldDb = $env:TEAM_LOOP_DB_PATH
    $oldData = $env:TEAM_LOOP_DATA_DIR
    $oldBackup = $env:TEAM_LOOP_BACKUP_DIR
    $oldEnvironment = $env:TEAM_LOOP_ENV
    $oldRelease = $env:TEAM_LOOP_RELEASE
    $oldTrustProxy = $env:TEAM_LOOP_TRUST_PROXY
    $oldRequireHttps = $env:TEAM_LOOP_REQUIRE_HTTPS
    try {
        $env:TEAM_LOOP_DB_PATH = $DatabasePath
        $env:TEAM_LOOP_DATA_DIR = Split-Path -Parent $DatabasePath
        $env:TEAM_LOOP_BACKUP_DIR = Join-Path (Split-Path -Parent $DatabasePath) "backups"
        $env:TEAM_LOOP_ENV = $Environment
        $env:TEAM_LOOP_RELEASE = $ReleaseId
        if ($Environment -eq "production") {
            $env:TEAM_LOOP_TRUST_PROXY = "1"
            $env:TEAM_LOOP_REQUIRE_HTTPS = "1"
        } else {
            $env:TEAM_LOOP_TRUST_PROXY = "0"
            $env:TEAM_LOOP_REQUIRE_HTTPS = "0"
        }
        & $Python (Join-Path $ReleasePath "server.py") --migrate-only
        if ($LASTEXITCODE -ne 0) {
            throw "Database migration failed for $Environment."
        }
    } finally {
        $env:TEAM_LOOP_DB_PATH = $oldDb
        $env:TEAM_LOOP_DATA_DIR = $oldData
        $env:TEAM_LOOP_BACKUP_DIR = $oldBackup
        $env:TEAM_LOOP_ENV = $oldEnvironment
        $env:TEAM_LOOP_RELEASE = $oldRelease
        $env:TEAM_LOOP_TRUST_PROXY = $oldTrustProxy
        $env:TEAM_LOOP_REQUIRE_HTTPS = $oldRequireHttps
    }
}

function Get-PortProcessId([int]$Port) {
    try {
        $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop | Select-Object -First 1
        if ($connection) { return [int]$connection.OwningProcess }
    } catch {
        $line = netstat -ano | Select-String -Pattern ":$Port\s+.*LISTENING\s+(\d+)" | Select-Object -First 1
        if ($line -and $line.Matches.Count -gt 0) {
            return [int]$line.Matches[0].Groups[1].Value
        }
    }
    return $null
}

function Stop-Environment([string]$Name, [int]$Port, [switch]$AllowTeamLoopTakeover) {
    $metadata = Read-Metadata $Name
    if ($metadata -and $metadata.pid) {
        $process = Get-Process -Id ([int]$metadata.pid) -ErrorAction SilentlyContinue
        if ($process) {
            Stop-Process -Id $process.Id -Force
            $process.WaitForExit()
        }
    }

    $portPid = Get-PortProcessId $Port
    if ($portPid) {
        if (-not $AllowTeamLoopTakeover) {
            throw "Port $Port is occupied by PID $portPid."
        }
        $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$portPid" -ErrorAction SilentlyContinue
        if (-not $processInfo -or $processInfo.CommandLine -notmatch "server\.py") {
            throw "Port $Port is occupied by a process that is not Team Loop (PID $portPid)."
        }
        Stop-Process -Id $portPid -Force
        Start-Sleep -Milliseconds 500
    }
    Remove-Item -LiteralPath (Get-MetadataPath $Name) -Force -ErrorAction SilentlyContinue
}

function Start-Environment(
    [string]$Name,
    [string]$ReleasePath,
    [string]$DatabasePath,
    [string]$Environment,
    [string]$ReleaseId,
    [int]$Port
) {
    Stop-Environment -Name $Name -Port $Port -AllowTeamLoopTakeover
    $stdout = Join-Path $RuntimeRoot "$Name.stdout.log"
    $stderr = Join-Path $RuntimeRoot "$Name.stderr.log"
    $oldDb = $env:TEAM_LOOP_DB_PATH
    $oldData = $env:TEAM_LOOP_DATA_DIR
    $oldBackup = $env:TEAM_LOOP_BACKUP_DIR
    $oldEnvironment = $env:TEAM_LOOP_ENV
    $oldRelease = $env:TEAM_LOOP_RELEASE
    try {
        $env:TEAM_LOOP_DB_PATH = $DatabasePath
        $env:TEAM_LOOP_DATA_DIR = Split-Path -Parent $DatabasePath
        $env:TEAM_LOOP_BACKUP_DIR = Join-Path (Split-Path -Parent $DatabasePath) "backups"
        $env:TEAM_LOOP_ENV = $Environment
        $env:TEAM_LOOP_RELEASE = $ReleaseId
        $process = Start-Process -FilePath $Python `
            -ArgumentList @("-u", "server.py", "--host", $HostAddress, "--port", "$Port") `
            -WorkingDirectory $ReleasePath `
            -RedirectStandardOutput $stdout `
            -RedirectStandardError $stderr `
            -WindowStyle Hidden `
            -PassThru
    } finally {
        $env:TEAM_LOOP_DB_PATH = $oldDb
        $env:TEAM_LOOP_DATA_DIR = $oldData
        $env:TEAM_LOOP_BACKUP_DIR = $oldBackup
        $env:TEAM_LOOP_ENV = $oldEnvironment
        $env:TEAM_LOOP_RELEASE = $oldRelease
    }

    $metadata = [ordered]@{
        name = $Name
        environment = $Environment
        release = $ReleaseId
        release_path = $ReleasePath
        database = $DatabasePath
        host = $HostAddress
        port = $Port
        https_required = ($Environment -eq "production")
        pid = $process.Id
        started_at = (Get-Date).ToString("o")
    }
    Write-Metadata $Name $metadata
    return $metadata
}

function Wait-ForHealth([int]$Port, [string]$Environment, [string]$ReleaseId) {
    $url = "http://127.0.0.1:$Port/api/health"
    $deadline = (Get-Date).AddSeconds(30)
    do {
        try {
            $health = Invoke-RestMethod -Uri $url -TimeoutSec 3
            if ($health.status -eq "ok" -and $health.environment -eq $Environment -and $health.release -eq $ReleaseId) {
                return
            }
        } catch {
            Start-Sleep -Milliseconds 750
        }
    } while ((Get-Date) -lt $deadline)
    throw "Health check timed out: $url"
}

function Invoke-SmokeTest([int]$Port, [string]$Environment, [string]$ReleaseId) {
    & $Python (Join-Path $Root "scripts\smoke_test.py") `
        --base-url "http://127.0.0.1:$Port" `
        --environment $Environment `
        --release $ReleaseId
    if ($LASTEXITCODE -ne 0) {
        throw "Smoke test failed for $Environment."
    }
}

function Start-Gray {
    if (-not (Test-Path -LiteralPath $ProductionDb)) {
        throw "Production database does not exist: $ProductionDb"
    }
    $release = New-Release
    Stop-Environment -Name "gray" -Port $GrayPort -AllowTeamLoopTakeover
    Invoke-DbSnapshot -Source $ProductionDb -Target $GrayDb
    Invoke-Migration -ReleasePath $release.Path -DatabasePath $GrayDb -Environment "gray" -ReleaseId $release.Id
    Start-Environment -Name "gray" -ReleasePath $release.Path -DatabasePath $GrayDb -Environment "gray" -ReleaseId $release.Id -Port $GrayPort | Out-Null
    Wait-ForHealth -Port $GrayPort -Environment "gray" -ReleaseId $release.Id
    Invoke-SmokeTest -Port $GrayPort -Environment "gray" -ReleaseId $release.Id
    Write-Host "Gray deployment is ready: http://127.0.0.1:$GrayPort/"
}

function Start-Production {
    $release = New-Release
    Invoke-Migration -ReleasePath $release.Path -DatabasePath $ProductionDb -Environment "production" -ReleaseId $release.Id
    Start-Environment -Name "production" -ReleasePath $release.Path -DatabasePath $ProductionDb -Environment "production" -ReleaseId $release.Id -Port $ProductionPort | Out-Null
    Wait-ForHealth -Port $ProductionPort -Environment "production" -ReleaseId $release.Id
    Invoke-SmokeTest -Port $ProductionPort -Environment "production" -ReleaseId $release.Id
    Write-Host "Production is ready: http://127.0.0.1:$ProductionPort/"
}

function Promote-Gray {
    $gray = Read-Metadata "gray"
    if (-not $gray) {
        throw "No gray deployment metadata was found. Run Gray first."
    }
    Wait-ForHealth -Port $GrayPort -Environment "gray" -ReleaseId $gray.release
    Invoke-SmokeTest -Port $GrayPort -Environment "gray" -ReleaseId $gray.release

    $previous = Read-Metadata "production"
    $backup = Join-Path $DeployBackupRoot ("production_{0}.db" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
    Invoke-DbSnapshot -Source $ProductionDb -Target $backup

    try {
        Stop-Environment -Name "production" -Port $ProductionPort -AllowTeamLoopTakeover
        Invoke-Migration -ReleasePath $gray.release_path -DatabasePath $ProductionDb -Environment "production" -ReleaseId $gray.release
        $metadata = Start-Environment -Name "production" -ReleasePath $gray.release_path -DatabasePath $ProductionDb -Environment "production" -ReleaseId $gray.release -Port $ProductionPort
        $metadata["rollback_backup"] = $backup
        $metadata["previous"] = $previous
        $metadata["promoted_at"] = (Get-Date).ToString("o")
        Write-Metadata "production" $metadata
        Wait-ForHealth -Port $ProductionPort -Environment "production" -ReleaseId $gray.release
        Invoke-SmokeTest -Port $ProductionPort -Environment "production" -ReleaseId $gray.release
    } catch {
        Write-Warning "Promotion failed. Restoring the production database."
        Stop-Environment -Name "production" -Port $ProductionPort -AllowTeamLoopTakeover
        Invoke-DbSnapshot -Source $backup -Target $ProductionDb
        if ($previous -and (Test-Path -LiteralPath $previous.release_path)) {
            Start-Environment -Name "production" -ReleasePath $previous.release_path -DatabasePath $ProductionDb -Environment "production" -ReleaseId $previous.release -Port $ProductionPort | Out-Null
        }
        throw
    }
    Write-Host "Gray release promoted to production: http://127.0.0.1:$ProductionPort/"
}

function Rollback-Production {
    $current = Read-Metadata "production"
    if (-not $current -or -not $current.rollback_backup) {
        throw "No rollback point is available."
    }
    Stop-Environment -Name "production" -Port $ProductionPort -AllowTeamLoopTakeover
    Invoke-DbSnapshot -Source $current.rollback_backup -Target $ProductionDb
    $previous = $current.previous
    if (-not $previous -or -not (Test-Path -LiteralPath $previous.release_path)) {
        throw "Database was restored, but the previous release package is unavailable."
    }
    Start-Environment -Name "production" -ReleasePath $previous.release_path -DatabasePath $ProductionDb -Environment "production" -ReleaseId $previous.release -Port $ProductionPort | Out-Null
    Wait-ForHealth -Port $ProductionPort -Environment "production" -ReleaseId $previous.release
    Invoke-SmokeTest -Port $ProductionPort -Environment "production" -ReleaseId $previous.release
    Write-Metadata "production" $previous
    Write-Host "Production rollback completed."
}

function Show-Status {
    foreach ($item in @(@("production", $ProductionPort), @("gray", $GrayPort))) {
        $name = $item[0]
        $port = [int]$item[1]
        $metadata = Read-Metadata $name
        $pidOnPort = Get-PortProcessId $port
        if ($metadata) {
            Write-Host ("{0}: release={1}, port={2}, pid={3}, listening={4}" -f $name, $metadata.release, $port, $metadata.pid, [bool]$pidOnPort)
        } else {
            Write-Host ("{0}: unmanaged, port={1}, listening={2}" -f $name, $port, [bool]$pidOnPort)
        }
    }
}

switch ($Action) {
    "Gray" { Start-Gray }
    "Promote" { Promote-Gray }
    "StartProduction" { Start-Production }
    "Rollback" { Rollback-Production }
    "StopGray" { Stop-Environment -Name "gray" -Port $GrayPort -AllowTeamLoopTakeover; Write-Host "Gray stopped." }
    "StopProduction" { Stop-Environment -Name "production" -Port $ProductionPort -AllowTeamLoopTakeover; Write-Host "Production stopped." }
    "Status" { Show-Status }
}
