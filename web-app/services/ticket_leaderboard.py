"""The Discord leaderboard channel, as data.

The bot posts one embed after every rated game: overall top 8, the ticket
holders ranked, and the best free-play (non-ticket) players. This service
produces the same sections from the same standings so a partner such as
Play Sorcery Online can show them without reading Discord.
"""

import logging

from repositories.brackets import BracketRepository
from services.leaderboard import LeaderboardService, unique_players, voice_requirement
from services.ticket_holders import (
    ensure_roster_fresh,
    is_configured,
    ticket_holder_ids,
)

logger = logging.getLogger(__name__)

# The bot's embed shows this many in each section.
OVERALL_SHOWN = 8
TICKET_HOLDERS_SHOWN = 24
FREE_PLAY_SHOWN = 8


class TicketLeaderboardService:
    def __init__(self, leaderboard_service=None, ticket_repo=None):
        self._leaderboard = leaderboard_service or LeaderboardService()
        self._ticket_repo = ticket_repo or BracketRepository()

    def get_leaderboard(self, limit: int | None = None) -> dict:
        """Ranked ticket holders, plus the other two sections the channel shows.

        Ranking mirrors the bot: current-event ELO restricted to players who
        have played this event, best first; lifetime ELO when no event is
        running. `limit` caps the ticket-holder list (the channel shows 24);
        by default every ranked ticket holder is returned.

        In an Avatar-mode event the ladder has one entry per player and
        avatar. `overall` keeps every entry; `ticket_holders` and `free_play`
        list each player once, at their best avatar, so a second avatar never
        takes someone else's top-cut slot. Every row carries `avatar` (null in
        Player mode).
        """
        data = self._leaderboard.get_event_leaderboard()
        standings = data.get("leaderboard") or []
        event = data.get("event")
        elo_key = "event_elo"
        rating = "event"

        if not standings:
            standings = self._leaderboard.get_leaderboard()
            elo_key = "elo"
            rating = "lifetime"

        synced_at = ensure_roster_fresh(self._ticket_repo)
        holders = ticket_holder_ids(self._ticket_repo)

        players = []
        for overall_rank, entry in enumerate(standings, 1):
            user_id = str(entry["id"])
            wins = entry.get("wins") or 0
            losses = entry.get("losses") or 0
            players.append(
                {
                    "overall_rank": overall_rank,
                    "user_id": user_id,
                    "display_name": entry.get("name"),
                    "elo": entry.get(elo_key),
                    "games": wins + losses,
                    "wins": wins,
                    "losses": losses,
                    "voice_games": entry.get("voice_games", 0),
                    "avatar": entry.get("avatar"),
                    "is_ticket_holder": user_id in holders,
                }
            )

        ticket_holders = _ranked(unique_players(p for p in players if p["is_ticket_holder"]))
        free_play = _ranked(unique_players(p for p in players if not p["is_ticket_holder"]))
        if limit is not None:
            ticket_holders = ticket_holders[:limit]

        return {
            "event": event,
            "rating": rating,
            "elo_mode": (event or {}).get("elo_mode", "player"),
            # Every rated game has exactly one winner in the standings.
            "games_played": sum(p["wins"] for p in players),
            "ticket_holders": ticket_holders,
            "free_play": free_play[:FREE_PLAY_SHOWN],
            "overall": _ranked(players)[:OVERALL_SHOWN],
            "roster": {
                "size": len(holders),
                "synced_at": synced_at,
                "configured": is_configured(),
            },
            "voice_requirement": voice_requirement(),
        }


def _ranked(entries) -> list[dict]:
    """Number a section 1..n in the order given."""
    return [{"rank": rank, **p} for rank, p in enumerate(entries, 1)]
