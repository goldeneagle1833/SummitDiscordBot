"""Analytics API routes for banner click tracking and site stats."""

from flask import Blueprint, jsonify, request

from repositories.analytics import AnalyticsRepository
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
