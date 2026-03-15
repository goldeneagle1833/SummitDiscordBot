@echo off
REM Upload server scripts to production server
REM Run this from your local machine

echo ================================================
echo Uploading Daily Log Report System to Server
echo ================================================
echo.

REM Upload files
echo Uploading files to root@50.116.43.215:/root/Summit/...
scp daily_log_report.py email_config.json.template install.sh root@50.116.43.215:/root/Summit/

echo.
echo ================================================
echo Upload Complete!
echo ================================================
echo.
echo Next steps:
echo 1. SSH into server: ssh root@50.116.43.215
echo 2. Run installer: cd /root/Summit ^&^& chmod +x install.sh ^&^& ./install.sh
echo 3. Configure email: nano /root/Summit/scripts/email_config.json
echo 4. Test it: python3 /root/Summit/scripts/daily_log_report.py
echo.
pause
