# Summit Ticket-Holder Leaderboard API

## `GET /api/leaderboard/ticket-holders`

Returns what the Summit's Discord leaderboard channel shows, as JSON: the current season's
ticket holders ranked by ELO, plus the overall top 8 and the top free-play (non-ticket)
players. It is built from the same standings the bot posts after every rated game, so the
two always agree.

### Authentication

Requires the partner API key via the `X-API-Key` header (same key as the matchmaking relay
and voice lookup).

### Request

```
GET https://sorcererssummit.com/api/leaderboard/ticket-holders
X-API-Key: <your-api-key>
```

| Parameter | Description                                                                          |
|-----------|--------------------------------------------------------------------------------------|
| `limit`   | Optional. Cap the `ticket_holders` list at this many players. The Discord embed shows 24. By default every ranked ticket holder is returned. |

### Response

`200 OK`

```json
{
  "success": true,
  "event": {
    "event_id": 7,
    "event_name": "Season 7",
    "start_date": "2026-09-01T00:00:00",
    "elo_mode": "avatar"
  },
  "rating": "event",
  "elo_mode": "avatar",
  "games_played": 412,
  "ticket_holders": [
    {
      "rank": 1,
      "overall_rank": 2,
      "user_id": "123456789012345678",
      "display_name": "Bruce",
      "elo": 1712,
      "games": 31,
      "wins": 20,
      "losses": 11,
      "voice_games": 14,
      "avatar": "Imposter",
      "is_ticket_holder": true
    }
  ],
  "overall": [ { "rank": 1, "overall_rank": 1, "user_id": "…", "is_ticket_holder": false, "...": "..." } ],
  "free_play": [ { "rank": 1, "overall_rank": 1, "user_id": "…", "is_ticket_holder": false, "...": "..." } ],
  "roster": {
    "size": 38,
    "synced_at": "2026-09-28T14:02:11.318402",
    "configured": true
  },
  "voice_requirement": { "min_games": 5, "enforced": false }
}
```

| Field                    | Description                                                                          |
|--------------------------|--------------------------------------------------------------------------------------|
| `event`                  | The active Summit season, or `null` when none is running                             |
| `rating`                 | `event` while a season is running (season ELO), otherwise `lifetime`                 |
| `elo_mode`               | `player` (one season ELO per player) or `avatar` (one per player and avatar)         |
| `games_played`           | Rated games counted this season — the number in the embed's title                    |
| `ticket_holders`         | Every ranked player who holds a Summit ticket, best first                            |
| `overall`                | Top 8 of everyone ranked, with or without a ticket                                   |
| `free_play`              | Top 8 of the players without a ticket                                                |
| `[].rank`                | Position within that section (1 = best)                                              |
| `[].overall_rank`        | Position on the full ladder, so a ticket holder's rank among everyone is available too |
| `[].user_id`             | Discord user ID (Google-only accounts appear with their Google ID)                   |
| `[].display_name`        | The name the Summit site shows for the player                                        |
| `[].elo`                 | Season ELO (or lifetime ELO when `rating` is `lifetime`)                             |
| `[].games` / `wins` / `losses` | This season's rated record                                                     |
| `[].voice_games`         | Games played on voice this season; see `voice_requirement` for the top-cut rule      |
| `[].avatar`              | Avatar-mode seasons: the avatar this row's ELO belongs to. `null` in Player mode     |
| `roster.size`            | Number of Discord members currently holding a ticket role                            |
| `roster.synced_at`       | When the ticket roster was last read from Discord; `null` if it never has been       |
| `roster.configured`      | `false` means the site cannot read Discord roles, so `ticket_holders` will be empty  |
| `voice_requirement`      | Minimum voice games for top cut, and whether it is currently enforced                |

Only players who have played at least one rated game this season are ranked, exactly as in
the Discord channel. Ties in ELO keep the ladder's order.

**Avatar-mode seasons.** Every player/avatar pair has its own season ELO, so a player can
hold several places on the ladder. `overall` keeps every entry (and `overall_rank` counts
entries). `ticket_holders` and `free_play` list each player **once**, at their best
avatar: top cut belongs to the player, so a second qualifying avatar never takes someone
else's slot. `games` / `wins` / `losses` are that avatar's record; `voice_games` is the
player's total.

### Errors

| Status | Meaning                                    |
|--------|--------------------------------------------|
| `400`  | `limit` is not a positive integer           |
| `401`  | Missing or invalid API key                  |
| `500`  | The leaderboard could not be built          |

### Notes

- The ticket roster is cached from Discord and refreshed automatically when it is more than
  15 minutes old, so polling is cheap. A stale roster is served while the refresh runs in the
  background; `roster.synced_at` tells you what you got.
- Someone who buys a ticket appears in `ticket_holders` on the next refresh after Discord
  grants their role. Until then they are listed under `free_play`.
- Ratings move the moment a game is rated by the bot, or when a match reported through
  `POST /api/report-external-match` confirms (24 hours after the report unless disputed).
