# Summit API Documentation

External API for third-party applications to report match results and manage limited arena runs.

## Base URL

```
https://sorcererssummit.com
```

## Authentication

All endpoints require an API key via the `X-API-Key` header:

```
X-API-Key: your_api_key_here
```

Contact the server administrator to obtain an API key.

Unauthorized requests return:

```json
{ "success": false, "error": "Invalid API key" }
```

---

## Health Check

**`GET /api/status`** (no auth required)

```json
{ "status": "online", "message": "Summit Web App is running!" }
```

---

## Ranked Match Reporting

### Report External Match

**`POST /api/report-external-match`**

Record a ranked match result. Updates unified ELO ratings and stores deck data.

#### Required Fields

| Field            | Type   | Description                              |
| ---------------- | ------ | ---------------------------------------- |
| `winner_id`      | string | Discord user ID of the winner            |
| `loser_id`       | string | Discord user ID of the loser             |
| `winner_deck_url`| string | Winner's deck URL (Curiosa.io)           |
| `loser_deck_url` | string | Loser's deck URL (Curiosa.io)            |
| `source`         | string | Identifier for the reporting application |

#### Optional Fields

| Field              | Type    | Description                                           |
| ------------------ | ------- | ----------------------------------------------------- |
| `winner_name`      | string  | Display name of the winner                            |
| `loser_name`       | string  | Display name of the loser                             |
| `winner_went_first`| boolean | `true` if winner went first, `false` if loser did     |
| `match_time`       | integer | Match duration in seconds                             |
| `match_comment`    | string  | Additional notes about the match                      |

#### Example Request

```bash
curl -X POST https://sorcererssummit.com/api/report-external-match \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key_here" \
  -d '{
    "winner_id": "123456789012345678",
    "loser_id": "987654321098765432",
    "winner_deck_url": "https://curiosa.io/decks/abc123",
    "loser_deck_url": "https://curiosa.io/decks/xyz789",
    "source": "draft-sorcery",
    "winner_name": "Alice",
    "loser_name": "Bob",
    "winner_went_first": true,
    "match_time": 1800,
    "match_comment": "Great game"
  }'
```

#### Success Response (200)

```json
{
  "success": true,
  "message": "External match recorded successfully",
  "report_id": 42,
  "winner_id": "123456789012345678",
  "loser_id": "987654321098765432",
  "winner_elo": 1516,
  "loser_elo": 1484,
  "winner_elo_change": 16,
  "loser_elo_change": -16,
  "source": "draft-sorcery",
  "timestamp": "2026-06-07T14:30:00.000000"
}
```

#### Error Responses

| Status | Condition                  | Example Body                                                        |
| ------ | -------------------------- | ------------------------------------------------------------------- |
| 400    | Missing required fields    | `{"success": false, "error": "Missing required fields: source"}`    |
| 400    | Same winner and loser      | `{"success": false, "error": "winner_id and loser_id must be different"}` |
| 400    | Empty source               | `{"success": false, "error": "source cannot be empty"}`             |
| 400    | Invalid data               | `{"success": false, "error": "Invalid data: ..."}`                  |
| 401    | Bad or missing API key     | `{"success": false, "error": "Invalid API key"}`                    |
| 500    | Server error               | `{"success": false, "error": "Internal server error"}`              |

---

### Get Matches by Date Range

**`GET /api/matches/date-range`**

Retrieve ranked match results between two dates (inclusive).

#### Query Parameters

| Parameter    | Required | Format       | Description                     |
| ------------ | -------- | ------------ | ------------------------------- |
| `start_date` | Yes      | `YYYY-MM-DD` | Start of date range (inclusive) |
| `end_date`   | Yes      | `YYYY-MM-DD` | End of date range (inclusive)   |

#### Example Request

```bash
curl -H "X-API-Key: your_api_key_here" \
  "https://sorcererssummit.com/api/matches/date-range?start_date=2026-06-01&end_date=2026-06-07"
```

#### Success Response (200)

```json
{
  "start_date": "2026-06-01",
  "end_date": "2026-06-07",
  "total_matches": 2,
  "matches": [
    {
      "match_id": 1542,
      "winner": "Alice",
      "winner_id": "123456789012345678",
      "winner_elo_change": 16,
      "loser": "Bob",
      "loser_id": "987654321098765432",
      "loser_elo_change": -16,
      "match_time": 1823,
      "timestamp": "2026-06-05 19:32:05",
      "winner_deck": {
        "avatar": "Fen Cleric",
        "spellbook": ["Card A", "Card B"],
        "atlas": ["Land A", "Land B"]
      },
      "loser_deck": {
        "avatar": "Storm Mage",
        "spellbook": ["Card C", "Card D"],
        "atlas": ["Land C", "Land D"]
      }
    }
  ]
}
```

