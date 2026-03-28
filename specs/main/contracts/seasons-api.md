# API Contract: User Created Seasons

Base path: `/api/seasons`

All endpoints require authentication (`@require_auth` decorator, same as existing match reporting endpoints) unless noted otherwise. User ID is read from `session["user_id"]`.

---

## POST `/api/seasons`

Create a new season. Creator is automatically enrolled.

### Request

```json
{
    "title": "Portland Winter League",
    "description": "Weekly meetups at Guardian Games",
    "start_date": "2026-04-01",
    "end_date": "2026-06-30",
    "k_value": 32,
    "base_elo": 1500,
    "max_members": 20,
    "region": "Portland, OR"
}
```

| Field       | Type    | Required | Validation                              |
|------------|---------|----------|-----------------------------------------|
| title      | string  | Yes      | 1-100 chars, trimmed                    |
| description| string  | No       | Max 500 chars                           |
| start_date | string  | Yes      | YYYY-MM-DD, must be today or future     |
| end_date   | string  | Yes      | YYYY-MM-DD, must be >= start_date       |
| k_value    | integer | No       | 1-64, defaults to 32                    |
| base_elo   | integer | No       | 500-3000, defaults to 1500              |
| max_members| integer | No       | >= 2 if provided, NULL = unlimited      |
| region     | string  | No       | Max 100 chars                           |

### Response

**201 Created**
```json
{
    "success": true,
    "season_id": 1,
    "title": "Portland Winter League",
    "start_date": "2026-04-01",
    "end_date": "2026-06-30",
    "message": "Season created successfully. You have been automatically enrolled."
}
```

**400 Bad Request**
```json
{
    "success": false,
    "error": "End date must be on or after start date"
}
```

**409 Conflict** (already in a season)
```json
{
    "success": false,
    "error": "You are already in a season. Leave your current season before creating a new one."
}
```

---

## GET `/api/seasons/search`

Search for joinable seasons.

### Query Parameters

| Param | Type   | Required | Description                              |
|-------|--------|----------|------------------------------------------|
| q     | string | No       | Search term (matches against title). If empty, returns all non-ended seasons |

### Response

**200 OK**
```json
{
    "success": true,
    "seasons": [
        {
            "season_id": 1,
            "title": "Portland Winter League",
            "description": "Weekly meetups at Guardian Games",
            "start_date": "2026-04-01",
            "end_date": "2026-06-30",
            "creator_name": "PlayerOne",
            "member_count": 8,
            "max_members": 20,
            "region": "Portland, OR",
            "is_member": false,
            "status": "active"
        }
    ]
}
```

**Notes:**
- `status` derived: `"upcoming"` if start_date > today, `"active"` if between dates
- `is_member` indicates if the authenticated user is already a member
- Only returns seasons with `status = 'active'` and `end_date >= today` (excludes ended/deleted)
- Sorted by start_date ascending

---

## POST `/api/seasons/<season_id>/join`

Join an existing season. User must not already be in another season.

### Request

No body required. Season ID is in the URL path.

### Response

**200 OK**
```json
{
    "success": true,
    "season_id": 1,
    "title": "Portland Winter League",
    "message": "Successfully joined the season"
}
```

**409 Conflict** (already in a season)
```json
{
    "success": false,
    "error": "You are already in a season. Leave your current season first."
}
```

**404 Not Found**
```json
{
    "success": false,
    "error": "Season not found"
}
```

---

## POST `/api/seasons/<season_id>/leave`

Leave the current season. Cannot be used by the season creator (use delete/end instead).

### Request

No body required.

### Response

**200 OK**
```json
{
    "success": true,
    "message": "You have left the season"
}
```

**400 Bad Request** (creator cannot leave)
```json
{
    "success": false,
    "error": "Season creators cannot leave. Use End Season or Delete Season instead."
}
```

**404 Not Found** (not a member)
```json
{
    "success": false,
    "error": "You are not a member of this season"
}
```

---

## PUT `/api/seasons/<season_id>`

Modify season settings. Creator only.

### Request

```json
{
    "start_date": "2026-04-15",
    "end_date": "2026-07-15",
    "description": "Updated description",
    "k_value": 24,
    "max_members": 30,
    "region": "Portland, OR"
}
```

| Field       | Type    | Required | Validation                              |
|------------|---------|----------|-----------------------------------------|
| start_date | string  | No       | YYYY-MM-DD                              |
| end_date   | string  | No       | YYYY-MM-DD, must be >= start_date       |
| description| string  | No       | Max 500 chars                           |
| k_value    | integer | No       | 1-64                                    |
| max_members| integer | No       | >= current member count if provided     |
| region     | string  | No       | Max 100 chars                           |

