"""Analytics API routes for banner click tracking, site stats, and promo banners."""

from flask import Blueprint, jsonify, request, session

from repositories.analytics import AnalyticsRepository
from repositories.audit import AuditRepository
from utils.auth import require_admin

analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.route("/analytics/banner-click", methods=["POST"])
def banner_click():
    """Record a banner click (public endpoint)."""
    data = request.get_json(silent=True) or {}
    banner_type = data.get("banner_type", "new_event")
    AnalyticsRepository().log_banner_click(banner_type)
    return "", 204


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
    )

    AuditRepository().log_action(
        session.get("user_id", 0), admin_name, "create_promo_banner",
        target_id=str(banner_id),
        new_state={"title": title, "link": link, "expires_at": expires_at},
        details=f"Created promo banner '{title}' -> {link} (expires {expires_at})",
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
