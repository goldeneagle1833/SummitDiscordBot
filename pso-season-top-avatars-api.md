# Summit Season Top Avatars API (for Play Sorcery Online)

One call returns **the top player on each avatar for past Summit avatar seasons**, so PSO
can show "Top Imposter, Gothic Season 9" and the like without asking about players one by one.

These are the same people as the "Top &lt;avatar&gt;" season avatar honours that
`GET /api/partner/season-badges` already returns per player. This endpoint is the
season-first view of the same data.

Base URL: `https://sorcererssummit.com`

## Authentication

Same key as `POST /api/report-external-match` and `/api/partner/season-badges`:

```
X-API-Key: <your Summit API key>
```

(`Authorization: Bearer <key>` also works.) A missing or wrong key returns `401`.

## Request

```
GET /api/partner/season-top-avatars                         every past avatar season, top player per avatar
GET /api/partner/season-top-avatars?season=9                one season, by id
GET /api/partner/season-top-avatars?season=Gothic%20Season%209   one season, by name (any case)
GET /api/partner/season-top-avatars?places=3                top three per avatar instead of top one
GET /api/partner/season-top-avatars?ladder=plain            raw ladder order (see below)
```

| Parameter | Description |
|-----------|-------------|
| `season`  | Optional. Season id or exact season name. Without it, every ended Avatar-mode season, newest first. Unknown season: `404`. |
| `places`  | Optional, `1` to `3`, default `1`. How many players per avatar. |
| `ladder`  | Optional. `honours` (default): matches the season badges, so a player counts only on their best avatar that season and the next player moves up on their other avatars. `plain`: each avatar's own ladder order, so one player can top several avatars. |

## Who counts

- Only **ended Avatar-mode seasons**. The running season never appears; player-mode
  seasons have no per-avatar ladder and don't appear.
- Ranked by the player's **final season rating on that avatar** (Elo up to Season 8,
  Glicko-2 from Season 9), with at least **10 games** on that avatar (`min_games`).
- An avatar with nobody at 10+ games is left out of that season.
- Data comes from saved season standings on the Summit; nothing calls PSO.

## Response

```json
{
  "success": true,
  "ladder": "honours",
  "places": 1,
  "min_games": 10,
  "seasons": [
    {
      "season_id": 9,
      "season": "Gothic Season 9",
      "season_ended": "2027-02-12",
      "avatars": [
        {
          "avatar": "Imposter",
          "place": 1,
          "user_id": "181472996882513920",
          "name": "Ann",
          "elo": 1712,
          "games": 34,
          "wins": 22,
          "losses": 12,
          "label": "Top Imposter",
          "title": "Gothic Season 9 Top Imposter"
        }
      ]
    }
  ]
}
```

| Field | Meaning |
|-------|---------|
| `user_id` | Discord user id (a string). |
| `name` | Summit display name at the time of the call. |
| `elo` | Final season rating on that avatar. |
| `games` | Season games on that avatar. `wins` / `losses` may be `null` if the game records can't be found. |
| `place` / `label` / `title` | 1 = "Top", 2 = "2nd", 3 = "3rd"; `title` is ready to show. |

Avatars inside a season are in A-Z order, then by place. The answer changes only when a
season ends or an admin corrects a past result, so caching it for an hour or a day is fine.
