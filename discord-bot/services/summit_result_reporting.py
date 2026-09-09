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

# The callback audit table lives in the same match_records.db the rest of
# the bot uses (elo_repo / elo_service open it CWD-relative), so pairings,
# match rows and callbacks always land in one file.
MATCH_RECORDS_DB = "match_records.db"
CALLBACK_TABLE = "sorcery_online_match_callbacks"
_CALLBACK_COLUMNS = (
    "id", "guild_id", "pairing_id", "queue_type", "outcome", "reporter_id",
    "winner_id", "loser_id", "match_id", "played_cards", "raw_players", "created_at",
)


def _get_match_records_db():
    return MATCH_RECORDS_DB


def _ensure_callback_table():
    conn = sqlite3.connect(_get_match_records_db())
    try:
        existing = {
            row[1] for row in conn.execute(f"PRAGMA table_info({CALLBACK_TABLE})")
        }
        if existing and not {"played_cards", "raw_players"}.issubset(existing):
            # Earlier table shape (composite primary key, played_cards_json NOT NULL).
            # CREATE TABLE IF NOT EXISTS won't upgrade it, so keep the old rows
            # under a legacy name and start a fresh table.
            legacy = f"{CALLBACK_TABLE}_legacy"
            conn.execute(f"DROP TABLE IF EXISTS {legacy}")
            conn.execute(f"ALTER TABLE {CALLBACK_TABLE} RENAME TO {legacy}")
            logger.warning(
                "Migrated old %s schema to %s; new callbacks use the current schema",
                CALLBACK_TABLE, legacy,
            )
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {CALLBACK_TABLE} (
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
    """Append an audit row for a Sorcery Online callback.

    This is bookkeeping only. It must never turn an already-recorded match
    into an error response (SO would retry and see a confusing duplicate),
    so failures are logged and swallowed.
    """
    try:
        _ensure_callback_table()
        played_json = json.dumps(played_cards) if played_cards else None
        raw_json = json.dumps(raw_players) if raw_players else None
        logger.info(
            "SO _save_callback: pairing=%s outcome=%s match_id=%s "
            "played_cards_null=%s raw_players_null=%s",
            pairing_id, outcome, match_id,
            played_json is None, raw_json is None,
        )
        conn = sqlite3.connect(_get_match_records_db())
        try:
            conn.execute(
                f"""INSERT INTO {CALLBACK_TABLE}
                   (guild_id, pairing_id, queue_type, outcome,
                    reporter_id, winner_id, loser_id, match_id,
                    played_cards, raw_players)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    guild_id, pairing_id, queue_type, outcome,
                    reporter_id, winner_id, loser_id, match_id,
                    played_json, raw_json,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error:
        logger.error(
            "Could not store Sorcery Online callback audit row for pairing %s (%s)",
            pairing_id, outcome, exc_info=True,
        )


def _recorded_callback_match_id(guild_id, pairing_id, queue_type):
    """Return the match created by an earlier successful callback, if any."""
    try:
        _ensure_callback_table()
        conn = sqlite3.connect(_get_match_records_db())
        try:
            row = conn.execute(
                f"""SELECT match_id FROM {CALLBACK_TABLE}
                    WHERE guild_id = ? AND pairing_id = ? AND queue_type = ?
                      AND outcome = 'decided' AND match_id IS NOT NULL
                    ORDER BY id DESC LIMIT 1""",
                (guild_id, pairing_id, queue_type),
            ).fetchone()
            return int(row[0]) if row else None
        finally:
            conn.close()
    except sqlite3.Error:
        logger.error(
            "Could not check Sorcery Online callback state for pairing %s",
            pairing_id, exc_info=True,
        )
        return None


def _normalize_played_cards(players):
    """Extract played card names from SO player data.

    Returns a dict mapping discord_id -> list of card names, or None.
    """
    if not players:
        return None
    result = {}
    for p in players:
        discord_id = (
            p.get("discordId") or p.get("discord_id")
            or p.get("playerId") or p.get("player_id")
        )
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


async def _notify_sorcery_online_match_recorded(
    bot,
    *,
    match_id,
    match_type,
    winner_id,
    winner_name,
    loser_id,
    loser_name,
):
    """Best-effort Discord delivery for a result reported outside Discord.

    Sorcery Online callbacks do not have a live Discord interaction, so the
    normal confirmation follow-up cannot reach either player. Send both
    players an explicit Summit Bot DM and fall back to the DM-disabled channel
    independently if either delivery fails.
    """
    labels = {
        "limited": "Limited",
        "ranked": "Ranked",
        "rumble": "Rumble",
        "points": "Rumble (Omens)",
        "testing": "Casual",
    }
    label = labels.get(match_type, str(match_type).capitalize())
    messages = (
        (
            winner_id,
            f"✅ **{label} Match Recorded** — You defeated **{loser_name}** on "
            f"Sorcery Online. **Match ID: #{match_id}**",
        ),
        (
            loser_id,
            f"✅ **{label} Match Recorded** — **{winner_name}** defeated you on "
            f"Sorcery Online. **Match ID: #{match_id}**",
        ),
    )

    for user_id, message in messages:
        try:
            user = await bot.fetch_user(user_id)
            await user.send(message)
            logger.info(
                "Sent Sorcery Online match result DM to %s for match %s",
                user_id, match_id,
            )
            continue
        except Exception as exc:
            logger.warning(
                "Could not DM Sorcery Online match result to %s: %s",
                user_id, exc,
            )

        fallback_channel = bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
        if fallback_channel:
            try:
                await fallback_channel.send(f"<@{user_id}> {message}")
            except Exception as exc:
                logger.error(
                    "Could not send Sorcery Online match result fallback for %s: %s",
                    user_id, exc,
                )


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
    winner_went_first=None,
    players=None,
):
    """Record one authoritative pairing result, returning duplicate success on retries."""
    logger.info(
        "SO record_sorcery_online_result called: guild=%s pairing=%s queue=%s outcome=%s "
        "reporter=%s winner=%s loser=%s players_type=%s players_len=%s",
        guild_id, pairing_id, queue_type, outcome,
        reporter_id, winner_id, loser_id,
        type(players).__name__ if players else None,
        len(players) if isinstance(players, (list, dict)) else None,
    )
    if players:
        logger.info("SO players raw data: %s", json.dumps(players, default=str)[:2000])
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
        logger.info(
            "SO pairing %s: played_cards normalized=%s",
            pairing_id,
            json.dumps(played_cards, default=str)[:1000] if played_cards else None,
        )

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
            existing_match_id = _recorded_callback_match_id(
                guild_id, pairing_id, queue_type,
            )
            if existing_match_id is not None:
                return {
                    "recorded": False,
                    "duplicate": True,
                    "match_id": existing_match_id,
                }
            raise RuntimeError(
                "Pairing is closed but has no successfully recorded Sorcery Online match"
            )

        card = load_match_card_for_pairing(pairing_id, stored_type) or {}
        names = {
            int(card.get("player1_id", 0)): card.get("player1_global"),
            int(card.get("player2_id", 0)): card.get("player2_global"),
        }
        winner_global = names.get(winner_id) or await _display_name(bot, winner_id)
        loser_global = names.get(loser_id) or await _display_name(bot, loser_id)
        pso_deck_urls = {}
        if players:
            for p in players:
                pid = str(
                    p.get("player_id") or p.get("discord_id") or ""
                )
                url = p.get("deck_url") or p.get("deckUrl") or ""
                if pid and url:
                    pso_deck_urls[int(pid)] = url
        decks = {
            int(pairing["player1_id"]): pairing.get("player1_deck_url") or pso_deck_urls.get(int(pairing["player1_id"])),
            int(pairing["player2_id"]): pairing.get("player2_deck_url") or pso_deck_urls.get(int(pairing["player2_id"])),
        }
        runs = {
            int(pairing["player1_id"]): pairing.get("player1_run_id", 0),
            int(pairing["player2_id"]): pairing.get("player2_run_id", 0),
        }
        opponent_id = loser_id if reporter_id == winner_id else winner_id
        if winner_went_first is None:
            first_player = None
        else:
            reporter_went_first = bool(winner_went_first) == (reporter_id == winner_id)
            first_player = "y" if reporter_went_first else "n"
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
            "first_player": first_player,
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
                existing_match_id = _recorded_callback_match_id(
                    guild_id, pairing_id, queue_type,
                )
                if existing_match_id is not None:
                    return {
                        "recorded": False,
                        "duplicate": True,
                        "match_id": existing_match_id,
                    }
            async with processed_matches_lock:
                processed_matches.pop(match_key, None)
            raise RuntimeError("Match result could not be recorded")

        await _notify_sorcery_online_match_recorded(
            bot,
            match_id=match_id,
            match_type=stored_type,
            winner_id=winner_id,
            winner_name=winner_global,
            loser_id=loser_id,
            loser_name=loser_global,
        )

        _save_callback(
            guild_id, pairing_id, queue_type, outcome,
            reporter_id, winner_id, loser_id, match_id,
            played_cards, players,
        )
        return {"recorded": True, "duplicate": False, "match_id": match_id}
