# Multi-Server Support Plan

This document outlines the changes required to make the Summit Discord Bot available to multiple servers, allowing each server to host their own LFG channel and maintain server-specific or cross-server leaderboards.

## Overview

Currently, the bot is designed for a single server with hardcoded channel IDs and role IDs. To support multiple servers, we need to:

1. **Database Changes** - Add guild/server identifiers to all records
2. **Configuration System** - Per-server configuration storage
3. **Command Updates** - Server-aware commands and leaderboards
4. **Admin Tools** - Server setup and configuration commands

---

## Phase 1: Database Schema Updates

### 1.1 match_records Table

Add `guild_id` column to track which server the match was reported from.

```sql
-- Migration
ALTER TABLE match_records ADD COLUMN guild_id INTEGER;

-- New schema
CREATE TABLE IF NOT EXISTS match_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,                    -- NEW: Discord server ID
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
    loser_elo_change INTEGER
);

-- Index for faster server-specific queries
CREATE INDEX idx_match_records_guild ON match_records(guild_id);
```

### 1.2 solo_match_reports Table

```sql
-- Migration
ALTER TABLE solo_match_reports ADD COLUMN guild_id INTEGER;

-- New schema includes guild_id
CREATE TABLE IF NOT EXISTS solo_match_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,                    -- NEW: Discord server ID
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

### 1.3 overall_standings Table (elo.db)

Option A: **Global ELO** (single rating across all servers)

- Keep current schema, no changes needed
- Players have one ELO regardless of which server they play on

Option B: **Per-Server ELO** (separate ratings per server)

```sql
-- New schema with composite primary key
CREATE TABLE IF NOT EXISTS overall_standings (
    user_id INTEGER,
    guild_id INTEGER,                    -- NEW: Discord server ID
    user_display_name TEXT,
    elo INTEGER DEFAULT 1500,
    PRIMARY KEY (user_id, guild_id)
);
```

**Recommendation:** Start with Option A (Global ELO) for simplicity, add Option B later as a server configuration option.

### 1.4 New Table: guild_config

Store per-server configuration.

```sql
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id INTEGER PRIMARY KEY,
    guild_name TEXT,
    lfg_channel_id INTEGER,              -- Channel for LFG queue messages
    leaderboard_channel_id INTEGER,      -- Channel for leaderboard updates
    leaderboard_message_id INTEGER,      -- Message ID of pinned leaderboard
    match_report_channel_id INTEGER,     -- Channel for match result announcements
    admin_role_id INTEGER,               -- Role that can use admin commands
    elo_mode TEXT DEFAULT 'global',      -- 'global' or 'server'
    queue_min_time INTEGER DEFAULT 5,    -- Minimum queue time in minutes
    queue_max_time INTEGER DEFAULT 120,  -- Maximum queue time in minutes
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 1.5 New Table: guild_roles

Store special role IDs per server (e.g., Masters bracket roles).

```sql
CREATE TABLE IF NOT EXISTS guild_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    role_type TEXT,                      -- 'masters', 'verified', 'lfg_ping', etc.
    role_id INTEGER,
    UNIQUE(guild_id, role_type, role_id)
);
```

---

## Phase 2: Configuration System

### 2.1 Remove Hardcoded Values

Current hardcoded values in `lfg.py` and `config.py` that need to be moved to database:

| Current Location | Value                    | New Location                          |
| ---------------- | ------------------------ | ------------------------------------- |
| `lfg.py`         | `LFG_CHANNEL_ID`         | `guild_config.lfg_channel_id`         |
| `lfg.py`         | `LEADERBOARD_CHANNEL_ID` | `guild_config.leaderboard_channel_id` |
| `lfg.py`         | `masters_role_ids`       | `guild_roles` table                   |
| `config.py`      | Various channel IDs      | `guild_config` table                  |

### 2.2 New Config Helper Functions

Create `utils/guild_config.py`:

```python
import sqlite3
from typing import Optional, Dict, Any

def get_guild_config(guild_id: int) -> Optional[Dict[str, Any]]:
    """Get configuration for a specific guild."""
    conn = sqlite3.connect("guild_config.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "guild_id": row[0],
        "guild_name": row[1],
        "lfg_channel_id": row[2],
        "leaderboard_channel_id": row[3],
        "leaderboard_message_id": row[4],
        "match_report_channel_id": row[5],
        "admin_role_id": row[6],
        "elo_mode": row[7],
        "queue_min_time": row[8],
        "queue_max_time": row[9],
    }

def set_guild_config(guild_id: int, **kwargs) -> bool:
    """Update configuration for a specific guild."""
    # Implementation here
    pass

def get_guild_roles(guild_id: int, role_type: str) -> list[int]:
    """Get role IDs of a specific type for a guild."""
    # Implementation here
    pass
```

---

## Phase 3: Command Updates

### 3.1 Server Setup Command

New admin command for initial server setup:

```
!lfg_setup
```

This command will:

1. Check if the server is already configured
2. Create a new entry in `guild_config`
3. Prompt admin to configure channels and roles
4. Set up the leaderboard message

