# Tasks: Daily Summary Message

**Input**: Design documents from `specs/main/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: Not explicitly requested. Manual testing via `!daily_summary` admin command.

**Organization**: Tasks grouped by user story. All tasks primarily modify `discord-bot/cogs/daily_summary.py` so stories are sequential, not parallel.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4, US5)
- Include exact file paths in descriptions

---

## Phase 1: Setup & Configuration (US-5)

**Purpose**: Config constants, cog skeleton, bot registration — foundation for all other stories

- [x] T001 [P] [US5] Add `DAILY_SUMMARY_CHANNEL_ID`, `DAILY_SUMMARY_HOUR`, `DAILY_SUMMARY_MINUTE` constants to `discord-bot/config.py` — set defaults: `DAILY_SUMMARY_CHANNEL_ID = LEADERBOARD_CHANNEL_ID`, `DAILY_SUMMARY_HOUR = 23`, `DAILY_SUMMARY_MINUTE = 30`
- [x] T002 [P] [US5] Create `discord-bot/cogs/daily_summary.py` with `DailySummaryCog` class skeleton — inherit from `commands.Cog`, add `__init__(self, bot)`, `cog_unload(self)`, and empty async `_post_daily_summary(self, channel_override=None)` method. Add `async def setup(bot)` at bottom. Import `discord`, `commands`, `config`, `logging`, `datetime`, `asyncio`, `sqlite3`, `ZoneInfo` from `zoneinfo`
- [x] T003 [US5] Import and register `DailySummaryCog` in `discord-bot/main.py` inside `setup_cogs()` — add `from cogs.daily_summary import DailySummaryCog` and `await bot.add_cog(DailySummaryCog(bot))`

**Checkpoint**: Cog loads without errors on bot startup. No functionality yet.

---

## Phase 2: Automated Daily Posting (US-1)

**Goal**: The cog fires once daily at 11:30 PM EST and posts a placeholder embed

**Independent Test**: Bot boots, cog loads, `!daily_summary` admin command posts a test embed to the current channel

- [x] T004 [US1] Add `discord.ext.tasks` scheduled loop to `DailySummaryCog` in `discord-bot/cogs/daily_summary.py` — use `@tasks.loop(time=datetime.time(hour=config.DAILY_SUMMARY_HOUR, minute=config.DAILY_SUMMARY_MINUTE, tzinfo=ZoneInfo("America/New_York")))`. Start task in `__init__` with `self.daily_summary_task.start()`, cancel in `cog_unload` with `self.daily_summary_task.cancel()`. Add `@daily_summary_task.before_loop` waiting for `self.bot.wait_until_ready()`. Task calls `await self._post_daily_summary()`
- [x] T005 [US1] Implement `_post_daily_summary(self, channel_override=None)` in `discord-bot/cogs/daily_summary.py` — compute current EST date using `datetime.datetime.now(ZoneInfo("America/New_York"))`, format as `date_prefix = f"{est_now.strftime('%Y-%m-%d')}%"`. Get target channel: use `channel_override` if provided, else `self.bot.get_channel(config.DAILY_SUMMARY_CHANNEL_ID)`. If channel is None, log error and return. Post a placeholder embed with title `f"Daily Summary — {est_now.strftime('%B %d, %Y')}"`, color `0xFFD700`, footer "Summit Bot • Matches tracked since midnight EST"
- [x] T006 [US1] Add admin-only `!daily_summary` prefix command in `discord-bot/cogs/daily_summary.py` — `@commands.command(name="daily_summary")` with `@commands.has_permissions(administrator=True)`, calls `await self._post_daily_summary(channel_override=ctx.channel)`

**Checkpoint**: `!daily_summary` posts a placeholder embed. Scheduled task is wired up (verifiable via bot startup logs).

---

## Phase 3: Core Stats (US-2)

**Goal**: The embed shows total matches, most active player, largest ELO swing, top ELO gainer, biggest ELO loser

**Independent Test**: `!daily_summary` shows all 5 core stats from today's `match_records`

- [x] T007 [US2] Implement `_query_core_stats(self, date_prefix: str) -> dict` in `discord-bot/cogs/daily_summary.py` — open `match_records.db` (path from `config.MATCH_RECORDS_DB` or construct from `config.DB_PATH`), execute these SQL queries with `match_type = 'ranked'` filter. Note: loser column is spelled `losser_id` / `losser_display_name` in the schema. Queries: (1) `SELECT COUNT(*)` for total matches, (2) most active player via UNION ALL of `winner_id`/`losser_id` grouped by player_id ordered by count DESC LIMIT 1, (3) largest single-match ELO swing via `ABS(winner_lifetime_elo_change)` ORDER DESC LIMIT 1 (include both player names and the match result), (4) top ELO gainer via SUM of `winner_lifetime_elo_change`/`loser_lifetime_elo_change` per player ORDER DESC LIMIT 1, (5) biggest ELO loser — same sum ORDER ASC LIMIT 1. Return dict with keys: `total_matches`, `most_active` (name + count), `largest_swing` (winner_name, loser_name, change), `top_gainer` (name + net_change), `biggest_loser` (name + net_change). Close DB connection in finally block.
- [x] T008 [US2] Wire `_query_core_stats` into `_post_daily_summary` in `discord-bot/cogs/daily_summary.py` — replace placeholder embed. Call `stats = await asyncio.to_thread(self._query_core_stats, date_prefix)`. If `stats["total_matches"] == 0`, post simple embed with description "No ranked matches were played today." and return early. Otherwise proceed to build full embed.
- [x] T009 [US2] Build embed fields for core stats in `_post_daily_summary` in `discord-bot/cogs/daily_summary.py` — add embed fields: "Matches Played" (value=count, inline=True), "Most Active Player" (value=f"{name} ({count} matches)"), "Top ELO Gainer" (value=f"{name} (+{change} ELO)"), "Biggest ELO Drop" (value=f"{name} ({change} ELO)"), "Largest ELO Swing" (value=f"{winner} beat {loser} (+{change})")

**Checkpoint**: `!daily_summary` shows real stats from the database. Zero-match days show a brief message.

---

## Phase 4: Extended / Fun Stats (US-3)

**Goal**: Add unique players, biggest upset, avg match duration, hot streaks, and broken streaks

**Independent Test**: `!daily_summary` shows extended stats. Streak stats correctly span across days. Empty stats are omitted from embed.

- [x] T010 [US3] Add unique players and average match duration queries in `discord-bot/cogs/daily_summary.py` — extend `_query_core_stats` (or create `_query_extended_stats`). Unique players: `SELECT COUNT(DISTINCT player_id) FROM (SELECT winner_id as player_id ... UNION SELECT losser_id ...)`. Avg duration: `SELECT AVG(match_time) FROM match_records WHERE timestamp LIKE ? AND match_type='ranked' AND match_time > 0`. Add results to stats dict. Add embed fields: "Unique Players" (inline=True), "Avg Match Duration" (value=f"{round(avg)} min", inline=True). Omit avg duration field if result is None.
- [x] T011 [US3] Add biggest upset query in `discord-bot/cogs/daily_summary.py` — query the match with the highest `winner_lifetime_elo_change` today (proxy: larger ELO gain = lower-rated winner = bigger upset). Include winner name, loser name, and ELO change. Add embed field "Biggest Upset" (value=f"{winner} beat {loser} (+{change} ELO)"). Omit field if no matches or max change is ≤ 0.
- [x] T012 [US3] Implement hot streak detection in `discord-bot/cogs/daily_summary.py` — create `_compute_streaks(self, date_prefix: str) -> dict` that: (1) gets distinct player IDs from today's matches, (2) for each player, fetches their last 20 matches (`SELECT winner_id, losser_id, winner_display_name, losser_display_name, timestamp FROM match_records WHERE (winner_id=? OR losser_id=?) AND match_type='ranked' ORDER BY timestamp DESC LIMIT 20`), (3) iterates from most recent match backwards counting consecutive wins, (4) collects players with streak ≥ 3 into `hot_streaks` list (sorted by streak length DESC). Call via `asyncio.to_thread()`. Add embed field "Hot Streaks" with each player on a new line (e.g., "DragonSlayer is on a 5-win streak\nWizardKing is on a 3-win streak"). Omit field entirely if list is empty. Cap at top 5 entries.
- [x] T013 [US3] Implement broken streak detection in `discord-bot/cogs/daily_summary.py` — extend `_compute_streaks`: for each player who LOST at least one match today, find their earliest loss today in the ordered match history, then count consecutive wins immediately before that loss. If pre-loss streak was ≥ 6, record as broken: `{"player": loser_name, "streak": N, "broken_by": winner_name}`. Add embed field "Streak Broken" (e.g., "UnluckyMage's 8-win streak was ended by Newcomer"). Omit field if no 6+ streaks were broken.

**Checkpoint**: Full stat suite visible. Streak detection works across days. Missing stats gracefully omitted.

---

## Phase 5: GPT-Flavored Commentary (US-4)

**Goal**: Stats are sent to GPT for an entertaining commentary paragraph displayed at the top of the embed

**Independent Test**: `!daily_summary` shows GPT commentary in the embed description above the stat fields. Commentary varies in style. If OpenAI is unreachable, embed still posts with stats only.

- [x] T014 [US4] Implement `_format_stats_for_gpt(self, stats: dict) -> str` in `discord-bot/cogs/daily_summary.py` — convert stats dict into human-readable text: "Today's stats:\n- {N} ranked matches played\n- {N} unique players\n- Most active: {name} ({N} matches)\n- Top ELO gainer: {name} (+{N})\n- Biggest ELO drop: {name} ({N})\n..." etc. Include hot streaks and broken streaks if present. Omit lines for stats that don't exist. For zero-match days, return "No matches were played today."
- [x] T015 [US4] Implement `_generate_commentary(self, stats_text: str) -> str | None` in `discord-bot/cogs/daily_summary.py` — add `from openai import OpenAI` and `openai_client = OpenAI(api_key=config.OPENAI_API_KEY)` at module level. Define `DAILY_SUMMARY_PROMPT` constant with the system prompt from research.md R-4: "You are a Discord bot writing a daily recap for Sorcery: Contested Realm, a competitive card game. Write a short, entertaining commentary (2-4 sentences, under 100 words)... IMPORTANT: Vary your style every day. Rotate between these voices at random: Epic fantasy narrator, hype sports broadcaster, dry comedic observer, poetic bard, trash-talking arena announcer. Pick ONE style per day. Do not mix styles... NO emojis. Do not repeat the raw numbers... If no matches were played, write a short 'quiet day' message in your chosen style instead." Call `openai_client.responses.create(model="gpt-4.1-nano", instructions=DAILY_SUMMARY_PROMPT, input=stats_text)`, return `response.output_text`. On any exception, log error and return `None`.
- [x] T016 [US4] Integrate GPT commentary into embed in `discord-bot/cogs/daily_summary.py` — in `_post_daily_summary`, after gathering stats and before adding fields: call `stats_text = self._format_stats_for_gpt(stats)`, then `commentary = await asyncio.to_thread(self._generate_commentary, stats_text)`. If `commentary` is not None, set `embed.description = commentary`. For zero-match days, still call GPT with "No matches were played today." for a styled quiet-day message; if GPT returns None, use fallback description "No ranked matches were played today." Apply commentary to both normal and zero-match embeds.

**Checkpoint**: Full feature complete. Commentary appears at top of embed. Fallback works when GPT is unavailable.

---

## Phase 6: Polish & Validation

**Purpose**: Logging, error handling, embed size safety

- [x] T017 Add structured logging throughout `discord-bot/cogs/daily_summary.py` — use `logger = logging.getLogger("discord_bot")`. Log on: task start ("Running daily summary for {date}..."), zero-match day, GPT call success/failure, embed post success with channel name, channel-not-found error. Match logging style of existing cogs.
- [x] T018 Validate embed size constraints in `discord-bot/cogs/daily_summary.py` — ensure total embed content stays under Discord's 6000-char limit. If hot streaks list has more than 5 entries, truncate to top 5 with "and N more..." suffix. If GPT commentary exceeds 500 chars, truncate with "..." suffix. Add a helper `_truncate(text: str, max_len: int) -> str` if needed.
- [x] T019 Run `!daily_summary` end-to-end against live database to verify all stats render correctly, GPT commentary appears with varied styles, zero-match handling works, and embed formatting looks clean in Discord.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup/US-5)**: No dependencies — start immediately
- **Phase 2 (US-1)**: Depends on Phase 1 — cog skeleton must exist
- **Phase 3 (US-2)**: Depends on Phase 2 — needs `_post_daily_summary` method
- **Phase 4 (US-3)**: Depends on Phase 3 — extends the query + embed flow
- **Phase 5 (US-4)**: Depends on Phase 3 — needs stats dict to format for GPT
- **Phase 6 (Polish)**: Depends on all phases complete

### User Story Dependencies

```
Phase 1 (US-5: Config + skeleton)
    └── Phase 2 (US-1: Scheduling + admin command)
           └── Phase 3 (US-2: Core stats + embed)
                  ├── Phase 4 (US-3: Extended stats)
                  └── Phase 5 (US-4: GPT commentary)
                         └── Phase 6 (Polish)
