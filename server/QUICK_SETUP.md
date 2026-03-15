# 🚀 Quick Setup Guide - 5 Minutes

## TL;DR

Run these commands and you'll get daily email reports at 7 AM EST:

### 1️⃣ Upload Files to Server

```bash
# From your local machine (in project root)
scp server/daily_log_report.py server/email_config.json.template server/install.sh root@50.116.43.215:/root/Summit/
```

### 2️⃣ Install on Server

```bash
# SSH into server
ssh root@50.116.43.215

# Go to Summit directory
cd /root/Summit

# Run installer
chmod +x install.sh
./install.sh
```

### 3️⃣ Get Gmail App Password

1. Go to https://myaccount.google.com/apppasswords
2. Create app password for "Mail"
3. Copy the 16-character password (e.g., `abcd efgh ijkl mnop`)

### 4️⃣ Configure Email

```bash
# On the server, edit config
nano /root/Summit/scripts/email_config.json
```

Replace with your details:

```json
{
  "smtp_server": "smtp.gmail.com",
  "smtp_port": 587,
  "smtp_user": "YOUR-GMAIL@gmail.com",
  "smtp_password": "abcdefghijklmnop",
  "recipients": [
    "goldeneagle1833@gmail.com"
  ]
}
```

**Save:** Press `Ctrl+O`, then `Enter`, then `Ctrl+X`

### 5️⃣ Test It

```bash
# Run manually to test
python3 /root/Summit/scripts/daily_log_report.py
```

**✅ Check your email!** You should receive a report within seconds.

---

## That's It! 🎉

Your server will now automatically:
- ✅ Analyze logs every day at **7 AM EST**
- ✅ Email you a summary of errors/warnings
- ✅ Clean up logs older than 1 week

## Verify It's Working

```bash
# Check cron job exists
crontab -l

# Should see:
# 0 12 * * * /usr/bin/python3 /root/Summit/scripts/daily_log_report.py >> /root/Summit/log_report.log 2>&1
```

## Troubleshooting

**No email received?**
- Make sure you created a Gmail App Password (not your regular password)
- Check if 2FA is enabled on your Gmail (required for app passwords)
- Run the script manually to see errors: `python3 /root/Summit/scripts/daily_log_report.py`

**Need to change the time?**
- Edit cron: `crontab -e`
- Current: `0 12 * * *` (7 AM EST = 12 PM UTC)
- For 8 AM EST: `0 13 * * *`
- For 9 AM EST: `0 14 * * *`

For more details, see [README.md](README.md)
