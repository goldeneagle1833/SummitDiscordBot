# Summit Match History API

Look up any player's ranked match history on Sorcerers Summit: results, opponents,
rating changes, and the avatar and deck elements each side played. Deck lists and
deck links are never included.

Base URL: `https://sorcererssummit.com`

Terms of use: https://sorcererssummit.com/data-terms. By calling the API you agree to
them (short version: credit Sorcerers Summit, non-commercial unless we say yes, build
something new rather than copying Summit's own pages such as the match history tab,
respect players, cache what you fetch).

## Access

Open to everybody: no login and no API key, but **every call must name the website or
app that will show the data**, with `site=https://your-site.example` in the query
string (or an `X-Summit-Site` header). For a personal project with no site, send
`contact=<your Discord name>` instead (or an `X-Summit-Contact` header), or anything
else that lets us reach you. Calls with neither get `400`. Use your real site or
name: we check that the terms are being followed. Each visitor (by IP) can make 60 calls a
minute across these endpoints; past that the API answers `429`. Any website can call
it from the browser (`Access-Control-Allow-Origin: *`). Each player's list is cached
for a minute, so calling more often than that gets you nothing new.

Please send a `User-Agent` header that names your app and a way to reach you (for
example `SorceryStatsBot/1.0 (+https://example.com)`), so we know who to talk to
before limiting anything.

## Find a player's ID

```
GET /api/public/players/search?q=golden&site=https://your-site.example
```

| Parameter | Description |
|-----------|-------------|
| `site` | Your website or app's address. Required, unless you send `contact`. |
| `contact` | For a personal project: your Discord name or another way to reach you. |
| `q` | 2-50 characters of the player's name. |
| `limit` | 1-20. Default 10. |

```json
{
  "success": true,
  "players": [{ "id": "123456789012345678", "name": "GoldenEagle" }],
  "terms_of_use": "https://sorcererssummit.com/data-terms"
}
```

The ID is the player's Discord ID, the same number as in their profile link
(`sorcererssummit.com/player/<id>`).

## Match history

```
GET /api/public/players/<id>/matches?site=https://your-site.example
GET /api/public/players/<id>/matches?site=https://your-site.example&season=current
GET /api/public/players/<id>/matches?site=https://your-site.example&season=8&page=2&per_page=50
```

| Parameter | Description |
|-----------|-------------|
| `site` | Your website or app's address. Required, unless you send `contact`. |
| `contact` | For a personal project: your Discord name or another way to reach you. |
| `season` | `all` (default), `current`, or a season id (each match shows its `season_id`). |
| `page` | Page number, from 1. Default 1. |
| `per_page` | 1-100. Default 25. |

Matches come newest first.

### Response (example values)

```json
{
  "success": true,
  "player": { "id": "111111111111111111", "name": "GoldenEagle" },
  "season": "all",
  "record": { "wins": 120, "losses": 95, "games": 215, "win_rate": 55.8 },
  "deck_info_released_through": "2026-11-15",
  "terms_of_use": "https://sorcererssummit.com/data-terms",
  "matches": [
    {
      "match_id": 48211,
      "date": "2026-11-10T21:14:03",
      "season_id": 9,
      "season": "Gothic Season 9",
      "result": "win",
      "rating_change": 14,
      "rating_change_hidden": false,
      "on_play": true,
      "match_time_minutes": 32,
      "deck_info_released": true,
      "player": { "avatar": "Sparkmage", "elements": ["Air", "Fire"] },
      "opponent": {
        "id": "222222222222222222",
        "name": "Opponent",
        "avatar": "Geomancer",
        "elements": ["Earth"]
      }
    }
  ],
  "pagination": { "page": 1, "per_page": 25, "total_matches": 215, "total_pages": 9, "has_next": true }
}
```

### Fields

| Field | Meaning |
|-------|---------|
| `match_id` | Summit's match number (the same one the site and bot use). |
| `date` | When the result was reported (server time, ISO 8601). |
| `season_id`, `season` | The Summit season the game counted for. |
| `result` | `win` or `loss`, from this player's side. |
| `rating_change` | The rating change shown on the player's profile for this game (the avatar entry's change in avatar seasons). `null` when the player was still provisional (first 8 games of a Glicko-2 season); `rating_change_hidden` is then `true`. |
| `on_play` | `true` went first, `false` went second, `null` not recorded. |
| `match_time_minutes` | Game length if it was recorded, else `null`. |
| `deck_info_released` | `false` for games newer than the latest Meta Report release (1st and 15th of each month). Their `avatar` and `elements` are `null` until that batch is released. |
| `player`, `opponent` | Avatar and deck elements (Air, Earth, Fire, Water) each side played. Elements come from the spellbook and sideboard cards. |

## What is and isn't included

- Ranked Summit games only. Casual and testing games, solo reports, Limited and paper
  events are left out.
- Never a deck list, deck link, deck snapshot or replay.
- If a player reset their profile, games before the reset are left out (the current
  season's games stay), as on their profile.
- Everything comes from Summit's own database; the API never calls Play Sorcery Online.

## Errors

| Status | When |
|--------|------|
| `400` | Missing `site`/`contact`, or a bad parameter (the `error` field says which). |
| `404` | No ranked matches for that ID. |
| `429` | Over 60 calls a minute. Wait a minute. |
| `500` | Something went wrong on our side. |

Errors look like `{ "success": false, "error": "..." }`.
