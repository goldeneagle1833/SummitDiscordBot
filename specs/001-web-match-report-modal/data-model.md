# Data Model: Web-Based Match Reporting Modal

**Feature**: 001-web-match-report-modal
**Date**: 2026-03-10
**Database**: `match_records.db` (SQLite)

## Overview

This feature extends the existing `match_confirmations` table and leverages the `user_profiles` table for opponent search. The data model supports a two-phase match reporting flow: (1) user submits report, (2) opponent confirms or denies.

## Entity Relationship Diagram

```
┌─────────────────────┐         ┌──────────────────────┐
│   user_profiles     │         │ match_confirmations  │
├─────────────────────┤         ├──────────────────────┤
│ PK user_id (TEXT)   │◄────────│ submitter_discord_id │
│ PK provider (TEXT)  │    │    │ opponent_discord_id  │────┐
│    display_name     │    │    │ winner_discord_id    │    │
│    avatar           │    │    │ loser_discord_id     │    │
│    first_login_at   │    │    │ winner_deck_url      │    │
│    last_login_at    │    │    │ loser_deck_url       │    │
│    ...              │    │    │ went_first           │◄───┤
└─────────────────────┘    │    │ final_life_winner    │    │
                           │    │ final_life_loser     │    │
                           │    │ status               │    │
                           └────│ created_at           │    │
                                │ expires_at           │    │
                                │ reminder_sent_at     │ NEW│
                                │ confirmed_at         │    │
                                │ dispute_reason       │    │
                                └──────────────────────┘    │
                                          │                  │
                                          ▼                  │
                                ┌──────────────────┐         │
                                │  match_records   │◄────────┘
                                ├──────────────────┤
                                │ id               │
                                │ winner_id        │
                                │ loser_id         │
                                │ timestamp        │
                                │ ...              │
                                └──────────────────┘
                                (created when confirmed)
```

## Table Schemas

### 1. `match_confirmations` (Extended)

**Purpose**: Stores pending and processed match reports awaiting opponent confirmation.

**Schema**:
```sql
CREATE TABLE IF NOT EXISTS match_confirmations (
    -- Primary Key
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Players involved
    submitter_discord_id TEXT NOT NULL,      -- User who submitted the report
    opponent_discord_id TEXT NOT NULL,       -- User who must confirm/deny
    winner_discord_id TEXT NOT NULL,         -- Winner's Discord user ID
    loser_discord_id TEXT NOT NULL,          -- Loser's Discord user ID

    -- Match details
    winner_deck_url TEXT,                    -- Curiosa.io deck URL for winner
    loser_deck_url TEXT,                     -- Curiosa.io deck URL for loser
    went_first TEXT CHECK(went_first IN ('submitter', 'opponent')),  -- NEW: Turn order
    final_life_winner INTEGER NOT NULL,      -- Winner's final life total
    final_life_loser INTEGER NOT NULL,       -- Loser's final life total

    -- Status tracking
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'confirmed', 'disputed', 'expired', 'auto_confirmed')),
    created_at INTEGER NOT NULL,             -- Unix timestamp (report submitted)
    expires_at INTEGER NOT NULL,             -- Unix timestamp (48hr after created_at)
    reminder_sent_at INTEGER,                -- NEW: Unix timestamp (24hr reminder sent)
    confirmed_at INTEGER,                    -- Unix timestamp (when opponent confirmed/denied)
    dispute_reason TEXT,                     -- Optional reason if disputed

    -- Constraints
    CHECK(submitter_discord_id != opponent_discord_id),  -- Can't report against self
    CHECK(winner_discord_id IN (submitter_discord_id, opponent_discord_id)),  -- Winner must be a player
    CHECK(loser_discord_id IN (submitter_discord_id, opponent_discord_id)),   -- Loser must be a player
    CHECK(winner_discord_id != loser_discord_id)  -- Winner != Loser
);

-- Indexes for query performance
CREATE INDEX IF NOT EXISTS idx_opponent_pending ON match_confirmations(opponent_discord_id, status, expires_at)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_status_created ON match_confirmations(status, created_at);

CREATE INDEX IF NOT EXISTS idx_expires_reminder ON match_confirmations(expires_at, reminder_sent_at)
    WHERE status = 'pending' AND reminder_sent_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_submitter_recent ON match_confirmations(submitter_discord_id, created_at DESC);
```

