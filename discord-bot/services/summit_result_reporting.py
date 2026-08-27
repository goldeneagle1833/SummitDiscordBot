"""Idempotent Sorcery Online result delivery into Summit's match pipeline."""

import asyncio
import datetime
import json
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


_result_lock = asyncio.Lock()
_VALID_OUTCOMES = {"decided", "no_contest", "conflict", "unknown"}


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


def _normalize_played_cards(players, participants):
    if players is None:
        return [
            {"player_id": player_id, "played_cards": []}
            for player_id in sorted(participants)
        ]
    if not isinstance(players, list) or len(players) != len(participants):
        raise ValueError("Played cards must be supplied for both pairing players")
    normalized = []
    seen_players = set()
    for player in players:
        if not isinstance(player, dict):
            raise ValueError("Invalid played-card player entry")
        player_id = int(player.get("player_id"))
        if player_id not in participants or player_id in seen_players:
            raise ValueError("Played-card players do not match this pairing")
        cards = player.get("played_cards", [])
        if not isinstance(cards, list) or len(cards) > 200:
            raise ValueError("Invalid played-card list")
        normalized_cards = []
        seen_cards = set()
        for card in cards:
            if not isinstance(card, dict):
                raise ValueError("Invalid played card")
            card_id = str(card.get("card_id") or "").strip()
            card_name = str(card.get("card_name") or "").strip()
            quantity = int(card.get("quantity", 0))
            if (
                not card_id or len(card_id) > 200
                or not card_name or len(card_name) > 300
                or quantity < 1 or quantity > 100
                or card_id in seen_cards
            ):
                raise ValueError("Invalid played card")
            seen_cards.add(card_id)
            normalized_cards.append({
                "card_id": card_id,
                "card_name": card_name,
                "quantity": quantity,
            })
        seen_players.add(player_id)
        normalized.append({"player_id": player_id, "played_cards": normalized_cards})
    if seen_players != participants:
        raise ValueError("Played-card players do not match this pairing")
    return sorted(normalized, key=lambda player: player["player_id"])


