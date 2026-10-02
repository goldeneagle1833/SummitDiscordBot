# Summit Brackets API

The Summit runs its postseason brackets on the website. These endpoints return what the
bracket pages show: the list of brackets, a bracket's full tree with results, and each
player's postseason history. They are read-only and public (no API key needed), so they
can be called from the browser or server-to-server.

Base URL: `https://sorcererssummit.com`

---

## 1. List brackets

```
GET /api/brackets
```

Published brackets only, newest first. Drafts the admins are still seeding are not listed.

```json
{
  "success": true,
  "brackets": [
    {
      "bracket_id": 2,
      "slug": "gothic-season-6-postseason-bracket",
      "name": "Gothic Season 6 Postseason Bracket",
      "status": "complete",
      "entrant_count": 24,
      "bracket_size": 32,
      "seeded_from": "manual",
      "elo_event_name": null,
      "confirm_hours": 48,
      "published_at": "2026-09-28T17:13:40.546588",
      "completed_at": "2026-09-30T18:03:32.586403",
      "open_matches": 0,
      "champion": { "user_id": "670402383896903681", "display_name": "greenskin", "seed": 8 }
    }
  ]
}
```

| Field            | Description                                                                 |
|------------------|-----------------------------------------------------------------------------|
| `slug`           | Use this in the other calls                                                 |
| `status`         | `published` (in progress) or `complete`                                     |
| `entrant_count`  | Players in the field                                                        |
| `bracket_size`   | Tree size (next power of two); the difference is first-round byes           |
| `seeded_from`    | `ticket_holders`, `overall` or `manual`: where the seeding came from        |
| `elo_event_name` | The season the seeding Elo came from, when seeded from a ladder             |
| `confirm_hours`  | How long a reported result waits for the opponent before auto-confirming    |
| `open_matches`   | Matches with both players known that haven't been played yet                |
| `champion`       | The winner once the final is decided, otherwise `null`                      |

## 2. One bracket, with the full tree

```
GET /api/brackets/{slug}
```

```json
{
  "success": true,
  "bracket": { "...same fields as the list..." },
  "entrants": [
    { "seed": 1, "user_id": "181472996882513920", "display_name": "Weisel",
      "elo": 1712, "games": 31, "is_ticket_holder": 1 }
  ],
  "rounds": [
    {
      "round": 1,
      "title": "Round 1",
      "matches": [
        {
          "match_no": 5,
          "round": 1,
          "round_title": "Round 1",
          "position": 5,
          "state": "complete",
          "playable": true,
          "p1_seed": 9,  "p1_user_id": "…", "p1_name": "Alice", "p1_from_bye": false,
          "p2_seed": 24, "p2_user_id": "…", "p2_name": "Bob",   "p2_from_bye": false,
          "winner_seed": 9, "winner_user_id": "…",
          "next_match_no": 19, "next_slot": 1,
          "reported_at": "…", "reported_by": "…", "reported_winner_id": "…",
          "resolved_at": "…", "expires_at": "…",
          "replay_url": null, "replay_public": false,
          "has_table": false
        }
      ]
    }
  ],
  "champion": { "user_id": "…", "display_name": "…", "seed": 8 },
  "decks_missing": 0
}
```

Returns `404` for an unknown slug or a bracket that hasn't been published yet.

**Entrants** are listed in seed order. `elo` and `games` are the values at seeding time
(`null` when seeded by hand); `is_ticket_holder` is `1` or `0`.

**Rounds** are in play order, titled `Round 1`, `Round 2`, … then `Quarterfinals`, `Semifinals`, `Finals`. Byes are not drawn: a player with a first-round bye simply
appears in round two with `p1_from_bye` / `p2_from_bye` set.

**Match fields**

| Field                       | Description                                                                   |
|-----------------------------|-------------------------------------------------------------------------------|
| `match_no`                  | Stable number of the match within the bracket                                 |
| `state`                     | `pending` (not played), `reported` (one side reported, waiting for the other), `disputed`, `complete`, `bye` |
| `playable`                  | Both seats are known, so the match can be played                              |
| `p1_*` / `p2_*`             | The two players. Seats are `null` until the feeding matches are decided       |
| `winner_seed`, `winner_user_id` | Set once the match is `complete`                                          |
| `next_match_no`, `next_slot`| Where the winner goes (the match number and whether they become p1 or p2)     |
| `reported_*`, `expires_at`  | The pending report: who reported which winner, and when it auto-confirms      |
| `replay_url`                | A replay link when one was added and made public, otherwise `null`            |
| `has_table`                 | Whether a Sorcery Online table was opened for this match                      |

The `viewer_*` fields (`viewer_can_report`, `viewer_can_confirm`, `viewer_table_url`, …)
describe what a logged-in player may do on the Summit site. For a server-to-server call
they are always false / `null` and can be ignored.

**`decks_missing`** is how many entrants haven't submitted a decklist yet. The Summit
site keeps the tree hidden until it reaches `0`, so nobody scouts their draw before the
field is locked. You may want to do the same.

## 3. A player's postseason history

```
GET /api/brackets/player/{discordUserId}
```

```json
{
  "success": true,
  "brackets": [
    {
      "slug": "gothic-season-6-postseason-bracket",
      "name": "Gothic Season 6 Postseason Bracket",
      "status": "complete",
      "entrants": 24,
      "seed": 8,
      "placement": 1,
      "label": "Champion",
      "wins": 4,
      "losses": 0,
      "played_at": "2026-09-28T17:13:40.546588"
    }
  ]
}
```

`placement` is the player's finishing position (1 = champion; players still in the
running have `null` and the label `Still in`). `label` is one of `Champion`, `Finalist`,
`Top 4`, `Top 8` or `Top cut`. The list is empty for a player with no postseason games.

## 4. Postseason honours for every player

```
GET /api/brackets/marks
```

```json
{
  "success": true,
  "marks": {
    "670402383896903681": {
      "wins": 1,
      "best": 1,
      "best_label": "Champion",
      "entries": [
        { "slug": "…", "name": "…", "placement": 1, "label": "Champion" }
      ]
    }
  }
}
```

Keyed by Discord user ID, finished brackets only. This is what draws the trophy marks next
to names on the Summit leaderboard; one call covers everyone, so it suits a leaderboard
view better than calling section 3 per player.

---

## Notes

- Results are reported by the players themselves on the Summit site and confirmed by the
  opponent (or auto-confirmed after `confirm_hours`). Admins can resolve disputes. A
  bracket's tree can therefore change until `status` is `complete`.
- Bracket games move lifetime Elo only; they are not season games and never appear on the
  season ladder or the ticket-holder leaderboard.
- Names are the ones the Summit site shows (a player's chosen display name when they set
  one), the same as on the leaderboard endpoints.

Questions: ask Bruce in the Summit Discord.
