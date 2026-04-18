# Backup logs from server to local dated folder, then clear them on the server.
# Schedule this locally at 8am daily (after the server's daily_log_report.py runs).
#
# Usage: .\backup_logs.ps1
# Setup: Run setup as Admin: schtasks /create /tn "Summit Log Backup" /tr "powershell -File F:\GitHub\SummitDiscordBot\discord-bot\pull_from_server\backup_logs.ps1" /sc daily /st 08:15 /ru SYSTEM

$SERVER       = "root@50.116.43.215"
$REMOTE_BOT   = "/root/Summit/SummitDiscordBot/discord-bot"
$REMOTE_WEB   = "/var/log/summit-web"
$BACKUP_ROOT  = "F:\GitHub\SummitDiscordBot\discord-bot\pull_from_server\backup"

# Create dated subfolder (e.g. 2026-04-18)
$dateFolder = Get-Date -Format "yyyy-MM-dd"
$dest = Join-Path $BACKUP_ROOT $dateFolder
New-Item -ItemType Directory -Force -Path $dest | Out-Null

Write-Host "=== Summit Log Backup ===" -ForegroundColor Cyan
Write-Host "Date: $dateFolder"
Write-Host "Destination: $dest"
Write-Host ""

$files = @(
    @{ remote = "$REMOTE_BOT/bot.log";        label = "bot.log" },
    @{ remote = "$REMOTE_WEB/error.log";      label = "error.log" }
)

$downloaded = @()

foreach ($f in $files) {
    $localPath = Join-Path $dest $f.label
    Write-Host "Downloading $($f.label)..." -NoNewline

    scp -q "$SERVER`:$($f.remote)" "$localPath" 2>$null

    if ($LASTEXITCODE -eq 0 -and (Test-Path $localPath)) {
        $size = (Get-Item $localPath).Length
        Write-Host " OK ($([math]::Round($size/1KB, 1)) KB)" -ForegroundColor Green
        $downloaded += $f.remote
    } else {
        Write-Host " NOT FOUND (skipped)" -ForegroundColor Yellow
    }
}

# Only clear files that were successfully downloaded
if ($downloaded.Count -gt 0) {
    Write-Host ""
    Write-Host "Clearing logs on server..." -NoNewline

    $truncateCmds = ($downloaded | ForEach-Object { "truncate -s 0 $_" }) -join " && "
    ssh $SERVER $truncateCmds

    if ($LASTEXITCODE -eq 0) {
        Write-Host " OK" -ForegroundColor Green
    } else {
        Write-Host " FAILED - logs NOT cleared" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "Done. Backup saved to: $dest" -ForegroundColor Cyan
