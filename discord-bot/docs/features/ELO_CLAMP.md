# K-Factor Clamp System

## Problem

Without any adjustment, ELO produces asymmetric swings for heavily mismatched games. A player rated 1700 facing a 1400-rated opponent:

- Win (expected): gains ~6 ELO
- Loss (unexpected): loses ~26 ELO

This feels punishing because the high-rated player is getting penalized 4x more than they're being rewarded for the same information content.

## Solution: K-Factor Clamp

When a higher-rated player **loses** to a lower-rated opponent, the K-factor is reduced proportionally to the rating gap. This softens the loss without affecting wins or the ramp-up period.

### Rules

1. Only applies on **losses** (wins are unchanged)
2. Only applies when the **player's ELO > opponent's ELO** (higher-rated player losing)
3. Only kicks in when **K == 32** (after the 8-day event ramp-up period)
4. During the ramp-up week (K=16..30), behavior is unchanged

### Formula

```python
def update_elo(player_elo, opponent_elo, did_win, k=32):
    expected_score = 1 / (1 + 10 ** ((opponent_elo - player_elo) / 400))
    actual_score = 1 if did_win else 0

    if not did_win and player_elo > opponent_elo and k == 32:
        gap = player_elo - opponent_elo
        k = k * max(0.5, 1 - (gap / 800))

    new_elo = player_elo + k * (actual_score - expected_score)
    return round(new_elo)
```

### K Scale by Rating Gap

| Gap  | Effective K | Max Swing |
|------|-------------|-----------|
| 0    | 32.0        | ±16       |
| 50   | 30.0        | ±15       |
| 100  | 28.0        | ±14       |
| 150  | 26.0        | ±13       |
| 200  | 24.0        | ±12       |
| 250  | 22.0        | ±11       |
| 300  | 20.0        | ±10       |
| 350  | 18.0        | ±9        |
| 400+ | 16.0        | ±8        |

### Example: 1700 vs 1400 (300-point gap)

| Result | Old ELO Change | New ELO Change |
|--------|---------------|----------------|
| Win    | +6            | +6 (unchanged) |
| Loss   | -26           | -16            |

The loss is softened from -26 to -16 while wins remain identical.

## Interaction with Event Ramp-Up

The event K-factor starts at 16 on Day 0 and increases by 2 per day, capping at 32 on Day 8+.

- **Days 0-7** (K=16..30): Clamp does NOT apply — ramp-up K is already below 32
- **Day 8+** (K=32): Clamp applies normally

This means the first week of an event is entirely unaffected, which helps new players establish their ratings without interference from the clamp.

## What the Clamp Does NOT Change

- **Wins for higher-rated players** — unchanged
- **Any match where the lower-rated player loses** — unchanged
- **Ramp-up period** — unchanged
- **Expected value over time** — the system still converges correctly; upsets just hurt slightly less
