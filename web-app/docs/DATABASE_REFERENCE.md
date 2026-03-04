# Database Reference

Complete reference for all SQLite databases used by the Summit Discord Bot and Web App.

---

## Overview

The project uses **6 SQLite database files**. The discord-bot creates and owns all databases; the web-app shares 4 of them (read-mostly).

| Database | Location | Purpose |
|---|---|---|
| `elo.db` | `discord-bot/` | Player ELO ratings, events, archived standings |
| `match_records.db` | `discord-bot/` | Match history, pairings, challenges, external matches |
| `fart_scores.db` | `discord-bot/` | Fart game scores, history, cooldowns, shop items |
| `discord_purchases.db` | `discord-bot/` | Discord monetization purchase tracking |
| `community.db` | `discord-bot/` | Community resources (servers, YouTube channels, websites) |
| `streamers.db` | `data/` | Currently active streamers |

### Cross-System Access Matrix

| Table | discord-bot Reads | discord-bot Writes | web-app Reads | web-app Writes |
|---|---|---|---|---|
| **elo.db** | | | | |
| `overall_standings` | Yes | Yes | Yes | Yes (external matches) |
| `events` | Yes | Yes | Yes | No |
| `event_standings_archive` | Yes | Yes | Yes | No |
| `source_elo` | No | No | Yes | Yes |
| `user_links` | No | No | No | No |
| **match_records.db** | | | | |
| `match_records` | Yes | Yes | Yes | No |
| `match_records_archive` | No | Yes | Yes | No |
| `solo_match_reports` | Yes | Yes | Yes | No |
| `external_match_reports` | No | No | Yes | Yes |
| `challenge_matches` | No | No | No | No |
| `active_pairings` | Yes | Yes | No | No |
| `ladder_challenges` | Yes | Yes | No | No |
| **fart_scores.db** | | | | |
| `fart_scores` | Yes | Yes | Yes | No |
| `fart_history` | Yes | Yes | No | No |
| `protection_status` | Yes | Yes | No | No |
| `lucky_charms` | Yes | Yes | No | No |
| `lucky_charm_usage` | Yes | Yes | No | No |
| `command_usage` | Yes | Yes | No | No |
| `fart_leader_only_once` | Yes | Yes | No | No |
| `evil_star_usage` | Yes | Yes | No | No |
| **discord_purchases.db** | | | | |
| `purchase_records` | Yes | Yes | No | No |
| **community.db** | | | | |
| `discord_servers` | Yes | Yes | Yes | No |
| `youtube_channels` | Yes | Yes | Yes | No |
| `websites` | Yes | Yes | Yes | No |
| **streamers.db** | | | | |
| `active_streamers` | Yes | Yes | Yes | No |

---

## elo.db

### overall_standings

Player ELO ratings — both lifetime and per-event.

```sql
CREATE TABLE overall_standings (
    user_id INTEGER PRIMARY KEY,
    user_display_name TEXT,
    elo INTEGER DEFAULT 1500,
    event_elo INTEGER DEFAULT 1500
);
```

| Column | Type | Notes |
|---|---|---|
| `user_id` | INTEGER PK | Discord user ID |
| `user_display_name` | TEXT | Display name at time of last update |
| `elo` | INTEGER | Lifetime ELO (default 1500) |
| `event_elo` | INTEGER | Current event ELO (reset to 1500 on new event) |

**Read by:** `repositories/elo_repo.py` (`get_user_elo`, `get_user_event_elo`, `get_top_16_user_ids`), `cogs/elo.py` (`rank`, `leaderboard`, `event_leaderboard`, `masters_bracket`, `mystats`), `cogs/shop.py` (`get_sorted_players`), `web-app/repositories/elo.py`, `web-app/repositories/external_matches.py`

**Written by:** `services/elo_service.py` (`update_elo_db`, `update_elo_db_ladder`, `start_new_event`), `web-app/services/external_match.py` (via `upsert_overall_standings`)

---

### events

ELO seasons/events.

```sql
CREATE TABLE events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_name TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT,
    is_active BOOLEAN DEFAULT 1
);
```

