"""API routes for user-created seasons."""

import logging

from flask import Blueprint, jsonify, request, session

from services.seasons import SeasonsService
from utils.auth import require_auth

logger = logging.getLogger(__name__)

seasons_bp = Blueprint("seasons", __name__)
service = SeasonsService()


# ── US1: Create Season ───────────────────────────────────────────


@seasons_bp.route("/seasons", methods=["POST"])
@require_auth
def create_season():
    data = request.get_json() or {}
    user_id = str(session.get("user_id", ""))
    display_name = session.get("username", "Unknown")

    title = data.get("title")
    description = data.get("description")
    start_date = data.get("start_date")
    end_date = data.get("end_date")
    k_value = data.get("k_value", 32)
    base_elo = data.get("base_elo", 1500)
    max_members = data.get("max_members")
    region = data.get("region")

    try:
        season_id = service.create_season(
            user_id, display_name, title, description,
            start_date, end_date, k_value, base_elo,
            max_members, region,
        )
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400

    return jsonify({
        "success": True,
        "season_id": season_id,
        "title": title.strip(),
        "start_date": start_date,
        "end_date": end_date,
        "message": "Season created successfully. You have been automatically enrolled.",
    }), 201


# ── US2: Search / Join Season ────────────────────────────────────


@seasons_bp.route("/seasons/search", methods=["GET"])
@require_auth
def search_seasons():
    q = request.args.get("q", "").strip()
    user_id = str(session.get("user_id", ""))
    limit = request.args.get("limit", type=int)
    seasons = service.search_seasons(q, user_id)
    if limit and limit > 0:
        seasons = seasons[-limit:]
    return jsonify({"success": True, "seasons": seasons}), 200


@seasons_bp.route("/seasons/browse", methods=["GET"])
def browse_seasons():
    """Public endpoint for browsing/searching seasons (no auth required)."""
    q = request.args.get("q", "").strip()
    seasons = service.search_seasons(q, user_id="", include_ended=True)
    return jsonify({"success": True, "seasons": seasons}), 200


@seasons_bp.route("/seasons/<int:season_id>", methods=["GET"])
def get_season(season_id):
    """Public endpoint returning season info + members as a leaderboard."""
    season = service.repo.get_season_by_id(season_id)
    if not season:
        return jsonify({"success": False, "error": "Season not found"}), 404

    members = service.get_season_members(season_id)
    leaderboard = [
        {
            "id": m["user_id"],
            "name": m["display_name"],
            "elo": m["season_elo"],
            "wins": m["wins"],
            "losses": m["losses"],
            "rank": m["rank"],
            "is_creator": m["is_creator"],
        }
        for m in members
    ]
    return jsonify({
        "success": True,
        "season_id": season_id,
        "title": season["title"],
        "description": season["description"],
        "start_date": season["start_date"],
        "end_date": season["end_date"],
        "region": season["region"],
        "status": season["status"],
        "creator_display_name": season["creator_display_name"],
        "leaderboard": leaderboard,
    }), 200


@seasons_bp.route("/seasons/<int:season_id>/join", methods=["POST"])
@require_auth
def join_season(season_id):
    user_id = str(session.get("user_id", ""))
    display_name = session.get("username", "Unknown")
    try:
        service.join_season(user_id, display_name, season_id)
    except ValueError as e:
        msg = str(e)
        if "full" in msg.lower():
            return jsonify({"success": False, "error": msg}), 409
        if "not found" in msg.lower():
            return jsonify({"success": False, "error": msg}), 404
        return jsonify({"success": False, "error": msg}), 400

    season = service.repo.get_season_by_id(season_id)
    return jsonify({
        "success": True,
        "season_id": season_id,
        "title": season["title"] if season else "",
        "message": "Successfully joined the season",
    }), 200


# ── US5: Player Season / Leave ───────────────────────────────────


@seasons_bp.route("/player/<player_id>/seasons", methods=["GET"])
def get_player_seasons(player_id):
    seasons = service.get_player_seasons(player_id)
    return jsonify({"success": True, "seasons": seasons}), 200


@seasons_bp.route("/seasons/<int:season_id>/leave", methods=["POST"])
@require_auth
def leave_season(season_id):
    user_id = str(session.get("user_id", ""))
    try:
        service.leave_season(user_id, season_id)
    except ValueError as e:
        msg = str(e)
        if "cannot leave" in msg.lower() or "creators cannot" in msg.lower():
            return jsonify({"success": False, "error": msg}), 400
        if "not a member" in msg.lower():
            return jsonify({"success": False, "error": msg}), 404
        return jsonify({"success": False, "error": msg}), 400

    return jsonify({"success": True, "message": "You have left the season"}), 200


