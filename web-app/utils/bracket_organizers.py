"""Who may create and run community brackets.

Admins always can. Anyone else needs a Discord role: the roles in
BRACKET_ORGANIZER_ROLE_IDS, or - when that is not set - the server role named
BRACKET_ORGANIZER_ROLE_NAME ("Bracket Organizer"), so the role only has to be
created in Discord. Roles are read at login, and also asked of Discord with the
bot token (cached for a few minutes), so a role handed out after someone
logged in takes effect without them logging in again.
"""

import logging
import threading
import time

import requests
from flask import session

import webapp_config
from utils.auth import is_admin

logger = logging.getLogger(__name__)

DISCORD_API = "https://discord.com/api/v10"
REQUEST_TIMEOUT = (3, 5)
# How long a member's roles, and the role list, are trusted before asking again.
MEMBER_CACHE_SECONDS = 300
ROLE_CACHE_SECONDS = 600

_lock = threading.Lock()
_member_roles: dict[str, tuple[float, set[str] | None]] = {}
_named_roles: dict[str, object] = {"at": 0.0, "ids": set()}


def _headers() -> dict:
    return {"Authorization": f"Bot {webapp_config.DISCORD_BOT_TOKEN}"}


def organizer_role_ids() -> set[str]:
    """The role ids that make someone an organizer."""
    if webapp_config.BRACKET_ORGANIZER_ROLE_IDS:
        return set(webapp_config.BRACKET_ORGANIZER_ROLE_IDS)
    return _roles_named(webapp_config.BRACKET_ORGANIZER_ROLE_NAME)


def _roles_named(name: str) -> set[str]:
    """Ids of the server roles called `name` (case-insensitive), cached."""
    if not name or not webapp_config.DISCORD_BOT_TOKEN:
        return set()
    now = time.monotonic()
    with _lock:
        if now - _named_roles["at"] < ROLE_CACHE_SECONDS:
            return set(_named_roles["ids"])
    ids = set()
    try:
        resp = requests.get(
            f"{DISCORD_API}/guilds/{webapp_config.DISCORD_GUILD_ID}/roles",
            headers=_headers(),
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 200:
            wanted = name.strip().lower()
            ids = {
                str(role["id"])
                for role in resp.json()
                if str(role.get("name") or "").strip().lower() == wanted
            }
        else:
            logger.warning("Bracket organizer role lookup: Discord returned %s", resp.status_code)
    except Exception as e:
        logger.warning("Bracket organizer role lookup failed: %s", e)
    with _lock:
        _named_roles["at"] = now
        _named_roles["ids"] = ids
    return ids


def _live_roles(user_id: str) -> set[str] | None:
    """The member's current roles from Discord, cached; None if unknown."""
    if not webapp_config.DISCORD_BOT_TOKEN or not str(user_id).isdigit():
        return None
    now = time.monotonic()
    with _lock:
        cached = _member_roles.get(user_id)
        if cached and now - cached[0] < MEMBER_CACHE_SECONDS:
            return cached[1]
    roles = None
    try:
        resp = requests.get(
            f"{DISCORD_API}/guilds/{webapp_config.DISCORD_GUILD_ID}/members/{user_id}",
            headers=_headers(),
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 200:
            roles = {str(r) for r in resp.json().get("roles") or []}
        elif resp.status_code == 404:
            roles = set()  # Not in the server
    except Exception as e:
        logger.warning("Bracket organizer member lookup failed for %s: %s", user_id, e)
    with _lock:
        if len(_member_roles) > 5000:
            _member_roles.clear()
        _member_roles[user_id] = (now, roles)
    return roles


def is_bracket_organizer() -> bool:
    """True for admins and for signed-in players holding the organizer role."""
    if is_admin():
        return True
    user_id = session.get("user_id")
    if not user_id or session.get("auth_provider") not in (None, "discord"):
        return False
    wanted = organizer_role_ids()
    if not wanted:
        return False
    # Discord's answer wins, so taking the role away works without a logout;
    # the roles read at login stand in when Discord can't be asked.
    live = _live_roles(str(user_id))
    if live is not None:
        return bool(wanted & live)
    return bool(wanted & {str(r) for r in session.get("discord_roles") or []})
