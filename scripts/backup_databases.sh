#!/usr/bin/env bash
# Nightly online backup of every live SQLite database (bot + web app).
# Safe to run while both services are up: uses sqlite3's .backup, which
# takes a consistent snapshot without locking writers out.
#
# Cron (installed on the server):
#   15 2 * * * bash /root/Summit/scripts/backup_databases.sh >> /root/Summit/backup.log 2>&1
#
# Restore one file:  sqlite3 restored.db ".restore '/root/backups/<date>/elo.db'"
set -euo pipefail

REPO=${REPO:-/root/Summit/SummitDiscordBot}
ROOT=${BACKUP_ROOT:-/root/backups}
KEEP_DAYS=${KEEP_DAYS:-14}
STAMP=$(date +%F)
DEST="$ROOT/$STAMP"

mkdir -p "$DEST"
cd "$REPO"

DBS=(
  discord-bot/match_records.db
  discord-bot/elo.db
  discord-bot/fart_scores.db
  discord-bot/community.db
  discord-bot/discord_purchases.db
  discord-bot/reddit_bridge.db
  web-app/analytics.db
  web-app/monitoring.db
  web-app/explorer.db
  web-app/rumble.db
  web-app/store.db
  web-app/deck_builder.db
  web-app/feedback.db
  data/streamers.db
)

echo "[$(date -Is)] backup start -> $DEST"
for db in "${DBS[@]}"; do
  [ -f "$db" ] || { echo "  skip (missing): $db"; continue; }
  out="$DEST/$(basename "$db")"
  sqlite3 "$db" ".timeout 30000" ".backup '$out'"
  ok=$(sqlite3 "$out" "pragma quick_check" | head -1)
  printf "  %-32s %8s KB  %s\n" "$db" "$(( $(stat -c %s "$out") / 1024 ))" "$ok"
done

# Data that lives only on the server (not in git): tournament top-8 decks,
# uploaded banners/curios/store images, avatar images, card catalog JSON.
# card_images/ (3 GB) is excluded; it is regenerated from Curiosa.
for d in web-app/top-8-decks-by-event web-app/static/uploads web-app/templates/avatar_imgs web-app/curiosa-io-tools; do
  [ -d "$d" ] && tar -czf "$DEST/$(echo "$d" | tr / _).tar.gz" "$d" && printf "  %-32s %8s KB
" "$d" "$(( $(stat -c %s "$DEST/$(echo "$d" | tr / _).tar.gz") / 1024 ))"
done

tar -czf "$DEST.tar.gz" -C "$ROOT" "$STAMP"
rm -rf "$DEST"
find "$ROOT" -maxdepth 1 -name '*.tar.gz' -mtime +"$KEEP_DAYS" -delete
echo "[$(date -Is)] backup done: $(du -h "$DEST.tar.gz" | cut -f1)  (kept: $(ls "$ROOT"/*.tar.gz | wc -l))"