**Status Values**:
- `pending`: Awaiting opponent confirmation/denial (initial state)
- `confirmed`: Opponent confirmed the report → match finalized, ELO updated
- `disputed`: Opponent denied the report → no match record created
- `expired`: 48 hours elapsed with no response → marked void, no ELO changes
- `auto_confirmed`: System auto-confirmed after expiration (future feature, not in current spec)

**Field Details**:

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `id` | INTEGER | NO | Auto-increment primary key |
| `submitter_discord_id` | TEXT | NO | Discord user ID of report creator |
| `opponent_discord_id` | TEXT | NO | Discord user ID who must confirm |
| `winner_discord_id` | TEXT | NO | Winner's Discord ID (submitter or opponent) |
| `loser_discord_id` | TEXT | NO | Loser's Discord ID (submitter or opponent) |
| `winner_deck_url` | TEXT | YES | Curiosa.io deck URL for winner (optional) |
| `loser_deck_url` | TEXT | YES | Curiosa.io deck URL for loser (optional) |
| `went_first` | TEXT | NO | **NEW**: Turn order relative to submitter ('submitter' \| 'opponent') |
| `final_life_winner` | INTEGER | NO | Winner's final life total (for tracking) |
| `final_life_loser` | INTEGER | NO | Loser's final life total (for tracking) |
| `status` | TEXT | NO | Current state (see Status Values above) |
| `created_at` | INTEGER | NO | Unix timestamp when report submitted |
| `expires_at` | INTEGER | NO | Unix timestamp when report expires (created_at + 48hr) |
| `reminder_sent_at` | INTEGER | YES | **NEW**: Unix timestamp when 24hr reminder sent (NULL if not sent) |
| `confirmed_at` | INTEGER | YES | Unix timestamp when opponent took action |
| `dispute_reason` | TEXT | YES | Optional text if status='disputed' |

---

### 2. `user_profiles` (Existing, No Changes)

**Purpose**: Stores user profile information from OAuth providers for opponent search and display.

**Schema** (reference only, not modified):
```sql
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'discord',
    display_name TEXT NOT NULL,              -- Used for autocomplete search
    avatar TEXT,
    email TEXT,
    email_verified INTEGER,
    first_login_at TEXT NOT NULL,
    last_login_at TEXT NOT NULL,
    discriminator TEXT,                      -- Discord-specific
    flags INTEGER,
    public_flags INTEGER,
    given_name TEXT,                         -- Google-specific
    family_name TEXT,
    locale TEXT,
    raw_oauth_data TEXT,
    PRIMARY KEY (user_id, provider)
);
```

**Usage in This Feature**:
- Opponent autocomplete searches `display_name` field
- Recent opponent lookup joins with `match_records` table
- Avatar displayed in search results

---

### 3. `match_records` (Existing, No Changes)

**Purpose**: Final match records created when `match_confirmations.status = 'confirmed'`.

**Schema** (reference only, not modified):
```sql
CREATE TABLE IF NOT EXISTS match_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    winner_id TEXT NOT NULL,
    loser_id TEXT NOT NULL,
    winner_deck_url TEXT,
    loser_deck_url TEXT,
    timestamp INTEGER NOT NULL,
    -- ... other fields (elo_before, elo_after, event_id, etc.)
);
```

**Creation Trigger**:
- When `match_confirmations.status` changes from 'pending' → 'confirmed', a new `match_records` row is inserted
- ELO ratings are calculated and updated atomically in the same transaction

---

## Data Flow & State Transitions

### State Diagram: Match Confirmation Lifecycle