At least one field required. Omitted fields remain unchanged. Title cannot be changed after creation.

### Response

**200 OK**
```json
{
    "success": true,
    "message": "Season updated"
}
```

**403 Forbidden** (not the creator)
```json
{
    "success": false,
    "error": "Only the season creator can modify this season"
}
```

---

## POST `/api/seasons/<season_id>/end`

End a season immediately (sets end_date to today, status to 'ended'). Creator only.

### Request

No body required.

### Response

**200 OK**
```json
{
    "success": true,
    "message": "Season has been ended"
}
```

**403 Forbidden**
```json
{
    "success": false,
    "error": "Only the season creator can end this season"
}
```

---

## DELETE `/api/seasons/<season_id>`

Delete a season (soft delete, sets status to 'deleted'). Creator only. Removes all member associations.

### Request

No body required.

### Response

**200 OK**
```json
{
    "success": true,
    "message": "Season has been deleted"
}
```

**403 Forbidden**
```json
{
    "success": false,
    "error": "Only the season creator can delete this season"
}
```

---

## POST `/api/seasons/<season_id>/kick`

Kick a member from the season. Creator only.

### Request

```json
{
    "user_id": "296846802924208130"
}
```

| Field   | Type   | Required | Validation                              |
|---------|--------|----------|-----------------------------------------|
| user_id | string | Yes      | Must be a current member (not the creator) |

### Response

**200 OK**
```json
{
    "success": true,
    "message": "Member has been removed from the season",
    "kicked_user_id": "296846802924208130"
}
```

**400 Bad Request** (trying to kick self)
```json
{
    "success": false,
    "error": "You cannot kick yourself from your own season"
}
```

**403 Forbidden**
```json
{
    "success": false,
    "error": "Only the season creator can kick members"
}
```

---

## GET `/api/seasons/<season_id>/members`

Get all members of a season with ELO and rank. Used by the Kick Member modal.

### Response

**200 OK**
```json
{
    "success": true,
    "season_id": 1,
    "title": "Portland Winter League",
    "members": [
        {
            "user_id": "296846802924208130",
            "display_name": "PlayerOne",
            "season_elo": 1548,
            "wins": 7,
            "losses": 3,
            "rank": 1,
            "is_creator": true
        },
        {
            "user_id": "google_113075264611538227218",
            "display_name": "PlayerTwo",
            "season_elo": 1520,
            "wins": 5,
            "losses": 4,
            "rank": 2,
            "is_creator": false
        }
    ]
}
```

**Notes:**
- Rank is calculated at query time using `RANK() OVER (ORDER BY season_elo DESC)`
- No authentication required (public data)

---

## GET `/api/player/<player_id>/seasons`

Get the season a player currently belongs to (if any). Called by the player profile page.

### Response

**200 OK** (in a season)
```json
{
    "success": true,
    "current_season": {
        "season_id": 1,
        "title": "Portland Winter League",
        "description": "Weekly meetups at Guardian Games",
        "start_date": "2026-04-01",
        "end_date": "2026-06-30",
        "season_elo": 1532,
        "wins": 5,
        "losses": 2,
        "rank": 3,
        "member_count": 12,
        "max_members": 20,
        "region": "Portland, OR",
        "k_value": 32,
        "is_creator": false,
        "status": "active"
    }
}
```

**200 OK** (not in a season)
```json
{
    "success": true,
    "current_season": null
}
```

**Notes:**
- Returns only the one active/upcoming season the player is in (since one-at-a-time)
- `rank` is the player's current placement among season members
- `is_creator` indicates if this player created the season (shows management controls)
- No authentication required (public data, same as player stats)

---

## Internal: Season ELO Update (not an HTTP endpoint)

Called internally by `match_confirmation.py` after a match is confirmed.

### Function Signature

```python
def update_season_elos(
    winner_id: str,
    loser_id: str,
    match_id: str,
    is_repeat_matchup: bool,
    match_data: dict  # Full match details from the confirmed match
) -> list[dict]:
    """
    match_data contains: reporter_id, winner_display_name, loser_display_name,
    did_win, winner_went_first, loser_went_first, match_time, match_comment,
    curiosa_url_winner, curiosa_url_loser, json_deck_data_winner,
    json_deck_data_loser, source, match_type

    Returns list of season ELO changes (0 or 1 entry since players share at most one season):
    [
        {
            "season_id": 1,
            "season_title": "Portland Winter League",
            "winner_change": 16,
            "loser_change": -16
        }
    ]
    Returns empty list if no shared active season or if repeat matchup.
    """
```
