# Summit API changes for Avatar-mode seasons

The Summit's next ranked season rates **each player/avatar pair separately**. Every
avatar a player uses gets its own season Elo, starting at 1500. Lifetime Elo is unchanged
(one per player), and top cut is still **one invite per player**.

Each Summit season runs in one of two modes, chosen when the season starts:

| Mode     | Meaning                                              | What changes for PSO              |
|----------|------------------------------------------------------|-----------------------------------|
| `player` | One season Elo per player (how every past season ran) | Nothing                           |
| `avatar` | One season Elo per player **and avatar**             | Ranked joins need a deck link; leaderboard rows carry an `avatar` |

Everything below is already live. The season itself starts when the Summit admins run it;
until then all endpoints behave exactly as before.

---

## 1. Queue status — new fields

`GET /api/matchmaking/users/{discordUserId}/status`

```json
{
  "membership": "member",
  "elo_mode": "avatar",
  "queues": [
    {
      "type": "ranked",
      "label": "Ranked",
      "deck_mode": "required",
      "voice_options": true,
      "voice_choices": ["voice", "no_voice"],
      "default_voice": "voice",
      "...": "..."
    }
  ],
  "result": null
}
```

| Field                | Change                                                                                   |
|----------------------|------------------------------------------------------------------------------------------|
| `elo_mode`           | **New.** `"player"` or `"avatar"` for the running season (`"player"` when no season is running). |
| `queues[].deck_mode` | Existing field. For the `ranked` queue it becomes `"required"` while `elo_mode` is `"avatar"`. Other queues are unchanged. |

Use `deck_mode` (or `elo_mode`) to decide whether your ranked join form must collect a
deck link.

## 2. Joining ranked — deck link required in Avatar mode

`POST /api/matchmaking/users/{discordUserId}/queues`

```json
{
  "queue_type": "ranked",
  "duration_minutes": 30,
  "voice": "voice",
  "deck_url": "https://playsorceryonline.com/?deck=pD-1gXa3cg8c"
}
```

- `deck_url` is **required** for `ranked` while the season is in Avatar mode. Curiosa /
  sorcerytcg.com deck links and Play Sorcery Online deck links are both accepted. The deck
  must be readable (public).
- The avatar is read from the deck when the player joins (to reject bad links right away)
  and again **when the match is made**, and is then locked to that match. Changing the deck
  afterwards doesn't change the avatar the game is rated on.
- Nothing else about joining changes. Other queues don't need a deck.

New `400` responses (body is `{"error": "<message>"}`, suitable to show the player):

| Situation                                   | Message                                                                                                                      |
|---------------------------------------------|------------------------------------------------------------------------------------------------------------------------------|
| Ranked join with no `deck_url` in Avatar mode | `This season rates every avatar separately, so ranked games need a deck link. Paste your Curiosa or Sorcery Online deck link and join again.` |
| Link given but no avatar could be read      | `Couldn't read an avatar from that deck link. Check the link (and that the deck is public) and try again.`                   |

## 3. Match results — no change

`POST /api/matchmaking/matches/{guildId}/{pairingId}/results` is unchanged. The avatars
come from the pairing, so you don't need to send them. When the Summit bot asks the
opponent to confirm a result, it now shows both avatars and lets them dispute if one is
wrong.

## 4. Ticket-holder leaderboard — new fields

`GET /api/leaderboard/ticket-holders` (same `X-API-Key` as today)

```json
{
  "success": true,
  "event": { "event_id": 9, "event_name": "Season 9", "start_date": "...", "elo_mode": "avatar" },
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
  "overall": [ "..." ],
  "free_play": [ "..." ]
}
```

| Field              | Change                                                                                        |
|--------------------|-----------------------------------------------------------------------------------------------|
| `elo_mode`         | **New** (top level and inside `event`). `"player"` or `"avatar"`.                             |
| `[].avatar`        | **New** on every row. The avatar this row's Elo belongs to; `null` in Player mode.            |
| `overall`          | In Avatar mode this is the full ladder, so a player can appear more than once (once per avatar). `overall_rank` counts entries. |
| `ticket_holders`, `free_play` | Each player appears **once**, at their best avatar. Top cut belongs to the player, so a second avatar never takes someone else's slot. |
| `games` / `wins` / `losses` | That avatar's record in Avatar mode.                                                 |
| `voice_games`      | Still the player's total across all avatars (the voice rule for top cut is per player).       |

If you only read `ticket_holders`, the shape is the same as before plus `avatar`; nothing
breaks if you ignore the new fields.

## 5. Per-avatar leaderboards (no key)

`GET /api/leaderboard/avatars`

The season ladder split per avatar, so you can show "the top Imposter players" without
calling anything per player. One call returns every avatar; one request per avatar is
never needed.

```
GET https://sorcererssummit.com/api/leaderboard/avatars
GET https://sorcererssummit.com/api/leaderboard/avatars?avatar=Imposter
GET https://sorcererssummit.com/api/leaderboard/avatars?limit=10
```

| Parameter | Description                                                        |
|-----------|--------------------------------------------------------------------|
| `avatar`  | Optional. Only this avatar (case-insensitive, e.g. `imposter`).     |
| `limit`   | Optional. Cap each avatar's list at this many entries.              |

```json
{
  "success": true,
  "event": { "event_id": 9, "event_name": "Season 9", "start_date": "...", "elo_mode": "avatar" },
  "elo_mode": "avatar",
  "avatars": [
    {
      "avatar": "Imposter",
      "players": 11,
      "entries": [
        {
          "rank": 1,
          "overall_rank": 3,
          "user_id": "123456789012345678",
          "display_name": "Bruce",
          "elo": 1688,
          "games": 24,
          "wins": 16,
          "losses": 8,
          "voice_games": 14
        }
      ]
    }
  ],
  "voice_requirement": { "min_games": 5, "enforced": false }
}
```

| Field            | Description                                                                 |
|------------------|-----------------------------------------------------------------------------|
| `avatars`        | One block per avatar played this season, in alphabetical order              |
| `[].players`     | How many players have a rated entry on that avatar (before `limit` applies) |
| `[].entries`     | That avatar's players, best first                                           |
| `[].entries[].rank`         | Position among players of that avatar (1 = best)                 |
| `[].entries[].overall_rank` | Position of that entry on the full season ladder                 |
| `[].entries[].elo`          | The player's season Elo **on that avatar**                       |
| `[].entries[].games/wins/losses` | That avatar's record this season                            |
| `[].entries[].voice_games`  | The player's voice games this season (all avatars)               |

Only players with at least one rated game on the avatar are listed. In a Player-mode
season `elo_mode` is `"player"` and `avatars` is empty, since there is no per-avatar
ladder to show.

## 6. Public season ladder (optional, no key)

`GET /api/leaderboard/event` is what the Summit home page shows. It returns `event`
(with `elo_mode`) and `leaderboard`: one row per player/avatar entry with `id`,
`entry_id` (unique per row), `name`, `avatar`, `event_elo`, `wins`, `losses` and
`voice_games`. It has no ticket-holder split and no one-per-player rule, so use the
ticket-holder endpoint for anything top-cut related.

---

## Summary of what you need to do

1. Read `deck_mode` (or `elo_mode`) from the status call and, when ranked needs a deck,
   collect a deck link in your ranked join form and send it as `deck_url`.
2. Show the `error` message from a `400` on join; both messages are written for players.
3. Optionally show `avatar` next to names on the ticket-holder leaderboard, and use
   `/api/leaderboard/avatars` for per-avatar standings.

Questions: ask Bruce in the Summit Discord.
