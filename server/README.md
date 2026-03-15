# Server-Side Daily Log Report System

Automated daily log analysis and email reporting system that runs directly on the server.

## 📋 What It Does

Every day at **7 AM EST**, this system:

1. ✅ Analyzes the last 24 hours of bot and web app logs
2. 🔍 Identifies errors, warnings, critical issues, and exceptions
3. 📊 Generates a beautiful HTML summary report
4. 📧 Emails the report to goldeneagle1833@gmail.com
5. 🗑️ Deletes log archives older than 1 week

## 🚀 Quick Setup (5 minutes)

### Step 1: Upload Files to Server

From your local machine, upload the server files:

```bash
# From the project root
scp -r server/* root@50.116.43.215:/root/Summit/scripts/
```

### Step 2: SSH into Server

```bash
ssh root@50.116.43.215
cd /root/Summit/scripts
```

### Step 3: Run Installation Script

```bash
chmod +x install.sh
./install.sh
```

### Step 4: Configure Email Settings

Create a Gmail App Password (required for security):

1. Go to https://myaccount.google.com/security
2. Enable 2-Factor Authentication (if not already enabled)
3. Go to https://myaccount.google.com/apppasswords
4. Create an app password for "Mail"
5. Copy the 16-character password

Now edit the email config:

```bash
nano /root/Summit/scripts/email_config.json
```

Update with your details:

```json
{
  "smtp_server": "smtp.gmail.com",
  "smtp_port": 587,
  "smtp_user": "YOUR-GMAIL@gmail.com",
  "smtp_password": "your-16-char-app-password",
  "recipients": [
    "goldeneagle1833@gmail.com"
  ]
}
```

Save: `Ctrl+O`, Enter, then `Ctrl+X`

### Step 5: Test It

Run the script manually to test:

```bash
python3 /root/Summit/scripts/daily_log_report.py
```

You should receive an email within a few seconds!

## ✅ Verification

### Check Cron Job

```bash
crontab -l
```

You should see:
```
0 12 * * * /usr/bin/python3 /root/Summit/scripts/daily_log_report.py >> /root/Summit/log_report.log 2>&1
```

> **Note:** `0 12` = 12 PM UTC = 7 AM EST

### View Cron Logs

```bash
tail -f /root/Summit/log_report.log
```

### Manually Trigger Report

```bash
python3 /root/Summit/scripts/daily_log_report.py
```

## 📧 Email Report Features

The email report includes:

- **Status Badge**: 🟢 Healthy | 🟡 Warnings | 🟠 High Errors | 🔴 Critical
- **Summary Dashboard**: Total errors, warnings, critical issues, exceptions
- **Discord Bot Analysis**: Detailed breakdown of bot.log issues
- **Web App Analysis**: Detailed breakdown of app.log issues
- **Exception Stack Traces**: Full tracebacks for debugging
- **Beautiful HTML Formatting**: Easy to read on any device

## 🗑️ Log Cleanup

The script automatically deletes log files in `/root/Summit/log_archives/` that are older than **7 days**.

To change the retention period, edit `daily_log_report.py`:

```python
cleanup_old_logs(LOG_ARCHIVE_DIR, days=7)  # Change 7 to your preference
```

## ⚙️ Customization

### Change Email Time

Edit cron job to run at different time:

```bash
crontab -e
```

Common schedules:
- `0 12 * * *` - 7 AM EST (12 PM UTC) ← Current
- `0 16 * * *` - 11 AM EST (4 PM UTC)
- `0 0 * * *` - 7 PM EST previous day (12 AM UTC)

### Change Analysis Window

Edit `daily_log_report.py` to analyze different time periods:

```python
analyzer = LogAnalyzer(hours=24)  # Change 24 to 12, 48, etc.
```

### Add More Recipients

Edit `/root/Summit/scripts/email_config.json`:

```json
{
  "recipients": [
    "goldeneagle1833@gmail.com",
    "another-email@example.com"
  ]
}
```

### Analyze Different Log Files

Edit paths in `daily_log_report.py`:

```python
BOT_LOG = Path("/root/Summit/SummitDiscordBot/discord-bot/bot.log")
WEB_APP_LOG = Path("/root/Summit/SummitDiscordBot/web-app/app.log")
```

## 🐛 Troubleshooting

### No Email Received

**Check script output:**
```bash
python3 /root/Summit/scripts/daily_log_report.py
```

**Common issues:**
- ❌ Gmail App Password not configured → See Step 4 above
- ❌ 2FA not enabled on Gmail → Required for app passwords
- ❌ Wrong SMTP credentials → Check email_config.json
- ❌ Port 587 blocked → Try port 465 (SSL) instead

### Email Config Errors

```bash
# Validate JSON syntax
python3 -c "import json; json.load(open('/root/Summit/scripts/email_config.json'))"
```

### Cron Job Not Running

**Check cron service:**
```bash
systemctl status cron
```

**Check cron logs:**
```bash
grep CRON /var/log/syslog | tail -20
```

**Verify timing:**
```bash
date  # Check server time
# Should be UTC timezone
```

### Logs Not Found

**Verify log paths:**
```bash
ls -lh /root/Summit/SummitDiscordBot/discord-bot/bot.log
ls -lh /root/Summit/SummitDiscordBot/web-app/app.log
```

If paths are different, update `daily_log_report.py`:
```python
BOT_LOG = Path("/actual/path/to/bot.log")
WEB_APP_LOG = Path("/actual/path/to/app.log")
```

## 📂 File Structure

```
/root/Summit/
├── scripts/
│   ├── daily_log_report.py      # Main script
│   └── email_config.json         # Email configuration (gitignored)
├── log_archives/                 # Old logs (auto-deleted after 7 days)
└── log_report.log               # Cron execution logs
```

## 🔒 Security Notes

- `email_config.json` contains sensitive credentials
- This file is automatically added to `.gitignore`
- Never commit this file to version control
- Use Gmail App Passwords (not your real password)
- Restrict file permissions: `chmod 600 email_config.json`

## 📝 Manual Operations

### Run Report Now

```bash
python3 /root/Summit/scripts/daily_log_report.py
```

### Disable Daily Reports

```bash
crontab -e
# Comment out the line with '#'
# 0 12 * * * /usr/bin/python3 /root/Summit/scripts/daily_log_report.py >> /root/Summit/log_report.log 2>&1
```

### Re-enable Daily Reports

```bash
crontab -e
# Remove the '#' comment
```

### Uninstall

```bash
crontab -r  # Remove all cron jobs
rm -rf /root/Summit/scripts
rm -rf /root/Summit/log_archives
rm /root/Summit/log_report.log
```

## 📞 Support

If you encounter issues:

1. Check the troubleshooting section above
2. Review cron logs: `/root/Summit/log_report.log`
3. Test manually: `python3 /root/Summit/scripts/daily_log_report.py`
4. Verify email config: `cat /root/Summit/scripts/email_config.json`
