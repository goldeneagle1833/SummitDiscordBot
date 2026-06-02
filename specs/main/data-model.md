# Data Model: Top-8 Events Page Redesign

## Overview

No new database tables or schemas required. This feature modifies the **shape of existing API responses** and adds new fields derived from existing JSON files at read time.

## Existing Data (Unchanged)

### Event Folder Structure
```
web-app/top-8-decks-by-event/
├── _event_metadata.json      # Admin overrides (name, rating, description)
├── _event_order.json          # Admin custom sort order
├── latest_event.json          # Most recently added event
└── {EventFolderName}/
    ├── {name}top8.json        # Top 8 decks (array of deck objects)
    ├── {name}.json            # All participant decks (optional)
    └── *.csv                  # Card usage stats (auto-generated)
```

### Deck Object (from Curiosa API, stored in JSON)
```json
{
  "id": "string",
  "name": "1st place Ascanrask III Troll Magic",
  "username": "Dado",
  "avatar": [{
    "identifier": "necromancer",
    "name": "Necromancer"
  }],
  "spellbook": [],
  "format": "Constructed"
}
```

## Modified Data

### _event_metadata.json (Extended - Optional New Field)
```json
{
  "EventFolderName": {
    "name": "Display Name Override",
    "rating": 2,
    "description": "Optional event description",
    "event_date": "2026-04-04"
  }
}
```

New optional field:
- `event_date` (string, ISO date) — Admin override for events where date can't be parsed from folder name

### Event List Item (API Response Shape Change)

**GET /api/top-8-events** response — each event item gains new fields:

| Field | Type | Source | Nullable | New? |
|-------|------|--------|----------|------|
| `folder` | string | Directory name | No | Existing |
| `name` | string | Formatted name (date stripped) | No | Modified |
| `player_count` | int | JSON array length | No | Existing |
| `has_top8` | bool | top8 JSON file exists | No | Existing |
| `has_full` | bool | full JSON file exists | No | Existing |
| `rating` | int | Metadata or default | No | Existing |
| `event_date` | string | Parsed from folder or metadata | Yes | **New** |
| `event_date_display` | string | Formatted (e.g., "Apr 4, 2026") | Yes | **New** |
| `winner_username` | string | `data[0].username` from top8 JSON | Yes | **New** |
| `winner_avatar` | string | `data[0].avatar[0].name` | Yes | **New** |
| `winner_avatar_id` | string | `data[0].avatar[0].identifier` | Yes | **New** |

**Example response item (after)**:
```json
{
  "folder": "Ascanrask III 2026 4 4",
  "name": "Ascanrask III",
  "player_count": 24,
  "has_top8": true,
  "has_full": false,
  "rating": 1,
  "event_date": "2026-04-04",
  "event_date_display": "Apr 4, 2026",
  "winner_username": "Dado",
  "winner_avatar": "Necromancer",
  "winner_avatar_id": "necromancer"
}
```

## New Utility Functions (utils/formatting.py)

### `extract_date_from_name(folder_name: str) -> str | None`

Returns ISO date string or None. Matching patterns:

| Pattern | Example Input | Result |
|---------|--------------|--------|
| `... YYYY M D` | `Ascanrask III 2026 4 4` | `2026-04-04` |
| `... M_D_YYYY` | `Assorted Animals 5_19_2026` | `2026-05-19` |
| `... M D YYYY` | `Aus Store 3 28 2026` | `2026-03-28` |
| `... Month D-D YYYY` | `LinCon May 14-16 2026` | `2026-05-14` |
| Year only | `GenCon2024Stats` | None (fallback to year) |

### `strip_date_from_name(name: str) -> str`

Removes date components from display name to avoid duplication when date is shown separately.
- `"Ascanrask III 2026 4 4"` -> `"Ascanrask III"`
- `"Battle of Elverson Fields May 23rd 2026"` -> `"Battle of Elverson Fields"`

## Frontend State Changes

### Events.jsx State (Modified)
```js
// No new state variables needed
// Existing state is sufficient:
// - events[] now contains richer objects (new fields)
// - filtered[] derives from events with same logic
// - featured event = filtered[0] (most recent, rendered differently)
```

### Event Card Component (Visual)
```
Before:                          After:
┌──────────────────┐            ┌──────────────────────────┐
│ Event Name       │            │ Apr 4, 2026              │
│ ★ ★ ☆            │    ->      │ Ascanrask III             │
│ 24 decks         │            │ Winner: Dado (Necromancer)│
│ Top 8 Available  │            │ 24 decks                  │
└──────────────────┘            └──────────────────────────┘
```

### Featured Event (New Section)
```
┌─────────────────────────────────────────────────────────┐
│  LATEST EVENT                                           │
│                                                         │
│  Ascanrask III                         Apr 4, 2026      │
│  Winner: Dado playing Necromancer      24 decks         │
│                                                         │
│  [View Results ->]                                      │
└─────────────────────────────────────────────────────────┘
```
