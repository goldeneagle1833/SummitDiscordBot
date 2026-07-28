"""API routes for event deck management."""

import json
import logging
import os
import tempfile
import threading
import uuid

from flask import Blueprint, jsonify, request

from repositories.events import EventRepository
from utils.auth import is_admin, require_admin
from utils.formatting import format_event_name

# File-based job store for background Curiosa fetching.
# Using files instead of an in-memory dict so that jobs are visible
# across multiple Gunicorn worker processes.
_JOBS_DIR = os.path.join(tempfile.gettempdir(), "summit_event_jobs")
os.makedirs(_JOBS_DIR, exist_ok=True)


def _job_path(job_id):
    """Return the filesystem path for a job's status file."""
    # Sanitise to prevent path traversal
    safe_id = job_id.replace(os.sep, "").replace("/", "").replace("..", "")
    return os.path.join(_JOBS_DIR, f"{safe_id}.json")


def _write_job(job_id, data):
    """Atomically write job status to disk."""
    path = _job_path(job_id)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def _read_job(job_id):
    """Read job status from disk, or return None."""
    path = _job_path(job_id)
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _delete_job(job_id):
    """Remove a job status file."""
    try:
        os.remove(_job_path(job_id))
    except FileNotFoundError:
        pass

logger = logging.getLogger(__name__)

events_bp = Blueprint("events", __name__)


@events_bp.route("/top-8-events")
def list_top8_events():
    """Return all top-8 event folders with metadata."""
    try:
        repo = EventRepository()
        events = repo.get_all_events()
        featured = repo.get_featured_event()
        return jsonify({"events": events, "is_admin": is_admin(), "featured_event": featured})
    except Exception as e:
        logger.exception("Error listing events: %s", e)
        return jsonify({"error": "Failed to load events"}), 500


@events_bp.route("/events/<event_folder>")
def get_event_detail(event_folder: str):
    """Return deck tables, card stats, and element charts for a single event."""
    try:
        repo = EventRepository()
        decks = repo.get_event_decks(event_folder)
        if decks is None:
            return jsonify({"error": "Event not found"}), 404

        stats = repo.get_event_stats(event_folder)
        element_stats = repo.get_event_element_stats(event_folder)
        element_stats_by_group = repo.get_event_element_stats_by_group(event_folder)
        description = repo.get_event_description(event_folder)

        return jsonify({
            "event_name": format_event_name(event_folder),
            "event_folder": event_folder,
            "description": description,
            "top8_decks": decks["top8_decks"],
            "all_decks": decks["all_decks"],
            "card_data": stats["card_data"] if stats else [],
            "top8_card_data": stats["top8_card_data"] if stats else [],
            "element_stats": element_stats,
            "element_stats_by_group": element_stats_by_group,
            "is_admin": is_admin(),
        })
    except Exception as e:
        logger.exception("Error loading event %s: %s", event_folder, e)
        return jsonify({"error": "Failed to load event data"}), 500


@events_bp.route("/events/<event_folder>/metadata", methods=["PUT"])
@require_admin
def update_event_metadata(event_folder):
    """Update display name and/or star rating for an event (admin only)."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Request body required"}), 400

    name = data.get("name")
    rating = data.get("rating")
    description = data.get("description")
    event_date = data.get("event_date")

    if name is not None and (not isinstance(name, str) or not name.strip()):
        return jsonify({"success": False, "error": "Name must be a non-empty string"}), 400

    if rating is not None:
        if not isinstance(rating, int) or rating < 1 or rating > 3:
            return jsonify({"success": False, "error": "Rating must be 1, 2, or 3"}), 400

    if description is not None and not isinstance(description, str):
        return jsonify({"success": False, "error": "Description must be a string"}), 400

    repo = EventRepository()
    result = repo.update_event_metadata(
        event_folder,
        name=name.strip() if name else None,
        rating=rating,
        description=description.strip() if description else description,
        event_date=event_date.strip() if isinstance(event_date, str) else event_date,
    )

    status = 200 if result.get("success") else 400
    return jsonify(result), status


@events_bp.route("/events/<event_folder>/reorder", methods=["POST"])
@require_admin
def reorder_event_decks(event_folder):
    """Reorder decks in an event's JSON file (admin only)."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Request body required"}), 400

    table_type = data.get("table")
    if table_type not in ("top8", "all"):
        return jsonify({"success": False, "error": "table must be 'top8' or 'all'"}), 400

    new_order = data.get("order")
    if not isinstance(new_order, list) or not all(isinstance(i, int) for i in new_order):
        return jsonify({"success": False, "error": "order must be a list of integers"}), 400

    repo = EventRepository()
    result = repo.reorder_event_decks(event_folder, table_type, new_order)

    status = 200 if result.get("success") else 400
    return jsonify(result), status


