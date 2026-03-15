# Scripts

Utility scripts for managing the Summit Discord Bot.

## Log Pulling Scripts

Automated scripts to pull log files from the production server to your local machine.

### Setup

1. **First-time setup**: Run any of the scripts below. They will create a template `server_config.json` file.

2. **Configure server details**: Edit `scripts/server_config.json` with your server information:

```json
{
  "server_host": "your-server-ip-or-domain",
  "server_user": "your-username",
  "server_key": "C:/Users/YourName/.ssh/id_rsa",  // Optional
  "remote_bot_path": "/home/ubuntu/SummitDiscordBot/discord-bot",
  "remote_web_path": "/home/ubuntu/SummitDiscordBot/web-app",
  "local_logs_dir": "logs"
}
```

- `server_key` is optional - if not set, uses your default SSH key
- Paths can use forward slashes (/) on all platforms

3. **Test the connection**:

```bash
python scripts/test_connection.py
```

This will verify:
- SSH connection works
- SCP is available
- Log files are accessible on the server

### Usage

#### Option 1: Batch File (Easiest for Windows)

Double-click `pull_logs.bat` or run:
```bash
scripts\pull_logs.bat
```

#### Option 2: PowerShell Script

```powershell
# Pull all logs
.\scripts\pull_logs.ps1

# Pull only bot logs
.\scripts\pull_logs.ps1 -BotOnly

# Pull only web app logs
.\scripts\pull_logs.ps1 -WebOnly
```

#### Option 3: Python Script (Cross-platform)

```bash
# Pull all logs
python scripts/pull_logs.py

# Pull only bot logs
python scripts/pull_logs.py --bot-only

# Pull only web app logs
python scripts/pull_logs.py --web-only

# Use custom config file
python scripts/pull_logs.py --config /path/to/config.json
```

### Output

Logs are saved to the `logs/` directory with timestamps:
```
logs/
├── discord-bot/
│   └── bot_20260314_143052.log
└── web-app/
    ├── app_20260314_143052.log
    ├── error_20260314_143052.log
    └── access_20260314_143052.log
```

### Requirements

- **SSH access** to the production server
- **SCP/OpenSSH client** installed:
  - Windows: Install via Settings > Apps > Optional Features > OpenSSH Client
  - Linux/Mac: Usually pre-installed
- **Python 3.6+** (for Python script only)

### Automated Scheduled Pulls (Windows)

Set up a Windows Scheduled Task to automatically pull logs on a schedule:

```powershell
# Run PowerShell as Administrator, then:

# Daily at 2 AM (default)
.\scripts\setup_scheduled_task.ps1

# Daily at specific time (e.g., 6 PM)
.\scripts\setup_scheduled_task.ps1 -Frequency Daily -Hour 18 -Minute 0

# Weekly (Mondays at 2 AM)
.\scripts\setup_scheduled_task.ps1 -Frequency Weekly -Hour 2 -Minute 0

# Hourly
.\scripts\setup_scheduled_task.ps1 -Frequency Hourly
```

**Manage the scheduled task:**
- Open Task Scheduler (`taskschd.msc`)
- Find "Summit Bot - Pull Logs" under Task Scheduler Library
- Right-click to Run, Edit, Disable, or Delete

**Or use PowerShell:**
```powershell
# Run the task now
Start-ScheduledTask -TaskName "Summit Bot - Pull Logs"

# View task details
Get-ScheduledTask -TaskName "Summit Bot - Pull Logs"

# Remove the task
Unregister-ScheduledTask -TaskName "Summit Bot - Pull Logs"
```

### Troubleshooting

**"scp command not found"**
- Install OpenSSH client (see Requirements above)

**"Permission denied"**
- Check your SSH key is set up correctly
- Ensure `server_user` has read access to the log files

**"Connection refused"**
- Verify `server_host` is correct
- Check if SSH port 22 is accessible

**Logs not found on server**
- Update `remote_bot_path` and `remote_web_path` in config
- Check if logs are being written (they might be in a different location)

**Scheduled task not running**
- Check Task Scheduler for error messages
- Ensure your user has permission to run scheduled tasks
- Verify the script path is correct in the task settings