```
                    [User Submits Report]
                            │
                            ▼
                    ┌───────────────┐
                    │   PENDING     │
                    │ (created_at)  │
                    └───────┬───────┘
                            │
            ┌───────────────┼───────────────┐
            │               │               │
            ▼               ▼               ▼
    [24hr elapsed]  [Opponent Action] [48hr elapsed]
            │               │               │
            ▼               │               ▼
    ┌──────────────┐        │       ┌──────────────┐
    │Send Reminder │        │       │   EXPIRED    │
    │reminder_sent │        │       │ (expires_at) │
    │   _at set    │        │       └──────────────┘
    └──────────────┘        │               │
                            │               ▼
                    ┌───────┴───────┐   [Notify Both]
                    │               │   [No ELO Change]
                    ▼               ▼
            ┌─────────────┐ ┌─────────────┐
            │  CONFIRMED  │ │  DISPUTED   │
            │(confirmed_at│ │(confirmed_at│
            └──────┬──────┘ └─────────────┘
                   │                │
                   ▼                ▼
         [Create match_record] [No match_record]
         [Update ELO]          [Notify Both]
         [Notify Both]
```

### Data Flow Sequence

**1. User Submits Match Report** (POST /api/match-report/submit)
```
Input: {
  opponent_user_id: "123456789",
  result: "won" | "lost",
  went_first: "submitter" | "opponent",
  submitter_deck_url: "https://curiosa.io/decks/abc",
  opponent_deck_url: "https://curiosa.io/decks/xyz",
  final_life_submitter: 20,
  final_life_opponent: 0
}

→ Validate inputs (opponent exists, URLs valid, etc.)
→ Check for duplicate pending reports (within 1 hour)
→ Calculate winner/loser based on result
→ INSERT INTO match_confirmations (
    submitter_discord_id = current_user_id,
    opponent_discord_id = opponent_user_id,
    winner_discord_id = (submitter if result='won' else opponent),
    loser_discord_id = (opponent if result='won' else submitter),
    went_first = went_first,
    winner_deck_url = (submitter_deck_url if won else opponent_deck_url),
    loser_deck_url = (opponent_deck_url if won else submitter_deck_url),
    final_life_winner = (submitter_life if won else opponent_life),
    final_life_loser = (opponent_life if won else submitter_life),
    status = 'pending',
    created_at = now(),
    expires_at = now() + (48 * 3600)
  )

Output: {
  success: true,
  confirmation_id: 42,
  expires_at: 1234567890,
  awaiting_confirmation_from: "OpponentName"
}
```

**2. Background Job: 24-Hour Reminder** (Every 5 minutes)
```
→ SELECT * FROM match_confirmations
  WHERE status = 'pending'
    AND reminder_sent_at IS NULL
    AND created_at < (now() - 24hr)
    AND expires_at > now()

For each record:
  → Send notification to opponent_discord_id
  → UPDATE match_confirmations SET reminder_sent_at = now() WHERE id = ?
```

**3. Opponent Confirms Report** (POST /api/match-report/confirm/{id})
```
Input: { confirmation_id: 42 }

→ SELECT * FROM match_confirmations WHERE id = 42 AND opponent_discord_id = current_user_id
→ Verify status = 'pending' and not expired
→ BEGIN TRANSACTION
  → UPDATE match_confirmations SET status = 'confirmed', confirmed_at = now()
  → INSERT INTO match_records (winner_id, loser_id, ...) VALUES (...)
  → UPDATE elo ratings (call existing ELO service)
  → COMMIT
→ Notify both players (submitter + opponent)

Output: {
  success: true,
  match_id: 123,
  elo_changes: { winner: {old: 1500, new: 1516}, loser: {old: 1450, new: 1434} }
}
```

**4. Opponent Denies Report** (POST /api/match-report/deny/{id})
```
Input: { confirmation_id: 42, reason: "Wrong result" }

→ SELECT * FROM match_confirmations WHERE id = 42 AND opponent_discord_id = current_user_id
→ Verify status = 'pending'
→ UPDATE match_confirmations SET status = 'disputed', confirmed_at = now(), dispute_reason = ?
→ Notify both players

Output: {
  success: true,
  message: "Match report denied"
}
```