def _run_event_creation(job_id, title, valid_ranked, valid_bulk):
    """Background worker for event creation — fetches from Curiosa and saves."""
    try:
        from services.curiosa import CuriosaService
        curiosa = CuriosaService()

        errors = []
        top8_decks = []
        bulk_decks = []

        total_batches = 0
        if valid_ranked:
            total_batches += max(1, -(-len(valid_ranked) // 10))
        if valid_bulk:
            total_batches += max(1, -(-len(valid_bulk) // 10))

        completed_batches = [0]

        # Monkey-patch the rate_limit to update progress
        original_rate_limit = curiosa._rate_limit
        def _tracking_rate_limit():
            original_rate_limit()
            completed_batches[0] += 1
            _write_job(job_id, {"status": "processing", "progress": f"Fetching batch {completed_batches[0]}/{total_batches}"})
        curiosa._rate_limit = _tracking_rate_limit

        if valid_ranked:
            top8_decks, ranked_errors = curiosa.fetch_decks_batch(valid_ranked)
            errors.extend(ranked_errors)

        if valid_bulk:
            bulk_decks, bulk_errors = curiosa.fetch_decks_batch(valid_bulk)
            errors.extend(bulk_errors)

        if not top8_decks and not bulk_decks:
            _write_job(job_id, {
                "status": "failed",
                "result": {
                    "success": False,
                    "error": "No decks could be fetched. Check your URLs.",
                    "fetch_errors": errors,
                },
            })
            return

        repo = EventRepository()
        result = repo.create_event(title, top8_decks, bulk_decks if bulk_decks else None)

        if result.get("success"):
            result["top8_added"] = len(top8_decks)
            result["bulk_added"] = len(bulk_decks)
            if errors:
                result["warnings"] = errors

        _write_job(job_id, {
            "status": "completed" if result.get("success") else "failed",
            "result": result,
        })

    except Exception as e:
        logger.exception("Background event creation failed: %s", e)
        _write_job(job_id, {
            "status": "failed",
            "result": {"success": False, "error": f"Internal error: {e}"},
        })


@events_bp.route("/events/create", methods=["POST"])
@require_admin
def create_event():
    """Create a new event from Curiosa deck URLs (admin only).

    Returns a job_id immediately; the client polls /events/jobs/<job_id>.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Request body required"}), 400

    title = data.get("title", "").strip()
    if not title:
        return jsonify({"success": False, "error": "Title is required"}), 400

    ranked_urls = data.get("ranked_urls", [])
    if not isinstance(ranked_urls, list):
        return jsonify({"success": False, "error": "ranked_urls must be a list"}), 400

    bulk_urls = data.get("bulk_urls", [])
    if not isinstance(bulk_urls, list):
        return jsonify({"success": False, "error": "bulk_urls must be a list"}), 400

    valid_ranked = [u.strip() for u in ranked_urls if u and isinstance(u, str) and u.strip()]
    valid_bulk = [u.strip() for u in bulk_urls if u and isinstance(u, str) and u.strip()]

    if not valid_ranked and not valid_bulk:
        return jsonify({"success": False, "error": "At least one deck URL is required"}), 400

    job_id = str(uuid.uuid4())
    _write_job(job_id, {"status": "processing", "progress": "Starting..."})

    thread = threading.Thread(
        target=_run_event_creation,
        args=(job_id, title, valid_ranked, valid_bulk),
        daemon=True,
    )
    thread.start()

    return jsonify({"success": True, "job_id": job_id}), 202


@events_bp.route("/events/jobs/<job_id>")
@require_admin
def get_event_job_status(job_id):
    """Poll for background event job status."""
    job = _read_job(job_id)

    if not job:
        return jsonify({"error": "Job not found"}), 404

    response = {"status": job["status"]}
    if "progress" in job:
        response["progress"] = job["progress"]
    if "result" in job:
        response["result"] = job["result"]
        # Clean up completed/failed jobs after they're read
        _delete_job(job_id)

    return jsonify(response)


def _run_event_deck_update(job_id, event_folder, table_type, urls, mode):
    """Background worker for updating event decks."""
    try:
        from services.curiosa import CuriosaService
        curiosa = CuriosaService()

        decks, errors = curiosa.fetch_decks_batch(urls)

        if not decks:
            _write_job(job_id, {
                "status": "failed",
                "result": {
                    "success": False,
                    "error": "No decks could be fetched. Check your URLs.",
                    "fetch_errors": errors,
                },
            })
            return

        repo = EventRepository()
        result = repo.update_event_decks(event_folder, table_type, decks, mode)

        if result.get("success"):
            result["decks_added"] = len(decks)
            if errors:
                result["warnings"] = errors

        _write_job(job_id, {
            "status": "completed" if result.get("success") else "failed",
            "result": result,
        })

    except Exception as e:
        logger.exception("Background deck update failed: %s", e)
        _write_job(job_id, {
            "status": "failed",
            "result": {"success": False, "error": f"Internal error: {e}"},
        })


@events_bp.route("/events/<event_folder>/decks", methods=["POST"])
@require_admin
def update_event_decks(event_folder):
    """Add or replace decks in an existing event via Curiosa URLs (admin only)."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Request body required"}), 400

    table_type = data.get("table")
    if table_type not in ("top8", "all"):
        return jsonify({"success": False, "error": "table must be 'top8' or 'all'"}), 400

    mode = data.get("mode", "replace")
    if mode not in ("replace", "append"):
        return jsonify({"success": False, "error": "mode must be 'replace' or 'append'"}), 400

    urls = data.get("urls", [])
    if not isinstance(urls, list):
        return jsonify({"success": False, "error": "urls must be a list"}), 400

    job_id = str(uuid.uuid4())
    _write_job(job_id, {"status": "processing", "progress": "Starting..."})

    thread = threading.Thread(
        target=_run_event_deck_update,
        args=(job_id, event_folder, table_type, urls, mode),
        daemon=True,
    )
    thread.start()

    return jsonify({"success": True, "job_id": job_id}), 202


@events_bp.route("/events/<event_folder>", methods=["DELETE"])
@require_admin
def delete_event(event_folder):
    """Delete an event and all its data (admin only)."""
    repo = EventRepository()
    result = repo.delete_event(event_folder)

    status = 200 if result.get("success") else 400
    return jsonify(result), status


def _run_event_refresh(job_id, event_folder):
    """Background worker for refreshing event decks."""
    try:
        from services.curiosa import CuriosaService
        curiosa = CuriosaService()

        repo = EventRepository()
        result = repo.refresh_event_decks(event_folder, curiosa)

        _write_job(job_id, {
            "status": "completed" if result.get("success") else "failed",
            "result": result,
        })

    except Exception as e:
        logger.exception("Background event refresh failed: %s", e)
        _write_job(job_id, {
            "status": "failed",
            "result": {"success": False, "error": f"Internal error: {e}"},
        })


@events_bp.route("/events/<event_folder>/refresh", methods=["POST"])
@require_admin
def refresh_event(event_folder):
    """Re-fetch all deck data from Curiosa for an event (admin only)."""
    job_id = str(uuid.uuid4())
    _write_job(job_id, {"status": "processing", "progress": "Refreshing decks..."})

    thread = threading.Thread(
        target=_run_event_refresh,
        args=(job_id, event_folder),
        daemon=True,
    )
    thread.start()

    return jsonify({"success": True, "job_id": job_id}), 202


@events_bp.route("/events/featured", methods=["PUT"])
@require_admin
def set_featured_event():
    """Set or clear the featured (latest) event on the top 8 page (admin only)."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Request body required"}), 400

    folder = data.get("folder")  # None to clear
    if folder is not None and (not isinstance(folder, str) or not folder.strip()):
        return jsonify({"success": False, "error": "folder must be a non-empty string or null"}), 400

    repo = EventRepository()
    result = repo.set_featured_event(folder.strip() if folder else None)

    status = 200 if result.get("success") else 400
    return jsonify(result), status


@events_bp.route("/events/reorder", methods=["POST"])
@require_admin
def reorder_events_list():
    """Reorder the events listing page (admin only)."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Request body required"}), 400

    folder_order = data.get("order")
    if not isinstance(folder_order, list) or not all(isinstance(f, str) for f in folder_order):
        return jsonify({"success": False, "error": "order must be a list of folder name strings"}), 400

    repo = EventRepository()
    result = repo.save_event_order(folder_order)

    status = 200 if result.get("success") else 400
    return jsonify(result), status
