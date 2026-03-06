"""Admin API routes for player and match management."""

import logging

from flask import Blueprint, jsonify, request

from services.admin import AdminService
from utils.auth import require_admin

logger = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin/remove-player/<int:user_id>", methods=["DELETE"])
@require_admin
def remove_player(user_id):
    """Remove a player from overall_standings (admin only)."""
    service = AdminService()
    result = service.remove_player(user_id)
    status = 200 if result.get("success") else 404
    return jsonify(result), status


@admin_bp.route("/admin/remove-match/<int:match_id>", methods=["DELETE"])
@require_admin
def remove_match(match_id):
    """Remove a match record and reverse ELO changes (admin only)."""
    service = AdminService()
    result = service.remove_match(match_id)
    status = 200 if result.get("success") else 404
    return jsonify(result), status


@admin_bp.route("/admin/reset-elo/<int:user_id>", methods=["POST"])
@require_admin
def reset_elo(user_id):
    """Reset a player's ELO to 1500 (admin only)."""
    service = AdminService()
    result = service.reset_player_elo(user_id)
    status = 200 if result.get("success") else 404
    return jsonify(result), status


@admin_bp.route("/admin/rename-player/<int:user_id>", methods=["POST"])
@require_admin
def rename_player(user_id):
    """Rename a player's display name (admin only)."""
    data = request.get_json(silent=True)
    if not data or not data.get("new_name"):
        return jsonify({"success": False, "error": "new_name is required"}), 400

    new_name = str(data["new_name"]).strip()
    if not new_name or len(new_name) > 100:
        return jsonify({"success": False, "error": "Invalid name (1-100 characters)"}), 400

    service = AdminService()
    result = service.rename_player(user_id, new_name)
    status = 200 if result.get("success") else 404
    return jsonify(result), status
