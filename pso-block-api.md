# Summit Player Block and Report API (for Play Sorcery Online)

Players on sorcererssummit.com can block other players from their player profile
(Profile → Block List). A block is one-way: player A blocks player B. The Summit bot's
matchmaking keeps a pair apart if **either** player has blocked the other.

Endpoints 1 and 2 let Play Sorcery Online read those blocks so PSO can do the same.
They are **read only**: blocking and unblocking still happen on the Summit profile.
The private reason a player types when blocking is **never** returned.

Endpoint 3 is PSO's version of the **Report Player** button on the Discord pairing
message: a player reports their opponent, and the report goes to the same admin list as
reports from Discord, marked "via Sorcery Online".

Base URL: `https://sorcererssummit.com`

## Authentication

Send the partner API key in the `X-API-Key` header (the same key PSO already uses for
`/api/report-external-match` and `/api/leaderboard/ticket-holders`).
`Authorization: Bearer <key>` also works.

```
X-API-Key: <your-api-key>
```

A missing or wrong key returns `401`:

```json
{ "success": false, "error": "Invalid API key" }
```

## Player IDs

All IDs are **Discord user IDs** as strings, e.g. `"123456789012345678"`, the same
`discordUserId` Summit sends PSO when it opens a table.

Players who only ever signed in to Summit with Google are stored as `google_<id>`.
Passing either the bare ID or the `google_` form finds their blocks. IDs in responses are
returned exactly as stored, so you may occasionally see a `google_…` ID in a list.

---

## 1. Check a pair: `GET /api/blocks/check`

The call to make before seating two players together.

### Request

```
GET https://sorcererssummit.com/api/blocks/check?user_a=123456789012345678&user_b=876543210987654321
X-API-Key: <your-api-key>
```

| Parameter | Required | Description                     |
|-----------|----------|---------------------------------|
| `user_a`  | yes      | Discord user ID of one player   |
| `user_b`  | yes      | Discord user ID of the other    |

### Response `200 OK`

```json
{
  "success": true,
  "user_a": "123456789012345678",
  "user_b": "876543210987654321",
  "blocked": true,
  "a_blocked_b": false,
  "b_blocked_a": true
}
```

| Field         | Description                                                       |
|---------------|-------------------------------------------------------------------|
| `blocked`     | `true` if either player has blocked the other. Do not pair them.  |
| `a_blocked_b` | `user_a` has blocked `user_b`                                     |
| `b_blocked_a` | `user_b` has blocked `user_a`                                     |

Two players with no blocks return `"blocked": false` (not a 404).

---

## 2. A player's block list: `GET /api/blocks/<user_id>`

Everyone a player has blocked, and everyone who has blocked them. Useful for filtering a
whole queue at once or caching per player.

### Request

```
GET https://sorcererssummit.com/api/blocks/123456789012345678
X-API-Key: <your-api-key>
```

### Response `200 OK`

```json
{
  "success": true,
  "user_id": "123456789012345678",
  "blocked": [
    {
      "user_id": "876543210987654321",
      "display_name": "SomePlayer",
      "created_at": "2026-10-02 18:41:07"
    }
  ],
  "blocked_by": [
    {
      "user_id": "555555555555555555",
      "display_name": "OtherPlayer",
      "created_at": "2026-09-14 03:12:55"
    }
  ]
}
```

| Field                     | Description                                                     |
|---------------------------|-----------------------------------------------------------------|
| `blocked`                 | Players this player has blocked, newest first                  |
| `blocked_by`              | Players who have blocked this player, newest first             |
| `[].user_id`              | Discord user ID (Google-only accounts as `google_<id>`)          |
| `[].display_name`         | Name the Summit site shows; falls back to the ID if unknown     |
| `[].created_at`           | When the block was made, UTC, `YYYY-MM-DD HH:MM:SS`             |

A player with no blocks returns `200` with both lists empty.

To decide whether two players can be paired from this endpoint, check **both** lists:
the pair is blocked if the other player appears in `blocked` **or** `blocked_by`.

**Privacy:** `blocked_by` tells you who blocked a player. Use it only to keep players
apart; never show a player who has blocked them.

---

## 3. Report a player: `POST /api/player-reports`

Files a report about an opponent, exactly like the Discord **Report Player** button.
Summit admins see it on the admin log page under Blocked Users → Player Reports.