### 3.2 Server Configuration Commands

```
!lfg_config lfg_channel #channel        - Set LFG channel
!lfg_config leaderboard_channel #channel - Set leaderboard channel
!lfg_config report_channel #channel      - Set match report channel
!lfg_config admin_role @role             - Set admin role
!lfg_config elo_mode [global|server]     - Set ELO mode
!lfg_config add_masters_role @role       - Add a masters bracket role
!lfg_config remove_masters_role @role    - Remove a masters bracket role
!lfg_config show                         - Show current configuration
```

### 3.3 Update Existing Commands

Commands that need guild_id awareness:

| Command            | Change Required                                  |
| ------------------ | ------------------------------------------------ |
| `!lfg`             | Get LFG channel from guild_config                |
| `!leaderboard`     | Filter by guild or show global based on elo_mode |
| `!masters_bracket` | Get masters roles from guild_roles table         |
| `!rank`            | Show server or global rank based on elo_mode     |
| `!mystats`         | Filter matches by guild or show all              |
| `!game_activity`   | Add option to filter by server                   |
| `!reset_elo`       | Only reset for current server                    |
| `!remove_player`   | Only affect current server's matches             |

### 3.4 Cross-Server Features (Future)

- Global leaderboard showing all servers
- Cross-server matchmaking (opt-in)
- Player profiles showing stats across servers

---

## Phase 4: Code Changes Summary

### 4.1 Files to Modify

| File                    | Changes                                          |
| ----------------------- | ------------------------------------------------ |
| `utils/database.py`     | Add guild_id to all insert/update functions      |
| `utils/guild_config.py` | NEW - Guild configuration helpers                |
| `cogs/lfg.py`           | Replace hardcoded IDs with guild_config lookups  |
| `cogs/elo.py`           | Add guild awareness to rank/leaderboard commands |
| `main.py`               | Initialize guild_config database on startup      |

### 4.2 Function Signature Changes

```python
# Before
async def winner_report(reporter_id, user_id, ...)

# After
async def winner_report(guild_id, reporter_id, user_id, ...)
```

```python
# Before
def update_elo_db(user_id, user_display_name, did_win, opponent_id)

# After (for server-specific ELO)
def update_elo_db(guild_id, user_id, user_display_name, did_win, opponent_id, elo_mode='global')
```

---

## Phase 5: Migration Strategy

### 5.1 Backward Compatibility

1. Add `guild_id` columns with NULL default
2. Existing records without guild_id are treated as "legacy" or assigned to primary server
3. New records always include guild_id

### 5.2 Migration Script

```python
def migrate_to_multi_server(primary_guild_id: int):
    """Migrate existing data to multi-server format."""

    # 1. Add guild_id columns
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    try:
        cur.execute("ALTER TABLE match_records ADD COLUMN guild_id INTEGER")
    except sqlite3.OperationalError:
        pass  # Column exists

    # 2. Set existing records to primary guild
    cur.execute(
        "UPDATE match_records SET guild_id = ? WHERE guild_id IS NULL",
        (primary_guild_id,)
    )

    conn.commit()
    conn.close()

    # 3. Create guild_config table and add primary server
    # ...
```

---

## Phase 6: Web App Updates

### 6.1 API Changes

Update web API endpoints to support server filtering:

```
/api/leaderboard                    - Global leaderboard
/api/leaderboard?guild_id=123       - Server-specific leaderboard
/api/player/<id>                    - Global player stats
/api/player/<id>?guild_id=123       - Server-specific player stats
/api/avatars?guild_id=123           - Server-specific avatar stats
```

### 6.2 UI Changes

- Add server selector dropdown
- Show server name on leaderboard
- Filter match history by server

---

## Implementation Priority

### MVP (Minimum Viable Product)

1. ✅ Add `guild_id` to match_records and solo_match_reports
2. ✅ Create guild_config table
3. ✅ Create `!lfg_setup` command
4. ✅ Create basic `!lfg_config` commands
5. ✅ Update LFG channel lookup to use guild_config
6. ✅ Update leaderboard to use guild_config

### Phase 2

7. Per-server ELO option
8. Masters roles per server
9. Web app server filtering
10. Cross-server statistics

### Phase 3

11. Bot dashboard for configuration
12. Server invite flow with auto-setup
13. Cross-server matchmaking

---

## Security Considerations

1. **Admin Permissions** - Only server admins can configure the bot
2. **Data Isolation** - Servers cannot access each other's data
3. **Rate Limiting** - Prevent abuse of setup commands
4. **Validation** - Verify channel/role IDs belong to the guild

---

## Testing Checklist

- [ ] New server can set up bot from scratch
- [ ] Existing data migrates correctly
- [ ] Matches are recorded with correct guild_id
- [ ] Leaderboard shows correct server data
- [ ] Admin commands only affect current server
- [ ] Web app filters work correctly
- [ ] ELO calculations work in both modes

---

## Notes

- Keep the current Summit server as the "primary" server during development
- Test with a secondary test server before public release
- Consider a "verified server" system to prevent abuse
- Document setup process for new server admins
