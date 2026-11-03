"""Partner API: the 100 staple cards of Summit ranked play.

GET /api/partner/staples, with the same API key as /api/partner/season-badges.
See services/staples.py for the score. Aggregate card stats only: no deck
lists, no players.
"""

import logging
import re

from flask import Blueprint, jsonify, request

from services import staples
from utils.api_auth import require_integration_api_key

logger = logging.getLogger(__name__)

staples_bp = Blueprint("staples", __name__)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_WORD_RE = re.compile(r"^[A-Za-z ]{1,30}$")


def _error(message, status=400):
    return jsonify({"success": False, "error": message}), status


@staples_bp.route("/partner/staples", methods=["GET"])
@require_integration_api_key
def get_partner_staples():
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
    response.headers["Cache-Control"] = "private, max-age=300"
    return response