**5. Background Job: 48-Hour Expiration** (Every 15 minutes)
```
→ SELECT * FROM match_confirmations
  WHERE status = 'pending'
    AND expires_at <= now()

For each record:
  → UPDATE match_confirmations SET status = 'expired', confirmed_at = now()
  → Notify both players (submitter + opponent)
```

---

## Validation Rules

### Business Logic Constraints

1. **Duplicate Prevention**:
   ```sql
   -- Check: No pending confirmation between same players within 1 hour
   SELECT COUNT(*) FROM match_confirmations
   WHERE (submitter_discord_id = ? AND opponent_discord_id = ?)
      OR (submitter_discord_id = ? AND opponent_discord_id = ?)
   AND status = 'pending'
   AND created_at > (now() - 3600)
   ```

2. **Self-Reporting Prevention**:
   ```python
   if submitter_discord_id == opponent_discord_id:
       raise ValueError("Cannot report match against yourself")
   ```

3. **Turn Order Validation**:
   ```python
   if went_first not in ('submitter', 'opponent'):
       raise ValueError("went_first must be 'submitter' or 'opponent'")
   ```

4. **Deck URL Format**:
   ```python
   import re
   deck_url_pattern = r'^https?://(www\.)?curiosa\.io/decks/[a-zA-Z0-9_-]+$'
   if deck_url and not re.match(deck_url_pattern, deck_url):
       raise ValueError("Invalid Curiosa.io deck URL format")
   ```

5. **Life Total Validation**:
   ```python
   if not (0 <= final_life_winner <= 99 and 0 <= final_life_loser <= 99):
       raise ValueError("Life totals must be between 0 and 99")
   ```

6. **Authorization**:
   ```python
   # Only opponent can confirm/deny
   if current_user_id != confirmation.opponent_discord_id:
       raise PermissionError("Only the opponent can confirm this report")

   # Only submitter can create report
   if current_user_id != submitter_discord_id:
       raise PermissionError("Cannot submit report as another user")
   ```

---

## Query Patterns

### Common Queries with Indexes

**1. Get Pending Confirmations for User**:
```sql
-- Uses: idx_opponent_pending
SELECT * FROM match_confirmations
WHERE opponent_discord_id = ?
  AND status = 'pending'
  AND expires_at > ?
ORDER BY created_at DESC;
```

**2. Find Reports Needing 24hr Reminder**:
```sql
-- Uses: idx_expires_reminder
SELECT * FROM match_confirmations
WHERE status = 'pending'
  AND reminder_sent_at IS NULL
  AND created_at < (? - 86400)  -- 24 hours ago
  AND expires_at > ?
LIMIT 100;
```

**3. Find Expired Reports**:
```sql
-- Uses: idx_opponent_pending
SELECT * FROM match_confirmations
WHERE status = 'pending'
  AND expires_at <= ?
LIMIT 100;
```

**4. Get Recent Opponents for Autocomplete**:
```sql
-- Uses: match_records indexes (existing)
SELECT
    CASE
        WHEN winner_id = ? THEN loser_id
        ELSE winner_id
    END as opponent_id,
    MAX(timestamp) as last_matched_at,
    COUNT(*) as match_count
FROM match_records
WHERE winner_id = ? OR loser_id = ?
GROUP BY opponent_id
ORDER BY last_matched_at DESC
LIMIT 10;
```

**5. Search User Profiles by Display Name**:
```sql
-- Requires: CREATE INDEX idx_display_name ON user_profiles(display_name);
SELECT user_id, display_name, avatar
FROM user_profiles
WHERE LOWER(display_name) LIKE LOWER(? || '%')
  AND provider = 'discord'
LIMIT 10;
```

---

## Migration Script

### `add_match_confirmation_fields.sql`

