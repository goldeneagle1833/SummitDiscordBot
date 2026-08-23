"""Idempotent Sorcery Online result delivery into Summit's match pipeline."""

import asyncio
import datetime

from cogs.lfg.persistent_confirm import (
    _execute_match_confirmation,
    load_match_card_for_pairing,
)
from cogs.lfg.state import processed_matches, processed_matches_lock
from repositories.elo_repo import get_pairing_by_id
from repositories.limited_repo import get_limited_pairing_by_id


_result_lock = asyncio.Lock()


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
    reporter_id,
    winner_id,
    loser_id,
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
        participants = {int(pairing["player1_id"]), int(pairing["player2_id"])}
        if {int(winner_id), int(loser_id)} != participants or int(reporter_id) not in participants:
            raise ValueError("Result players do not match this pairing")
        if pairing.get("status") != "active":
            return {"recorded": False, "duplicate": True, "match_id": None}

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
        return {"recorded": True, "duplicate": False, "match_id": match_id}
