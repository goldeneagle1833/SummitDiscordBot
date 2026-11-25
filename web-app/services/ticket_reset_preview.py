"""What buying a season ticket right now would do to the buyer's season ratings.

Mirrors the bot's late-ticket reset (discord-bot/services/ticket_reset.py) so
the store can warn before checkout: after the first GRACE_DAYS of a season, a
new ticket sets every season rating above RESET_CAP to RESET_CAP, unless the
player has MAX_GAMES_WITHOUT_RESET or fewer season games (all avatars
together), and only once per player per season. Keep the numbers in step with
the bot's.
"""

import datetime
import sqlite3

import webapp_config
from repositories.elo import EloRepository
from repositories.store import CURRENT_SEASON_TICKET
from services import ticket_roles

RESET_CAP = 1500
GRACE_DAYS = 7
MAX_GAMES_WITHOUT_RESET = 2


def is_current_season_ticket(product: dict | None) -> bool:
    """Whether a listing gives this season's ticket role (the one the reset watches)."""
    if not product:
        return False
    role_id = str(product.get("discord_role_id") or "")
    if not role_id or product.get("product_type") not in ("discord_role", "bundle"):
        return False
    if role_id == CURRENT_SEASON_TICKET:
        # Once next season's ticket is on sale, this listing sells that one instead
        selling = ticket_roles.selling_ticket_role()
        active = ticket_roles.active_ticket_role()
        return selling is None or active is None or str(selling["role_id"]) == str(active["role_id"])
    return role_id in ticket_roles.ticket_holder_role_ids()


def _already_reset(db_path: str, event_id: int, user_id: str) -> bool:
    conn = sqlite3.connect(db_path)
    try:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ticket_resets'"
        ).fetchone():
            return False
        return conn.execute(
            "SELECT 1 FROM ticket_resets WHERE event_id = ? AND CAST(user_id AS TEXT) = ?",
            (event_id, str(user_id)),
        ).fetchone() is not None
    finally:
        conn.close()


def _player_mode_entries(user_id: str) -> list[dict]:
    from services.leaderboard import LeaderboardService

    rows = LeaderboardService().get_event_leaderboard().get("leaderboard") or []
    return [
        {"avatar": None, "elo": r.get("event_elo"), "games": (r.get("wins") or 0) + (r.get("losses") or 0)}
        for r in rows
        if str(r.get("id")) == str(user_id)
    ]


def preview_ticket_reset(user_id, *, elo_repo: EloRepository | None = None,
                         now: datetime.datetime | None = None) -> dict:
    """{will_reset, reason, event_name, grace_ends, games, entries:[{avatar, from, to}]}."""
    elo_repo = elo_repo or EloRepository()
    event = elo_repo.get_active_event()
    if not event:
        return {"will_reset": False, "reason": "no_event", "entries": []}

    start = datetime.datetime.fromisoformat(str(event["start_date"]))
    grace_ends = start + datetime.timedelta(days=GRACE_DAYS)
    base = {
        "event_name": event["event_name"],
        "grace_ends": grace_ends.isoformat(),
        "cap": RESET_CAP,
        "max_games_without_reset": MAX_GAMES_WITHOUT_RESET,
        "entries": [],
    }
    now = now or datetime.datetime.now()
    if now < grace_ends:
        return {**base, "will_reset": False, "reason": "grace"}

    db_path = getattr(elo_repo, "_db_path", None) or webapp_config.ELO_DB_PATH
    if _already_reset(db_path, event["event_id"], user_id):
        return {**base, "will_reset": False, "reason": "already_reset"}

    if event.get("elo_mode") == "avatar":
        mine = [
            {"avatar": r["avatar"], "elo": r["event_elo"], "games": r["games_played"] or 0}
            for r in elo_repo.get_avatar_standings(event["event_id"])
            if str(r["user_id"]) == str(user_id)
        ]
    else:
        mine = _player_mode_entries(user_id)

    games = sum(e["games"] for e in mine)
    base["games"] = games
    if games <= MAX_GAMES_WITHOUT_RESET:
        return {**base, "will_reset": False, "reason": "few_games"}

    above = [
        {"avatar": e["avatar"], "from": e["elo"], "to": RESET_CAP}
        for e in mine
        if (e["elo"] or 0) > RESET_CAP
    ]
    if not above:
        return {**base, "will_reset": False, "reason": "nothing_above_cap"}
    return {**base, "will_reset": True, "reason": "reset", "entries": above}
