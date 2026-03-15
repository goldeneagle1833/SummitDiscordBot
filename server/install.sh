#!/bin/bash
# Installation script for daily log report system
# Run this on the server as root

set -e  # Exit on error

echo "========================================="
echo "Summit Bot - Daily Log Report Installer"
echo "========================================="

# Create directory for scripts
SCRIPTS_DIR="/root/Summit/scripts"
echo "Creating scripts directory at $SCRIPTS_DIR..."
mkdir -p "$SCRIPTS_DIR"

# Create log archive directory
LOG_ARCHIVE_DIR="/root/Summit/log_archives"
echo "Creating log archive directory at $LOG_ARCHIVE_DIR..."
mkdir -p "$LOG_ARCHIVE_DIR"

# Copy the script
echo "Copying daily_log_report.py..."
cp daily_log_report.py "$SCRIPTS_DIR/"
chmod +x "$SCRIPTS_DIR/daily_log_report.py"

# Create email config if it doesn't exist
if [ ! -f "$SCRIPTS_DIR/email_config.json" ]; then
    echo "Creating email_config.json template..."
    cp email_config.json.template "$SCRIPTS_DIR/email_config.json"
    echo ""
    echo "⚠️  IMPORTANT: Edit $SCRIPTS_DIR/email_config.json with your email settings"
    echo "   nano $SCRIPTS_DIR/email_config.json"
    echo ""
else
    echo "email_config.json already exists, skipping..."
fi

# Test Python availability
echo "Testing Python..."
if ! command -v python3 &> /dev/null; then
    echo "✗ Python 3 not found. Installing..."
    apt-get update
    apt-get install -y python3
else
    echo "✓ Python 3 found: $(python3 --version)"
fi

# Set up cron job for 7 AM EST (12 PM UTC)
echo ""
echo "Setting up cron job for 7 AM EST (12 PM UTC)..."
CRON_JOB="0 12 * * * /usr/bin/python3 $SCRIPTS_DIR/daily_log_report.py >> /root/Summit/log_report.log 2>&1"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "daily_log_report.py"; then
    echo "Cron job already exists, skipping..."
else
    # Add cron job
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    echo "✓ Cron job added"
fi

echo ""
echo "========================================="
echo "Installation Complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Edit email configuration:"
echo "   nano $SCRIPTS_DIR/email_config.json"
echo ""
echo "2. Test the script manually:"
echo "   python3 $SCRIPTS_DIR/daily_log_report.py"
echo ""
echo "3. View cron jobs:"
echo "   crontab -l"
echo ""
echo "The script will run automatically every day at 7 AM EST (12 PM UTC)"
echo "Logs will be saved to: /root/Summit/log_report.log"
