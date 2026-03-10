-- Migration: Add turn order and reminder tracking to match_confirmations
-- Date: 2026-03-10
-- Feature: 001-web-match-report-modal
--
-- This migration extends the existing match_confirmations table with:
-- 1. went_first column (TEXT): Turn order relative to submitter ('submitter'|'opponent')
-- 2. reminder_sent_at column (INTEGER): Unix timestamp when 24hr reminder was sent
-- 3. Three new indexes for query performance optimization
--
-- IMPORTANT: This migration is ADDITIVE ONLY (no data loss)
-- - New columns are nullable (won't break existing rows)
-- - Indexes improve performance for pending/reminder/expiration queries
-- - Rollback: Can drop indexes, but SQLite doesn't support DROP COLUMN

BEGIN TRANSACTION;

-- ============================================================================
-- Step 1: Add new columns to match_confirmations table
-- ============================================================================

-- Add went_first column: Tracks turn order relative to submitter
-- Values: 'submitter' (submitter went first), 'opponent' (opponent went first), NULL (not specified)
-- Required for User Stories 1 & 2 (match report submission)
ALTER TABLE match_confirmations ADD COLUMN went_first TEXT;

-- Add reminder_sent_at column: Tracks when 24-hour reminder notification was sent
-- Value: Unix timestamp (seconds since epoch), NULL if reminder not yet sent
-- Required for Phase 5 (background reminder job)
ALTER TABLE match_confirmations ADD COLUMN reminder_sent_at INTEGER;

-- ============================================================================
-- Step 2: Create indexes for query performance
-- ============================================================================

-- Index 1: idx_opponent_pending
-- Purpose: Optimize GET /api/match-report/pending (User Story 3)
-- Query: SELECT * FROM match_confirmations WHERE opponent_discord_id = ? AND status = 'pending' AND expires_at > ?
-- Benefit: Speeds up pending confirmation lookups by 10-100x
CREATE INDEX IF NOT EXISTS idx_opponent_pending
    ON match_confirmations(opponent_discord_id, status, expires_at)
    WHERE status = 'pending';

-- Index 2: idx_expires_reminder
-- Purpose: Optimize background job queries for 24hr reminders (Phase 5)
-- Query: SELECT * FROM match_confirmations WHERE status = 'pending' AND reminder_sent_at IS NULL AND created_at < (now() - 24hr)
-- Benefit: Speeds up reminder job execution, prevents full table scans
CREATE INDEX IF NOT EXISTS idx_expires_reminder
    ON match_confirmations(expires_at, reminder_sent_at)
    WHERE status = 'pending' AND reminder_sent_at IS NULL;

-- Index 3: idx_submitter_recent
-- Purpose: Optimize recent opponent lookup for autocomplete (User Story 1)
-- Query: SELECT * FROM match_confirmations WHERE submitter_discord_id = ? ORDER BY created_at DESC
-- Benefit: Speeds up opponent search suggestions based on recent matches
CREATE INDEX IF NOT EXISTS idx_submitter_recent
    ON match_confirmations(submitter_discord_id, created_at DESC);

-- ============================================================================
-- Step 3: Verify data integrity (validation checks)
-- ============================================================================

-- Check 1: Ensure no existing rows violate self-reporting constraint
-- Expected: 0 rows (no user reported match against themselves)
SELECT
    COUNT(*) as invalid_self_reports
FROM match_confirmations
WHERE submitter_discord_id = opponent_discord_id;
-- If count > 0: Data integrity issue exists (should be investigated before proceeding)

-- Check 2: Ensure winner/loser are always one of the two players
-- Expected: 0 rows (winner and loser must be submitter or opponent)
SELECT
    COUNT(*) as invalid_winner_loser
FROM match_confirmations
WHERE winner_discord_id NOT IN (submitter_discord_id, opponent_discord_id)
   OR loser_discord_id NOT IN (submitter_discord_id, opponent_discord_id);
-- If count > 0: Data integrity issue exists

-- Check 3: Ensure winner != loser
-- Expected: 0 rows (winner and loser must be different)
SELECT
    COUNT(*) as invalid_same_winner_loser
FROM match_confirmations
WHERE winner_discord_id = loser_discord_id;
-- If count > 0: Data integrity issue exists

-- ============================================================================
-- Step 4: Update expiration time for existing pending reports (OPTIONAL)
-- ============================================================================

-- NOTE: This step is OPTIONAL and only needed if you want to extend expiration
-- for existing pending reports from 24hr to 48hr (as per new spec)
--
-- WARNING: Uncommenting this will change expires_at for all pending reports!
-- Consider the impact on users who are expecting reports to expire sooner.
--
-- UPDATE match_confirmations
-- SET expires_at = created_at + (48 * 3600)  -- 48 hours in seconds
-- WHERE status = 'pending'
--   AND expires_at = created_at + (24 * 3600);  -- Only update 24hr expirations

-- ============================================================================
-- Step 5: Verify migration success
-- ============================================================================

-- Check that new columns exist
-- Run this query and verify both columns appear in the result:
PRAGMA table_info(match_confirmations);
-- Expected columns should include: went_first (TEXT), reminder_sent_at (INTEGER)

-- Check that indexes were created
-- Run this query and verify all 3 indexes appear:
SELECT name, sql FROM sqlite_master
WHERE type = 'index'
  AND tbl_name = 'match_confirmations'
  AND name IN ('idx_opponent_pending', 'idx_expires_reminder', 'idx_submitter_recent');
-- Expected: 3 rows returned

COMMIT;

-- ============================================================================
-- Rollback script (if needed)
-- ============================================================================
--
-- WARNING: SQLite does NOT support DROP COLUMN, so columns will remain
-- even after "rollback". They will just be unused (NULL values).
--
-- To rollback this migration (remove indexes only):
-- BEGIN TRANSACTION;
-- DROP INDEX IF EXISTS idx_opponent_pending;
-- DROP INDEX IF EXISTS idx_expires_reminder;
-- DROP INDEX IF EXISTS idx_submitter_recent;
-- COMMIT;
--
-- Note: New columns (went_first, reminder_sent_at) cannot be removed in SQLite.
-- They are nullable and will not affect existing functionality if left unused.

-- ============================================================================
-- Post-migration notes
-- ============================================================================
--
-- 1. The application code in repositories/match_confirmation.py must be updated
--    to use the new went_first column when creating confirmations.
--
-- 2. The expiration logic in repositories/match_confirmation.py should be updated
--    from 24hr to 48hr (code change, not database change):
--    OLD: expires_at = created_at + (24 * 60 * 60)
--    NEW: expires_at = created_at + (48 * 60 * 60)
--
-- 3. Background jobs (Phase 5) will use reminder_sent_at to track 24hr reminders.
--    The job should:
--    - Query for pending reports where reminder_sent_at IS NULL AND created_at < (now - 24hr)
--    - Send reminder notification
--    - UPDATE reminder_sent_at = now()
--
-- 4. Monitor query performance after migration using EXPLAIN QUERY PLAN:
--    EXPLAIN QUERY PLAN SELECT * FROM match_confirmations WHERE opponent_discord_id = ? AND status = 'pending';
--    Should show "USING INDEX idx_opponent_pending"
