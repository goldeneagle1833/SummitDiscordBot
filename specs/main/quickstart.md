# Quickstart: RealmsDraft ↔ Summit API Integration

## What This Feature Does

Adds REST API endpoints to the Summit web app that RealmsDraft calls to manage player arena runs:
- **GET status**: RealmsDraft checks if a player has an active run, match history, score, and can queue
- **POST run**: RealmsDraft starts a new arena run (with deck URL) or forfeits the current one
- **POST end-run**: RealmsDraft ends a run early, applying remaining losses as ELO penalties
- **Queue rules**: Discord bot validates players have an active run before joining the Limited queue

The Discord bot's limited arena system (database, ELO, match reporting) is already fully implemented. This feature adds the external API surface.

## Key Files

| File | Purpose |
|------|---------|
| `web-app/routes/api/limited.py` | Blueprint with 3 endpoints (GET status, POST run, POST end-run) |
| `web-app/utils/api_auth.py` | `@require_api_key` decorator for RealmsDraft authentication |
| `web-app/webapp_config.py` | `REALMSDRAFT_API_KEY` config value |
| `web-app/routes/api/__init__.py` | Registers `limited_bp` blueprint |
| `discord-bot/repositories/limited_repo.py` | Data access: arena runs, ELO, pairings, match history |
| `discord-bot/services/limited_service.py` | Business logic: start run, forfeit, ELO calc |

## How It Works

### RealmsDraft Integration Flow

```
1. Player drafts a deck on RealmsDraft
2. RealmsDraft calls POST /api/limited/user/<id>/run with deck_url
   → Summit creates arena run (0-0 record) in limited_arena_runs
3. Player joins Limited queue on Discord (/lfg → Limited)
   → Bot checks: active run exists + wins < 5 + losses < 3
4. Player plays match, reports result via Discord
   → Bot updates run record + Limited ELO (existing flow)
5. RealmsDraft calls GET /api/limited/user/<id>/status
   → Gets current run record, match history, ELO, can_queue flag
6. When player wants to forfeit/abandon:
   → RealmsDraft calls POST /run with forfeit: true
   → Or POST /end-run to apply remaining losses
```

### Authentication

All endpoints require `X-API-Key` header with the shared secret from `webapp_config.py`.

```python
# In webapp_config.py:
REALMSDRAFT_API_KEY = os.environ.get("REALMSDRAFT_API_KEY", "")
```

### Existing Code Reuse

The web app's `app.py` already adds `discord-bot/` to `sys.path`. The API blueprint imports directly:

```python
from repositories.limited_repo import (
    get_active_arena_run, get_latest_arena_run, get_limited_elo, get_matches_for_run
)
from services.limited_service import start_arena_run, forfeit_arena_run
```

---

## API Endpoints

### GET `/api/limited/user/<user_id>/status`

Returns the player's current/latest run, match history for that run, ELO, and queue eligibility.

**Request:**
```bash
curl -H "X-API-Key: your-key" http://localhost:5000/api/limited/user/123/status
```

**Response (active run, 2-1 record):**
```json
{
    "success": true,
    "user_id": "123",
    "has_active_run": true,
    "run": {
        "run_id": 42,
        "deck_url": "https://curiosa.io/decks/abc123",
        "wins": 2,
        "losses": 1,
        "status": "active",
        "starting_elo": 1520,
        "created_at": "2026-04-01T14:30:00"
    },
    "match_history": [
        {
            "match_id": 101,
            "won": true,
            "opponent_name": "PlayerTwo",
            "opponent_id": 123456789,
            "elo_change": 18,
            "timestamp": "2026-04-01T15:00:00"
        },
        {
            "match_id": 102,
            "won": true,
            "opponent_name": "PlayerThree",
            "opponent_id": 987654321,
            "elo_change": 16,
            "timestamp": "2026-04-01T16:30:00"
        },
        {
            "match_id": 103,
            "won": false,
            "opponent_name": "PlayerFour",
            "opponent_id": 111222333,
            "elo_change": -14,
            "timestamp": "2026-04-01T17:15:00"
        }
    ],
    "limited_elo": 1535,
    "can_queue": true
}
```

**Response (no active run, never played):**
```json
{
    "success": true,
    "user_id": "123",
    "has_active_run": false,
    "run": null,
    "match_history": [],
    "limited_elo": 1500,
    "can_queue": false
}
```

