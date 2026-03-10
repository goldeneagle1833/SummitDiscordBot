-- Initial Table Creation: match_confirmations
-- Date: 2026-03-10
-- Feature: 001-web-match-report-modal
-- Database: match_records.db
--
-- This script creates the match_confirmations table from scratch.
-- Run this BEFORE migration.sql (which adds additional columns/indexes).

BEGIN TRANSACTION;

-- Create match_confirmations table
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
    went_first TEXT CHECK(went_first IN ('submitter', 'opponent')),  -- Turn order
    final_life_winner INTEGER NOT NULL,      -- Winner's final life total
    final_life_loser INTEGER NOT NULL,       -- Loser's final life total

    -- Status tracking
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'confirmed', 'disputed', 'expired', 'auto_confirmed')),
    created_at INTEGER NOT NULL,             -- Unix timestamp (report submitted)
    expires_at INTEGER NOT NULL,             -- Unix timestamp (48hr after created_at)
    reminder_sent_at INTEGER,                -- Unix timestamp (24hr reminder sent)
    confirmed_at INTEGER,                    -- Unix timestamp (when opponent confirmed/denied)
    dispute_reason TEXT,                     -- Optional reason if disputed

    -- Constraints
    CHECK(submitter_discord_id != opponent_discord_id),  -- Can't report against self
    CHECK(winner_discord_id IN (submitter_discord_id, opponent_discord_id)),  -- Winner must be a player
    CHECK(loser_discord_id IN (submitter_discord_id, opponent_discord_id)),   -- Loser must be a player
    CHECK(winner_discord_id != loser_discord_id)  -- Winner != Loser
);

-- Create indexes for query performance
CREATE INDEX IF NOT EXISTS idx_opponent_pending
    ON match_confirmations(opponent_discord_id, status, expires_at)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_status_created
    ON match_confirmations(status, created_at);

CREATE INDEX IF NOT EXISTS idx_expires_reminder
    ON match_confirmations(expires_at, reminder_sent_at)
    WHERE status = 'pending' AND reminder_sent_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_submitter_recent
    ON match_confirmations(submitter_discord_id, created_at DESC);

-- Verify table creation
SELECT 'match_confirmations table created successfully' as status;

PRAGMA table_info(match_confirmations);

COMMIT;