```sql
-- Migration: Add turn order and reminder tracking to match_confirmations
-- Date: 2026-03-10
-- Feature: 001-web-match-report-modal

BEGIN TRANSACTION;

-- Add new columns
ALTER TABLE match_confirmations ADD COLUMN went_first TEXT;
ALTER TABLE match_confirmations ADD COLUMN reminder_sent_at INTEGER;

-- Add constraint (SQLite doesn't support ALTER TABLE ADD CONSTRAINT, so we verify at app level)
-- CHECK(went_first IN ('submitter', 'opponent')) -- Enforced in application code

-- Create new indexes
CREATE INDEX IF NOT EXISTS idx_opponent_pending
    ON match_confirmations(opponent_discord_id, status, expires_at)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_expires_reminder
    ON match_confirmations(expires_at, reminder_sent_at)
    WHERE status = 'pending' AND reminder_sent_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_submitter_recent
    ON match_confirmations(submitter_discord_id, created_at DESC);

-- Add 'expired' status to existing status values (data migration not needed, no rows exist yet)

-- Verify existing constraints still valid
SELECT
    COUNT(*) as invalid_rows
FROM match_confirmations
WHERE submitter_discord_id = opponent_discord_id
   OR winner_discord_id NOT IN (submitter_discord_id, opponent_discord_id)
   OR loser_discord_id NOT IN (submitter_discord_id, opponent_discord_id)
   OR winner_discord_id = loser_discord_id;
-- Expected: 0 rows (if >0, data integrity issue exists)

COMMIT;

-- Rollback script (if needed):
-- BEGIN TRANSACTION;
-- DROP INDEX IF EXISTS idx_opponent_pending;
-- DROP INDEX IF EXISTS idx_expires_reminder;
-- DROP INDEX IF EXISTS idx_submitter_recent;
-- -- Note: SQLite doesn't support DROP COLUMN, so columns would remain but unused
-- COMMIT;
```

---

## Testing Data Fixtures

### Sample Data for Tests

**Scenario 1: Pending Confirmation (Happy Path)**
```python
{
    "id": 1,
    "submitter_discord_id": "100000001",
    "opponent_discord_id": "100000002",
    "winner_discord_id": "100000001",
    "loser_discord_id": "100000002",
    "winner_deck_url": "https://curiosa.io/decks/test-winner",
    "loser_deck_url": "https://curiosa.io/decks/test-loser",
    "went_first": "submitter",
    "final_life_winner": 15,
    "final_life_loser": 0,
    "status": "pending",
    "created_at": int(time.time()) - 3600,  # 1 hour ago
    "expires_at": int(time.time()) + 169200,  # 47 hours from now
    "reminder_sent_at": None,
    "confirmed_at": None,
    "dispute_reason": None
}
```

**Scenario 2: Needs Reminder**
```python
{
    "id": 2,
    "status": "pending",
    "created_at": int(time.time()) - 86400,  # 24 hours ago
    "expires_at": int(time.time()) + 86400,  # 24 hours from now
    "reminder_sent_at": None,
    # ... rest of fields
}
```

**Scenario 3: Expired Report**
```python
{
    "id": 3,
    "status": "pending",
    "created_at": int(time.time()) - 172800,  # 48 hours ago
    "expires_at": int(time.time()) - 3600,  # 1 hour ago (expired)
    "reminder_sent_at": int(time.time()) - 86400,  # Reminder was sent
    # ... rest of fields
}
```

---

## Data Retention & Cleanup

**Policy**:
- **Pending reports**: Automatically transitioned to 'expired' after 48 hours
- **Confirmed reports**: Retained indefinitely (match history)
- **Disputed reports**: Retained for 90 days, then archived/deleted
- **Expired reports**: Retained for 30 days, then archived/deleted

**Cleanup Job** (optional, run monthly):
```sql
-- Archive old disputed/expired reports (>90 days)
DELETE FROM match_confirmations
WHERE status IN ('disputed', 'expired')
  AND confirmed_at < (strftime('%s', 'now') - 7776000);  -- 90 days in seconds
```

---

## Next Steps

- Proceed to defining API contracts in `contracts/` directory
- Create implementation tasks in `tasks.md`
- Write database migration script
