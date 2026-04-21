# PowerShell script to pull log files from the server
# Usage: .\scripts\pull_logs.ps1 [-BotOnly] [-WebOnly]

param(
    [switch]$BotOnly,
    [switch]$WebOnly,
    [string]$ConfigFile = "scripts\server_config.json"
)

# Default configuration
$defaultConfig = @{
    server_host = "50.116.43.215"
    server_user = "root"
    server_key = $null
    remote_bot_path = "/root/Summit/SummitDiscordBot/discord-bot"
    remote_web_path = "/var/log/summit-web"
    remote_report_log = "/root/Summit/log_report.log"
    local_logs_dir = "logs"
}

function Load-Config {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        Write-Host "Config file not found: $Path" -ForegroundColor Yellow
        Write-Host "Creating template config file..."
        $defaultConfig | ConvertTo-Json -Depth 10 | Out-File $Path -Encoding UTF8
        Write-Host "Please edit $Path with your server details and run again." -ForegroundColor Green
        exit 1
    }

    return Get-Content $Path | ConvertFrom-Json
}

function Ensure-LocalDir {
    param([string]$Dir)

    if (-not (Test-Path $Dir)) {
        New-Item -ItemType Directory -Path $Dir -Force | Out-Null
    }
    return Resolve-Path $Dir
}

function Pull-LogFile {
    param(
        [object]$Config,
        [string]$RemoteFile,
        [string]$LocalSubDir
    )

    $localLogsDir = Ensure-LocalDir $Config.local_logs_dir
    $localFileDir = Join-Path $localLogsDir $LocalSubDir
    Ensure-LocalDir $localFileDir | Out-Null

    # Add timestamp to local filename
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $filename = Split-Path $RemoteFile -Leaf
    $nameParts = $filename -split '\.'
    if ($nameParts.Count -eq 2) {
        $localFilename = "$($nameParts[0])_$timestamp.$($nameParts[1])"
    } else {
        $localFilename = "${filename}_$timestamp"
    }

    $localPath = Join-Path $localFileDir $localFilename

    # Build SCP command
    $scpArgs = @()
    if ($Config.server_key) {
        $scpArgs += @("-i", $Config.server_key)
    }
    $scpArgs += @(
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "$($Config.server_user)@$($Config.server_host):$RemoteFile",
        $localPath
    )

    Write-Host "Pulling $RemoteFile..."
    try {
        $result = & scp $scpArgs 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  ✓ Saved to $localPath" -ForegroundColor Green
            return $true
        } else {
            Write-Host "  ✗ Failed: $result" -ForegroundColor Red
            return $false
        }
    } catch {
        Write-Host "  ✗ Error: $_" -ForegroundColor Red
        Write-Host "  Make sure OpenSSH client is installed (Settings > Apps > Optional Features)" -ForegroundColor Yellow
        return $false
    }
}

function Pull-AllLogs {
    param(
        [object]$Config,
        [bool]$BotOnly,
        [bool]$WebOnly
    )

    $successCount = 0
    $totalCount = 0

    # Discord bot logs
    if (-not $WebOnly) {
        Write-Host "`n=== Pulling Discord Bot Logs ===" -ForegroundColor Cyan
        $botLogs = @(
            "$($Config.remote_bot_path)/bot.log"
        )

        foreach ($logFile in $botLogs) {
            $totalCount++
            if (Pull-LogFile -Config $Config -RemoteFile $logFile -LocalSubDir "discord-bot") {
                $successCount++
            }
        }
    }

    # Web app logs
    if (-not $BotOnly) {
        Write-Host "`n=== Pulling Web App Logs ===" -ForegroundColor Cyan
        $webLogs = @(
            "$($Config.remote_web_path)/error.log"
        )

        foreach ($logFile in $webLogs) {
            $totalCount++
            if (Pull-LogFile -Config $Config -RemoteFile $logFile -LocalSubDir "web-app") {
                $successCount++
            }
        }
    }

    # System logs (log report, etc.)
    Write-Host "`n=== Pulling System Logs ===" -ForegroundColor Cyan
    $reportLog = if ($Config.remote_report_log) { $Config.remote_report_log } else { "/root/Summit/log_report.log" }
    $totalCount++
    if (Pull-LogFile -Config $Config -RemoteFile $reportLog -LocalSubDir "system") {
        $successCount++
    }

    Write-Host "`n=== Summary ===" -ForegroundColor Cyan
    Write-Host "Successfully pulled $successCount/$totalCount log files"
    Write-Host "Logs saved to: $($Config.local_logs_dir)" -ForegroundColor Green
}

# Main execution
$config = Load-Config -Path $ConfigFile
Pull-AllLogs -Config $config -BotOnly:$BotOnly -WebOnly:$WebOnly
