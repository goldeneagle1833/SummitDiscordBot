# Dual ELO System Specification

## Overview
Separate ELO tracking for web-based (Paper) and Discord bot-based (Online) match reports.

## Database Schema

### overall_standings table
- `paper_elo` - Lifetime ELO from web-reported matches
- `paper_event_elo` - Current event ELO from web-reported matches
- `online_elo` - Lifetime ELO from bot-reported matches (formerly `elo`)
- `online_event_elo` - Current event ELO from bot-reported matches (formerly `event_elo`)

**Legacy columns** (`elo`, `event_elo`):
- Currently used by Discord bot
- Bot should migrate to using `online_elo` and `online_event_elo`
- Web app NO LONGER updates these (as of this change)

## Match Sources

### Web-Based Matches (`match_reports_web` table)
- **Source**: `"Web"`
- **Updates**: `paper_elo`, `paper_event_elo` ONLY
- **Service**: `services/paper_elo.py`
- **User IDs**: TEXT (supports `google_` prefix)

### Bot-Based Matches (`match_records` table)
- **Source**: `"Discord"` (or other bot sources)
- **Updates**: `online_elo`, `online_event_elo` (to be migrated from legacy columns)
- **Service**: Discord bot `services/elo_service.py`
- **User IDs**: INTEGER (Discord IDs only)

## Player Profile Toggle

### UI Component
Location: Next to player name in header

```
[Player Name]        [🌐 Web] [🤖 Bot]
ELO: 1650            (toggle switches between sources)
```

### Toggle States

#### Web (Paper) ELO Mode
- **Displays**: `paper_elo`, `paper_event_elo`
- **Rank**: Based on paper ELO standings
- **Match History**: Only matches from `match_reports_web` (source="Web")
- **Stats**: Win/loss calculated from web matches only

#### Bot (Online) ELO Mode
- **Displays**: `online_elo` (or legacy `elo`), `online_event_elo` (or legacy `event_elo`)
- **Rank**: Based on online ELO standings
- **Match History**: Only matches from `match_records` (source="Discord")
- **Stats**: Win/loss calculated from bot matches only

### Default Mode
- **Web users** (Google OAuth): Default to "Web" mode
- **Discord users**: Default to "Bot" mode
- **Preference** saved in localStorage

## API Changes

### GET /api/player/{player_id}

**New Query Parameter**: `source=web|bot` (default: auto-detect)

**Response Schema**:
```json
{
  "name": "Player Name",
  "user_id": "123456789",

  // ELO data (varies by source)
  "elo": 1650,           // paper_elo or online_elo
  "event_elo": 1620,     // paper_event_elo or online_event_elo
  "rank": 42,            // rank within source

  // Stats (filtered by source)
  "wins": 25,
  "losses": 15,
  "win_rate": 62.5,
  "matches": [...],      // Only from selected source

  // Source indicator
  "elo_source": "web",   // or "bot"

  // Available sources
  "has_web_matches": true,
  "has_bot_matches": true,
  "paper_elo": 1650,     // Always returned for toggle
  "online_elo": 1580,    // Always returned for toggle
}
```

## Frontend Implementation

### Toggle Component
- **Type**: Segmented control (iOS-style toggle)
- **Styling**: Matches existing design system
- **Behavior**: Immediate switch (no page reload)
- **State**: Stored in `localStorage` as `elo_source_preference`

### Data Flow
```
User clicks toggle
  ↓
Update localStorage
  ↓
Fetch new data: GET /api/player/{id}?source={web|bot}
  ↓
Re-render all stats, ELO, rank, match history
  ↓
Update chart with new data
```

## Migration Notes

### For Discord Bot
The bot currently uses `elo` and `event_elo` columns. It should be updated to use:
- `online_elo` instead of `elo`
- `online_event_elo` instead of `event_elo`

This can be done gradually:
1. Update bot to write to BOTH old and new columns
2. Verify data consistency
3. Switch bot to read from new columns
4. Eventually deprecate legacy columns

### For Existing Data
If `online_elo` is NULL or 1500, fall back to reading from legacy `elo` column for backwards compatibility.

## Example User Scenarios

### Scenario 1: Discord-only player
- Has matches in `match_records` only
- Toggle defaults to "Bot" mode
- "Web" mode shows "No web matches yet"

### Scenario 2: Web-only player (Google OAuth)
- Has matches in `match_reports_web` only
- Toggle defaults to "Web" mode
- "Bot" mode shows "No bot matches yet"

### Scenario 3: Hybrid player
- Has matches in both tables
- Can toggle between both views
- Each view shows independent ELO and stats

## Testing Checklist

- [ ] Web match reports update only `paper_elo`, `paper_event_elo`
- [ ] Bot match reports update only `online_elo`, `online_event_elo`
- [ ] Toggle switches data sources correctly
- [ ] Match history filters by source
- [ ] Stats calculate correctly per source
- [ ] Ranks calculate correctly per source
- [ ] localStorage persists preference
- [ ] Default mode selects correctly
- [ ] API returns correct data per source parameter
- [ ] Chart updates with correct data
