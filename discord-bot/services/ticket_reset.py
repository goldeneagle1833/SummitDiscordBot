"""Late-ticket reset: buying a season ticket mid-season caps your ratings at 1500.

Bruce's rule (2026-11-11): when someone gets a ticket after the season has
started, any season rating of theirs above 1500 drops to 1500; anything at or
below 1500 stays. Two exceptions:

- Grace week: tickets picked up in the first GRACE_DAYS of the season never
  reset anything.
- New players: someone with MAX_GAMES_WITHOUT_RESET or fewer season games is
  left alone.

In an Avatar-mode season every avatar entry above 1500 is capped; the games
count is the player's total across all their avatars. Each player is reset
at most once per season (logged in ticket_resets), so losing and regaining
the role doesn't reset them again.
"""

import datetime
import logging
import sqlite3
from dataclasses import dataclass, field

from repositories.audit_repo import log_admin_action
from repositories.avatar_elo_repo import set_avatar_event_elo
from repositories.elo_repo import set_player_event_elo
from services.avatar_mode import get_event_ladder, is_avatar_mode

logger = logging.getLogger("discord_bot")

RESET_CAP = 1500
GRACE_DAYS = 7
MAX_GAMES_WITHOUT_RESET = 2


@dataclass
class TicketResetPlan:
    """What a new ticket does to one player's ratings."""

    reason: str  # "reset", "grace", "few_games", "nothing_above_cap", "no_event", "already_reset"
    games: int = 0
    # (avatar or None, old_elo) for every entry that drops to RESET_CAP
    entries: list = field(default_factory=list)

    @property
    def will_reset(self) -> bool:
        return self.reason == "reset"


def _ensure_table(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ticket_resets (
               event_id INTEGER NOT NULL,
               user_id INTEGER NOT NULL,
               reset_at TEXT NOT NULL,
               details TEXT,
               PRIMARY KEY (event_id, user_id)
           )"""
    )


def already_reset(event_id: int, user_id: int) -> bool:
    conn = sqlite3.connect("elo.db")
    try:
        _ensure_table(conn)
        return conn.execute(
            "SELECT 1 FROM ticket_resets WHERE event_id = ? AND user_id = ?",
            (event_id, user_id),
        ).fetchone() is not None
    finally:
        conn.close()


def grace_ends(event: dict) -> datetime.datetime:
    return event["start_date"] + datetime.timedelta(days=GRACE_DAYS)


def plan_ticket_reset(event: dict | None, user_id: int, now: datetime.datetime | None = None) -> TicketResetPlan:
    """Work out whether (and which) ratings a new ticket resets. Changes nothing."""
    if not event:
        return TicketResetPlan("no_event")
    now = now or datetime.datetime.now()
    if now < grace_ends(event):
        return TicketResetPlan("grace")
    if already_reset(event["event_id"], user_id):
        return TicketResetPlan("already_reset")

    mine = [e for e in get_event_ladder(event) if e.user_id == user_id]
    games = sum(e.games_played for e in mine)
    if games <= MAX_GAMES_WITHOUT_RESET:
        return TicketResetPlan("few_games", games)

    entries = [(e.avatar, e.event_elo) for e in mine if (e.event_elo or 0) > RESET_CAP]
    if not entries:
        return TicketResetPlan("nothing_above_cap", games)
    return TicketResetPlan("reset", games, entries)


def apply_ticket_reset(event: dict, user_id: int, display_name: str, plan: TicketResetPlan) -> None:
    """Cap the planned entries at RESET_CAP and record that this player was reset."""
    if not plan.will_reset:
        return
    for avatar, old_elo in plan.entries:
        if is_avatar_mode(event):
            set_avatar_event_elo(event["event_id"], user_id, display_name, avatar, RESET_CAP)
        else:
            set_player_event_elo(user_id, display_name, RESET_CAP)

    summary = ", ".join(
        f"{avatar}: {old} -> {RESET_CAP}" if avatar else f"{old} -> {RESET_CAP}"
        for avatar, old in plan.entries
    )
    conn = sqlite3.connect("elo.db")
    try:
        _ensure_table(conn)
        conn.execute(
            "INSERT OR REPLACE INTO ticket_resets (event_id, user_id, reset_at, details) VALUES (?, ?, ?, ?)",
            (event["event_id"], user_id, datetime.datetime.now().isoformat(), summary),
        )
        conn.commit()
    finally:
        conn.close()

    log_admin_action(
        0,
        "Summit-Bot (late ticket)",
        "ticket_late_reset",
        target_id=user_id,
        target_name=display_name,
        previous_state={"entries": [{"avatar": a, "elo": e} for a, e in plan.entries]},
        new_state={"elo": RESET_CAP},
        details=f"Ticket bought after the grace week of '{event['event_name']}': {summary}",
    )
    logger.info("Late ticket reset for %s (%s) in %s: %s", display_name, user_id, event["event_name"], summary)
