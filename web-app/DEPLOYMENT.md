# Summit Web Application - Production Deployment Guide

This guide explains how to deploy the Summit Discord Bot web application to production using gunicorn behind nginx.

## Overview

The production stack consists of:
- **Flask**: Web application framework
- **Gunicorn**: Production WSGI HTTP server
- **Nginx**: Reverse proxy and static file server
- **Systemd**: Process management and auto-restart
- **Let's Encrypt**: SSL/TLS certificates

## Prerequisites

- Ubuntu/Debian Linux server (Linode, AWS, etc.)
- Root or sudo access
- Domain name pointing to server IP (sorcererssummit.com)
- Python 3.8 or higher
- Git installed

## Initial Server Setup

### 1. Update System Packages

```bash
sudo apt update
sudo apt upgrade -y
```

### 2. Install Required System Packages

```bash
sudo apt install -y python3 python3-pip python3-venv nginx git
```

### 3. Clone the Repository

```bash
cd /root/Summit
git clone https://github.com/your-username/SummitDiscordBot.git
cd SummitDiscordBot
```

### 4. Install Python Dependencies

```bash
cd web-app
pip3 install -r requirements.txt
```

## SSL Certificate Setup

If you haven't already set up SSL, use Let's Encrypt:

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d sorcererssummit.com -d www.sorcererssummit.com
```

Follow the prompts to configure HTTPS. Certbot will automatically:
- Generate SSL certificates
- Configure nginx
- Set up auto-renewal

**Note**: The nginx configuration in this repo assumes SSL is at:
- Certificate: `/etc/letsencrypt/live/sorcererssummit.com/fullchain.pem`
- Private Key: `/etc/letsencrypt/live/sorcererssummit.com/privkey.pem`

## Application Configuration

### 1. Verify Environment Variables

Check that [discord-bot/.env](../discord-bot/.env) has production values:

```env
DISCORD_REDIRECT_URI='https://sorcererssummit.com/auth/discord/callback'
SECRET_KEY='<your-secure-secret-key>'
API_KEYS='<your-api-keys>'
DISCORD_CLIENT_ID='<your-client-id>'
DISCORD_CLIENT_SECRET='<your-client-secret>'
OPENAI_API_KEY='<your-openai-key>'
```

### 2. Update Discord Developer Portal

**CRITICAL**: Add the production redirect URI to your Discord application:

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Select your application
3. Navigate to **OAuth2** → **Redirects**
4. Add: `https://sorcererssummit.com/auth/discord/callback`
5. Click **Save Changes**

## Deployment Steps

### 1. Create Log Directory

```bash
cd /root/Summit/SummitDiscordBot/web-app
chmod +x setup_logs.sh
./setup_logs.sh
```

This creates:
- `/var/log/summit-web/error.log`
- `/var/log/summit-web/access.log`

### 2. Configure Nginx

```bash
# Copy nginx configuration
sudo cp nginx/summit-web.conf /etc/nginx/sites-available/summit-web

# Create symbolic link to enable the site
sudo ln -s /etc/nginx/sites-available/summit-web /etc/nginx/sites-enabled/

# Test nginx configuration
sudo nginx -t

# If test passes, reload nginx
sudo systemctl reload nginx
```

**Important**: If you have existing nginx configurations, you may need to:
- Remove default site: `sudo rm /etc/nginx/sites-enabled/default`
- Check for port conflicts: `sudo netstat -tlnp | grep :80`

### 3. Configure Systemd Service

```bash
# Copy service file
sudo cp systemd/summit-web.service /etc/systemd/system/

# Reload systemd to recognize new service
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable summit-web

# Start the service
sudo systemctl start summit-web
```

### 4. Verify Deployment

Check service status:
```bash
sudo systemctl status summit-web
```

Expected output:
```
● summit-web.service - Summit Discord Bot Web Application
   Loaded: loaded (/etc/systemd/system/summit-web.service; enabled)
   Active: active (running) since ...
```

View logs:
```bash
# View live logs
sudo journalctl -u summit-web -f

# View recent logs
sudo journalctl -u summit-web -n 50
```

### 5. Test the Application

1. **Health Check**:
   ```bash
   curl https://sorcererssummit.com/health
   # Should return: healthy
   ```

2. **API Status**:
   ```bash
   curl https://sorcererssummit.com/api/status
   # Should return: {"status": "online", "message": "Summit Web App is running!"}
   ```

3. **Web Interface**:
   - Open browser to https://sorcererssummit.com
   - Should see the home page
   - Check that static files (CSS, JS, images) load properly

4. **Discord OAuth**:
   - Click "Login with Discord"
   - Should redirect to Discord
   - After authentication, should return to sorcererssummit.com (not localhost)

## Deployment Workflow (GitHub Actions)

The repository includes automated deployment via GitHub Actions ([.github/workflows/deploy-web.yml](../.github/workflows/deploy-web.yml)).

When you push changes to the `main` branch (affecting `web-app/**` files), the workflow:
1. SSH into the Linode server
2. Pull latest changes from GitHub
3. Install/update dependencies
4. Restart the systemd service

This means future updates are automatic - just push to main!

## Maintenance & Operations

### Viewing Logs

**Application logs** (gunicorn):
```bash
# Live tail
tail -f /var/log/summit-web/access.log
tail -f /var/log/summit-web/error.log

# Search for errors
grep ERROR /var/log/summit-web/error.log
```

**Systemd logs**:
```bash
# Live tail
sudo journalctl -u summit-web -f

# Last 100 lines
sudo journalctl -u summit-web -n 100

# Logs from today
sudo journalctl -u summit-web --since today
```

**Nginx logs**:
```bash
tail -f /var/log/nginx/summit-web-access.log
tail -f /var/log/nginx/summit-web-error.log
```

