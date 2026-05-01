"""API endpoints for curio tracking."""

import os
import uuid
import logging

from flask import Blueprint, jsonify, request, session
from werkzeug.utils import secure_filename

from utils.auth import is_curio_editor
from repositories.curios import CurioRepository
from webapp_config import CURIO_UPLOADS_DIR

logger = logging.getLogger(__name__)

curios_bp = Blueprint("curios", __name__)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB


def _validate_image(file):
    """Validate uploaded image file. Returns (ok, error_message)."""
    if not file or not file.filename:
        return False, "No image file provided"

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"Invalid image format. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"

    # Check file size by reading and resetting
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > MAX_IMAGE_SIZE:
        return False, f"Image too large. Maximum size is {MAX_IMAGE_SIZE // (1024 * 1024)}MB"

    return True, None


def _save_image(file) -> str:
    """Save uploaded image with UUID filename. Returns the filename."""
    ext = os.path.splitext(secure_filename(file.filename))[1].lower()
    filename = f"{uuid.uuid4()}{ext}"
    filepath = CURIO_UPLOADS_DIR / filename
    file.save(str(filepath))
    return filename


def _delete_image(filename: str):
    """Delete an image file from disk. Handles missing files gracefully."""
    try:
        filepath = CURIO_UPLOADS_DIR / filename
        if filepath.exists():
            os.remove(filepath)
    except OSError as e:
        logger.warning(f"Failed to delete image {filename}: {e}")


def _entry_to_json(entry: dict) -> dict:
    """Convert entry dict to JSON response format with image_url."""
    return {
        "id": entry["id"],
        "name": entry["name"],
        "number_pulled": entry["number_pulled"],
        "description": entry["description"],
        "set_id": entry["set_id"],
        "set_name": entry["set_name"],
        "image_url": f"/static/uploads/curios/{entry['image_filename']}",
        "created_by": entry["created_by"],
        "created_at": entry["created_at"],
        "updated_at": entry["updated_at"],
    }


# --- Entry endpoints ---


@curios_bp.route("/", methods=["GET"])
def list_entries():
    """List all curio entries with set information."""
    repo = CurioRepository()
    entries = repo.get_all_entries()
    sets = repo.get_all_sets()
    return jsonify({
        "entries": [_entry_to_json(e) for e in entries],
        "sets": [{"id": s["id"], "name": s["name"], "is_default": s["is_default"]} for s in sets],
        "can_edit": is_curio_editor(),
    })


@curios_bp.route("/", methods=["POST"])
def create_entry():
    """Create a new curio entry with image upload."""
    if not is_curio_editor():
        return jsonify({"error": "Unauthorized"}), 403

    # Validate required fields
    name = request.form.get("name", "").strip()
    if not name or len(name) > 200:
        return jsonify({"error": "Name is required (max 200 characters)"}), 400

    try:
        number_pulled = int(request.form.get("number_pulled", ""))
        if number_pulled < 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "Number pulled must be a non-negative integer"}), 400

    description = request.form.get("description", "").strip()
    if not description or len(description) > 500:
        return jsonify({"error": "Description is required (max 500 characters)"}), 400

    try:
        set_id = int(request.form.get("set_id", ""))
    except (ValueError, TypeError):
        return jsonify({"error": "Set is required"}), 400

    # Validate image
    image = request.files.get("image")
    ok, error = _validate_image(image)
    if not ok:
        return jsonify({"error": error}), 400

    # Save image and create entry
    filename = _save_image(image)
    repo = CurioRepository()

    # Verify set_id exists
    sets = {s["id"] for s in repo.get_all_sets()}
    if set_id not in sets:
        _delete_image(filename)
        return jsonify({"error": "Invalid set"}), 400

    created_by = str(session.get("user_id", "unknown"))
    entry = repo.create_entry(name, number_pulled, description, set_id, filename, created_by)
    return jsonify(_entry_to_json(entry)), 201


@curios_bp.route("/<int:entry_id>", methods=["PUT"])
def update_entry(entry_id):
    """Update an existing curio entry."""
    if not is_curio_editor():
        return jsonify({"error": "Unauthorized"}), 403

    repo = CurioRepository()
    existing = repo.get_entry(entry_id)
    if not existing:
        return jsonify({"error": "Entry not found"}), 404

    updates = {}

    name = request.form.get("name")
    if name is not None:
        name = name.strip()
        if not name or len(name) > 200:
            return jsonify({"error": "Name must be 1-200 characters"}), 400
        updates["name"] = name

    number_pulled = request.form.get("number_pulled")
    if number_pulled is not None:
        try:
            number_pulled = int(number_pulled)
            if number_pulled < 0:
                raise ValueError
            updates["number_pulled"] = number_pulled
        except (ValueError, TypeError):
            return jsonify({"error": "Number pulled must be a non-negative integer"}), 400

    description = request.form.get("description")
    if description is not None:
        description = description.strip()
        if not description or len(description) > 500:
            return jsonify({"error": "Description must be 1-500 characters"}), 400
        updates["description"] = description

    set_id = request.form.get("set_id")
    if set_id is not None:
        try:
            set_id = int(set_id)
            sets = {s["id"] for s in repo.get_all_sets()}
            if set_id not in sets:
                return jsonify({"error": "Invalid set"}), 400
            updates["set_id"] = set_id
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid set ID"}), 400

    # Handle optional image replacement
    image = request.files.get("image")
    if image and image.filename:
        ok, error = _validate_image(image)
        if not ok:
            return jsonify({"error": error}), 400
        new_filename = _save_image(image)
        _delete_image(existing["image_filename"])
        updates["image_filename"] = new_filename

    updated = repo.update_entry(entry_id, **updates)
    return jsonify(_entry_to_json(updated))


@curios_bp.route("/<int:entry_id>", methods=["DELETE"])
def delete_entry(entry_id):
    """Delete a curio entry and its image."""
    if not is_curio_editor():
        return jsonify({"error": "Unauthorized"}), 403

    repo = CurioRepository()
    old_filename = repo.delete_entry(entry_id)
    if old_filename is None:
        return jsonify({"error": "Entry not found"}), 404

    _delete_image(old_filename)
    return jsonify({"message": "Entry deleted"})


# --- Set endpoints ---


@curios_bp.route("/sets", methods=["GET"])
def list_sets():
    """List all available sets."""
    repo = CurioRepository()
    sets = repo.get_all_sets()
    return jsonify({
        "sets": [{"id": s["id"], "name": s["name"], "is_default": s["is_default"]} for s in sets],
    })


@curios_bp.route("/sets", methods=["POST"])
def create_set():
    """Create a new custom set."""
    if not is_curio_editor():
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name or len(name) > 100:
        return jsonify({"error": "Set name is required (max 100 characters)"}), 400

    repo = CurioRepository()
    try:
        new_set = repo.create_set(name)
    except ValueError:
        return jsonify({"error": f"Set '{name}' already exists"}), 409

    return jsonify({"id": new_set["id"], "name": new_set["name"], "is_default": False}), 201
