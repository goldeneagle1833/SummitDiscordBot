# PSO Ranked Match Reporting API Reference

## `POST /api/report-external-match`

Reports a ranked match result from Play Sorcery Online. The match enters a **pending confirmation** state and auto-confirms after **24 hours** unless disputed by either player. Upon confirmation, ELO is updated for both players.

Both players receive a web notification when the match is reported.

### Authentication

Requires an API key passed via the `X-API-Key` header.

### Request

```
POST https://<host>/api/report-external-match
Content-Type: application/json
X-API-Key: <your-api-key>
```

### Request Body

```json
{
  "winner_id": "123456789012345678",
  "loser_id": "987654321098765432",
  "winner_deck_url": "https://curiosa.io/decks/abcd1234",
  "loser_deck_url": "https://curiosa.io/decks/efgh5678",
  "source": "PSO Ranked",
  "winner_name": "PlayerOne",
  "loser_name": "PlayerTwo",
  "winner_went_first": true,
  "match_time": 1725500000,
  "match_comment": "Great game, close finish"
}
```

### Field Descriptions

| Field               | Type    | Required | Description                                                                 |
|---------------------|---------|----------|-----------------------------------------------------------------------------|
| `winner_id`         | string  | Yes      | Discord user ID (or Google OAuth ID) of the winning player                  |
| `loser_id`          | string  | Yes      | Discord user ID (or Google OAuth ID) of the losing player                   |
| `winner_deck_url`   | string  | Yes      | Curiosa deck URL used by the winner                                         |
| `loser_deck_url`    | string  | Yes      | Curiosa deck URL used by the loser                                          |
| `source`            | string  | Yes      | Must be `"PSO Ranked"` for ranked match reporting                           |
| `winner_name`       | string  | No       | Display name of the winner (used for notifications)                         |
| `loser_name`        | string  | No       | Display name of the loser (used for notifications)                          |
| `winner_went_first` | boolean | No       | `true` if the winner went first, `false` otherwise                          |
| `match_time`        | integer | No       | Unix timestamp of when the match was played                                 |
| `match_comment`     | string  | No       | Free-text comment about the match                                           |

### Success Response

`200 OK`

```json
{
  "success": true,
  "confirmation_id": 42,
  "expires_at": 1725586400,
  "pipeline": "pso_ranked",
  "winner": {
    "id": "123456789012345678",
    "display_name": "PlayerOne"
  },
  "loser": {
    "id": "987654321098765432",
    "display_name": "PlayerTwo"
  }
}
```

| Field             | Type    | Description                                                        |
|-------------------|---------|--------------------------------------------------------------------|
| `success`         | boolean | `true` if the match was accepted                                   |
| `confirmation_id` | integer | Unique ID for this pending confirmation                            |
| `expires_at`      | integer | Unix timestamp when the match will auto-confirm (24h from report)  |
| `pipeline`        | string  | Always `"pso_ranked"` for PSO ranked matches                       |
| `winner`          | object  | Winner player info (`id`, `display_name`)                          |
| `loser`           | object  | Loser player info (`id`, `display_name`)                           |

### Error Responses

#### `400 Bad Request` — Missing or invalid fields

```json
{
  "success": false,
  "error": "Missing required fields: winner_deck_url, loser_deck_url",
  "pipeline": "pso_ranked"
}
```

#### `400 Bad Request` — Same player as winner and loser

```json
{
  "success": false,
  "error": "winner_id and loser_id must be different"
}
```

#### `409 Conflict` — Duplicate pending match

```json
{
  "success": false,
  "error": "A pending match already exists between these players",
  "pipeline": "pso_ranked"
}
```

#### `401 Unauthorized` — Missing or invalid API key

```json
{
  "error": "Unauthorized"
}
```

#### `500 Internal Server Error`

```json
{
  "success": false,
  "error": "Internal server error"
}
```

---

## Match Lifecycle

1. **Reported** — PSO sends the match result via this API. Both players receive a web notification. The **loser** also receives a **Discord DM** with the match details (including both deck URLs) and **Confirm / Dispute** buttons.
2. **Pending (24h)** — The match appears on both players' profile pages under "Pending Match Reports". Either player can dispute during this window — the loser can use the Discord buttons or the website, the winner can dispute from the website.
3. **Auto-confirmed** — After 24 hours with no dispute, the match is finalized: ELO is updated, the match is recorded, and deck data is stored. Both players are notified.
4. **Disputed** — If a player clicks Dispute (in Discord DM or on the website), the match is cancelled with no ELO change.

---

## Example: cURL

```bash
curl -X POST https://<host>/api/report-external-match \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key-here" \
  -d '{
    "winner_id": "123456789012345678",
    "loser_id": "987654321098765432",
    "winner_deck_url": "https://curiosa.io/decks/abcd1234",
    "loser_deck_url": "https://curiosa.io/decks/efgh5678",
    "source": "PSO Ranked",
    "winner_name": "PlayerOne",
    "loser_name": "PlayerTwo",
    "winner_went_first": true,
    "match_time": 1725500000
  }'
```

## Example: Python (requests)

```python
import requests

response = requests.post(
    "https://<host>/api/report-external-match",
    headers={
        "Content-Type": "application/json",
        "X-API-Key": "your-api-key-here",
    },
    json={
        "winner_id": "123456789012345678",
        "loser_id": "987654321098765432",
        "winner_deck_url": "https://curiosa.io/decks/abcd1234",
        "loser_deck_url": "https://curiosa.io/decks/efgh5678",
        "source": "PSO Ranked",
        "winner_name": "PlayerOne",
        "loser_name": "PlayerTwo",
        "winner_went_first": True,
        "match_time": 1725500000,
    },
)

data = response.json()
if data["success"]:
    print(f"Match pending: confirmation #{data['confirmation_id']}")
    print(f"Auto-confirms at: {data['expires_at']}")
else:
    print(f"Error: {data['error']}")
```

## Example: JavaScript (fetch)

```javascript
const response = await fetch("https://<host>/api/report-external-match", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-API-Key": "your-api-key-here",
  },
  body: JSON.stringify({
    winner_id: "123456789012345678",
    loser_id: "987654321098765432",
    winner_deck_url: "https://curiosa.io/decks/abcd1234",
    loser_deck_url: "https://curiosa.io/decks/efgh5678",
    source: "PSO Ranked",
    winner_name: "PlayerOne",
    loser_name: "PlayerTwo",
    winner_went_first: true,
    match_time: 1725500000,
  }),
});

const data = await response.json();
if (data.success) {
  console.log(`Match pending: confirmation #${data.confirmation_id}`);
  console.log(`Auto-confirms at: ${data.expires_at}`);
} else {
  console.error(`Error: ${data.error}`);
}
```

## Notes

- `source` **must** be exactly `"PSO Ranked"` (case-sensitive) to trigger the ranked pipeline. Other source values route to the external (stats-only, no ELO) pipeline.
- Player IDs should be Discord user IDs or Google OAuth IDs matching accounts registered on Summit.
- Both players must exist in the Summit system. If a player ID is not found, a new entry is created at the default 1500 ELO.
- Deck URLs should be valid Curiosa deck links. Deck metadata (atlas, cards) is fetched automatically on confirmation.
- The 24-hour auto-confirm timer starts from the moment the API call is made.
- Matches count toward the current active event/season ELO if one is running.
