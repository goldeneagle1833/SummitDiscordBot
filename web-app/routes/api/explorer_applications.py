"""Explorer Series host application API routes.

Public side: a logged-in Discord user submits one application to host an
Explorer Series event. Admin side: Explorer admins review applications on a
map, score them on three criteria, leave notes and approve or reject.
"""

import csv
import io
import logging
import threading

from flask import Blueprint, Response, jsonify, request, session

from repositories.explorer_applications import (
    APPLICATION_FIELDS,
    SCORE_FIELDS,
    STATUSES,
    ExplorerApplicationRepository,
)
from services.geocoding import geocode_location
from services.explorer_notifications import (
    notify_new_application_in_background,
)
from utils.auth import require_auth, require_explorer_admin

logger = logging.getLogger(__name__)

explorer_applications_bp = Blueprint("explorer_applications", __name__)

REQUIRED_FIELDS = ("first_name", "last_name", "email", "city", "state", "lgs_name")

MAX_FIELD_LENGTH = 5000


def _current_user():
    return str(session.get("user_id", "")), session.get("username")


def _clean(value) -> str:
    if value is None:
        return ""
    return str(value).strip()[:MAX_FIELD_LENGTH]


def _collect_fields(data: dict) -> dict:
    """Pull the known application fields out of a request body."""
    fields = {}
    for name in APPLICATION_FIELDS:
        if name not in data:
            continue
        if name == "read_navigator_role":
            fields[name] = 1 if data[name] else 0
        elif name == "events_run_count":
            try:
                fields[name] = int(data[name]) if data[name] not in (None, "") else None
            except (TypeError, ValueError):
                fields[name] = None
        else:
            fields[name] = _clean(data[name])
    return fields


def _geocode_in_background(application_id: int, city, state, country):
    """Resolve coordinates off the request path.

    Nominatim is rate limited and can be slow, and the app runs on a small
    number of sync workers — blocking a submission on it would tie one up.
    If this fails the row simply has no pin, and an admin can retry from the
    review page.
    """
    def run():
        try:
            coords = geocode_location(city, state, country)
            if coords:
                ExplorerApplicationRepository().set_coordinates(application_id, *coords)
        except Exception:
            logger.exception("Background geocoding failed for application %s", application_id)

    threading.Thread(target=run, daemon=True).start()


# ── Public (logged-in applicant) ──────────────────────────────────────────────


@explorer_applications_bp.route("", methods=["POST"])
@require_auth
def submit_application():
    """Submit an Explorer Series host application. Requires a Discord login."""
    user_id, username = _current_user()
    if not user_id:
        return jsonify({"success": False, "error": "You must be logged in to apply"}), 401
    if session.get("auth_provider") != "discord":
        return jsonify({
            "success": False,
            "error": "Explorer applications require a Discord login",
        }), 403

    data = request.get_json(silent=True) or {}
    fields = _collect_fields(data)

    missing = [name for name in REQUIRED_FIELDS if not fields.get(name)]
    if missing:
        return jsonify({
            "success": False,
            "error": f"Missing required field(s): {', '.join(missing)}",
        }), 400

    if not fields.get("read_navigator_role"):
        return jsonify({
            "success": False,
            "error": "Please confirm you have read the Navigator role summary",
        }), 400

    repo = ExplorerApplicationRepository()
    if repo.get_by_discord_user(user_id):
        return jsonify({
            "success": False,
            "error": "You have already submitted an application. Contact an Explorer"
                     " admin if you need to change it.",
        }), 409

    fields.setdefault("discord_handle", username or "")
    application_id = repo.create_application(user_id, fields, source="application")

    _geocode_in_background(
        application_id, fields.get("city"), fields.get("state"), fields.get("country")
    )
    notify_new_application_in_background({**fields, "id": application_id})

    return jsonify({"success": True, "application_id": application_id}), 201


@explorer_applications_bp.route("/mine", methods=["GET"])
@require_auth
def my_application():
    """Return the logged-in user's own application, if they have one."""
    user_id, _ = _current_user()
    if not user_id:
        return jsonify({"success": True, "application": None}), 200

    application = ExplorerApplicationRepository().get_by_discord_user(user_id)
    return jsonify({"success": True, "application": application}), 200


# ── Explorer admin review ─────────────────────────────────────────────────────


@explorer_applications_bp.route("", methods=["GET"])
@require_explorer_admin
def list_applications():
    """List every application with vote aggregates, for the review board."""
    status = request.args.get("status") or None
    if status and status not in STATUSES:
        return jsonify({"success": False, "error": f"Unknown status '{status}'"}), 400

    applications = ExplorerApplicationRepository().list_applications(status)
    return jsonify({"success": True, "applications": applications}), 200


@explorer_applications_bp.route("/<int:application_id>", methods=["GET"])
@require_explorer_admin
def get_application(application_id):
    """Full detail for one application, with every reviewer's scores and notes."""
    repo = ExplorerApplicationRepository()
    application = repo.get_application(application_id)
    if not application:
        return jsonify({"success": False, "error": "Application not found"}), 404

    return jsonify({
        "success": True,
        "application": application,
        "votes": repo.get_votes(application_id),
        "comments": repo.get_comments(application_id),
    }), 200


