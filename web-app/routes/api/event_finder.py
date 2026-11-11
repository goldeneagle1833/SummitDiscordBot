"""Find a player at an in-person event.

Public (no login): a person's page by their private link, and the event list
of people who chose to be listed. Logged in: your own sharing settings and
spot. Admins: the event maps (floor plan, dates, daily hours, quick spots).
"""

import logging
import os
import uuid
from io import BytesIO

from flask import Blueprint, jsonify, request, send_file, session

from repositories.event_finder import EventFinderRepository
from services import event_finder as rules
from utils.auth import is_admin, require_admin, require_auth
from webapp_config import EVENT_MAP_UPLOADS_DIR

event_finder_bp = Blueprint("event_finder", __name__)
logger = logging.getLogger(__name__)

FIND_PATH = "/find/"
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_SIZE = 15 * 1024 * 1024


def _repo() -> EventFinderRepository:
    return EventFinderRepository()


def _person_url(token: str) -> str:
    from services.store_checkout import _site_url
    return _site_url(f"{FIND_PATH}{token}")


def _avatar_url() -> str | None:
    """Full picture URL: Google gives one, Discord gives a hash."""
    avatar = session.get("avatar")
    if not avatar:
        return None
    if str(avatar).startswith("http"):
        return avatar
    return f"https://cdn.discordapp.com/avatars/{session.get('user_id')}/{avatar}.png?size=128"


def _my_share() -> dict:
    return _repo().get_or_create_share(
        str(session.get("user_id")), session.get("username"), _avatar_url(),
    )


def _me_payload(share: dict) -> dict:
    repo = _repo()
    maps = repo.list_maps(include_past=is_admin())
    event_map = repo.get_map(share["map_id"]) if share.get("map_id") else None
    return {
        "share": {
            "map_id": share.get("map_id"),
            "sharing": bool(share.get("sharing")),
            "listed": bool(share.get("listed")),
            "x": share.get("x"),
            "y": share.get("y"),
            "label": share.get("label"),
            "note": share.get("note"),
            "updated_at": share.get("updated_at"),
            "token": share["token"],
            "url": _person_url(share["token"]),
        },
        "status": rules.window_status(event_map),
        "maps": [rules.public_map(m) for m in maps],
        "can_manage_maps": is_admin(),
    }


# ----------------------------------------------------------------------
# Public
# ----------------------------------------------------------------------

@event_finder_bp.route("/event-finder/maps", methods=["GET"])
def list_maps():
    """Current and upcoming events with a hall map."""
    return jsonify({"maps": [rules.public_map(m) for m in _repo().list_maps()]})


@event_finder_bp.route("/event-finder/maps/<int:map_id>/people", methods=["GET"])
def map_people(map_id: int):
    """Everyone sharing on this map who chose to be on the public list."""
    repo = _repo()
    event_map = repo.get_map(map_id)
    if not event_map:
        return jsonify({"error": "Event not found"}), 404
    status = rules.window_status(event_map)
    people = []
    if status["open"]:
        for share in repo.listed_on_map(map_id):
            person = rules.public_person(share, event_map)
            person.pop("map", None)
            person["token"] = share["token"]
            people.append(person)
    return jsonify({"map": rules.public_map(event_map), "people": people})


@event_finder_bp.route("/event-finder/p/<token>", methods=["GET"])
def person(token: str):
    """One person's spot, opened from their link or QR code."""
    repo = _repo()
    share = repo.get_share_by_token(token)
    if not share:
        return jsonify({"error": "Not found"}), 404
    event_map = repo.get_map(share["map_id"]) if share.get("map_id") else None
    return jsonify(rules.public_person(share, event_map))


# ----------------------------------------------------------------------
# Your own spot
# ----------------------------------------------------------------------

@event_finder_bp.route("/event-finder/me", methods=["GET"])
@require_auth
def get_me():
    if not session.get("user_id"):
        return jsonify({"error": "Log in to share your spot"}), 401
    return jsonify(_me_payload(_my_share()))


@event_finder_bp.route("/event-finder/me", methods=["PUT"])
@require_auth
def update_me():
    if not session.get("user_id"):
        return jsonify({"error": "Log in to share your spot"}), 401
    share = _my_share()
    try:
        fields = rules.clean_share_fields(request.get_json(silent=True) or {})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if fields.get("map_id") is not None and not _repo().get_map(fields["map_id"]):
        return jsonify({"error": "That event no longer exists"}), 400
    share = _repo().update_share(share["user_id"], **fields)
    return jsonify(_me_payload(share))


@event_finder_bp.route("/event-finder/me/new-link", methods=["POST"])
@require_auth
def new_link():
    """Retire the old link (and its QR code) and make a new one."""
    if not session.get("user_id"):
        return jsonify({"error": "Log in to share your spot"}), 401
    share = _my_share()
    return jsonify(_me_payload(_repo().new_link(share["user_id"])))


@event_finder_bp.route("/event-finder/me/qr.png", methods=["GET"])
@require_auth
def my_qr():
    """QR code of your link. ?download=1 saves it."""
    if not session.get("user_id"):
        return jsonify({"error": "Log in to share your spot"}), 401
    from services.store_private_link import qr_png

    share = _my_share()
    return send_file(
        BytesIO(qr_png(_person_url(share["token"]))), mimetype="image/png",
        as_attachment=request.args.get("download") == "1",
        download_name="find-me-qr.png", max_age=0,
    )


# ----------------------------------------------------------------------
# Admin: event maps
# ----------------------------------------------------------------------

@event_finder_bp.route("/event-finder/admin/maps", methods=["POST"])
@require_admin
def create_map():
    try:
        fields = rules.clean_map_fields(request.get_json(silent=True) or {})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"map": rules.public_map(_repo().create_map(**fields))})


@event_finder_bp.route("/event-finder/admin/maps/<int:map_id>", methods=["PUT"])
@require_admin
def update_map(map_id: int):
    repo = _repo()
    current = repo.get_map(map_id)
    if not current:
        return jsonify({"error": "Event not found"}), 404
    data = request.get_json(silent=True) or {}
    try:
        fields = rules.clean_map_fields(data, partial=True)
        # Check the date and hour pairs against what's already saved too
        rules.clean_map_fields({**current, **fields, "image_url": None, "spots": None})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"map": rules.public_map(repo.update_map(map_id, **fields))})


@event_finder_bp.route("/event-finder/admin/maps/<int:map_id>", methods=["DELETE"])
@require_admin
def delete_map(map_id: int):
    _repo().delete_map(map_id)
    return jsonify({"success": True})


@event_finder_bp.route("/event-finder/admin/maps/upload-image", methods=["POST"])
@require_admin
def upload_map_image():
    file = request.files.get("image")
    if not file or not file.filename:
        return jsonify({"error": "Choose an image to upload."}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        return jsonify({"error": "Use a JPG, PNG or WEBP image. For a PDF, take a screenshot first."}), 400
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > MAX_IMAGE_SIZE:
        return jsonify({"error": f"That image is {size / (1024 * 1024):.1f} MB. Maps must be 15 MB or smaller."}), 400
    filename = f"{uuid.uuid4()}{ext}"
    file.save(str(EVENT_MAP_UPLOADS_DIR / filename))
    return jsonify({"url": f"/static/uploads/event-maps/{filename}"})