#### Error Responses

| Status | Condition                         | Body                                                              |
| ------ | --------------------------------- | ----------------------------------------------------------------- |
| 400    | Missing params                    | `{"error": "start_date and end_date query params are required"}`  |
| 400    | Invalid format                    | `{"error": "Dates must be in YYYY-MM-DD format"}`                 |
| 400    | start_date after end_date         | `{"error": "start_date must be before or equal to end_date"}`     |
| 401    | Bad or missing API key            | `{"success": false, "error": "Invalid API key"}`                  |

---

## Limited Arena API

Endpoints for managing limited (draft/sealed) arena runs. All prefixed with `/api/limited`.

### Get User Status

**`GET /api/limited/user/{user_id}/status`**

Get a player's current limited arena status, active run, match history, and ELO.

#### Example Request

```bash
curl -H "X-API-Key: your_api_key_here" \
  "https://sorcererssummit.com/api/limited/user/123456789012345678/status"
```

#### Success Response (200)

```json
{
  "success": true,
  "user_id": "123456789012345678",
  "has_active_run": true,
  "run": {
    "run_id": 5,
    "deck_url": "https://curiosa.io/decks/abc123",
    "wins": 3,
    "losses": 1,
    "status": "active",
    "starting_elo": 1500,
    "created_at": "2026-06-05T10:00:00"
  },
  "match_history": [],
  "limited_elo": 1532,
  "can_queue": true,
  "is_archived": false
}
```

| Field            | Type    | Description                                            |
| ---------------- | ------- | ------------------------------------------------------ |
| `has_active_run`  | boolean | Whether the player has an in-progress run              |
| `run`             | object  | Current or most recent run (null if none)              |
| `match_history`   | array   | Matches for the current/latest run                     |
| `limited_elo`     | integer | Player's limited format ELO rating                     |
| `can_queue`       | boolean | Whether the player can queue for another match         |
| `is_archived`     | boolean | Whether the data is from a previous event's archive    |

---

### Start Arena Run / Forfeit Run

**`POST /api/limited/user/{user_id}/run`**

Start a new arena run or forfeit the current one.

#### Start New Run

```json
{
  "deck_url": "https://curiosa.io/decks/abc123",
  "display_name": "Alice"
}
```

**Success Response (201):**

```json
{
  "success": true,
  "action": "created",
  "run": {
    "run_id": 6,
    "deck_url": "https://curiosa.io/decks/abc123",
    "wins": 0,
    "losses": 0,
    "status": "active",
    "starting_elo": 1500,
    "created_at": "2026-06-07T10:00:00"
  },
  "limited_elo": 1500
}
```

#### Forfeit Current Run

```json
{
  "forfeit": true
}
```

**Success Response (200):**

```json
{
  "success": true,
  "action": "forfeited",
  "run": { "..." },
  "limited_elo": 1480,
  "penalty_summary": "..."
}
```

#### Errors

| Status | Condition                          | Body                                                                         |
| ------ | ---------------------------------- | ---------------------------------------------------------------------------- |
| 400    | Missing deck_url or display_name   | `{"success": false, "error": "deck_url and display_name are required..."}`   |
| 400    | Business logic error               | `{"success": false, "error": "..."}`                                         |
| 400    | Invalid user_id                    | `{"success": false, "error": "Invalid user_id"}`                             |

---

### Report Limited Match

**`POST /api/limited/report-match`**

Submit a limited format match result. Both players must have active arena runs.

#### Required Fields

| Field                  | Type    | Description                     |
| ---------------------- | ------- | ------------------------------- |
| `winner_id`            | integer | Discord user ID of the winner   |
| `loser_id`             | integer | Discord user ID of the loser    |
| `winner_display_name`  | string  | Display name of the winner      |
| `loser_display_name`   | string  | Display name of the loser       |

#### Optional Fields

| Field           | Type    | Description                                       |
| --------------- | ------- | ------------------------------------------------- |
| `first_player`  | string  | Who went first (implementation-dependent)         |
| `match_time`    | integer | Match duration                                    |
| `match_comment` | string  | Additional notes                                  |

#### Example Request

```bash
curl -X POST https://sorcererssummit.com/api/limited/report-match \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key_here" \
  -d '{
    "winner_id": 123456789012345678,
    "loser_id": 987654321098765432,
    "winner_display_name": "Alice",
    "loser_display_name": "Bob"
  }'
```

#### Success Response (201)

```json
{
  "success": true,
  "match_id": 15,
  "..."
}
```

#### Errors

