# Summit API update: per-avatar top players now ranked by Avatar Score

`GET /api/leaderboard/avatars` now ranks each avatar's players by **Avatar Score** by default, instead of season rating. Avatar Score is the same score the Summit's Top Players by Avatar page uses, so the #1 player you show for an avatar now matches the #1 on our site.

You don't need to change anything. Your current calls keep working and get the new order.

## What changed

| Change | Details |
|--------|---------|
| Default order | Avatar Score, best first. Was season rating. |
| `rank` | Position among that avatar's players in the new order (1 = best). |
| `rank_by` | Default is now `avatar_score`. `rank_by=elo` still gives the season rating order. |
| Response `rank_by` | Now says `"avatar_score"` unless you ask for `elo`. |

Nothing else changed. The 10-game minimum (`min_games`) still applies: players with fewer than 10 games on an avatar rank after everyone who has played enough. Every entry still carries `elo`, `avatar_score`, `overall_rank`, `games`, `wins`, `losses` and `voice_games`.

## What Avatar Score is

Avatar Score rewards a strong win rate over a real number of games. It is the lower bound of the Wilson score interval on the player's win rate with that avatar, plus a small bonus for games played. A 10-2 record beats a 2-0 record, for example. Ties break on win rate, then wins.

## Examples

```
GET https://sorcererssummit.com/api/leaderboard/avatars                      (Avatar Score order)
GET https://sorcererssummit.com/api/leaderboard/avatars?avatar=Imposter&limit=1
GET https://sorcererssummit.com/api/leaderboard/avatars?rank_by=elo          (old season rating order)
```

## Not changed

The past-season endpoints, `GET /api/partner/season-top-avatars` and `GET /api/partner/season-badges`, still rank by final season rating on each avatar.
