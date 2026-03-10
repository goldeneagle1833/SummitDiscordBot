# Data Model: Mobile Life Counter

**Feature**: Mobile Life Counter with Match Reporting
**Branch**: `001-mobile-life-counter`
**Date**: 2026-03-09

This document defines all entities (client-side and database) for the life counter feature.

---

## Client-Side Entities

### LifeCounterState (Session Storage)

**Purpose**: Tracks current game state in browser session storage. Persists across page refreshes within the same tab.

**Storage Key**: `lifeCounterState`

**Schema**:
```json
{
  "version": "1.0",
  "timestamp": 1709999999000,
  "players": {
    "player1": {
      "name": "Player 1",
      "life": 20,
      "element": "fire" | "water" | "earth" | "air" | null,
      "counters": {
        "dice": 0,
        "pyramid": 0,
        "token": 0
      }
    },
    "player2": {
      "name": "Player 2",
      "life": 20,
      "element": "fire" | "water" | "earth" | "air" | null,
      "counters": {
        "dice": 0,
        "pyramid": 0,
        "token": 0
      }
    }
  },
  "matchStartedAt": 1709999999000,
  "lastModified": 1709999999000
}
```

**Field Definitions**:
- `version` (string): Schema version for future migrations (always "1.0" for MVP)
- `timestamp` (number): Unix timestamp in milliseconds when state was created
- `players.player1/player2.name` (string): Display name for each player (default "Player 1"/"Player 2")
- `players.player1/player2.life` (number): Current life total (default 20, can be negative)
- `players.player1/player2.element` (string | null): Selected element icon, one of: "fire", "water", "earth", "air", or null if not selected
- `players.player1/player2.counters` (object): Additional game counters (dice, pyramid, token), default 0 each
- `matchStartedAt` (number): Unix timestamp when life counter was initialized
- `lastModified` (number): Unix timestamp of last state update (for detecting staleness)

**Validation Rules**:
- Life totals: No min/max constraints (can go negative, can exceed 20)
- Element: Must be one of 4 valid values or null
- Counters: Must be non-negative integers
- Names: Max 50 characters, default to "Player 1"/"Player 2" if empty

**State Transitions**:
1. **Initialize**: Create new state object with default values when page loads with no existing state
2. **Update**: Merge changes on every counter adjustment, update `lastModified`
3. **Reset**: Clear state and reinitialize with defaults when user taps reset button
4. **Submit**: Clear state after successful match report submission

**Persistence Strategy**:
- Auto-save on every change (debounced to 500ms max)
- Load on page mount: `const state = JSON.parse(sessionStorage.getItem('lifeCounterState') || 'null')`
- Clear on explicit reset or match submission

---

## Database Entities

### MatchConfirmation (New Table)

**Purpose**: Track pending match confirmation requests sent to opponents after match report submission.

**Table Name**: `match_confirmations`

**Schema** (SQLite):
```sql
CREATE TABLE match_confirmations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_report_id INTEGER, -- Foreign key to match_records.id (nullable until confirmed)
    submitter_discord_id INTEGER NOT NULL, -- Winner who submitted the report
    opponent_discord_id INTEGER NOT NULL, -- Loser who must confirm
    winner_discord_id INTEGER NOT NULL, -- Clarifies who won (can be submitter or opponent)
    loser_discord_id INTEGER NOT NULL, -- Clarifies who lost
    winner_deck_url TEXT, -- Optional Curiosa.io deck link for winner
    loser_deck_url TEXT, -- Optional Curiosa.io deck link for loser
    final_life_winner INTEGER NOT NULL, -- Winner's final life total
    final_life_loser INTEGER NOT NULL, -- Loser's final life total (typically 0)
    status TEXT NOT NULL DEFAULT 'pending', -- 'pending', 'confirmed', 'disputed', 'auto_confirmed'
    created_at INTEGER NOT NULL, -- Unix timestamp (seconds)
    confirmed_at INTEGER, -- Unix timestamp when confirmed/disputed (null if pending)
    expires_at INTEGER NOT NULL, -- Unix timestamp when auto-confirm triggers (created_at + 24h)
    dispute_reason TEXT, -- Optional text if disputed
    FOREIGN KEY (match_report_id) REFERENCES match_records(id) ON DELETE SET NULL
);

-- Indexes for query performance
CREATE INDEX idx_match_confirmations_opponent ON match_confirmations(opponent_discord_id, status);
CREATE INDEX idx_match_confirmations_expires ON match_confirmations(expires_at, status);
CREATE INDEX idx_match_confirmations_status ON match_confirmations(status);
```