| Column | Type | Notes |
|---|---|---|
| `event_id` | INTEGER PK | Auto-increment |
| `event_name` | TEXT | Event display name |
| `start_date` | TEXT | ISO datetime string |
| `end_date` | TEXT | NULL while active |
| `is_active` | BOOLEAN | Only one active at a time |

**Read by:** `repositories/elo_repo.py` (`get_active_event`, `get_past_events`), `web-app/repositories/elo.py`, `web-app/repositories/external_matches.py`

**Written by:** `services/elo_service.py` (`start_new_event`, `end_current_event`)

---

### event_standings_archive

Snapshot of final standings when an event ends.

```sql
CREATE TABLE event_standings_archive (
    archive_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    user_display_name TEXT,
    final_event_elo INTEGER,
    final_rank INTEGER,
    archived_at TEXT
);
```

**Read by:** `repositories/elo_repo.py` (`get_event_archive_standings`), `web-app/repositories/elo.py`, `web-app/routes/api/players.py`

**Written by:** `services/elo_service.py` (`end_current_event` — bulk insert from `overall_standings`)

---

### source_elo

Per-source ELO tracking for cross-platform integration (e.g., external tournament platforms).

```sql
CREATE TABLE source_elo (
    user_id TEXT NOT NULL,
    source TEXT NOT NULL,
    user_display_name TEXT,
    elo INTEGER DEFAULT 1500,
    PRIMARY KEY (user_id, source)
);
```

| Column | Type | Notes |
|---|---|---|
| `user_id` | TEXT | Source-specific user ID (not necessarily Discord ID) |
| `source` | TEXT | Platform name (e.g., "spellslingers") |
| `elo` | INTEGER | ELO for this specific source |

**Read by:** `web-app/repositories/external_matches.py` (`get_source_elo`, `get_source_elo_standings`, `get_all_source_elo_players`)

**Written by:** `web-app/repositories/external_matches.py` (`update_source_elo`)

---

### user_links

Cross-source account linking. **Created but never queried — see Removal Candidates.**

```sql
CREATE TABLE user_links (
    discord_user_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    source_user_id TEXT NOT NULL,
    linked_at TEXT NOT NULL,
    PRIMARY KEY (source, source_user_id)
);
```

**Read by:** None

**Written by:** Created via `ensure_tables()` in both `discord-bot/repositories/elo_repo.py` and `web-app/repositories/external_matches.py`, but no insert/update calls exist.

---

## match_records.db

### match_records

Primary match history with ELO changes and deck data. Cleared when an event ends (archived to `match_records_archive`).

```sql
CREATE TABLE match_records (
    match_id INTEGER PRIMARY KEY AUTOINCREMENT,
    reporter_id INTEGER,
    winner_id INTEGER,
    winner_display_name TEXT,
    losser_id INTEGER,
    losser_display_name TEXT,
    did_win BOOLEAN,
    timestamp TEXT,
    first_player TEXT,
    match_time INTEGER,
    curiosa_url TEXT,
    match_comment TEXT,
    json_deck_data TEXT,
    winner_elo_change INTEGER,
    loser_elo_change INTEGER,
    curiosa_url_winner TEXT,
    curiosa_url_loser TEXT,
    json_deck_data_winner TEXT,
    json_deck_data_loser TEXT,
    winner_went_first TEXT,
    loser_went_first TEXT
);
```

| Column | Type | Notes |
|---|---|---|
| `reporter_id` | INTEGER | Discord ID of who reported the match |
| `winner_id` / `losser_id` | INTEGER | Discord IDs (note: "losser" is a legacy typo) |
| `did_win` | BOOLEAN | From reporter's perspective |
| `timestamp` | TEXT | ISO datetime |
| `first_player` | TEXT | Legacy — replaced by `winner_went_first`/`loser_went_first` |
| `match_time` | INTEGER | Match duration in minutes |
| `curiosa_url` | TEXT | Legacy single deck URL |
| `curiosa_url_winner`/`_loser` | TEXT | Per-player deck URLs |
| `json_deck_data`/`_winner`/`_loser` | TEXT | JSON deck card data from Curiosa API |
| `winner_elo_change`/`loser_elo_change` | INTEGER | ELO delta for this match |
| `winner_went_first`/`loser_went_first` | TEXT | "Yes"/"No" per player |