def _save_callback(
    *, guild_id, pairing_id, queue_type, outcome, reporter_id,
    winner_id, loser_id, players, match_id=None,
):
    conn = sqlite3.connect("match_records.db")
    conn.execute("""CREATE TABLE IF NOT EXISTS sorcery_online_match_callbacks (
        guild_id INTEGER NOT NULL,
        pairing_id INTEGER NOT NULL,
        queue_type TEXT NOT NULL,
        outcome TEXT NOT NULL,
        reporter_id INTEGER,
        winner_id INTEGER,
        loser_id INTEGER,
        played_cards_json TEXT NOT NULL,
        match_id INTEGER,
        received_at TEXT NOT NULL,
        PRIMARY KEY (guild_id, pairing_id, queue_type)
    )""")
    conn.execute(
        """INSERT INTO sorcery_online_match_callbacks (
               guild_id, pairing_id, queue_type, outcome, reporter_id,
               winner_id, loser_id, played_cards_json, match_id, received_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(guild_id, pairing_id, queue_type) DO UPDATE SET
               outcome = excluded.outcome,
               reporter_id = excluded.reporter_id,
               winner_id = excluded.winner_id,
               loser_id = excluded.loser_id,
               played_cards_json = excluded.played_cards_json,
               match_id = COALESCE(excluded.match_id, sorcery_online_match_callbacks.match_id),
               received_at = excluded.received_at""",
        (
            guild_id, pairing_id, queue_type, outcome, reporter_id,
            winner_id, loser_id, json.dumps(players, separators=(",", ":")),
            match_id, datetime.datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


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
    """Record every terminal callback and apply decided results to the match pipeline."""
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
        participants = {int(pairing["player1_id"]), int(pairing["player2_id"])}
        if outcome not in _VALID_OUTCOMES:
            raise ValueError("Invalid Sorcery Online outcome")
        reporter_id = int(reporter_id) if reporter_id is not None else None
        winner_id = int(winner_id) if winner_id is not None else None
        loser_id = int(loser_id) if loser_id is not None else None
        if reporter_id is not None and reporter_id not in participants:
            raise ValueError("Result players do not match this pairing")
        if outcome == "decided":
            if (
                reporter_id not in participants
                or winner_id is None or loser_id is None
                or {winner_id, loser_id} != participants
            ):
                raise ValueError("Result players do not match this pairing")
        elif winner_id is not None or loser_id is not None:
            raise ValueError("Only decided outcomes may name a winner and loser")
        normalized_players = _normalize_played_cards(players, participants)
        _save_callback(
            guild_id=int(guild_id),
            pairing_id=int(pairing_id),
            queue_type=queue_type,
            outcome=outcome,
            reporter_id=reporter_id,
            winner_id=winner_id,
            loser_id=loser_id,
            players=normalized_players,
        )
        if pairing.get("status") != "active":
            return {"recorded": False, "duplicate": True, "match_id": None}
        if outcome != "decided":
            first_id, second_id = sorted(participants)
            mark_reported = (
                mark_limited_pairing_reported if is_limited else mark_pairing_reported
            )
            if not mark_reported(
                int(guild_id), first_id, second_id, pairing_id=int(pairing_id)
            ):
                raise RuntimeError("Pairing completion could not be recorded")
            return {
                "recorded": False,
                "duplicate": False,
                "match_id": None,
                "outcome": outcome,
            }

        card = load_match_card_for_pairing(pairing_id, stored_type) or {}
        names = {
            int(card.get("player1_id", 0)): card.get("player1_global"),
            int(card.get("player2_id", 0)): card.get("player2_global"),
        }
        winner_global = names.get(int(winner_id)) or await _display_name(bot, int(winner_id))
        loser_global = names.get(int(loser_id)) or await _display_name(bot, int(loser_id))
        decks = {
            int(pairing["player1_id"]): pairing.get("player1_deck_url"),
            int(pairing["player2_id"]): pairing.get("player2_deck_url"),
        }
        runs = {
            int(pairing["player1_id"]): pairing.get("player1_run_id", 0),
            int(pairing["player2_id"]): pairing.get("player2_run_id", 0),
        }
        opponent_id = int(loser_id) if int(reporter_id) == int(winner_id) else int(winner_id)
        data = {
            "reporter_id": int(reporter_id),
            "opponent_id": opponent_id,
            "winner_id": int(winner_id),
            "winner_global": winner_global,
            "loser_id": int(loser_id),
            "loser_global": loser_global,
            "reporter_global": winner_global if int(reporter_id) == int(winner_id) else loser_global,
            "opponent_global": loser_global if int(reporter_id) == int(winner_id) else winner_global,
            "match_start_time": card.get("match_start_time"),
            "first_player": None,
            "match_time": _minutes_since(pairing.get("created_at")),
            "match_comment": "Automatically reported by Sorcery Online",
            "winner_deck_url": decks.get(int(winner_id)),
            "loser_deck_url": decks.get(int(loser_id)),
            "ladder_info": card.get("ladder_info") or {},
            "match_type": stored_type,
            "guild_id": int(guild_id),
            "winner_run_id": runs.get(int(winner_id), 0),
            "loser_run_id": runs.get(int(loser_id), 0),
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
                return {"recorded": False, "duplicate": True, "match_id": None}
            async with processed_matches_lock:
                processed_matches.pop(match_key, None)
            raise RuntimeError("Match result could not be recorded")
        _save_callback(
            guild_id=int(guild_id),
            pairing_id=int(pairing_id),
            queue_type=queue_type,
            outcome=outcome,
            reporter_id=reporter_id,
            winner_id=winner_id,
            loser_id=loser_id,
            players=normalized_players,
            match_id=match_id,
        )
        return {"recorded": True, "duplicate": False, "match_id": match_id}
