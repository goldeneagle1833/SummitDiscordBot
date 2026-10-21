"""Season ticket roles, read from the bot's elo.db.

The bot's ``!ticket_role`` puts next season's ticket role on sale and
``!start_event`` makes it the season's active one (see
discord-bot/repositories/ticket_roles_repo.py). Until a season has its own
role, TICKET_HOLDER_ROLE_IDS from the environment still counts.
"""

import logging
import sqlite3

import webapp_config

logger = logging.getLogger(__name__)


def _role(status: str) -> dict | None:
    try:
        conn = sqlite3.connect(f"file:{webapp_config.ELO_DB_PATH}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM season_ticket_roles WHERE status = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (status,),
        ).fetchone()
        return dict(row) if row else None
    except sqlite3.Error:
        return None  # no table yet: no season has its own role
    finally:
        conn.close()


def active_ticket_role() -> dict | None:
    return _role("active")


def ticket_holder_role_ids() -> set[str]:
    """Roles that make someone a ticket holder this season."""
    active = active_ticket_role()
    if active:
        return {str(active["role_id"])}
    return set(webapp_config.TICKET_HOLDER_ROLE_IDS)


def selling_ticket_role() -> dict | None:
    """The role a "current season ticket" listing gives right now.

    Next season's role once it's on sale, otherwise this season's.
    """
    return _role("on_sale") or _role("active")


def ticket_free_shipping_role_ids() -> set[str]:
    """This season's and next season's ticket roles (free shipping perk)."""
    return {str(r["role_id"]) for r in (_role("active"), _role("on_sale")) if r}
