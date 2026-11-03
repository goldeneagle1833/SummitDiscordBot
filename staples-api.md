# Summit Staples API

One call returns the top 100 staple cards of Summit ranked constructed play: the cards
that are both widely played and actually help you win.

Base URL: `https://sorcererssummit.com`

## Access

Open to everybody: no login and no API key. Each visitor (by IP) can make 60 calls a
minute; past that the API answers `429`. Any website can call it from the browser
(`Access-Control-Allow-Origin: *`).

## Request

```
GET /api/staples
GET /api/staples?season=all
GET /api/staples?season=8&type=Minion&limit=25
GET /api/staples?from=2026-10-01&through=2026-10-31&element=Fire
```

| Parameter | Description |
|-----------|-------------|
| `season` | `all`, or a Summit season id (the ids from `/api/ranked-analytics/seasons`). |
| `from`, `through` | `YYYY-MM-DD` date range. Ignored when `season` is given. |
| `limit` | 1-100. Default 100. |
| `min_games` | In-deck games a card needs to be ranked. Default 50. |
| `type` | Only this card type (`Minion`, `Magic`, `Site`, `Aura`, `Artifact`...). |
| `element` | `Air`, `Earth`, `Fire`, `Water`, `None` or `Multi`. |

With no `season`, `from` or `through`, the last 90 days up to the latest release are used.

## Where the numbers come from

The same data as the Card Win Rates page: Play Sorcery Online's Summit ranked games
(first game at each Summit matchmade ranked table, constructed). Data is released in
batches on the 1st and 15th, so the newest games are never included;
`releasedThrough` says how far the data goes. Summit saves Play Sorcery Online's card
table once per release (All time, each season and the last 90 days), so those answers
come from Summit's own copy. Only a custom `from`/`through` range asks Play Sorcery
Online live. Only card totals are returned, never a
deck list or a player.

## Staple score

Each card gets a score from 0 to 100:

| Part | Weight | What it measures |
|------|--------|------------------|
| Popularity | 50% | Deck share: how many decks run the card. |
| Impact | 30% | Win rate when played minus win rate when it sat in the deck unplayed (the page's "Played vs. not played"). Needs 20+ games each way, and is pulled toward 0 for small samples (50 games of prior). |
| Win rate | 20% | Win rate when the card is in the deck, pulled toward 50% for small samples (50 games of prior). |

Each part is turned into a percentile among the ranked cards before weighting, so the
three are on the same 0-100 scale (shown under `components`). Avatars are left out,
since every deck runs exactly one.

## Response (example values)

```json
{
  "success": true,
  "window": {"label": "Last 90 days", "from": "2026-08-03", "through": "2026-10-31"},
  "releasedThrough": "2026-10-31",
  "totalGames": 4800,
  "eligibleCards": 312,
  "minGames": 50,
  "count": 100,
  "formula": {"weights": {"popularity": 0.5, "impact": 0.3, "win_rate": 0.2}, "...": "..."},
  "breakdown": {
    "type": {"Minion": 41, "Site": 22, "Magic": 21, "Aura": 9, "Artifact": 7},
    "element": {"Fire": 27, "Earth": 25, "Water": 20, "Air": 18, "None": 6, "Multi": 4},
    "rarity": {"Ordinary": 38, "Exceptional": 31, "Elite": 22, "Unique": 9}
  },
  "cards": [
    {
      "rank": 1,
      "name": "Pudge Butcher",
      "cardKey": "pudge butcher",
      "type": "Minion",
      "elements": ["Earth"],
      "rarity": "Exceptional",
      "imageUrl": "https://sorcererssummit.com/card-images/pudge_butcher.png",
      "stapleScore": 93.4,
      "components": {"popularity": 96.0, "impact": 91.2, "win_rate": 90.1},
      "deckShare": 40.0,
      "inDeckWinRate": 54.0,
      "playedWinRate": 58.0,
      "notPlayedWinRate": 42.0,
      "playedVsNotPlayed": 16.0,
      "openingHandWinRate": 56.0,
      "games": {"inDeck": 3840, "played": 2900, "notPlayed": 940, "openingHand": 1200}
    }
  ]
}
```

Rates and shares are percentages (40.0 = 40%); `playedVsNotPlayed` is in percentage
points. A rate is `null` when PSO has no games for it.

| Status | Meaning |
|--------|---------|
| `400` | A bad parameter (message in `error`). |
| `429` | Over 60 calls a minute from one visitor. |
| `503` | Play Sorcery Online's card data could not be reached (`available: false`). |

Custom date ranges are cached for 10 minutes.
