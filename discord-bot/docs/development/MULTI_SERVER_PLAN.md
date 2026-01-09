# Multi-Server Support Plan

This document outlines the changes required to make the Summit Discord Bot available to multiple servers, allowing each server to host their own LFG channel and maintain server-specific or cross-server leaderboards.

## Overview

Currently, the bot is designed for a single server with hardcoded channel IDs and role IDs. To support multiple servers and data sources, we need to:

1. **Database Changes** - Add guild/server identifiers and source tracking to all records
2. **Multi-Platform Support** - Enable data input from Discord, web forms, mobile apps, APIs, and other sources
3. **Configuration System** - Per-server configuration storage
4. **Command Updates** - Server-aware commands and leaderboards
5. **Admin Tools** - Server setup and configuration commands

**Important:** LFG matchmaking is **server-isolated**. Players can only be matched with others in the same Discord server. There is no cross-server matchmaking functionality.

---

## Phase 1: Database Schema Updates

### 1.1 match_records Table

Add `guild_id` to track which server/community the match was reported from, and `source` to track the input platform.

**Supported Sources:**

- `discord` - Discord bot commands
- `web` - Web application form submissions
- `mobile` - Mobile app submissions
- `api` - Direct API calls
- `manual` - Manual admin entries
- `import` - Bulk data imports

```sql
-- Migration
ALTER TABLE match_records ADD COLUMN guild_id INTEGER;
ALTER TABLE match_records ADD COLUMN source TEXT DEFAULT 'discord';

-- New schema
CREATE TABLE IF NOT EXISTS match_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,                    -- Discord server ID (or community ID for other platforms)
    source TEXT DEFAULT 'discord',       -- NEW: Data source ('discord', 'web', 'mobile', 'api', 'manual')
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
CREATE INDEX idx_match_records_source ON match_records(source);
```

### 1.2 solo_match_reports Table

```sql
-- Migration
ALTER TABLE solo_match_reports ADD COLUMN guild_id INTEGER;
ALTER TABLE solo_match_reports ADD COLUMN source TEXT DEFAULT 'discord';

-- New schema includes guild_id and source
CREATE TABLE IF NOT EXISTS solo_match_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,                    -- Discord server ID (or community ID for other platforms)
    source TEXT DEFAULT 'discord',       -- NEW: Data source ('discord', 'web', 'mobile', 'api', 'manual')
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

**Single Table with Guild ID** - One unified table supporting both global and per-server ELO modes:

```sql
-- New schema with composite primary key
CREATE TABLE IF NOT EXISTS overall_standings (
    user_id INTEGER,
    guild_id INTEGER NOT NULL,           -- Discord server ID (always required)
    user_display_name TEXT,
    elo INTEGER DEFAULT 1500,
    PRIMARY KEY (user_id, guild_id)
);

-- Index for faster server-specific queries
CREATE INDEX idx_standings_guild ON overall_standings(guild_id);
CREATE INDEX idx_standings_user ON overall_standings(user_id);
```

**How it works:**

- **All records store `guild_id`** - Every ELO record is associated with the server where it was earned
- **Leaderboards are server-scoped** - Only show players who have played matches in the current server
- **Per-Server ELO mode:** Each player has a separate ELO rating per server (stored with `guild_id`)
- **Global ELO mode:** (Future/Optional) Aggregate ELO across all of a player's servers for display purposes
- The `guild_config.elo_mode` setting determines which calculation method is used
- **Important:** Regardless of ELO mode, leaderboards ONLY display players from the current server

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
    admin_role_id INTEGER,               -- Role that can use admin commands (optional)
    elo_mode TEXT DEFAULT 'server',      -- 'server' (separate per server) or 'global' (future: shared across servers)
    queue_min_time INTEGER DEFAULT 5,    -- Minimum queue time in minutes
    queue_max_time INTEGER DEFAULT 120,  -- Maximum queue time in minutes
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
2. Open an interactive modal with configuration fields
3. Create a new entry in `guild_config` with provided settings
4. Set up the leaderboard message

**Setup Modal Fields:**

- **LFG Channel** - Channel for LFG queue messages
- **Leaderboard Channel** - Channel for leaderboard updates
- **Match Report Channel** - Channel for match result announcements
- **Admin Role** (optional) - Role that can use admin commands
- **ELO Mode** - Dropdown: Global or Server-specific
- **Min Queue Time** - Minimum minutes (default: 5)
- **Max Queue Time** - Maximum minutes (default: 120)

### 3.2 Server Configuration Commands

```
!lfg_config        - Opens modal to edit all configuration settings
!lfg_config show   - Display current server configuration
```

The `!lfg_config` modal allows admins to update any configuration value without needing separate commands for each setting. All fields are pre-filled with current values for easy editing.

### 3.3 Update Existing Commands

Commands that need guild_id awareness:

| Command          | Change Required                                                    |
| ---------------- | ------------------------------------------------------------------ |
| `!lfg`           | Get LFG channel from guild_config, match only in server            |
| `!leaderboard`   | Show only players who have played in current server                |
| `!rank`          | Show rank among players in current server only                     |
| `!mystats`       | Show stats for matches played in current server                    |
| `!game_activity` | Show activity for current server only                              |
| `!reset_elo`     | Only reset ELO for players in current server (admin only)          |
| `!remove_player` | Only affect matches/data from current server (admin only)          |
| `!admin_report`  | Can only report matches for players in current server (admin only) |

**Admin Command Scoping:** All admin commands (`!reset_elo`, `!remove_player`, `!admin_report`, `!spot_elo_reset`) automatically filter to only affect data from the server where the command is executed. Admins cannot modify data from other servers.

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
2. Existing records without guild_id are assigned to Sorcerers Summit server (guild_id: `1319120227643949211`)
3. New records always include guild_id

### 5.2 Migration Script

```python
def migrate_to_multi_server(primary_guild_id: int = 1319120227643949211):
    """Migrate existing data to multi-server format.

    Args:
        primary_guild_id: Sorcerers Summit server ID (default: 1319120227643949211)
    """

    # 1. Add guild_id columns
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    try:
        cur.execute("ALTER TABLE match_records ADD COLUMN guild_id INTEGER")
    except sqlite3.OperationalError:
        pass  # Column exists

    # 2. Set existing records to Sorcerers Summit server
    cur.execute(
        "UPDATE match_records SET guild_id = ? WHERE guild_id IS NULL",
        (primary_guild_id,)
    )

    conn.commit()
    conn.close()

    # 3. Create guild_config table and add Sorcerers Summit as primary server
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
8. Web app server filtering
9. Cross-server statistics dashboard

### Phase 3

10. Bot dashboard for configuration
11. Server invite flow with auto-setup
12. Advanced analytics and reporting

---

## Security Considerations

1. **Admin Permissions** - Only server admins can configure the bot and use admin commands
2. **Server-Scoped Admin Commands** - Admin commands only affect data from their own server (matches, ELO, player data)
3. **Data Isolation** - Servers cannot access or modify each other's data (includes LFG queues, match reports, ELO)
4. **Server-Isolated Matching** - LFG queues are per-server only, no cross-server matching
5. **Rate Limiting** - Prevent abuse of setup commands
6. **Validation** - Verify channel/role IDs belong to the guild and users exist in the server

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

- Sorcerers Summit server (guild_id: `1319120227643949211`) is the primary server for existing data
- Test with a secondary test server before public release
- Consider a "verified server" system to prevent abuse
- Document setup process for new server admins
