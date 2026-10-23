# Summit Season Badges API (for Play Sorcery Online)

One call returns every season badge a Summit player holds, so PSO can show them on a
player's profile or beside their name:

- **Bracket finishes** from the Summit postseason brackets: Champion, Finalist, Top 4,
  Top 8 and Top cut (anyone else in the bracket), plus the Limited versions.
- **Season avatar honours**: the top three players on each avatar's ladder in each ended
  Avatar-mode season, e.g. "Gothic Season 9 Top Imposter", "Gothic Season 9 2nd Imposter",
  "Gothic Season 9 3rd Imposter".

Base URL: `https://sorcererssummit.com`

## Authentication

Same key as `POST /api/report-external-match`:

```
X-API-Key: <your Summit API key>
```

(`Authorization: Bearer <key>` also works.) A missing or wrong key returns `401`.

## Request

```
GET /api/partner/season-badges?user_id=181472996882513920
GET /api/partner/season-badges?user_id=181472996882513920,670402383896903681
GET /api/partner/season-badges
```

| Parameter | Description |
|-----------|-------------|
| `user_id` | Optional. One Discord user id, or up to 200 separated by commas. Without it, every player who holds at least one badge is returned. |

A player with no badges still comes back, with two empty lists.

## Response

```json
{
  "success": true,
  "players": [
    {
      "user_id": "181472996882513920",
      "brackets": [
        {
          "season": "Gothic Season 7",
          "bracket": "Gothic Season 7 Postseason Bracket",
          "bracket_slug": "gothic-season-7-postseason-bracket",
          "format": "constructed",
          "placement": 1,
          "label": "Champion",
          "finish": "Champion",
          "title": "Gothic Season 7 Champion",
          "completed_at": "2026-10-01T18:03:32.586403"
        }
      ],
      "avatar_honours": [
        {
          "season": "Gothic Season 9",
          "season_id": 9,
          "avatar": "Imposter",
          "place": 1,
          "label": "Top Imposter",
          "title": "Gothic Season 9 Top Imposter",
          "elo": 1712,
          "wins": 14,
          "losses": 2,
          "games": 16
        }
      ]
    }
  ]
}
```

### `brackets[]`

| Field | Description |
|-------|-------------|
| `season` | The season the bracket closed |
| `bracket` / `bracket_slug` | The bracket's name, and the slug for `GET /api/brackets/{slug}` (see pso-brackets-api.md) |
| `format` | `constructed` or `limited` |
| `placement` | 1 = champion, 2 = finalist, 3 = semifinal, 5 = quarterfinal, 9 = round of 16, and so on |
| `label` | What to show: `Champion`, `Finalist`, `Top 4`, `Top 8`, `Top cut`, or `Limited Champion` etc. |
| `finish` | The same without the Limited prefix, handy for picking a colour or icon |
| `title` | Ready-made text: season + label, e.g. `Gothic Season 7 Top 8` |
| `completed_at` | When the bracket finished |

Only finished brackets count. A bracket that is still being played has not placed anyone yet.

### `avatar_honours[]`

| Field | Description |
|-------|-------------|
| `season` / `season_id` | The ended season |
| `avatar` | The avatar the honour is for |
| `place` | 1, 2 or 3 |
| `label` | `Top <avatar>`, `2nd <avatar>`, `3rd <avatar>` |
| `title` | Ready-made text, e.g. `Gothic Season 9 2nd Imposter` |
| `elo` | Their final season Elo on that avatar, the number they were ranked by |
| `games` | Rated games on that avatar that season |
| `wins` / `losses` | Their record on that avatar that season (`null` if it can't be read) |

How the top three are picked: only **Avatar-mode seasons** give out avatar honours, since
only they have a separate Elo ladder for each avatar (the same ladder as
`GET /api/leaderboard/avatars`). When the season ends, each avatar's ladder is ranked by
final season Elo and the first three entries with at least **10 games** on that avatar earn
Top, 2nd and 3rd. Each player counts only on their highest-ranked avatar that season
(their best entry with 10+ games); their other avatar entries step aside and the next
player moves up, so a player holds at most one avatar honour per season. An avatar where fewer than three players reached 10 games gives out fewer
honours. Player-mode seasons (every season before Avatar mode) have none.

Honours appear as soon as the season is archived and stay fixed after that. The running
season has none.

Both lists are newest season first.

## Notes

- Ids are Discord user ids as strings. Players who signed in with Google appear as
  `google_<id>`.
- The response is cheap to call but changes at most a few times a season, so caching it
  for an hour or more is fine.
- No deck lists or deck links are included.