### Restarting the Service

```bash
# Restart application
sudo systemctl restart summit-web

# Reload nginx (after config changes)
sudo systemctl reload nginx

# Full nginx restart
sudo systemctl restart nginx
```

### Updating the Application

```bash
cd /root/Summit/SummitDiscordBot
git pull origin main
cd web-app
pip3 install -r requirements.txt
sudo systemctl restart summit-web
```

Or wait for GitHub Actions to auto-deploy (if workflow is triggered).

### Checking Service Health

```bash
# Service status
sudo systemctl status summit-web

# Is service running?
ps aux | grep gunicorn

# Check socket file exists
ls -la /tmp/summit-web.sock

# Check server resources
htop
```

## Troubleshooting

### Service Won't Start

```bash
# Check systemd logs for errors
sudo journalctl -u summit-web -n 50 --no-pager

# Common issues:
# - Path typos in service file
# - Missing dependencies
# - Port/socket conflicts
# - Permission issues
```

### 502 Bad Gateway Error

This means nginx can't connect to gunicorn:

```bash
# Check if gunicorn is running
ps aux | grep gunicorn

# Check socket exists
ls -la /tmp/summit-web.sock

# Check nginx error logs
tail -f /var/log/nginx/summit-web-error.log

# Restart the service
sudo systemctl restart summit-web
```

### Static Files Not Loading

```bash
# Verify paths in nginx config
sudo nginx -t

# Check file permissions
ls -la /root/Summit/SummitDiscordBot/web-app/static/
ls -la /root/Summit/SummitDiscordBot/web-app/templates/avatar_imgs/

# Reload nginx
sudo systemctl reload nginx
```

### Discord OAuth Not Working

1. **Check redirect URI** in Discord Developer Portal
2. **Verify environment variable**:
   ```bash
   grep DISCORD_REDIRECT_URI /root/Summit/SummitDiscordBot/discord-bot/.env
   # Should be: https://sorcererssummit.com/auth/discord/callback
   ```
3. **Restart service** after .env changes:
   ```bash
   sudo systemctl restart summit-web
   ```

### Database Errors

```bash
# Check database file exists
ls -la /root/Summit/SummitDiscordBot/discord-bot/match_records.db
ls -la /root/Summit/SummitDiscordBot/discord-bot/elo.db

# Check permissions
chmod 644 /root/Summit/SummitDiscordBot/discord-bot/*.db
```

### High CPU/Memory Usage

```bash
# Check resource usage
htop

# Reduce gunicorn workers if needed
# Edit gunicorn_config.py and reduce workers count
nano /root/Summit/SummitDiscordBot/web-app/gunicorn_config.py

# Restart service
sudo systemctl restart summit-web
```

## Security Best Practices

1. **Keep system updated**:
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

2. **Set up firewall**:
   ```bash
   sudo ufw allow 22/tcp   # SSH
   sudo ufw allow 80/tcp   # HTTP
   sudo ufw allow 443/tcp  # HTTPS
   sudo ufw enable
   ```

3. **Rotate API keys** regularly in `.env`

4. **Monitor logs** for suspicious activity

5. **Set up log rotation** (already handled by systemd)

6. **Backup databases** regularly:
   ```bash
   # Create backup script
   #!/bin/bash
   DATE=$(date +%Y%m%d_%H%M%S)
   cp /root/Summit/SummitDiscordBot/discord-bot/*.db /root/backups/db_$DATE/
   ```

## Rollback Procedure

If deployment fails:

```bash
# Stop the service
sudo systemctl stop summit-web

# Revert code changes
cd /root/Summit/SummitDiscordBot
git log --oneline  # Find previous commit
git reset --hard <commit-hash>

# Restart service
sudo systemctl start summit-web
```

Temporary debugging (run Flask dev server):
```bash
cd /root/Summit/SummitDiscordBot/web-app
python3 app.py
```

## Performance Optimization

### Adjust Gunicorn Workers

Edit `gunicorn_config.py`:
```python
# Formula: (2 x CPU cores) + 1
workers = 4  # For 2-core server

# Or use dynamic calculation (current default):
import multiprocessing
workers = multiprocessing.cpu_count() * 2 + 1
```

### Enable Nginx Caching

Add to nginx config:
```nginx
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=my_cache:10m;

location / {
    proxy_cache my_cache;
    proxy_cache_valid 200 1h;
    # ... rest of config
}
```

### Database Optimization

For high traffic, consider:
- Migrating from SQLite to PostgreSQL
- Adding connection pooling
- Implementing Redis caching for API responses

## Monitoring Setup (Optional)

Set up monitoring with systemd timers:

```bash
# Create monitoring script
cat > /root/monitor.sh << 'EOF'
#!/bin/bash
if ! systemctl is-active --quiet summit-web; then
    echo "summit-web is down!" | mail -s "Service Alert" admin@example.com
    systemctl restart summit-web
fi
EOF

chmod +x /root/monitor.sh

# Add to crontab (check every 5 minutes)
(crontab -l 2>/dev/null; echo "*/5 * * * * /root/monitor.sh") | crontab -
```

## Additional Resources

- [Flask Documentation](https://flask.palletsprojects.com/)
- [Gunicorn Documentation](https://docs.gunicorn.org/)
- [Nginx Documentation](https://nginx.org/en/docs/)
- [Let's Encrypt Documentation](https://letsencrypt.org/docs/)
- [Systemd Documentation](https://www.freedesktop.org/software/systemd/man/)

## Support

For issues or questions:
1. Check logs: `sudo journalctl -u summit-web -f`
2. Review this documentation
3. Check GitHub Issues
4. Contact server administrator

---

**Last Updated**: January 2026
**Author**: Claude Code
**Version**: 1.0