**Read by:** `cogs/elo.py` (`mystats`, `mygames`, `replay`), `repositories/elo_repo.py` (`get_total_match_count`), `web-app/repositories/matches.py`, `web-app/services/metagame.py`, `web-app/routes/api/players.py`

**Written by:** `services/elo_service.py` (`winner_report`, `losser_report`)

---

### match_records_archive

Archived matches from completed events. Populated when `end_current_event()` runs.

```sql
CREATE TABLE match_records_archive (
    archive_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    original_match_id INTEGER,
    reporter_id INTEGER,
    winner_id INTEGER,
    winner_display_name TEXT,
    losser_id INTEGER,
    losser_display_name TEXT,
    did_win BOOLEAN,
    timestamp TEXT,
    first_player TEXT,
    match_time INTEGER,
    curiosa_url TEXT,
    curiosa_url_winner TEXT,
    curiosa_url_loser TEXT,
    match_comment TEXT,
    json_deck_data TEXT,
    json_deck_data_winner TEXT,
    json_deck_data_loser TEXT,
    winner_elo_change INTEGER,
    loser_elo_change INTEGER,
    winner_lifetime_elo_change INTEGER,
    loser_lifetime_elo_change INTEGER,
    archived_at TEXT
);
```

Same columns as `match_records` plus `event_id`, `original_match_id`, `archived_at`, and lifetime ELO change columns.

**Read by:** `web-app/repositories/matches.py`, `web-app/services/metagame.py`, `web-app/routes/api/players.py`

**Written by:** `services/elo_service.py` (`end_current_event` — bulk copy from `match_records`, then `match_records` is cleared)

---

### solo_match_reports

Solo/casual match reports that don't affect ELO (self-reported, no opponent confirmation).

```sql
CREATE TABLE solo_match_reports (
    report_id INTEGER PRIMARY KEY AUTOINCREMENT,
    reporter_id INTEGER,
    reporter_name TEXT,
    opponent_name TEXT,
    is_winner BOOLEAN,
    first_player TEXT,
    match_time INTEGER,
    curiosa_link TEXT,
    match_comment TEXT,
    report_date DATETIME,
    json_deck_data TEXT
);
```

**Read by:** `cogs/elo.py` (`mystats`, `mygames` — UNION with `match_records`), `web-app/routes/api/players.py`

**Written by:** `services/elo_service.py` (`solo_match_report`)

---

### external_match_reports

Matches imported from external sources (tournament platforms, etc.). Written primarily by the web-app.

```sql
CREATE TABLE external_match_reports (
    report_id INTEGER PRIMARY KEY AUTOINCREMENT,
    winner_id TEXT NOT NULL,
    loser_id TEXT NOT NULL,
    winner_display_name TEXT,
    loser_display_name TEXT,
    winner_deck_url TEXT,
    loser_deck_url TEXT,
    json_deck_data_winner TEXT,
    json_deck_data_loser TEXT,
    winner_went_first TEXT,
    match_time INTEGER,
    match_comment TEXT,
    source TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    winner_elo_change INTEGER,
    loser_elo_change INTEGER,
    winner_main_elo_change INTEGER,
    loser_main_elo_change INTEGER
);
```

| Column | Type | Notes |
|---|---|---|
| `winner_id`/`loser_id` | TEXT | Source-specific user IDs (not necessarily Discord IDs) |
| `source` | TEXT | Platform name matching `source_elo.source` |
| `winner_main_elo_change`/`loser_main_elo_change` | INTEGER | Added by migration — tracks main ELO impact |

**Read by:** `web-app/repositories/external_matches.py`, `web-app/repositories/matches.py` (win/loss counts)

**Written by:** `web-app/repositories/external_matches.py` (`insert_report`)

---

### challenge_matches

**DEAD CODE — See Removal Candidates.**

