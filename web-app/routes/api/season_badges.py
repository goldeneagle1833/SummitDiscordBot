"""Season honours: avatar top-three tags, plus the partner (PSO) badges API.

GET /api/avatar-honours is what profiles read. The partner endpoint puts those
together with the postseason bracket finishes (Champion, Finalist, Top 4,
Top 8, Top cut) so Play Sorcery Online can show every season badge a player
holds from one call, with the same API key as /api/report-external-match.
"""

import logging
import re

from flask import Blueprint, jsonify, request

from services import avatar_honours
from services.brackets import BracketService
from utils.api_auth import require_integration_api_key

logger = logging.getLogger(__name__)

season_badges_bp = Blueprint("season_badges", __name__)

MAX_USER_IDS = 200

# "Gothic Season 6 Postseason Bracket" -> "Gothic Season 6"
_BRACKET_SUFFIX = re.compile(
    r"\s+(?:limited\s+)?(?:postseason\s+bracket|postseason|top\s*cut|top\s*8|bracket)\s*$",
    re.IGNORECASE,
)


def bracket_season(bracket: dict) -> str:
    """The season a bracket belongs to, for titles like 'Gothic Season 6 Champion'."""
    if bracket.get("elo_event_name"):
        return bracket["elo_event_name"]
    name = bracket.get("name") or ""
    return _BRACKET_SUFFIX.sub("", name).strip() or name


@season_badges_bp.route("/avatar-honours", methods=["GET"])
def get_avatar_honours():
    """Top three per avatar for every ended season, keyed by player id."""
    try:
        return jsonify({"success": True, "honours": avatar_honours.get_honours_by_player()}), 200
    except Exception as e:
        logger.error("Failed to load avatar honours: %s", e, exc_info=True)
        # Profiles should still render without their decorations.
        return jsonify({"success": True, "honours": {}}), 200


def _bracket_badges() -> dict:
    """{user_id: [bracket badge, ...]} from every finished published bracket."""
    service = BracketService()
    by_slug = {b["slug"]: b for b in service._repo.list_brackets(published_only=True)}
    badges = {}
    for user_id, marks in service.get_player_marks().items():
        for entry in marks["entries"]:
            bracket = by_slug.get(entry["slug"], {})
            season = bracket_season({**bracket, "name": entry["name"]})
            badges.setdefault(user_id, []).append(
                {
                    "season": season,
                    "bracket": entry["name"],
                    "bracket_slug": entry["slug"],
                    "format": entry["format"],
                    "placement": entry["placement"],
                    "label": entry["label"],
                    "finish": entry["finish"],
                    "title": f"{season} {entry['label']}",
                    "completed_at": bracket.get("completed_at"),
                }
            )
    return badges


def _avatar_badges() -> dict:
    keep = ("season", "season_id", "avatar", "place", "label", "title",
            "wins", "losses", "games", "avatar_score")
    return {
        user_id: [{k: h[k] for k in keep} for h in honours]
        for user_id, honours in avatar_honours.get_honours_by_player().items()
    }


def _player_payload(user_id, brackets, avatars) -> dict:
    return {
        "user_id": user_id,
        "brackets": brackets.get(user_id, []),
        "avatar_honours": avatars.get(user_id, []),
    }


@season_badges_bp.route("/partner/season-badges", methods=["GET"])
@require_integration_api_key
def get_partner_season_badges():
    """Every season badge a player holds: bracket finishes and avatar top three.

    ?user_id=<id>[,<id>...] narrows to those players (up to 200). Without it,
    every player who holds at least one badge is returned.
    """
    raw = request.args.get("user_id", "").strip()
    wanted = [u.strip() for u in raw.split(",") if u.strip()] if raw else None
    if wanted and len(wanted) > MAX_USER_IDS:
        return jsonify({"success": False, "error": f"At most {MAX_USER_IDS} user_ids per call"}), 400

    brackets = _bracket_badges()
    avatars = _avatar_badges()
    if wanted is None:
        wanted = sorted(set(brackets) | set(avatars))
    players = [_player_payload(u, brackets, avatars) for u in wanted]
    return jsonify({"success": True, "players": players}), 200
