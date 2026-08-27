"""Idempotent Sorcery Online result delivery into Summit's match pipeline."""

import asyncio
import datetime
import json
import logging
import sqlite3

from cogs.lfg.persistent_confirm import (
    _execute_match_confirmation,
    load_match_card_for_pairing,
)
from cogs.lfg.state import processed_matches, processed_matches_lock
from repositories.elo_repo import get_pairing_by_id, mark_pairing_reported
from repositories.limited_repo import (
    get_limited_pairing_by_id,
    mark_limited_pairing_reported,
)

import config


logger = logging.getLogger("discord_bot")

_result_lock = asyncio.Lock()
_VALID_OUTCOMES = {"decided", "no_contest", "conflict", "unknown"}

# Path to the match_records database (same one elo_repo uses for pairings)
_MATCH_RECORDS_DB = None


def _get_match_records_db():
    global _MATCH_RECORDS_DB
    if _MATCH_RECORDS_DB is None:
        import os
        _MATCH_RECORDS_DB = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "match_records.db"
        )
    return _MATCH_RECORDS_DB


def _ensure_callback_table():
    db_path = _get_match_records_db()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sorcery_online_match_callbacks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                pairing_id INTEGER NOT NULL,
                queue_type TEXT NOT NULL,
                outcome TEXT NOT NULL,
                reporter_id INTEGER,
                winner_id INTEGER,
                loser_id INTEGER,
                match_id INTEGER,
                played_cards TEXT,
                raw_players TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    finally:
        conn.close()