# ── US4: Season Management (Creator) ────────────────────────────


@seasons_bp.route("/seasons/<int:season_id>", methods=["PUT"])
@require_auth
def modify_season(season_id):
    data = request.get_json() or {}
    user_id = str(session.get("user_id", ""))

    fields = {}
    for key in ("start_date", "end_date", "description", "k_value",
                "max_members", "region"):
        if key in data:
            fields[key] = data[key]

    if not fields:
        return jsonify({"success": False, "error": "At least one field is required"}), 400

    try:
        service.modify_season(user_id, season_id, **fields)
    except ValueError as e:
        msg = str(e)
        if "only the season creator" in msg.lower():
            return jsonify({"success": False, "error": msg}), 403
        return jsonify({"success": False, "error": msg}), 400

    return jsonify({"success": True, "message": "Season updated"}), 200


@seasons_bp.route("/seasons/<int:season_id>/end", methods=["POST"])
@require_auth
def end_season(season_id):
    user_id = str(session.get("user_id", ""))
    try:
        service.end_season(user_id, season_id)
    except ValueError as e:
        msg = str(e)
        if "only the season creator" in msg.lower():
            return jsonify({"success": False, "error": msg}), 403
        return jsonify({"success": False, "error": msg}), 400

    return jsonify({"success": True, "message": "Season has been ended"}), 200


@seasons_bp.route("/seasons/<int:season_id>", methods=["DELETE"])
@require_auth
def delete_season(season_id):
    user_id = str(session.get("user_id", ""))
    try:
        service.delete_season(user_id, season_id)
    except ValueError as e:
        msg = str(e)
        if "only the season creator" in msg.lower():
            return jsonify({"success": False, "error": msg}), 403
        return jsonify({"success": False, "error": msg}), 400

    return jsonify({"success": True, "message": "Season has been deleted"}), 200


@seasons_bp.route("/seasons/<int:season_id>/kick", methods=["POST"])
@require_auth
def kick_member(season_id):
    data = request.get_json() or {}
    creator_id = str(session.get("user_id", ""))
    target_user_id = data.get("user_id")

    if not target_user_id:
        return jsonify({"success": False, "error": "user_id is required"}), 400

    try:
        service.kick_member(creator_id, season_id, target_user_id)
    except ValueError as e:
        msg = str(e)
        if "only the season creator" in msg.lower():
            return jsonify({"success": False, "error": msg}), 403
        if "cannot kick yourself" in msg.lower():
            return jsonify({"success": False, "error": msg}), 400
        return jsonify({"success": False, "error": msg}), 400

    return jsonify({
        "success": True,
        "message": "Member has been removed from the season",
        "kicked_user_id": target_user_id,
    }), 200


@seasons_bp.route("/seasons/<int:season_id>/report-match", methods=["POST"])
@require_auth
def report_season_match(season_id):
    data = request.get_json() or {}
    creator_id = str(session.get("user_id", ""))
    winner_id = data.get("winner_id")
    loser_id = data.get("loser_id")

    if not winner_id or not loser_id:
        return jsonify({"success": False, "error": "Winner and loser are required"}), 400

    if str(winner_id) == str(loser_id):
        return jsonify({"success": False, "error": "Winner and loser must be different players"}), 400

    try:
        result = service.report_match_as_creator(
            creator_id, season_id, winner_id, loser_id
        )
    except ValueError as e:
        msg = str(e)
        if "only the season creator" in msg.lower():
            return jsonify({"success": False, "error": msg}), 403
        return jsonify({"success": False, "error": msg}), 400
    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e)}), 500

    return jsonify({
        "success": True,
        "match_id": result["match_id"],
        "message": result["message"],
        "is_repeat_matchup": result.get("is_repeat_matchup", False),
    }), 201


@seasons_bp.route("/seasons/<int:season_id>/members", methods=["GET"])
def get_season_members(season_id):
    season = service.repo.get_season_by_id(season_id)
    if not season:
        return jsonify({"success": False, "error": "Season not found"}), 404

    members = service.get_season_members(season_id)
    return jsonify({
        "success": True,
        "season_id": season_id,
        "title": season["title"],
        "description": season["description"],
        "start_date": season["start_date"],
        "end_date": season["end_date"],
        "region": season["region"],
        "creator_display_name": season["creator_display_name"],
        "status": season["status"],
        "members": members,
    }), 200