@explorer_applications_bp.route("/<int:application_id>/vote", methods=["POST"])
@require_explorer_admin
def vote_application(application_id):
    """Record the current admin's 1-5 scores for an application."""
    repo = ExplorerApplicationRepository()
    if not repo.get_application(application_id):
        return jsonify({"success": False, "error": "Application not found"}), 404

    data = request.get_json(silent=True) or {}
    scores = {}
    for field in SCORE_FIELDS:
        raw = data.get(field)
        if raw in (None, ""):
            scores[field] = None
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": f"{field} must be a number 1-5"}), 400
        if not 1 <= value <= 5:
            return jsonify({"success": False, "error": f"{field} must be between 1 and 5"}), 400
        scores[field] = value

    voter_id, voter_name = _current_user()
    repo.upsert_vote(application_id, voter_id, voter_name, scores)

    return jsonify({
        "success": True,
        "votes": repo.get_votes(application_id),
    }), 200


@explorer_applications_bp.route("/<int:application_id>/status", methods=["POST"])
@require_explorer_admin
def set_status(application_id):
    """Move an application through pending / pre-approved / approved / rejected."""
    data = request.get_json(silent=True) or {}
    status = _clean(data.get("status"))
    if status not in STATUSES:
        return jsonify({
            "success": False,
            "error": f"status must be one of: {', '.join(STATUSES)}",
        }), 400

    repo = ExplorerApplicationRepository()
    if not repo.update_status(application_id, status):
        return jsonify({"success": False, "error": "Application not found"}), 404

    _, admin_name = _current_user()
    logger.info("Explorer application %s set to %s by %s", application_id, status, admin_name)
    return jsonify({"success": True, "status": status}), 200


@explorer_applications_bp.route("/<int:application_id>/comments", methods=["POST"])
@require_explorer_admin
def add_comment(application_id):
    """Leave a note on an application for the other Explorer admins."""
    repo = ExplorerApplicationRepository()
    if not repo.get_application(application_id):
        return jsonify({"success": False, "error": "Application not found"}), 404

    body = _clean((request.get_json(silent=True) or {}).get("body"))
    if not body:
        return jsonify({"success": False, "error": "Comment body is required"}), 400

    author_id, author_name = _current_user()
    repo.add_comment(application_id, author_id, author_name, body)
    return jsonify({"success": True, "comments": repo.get_comments(application_id)}), 201


@explorer_applications_bp.route("/candidates", methods=["POST"])
@require_explorer_admin
def add_candidate():
    """Add a prospective Navigator by Discord handle before they've applied.

    These rows carry no discord_user_id, so the person can still submit a real
    application later without colliding with the placeholder.
    """
    data = request.get_json(silent=True) or {}
    fields = _collect_fields(data)

    if not fields.get("discord_handle") and not fields.get("first_name"):
        return jsonify({
            "success": False,
            "error": "A Discord handle or a first name is required",
        }), 400

    _, admin_name = _current_user()
    repo = ExplorerApplicationRepository()
    application_id = repo.create_application(
        None, fields, source="admin_added", created_by=admin_name
    )

    if fields.get("city") or fields.get("state"):
        _geocode_in_background(
            application_id, fields.get("city"), fields.get("state"), fields.get("country")
        )

    return jsonify({"success": True, "application_id": application_id}), 201


@explorer_applications_bp.route("/<int:application_id>", methods=["DELETE"])
@require_explorer_admin
def delete_application(application_id):
    """Remove an application or candidate row."""
    if not ExplorerApplicationRepository().delete_application(application_id):
        return jsonify({"success": False, "error": "Application not found"}), 404
    return jsonify({"success": True}), 200


@explorer_applications_bp.route("/<int:application_id>/geocode", methods=["POST"])
@require_explorer_admin
def regeocode(application_id):
    """Retry geocoding for an application whose pin is missing.

    Runs inline so the admin sees the outcome immediately.
    """
    repo = ExplorerApplicationRepository()
    application = repo.get_application(application_id)
    if not application:
        return jsonify({"success": False, "error": "Application not found"}), 404

    coords = geocode_location(
        application.get("city"), application.get("state"), application.get("country")
    )
    if not coords:
        return jsonify({
            "success": False,
            "error": "Could not find that location. Check the city and state.",
        }), 404

    repo.set_coordinates(application_id, *coords)
    return jsonify({"success": True, "latitude": coords[0], "longitude": coords[1]}), 200


CSV_COLUMNS = (
    "id", "status", "source", "first_name", "last_name", "discord_handle", "email",
    "city", "state", "country", "lgs_name", "lgs_url", "lgs_confirmed",
    "expected_attendance", "proposed_dates", "events_run_count", "avg_headcount",
    "events_run", "motivation", "reference_contact", "anything_else", "referral",
    "vote_count", "avg_enthusiasm", "avg_track_record", "avg_local_activity",
    "average_score", "submitted_at",
)


@explorer_applications_bp.route("/export.csv", methods=["GET"])
@require_explorer_admin
def export_csv():
    """Download every application with its scores as CSV."""
    applications = ExplorerApplicationRepository().list_applications()

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for application in applications:
        writer.writerow({key: application.get(key, "") for key in CSV_COLUMNS})

    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=explorer-applications.csv"},
    )
