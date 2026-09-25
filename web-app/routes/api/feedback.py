"""Feedback API routes for community feedback submissions."""

import csv
import io
import re

from flask import Blueprint, Response, jsonify, request, session

from repositories.feedback import FeedbackRepository
from repositories.season_feedback import SeasonFeedbackRepository
from services import season_feedback
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


# ---------------------------------------------------------------------------
# Post-season feedback survey
#
# The form is public: the link goes out in the season wrap-up announcement
# rather than in the site nav, and players shouldn't need to log in to answer.
# If they are logged in, the session identity is attached so admins can
# follow up on anything serious.
# ---------------------------------------------------------------------------


@feedback_bp.route("/season/form", methods=["GET"])
def get_season_feedback_form():
    """Question schema for the post-season feedback form (public)."""
    return jsonify(season_feedback.get_form())


@feedback_bp.route("/season", methods=["POST"])
def submit_season_feedback():
    """Submit a post-season feedback response (public, no login required)."""
    data = request.get_json(silent=True) or {}
    try:
        answers = season_feedback.validate_answers(data.get("answers") or {})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    user_id = session.get("user_id")
    username = session.get("username")

    repo = SeasonFeedbackRepository()
    response_id = repo.create(
        season=season_feedback.CURRENT_SEASON,
        answers=answers,
        user_id=str(user_id) if user_id else None,
        username=username,
    )
    return jsonify({"success": True, "id": response_id}), 201


@feedback_bp.route("/season/responses", methods=["GET"])
@require_admin
def list_season_feedback():
    """Responses for one season with per-question tallies (admin only)."""
    repo = SeasonFeedbackRepository()
    seasons = repo.list_seasons()
    season = request.args.get("season") or (seasons[0] if seasons else season_feedback.CURRENT_SEASON)
    responses = repo.list_responses(season)
    return jsonify({
        "season": season,
        "seasons": seasons,
        "current_season": season_feedback.CURRENT_SEASON,
        "sections": season_feedback.SECTIONS,
        "responses": responses,
        "summary": season_feedback.summarize(responses),
    })


@feedback_bp.route("/season/export.csv", methods=["GET"])
@require_admin
def export_season_feedback_csv():
    """Download responses as CSV, one column per question (admin only)."""
    repo = SeasonFeedbackRepository()
    season = request.args.get("season") or None
    responses = repo.list_responses(season)

    columns = season_feedback.csv_columns()
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for response in responses:
        writer.writerow(season_feedback.csv_row(response))

    slug = re.sub(r"[^a-z0-9]+", "-", (season or "all-seasons").lower()).strip("-")
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=season-feedback-{slug}.csv"},
    )


@feedback_bp.route("/season/<int:response_id>", methods=["DELETE"])
@require_admin
def delete_season_feedback(response_id):
    """Delete one survey response (admin only)."""
    repo = SeasonFeedbackRepository()
    if not repo.delete(response_id):
        return jsonify({"error": "Response not found"}), 404
    return jsonify({"success": True})