### Request

```
POST https://sorcererssummit.com/api/player-reports
X-API-Key: <your-api-key>
Content-Type: application/json
```

```json
{
  "reporter_id": "123456789012345678",
  "reported_id": "876543210987654321",
  "reporter_name": "Alice",
  "reported_name": "Bob",
  "reasons": ["no_show", "toxic"],
  "details": "Never joined the table and sent rude DMs.",
  "pairing_id": 1234,
  "match_type": "ranked"
}
```

| Field           | Required | Description                                                                 |
|-----------------|----------|-----------------------------------------------------------------------------|
| `reporter_id`   | yes      | Discord user ID of the player filing the report                             |
| `reported_id`   | yes      | Discord user ID of the player being reported (must differ from the reporter) |
| `reasons`       | see note | List of reason codes from the table below                                   |
| `details`       | see note | Free text, up to 1000 characters                                            |
| `reporter_name` | no       | Name to show admins if Summit doesn't know the player (max 100 chars)       |
| `reported_name` | no       | Same, for the reported player                                               |
| `pairing_id`    | no       | Summit `pairingId` from the table Summit opened, if there was one           |
| `match_type`    | no       | Free label shown to admins, e.g. `ranked`, `casual`, `testing` (max 30 chars) |

**Note:** send at least one reason **or** some details. A report with neither is rejected,
same as the Discord form.

PSO should only let a player report someone they actually played, and should send the
reporter's own ID (from their PSO login), not one typed in by the player.

### Reason codes

These match the checkboxes on the Discord Report Player form.

| Code            | Label shown to the player                                       |
|-----------------|-----------------------------------------------------------------|
| `voice_refused` | Opponent joined voice but didn't want to use voice              |
| `left_early`    | Opponent left the match early without conceding                 |
| `no_show`       | Opponent never showed up or joined the game                     |
| `toxic`         | Opponent was rude, toxic, or harassing                          |
| `stalling`      | Opponent stalled or played unreasonably slowly                  |
| `wrong_result`  | Opponent reported the wrong result                              |
| `deck_mismatch` | Opponent played a different deck than they submitted            |
| `cheating`      | Suspected cheating                                              |
| `other`         | Something else (explain below)                                  |

### Response `201 Created`

```json
{ "success": true, "report_id": 87 }
```

Reports are write-only for PSO; there is no endpoint to read reports back. A report does
not block anyone or change ratings. Admins review it.

---

## Errors

| Status | When                                   | Body                                                                 |
|--------|----------------------------------------|----------------------------------------------------------------------|
| `400`  | `user_a` or `user_b` missing           | `{"success": false, "error": "user_a and user_b are required"}`      |
| `400`  | User ID empty or over 64 characters    | `{"success": false, "error": "Invalid user id"}`                     |
| `400`  | Report: body not JSON                  | `{"success": false, "error": "Request body must be JSON"}`           |
| `400`  | Report: `reporter_id` or `reported_id` missing | `{"success": false, "error": "reporter_id and reported_id are required"}` |
| `400`  | Report: reporter and reported are the same | `{"success": false, "error": "A player cannot report themselves"}` |
| `400`  | Report: unknown reason code            | `{"success": false, "error": "Unknown reasons: rude", "allowed_reasons": ["voice_refused", "..."]}` |
| `400`  | Report: no reasons and no details      | `{"success": false, "error": "Give at least one reason or some details"}` |
| `400`  | Report: `details` over 1000 characters | `{"success": false, "error": "details must be 1000 characters or fewer"}` |
| `400`  | Report: `pairing_id` not a number      | `{"success": false, "error": "pairing_id must be an integer"}`       |
| `401`  | Missing or wrong API key (any endpoint) | `{"success": false, "error": "Invalid API key"}`                    |
| `500`  | Server error                           | `{"success": false, "error": "Could not check blocks"}` (or `"Could not load blocks"`, `"Could not save report"`) |

## Notes

- Blocks take effect immediately; there is no caching on Summit's side. If PSO caches the
  per-player list, keep it short (a few minutes) so new blocks and unblocks show up quickly.
- Blocking is directional on Summit, but for matchmaking treat it as mutual.
- There is no endpoint for PSO to add or remove blocks. Players manage them on their Summit
  profile. Ask Summit if PSO needs write access.