**Field Definitions**:
- `id`: Auto-incrementing primary key
- `match_report_id`: Foreign key to `match_records.id`, set when confirmation is processed and match record created (nullable until then)
- `submitter_discord_id`: Discord user ID of player who submitted the report (typically the winner)
- `opponent_discord_id`: Discord user ID of player who must confirm (typically the loser)
- `winner_discord_id`: Discord user ID of the winning player (clarifies role if submitter isn't winner in draw scenarios)
- `loser_discord_id`: Discord user ID of the losing player
- `winner_deck_url`: Optional URL to winner's deck on Curiosa.io (nullable)
- `loser_deck_url`: Optional URL to loser's deck on Curiosa.io (nullable)
- `final_life_winner`: Winner's life total when match ended (integer, typically >0)
- `final_life_loser`: Loser's life total when match ended (integer, typically 0)
- `status`: Confirmation status enum: 'pending' (default), 'confirmed', 'disputed', 'auto_confirmed'
- `created_at`: Unix timestamp (seconds) when confirmation was created
- `confirmed_at`: Unix timestamp (seconds) when opponent confirmed/disputed (null if still pending)
- `expires_at`: Unix timestamp (seconds) when auto-confirm triggers (created_at + 86400 seconds)
- `dispute_reason`: Optional text field for opponent to explain dispute (nullable)

**Validation Rules**:
- `status`: Must be one of: 'pending', 'confirmed', 'disputed', 'auto_confirmed'
- `expires_at`: Must be >= created_at (typically created_at + 86400 for 24 hours)
- `final_life_loser`: Typically 0, but can be >0 in edge cases (both players at 0 simultaneously)
- `winner_discord_id` and `loser_discord_id`: Must be different
- `opponent_discord_id`: Must match either winner or loser (typically loser)

**State Transitions**:
```text
pending → confirmed (opponent clicks "Confirm")
pending → disputed (opponent clicks "Dispute")
pending → auto_confirmed (24 hours pass with no response)
```

**Queries**:
1. **Get pending confirmations for user**:
   ```sql
   SELECT * FROM match_confirmations
   WHERE opponent_discord_id = ? AND status = 'pending' AND expires_at > ?
   ORDER BY created_at DESC;
   ```

2. **Get expired confirmations for auto-confirm**:
   ```sql
   SELECT * FROM match_confirmations
   WHERE status = 'pending' AND expires_at <= ?;
   ```

3. **Check for duplicate pending within 1 hour**:
   ```sql
   SELECT COUNT(*) FROM match_confirmations
   WHERE submitter_discord_id = ? AND opponent_discord_id = ?
     AND status = 'pending' AND created_at > ?;
   ```

---

### MatchRecord (Extended Table)

**Purpose**: Extend existing `match_records` table with life counter metadata.

**Table Name**: `match_records` (existing)

**Schema Changes** (ALTER TABLE):
```sql
-- Add new columns to existing match_records table
ALTER TABLE match_records ADD COLUMN submitted_via_life_counter INTEGER DEFAULT 0; -- Boolean (0/1)
ALTER TABLE match_records ADD COLUMN final_player1_life INTEGER; -- Nullable for legacy records
ALTER TABLE match_records ADD COLUMN final_player2_life INTEGER; -- Nullable for legacy records
```

**New Field Definitions**:
- `submitted_via_life_counter` (INTEGER 0/1): Boolean flag indicating match was reported via life counter page (0 = no, 1 = yes)
- `final_player1_life` (INTEGER, nullable): Player 1's final life total when match ended (null for legacy matches not from life counter)
- `final_player2_life` (INTEGER, nullable): Player 2's final life total when match ended (null for legacy matches not from life counter)

**Existing Fields** (for reference, not modified):
- `id`: Primary key
- `winner_id`: Discord user ID of winner
- `loser_id`: Discord user ID of loser
- `winner_elo`: Winner's ELO rating after match
- `loser_elo`: Loser's ELO rating after match
- `elo_change`: ELO points exchanged
- `timestamp`: Unix timestamp of match
- `winner_deck_url`: Optional deck URL for winner
- `loser_deck_url`: Optional deck URL for loser
- `event_id`: Optional event/tournament ID (null for casual matches)

**Validation Rules**:
- `submitted_via_life_counter`: Must be 0 or 1
- `final_player1_life` and `final_player2_life`: If not null, at least one must be ≤ 0 (someone lost)
- New columns are nullable to maintain backward compatibility with existing records

**Migration Strategy**:
- Run ALTER TABLE statements in a migration script (not inline)
- Existing records will have null values for new columns (acceptable)
- New records from life counter will populate all three new fields

---

## Entity Relationships

```text
┌─────────────────────────┐
│ LifeCounterState        │ (Client-side, Session Storage)
│ - version               │
│ - players[]             │
│   - life, element, etc. │
└─────────────────────────┘
            │
            │ (User submits report)
            ↓
┌─────────────────────────┐
│ MatchConfirmation       │ (Database, match_confirmations table)
│ - submitter_discord_id  │
│ - opponent_discord_id   │
│ - status: pending       │
│ - final_life_winner     │ ← Copied from LifeCounterState
│ - final_life_loser      │ ← Copied from LifeCounterState
└─────────────────────────┘
            │
            │ (Opponent confirms OR 24h timeout)
            ↓
┌─────────────────────────┐
│ MatchRecord             │ (Database, match_records table)
│ - winner_id             │ ← From MatchConfirmation.winner_discord_id
│ - loser_id              │ ← From MatchConfirmation.loser_discord_id
│ - submitted_via_life_   │ ← Set to 1 (true)
│   counter               │
│ - final_player1_life    │ ← From MatchConfirmation
│ - final_player2_life    │ ← From MatchConfirmation
└─────────────────────────┘
            │
            │ (Triggers ELO update)
            ↓
┌─────────────────────────┐
│ ELO Ratings             │ (Database, elo.db table - existing)
│ - Updated via existing  │
│   ELO service           │
└─────────────────────────┘
```

**Flow Summary**:
1. User tracks game with `LifeCounterState` (client-side)
2. When life → 0, user submits report → creates `MatchConfirmation` (pending)
3. Opponent receives notification → confirms → status becomes 'confirmed'
4. System creates `MatchRecord` with life counter metadata
5. Existing ELO service updates player ratings

---

## Validation & Constraints Summary

| Entity | Key Constraints | Validation Rules |
|--------|-----------------|------------------|
| LifeCounterState | Session-only, ~500 bytes | Life: any integer; Element: enum or null; Counters: ≥0 |
| MatchConfirmation | Unique pending per player pair within 1h | Status: enum; Expires ≥ Created; Winner ≠ Loser |
| MatchRecord | Extended existing schema | New fields nullable for backward compat; At least one player life ≤0 |

---

## Database Migration Script

**File**: `web-app/migrations/001_add_life_counter_support.sql`

```sql
-- Migration: Add Life Counter Support
-- Date: 2026-03-09
-- Description: Create match_confirmations table and extend match_records

-- 1. Create match_confirmations table
CREATE TABLE IF NOT EXISTS match_confirmations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_report_id INTEGER,
    submitter_discord_id INTEGER NOT NULL,
    opponent_discord_id INTEGER NOT NULL,
    winner_discord_id INTEGER NOT NULL,
    loser_discord_id INTEGER NOT NULL,
    winner_deck_url TEXT,
    loser_deck_url TEXT,
    final_life_winner INTEGER NOT NULL,
    final_life_loser INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at INTEGER NOT NULL,
    confirmed_at INTEGER,
    expires_at INTEGER NOT NULL,
    dispute_reason TEXT,
    FOREIGN KEY (match_report_id) REFERENCES match_records(id) ON DELETE SET NULL
);

-- 2. Create indexes
CREATE INDEX IF NOT EXISTS idx_match_confirmations_opponent ON match_confirmations(opponent_discord_id, status);
CREATE INDEX IF NOT EXISTS idx_match_confirmations_expires ON match_confirmations(expires_at, status);
CREATE INDEX IF NOT EXISTS idx_match_confirmations_status ON match_confirmations(status);

-- 3. Extend match_records table (check if columns exist first)
-- Note: SQLite doesn't support "IF NOT EXISTS" for columns, so check in application code before running

ALTER TABLE match_records ADD COLUMN submitted_via_life_counter INTEGER DEFAULT 0;
ALTER TABLE match_records ADD COLUMN final_player1_life INTEGER;
ALTER TABLE match_records ADD COLUMN final_player2_life INTEGER;

-- 4. Verify schema
PRAGMA table_info(match_confirmations);
PRAGMA table_info(match_records);
```

**Rollback Script** (if needed):

```sql
-- Rollback: Remove Life Counter Support
DROP TABLE IF EXISTS match_confirmations;

-- Note: SQLite doesn't support DROP COLUMN directly
-- To remove columns from match_records, must recreate table
-- (Not recommended for production - leave columns for backward compatibility)
```

---

## Next Steps

- ✅ Data model defined with 3 entities (1 client-side, 2 database)
- ⬜ Define API contracts in `contracts/` directory
- ⬜ Create quickstart guide in `quickstart.md`
- ⬜ Generate implementation tasks via `/speckit.tasks`
