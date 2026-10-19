# Summit Player Block and Report API (for Play Sorcery Online)

Players on sorcererssummit.com can block other players from their player profile
(Profile → Block List). These endpoints let Play Sorcery Online do the same from inside
PSO: add a player to someone's block list, or take them off it. A block added from PSO
goes into the **same** Summit block list, so it shows on the player's Summit profile and
the Summit Discord bot will no longer pair the two players.

PSO can also file **Report Player** reports, the same as the 🚩 button on the Discord
pairing message (section 3).

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

Always send the blocking or reporting player's own ID from their PSO login, never an ID
the player typed in.

---

## 1. Block a player: `POST /api/blocks`

Adds `blocked_user_id` to `user_id`'s block list.

### Request

```
POST https://sorcererssummit.com/api/blocks
X-API-Key: <your-api-key>
Content-Type: application/json
```

```json
{
  "user_id": "123456789012345678",
  "blocked_user_id": "876543210987654321",
  "reason": "Rude in chat"
}
```

| Field             | Required | Description                                                       |
|-------------------|----------|-------------------------------------------------------------------|
| `user_id`         | yes      | Discord user ID of the player doing the blocking                  |
| `blocked_user_id` | yes      | Discord user ID of the player being blocked                       |
| `reason`          | yes      | Why they're blocking (max 200 chars, longer is cut). Required, the same as on the Summit profile. Admins can see it; the blocked player never does. |

### Response

`201 Created` when the block is new:

```json
{ "success": true, "added": true }
```

`200 OK` when that player was already blocked (nothing changes, the original reason is
kept):

```json
{ "success": true, "added": false }
```

### What a block does

- It is one-way (A blocks B), but Summit matchmaking treats it as mutual: if either player
  has blocked the other, they are not paired. PSO should do the same.
- It shows in the player's block list on their Summit profile, where they can also remove it.

---

## 2. Unblock a player: `DELETE /api/blocks/<user_id>/<blocked_user_id>`

Takes `blocked_user_id` off `user_id`'s block list.

### Request

```
DELETE https://sorcererssummit.com/api/blocks/123456789012345678/876543210987654321
X-API-Key: <your-api-key>
```

### Response `200 OK`

```json
{ "success": true, "removed": true }
```

`"removed": false` means there was no such block (not an error).

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

| Status | When                                            | Body                                                                 |
|--------|-------------------------------------------------|----------------------------------------------------------------------|
| `400`  | Body not JSON                                   | `{"success": false, "error": "Request body must be JSON"}`           |
| `400`  | Block: `user_id` or `blocked_user_id` missing   | `{"success": false, "error": "user_id and blocked_user_id are required"}` |
| `400`  | Block: player blocking themselves               | `{"success": false, "error": "A player cannot block themselves"}`    |
| `400`  | Block: no reason                                | `{"success": false, "error": "A reason is required when blocking a user"}` |
| `400`  | Unblock: ID empty or over 64 characters         | `{"success": false, "error": "Invalid user id"}`                     |
| `400`  | Report: `reporter_id` or `reported_id` missing  | `{"success": false, "error": "reporter_id and reported_id are required"}` |
| `400`  | Report: reporter and reported are the same      | `{"success": false, "error": "A player cannot report themselves"}`   |
| `400`  | Report: unknown reason code                     | `{"success": false, "error": "Unknown reasons: rude", "allowed_reasons": ["voice_refused", "..."]}` |
| `400`  | Report: no reasons and no details               | `{"success": false, "error": "Give at least one reason or some details"}` |
| `400`  | Report: `details` over 1000 characters          | `{"success": false, "error": "details must be 1000 characters or fewer"}` |
| `400`  | Report: `pairing_id` not a number               | `{"success": false, "error": "pairing_id must be an integer"}`       |
| `401`  | Missing or wrong API key (any endpoint)         | `{"success": false, "error": "Invalid API key"}`                     |
| `500`  | Server error                                    | `{"success": false, "error": "Could not save block"}` (or `"Could not remove block"`, `"Could not save report"`) |