```sql
CREATE TABLE challenge_matches (
    match_id INTEGER PRIMARY KEY AUTOINCREMENT,
    challenger_id INTEGER NOT NULL,
    challenged_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    match_time DATETIME NOT NULL,
    winner_id INTEGER,
    curiosa_url TEXT,
    match_comment TEXT,
    json_deck_data TEXT
);
```

**Read by:** None

**Written by:** `save_challenge_match()` is defined in `elo_repo.py` but never called from any cog. Only referenced in `!wipe` admin command (table recreation).

---

### active_pairings

Tracks active LFG queue match pairings.

```sql
CREATE TABLE active_pairings (
    pairing_id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    player1_id INTEGER NOT NULL,
    player2_id INTEGER NOT NULL,
    player1_deck_url TEXT,
    player2_deck_url TEXT,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
);
```

| Column | Type | Notes |
|---|---|---|
| `status` | TEXT | `'active'`, `'reported'`, `'cancelled'`, `'expired'` |

**Read by:** `repositories/elo_repo.py` (`get_active_pairing_for_user`, `get_opponent_from_pairing`, `get_pairing_between_players`, `validate_pairing`)

**Written by:** `repositories/elo_repo.py` (`save_pairing`, `mark_pairing_reported`, `cancel_pairing`, `cleanup_old_pairings`)

---

### ladder_challenges

Top-16 ladder challenge tracking.

```sql
CREATE TABLE ladder_challenges (
    challenge_id INTEGER PRIMARY KEY AUTOINCREMENT,
    challenger_id INTEGER NOT NULL,
    selected_opponent_id INTEGER,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL,
    completed_at TEXT,
    winner_id INTEGER,
    match_id INTEGER
);
```

| Column | Type | Notes |
|---|---|---|
| `status` | TEXT | `'open'`, `'completed'` |

**Read by:** `repositories/elo_repo.py` (`get_ladder_challenge_today`)

**Written by:** `repositories/elo_repo.py` (`save_ladder_challenge`, `complete_ladder_challenge`, `delete_ladder_challenge`)

---

## fart_scores.db

### fart_scores

Main fart game scores and cooldown tracking.

```sql
CREATE TABLE fart_scores (
    user_id INTEGER PRIMARY KEY,
    user_display_name TEXT,
    date_last_updated TEXT,
    score INTEGER
);
```

| Column | Type | Notes |
|---|---|---|
| `user_id` | INTEGER PK | Discord user ID |
| `date_last_updated` | TEXT | ISO datetime — used for daily fart cooldown |
| `score` | INTEGER | Fart points (currency for shop) |

**Read by:** `cogs/fun.py` (`fart`, `fartrank`, `fartleaderboard`, `attackfart`, `syphonfart`, `syphonstatus`, `bullfart`, `taxes`, `wealth`, `update_fart_leader_role`), `cogs/shop.py` (`check_points`, `get_sorted_players`), `web-app/repositories/fart.py`

**Written by:** `cogs/fun.py` (`save_fart_score`, `fart`, `attackfart`, `syphonfart`, `bullfart`, `taxes`, `wealth`, `reset_fart_cooldown`), `cogs/shop.py` (`deduct_points`, `deduct_damage`, `star`)

---

### fart_history

Tracks fart type history for bullfart bonus calculation.

```sql
CREATE TABLE fart_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    fart_type TEXT NOT NULL,
    roll INTEGER NOT NULL,
    timestamp TEXT NOT NULL
);
```

**Read by:** `cogs/fun.py` (`bullfart` — reads last fart type for bonus)

**Written by:** `cogs/fun.py` (`save_fart_type` — called from `fart` and `fartprediction`)

---

### protection_status

Star protection from shop items (prevents point theft attacks).

```sql
CREATE TABLE protection_status (
    user_id INTEGER PRIMARY KEY,
    protected_until TIMESTAMP
);
```

**Read by:** `cogs/shop.py` (`is_protected` — checked by all attack items: blue_shell, red_shell, etc.)

**Written by:** `cogs/shop.py` (`star` — 24hr protection, `blue_star` — 12hr protection, `fart_star` — removes random protection)

---

### lucky_charms

Active mushroom boost status. Row exists = boost is active. Deleted after use.

