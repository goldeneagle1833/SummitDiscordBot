"""Analytics API routes for banner click tracking, site stats, and promo banners."""

import json
import os
import uuid

from flask import Blueprint, jsonify, request, session
from werkzeug.utils import secure_filename

from repositories.analytics import AnalyticsRepository
from repositories.audit import AuditRepository
from utils.auth import require_admin
from webapp_config import BANNER_UPLOADS_DIR

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB

analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.route("/analytics/page-view", methods=["POST"])
def page_view():
    """Record a page view from the React SPA (public endpoint)."""
    data = request.get_json(silent=True) or {}
    path = data.get("path", "/")
    AnalyticsRepository().log_page_view(
        path,
        request.headers.get("User-Agent"),
        data.get("referrer"),
    )
    return "", 204


@analytics_bp.route("/analytics/banner-click", methods=["POST"])
def banner_click():
    """Record a banner click (public endpoint)."""
    data = request.get_json(silent=True) or {}
    banner_type = data.get("banner_type", "new_event")
    AnalyticsRepository().log_banner_click(banner_type)
    return "", 204


@analytics_bp.route("/analytics/heartbeat", methods=["POST"])
def heartbeat():
    """Record a heartbeat from an active browser session (public endpoint)."""
    data = request.get_json(silent=True) or {}
    session_id = data.get("sid", "")
    if not session_id or len(session_id) > 64:
        return "", 204
    ip = request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr
    ua = request.headers.get("User-Agent")
    path = data.get("path", "")[:200] if data.get("path") else None
    tz = data.get("timezone", "")[:60] if data.get("timezone") else None
    AnalyticsRepository().record_heartbeat(session_id, ip=ip, user_agent=ua, path=path, timezone=tz)
    return "", 204


@analytics_bp.route("/analytics/active-users", methods=["GET"])
@require_admin
def active_users():
    """Get the number of currently active site users (admin only)."""
    count = AnalyticsRepository().get_active_user_count()
    return jsonify({"success": True, "active_users": count})


@analytics_bp.route("/analytics/active-sessions", methods=["GET"])
@require_admin
def active_sessions_list():
    """Get all active sessions with metadata (admin only)."""
    sessions = AnalyticsRepository().get_active_sessions()
    return jsonify({"success": True, "sessions": sessions})


@analytics_bp.route("/analytics/stats", methods=["GET"])
@require_admin
def analytics_stats():
    """Get site analytics (admin only)."""
    hours = request.args.get("hours", type=int)
    repo = AnalyticsRepository()
    return jsonify({
        "success": True,
        "page_views": repo.get_page_view_stats(hours=hours),
        "banner_clicks": repo.get_banner_click_stats(),
    })


# --- Banner Image Upload ---

@analytics_bp.route("/analytics/banners/upload-image", methods=["POST"])
@require_admin
def upload_banner_image():
    """Upload a banner image. Returns the URL path."""
    file = request.files.get("image")
    if not file or not file.filename:
        return jsonify({"success": False, "error": "No image file provided"}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        return jsonify({"success": False, "error": f"Invalid format. Allowed: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}"}), 400

    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > MAX_IMAGE_SIZE:
        return jsonify({"success": False, "error": "Image too large. Maximum 5MB"}), 400

    filename = f"{uuid.uuid4()}{ext}"
    file.save(str(BANNER_UPLOADS_DIR / filename))

    url = f"/static/uploads/banners/{filename}"
    return jsonify({"success": True, "url": url})


# --- Promo Banners ---

@analytics_bp.route("/analytics/banners/active", methods=["GET"])
def active_banners():
    """Get all active, non-expired promo banners (public endpoint)."""
    banners = AnalyticsRepository().get_active_banners()
    return jsonify({"success": True, "banners": banners})


@analytics_bp.route("/analytics/banners", methods=["GET"])
@require_admin
def list_banners():
    """Get all banners for admin management."""
    banners = AnalyticsRepository().get_all_banners()
    return jsonify({"success": True, "banners": banners})


@analytics_bp.route("/analytics/banners", methods=["POST"])
@require_admin
def create_banner():
    """Create a new promo banner."""
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    link = (data.get("link") or "").strip()
    expires_at = (data.get("expires_at") or "").strip()

    if not title or not link or not expires_at:
        return jsonify({"success": False, "error": "title, link, and expires_at are required"}), 400

    # Parse images list - filter out empty strings
    raw_images = data.get("images") or []
    images = [url.strip() for url in raw_images if url and url.strip()]
    images_json = json.dumps(images) if images else None

    repo = AnalyticsRepository()
    admin_name = session.get("username", "API/localhost")
    banner_id = repo.create_banner(
        title=title,
        link=link,
        expires_at=expires_at,
        subtitle=(data.get("subtitle") or "").strip() or None,
        badge_text=(data.get("badge_text") or "NEW").strip(),
        color=(data.get("color") or "blue").strip(),
        created_by=admin_name,
        images=images_json,
    )

    AuditRepository().log_action(
        session.get("user_id", 0), admin_name, "create_promo_banner",
        target_id=str(banner_id),
        new_state={"title": title, "link": link, "expires_at": expires_at, "images": len(images)},
        details=f"Created promo banner '{title}' -> {link} (expires {expires_at}, {len(images)} images)",
    )

    return jsonify({"success": True, "id": banner_id}), 201


@analytics_bp.route("/analytics/banners/<int:banner_id>", methods=["DELETE"])
@require_admin
def delete_banner(banner_id):
    """Delete a promo banner."""
    repo = AnalyticsRepository()
    deleted = repo.delete_banner(banner_id)
    if not deleted:
        return jsonify({"success": False, "error": "Banner not found"}), 404

    admin_name = session.get("username", "API/localhost")
    AuditRepository().log_action(
        session.get("user_id", 0), admin_name, "delete_promo_banner",
        target_id=str(banner_id),
        details=f"Deleted promo banner ID {banner_id}",
    )

    return jsonify({"success": True})


@analytics_bp.route("/analytics/banners/<int:banner_id>/toggle", methods=["POST"])
@require_admin
def toggle_banner(banner_id):
    """Toggle a banner's active state."""
    repo = AnalyticsRepository()
    new_state = repo.toggle_banner(banner_id)
    if new_state is None:
        return jsonify({"success": False, "error": "Banner not found"}), 404

    admin_name = session.get("username", "API/localhost")
    AuditRepository().log_action(
        session.get("user_id", 0), admin_name, "toggle_promo_banner",
        target_id=str(banner_id),
        new_state={"active": new_state},
        details=f"{'Activated' if new_state else 'Deactivated'} promo banner ID {banner_id}",
    )

    return jsonify({"success": True, "active": new_state})
