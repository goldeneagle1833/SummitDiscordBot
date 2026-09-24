# Server and Database Upgrade Plan

**Reviewed:** 2026-09-24
**Phase 1 and 2 applied on the server:** 2026-09-24 (no service restarts; see the checklist and the status notes at the bottom)
**Scope:** production host (`/root/Summit/SummitDiscordBot`) and every SQLite database the bot and web app share.

The good news first. Both services are stable: memory is comfortable, load is low, the 5xx rate over the last week rounds to zero, and every database passes an integrity check. The four shared databases are already in WAL mode, migrations run on startup, and the monitoring database already prunes itself. Everything below builds on that foundation.

The plan is grouped into four phases. Each item has a payoff, the steps to get there, and a way to confirm it worked.

---

## Phase 1: Protect the data (this week)

### 1.1 Nightly database backups, kept off the box

**Payoff.** Match history, ELO, store orders and Explorer applications survive a disk failure, a bad migration, or a mistyped `rm`.

**Steps.**
1. Add `scripts/backup_databases.sh` that uses SQLite's online backup so it is safe while the apps are live:
   ```bash
   #!/usr/bin/env bash
   set -euo pipefail
   DEST=/root/backups/$(date +%F)
   mkdir -p "$DEST"
   cd /root/Summit/SummitDiscordBot
   for db in discord-bot/{match_records,elo,fart_scores,community,discord_purchases,reddit_bridge}.db \
             web-app/{analytics,monitoring,explorer,rumble,store,deck_builder,feedback}.db \
             data/streamers.db; do
     [ -f "$db" ] && sqlite3 "$db" ".backup '$DEST/$(basename "$db")'"
   done
   tar -czf "$DEST.tar.gz" -C /root/backups "$(date +%F)" && rm -rf "$DEST"
   find /root/backups -name '*.tar.gz' -mtime +14 -delete
   ```
2. Replace the dead cron line (`backup_logs.sh` no longer exists) with:
   ```
   15 2 * * * bash /root/Summit/SummitDiscordBot/scripts/backup_databases.sh >> /root/Summit/backup.log 2>&1
   ```
3. Ship the archive off-box. Cheapest options: enable Linode Backups on the instance, or `rclone copy /root/backups remote:summit-backups` to Backblaze B2 after the tar step.
4. Schedule the existing `web-app/scripts/backup_store_db.py` as well, since it already handles rotation for orders.

**Confirm.** `ls /root/backups` shows a dated archive the next morning, and `sqlite3 restored.db "pragma integrity_check"` returns `ok` on a restored copy.

### 1.2 Lock the front door

**Payoff.** The 5,000+ daily password-guessing attempts against root stop mattering, and the deploy path stays the same.

**Steps.**
1. Confirm the GitHub Actions deploy key and your own key are in `/root/.ssh/authorized_keys`.
2. In `/etc/ssh/sshd_config` set `PermitRootLogin prohibit-password` and `PasswordAuthentication no`, then `systemctl reload ssh`. Keep your current session open until a fresh key login succeeds.
3. `apt install fail2ban` and enable the default `sshd` jail.
4. Turn on the firewall, allowing SSH from anywhere and HTTP only from Cloudflare:
   ```bash
   ufw default deny incoming
   ufw allow 22/tcp
   for r in $(curl -s https://www.cloudflare.com/ips-v4) $(curl -s https://www.cloudflare.com/ips-v6); do ufw allow from "$r" to any port 80 proto tcp; done
   ufw enable
   ```
   This also closes the gap where the origin IP could be hit directly, skipping Cloudflare caching and bot protection.

**Confirm.** `ssh -o PubkeyAuthentication=no root@host` is refused, `curl http://50.116.43.215` times out from a non-Cloudflare address, and `journalctl -u ssh --since "1 day ago" | grep -c "Failed password"` drops to zero.

### 1.3 Log rotation and a journal cap

**Payoff.** Reclaims roughly 11 GB now and stops the slow march toward a full disk.

| Log | Today | After |
|---|---|---|
| `/var/log/summit-web/access.log` | 7.2 GB | 14 daily files, compressed |
| systemd journal | 4.0 GB | capped at 500 MB |
| `discord-bot/bot.log` | 165 MB | weekly rotation, 4 kept |

**Steps.**
1. `/etc/logrotate.d/summit`:
   ```
   /var/log/summit-web/*.log /root/Summit/SummitDiscordBot/discord-bot/bot.log {
       daily
       rotate 14
       compress
       delaycompress
       missingok
       notifempty
       copytruncate
   }
   ```
   `copytruncate` means neither gunicorn nor the bot needs a restart or a reopen signal.
2. In `/etc/systemd/journald.conf` set `SystemMaxUse=500M`, then `systemctl restart systemd-journald` and `journalctl --vacuum-size=500M`.
3. Run `logrotate -f /etc/logrotate.d/summit` once to take the first cut of the 7 GB file.

**Confirm.** `df -h /` shows the space back, and `ls /var/log/summit-web` shows a rotated `.1` file the next day.

