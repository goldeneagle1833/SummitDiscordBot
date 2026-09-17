"""Health check and admin monitoring dashboard endpoints."""

from flask import Blueprint, jsonify, request

from services.monitoring import get_dashboard, get_health
from utils.auth import require_admin

monitoring_bp = Blueprint("monitoring", __name__)

MAX_HOURS = 24 * 7


@monitoring_bp.route("/health")
def health():
    """Public health check for uptime monitors. 503 only when a critical dependency is down."""
    result = get_health()
    public = {
        "status": result["status"],
        "version": result["version"],
        "uptime_s": result["uptime_s"],
        "checked_at": result["checked_at"],
        # Pass/fail per check only; details (paths, error types) stay admin-only
        "failing": sorted(name for name, c in result["checks"].items() if not c["ok"]),
    }
    return jsonify(public), 503 if result["status"] == "down" else 200


@monitoring_bp.route("/admin/monitoring")
@require_admin
def monitoring_dashboard():
    """Request, outbound API, resource and error metrics for the admin dashboard."""
    try:
        hours = float(request.args.get("hours", 24))
    except ValueError:
        return jsonify({"error": "hours must be a number"}), 400
    hours = min(max(hours, 0.25), MAX_HOURS)
    return jsonify(get_dashboard(hours))
