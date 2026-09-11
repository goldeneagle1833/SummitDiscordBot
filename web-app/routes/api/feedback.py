"""Feedback API routes for community feedback submissions."""

from flask import Blueprint, jsonify, request, session

from repositories.feedback import FeedbackRepository
from utils.auth import require_admin, require_api_key

feedback_bp = Blueprint("feedback", __name__)


@feedback_bp.route("/feedback", methods=["POST"])
def submit_feedback():
    """Submit feedback (public, no login required)."""
    data = request.get_json(silent=True) or {}
    feedback_type = data.get("type", "general")
    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()

    if not title or not description:
        return jsonify({"error": "Title and description are required"}), 400

    if feedback_type not in FeedbackRepository.VALID_TYPES:
        return jsonify({"error": f"Invalid type. Must be one of: {', '.join(FeedbackRepository.VALID_TYPES)}"}), 400

    if len(title) > 200:
        return jsonify({"error": "Title must be 200 characters or less"}), 400
    if len(description) > 2000:
        return jsonify({"error": "Description must be 2000 characters or less"}), 400

    # Attach user info if logged in
    user_id = session.get("user_id")
    username = session.get("username")

    repo = FeedbackRepository()
    feedback_id = repo.create(
        type=feedback_type,
        title=title,
        description=description,
        user_id=str(user_id) if user_id else None,
        username=username,
    )

    return jsonify({"success": True, "id": feedback_id}), 201


@feedback_bp.route("/feedback", methods=["GET"])
@require_admin
def list_feedback():
    """List all feedback items (admin only)."""
    repo = FeedbackRepository()
    items = repo.get_all()
    return jsonify({"items": items})


@feedback_bp.route("/feedback/<int:feedback_id>/status", methods=["PATCH"])
@require_admin
def update_feedback_status(feedback_id):
    """Update feedback status and/or admin notes (admin only)."""
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    admin_notes = data.get("admin_notes")

    if status and status not in FeedbackRepository.VALID_STATUSES:
        return jsonify({"error": f"Invalid status. Must be one of: {', '.join(FeedbackRepository.VALID_STATUSES)}"}), 400

    repo = FeedbackRepository()
    item = repo.get_by_id(feedback_id)
    if not item:
        return jsonify({"error": "Feedback item not found"}), 404

    repo.update_status(feedback_id, status or item["status"], admin_notes)
    updated = repo.get_by_id(feedback_id)
    return jsonify({"success": True, "item": updated})


@feedback_bp.route("/feedback/<int:feedback_id>", methods=["DELETE"])
@require_admin
def delete_feedback(feedback_id):
    """Delete a feedback item (admin only)."""
    repo = FeedbackRepository()
    if not repo.delete(feedback_id):
        return jsonify({"error": "Feedback item not found"}), 404
    return jsonify({"success": True})


@feedback_bp.route("/feedback/pending-notifications", methods=["GET"])
@require_api_key
def get_pending_notifications():
    """Get resolved feedback needing Discord notification (bot polling)."""
    repo = FeedbackRepository()
    items = repo.get_pending_notifications()
    return jsonify({"items": items})


@feedback_bp.route("/feedback/<int:feedback_id>/mark-notified", methods=["POST"])
@require_api_key
def mark_feedback_notified(feedback_id):
    """Mark feedback as notified after bot sends DM."""
    repo = FeedbackRepository()
    repo.mark_notified(feedback_id)
    return jsonify({"success": True})
