# Quickstart: Daily Summary Message

## What This Feature Does

Posts an automated daily recap embed to a Discord channel at 11:30 PM EST. Stats are gathered from the database, then passed through GPT (`gpt-4.1-nano`) to generate an entertaining commentary paragraph. The embed shows the GPT commentary plus structured stat fields: total matches, most active player, ELO leaders/losers, biggest upset, hot streaks, broken streaks, and average match duration. Zero database changes — purely reads from existing `match_records` table.

## Key Files

| File | Purpose |
|------|---------|
| `discord-bot/cogs/daily_summary.py` | New cog: scheduled task + embed builder + admin trigger command |
| `discord-bot/config.py` | 3 new constants: `DAILY_SUMMARY_CHANNEL_ID`, `DAILY_SUMMARY_HOUR`, `DAILY_SUMMARY_MINUTE` |
| `discord-bot/main.py` | One line to load the cog |
| `discord-bot/tests/test_daily_summary.py` | Unit tests for stat computation logic |

## How It Works

### Scheduling

Uses `discord.ext.tasks` with `time=` parameter (same pattern as `MatchConfirmationJobs`):

```python
from discord.ext import tasks
from zoneinfo import ZoneInfo
import datetime

EST = ZoneInfo("America/New_York")

@tasks.loop(time=datetime.time(hour=23, minute=30, tzinfo=EST))
async def daily_summary_task(self):
    await self._post_daily_summary()
```

The task fires once per day at 11:30 PM EST. DST is handled automatically by `ZoneInfo`.

### Data Gathering

All queries run in a single function using `asyncio.to_thread()` to avoid blocking:

```python
async def _gather_stats(self, date_prefix: str) -> dict:
    return await asyncio.to_thread(self._query_stats, date_prefix)
```

The `date_prefix` is `"YYYY-MM-DD%"` computed from the current EST date.

### GPT Commentary

After stats are gathered, they're formatted into a text summary and sent to GPT for commentary:

```python
from openai import OpenAI

openai_client = OpenAI(api_key=config.OPENAI_API_KEY)

def generate_commentary(stats_text: str) -> str:
    """Generate entertaining commentary from raw stats via GPT."""
    try:
        response = openai_client.responses.create(
            model="gpt-4.1-nano",
            instructions=(
                "You are a Discord bot writing a daily recap for Sorcery: Contested Realm, a competitive card game. "
                "Write a short, entertaining commentary (2-4 sentences, under 100 words) summarizing the day's competitive action. "
                "Reference players by name. Call out upsets, streaks, and drama — make it feel like a real recap of the day's battles. "
                "IMPORTANT: Vary your style every day. Rotate between these voices at random: "
                "Epic fantasy narrator, hype sports broadcaster, dry comedic observer, poetic bard, trash-talking arena announcer. "
                "Pick ONE style per day. Do not mix styles within the same recap. "
                "NO emojis. Do not repeat the raw numbers — the stats are shown separately below your commentary. "
                "If no matches were played, write a short 'quiet day' message in your chosen style instead."
            ),
            input=stats_text,
        )
        return response.output_text
    except Exception as e:
        logger.error(f"OpenAI API error for daily summary: {e}")
        return None  # Embed posts without commentary
```

Same pattern as `cogs/lfg/helpers.py:generate_milestone_message()`.

### Stats Computed

| Stat | Source | Query Strategy |
|------|--------|---------------|
| Total matches | `match_records` | `COUNT(*)` where ranked + today |
| Unique players | `match_records` | `COUNT(DISTINCT)` on union of winner/loser IDs |
| Most active player | `match_records` | Union winner+loser, group by player, max count |
| Top ELO gainer | `match_records` | Sum `winner/loser_lifetime_elo_change` per player, max |
| Biggest ELO drop | `match_records` | Same sum, min |
| Largest ELO swing | `match_records` | Max `ABS(winner_lifetime_elo_change)` in single match |
| Biggest upset | `match_records` | Max `winner_lifetime_elo_change` (higher = bigger upset) |
| Hot streaks | `match_records` | For each today's player, fetch last 20 matches, count consecutive wins from most recent. Show if ≥ 3 |
| Streak broken | `match_records` | For each player who lost today, check if they had a 6+ win streak going into that loss |
| Avg match duration | `match_records` | `AVG(match_time)` where > 0 |

### Embed Layout

```
┌──────────────────────────────────────┐
│  📊 Daily Summary — April 7, 2026   │
│                                      │
│  DragonSlayer was an absolute       │
│  machine today, grinding out five   │
│  matches and extending a dominant   │
│  five-win streak. Meanwhile,        │
│  Newcomer pulled off the upset of   │
│  the day, toppling Veteran and      │
│  snapping UnluckyMage's legendary   │
│  eight-win run in the process.      │
│                                      │
│  ⚔️ Matches Played    🎮 Players    │
│  12                    8             │
│                                      │
│  👑 Most Active Player               │
│  DragonSlayer (5 matches)            │
│                                      │
│  📈 Top ELO Gainer                   │
│  WizardKing (+48 ELO)               │
│                                      │
│  📉 Biggest ELO Drop                 │
│  UnluckyMage (-35 ELO)              │
│                                      │
│  💥 Largest ELO Swing                │
│  WizardKing beat UnluckyMage (+24)  │
│                                      │
│  🎯 Biggest Upset                    │
│  Newcomer beat Veteran (+28 ELO)    │
│                                      │
│  🔥 Hot Streaks                      │
│  DragonSlayer is on a 5-win streak  │
│  WizardKing is on a 3-win streak   │
│                                      │
│  💔 Streak Broken                    │
│  UnluckyMage's 8-win streak was    │
│  ended by Newcomer                  │
│                                      │
│  ⏱️ Avg Match Duration: 18 min      │
│                                      │
│  Summit Bot • Since midnight EST     │
└──────────────────────────────────────┘
```

### Admin Trigger

```python
@commands.command(name="daily_summary")
@commands.has_permissions(administrator=True)
async def trigger_summary(self, ctx):
    """Manually trigger the daily summary (admin only)."""
    await self._post_daily_summary(channel_override=ctx.channel)
```

### Zero-Match Day

When no ranked matches are recorded, a simpler embed is posted:

```
┌──────────────────────────────────────┐
│  📊 Daily Summary — April 7, 2026   │
│                                      │
│  [GPT "quiet day" commentary]       │
│  e.g. "The arena stood silent       │
│  today — not a single spell was     │
│  cast. Sharpen your decks,          │
│  tomorrow the battle resumes."      │
│                                      │
│  Summit Bot • Since midnight EST     │
└──────────────────────────────────────┘
```

## Config Changes

Add to `discord-bot/config.py`:

```python
# Daily Summary
DAILY_SUMMARY_CHANNEL_ID = LEADERBOARD_CHANNEL_ID  # or a dedicated channel
DAILY_SUMMARY_HOUR = 23    # 11 PM EST (24h)
DAILY_SUMMARY_MINUTE = 30  # :30
```

## Cog Loading

Add to `discord-bot/main.py` in `setup_cogs()`:

```python
from cogs.daily_summary import DailySummaryCog
await bot.add_cog(DailySummaryCog(bot))
```

## Testing Strategy

Unit tests mock the database and OpenAI client, verifying:
- Stat computation from sample match data
- Embed construction (field count, values, description from GPT)
- Zero-match handling (GPT quiet-day message)
- GPT fallback (embed posts without commentary when OpenAI fails)
- Hot streak algorithm (cross-day streaks, edge cases: single match, all wins)
- Broken streak detection (6+ threshold, who broke it)
- Date prefix generation in EST
