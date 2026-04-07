# Feature Specification: Daily Summary Message

## Overview

An automated daily recap message posted to a designated Discord channel every day at 11:30 PM EST. The message provides a snapshot of the day's competitive activity: total matches played, most active players, biggest ELO swings, top ELO gainers, and other community engagement stats. The feature is a new cog that queries existing `match_records` and `overall_standings` tables — no schema changes required.

## User Stories

### US-1: Automated Daily Posting

As a community member, I want an automated daily summary posted at 11:30 PM EST so I can see the day's activity at a glance.

**Acceptance Criteria:**
- A rich embed message is posted to a configurable channel every day at 11:30 PM EST
- The message covers all ranked matches from midnight EST to the time of posting (same calendar day)
- If zero matches were played, a brief "No matches today" message is posted instead
- The scheduled task starts automatically when the bot boots and survives across days
- The task uses `discord.ext.tasks` following the existing `MatchConfirmationJobs` pattern

### US-2: Core Stats

As a community member, I want to see key competitive stats for the day.

**Acceptance Criteria:**
- **Total Matches Played** — count of ranked matches recorded today
- **Most Active Player** — the player who appeared in the most matches (wins + losses), with match count shown
- **Largest ELO Swing** — the single match with the biggest absolute ELO change, showing both players, the result, and the ELO delta
- **Top ELO Gainer** — the player who gained the most cumulative online lifetime ELO across all today's matches, with net change shown
- **Biggest ELO Loser** — the player who lost the most cumulative online lifetime ELO today (displayed lightheartedly)

### US-3: Extended / Fun Stats

As a community member, I want additional fun and engagement stats in the daily summary.

**Acceptance Criteria:**
- **Unique Players** — count of distinct players who played at least one match today
- **Hot Streaks** — players currently on a win streak of 3+ (computed from recent match history, not just today). Shows player name and streak length (e.g., "DragonSlayer is on a 5-win streak")
- **Streak Broken** — players who lost today and had a win streak of 6+ going into that loss. Shows player name, the streak that was broken, and who broke it (e.g., "WizardKing's 8-win streak was ended by Newcomer")
- **Biggest Upset** — the match where the lower-rated player beat the higher-rated player by the largest ELO gap
- **Average Match Duration** — mean match time in minutes (from `match_time` column, excluding nulls/zeros)
- Stats that have no data (e.g., no one is on a 3+ streak) are omitted from the embed rather than showing "N/A"

### US-4: GPT-Flavored Commentary

As a community member, I want the daily summary to feel alive and entertaining, not just raw stats.

**Acceptance Criteria:**
- After computing all stats, the raw data is sent to OpenAI (`gpt-4.1-nano`) to generate a short, themed commentary paragraph
- The commentary is placed at the top of the embed (in the description field) before the stat fields
- The system prompt instructs GPT to write a brief, entertaining recap varying its style each day — sometimes dramatic narrator, sometimes sports broadcaster, sometimes comedic, sometimes poetic. It should reference players by name and call out upsets, streaks, and drama
- Follows the same pattern as the milestone message in `cogs/lfg/helpers.py`: `openai_client.responses.create()` with `instructions` + `input`
- If the OpenAI call fails, the embed posts normally without commentary (stats only, no error shown to users)
- Commentary is capped at ~100 words to keep the embed concise
- Zero-match days get a short "quiet day" themed message from GPT instead

### US-5: Configuration

As a bot administrator, I want to configure the daily summary channel and time.

**Acceptance Criteria:**
- `DAILY_SUMMARY_CHANNEL_ID` added to `config.py` (defaults to `LEADERBOARD_CHANNEL_ID`)
- `DAILY_SUMMARY_HOUR` and `DAILY_SUMMARY_MINUTE` in `config.py` (default 23 and 30)
- No slash/prefix commands needed to trigger the summary — it is purely automated
- An admin-only `!daily_summary` prefix command can manually trigger the summary for testing

## Non-Functional Requirements

- Read-only: no writes to any database table; purely SELECT queries
- Core stats scoped to current EST calendar day (`timestamp LIKE 'YYYY-MM-DD%'`)
- Win streak stats require querying recent match history (beyond today) to compute current streaks and detect broken streaks
- Only counts `match_type = 'ranked'` matches (excludes testing matches)
- Must not block the bot event loop — all DB access in executor or async-safe
- Embed follows Discord's 6000-character limit; truncate gracefully if needed
- Uses existing EST timezone pattern from `cogs/fun.py` (`ZoneInfo("America/New_York")`)

## Out of Scope (Future)

- Weekly / monthly summary rollups
- Configurable stats (pick which stats appear)
- Web app dashboard for daily summaries
- Sending summary via DM to opted-in users
- Historical summary archive
