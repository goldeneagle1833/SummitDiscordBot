# Research: Daily Summary Message

## R-1: Scheduling a daily task at a specific wall-clock time

**Decision:** Use `discord.ext.tasks.loop` with a `time` parameter set to 23:30 EST.

**Rationale:** `discord.ext.tasks` supports a `time=` parameter accepting a `datetime.time` with timezone info. This fires the loop exactly once per day at the specified wall-clock time, handling DST transitions automatically via `ZoneInfo("America/New_York")`. This is the same library already used by `MatchConfirmationJobs`, `StreamingCog`, and `LFGCog` — no new dependencies.

**Alternatives considered:**
- `asyncio.sleep` loop: fragile, drifts, doesn't handle DST. Rejected.
- APScheduler: powerful but adds a dependency the project doesn't use. Rejected.
- OS-level cron: over-engineered for a single daily message. Rejected.

**Implementation pattern:**
```python
from discord.ext import tasks
from zoneinfo import ZoneInfo
import datetime

EST = ZoneInfo("America/New_York")
DAILY_TIME = datetime.time(hour=23, minute=30, tzinfo=EST)

@tasks.loop(time=DAILY_TIME)
async def daily_summary_task(self):
    ...
```

## R-2: Querying today's matches from `match_records`

**Decision:** Filter using `timestamp LIKE 'YYYY-MM-DD%'` where the date is the current EST date.

**Rationale:** The `timestamp` column stores ISO format strings (e.g. `2026-04-07T15:30:45.123456`). SQLite's LIKE operator efficiently filters by date prefix. The date is computed in EST using the existing `ZoneInfo("America/New_York")` pattern from `cogs/fun.py`.

**Key queries:**

1. **Total matches today:**
   ```sql
   SELECT COUNT(*) FROM match_records
   WHERE timestamp LIKE ? AND match_type = 'ranked'
   ```

2. **Most active player** (most matches as winner or loser):
   ```sql
   SELECT player_id, player_name, COUNT(*) as match_count FROM (
       SELECT winner_id as player_id, winner_display_name as player_name
       FROM match_records WHERE timestamp LIKE ? AND match_type = 'ranked'
       UNION ALL
       SELECT losser_id as player_id, losser_display_name as player_name
       FROM match_records WHERE timestamp LIKE ? AND match_type = 'ranked'
   ) GROUP BY player_id ORDER BY match_count DESC LIMIT 1
   ```

3. **Largest single-match ELO swing:**
   ```sql
   SELECT *, ABS(winner_lifetime_elo_change) as swing
   FROM match_records
   WHERE timestamp LIKE ? AND match_type = 'ranked'
   ORDER BY swing DESC LIMIT 1
   ```

4. **Top ELO gainer** (net across all matches):
   ```sql
   SELECT player_id, player_name, SUM(elo_change) as net_change FROM (
       SELECT winner_id as player_id, winner_display_name as player_name,
              winner_lifetime_elo_change as elo_change
       FROM match_records WHERE timestamp LIKE ? AND match_type = 'ranked'
       UNION ALL
       SELECT losser_id as player_id, losser_display_name as player_name,
              loser_lifetime_elo_change as elo_change
       FROM match_records WHERE timestamp LIKE ? AND match_type = 'ranked'
   ) GROUP BY player_id ORDER BY net_change DESC LIMIT 1
   ```

5. **Biggest ELO loser:** Same as #4 but `ORDER BY net_change ASC LIMIT 1`

6. **Unique players:**
   ```sql
   SELECT COUNT(DISTINCT player_id) FROM (
       SELECT winner_id as player_id FROM match_records
       WHERE timestamp LIKE ? AND match_type = 'ranked'
       UNION
       SELECT losser_id as player_id FROM match_records
       WHERE timestamp LIKE ? AND match_type = 'ranked'
   )
   ```

7. **Average match duration:**
   ```sql
   SELECT AVG(match_time) FROM match_records
   WHERE timestamp LIKE ? AND match_type = 'ranked' AND match_time > 0
   ```

8. **Biggest upset** (lower-rated player won): A large positive `winner_lifetime_elo_change` indicates the winner was lower-rated (expected to lose). Use `winner_lifetime_elo_change` as upset proxy — larger change = bigger upset.

## R-3: Win streak detection (current streaks + broken streaks)

**Decision:** Two-phase approach — identify players from today's matches, then query their recent match history to compute streaks.

**Rationale:** Streaks span across days, so we can't just look at today's matches. A player who won 4 matches yesterday and 2 today is on a 6-win streak. Similarly, detecting a "broken streak" requires knowing the streak length before today's loss.

**Phase 1 — Get today's players:**
```sql
SELECT DISTINCT player_id FROM (
    SELECT winner_id as player_id FROM match_records
    WHERE timestamp LIKE ? AND match_type = 'ranked'
    UNION
    SELECT losser_id as player_id FROM match_records
    WHERE timestamp LIKE ? AND match_type = 'ranked'
)
```