**Response (completed run, needs new run to queue):**
```json
{
    "success": true,
    "user_id": "123",
    "has_active_run": false,
    "run": {
        "run_id": 42,
        "deck_url": "https://curiosa.io/decks/abc123",
        "wins": 5,
        "losses": 2,
        "status": "completed",
        "starting_elo": 1520,
        "created_at": "2026-04-01T14:30:00",
        "completed_at": "2026-04-01T18:45:00"
    },
    "match_history": [
        {"match_id": 101, "won": true, "opponent_name": "PlayerTwo", "opponent_id": 123456789, "elo_change": 18, "timestamp": "2026-04-01T15:00:00"},
        {"match_id": 102, "won": true, "opponent_name": "PlayerThree", "opponent_id": 987654321, "elo_change": 16, "timestamp": "2026-04-01T16:30:00"},
        {"match_id": 103, "won": false, "opponent_name": "PlayerFour", "opponent_id": 111222333, "elo_change": -14, "timestamp": "2026-04-01T17:00:00"},
        {"match_id": 104, "won": true, "opponent_name": "PlayerFive", "opponent_id": 444555666, "elo_change": 15, "timestamp": "2026-04-01T17:30:00"},
        {"match_id": 105, "won": true, "opponent_name": "PlayerSix", "opponent_id": 777888999, "elo_change": 17, "timestamp": "2026-04-01T18:00:00"},
        {"match_id": 106, "won": false, "opponent_name": "PlayerSeven", "opponent_id": 222333444, "elo_change": -15, "timestamp": "2026-04-01T18:30:00"},
        {"match_id": 107, "won": true, "opponent_name": "PlayerEight", "opponent_id": 555666777, "elo_change": 16, "timestamp": "2026-04-01T18:45:00"}
    ],
    "limited_elo": 1580,
    "can_queue": false
}
```

---

### POST `/api/limited/user/<user_id>/run`

Start a new arena run or forfeit the current one.

**Request (start new run):**
```bash
curl -X POST -H "X-API-Key: your-key" -H "Content-Type: application/json" \
  -d '{"deck_url": "https://curiosa.io/decks/abc", "display_name": "PlayerOne"}' \
  http://localhost:5000/api/limited/user/123/run
```

**Response (201 Created):**
```json
{
    "success": true,
    "action": "created",
    "run": {
        "run_id": 43,
        "deck_url": "https://curiosa.io/decks/abc",
        "wins": 0,
        "losses": 0,
        "status": "active",
        "starting_elo": 1535,
        "created_at": "2026-04-02T10:00:00"
    },
    "limited_elo": 1535
}
```

**Request (forfeit current run):**
```bash
curl -X POST -H "X-API-Key: your-key" -H "Content-Type: application/json" \
  -d '{"forfeit": true}' \
  http://localhost:5000/api/limited/user/123/run
```

**Response (200 OK):**
```json
{
    "success": true,
    "action": "forfeited",
    "run": {
        "run_id": 42,
        "deck_url": "https://curiosa.io/decks/old-deck",
        "wins": 2,
        "losses": 1,
        "status": "forfeited",
        "starting_elo": 1520,
        "created_at": "2026-04-01T14:30:00",
        "completed_at": "2026-04-02T10:00:00"
    },
    "limited_elo": 1490,
    "penalty_summary": "Applied 2 phantom losses. ELO: 1535 → 1490"
}
```

**Error (already has active run):**
```json
{"success": false, "error": "Player already has an active run (run_id: 42). Forfeit or complete it first."}
```

**Error (missing fields):**
```json
{"success": false, "error": "deck_url and display_name are required to start a new run"}
```

---

### POST `/api/limited/user/<user_id>/end-run`

End the current active run early, applying remaining losses as ELO penalties.

**Request:**
```bash
curl -X POST -H "X-API-Key: your-key" \
  http://localhost:5000/api/limited/user/123/end-run
```

**Response (200 OK, player was 2-1 so 2 losses applied):**
```json
{
    "success": true,
    "run": {
        "run_id": 42,
        "deck_url": "https://curiosa.io/decks/abc123",
        "wins": 2,
        "losses": 1,
        "status": "forfeited",
        "starting_elo": 1520,
        "created_at": "2026-04-01T14:30:00",
        "completed_at": "2026-04-02T10:00:00"
    },
    "limited_elo": 1490,
    "losses_applied": 2,
    "penalty_summary": "Applied 2 phantom losses. ELO: 1535 → 1490"
}
```

**Error (no active run):**
```json
{"success": false, "error": "No active run to end"}
```

---

## Error Responses

All errors follow this format:
```json
{"success": false, "error": "<message>"}
```

| Status | Meaning |
|--------|---------|
| 400 | Bad request (invalid user_id, missing fields, no active run) |
| 401 | Missing or invalid `X-API-Key` header |
| 500 | Database or server error |
