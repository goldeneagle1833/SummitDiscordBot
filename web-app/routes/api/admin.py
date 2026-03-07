"""Admin API routes for player and match management."""

import logging

from flask import Blueprint, jsonify, request, session

from services.admin import AdminService
from repositories.audit import AuditRepository
from utils.auth import require_admin

logger = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__)


def _get_admin_info():
    """Get the current admin's ID and name from the session."""
    admin_id = session.get("user_id", 0)
    admin_name = session.get("username", "API/localhost")
    return admin_id, admin_name


@admin_bp.route("/admin/remove-player/<int:user_id>", methods=["DELETE"])
@require_admin
def remove_player(user_id):
    """Remove a player from overall_standings (admin only)."""
    service = AdminService()
    # Capture previous state before removal
    current_elo = service._elo_repo.get_user_elo(user_id)
    result = service.remove_player(user_id)
    if result.get("success"):
        admin_id, admin_name = _get_admin_info()
        audit = AuditRepository()
        audit.log_action(
            admin_id, admin_name, "web_remove_player",
            target_id=str(user_id),
            previous_state={"elo": current_elo},
            new_state={"result": "player removed from standings"},
            details=f"Removed player {user_id} from standings (ELO was {current_elo})",
        )
    status = 200 if result.get("success") else 404
    return jsonify(result), status


@admin_bp.route("/admin/remove-match/<int:match_id>", methods=["DELETE"])
@require_admin
def remove_match(match_id):
    """Remove a match record and reverse ELO changes (admin only)."""
    service = AdminService()
    # Capture match details before removal
    match = service._match_repo.get_match_full_details(match_id)
    result = service.remove_match(match_id)
    if result.get("success") and match:
        admin_id, admin_name = _get_admin_info()
        audit = AuditRepository()
        audit.log_action(
            admin_id, admin_name, "web_remove_match",
            target_id=str(match_id),
            previous_state={
                "winner_id": str(match.get("winner_id")),
                "winner_name": match.get("winner_name"),
                "loser_id": str(match.get("loser_id")),
                "loser_name": match.get("loser_name"),
            },
            new_state={"result": "match deleted, ELO reversed"},
            details=f"Removed match #{match_id}: {match.get('winner_name')} vs {match.get('loser_name')}",
        )
    status = 200 if result.get("success") else 404
    return jsonify(result), status


@admin_bp.route("/admin/reset-elo/<int:user_id>", methods=["POST"])
@require_admin
def reset_elo(user_id):
    """Reset a player's ELO to a specified value (admin only)."""
    data = request.get_json(silent=True)
    new_elo = 1500
    if data and data.get("new_elo") is not None:
        try:
            new_elo = int(data["new_elo"])
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "new_elo must be a number"}), 400
        if new_elo < 0 or new_elo > 5000:
            return jsonify({"success": False, "error": "ELO must be between 0 and 5000"}), 400

    service = AdminService()
    current_elo = service._elo_repo.get_user_elo(user_id)
    result = service.reset_player_elo(user_id, new_elo)
    if result.get("success"):
        admin_id, admin_name = _get_admin_info()
        audit = AuditRepository()
        audit.log_action(
            admin_id, admin_name, "web_reset_elo",
            target_id=str(user_id),
            previous_state={"elo": current_elo},
            new_state={"elo": new_elo},
            details=f"Reset ELO for player {user_id}: {current_elo} -> {new_elo}",
        )
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
    if result.get("success"):
        admin_id, admin_name = _get_admin_info()
        audit = AuditRepository()
        audit.log_action(
            admin_id, admin_name, "web_rename_player",
            target_id=str(user_id),
            new_state={"new_name": new_name},
            details=f"Renamed player {user_id} to '{new_name}'",
        )
    status = 200 if result.get("success") else 404
    return jsonify(result), status
