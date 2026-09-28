"""Public proxy routes for Play Sorcery Online ranked analytics.

See ``services/ranked_analytics.py`` for what is and is not forwarded. Every
response is marked ``private, no-store``: replay links must not be cached
because a player can make a replay private at any time.
"""

import json
import logging
from urllib.parse import quote

from flask import Blueprint, jsonify, request

from services.ranked_analytics import (
    MAX_BODY_BYTES,
    AnalyticsUnavailable,
    InvalidSelection,
    build_catalog,
    claim_request,
    clean_selection,
    forward,
    validate_card_key,
)

ranked_analytics_bp = Blueprint("ranked_analytics", __name__)
logger = logging.getLogger(__name__)


def _client_key() -> str:
    forwarded = request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For", "")
    ip = forwarded.split(",")[0].strip() or request.remote_addr or "unknown"
    return f"ip:{ip}"


def _respond(status: int, body):
    response = jsonify(body)
    response.status_code = status
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _relay(method: str, route: str, *, params=None, body=None):
    if not claim_request(_client_key()):
        return _respond(429, {"error": "Too many analytics requests. Try again in a minute."})
    try:
        result = forward(method, route, params=params, body=body)
    except AnalyticsUnavailable as exc:
        return _respond(503, {"error": str(exc), "available": False})
    return _respond(result.status, result.body)


@ranked_analytics_bp.errorhandler(InvalidSelection)
def _invalid_selection(exc):
    return _respond(400, {"error": str(exc)})


@ranked_analytics_bp.route("/cards")
def cards():
    """Card share and win-rate table for a format and date range."""
    return _relay("GET", "cards", params=clean_selection(request.args))


@ranked_analytics_bp.route("/query-options")
def query_options():
    """Recorded card and avatar names for the query builder's suggestions."""
    return _relay("GET", "query-options", params=clean_selection(request.args))


@ranked_analytics_bp.route("/cards/<path:card_key>/replays")
def card_replays(card_key):
    """Currently public replay clips for one card. Never cached."""
    key = validate_card_key(card_key)
    return _relay("GET", f"cards/{quote(key, safe='')}/replays", params=clean_selection(request.args))


@ranked_analytics_bp.route("/cohort", methods=["POST"])
def cohort():
    """Cohort size and win rate for a nested query built in the browser."""
    if request.args:
        raise InvalidSelection("Query parameters are not accepted here")
    if not (request.content_type or "").startswith("application/json"):
        return _respond(415, {"error": "Expected a JSON body"})
    body = request.get_data()
    if len(body) > MAX_BODY_BYTES:
        return _respond(413, {"error": "Query is too large"})
    try:
        payload = json.loads(body)
    except ValueError:
        raise InvalidSelection("Expected a JSON object with a selection")
    if not isinstance(payload, dict) or not isinstance(payload.get("selection"), dict):
        raise InvalidSelection("Expected a JSON object with a selection")
    return _relay("POST", "cohort", body=body)


@ranked_analytics_bp.route("/catalog")
def catalog():
    """Card metadata and art for filters and detail rows. Local data only."""
    response = jsonify(build_catalog())
    response.headers["Cache-Control"] = "public, max-age=600"
    return response

