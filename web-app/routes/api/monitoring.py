"""Health check and admin monitoring dashboard endpoints."""

import logging

from flask import Blueprint, jsonify, request, session

from repositories.audit import AuditRepository
from services import bot_monitor
from services.monitoring import get_dashboard, get_health
from utils.auth import require_admin
from utils.monitoring import client_ip

logger = logging.getLogger(__name__)

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



def _hours_arg():
    try:
        hours = float(request.args.get("hours", 24))
    except ValueError:
        return None
    return min(max(hours, 1), MAX_HOURS)


def _admin():
    return str(session.get("user_id") or "admin"), session.get("username") or "admin"


def _audit(action, target, details, **state):
    try:
        admin_id, admin_name = _admin()
        AuditRepository().log_action(admin_id, admin_name, action, target_id=target, details=details, **state)
    except Exception:
        logger.warning("Could not write audit entry for %s", action, exc_info=True)


@monitoring_bp.route("/admin/bots")
@require_admin
def bot_traffic():
    """Clients by User-Agent and IP with bot classification, plus the block list."""
    hours = _hours_arg()
    if hours is None:
        return jsonify({"error": "hours must be a number"}), 400
    return jsonify(bot_monitor.bot_summary(hours))


@monitoring_bp.route("/admin/bots/blocks", methods=["POST"])
@require_admin
def add_bot_block():
    """Block a User-Agent (substring) or an IP from the API."""
    data = request.get_json(silent=True) or {}
    kind = data.get("kind")
    pattern = data.get("pattern")
    reason = data.get("reason") or ""
    _, admin_name = _admin()
    try:
        block = bot_monitor.add_block(
            kind, pattern, reason, admin_name,
            own_agent=request.headers.get("User-Agent", ""), own_ip=client_ip(),
        )
    except bot_monitor.BlockError as e:
        return jsonify({"error": str(e)}), 400
    _audit("web_block_client", f"{block['kind']}:{block['pattern']}",
           f"Blocked {block['kind']} '{block['pattern']}' from the API. {reason}".strip(),
           new_state={"kind": block["kind"], "pattern": block["pattern"], "reason": reason})
    return jsonify({"success": True, "block": block})


@monitoring_bp.route("/admin/bots/blocks/<int:block_id>", methods=["DELETE"])
@require_admin
def remove_bot_block(block_id):
    """Lift a block (kept in the list as removed)."""
    _, admin_name = _admin()
    block = bot_monitor.remove_block(block_id, admin_name)
    if block is None:
        return jsonify({"error": "Block not found"}), 404
    _audit("web_unblock_client", f"{block['kind']}:{block['pattern']}",
           f"Unblocked {block['kind']} '{block['pattern']}'",
           previous_state={"kind": block["kind"], "pattern": block["pattern"], "reason": block["reason"]})
    return jsonify({"success": True})
