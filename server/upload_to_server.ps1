# PowerShell script to upload server scripts to production
# Run from the server directory

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Uploading Daily Log Report System to Server" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

$serverUser = "root"
$serverHost = "50.116.43.215"
$serverPath = "/root/Summit/"

$files = @(
    "daily_log_report.py",
    "email_config.json.template",
    "install.sh"
)

Write-Host "Uploading to ${serverUser}@${serverHost}:${serverPath}..." -ForegroundColor Yellow
Write-Host ""

foreach ($file in $files) {
    Write-Host "  Uploading $file..." -ForegroundColor Gray
    scp $file "${serverUser}@${serverHost}:${serverPath}"

    if ($LASTEXITCODE -eq 0) {
        Write-Host "    ✓ $file uploaded" -ForegroundColor Green
    } else {
        Write-Host "    ✗ $file failed" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Upload Complete!" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. SSH into server:" -ForegroundColor White
Write-Host "     ssh root@50.116.43.215" -ForegroundColor Gray
Write-Host ""
Write-Host "  2. Run installer:" -ForegroundColor White
Write-Host "     cd /root/Summit && chmod +x install.sh && ./install.sh" -ForegroundColor Gray
Write-Host ""
Write-Host "  3. Configure email:" -ForegroundColor White
Write-Host "     nano /root/Summit/scripts/email_config.json" -ForegroundColor Gray
Write-Host ""
Write-Host "  4. Test it:" -ForegroundColor White
Write-Host "     python3 /root/Summit/scripts/daily_log_report.py" -ForegroundColor Gray
Write-Host ""