| Status | Condition                           | Body                                                                              |
| ------ | ----------------------------------- | --------------------------------------------------------------------------------- |
| 400    | Missing required fields             | `{"success": false, "error": "winner_id, loser_id, winner_display_name, and loser_display_name are required"}` |
| 400    | Invalid IDs                         | `{"success": false, "error": "winner_id and loser_id must be valid integers"}`    |
| 400    | Same player                         | `{"success": false, "error": "winner_id and loser_id must be different"}`         |
| 400    | No active run / business error      | `{"success": false, "error": "..."}`                                              |

---

### End Arena Run

**`POST /api/limited/user/{user_id}/end-run`**

End the current active run early, applying remaining losses as ELO penalties.

#### Example Request

```bash
curl -X POST https://sorcererssummit.com/api/limited/user/123456789012345678/end-run \
  -H "X-API-Key: your_api_key_here"
```

#### Success Response (200)

```json
{
  "success": true,
  "run": { "..." },
  "limited_elo": 1465,
  "losses_applied": 2,
  "penalty_summary": "..."
}
```

---

### Get Limited Match History

**`GET /api/limited/match-history`**

Get limited match history with deck links. Supports three query modes:

| Query Param | Description                                    |
| ----------- | ---------------------------------------------- |
| (none)      | All match records globally                     |
| `user_id`   | All runs and per-run history for a user        |
| `run_id`    | Match history for a specific run               |

Cannot provide both `user_id` and `run_id`.

#### Example: By User

```bash
curl -H "X-API-Key: your_api_key_here" \
  "https://sorcererssummit.com/api/limited/match-history?user_id=123456789012345678"
```

```json
{
  "success": true,
  "user_id": "123456789012345678",
  "runs": [
    {
      "run_id": 5,
      "deck_url": "https://curiosa.io/decks/abc123",
      "wins": 7,
      "losses": 3,
      "status": "completed",
      "starting_elo": 1500,
      "created_at": "2026-06-01T10:00:00",
      "completed_at": "2026-06-03T15:30:00",
      "matches": []
    }
  ]
}
```

### Get Run Matchups (Public)

**`GET /api/limited/run/{run_id}/matchups`** (no auth required)

Get detailed matchups for a specific arena run. Opponent deck URLs are hidden while the opponent's run is still active.

```json
{
  "run_id": 5,
  "user_id": 123456789012345678,
  "user_display_name": "Alice",
  "deck_url": "https://curiosa.io/decks/abc123",
  "wins": 7,
  "losses": 3,
  "status": "completed",
  "matchups": []
}
```

---

## ELO System

Both ranked and limited formats use standard ELO:

- **Starting ELO:** 1500
- **K-factor:** 32
- **Formula:** `new_elo = old_elo + K * (actual - expected)`
  - `expected = 1 / (1 + 10^((opponent_elo - player_elo) / 400))`
  - `actual = 1` for win, `0` for loss

New players start at 1500 and are created automatically on first match.

---

## Code Examples

### Python

```python
import requests

API_KEY = "your_api_key_here"
BASE = "https://sorcererssummit.com"
HEADERS = {"Content-Type": "application/json", "X-API-Key": API_KEY}

# Report a ranked match
response = requests.post(f"{BASE}/api/report-external-match", headers=HEADERS, json={
    "winner_id": "123456789012345678",
    "loser_id": "987654321098765432",
    "winner_deck_url": "https://curiosa.io/decks/abc123",
    "loser_deck_url": "https://curiosa.io/decks/xyz789",
    "source": "my-app",
    "winner_name": "Alice",
    "loser_name": "Bob",
    "winner_went_first": True,
    "match_time": 1800,
})

result = response.json()
if result["success"]:
    print(f"Match #{result['report_id']} recorded")
    print(f"Winner ELO: {result['winner_elo']} ({result['winner_elo_change']:+d})")
    print(f"Loser ELO: {result['loser_elo']} ({result['loser_elo_change']:+d})")
```

### JavaScript

```javascript
const API_KEY = "your_api_key_here";
const BASE = "https://sorcererssummit.com";

const res = await fetch(`${BASE}/api/report-external-match`, {
  method: "POST",
  headers: { "Content-Type": "application/json", "X-API-Key": API_KEY },
  body: JSON.stringify({
    winner_id: "123456789012345678",
    loser_id: "987654321098765432",
    winner_deck_url: "https://curiosa.io/decks/abc123",
    loser_deck_url: "https://curiosa.io/decks/xyz789",
    source: "my-app",
    winner_name: "Alice",
    loser_name: "Bob",
    winner_went_first: true,
    match_time: 1800,
  }),
});

const result = await res.json();
console.log(result);
```

---

## Best Practices

1. **Store the API key securely** -- never commit it to version control
2. **Always use HTTPS** in production
3. **Validate input** before submitting (correct Discord IDs, valid deck URLs)
4. **Handle errors** by checking `success` field and HTTP status codes
5. **Report matches promptly** for accurate ELO tracking
6. **Use the `source` field** consistently to identify your application