**Phase 2 — For each player, fetch recent matches (last 20 is sufficient):**
```sql
SELECT winner_id, losser_id, timestamp FROM match_records
WHERE (winner_id = ? OR losser_id = ?) AND match_type = 'ranked'
ORDER BY timestamp DESC LIMIT 20
```

**Hot Streaks algorithm (current streak ≥ 3):**
1. For each player, iterate their matches from most recent backwards
2. Count consecutive wins from the top
3. If streak ≥ 3, include in "Hot Streaks" section

**Broken Streaks algorithm (streak of 6+ ended today):**
1. For each player who **lost** today, look at their match history
2. Find the first loss today, then count consecutive wins immediately before it
3. If that pre-loss streak was ≥ 6, report it as a broken streak
4. Include who broke the streak (the opponent who won that match)

**Performance:** Typically <30 players per day, each needing 1 query of 20 rows. Total: ~30 small queries + Python iteration. Well within acceptable limits for a once-daily task.

## R-4: GPT commentary generation

**Decision:** Use `gpt-4.1-nano` via the OpenAI Responses API to generate a short themed commentary from the raw stats. Same pattern as the milestone message in `cogs/lfg/helpers.py`.

**Rationale:** The milestone feature already proves this pattern works — cheap, fast, and the `gpt-4.1-nano` model is sufficient for short creative text. Reusing the same client (`openai.OpenAI`) and API shape (`responses.create` with `instructions` + `input`) keeps consistency.

**System prompt (instructions):**
```
You are a Discord bot writing a daily recap for Sorcery: Contested Realm, a competitive card game.
Write a short, entertaining commentary (2-4 sentences, under 100 words) summarizing the day's competitive action.
Reference players by name. Call out upsets, streaks, and drama — make it feel like a real recap of the day's battles.
IMPORTANT: Vary your style every day. Rotate between these voices at random:
- Epic fantasy narrator ("The realm trembled as...")
- Hype sports broadcaster ("WHAT a day on the ladder!")
- Dry comedic observer ("In today's episode of 'questionable life choices'...")
- Poetic bard ("A tale of triumph and tragedy unfolded...")
- Trash-talking arena announcer ("Ladies and gentlemen, we have CARNAGE!")
Pick ONE style per day. Do not mix styles within the same recap.
NO emojis. Do not repeat the raw numbers — the stats are shown separately below your commentary.
If no matches were played, write a short "quiet day" message in your chosen style instead.
```

**User prompt (input):**
```
Today's stats:
- 12 ranked matches played
- 8 unique players
- Most active: DragonSlayer (5 matches)
- Top ELO gainer: WizardKing (+48)
- Biggest ELO drop: UnluckyMage (-35)
- Largest swing: WizardKing beat UnluckyMage (+24 in one match)
- Biggest upset: Newcomer beat Veteran (+28 ELO gain)
- Hot streaks: DragonSlayer (5-win streak)
- Streak broken: UnluckyMage's 8-win streak ended by Newcomer
- Avg match duration: 18 min
```

**Fallback:** If OpenAI call fails (network error, rate limit, etc.), the embed posts without commentary — just the stat fields. Error is logged but not shown to users.

**Cost:** `gpt-4.1-nano` is extremely cheap (~$0.001 per call). One call per day is negligible.

## R-5: Channel and embed design

**Decision:** Use a single `discord.Embed` with GPT commentary in the description and stat fields below.

**Rationale:** Discord embeds support up to 25 fields, 6000 total characters. The `description` field holds the GPT commentary paragraph. Individual stats go in embed fields below for clean formatting.

**Embed structure:**
- Title: "Daily Summary — April 7, 2026"
- Description: GPT-generated commentary (2-4 sentences)
- Color: Gold/amber theme (0xFFD700)
- Footer: "Summit Bot • Matches tracked since midnight EST"
- Fields (inline where appropriate):
  - Matches Played
  - Unique Players
  - Most Active Player
  - Top ELO Gainer
  - Biggest ELO Drop
  - Largest ELO Swing (single match)
  - Biggest Upset
  - Hot Streaks (players on 3+ current win streak, omitted if none)
  - Streak Broken (6+ streak ended today, omitted if none)
  - Avg Match Duration

## R-6: Database access pattern

**Decision:** Direct SQLite queries in the cog using `sqlite3`, reading from `match_records.db`.

**Rationale:** The daily summary is read-only with no business logic writes. Direct DB access follows KISS. The database path comes from config (same pattern as other cogs).

**Thread safety:** Use `asyncio.to_thread()` to avoid blocking the event loop during DB reads.

## R-7: "No matches" handling

**Decision:** Post a brief embed with GPT-generated "quiet day" message when zero matches are recorded.

**Rationale:** Posting even on quiet days maintains consistency. The GPT system prompt already handles this case ("If no matches were played, write a short 'quiet day' message instead"). Fallback if GPT fails: "No matches were played today. Rest up — tomorrow's a new day!"