```sql
CREATE TABLE lucky_charms (
    user_id INTEGER PRIMARY KEY,
    activated_at TEXT
);
```

**Read by:** `cogs/fun.py` (`fart`, `fartprediction` — check and consume boost), `cogs/fun.py` (`mushroom` — check if already active)

**Written by:** `cogs/shop.py` (`mushroom` — INSERT), `cogs/fun.py` (`fart`, `fartprediction` — DELETE after consuming)

---

### lucky_charm_usage

Weekly cooldown tracking for mushroom boost purchases.

```sql
CREATE TABLE lucky_charm_usage (
    user_id INTEGER,
    command_name TEXT,
    last_used TEXT,
    PRIMARY KEY (user_id, command_name)
);
```

**Read by:** `cogs/shop.py` (`mushroom` — check weekly cooldown)

**Written by:** `cogs/shop.py` (`mushroom` — INSERT OR UPDATE `last_used`)

---

### command_usage

Weekly cooldown tracking for special commands (e.g., bullfart).

```sql
CREATE TABLE command_usage (
    user_id INTEGER,
    command_name TEXT,
    last_used TEXT,
    PRIMARY KEY (user_id, command_name)
);
```

**Read by:** `cogs/fun.py` (`bullfart` — check weekly cooldown)

**Written by:** `cogs/fun.py` (`bullfart` — INSERT OR REPLACE `last_used`)

---

### fart_leader_only_once

Tracks one-time-per-reign leader commands (taxes, wealth).

```sql
CREATE TABLE fart_leader_only_once (
    user_id INTEGER PRIMARY KEY,
    user_display_name TEXT
);
```

**Read by:** `cogs/fun.py` (`taxes`, `wealth` — check if already used this reign)

**Written by:** `cogs/fun.py` (`taxes`, `wealth` — INSERT OR REPLACE when used)

---

### evil_star_usage

Tracks one-time evil star use (doubles 666 points to 1332).

```sql
CREATE TABLE evil_star_usage (
    user_id INTEGER PRIMARY KEY,
    used_at TEXT NOT NULL
);
```

**Read by:** `cogs/shop.py` (`evil_star` — check if already used, `fart_star` — blocks if user used evil_star)

**Written by:** `cogs/shop.py` (`evil_star` — INSERT on use)

---

## discord_purchases.db

### purchase_records

Discord monetization purchase tracking (subscriptions, server products).

```sql
CREATE TABLE purchase_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    user_discriminator TEXT,
    purchase_type TEXT NOT NULL,
    sku_id TEXT,
    sku_name TEXT,
    entitlement_id TEXT,
    subscription_id TEXT,
    guild_id INTEGER,
    purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    is_active BOOLEAN DEFAULT 1,
    notes TEXT
);
```

**Read by:** `cogs/purchase_tracking.py` (`purchase_history`, `purchase_stats`)

**Written by:** `cogs/purchase_tracking.py` (`log_discord_purchase`, entitlement event listeners, `test_purchase_log`)

**Note:** `setup_purchase_database()` is duplicated in both `cogs/purchase_tracking.py` and `cogs/shop.py` — cleanup candidate.

---

## community.db

### discord_servers

Community Discord server listings.

```sql
CREATE TABLE discord_servers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    invite_url TEXT NOT NULL,
    state TEXT NOT NULL,
    added_by INTEGER,
    added_at TEXT
);
```

| Column | Type | Notes |
|---|---|---|
| `state` | TEXT | Location info (city, state, country, region) — not US state only |

**Read by:** `repositories/community_repo.py` (`get_all_discord_servers`), `web-app/repositories/community.py`

**Written by:** `repositories/community_repo.py` (`add_discord_server`, `remove_entry`)

---

### youtube_channels

Community YouTube channel listings.

```sql
CREATE TABLE youtube_channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    channel_url TEXT NOT NULL,
    added_by INTEGER,
    added_at TEXT
);
```

**Read by:** `repositories/community_repo.py` (`get_all_youtube_channels`), `web-app/repositories/community.py`