---

## Phase 2: Tidy the host (next two weeks)

### 2.1 Reclaim disk from leftovers

**Payoff.** Another 3.5 GB back and a repo directory that matches what is in git.

| Item | Size | Action |
|---|---|---|
| `web-app/card_images_backup_2026-09-21/` | 3.2 GB | Delete once `card_images/` is confirmed good |
| `discord-bot/deck_data_test.json` | 254 MB | Delete, it is test data that also lives at the repo root |
| `discord-bot/1`, `discord-bot/udo journalctl ...` | tiny | Delete, they are mistyped-command captures |
| `web-app/card_images_dupes/` | small | Review, then delete |
| `SorceryAI/` | 15 MB | Move out of the repo checkout or add to `.gitignore` |

`git status` on the server should end up clean apart from uploads under `web-app/static/uploads/`.

### 2.2 Retire orphan database files

**Payoff.** Backups and future migrations only touch databases that are actually in use.

These files are not referenced by any current code path:

- `web-app/match_records.db` (a stale copy from January; the web app reads the bot's copy)
- `elo.db` at the repo root and `discord-bot/utils/elo.db` (both zero bytes)
- `discord-bot/profiles.db`
- `discord-bot/facebook_bridge.db`

Move them into the first backup archive, then delete them from the working tree.

### 2.3 Align the service unit with the repo

**Payoff.** The next person who copies `web-app/systemd/summit-web.service` onto a server gets the working config.

The server unit starts gunicorn from `web-app/venv/bin/gunicorn`; the repo copy points at `/usr/local/bin/gunicorn`. Update the repo copy to the venv path. While there, uncomment `PrivateTmp=true` and `NoNewPrivileges=true`, move the socket from `/tmp/summit-web.sock` to `/run/summit-web/summit-web.sock` with `RuntimeDirectory=summit-web`, and tighten `.env` to `chmod 600`.

### 2.4 Apply pending updates

86 packages are waiting. Unattended upgrades already handle security patches, so this is `apt upgrade` plus a reboot at a quiet hour. Uptime is 157 days, so a reboot also confirms both services come back on their own.

---

## Phase 3: Slim and index the databases (next month)

### 3.1 Store each deck once

**Payoff.** `match_records.db` drops from 817 MB to well under 100 MB, so backups, `VACUUM`, and any full-table scan become fast.

Today every archived match stores its deck JSON three times: a legacy `json_deck_data` column plus `json_deck_data_winner` and `json_deck_data_loser`, at about 43 KB per copy.

| Table | Size | Of which deck JSON |
|---|---|---|
| `match_records_archive` | 613 MB | 598 MB |
| `match_records` | 174 MB | 170 MB |

**Steps.**
1. Add a `decks` table keyed by a SHA-256 of the normalized deck JSON, with `curiosa_url`, `avatar_name`, `json_data`, `first_seen`.
2. Add `winner_deck_id` and `loser_deck_id` to the match tables, backfill by hashing existing JSON, and point the read paths at the join.
3. Drop the three JSON columns and `VACUUM`.
4. Same treatment for `rumble_match_records`, `match_reports_web`, and the limited tables, which share the pattern.

A quick win that needs no code changes: drop only the legacy `json_deck_data` column where it duplicates the winner column, which alone frees about 260 MB.

### 3.2 Give the live match table a key and indexes

**Payoff.** Leaderboard, player page and archive queries stop scanning 3,500 rows, and the table can be referenced by id instead of the implicit rowid that `recalculate_event_elo.py` relies on today.

```sql
-- new migration
CREATE TABLE match_records_new (match_id INTEGER PRIMARY KEY AUTOINCREMENT, ...same columns...);
INSERT INTO match_records_new SELECT rowid, * FROM match_records;
DROP TABLE match_records; ALTER TABLE match_records_new RENAME TO match_records;
CREATE INDEX idx_match_records_winner ON match_records(winner_id);
CREATE INDEX idx_match_records_loser ON match_records(losser_id);
CREATE INDEX idx_match_records_timestamp ON match_records(timestamp);
CREATE INDEX idx_match_records_archive_event ON match_records_archive(event_id);
CREATE INDEX idx_solo_reports_reporter ON solo_match_reports(reporter_id);
```

Also worth indexing while there: `overall_standings(elo)` and `event_standings_archive(event_id)` in `elo.db`, which currently has no indexes at all.

### 3.3 Move analytics to WAL and add retention

**Payoff.** Page-view logging stops competing with page-view reporting for the same lock, and the file stops growing forever.

- Add `ANALYTICS_DB_PATH` and `MONITORING_DB_PATH` to the tuple in `web-app/migrations/enable_wal_mode.py`.
- Give the analytics connection `timeout=5` and `PRAGMA busy_timeout`, matching what the bot databases already do.
- Add a nightly prune: keep 90 days of `page_views` and `session_page_views`, roll older rows into a daily summary table if the admin dashboard needs history.

Current size is 116 MB with 356,000 raw page views since April.

### 3.4 Prune finished pairings and callbacks

**Payoff.** The bot's hottest table stays small.

`active_pairings` has 19,478 rows, of which 19 are active. Add a weekly job that deletes `reported` and `expired` rows older than 30 days, and cap `sorcery_online_match_callbacks` the same way once the PSO integration has settled.

---

## Phase 4: One schema owner (ongoing)

### 4.1 A schema version table

**Payoff.** You can tell at a glance which migrations have run on which database, and a migration can safely be non-idempotent.

Add `schema_migrations(name TEXT PRIMARY KEY, applied_at TEXT)` to each database. The startup runner in `web-app/app.py` records each migration after it succeeds and skips ones already recorded. The bot's lazy `CREATE TABLE IF NOT EXISTS` calls can then move into the same runner so only one side creates tables.

### 4.2 Collapse the match tables

**Payoff.** One place to add a column, one place to fix the `losser_id` spelling, one query for "every game this player has played".

Eight tables today carry the same match shape: live, archive, web reports, rumble, limited, limited archive, external matches, external reports, plus `season_match_elo`. A single `matches` table with `format` (`ranked`, `casual`, `rumble`, `limited`, `external`) and `event_id` columns, plus the `decks` table from 3.1, covers all of them. Views can preserve the old names while callers migrate.

### 4.3 Declare foreign keys as tables are rebuilt

There are none today across roughly 120 tables. Each rebuild in Phase 3 is a chance to add `REFERENCES` clauses, and `PRAGMA foreign_keys=ON` on connection open makes SQLite enforce them.

---

## Checklist

- [x] 1.1 Nightly backups running (`/root/backups`, 14 kept, 02:15 UTC) — **off-box copy still to do** (enable Linode Backups or add an rclone target)
- [x] 1.2 Key-only SSH, fail2ban, firewall with Cloudflare-only port 80
- [x] 1.3 logrotate for gunicorn and bot logs, journald capped at 500 MB
- [x] 2.1 Leftover files removed (disk 34% → 16%)
- [x] 2.2 Orphan `.db` files archived to `/root/backups/orphans/` and deleted
- [x] 2.3 Repo service unit now matches the server's ExecStart (hardening flags deferred, see notes)
- [ ] 2.4 Packages upgraded, reboot verified — needs a maintenance window
- [ ] 3.1 Deck JSON stored once
- [~] 3.2 Indexes on match tables — migration written (`add_match_records_indexes.py`), ships with the next deploy; primary-key rebuild deferred
- [~] 3.3 Analytics in WAL (done on the server and in the migration); 90-day retention **needs a decision** on whether all-time page-view totals must stay exact
- [ ] 3.4 Pairing and callback pruning scheduled
- [ ] 4.1 `schema_migrations` table in every database
- [ ] 4.2 Match tables collapsed behind views
- [ ] 4.3 Foreign keys declared and enforced

## Status notes (2026-09-24)

**What is now in place on the server**

- `/root/Summit/scripts/backup_databases.sh` (copy in `scripts/`) runs nightly from root's crontab. Each archive holds every live database (verified with `quick_check`) plus the server-only data that is not in git: `top-8-decks-by-event/`, `static/uploads/`, `templates/avatar_imgs/`, `curiosa-io-tools/`. First archive: 139 MB. `card_images/` (3 GB) is excluded because it is regenerated.
- `/etc/ssh/sshd_config.d/00-summit-hardening.conf` (copy in `server/sshd-hardening.conf`). Password login is refused; the workstation key and the GitHub Actions deploy key are the same ED25519 key, so deploys are unaffected.
- fail2ban with `server/fail2ban-jail.local`; the operator's home IP is in `ignoreip`.
- ufw enabled by `server/ufw-cloudflare.sh` (also at `/root/Summit/scripts/`): 22 open, 80 only from Cloudflare's 22 published ranges. Re-run the script if Cloudflare changes its ranges. Direct hits on the origin IP now time out; the site through Cloudflare was verified unchanged.
- `/etc/logrotate.d/summit` (copy in `server/logrotate-summit.conf`) with `copytruncate`, so no restarts. The 7.2 GB gunicorn access log was trimmed to its last 300k lines.
- `analytics.db` switched to WAL in place; the `enable_wal_mode` migration now covers it and `monitoring.db` so a fresh checkout gets the same.
- `.env` is `chmod 600`.

**Deferred on purpose**

- `PrivateTmp=true` on the web service would hide the gunicorn socket from nginx (it lives in `/tmp`). Move the socket to `/run/summit-web/` in both the unit and the nginx config before turning it on.
- The match table primary-key rebuild changes the table under a live bot; do it in a maintenance window with a fresh backup.
- Page-view retention: the admin dashboard shows all-time totals. Either keep raw rows forever, or add a daily rollup table before pruning.

**Verification performed after the changes**

Leaderboard, events, store, streamers and the SPA all returned the same status and payload sizes through Cloudflare as before. The bot processed a Sorcery Online match during the work with no errors. Leaderboard responses take ~25 s both before and after; that is pre-existing (see 3.1 and 3.2).