```

- US-3 and US-4 could theoretically run in parallel after US-2, but since all tasks modify the same file (`daily_summary.py`), sequential execution is safer.

### Parallel Opportunities

- **Phase 1**: T001 and T002 can run in parallel (different files: `config.py` vs `daily_summary.py`)
- **All other tasks**: Sequential (same file)

---

## Parallel Example: Phase 1

```bash
# These touch different files and can run simultaneously:
Task: "T001 - Add config constants to discord-bot/config.py"
Task: "T002 - Create cog skeleton in discord-bot/cogs/daily_summary.py"
```

---

## Implementation Strategy

### MVP First (Phases 1-3)

1. Complete Phase 1: Setup — config + skeleton + registration
2. Complete Phase 2: Scheduling — task loop + admin command
3. Complete Phase 3: Core Stats — real data in the embed
4. **STOP and VALIDATE**: `!daily_summary` shows core stats
5. Deploy — daily summaries start posting with basic stats

### Full Feature (add Phases 4-5)

6. Complete Phase 4: Extended Stats — streaks, upsets, unique players
7. Complete Phase 5: GPT Commentary — entertaining rotating-voice recaps
8. Complete Phase 6: Polish — logging, embed safety
9. **VALIDATE**: Full embed with GPT commentary
10. Deploy final version

### Incremental Value

- **After Phase 3**: Basic daily summary with 5 core competitive stats
- **After Phase 4**: Rich stats including cross-day streak tracking and upset detection
- **After Phase 5**: GPT commentary gives each day's summary personality with rotating voices

---

## Total Task Count

| Phase | Description | Tasks |
|-------|-------------|-------|
| Phase 1 | Setup & Config (US-5) | 3 |
| Phase 2 | Scheduling (US-1) | 3 |
| Phase 3 | Core Stats (US-2) | 3 |
| Phase 4 | Extended Stats (US-3) | 4 |
| Phase 5 | GPT Commentary (US-4) | 3 |
| Phase 6 | Polish | 3 |
| **Total** | | **19** |

---

## Notes

- All tasks modify `discord-bot/cogs/daily_summary.py` unless noted otherwise
- The `losser_id` / `losser_display_name` typo in the database schema is intentional — all queries MUST use this spelling
- EST timezone: use `ZoneInfo("America/New_York")` which handles DST automatically
- Existing pattern references: `cogs/match_confirmation_jobs.py` for task loop, `cogs/lfg/helpers.py` for OpenAI integration
- DB file: `match_records.db` — check config for exact path construction
- The OpenAI client uses `responses.create()` (Responses API), NOT `chat.completions.create()`
