# Feature Specification: Limited Queue (Arena Draft Mode)

## Overview

A new "Limited" queue type for the LFG system that enables arena-style draft play. Players draft a deck on Curiosa (against 7 bots), then queue via the Discord bot to play against other drafters. Each player has an "arena run" that tracks wins and losses - the run ends at 3 losses or 5 wins. The entire system is fully isolated from the existing ranked/testing queues: separate database tables, separate ELO tracking, separate match history, and separate player profile stats.

## User Stories

### US-1: Join Limited Queue with Draft Deck

As a player, I want to join the Limited queue with my drafted deck so I can play arena-style matches against other drafters.

**Acceptance Criteria:**
- A new "Limited" option appears in the LFG queue type selection (alongside Ranked/Casual/Both)
- When selecting Limited, the player MUST provide a Curiosa deck URL (required, not optional)
- The system checks if the player has an active arena run:
  - If no active run: creates a new arena run (0 wins, 0 losses) and adds player to queue
  - If active run exists (not yet at 3L/5W): adds player to queue with existing run
  - If run is finished (3L or 5W): player is informed their run is over and must start a new one
- Limited queue players are ONLY matched with other Limited queue players (fully isolated pool)
- Matching uses FIFO + anti-rematch logic (same as existing queue, but within the limited pool only)

### US-2: Arena Run Tracking

As a player in a Limited arena run, I want my wins and losses tracked so I know my progress toward 3 losses or 5 wins.

**Acceptance Criteria:**
- Each arena run tracks: player_id, deck_url, wins, losses, start_time, end_time, status
- After each confirmed match, the winner's run wins increment and the loser's run losses increment
- When a player reaches 3 losses OR 5 wins, the run is marked as "completed"
- A completed player receives a DM summary of their run: final record (e.g., "4-3"), deck used, matches played
- A player can only have ONE active arena run at a time

### US-3: Limited Match Reporting

As a player in a Limited match, I want to report results the same way as regular matches but with Limited-specific tracking.

**Acceptance Criteria:**
- Match reporting flow is identical to existing (WentFirstView → Report → Confirm)
- Confirmed matches are saved to a SEPARATE `limited_match_records` table (not `match_records`)
- Limited ELO is updated in a SEPARATE `limited_elo` table (not `overall_standings`)
- Limited ELO starts at 1500 for new players, uses same K-factor/formula as existing system
- Active pairings for limited matches stored in a SEPARATE `limited_active_pairings` table
- After match confirmation, both players' arena runs are updated (winner +1 win, loser +1 loss)
- If either player's run reaches 3L or 5W after this match, they receive a run-complete DM

### US-4: Post-Match Run Status DM (Continue / Forfeit)

As a player who just finished a limited match, I want to see my run status and choose whether to continue or forfeit.

**Acceptance Criteria:**
- After each confirmed limited match, the bot DMs the player with:
  - Current run record (e.g., "Your Limited run: 2-1")
  - Deck URL used for the run
  - Two buttons: **Continue Run** and **Forfeit Run**
- **Continue Run** button: Dismisses the prompt and replies with the player's current run stats (record, deck, Limited ELO). Does NOT auto-requeue - player joins the limited queue manually when ready.
- **Forfeit Run** button: Immediately ends the run, applies remaining losses to Limited ELO
  - Remaining losses = `3 - current_losses`, each calculated against starting ELO
  - Example: Player is 2-1. Forfeit applies 2 additional phantom losses
  - Forfeited runs are marked with status "forfeited" in the database
  - Player receives a final DM summary of the forfeited run
- **No response (ignored)**: Treated as continuing - the run stays active, player can manually `/lfg` into limited queue later
- Buttons have a reasonable timeout (e.g., 60 minutes) after which they expire silently

### US-5: Limited Stats on Player Profile (Web App)

As a player, I want to see my Limited arena stats on my player profile page, separate from my main stats.

**Acceptance Criteria:**
- A new "Limited Arena" section appears at the bottom of the player profile page
- Shows: Limited ELO, total arena runs, total wins, total losses, best run record
- Shows recent limited match history (same format as existing match history but from `limited_match_records`)
- Completely separate from the main stats section - does not affect any existing profile data

### US-6: Start New Arena Run

As a player whose previous run ended, I want to start a fresh arena run with a new draft deck.

**Acceptance Criteria:**
- When joining Limited queue after a completed/forfeited run, a new run is automatically created
- The new run starts with 0 wins, 0 losses
- The player must provide a new deck URL (can reuse the same URL if they want)
- Previous run history is preserved in the database

## Non-Functional Requirements

- No changes to existing ranked/testing queue functionality (additive only)
- No changes to existing ELO calculation for main/event standings
- Database tables use CREATE TABLE IF NOT EXISTS pattern (idempotent)
- Limited queue state is in-memory (resets on bot restart, like existing queue)
- Arena run state is persisted in database (survives bot restarts)
- User IDs stored as INTEGER to match existing Discord ID format

## Out of Scope (Future)

- Limited-specific leaderboard page on web app
- Draft deck validation (checking if deck was actually drafted vs constructed)
- Limited queue seasonal resets
- Limited arena entry fees or rewards system
- Spectator mode for limited matches