def _save_callback(guild_id, pairing_id, queue_type, outcome,
                   reporter_id, winner_id, loser_id, match_id,
                   played_cards, raw_players):
    _ensure_callback_table()
    db_path = _get_match_records_db()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """INSERT INTO sorcery_online_match_callbacks
               (guild_id, pairing_id, queue_type, outcome,
                reporter_id, winner_id, loser_id, match_id,
                played_cards, raw_players)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                guild_id, pairing_id, queue_type, outcome,
                reporter_id, winner_id, loser_id, match_id,
                json.dumps(played_cards) if played_cards else None,
                json.dumps(raw_players) if raw_players else None,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _normalize_played_cards(players):
    """Extract played card names from SO player data.

    Returns a dict mapping discord_id -> list of card names, or None.
    """
    if not players:
        return None
    result = {}
    for p in players:
        discord_id = p.get("discordId") or p.get("discord_id")
        cards = p.get("playedCards") or p.get("played_cards") or []
        if discord_id and cards:
            names = []
            for c in cards:
                if isinstance(c, str):
                    names.append(c)
                elif isinstance(c, dict):
                    names.append(c.get("name") or c.get("card_name") or str(c))
            result[str(discord_id)] = names
    return result or None


class ApiFollowup:
    async def send(self, *_args, **_kwargs):
        return None


class ApiInteraction:
    def __init__(self, bot):
        self.client = bot
        self.followup = ApiFollowup()


def _minutes_since(created_at):
    try:
        started = datetime.datetime.fromisoformat(created_at)
        return max(0, int((datetime.datetime.now() - started).total_seconds() / 60))
    except (TypeError, ValueError):
        return 0


async def _display_name(bot, user_id):
    try:
        user = await bot.fetch_user(user_id)
        return user.global_name or user.display_name
    except Exception:
        return str(user_id)


async def record_sorcery_online_result(
    bot,
    *,
    guild_id,
    pairing_id,
    queue_type,
    outcome="decided",
    reporter_id=None,
    winner_id=None,
    loser_id=None,
    players=None,
):
    """Record one authoritative pairing result, returning duplicate success on retries."""
    async with _result_lock:
        is_limited = queue_type == "limited"
        pairing = (
            get_limited_pairing_by_id(guild_id, pairing_id)
            if is_limited
            else get_pairing_by_id(guild_id, pairing_id)
        )
        if not pairing:
            raise LookupError("Pairing not found")
        stored_type = "limited" if is_limited else pairing.get("match_type") or "ranked"
        if stored_type != queue_type:
            raise ValueError("Queue type does not match this pairing")
        if outcome not in _VALID_OUTCOMES:
            raise ValueError("Invalid Sorcery Online outcome")

        played_cards = _normalize_played_cards(players)

        # --- Non-decided outcomes (no_contest, unknown, conflict) ---
        if outcome != "decided":
            logger.info(
                "SO callback outcome=%s for pairing %s (guild %s, type %s)",
                outcome, pairing_id, guild_id, queue_type,
            )
            # Only close the pairing for no_contest (both players agreed no game).
            # Leave unknown/conflict pairings active so players can still report
            # via the Discord Report button or a later decided callback.
            if outcome == "no_contest":
                p1 = int(pairing["player1_id"])
                p2 = int(pairing["player2_id"])
                mark_reported = (
                    mark_limited_pairing_reported if is_limited else mark_pairing_reported
                )
                mark_reported(int(guild_id), p1, p2, pairing_id=int(pairing_id))

            _save_callback(
                guild_id, pairing_id, queue_type, outcome,
                reporter_id, winner_id, loser_id, None,
                played_cards, players,
            )
            return {"recorded": False, "duplicate": False, "match_id": None, "outcome": outcome}

        # --- Decided outcome: record the match ---
        if not reporter_id or not winner_id or not loser_id:
            raise ValueError("decided outcome requires reporter_id, winner_id, and loser_id")

        reporter_id = int(reporter_id)
        winner_id = int(winner_id)
        loser_id = int(loser_id)

        participants = {int(pairing["player1_id"]), int(pairing["player2_id"])}
        if {winner_id, loser_id} != participants:
            raise ValueError("Result players do not match this pairing")
        if pairing.get("status") != "active":
            _save_callback(
                guild_id, pairing_id, queue_type, outcome,
                reporter_id, winner_id, loser_id, None,
                played_cards, players,
            )
            return {"recorded": False, "duplicate": True, "match_id": None}

        card = load_match_card_for_pairing(pairing_id, stored_type) or {}
        names = {
            int(card.get("player1_id", 0)): card.get("player1_global"),
            int(card.get("player2_id", 0)): card.get("player2_global"),
        }
        winner_global = names.get(winner_id) or await _display_name(bot, winner_id)
        loser_global = names.get(loser_id) or await _display_name(bot, loser_id)
        decks = {
            int(pairing["player1_id"]): pairing.get("player1_deck_url"),
            int(pairing["player2_id"]): pairing.get("player2_deck_url"),
        }
        runs = {
            int(pairing["player1_id"]): pairing.get("player1_run_id", 0),
            int(pairing["player2_id"]): pairing.get("player2_run_id", 0),
        }
        opponent_id = loser_id if reporter_id == winner_id else winner_id
        data = {
            "reporter_id": reporter_id,
            "opponent_id": opponent_id,
            "winner_id": winner_id,
            "winner_global": winner_global,
            "loser_id": loser_id,
            "loser_global": loser_global,
            "reporter_global": winner_global if reporter_id == winner_id else loser_global,
            "opponent_global": loser_global if reporter_id == winner_id else winner_global,
            "match_start_time": card.get("match_start_time"),
            "first_player": None,
            "match_time": _minutes_since(pairing.get("created_at")),
            "match_comment": "Automatically reported by Sorcery Online",
            "winner_deck_url": decks.get(winner_id),
            "loser_deck_url": decks.get(loser_id),
            "ladder_info": card.get("ladder_info") or {},
            "match_type": stored_type,
            "guild_id": int(guild_id),
            "winner_run_id": runs.get(winner_id, 0),
            "loser_run_id": runs.get(loser_id, 0),
            "pairing_id": int(pairing_id),
            "notify_reporter": False,
        }
        match_key = f"pairing:{stored_type}:{pairing_id}"
        try:
            match_id = await _execute_match_confirmation(
                ApiInteraction(bot),
                0,
                data,
                interaction_valid=False,
            )
        except Exception:
            async with processed_matches_lock:
                processed_matches.pop(match_key, None)
            raise
        if match_id is None:
            refreshed = (
                get_limited_pairing_by_id(guild_id, pairing_id)
                if is_limited
                else get_pairing_by_id(guild_id, pairing_id)
            )
            if refreshed and refreshed.get("status") != "active":
                _save_callback(
                    guild_id, pairing_id, queue_type, outcome,
                    reporter_id, winner_id, loser_id, None,
                    played_cards, players,
                )
                return {"recorded": False, "duplicate": True, "match_id": None}
            async with processed_matches_lock:
                processed_matches.pop(match_key, None)
            raise RuntimeError("Match result could not be recorded")

        _save_callback(
            guild_id, pairing_id, queue_type, outcome,
            reporter_id, winner_id, loser_id, match_id,
            played_cards, players,
        )
        return {"recorded": True, "duplicate": False, "match_id": match_id}
