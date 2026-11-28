"""A signed-in AI app reads the player's own data (see services/mcp_oauth.py).

The Summit MCP server calls these with the player's access token in
``X-Summit-User-Token`` (plus the usual site token for the site gate). A token
only ever reads its own player's data; nothing here changes anything.

GET /api/mcp/me               who signed in
GET /api/mcp/me/matches       own ranked history, newest games' avatars included
GET /api/mcp/me/card-stats    own Card Stats (private on the profile by default)

Players manage their connected apps with the session-based endpoints:
GET /api/mcp/connections, DELETE /api/mcp/connections[/<client_id>]
"""

from __future__ import annotations

import logging
import re
from functools import wraps

from flask import Blueprint, g, jsonify, request, session

import webapp_config
from services import mcp_oauth
from services import public_match_history as history
from services.summit_player_numbers import bot_player_id
from utils.auth import require_auth

logger = logging.getLogger(__name__)

mcp_account_bp = Blueprint("mcp_account", __name__)

TOKEN_HEADER = "X-Summit-User-Token"
_SEASON_RE = re.compile(r"^(all|current|\d{1,6})$")


def require_mcp_user(f):
    """A live AI-app access token is required; sets g.mcp_user_id."""

    @wraps(f)
    def decorated(*args, **kwargs):
        info = mcp_oauth.verify_access_token(request.headers.get(TOKEN_HEADER) or "")
        if not info:
            return jsonify({"error": "Sign in again from your AI app."}), 401
        g.mcp_user_id = info["user_id"]
        g.mcp_client = info
        return f(*args, **kwargs)

    decorated._auth_required = True
    return decorated


def _player_id() -> str:
    return bot_player_id(g.mcp_user_id)


def _display_name(player_id: str) -> str | None:
    try:
        from repositories.elo import EloRepository
        name = EloRepository().get_display_name(player_id)
        if name:
            return name
    except Exception:
        pass
    try:
        from routes.api.players import _any_display_name
        return _any_display_name(player_id)
    except Exception:
        return None


@mcp_account_bp.route("/mcp/me", methods=["GET"])
@require_mcp_user
def mcp_me():
    pid = _player_id()
    return jsonify({
        "player_id": pid,
        "name": _display_name(pid),
        "app": g.mcp_client.get("client_name"),
        "profile": f"/player/{pid}",
    })


@mcp_account_bp.route("/mcp/me/matches", methods=["GET"])
@require_mcp_user
def mcp_my_matches():
    pid = _player_id()
    season = (request.args.get("season") or "all").strip().lower()
    if not _SEASON_RE.match(season):
        return jsonify({"error": 'season must be "all", "current" or a season id'}), 400
    page = max(1, request.args.get("page", 1, type=int) or 1)
    per_page = min(history.MAX_PER_PAGE, max(1, request.args.get("per_page", 100, type=int) or 100))
    try:
        data = history.get_match_history(pid, season=season, page=page, per_page=per_page, owner=True)
    except history.PlayerNotFound:
        return jsonify({"player": {"id": pid}, "matches": [], "pagination": {"has_next": False}})
    except ValueError:
        return jsonify({"player": {"id": pid}, "matches": [], "pagination": {"has_next": False}})
    return jsonify(data)


@mcp_account_bp.route("/mcp/me/card-stats", methods=["GET"])
@require_mcp_user
def mcp_my_card_stats():
    """Own played-card stats from saved Play Sorcery Online results (never a live PSO call)."""
    from repositories.user_profiles import UserProfileRepository
    from routes.api.cards import _get_event_date_range, _load_card_elements
    from services.player_card_stats import QUEUE_FILTERS, load_player_games, summarize

    pid = _player_id()
    event = request.args.get("event", "lifetime")
    if event not in ("lifetime", "current") and not str(event).isdigit():
        event = "lifetime"
    start, end = (None, None) if event == "lifetime" else _get_event_date_range(event)
    repo = UserProfileRepository()
    reset_at = repo.get_profile_reset_at(pid) or repo.get_profile_reset_at(str(g.mcp_user_id))
    if reset_at and (not start or str(reset_at) > str(start)):
        start = reset_at
    queue = request.args.get("queue", "ranked")
    if queue not in QUEUE_FILTERS:
        queue = "ranked"
    result = summarize(load_player_games(webapp_config.MATCH_RECORDS_DB_PATH, pid, start, end, queue))
    elements = _load_card_elements()
    for card in result["cards"]:
        element = elements.get(card["name"].lower())
        if isinstance(element, (set, list, tuple)):
            element = " / ".join(sorted(element)) or None
        card["element"] = element
    result.update({"queue": queue, "event": event})
    return jsonify(result)


# ---------------------------------------------------------------------------
# The player manages their connected apps (site session)
# ---------------------------------------------------------------------------


@mcp_account_bp.route("/mcp/connections", methods=["GET"])
@require_auth
def mcp_connections():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Sign in first"}), 401
    return jsonify({"connections": mcp_oauth.connections(str(user_id))})


@mcp_account_bp.route("/mcp/connections", methods=["DELETE"])
@mcp_account_bp.route("/mcp/connections/<client_id>", methods=["DELETE"])
@require_auth
def mcp_disconnect(client_id=None):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Sign in first"}), 401
    mcp_oauth.disconnect(str(user_id), client_id)
    logger.info("Player %s disconnected AI app %s", user_id, client_id or "(all)")
    return jsonify({"success": True, "connections": mcp_oauth.connections(str(user_id))})
