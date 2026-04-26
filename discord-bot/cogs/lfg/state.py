"""Shared mutable state for the LFG system.

All module-level state is centralized here so it can be imported
by any submodule without circular dependencies.
"""

import asyncio

# In-memory LFG queue
# user_id: {timestamp, timeframe, deck_url, queue_type, ladder_info (optional), run_id (limited only)}
# queue_type: "ranked", "testing", "both", or "limited"
# ladder_info: dict with {challenger_id, challenge_id, elo_multiplier_winner, elo_multiplier_loser, guild_id}
# run_id: int - active arena run ID (only present for queue_type="limited")
lfg_queue = {}

# Lock to prevent race conditions when accessing the queue
lfg_queue_lock = asyncio.Lock()

# Lock to prevent concurrent update_lfg_status calls (avoids duplicate messages)
lfg_status_lock = asyncio.Lock()

# Track pending match reports awaiting confirmation
# Key: (reporter_id, opponent_id), Value: match report data
pending_match_reports = {}

# Track processed matches to prevent double reporting
# Key: frozenset({player1_id, player2_id}), Value: timestamp
processed_matches = {}

# Lock to prevent race conditions when checking/recording processed matches
processed_matches_lock = asyncio.Lock()

# Store the persistent status message ID
lfg_status_message_id = None

# Store the leaderboard message ID
leaderboard_message_id = None

# In-memory ladder challenge queues
# Key: challenger_id, Value: {challenger_global, joiners: [...], message, channel, challenge_id, task}
active_ladder_challenges = {}

# Lock for ladder challenge operations
ladder_challenge_lock = asyncio.Lock()

LADDER_CHALLENGE_MAX_JOINERS = 3
LADDER_CHALLENGE_TIMEOUT_SECONDS = 300  # 5 minutes