**Written by:** `repositories/community_repo.py` (`add_youtube_channel`, `remove_entry`)

---

### websites

Community website listings.

```sql
CREATE TABLE websites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    url TEXT NOT NULL,
    added_by INTEGER,
    added_at TEXT
);
```

**Read by:** `repositories/community_repo.py` (`get_all_websites`), `web-app/repositories/community.py`

**Written by:** `repositories/community_repo.py` (`add_website`, `remove_entry`)

---

## streamers.db

### active_streamers

Currently live streamers. Ephemeral — rows are added/removed as members go live.

```sql
CREATE TABLE active_streamers (
    user_id INTEGER PRIMARY KEY,
    username TEXT NOT NULL,
    display_name TEXT NOT NULL,
    avatar_url TEXT,
    stream_url TEXT,
    stream_title TEXT,
    game_name TEXT,
    platform TEXT,
    started_at TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
```

| Column | Type | Notes |
|---|---|---|
| `platform` | TEXT | "Twitch", "YouTube", "Discord Go Live" |
| `last_seen` | TEXT | Used by `cleanup_stale_streamers` (removes if >30 min stale) |

**Location:** `data/streamers.db` (not in `discord-bot/`)

**Read by:** `cogs/streaming.py` (`list_streamers`, debug commands), `web-app/routes/api/streamers.py`

**Written by:** `cogs/streaming.py` (`_add_streamer`, `_add_voice_streamer`, `_remove_streamer`, `cleanup_stale_streamers`, `refresh_streamers`)

---

## Removal Candidates

### Recommended for removal

| Table | Database | Reason |
|---|---|---|
| `challenge_matches` | match_records.db | **Dead code.** `save_challenge_match()` exists in `elo_repo.py` and is exported via `database.py`, but is **never called** from any cog or service. The table is only referenced in the `!wipe` admin command (table recreation). No production reads or writes. |
| `user_links` | elo.db | **Dead code.** Table is created by `ensure_tables()` in both discord-bot and web-app, but **no code ever inserts into or queries** it. The external match system works without account linking. |

### Review candidates (not recommended for removal, but worth noting)

| Table | Database | Notes |
|---|---|---|
| `fart_history` | fart_scores.db | Only used by `bullfart()` bonus calculation. Actively used but accumulates rows indefinitely with no cleanup. Consider adding a retention policy. |
| `fart_leader_only_once` | fart_scores.db | Could theoretically be an in-memory set since it resets on leadership change, but persisting it across restarts is useful. Keep. |
| `purchase_records` setup | discord_purchases.db | `setup_purchase_database()` is **duplicated** in both `purchase_tracking.py` and `shop.py`. Should be deduplicated into one location. |

### Legacy columns in match_records

These columns in `match_records` are superseded but still populated:
- `curiosa_url` — replaced by `curiosa_url_winner` / `curiosa_url_loser`
- `json_deck_data` — replaced by `json_deck_data_winner` / `json_deck_data_loser`
- `first_player` — replaced by `winner_went_first` / `loser_went_first`

These should not be removed (SQLite doesn't support DROP COLUMN easily) but new code should use the per-player columns.

---

## Key Patterns

### Connection management
All database connections use `sqlite3.connect()` with manual `conn.close()` in `finally` blocks. Connections are opened and closed per function call — no connection pooling.

### Schema migration
Tables use `CREATE TABLE IF NOT EXISTS`. Column additions use `ALTER TABLE` wrapped in `try/except` to handle the case where the column already exists.

### Timestamps
All timestamps are ISO format strings via `datetime.datetime.now().isoformat()`. The `fart_scores.db` cooldown system compares dates in EST timezone.

### Dual ELO system
Players have two ELO ratings in `overall_standings`:
- **`elo`** — Lifetime ELO, never resets
- **`event_elo`** — Resets to 1500 when a new event starts via `start_new_event()`

Both are updated on every match. When an event ends, `event_standings_archive` snapshots the final standings.

### Facade pattern
`discord-bot/utils/database.py` re-exports all functions from `repositories/elo_repo.py` and `services/elo_service.py`. Callers can `from utils.database import X` without knowing the internal split.
