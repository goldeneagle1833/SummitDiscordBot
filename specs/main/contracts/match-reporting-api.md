# API Contract Changes: Match Reporting + Seasons

**Note**: Documents changes to EXISTING endpoints. New endpoints are not needed — all season-related endpoints already exist.

## Modified Endpoints

### `POST /api/match-report/submit` — Add `season_id`

**File**: `web-app/routes/api/match_reporting.py`

**Current payload**:
```json
{
  "opponent_user_id": "123456",
  "result": "won" | "lost",
  "went_first": "submitter" | "opponent",
  "submitter_deck_url": "https://curiosa.io/decks/...",
  "final_life_submitter": 0,
  "final_life_opponent": 5,
  "match_type": "ranked" | "casual"
}
```

**Updated payload** (one new optional field):
```json
{
  "opponent_user_id": "123456",
  "result": "won" | "lost",
  "went_first": "submitter" | "opponent",
  "submitter_deck_url": "https://curiosa.io/decks/...",
  "final_life_submitter": 0,
  "final_life_opponent": 5,
  "match_type": "ranked" | "casual",
  "season_id": 42
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `season_id` | integer | No | null | Season to count this match toward. Must be an active season the submitter is a member of. |

**Validation** (service layer):
- If provided, verify season exists and `status = 'active'` and `end_date >= today`
- If provided, verify submitter is in `season_members` for that season
- If validation fails: 400 with `{"success": false, "error": "You are not a member of this season"}`

**Response**: Unchanged (201 with `confirmation_id`, `expires_at`, `opponent`, `message`).

---

### `POST /api/match-report/confirm/{confirmation_id}` — Season ELO via stored `season_id`

**File**: `web-app/routes/api/match_reporting.py`

**Current payload**:
```json
{
  "deck_url": "https://curiosa.io/decks/..."
}
```

**Updated payload**: No change. The `season_id` is already stored in `match_confirmations` from the submit step.

**Behavior change**: During confirmation processing in `match_confirmation.py`:
1. Read `season_id` from the `match_confirmations` record
2. If `season_id` is not null:
   - Verify both players are still members of that season
   - Verify season is still active and not ended
   - If valid: call `update_season_elos()` with the explicit `season_id`
   - If invalid (player left, season ended): skip season ELO silently (non-blocking)
3. If `season_id` is null: skip season ELO entirely (existing behavior for pre-update matches)

**Response**: Unchanged (200 with `match_id` and success message).

---

### `GET /api/player/{player_id}/seasons` — Return list instead of single

**File**: `web-app/routes/api/seasons.py`

**Current response**:
```json
{
  "current_season": {
    "season_id": 1,
    "title": "Portland League",
    "season_elo": 1523,
    "wins": 7,
    "losses": 3,
    "rank": 3,
    "member_count": 12,
    ...
  }
}
```

**Updated response**:
```json
{
  "seasons": [
    {
      "season_id": 1,
      "title": "Portland League",
      "season_elo": 1523,
      "wins": 7,
      "losses": 3,
      "rank": 3,
      "member_count": 12,
      "is_creator": false,
      "start_date": "2026-03-01",
      "end_date": "2026-06-01",
      "description": "Local Portland group",
      "region": "Portland, OR",
      "k_value": 32,
      "max_members": 20,
      "status": "active"
    },
    {
      "season_id": 5,
      "title": "Online Winter Cup",
      ...
    }
  ]
}
```

**Breaking change**: `current_season` (single object/null) becomes `seasons` (array, may be empty). Frontend must be updated to iterate over the list.

---

### `POST /api/seasons` — Remove one-season check

**File**: `web-app/routes/api/seasons.py`

**Current behavior**: Returns 409 if user is already in an active season.
**Updated behavior**: Always allows creation (no 409 for "already in a season"). Other validations unchanged.

---

### `POST /api/seasons/{id}/join` — Remove one-season check

**File**: `web-app/routes/api/seasons.py`

**Current behavior**: Returns 409 if user is already in an active season.
**Updated behavior**: Always allows joining (no 409 for "already in a season"). Still returns 409 if season is full (max_members reached) or user is already a member of THIS specific season.

---

## Unchanged Endpoints

All other endpoints are unaffected:
- `POST /api/record-game` — unchanged; still used by player profile Solo mode and API key users
- `GET /api/seasons/search` — unchanged
- `GET /api/seasons/browse` — unchanged
- `POST /api/seasons/{id}/leave` — unchanged
- `PUT /api/seasons/{id}` — unchanged
- `POST /api/seasons/{id}/end` — unchanged
- `DELETE /api/seasons/{id}` — unchanged
- `POST /api/seasons/{id}/kick` — unchanged
- `GET /api/seasons/{id}/members` — unchanged
- `POST /api/match-report/deny/{id}` — unchanged
- `GET /api/match-report/pending` — unchanged
- `GET /api/match-report/search-opponents` — unchanged (reused by player profile Ranked mode)
