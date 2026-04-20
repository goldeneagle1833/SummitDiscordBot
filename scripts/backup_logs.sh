#!/bin/bash
# Backup logs to a dated folder on the server, then truncate the originals.
# Runs as part of the daily cron job (after daily_log_report.py).
#
# Usage: bash /root/Summit/SummitDiscordBot/scripts/backup_logs.sh
# Cron:  15 8 * * * bash /root/Summit/SummitDiscordBot/scripts/backup_logs.sh

BOT_LOG="/root/Summit/SummitDiscordBot/discord-bot/bot.log"
WEB_LOG="/var/log/summit-web/error.log"
BACKUP_ROOT="/root/Summit/log_archives"

DATE=$(date +%Y-%m-%d)
DEST="$BACKUP_ROOT/$DATE"

echo "=== Summit Log Backup ==="
echo "Date: $DATE"
echo "Destination: $DEST"
echo ""

mkdir -p "$DEST"

for LOG in "$BOT_LOG" "$WEB_LOG"; do
    FILENAME=$(basename "$LOG")
    if [ -f "$LOG" ] && [ -s "$LOG" ]; then
        cp "$LOG" "$DEST/$FILENAME"
        SIZE=$(du -sh "$DEST/$FILENAME" | cut -f1)
        echo "  Backed up $FILENAME ($SIZE)"
        truncate -s 0 "$LOG"
        echo "  Cleared $LOG"
    else
        echo "  $FILENAME not found or empty (skipped)"
    fi
done

echo ""
echo "Done. Backup saved to: $DEST"
