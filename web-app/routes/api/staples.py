"""Open API: the 100 staple cards of Summit ranked play.

GET /api/staples is open to everybody: no login and no API key (it is on the
site gate's exempt list). It spends Play Sorcery Online's capacity, so each
visitor is throttled and every date range is cached for 10 minutes.
See services/staples.py for the score. Aggregate card stats only: no deck
lists, no players.
"""

import logging
import re

from flask import Blueprint, jsonify, request

from services import ranked_analytics, staples

logger = logging.getLogger(__name__)

staples_bp = Blueprint("staples", __name__)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_WORD_RE = re.compile(r"^[A-Za-z ]{1,30}$")


def _error(message, status=400):
    return jsonify({"success": False, "error": message}), status


def _client_key() -> str:
    forwarded = request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For", "")
    ip = forwarded.split(",")[0].strip() or request.remote_addr or "unknown"
    return f"staples:{ip}"


@staples_bp.route("/staples", methods=["GET"])
def get_staples():
    """Top staple cards (default and max 100).

    Query params (all optional):
        season: "all" or a Summit season id (from /api/ranked-analytics/seasons)
        from, through: YYYY-MM-DD range (ignored when season is given)
        limit: 1-100 (default 100)
        min_games: in-deck games a card needs (default 50)
        type: Minion, Magic, Site, Aura, Artifact... (case-insensitive)
        element: Air, Earth, Fire, Water, None or Multi
    Without season/from/through, the last 90 days of released data.
    """
    if not ranked_analytics.claim_request(_client_key()):
        return _error("Too many requests. Try again in a minute.", 429)
    args = request.args
    limit = args.get("limit", staples.DEFAULT_LIMIT, type=int)
    if limit is None or not 1 <= limit <= staples.MAX_LIMIT:
        return _error(f"limit must be 1-{staples.MAX_LIMIT}")
    min_games = args.get("min_games", staples.DEFAULT_MIN_GAMES, type=int)
    if min_games is None or not 1 <= min_games <= 100000:
        return _error("min_games must be a positive integer")
    from_, through = (args.get("from") or "").strip(), (args.get("through") or "").strip()
    for name, value in (("from", from_), ("through", through)):
        if value and not _DATE_RE.match(value):
            return _error(f"{name} must be a YYYY-MM-DD date")
    if from_ and through and from_ > through:
        return _error("from must be on or before through")
    card_type, element = (args.get("type") or "").strip(), (args.get("element") or "").strip()
    for name, value in (("type", card_type), ("element", element)):
        if value and not _WORD_RE.match(value):
            return _error(f"Invalid {name}")
    try:
        window = staples.resolve_window((args.get("season") or "").strip() or None, from_ or None, through or None)
    except ValueError as exc:
        return _error(str(exc))
    try:
        data = staples.get_staples(window, limit=limit, min_games=min_games,
                                   card_type=card_type or None, element=element or None)
    except staples.StaplesUnavailable as exc:
        return jsonify({"success": False, "available": False, "error": str(exc)}), 503
    except Exception as exc:
        logger.error("Could not build staples: %s", exc, exc_info=True)
        return _error("Could not build staples", 500)
    response = jsonify({"success": True, **data})
    response.headers["Cache-Control"] = "public, max-age=300"
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response
