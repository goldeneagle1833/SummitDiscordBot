"""Open API: a player's ranked match history, and a name search to find their id.

GET /api/public/players/<player_id>/matches and GET /api/public/players/search
are open to everybody: no login and no API key (site gate exempt list), with
CORS open. Each visitor (by IP) gets 60 calls a minute across both.

Per match: result, opponent, date, rating change, play/draw, and each side's
avatar and deck elements. Never a deck list, deck link or replay (Bruce).
See services/public_match_history.py for the rules.
"""

import logging
import re

from flask import Blueprint, jsonify, request

from services import api_usage
from services import public_match_history as history
from services import ranked_analytics

logger = logging.getLogger(__name__)

public_matches_bp = Blueprint("public_matches", __name__)
public_matches_bp.after_request(api_usage.log_response)  # admin page "API Usage"

_SEASON_RE = re.compile(r"^(all|current|\d{1,6})$")


def _client_key() -> str:
    forwarded = request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For", "")
    ip = forwarded.split(",")[0].strip() or request.remote_addr or "unknown"
    return f"public-matches:{ip}"


def _respond(payload, status=200, max_age=60):
    response = jsonify(payload)
    response.status_code = status
    response.headers["Access-Control-Allow-Origin"] = "*"
    if status == 200:
        response.headers["Cache-Control"] = f"public, max-age={max_age}"
    return response


def _error(message, status=400):
    return _respond({"success": False, "error": message}, status)


@public_matches_bp.route("/public/players/<player_id>/matches", methods=["GET"])
def get_player_matches(player_id):
    """One page of a player's ranked match history, newest first.

    Query params (all optional):
        season: "all" (default), "current", or a season id
        page: 1-based page (default 1)
        per_page: 1-100 (default 25)
    """
    if not ranked_analytics.claim_request(_client_key()):
        return _error("Too many requests. Try again in a minute.", 429)
    try:
        pid = history.normalize_player_id(player_id)
    except ValueError as exc:
        return _error(str(exc))
    season = (request.args.get("season") or "all").strip().lower()
    if not _SEASON_RE.match(season):
        return _error('season must be "all", "current" or a season id')
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", history.DEFAULT_PER_PAGE, type=int)
    if page is None or page < 1:
        return _error("page must be a positive integer")
    if per_page is None or not 1 <= per_page <= history.MAX_PER_PAGE:
        return _error(f"per_page must be 1-{history.MAX_PER_PAGE}")
    try:
        data = history.get_match_history(pid, season=season, page=page, per_page=per_page)
    except history.PlayerNotFound:
        return _error("No ranked matches found for this player", 404)
    except Exception as exc:
        logger.error("Public match history failed for %s: %s", pid, exc, exc_info=True)
        return _error("Could not load match history", 500)
    return _respond({"success": True, **data})


@public_matches_bp.route("/public/players/search", methods=["GET"])
def search_public_players():
    """Find a player's id by name. GET /api/public/players/search?q=<name>&limit=10"""
    if not ranked_analytics.claim_request(_client_key()):
        return _error("Too many requests. Try again in a minute.", 429)
    query = (request.args.get("q") or "").strip()
    if len(query) < 2 or len(query) > 50:
        return _error("q must be 2-50 characters")
    limit = request.args.get("limit", 10, type=int)
    if limit is None or not 1 <= limit <= 20:
        return _error("limit must be 1-20")
    players, seen = [], set()
    try:
        from repositories.elo import EloRepository
        from repositories.user_profiles import UserProfileRepository

        for r in UserProfileRepository().search_users(query, limit=limit):
            uid = str(r["user_id"])
            uid = uid[7:] if uid.startswith("google_") else uid
            if uid not in seen:
                seen.add(uid)
                players.append({"id": uid, "name": r.get("display_name")})
        if len(players) < limit:
            for r in EloRepository().search_players_by_name(query, limit=limit):
                uid = str(r["user_id"])
                if uid not in seen:
                    seen.add(uid)
                    players.append({"id": uid, "name": r.get("display_name")})
    except Exception as exc:
        logger.error("Public player search failed: %s", exc, exc_info=True)
        return _error("Could not search players", 500)
    return _respond({"success": True, "players": players[:limit], "terms_of_use": history.TERMS_URL},
                    max_age=300)
