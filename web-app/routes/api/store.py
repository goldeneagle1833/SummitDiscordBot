"""Store API routes.

Public:       product catalog
Logged-in:    (phase 2) checkout / order creation
Store admin:  product CRUD, order queue, mark shipped, backup download

Registered via routes/api/__init__.py alongside the other sub-blueprints.
"""

import logging
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file, session

from repositories.store import StoreRepository, ORDER_STATUSES, STORE_DB_PATH
from utils.store_auth import require_store_admin

logger = logging.getLogger(__name__)

store_bp = Blueprint("store", __name__)


def _repo() -> StoreRepository:
    return StoreRepository()


def _actor():
    return str(session.get("user_id", 0)), session.get("username", "API/localhost")


# ----------------------------------------------------------------------
# Public catalog
# ----------------------------------------------------------------------

@store_bp.route("/store/products", methods=["GET"])
def list_products():
    products = _repo().list_products(include_inactive=False)
    return jsonify({"products": products})


# ----------------------------------------------------------------------
# Store admin: product management
# ----------------------------------------------------------------------

@store_bp.route("/store/admin/products", methods=["GET"])
@require_store_admin
def admin_list_products():
    return jsonify({"products": _repo().list_products(include_inactive=True)})


@store_bp.route("/store/admin/products", methods=["POST"])
@require_store_admin
def admin_create_product():
    data = request.get_json(silent=True) or {}
    required = ("sku", "name", "price_cents")
    missing = [f for f in required if not data.get(f) and data.get(f) != 0]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400
    try:
        price_cents = int(data["price_cents"])
        stock = int(data.get("stock_quantity", 0))
        if price_cents < 0 or stock < 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "price_cents and stock_quantity must be non-negative integers"}), 400

    repo = _repo()
    try:
        product_id = repo.create_product(
            sku=str(data["sku"]).strip(),
            name=str(data["name"]).strip(),
            price_cents=price_cents,
            description=str(data.get("description", "")),
            image_url=data.get("image_url"),
            stock_quantity=stock,
        )
    except sqlite3.IntegrityError:
        return jsonify({"error": "A product with that SKU already exists"}), 409

    actor_id, actor_name = _actor()
    repo.log_action(actor_id, actor_name, "create_product",
                    f"id={product_id} sku={data['sku']}")
    return jsonify({"id": product_id}), 201


@store_bp.route("/store/admin/products/<int:product_id>", methods=["PATCH"])
@require_store_admin
def admin_update_product(product_id: int):
    data = request.get_json(silent=True) or {}
    repo = _repo()
    if not repo.get_product(product_id):
        return jsonify({"error": "Product not found"}), 404
    try:
        updated = repo.update_product(product_id, **data)
    except sqlite3.IntegrityError:
        return jsonify({"error": "SKU conflict"}), 409
    if not updated:
        return jsonify({"error": "No valid fields to update"}), 400

    actor_id, actor_name = _actor()
    repo.log_action(actor_id, actor_name, "update_product",
                    f"id={product_id} fields={sorted(data.keys())}")
    return jsonify({"success": True})


@store_bp.route("/store/admin/products/<int:product_id>/deactivate", methods=["POST"])
@require_store_admin
def admin_deactivate_product(product_id: int):
    """Soft delete: products referenced by orders must never be hard-deleted."""
    repo = _repo()
    if not repo.update_product(product_id, is_active=0):
        return jsonify({"error": "Product not found"}), 404
    actor_id, actor_name = _actor()
    repo.log_action(actor_id, actor_name, "deactivate_product", f"id={product_id}")
    return jsonify({"success": True})


# ----------------------------------------------------------------------
# Store admin: order queue
# ----------------------------------------------------------------------

@store_bp.route("/store/admin/orders", methods=["GET"])
@require_store_admin
def admin_list_orders():
    status = request.args.get("status")
    try:
        limit = min(int(request.args.get("limit", 100)), 500)
        orders = _repo().list_orders(status=status, limit=limit)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"orders": orders, "statuses": ORDER_STATUSES})


@store_bp.route("/store/admin/orders/<int:order_id>", methods=["GET"])
@require_store_admin
def admin_get_order(order_id: int):
    order = _repo().get_order(order_id)
    if not order:
        return jsonify({"error": "Order not found"}), 404
    return jsonify({"order": order})


@store_bp.route("/store/admin/orders/<int:order_id>/ship", methods=["POST"])
@require_store_admin
def admin_ship_order(order_id: int):
    data = request.get_json(silent=True) or {}
    tracking = (data.get("tracking_number") or "").strip()
    if not tracking:
        return jsonify({"error": "tracking_number is required"}), 400

    repo = _repo()
    if not repo.mark_shipped(order_id, tracking, data.get("tracking_carrier")):
        return jsonify({"error": "Order not found or not in 'paid' status"}), 409

    actor_id, actor_name = _actor()
    repo.log_action(actor_id, actor_name, "ship_order",
                    f"id={order_id} tracking={tracking}")
    try:
        from services.store_notifications import StoreNotificationService
        StoreNotificationService(repo).notify_order_shipped(repo.get_order(order_id))
    except Exception:
        logger.exception(f"Shipped notification failed for order {order_id}")
    return jsonify({"success": True})


@store_bp.route("/store/admin/orders/<int:order_id>/status", methods=["POST"])
@require_store_admin
def admin_set_order_status(order_id: int):
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    repo = _repo()
    try:
        if not repo.set_status(order_id, status):
            return jsonify({"error": "Order not found"}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if status == "cancelled":
        repo.restock_order_items(order_id)

    actor_id, actor_name = _actor()
    repo.log_action(actor_id, actor_name, "set_order_status",
                    f"id={order_id} status={status}")
    return jsonify({"success": True})


@store_bp.route("/store/admin/audit", methods=["GET"])
@require_store_admin
def admin_audit_log():
    return jsonify({"audit": _repo().list_audit()})


# ----------------------------------------------------------------------
# Store admin: backup download
# ----------------------------------------------------------------------

@store_bp.route("/store/admin/backup", methods=["GET"])
@require_store_admin
def admin_download_backup():
    """Stream a consistent snapshot of store.db to the admin's machine.

    Uses SQLite's online backup API, which is safe while the DB is in use
    (a plain file copy of a live SQLite database can be corrupt).
    """
    src = sqlite3.connect(STORE_DB_PATH)
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()
    try:
        dest = sqlite3.connect(tmp_path)
        with dest:
            src.backup(dest)
        dest.close()
    finally:
        src.close()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    actor_id, actor_name = _actor()
    _repo().log_action(actor_id, actor_name, "download_backup", stamp)
    return send_file(
        tmp_path,
        as_attachment=True,
        download_name=f"store-backup-{stamp}.db",
        mimetype="application/octet-stream",
    )


# ----------------------------------------------------------------------
# Checkout (logged-in buyers)
# ----------------------------------------------------------------------

from utils.auth import require_auth  # noqa: E402
from services.store_checkout import StoreCheckoutService  # noqa: E402


@store_bp.route("/store/checkout", methods=["POST"])
@require_auth
def create_checkout():
    """Create a pending order and return a Stripe hosted checkout URL.

    Body: {
      items: [{product_id, quantity}],
      shipping_address: {name, line1, line2?, city, state, postal, country?},
      email?: str
    }
    """
    service = StoreCheckoutService()
    if not service.is_configured():
        return jsonify({"error": "Payments are not configured"}), 503

    data = request.get_json(silent=True) or {}
    items = data.get("items") or []
    address = data.get("shipping_address") or {}

    if not items:
        return jsonify({"error": "Cart is empty"}), 400
    required_addr = ("name", "line1", "city", "state", "postal")
    missing = [f for f in required_addr if not (address.get(f) or "").strip()]
    if missing:
        return jsonify({"error": f"Missing address fields: {', '.join(missing)}"}), 400

    provider = session.get("auth_provider", "discord")
    if provider != "discord" and not (data.get("email") or "").strip():
        # Email is the only way to reach non-Discord buyers about their order
        return jsonify({"error": "Email address is required"}), 400

    user_id = str(session.get("user_id", 0))
    username = session.get("username", "unknown")

    try:
        result = service.create_checkout(
            user_id=user_id,
            username=username,
            items=items,
            shipping_address=address,
            email=data.get("email"),
            auth_provider=provider,
            address_validated=False,  # phase 4: Google address validation
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    except Exception:
        logger.exception("Checkout creation failed")
        return jsonify({"error": "Could not start checkout, please try again"}), 502

    return jsonify(result), 201


@store_bp.route("/store/orders/mine", methods=["GET"])
@require_auth
def my_orders():
    """List the logged-in user's own orders (most recent first)."""
    user_id = str(session.get("user_id", 0))
    repo = _repo()
    orders = [o for o in repo.list_orders(limit=200) if o["user_id"] == user_id]
    # Buyers don't need internal/admin fields
    public_fields = (
        "order_number", "status", "total_cents", "currency",
        "tracking_number", "tracking_carrier", "created_at", "paid_at", "shipped_at",
    )
    return jsonify({
        "orders": [{k: o.get(k) for k in public_fields} for o in orders[:50]]
    })


# ----------------------------------------------------------------------
# Stripe webhook (no session auth: verified by signature instead)
# ----------------------------------------------------------------------

@store_bp.route("/store/webhooks/stripe", methods=["POST"])
def stripe_webhook():
    """Receive Stripe events. This is the ONLY path that marks orders paid."""
    service = StoreCheckoutService()
    if not service.is_configured():
        return jsonify({"error": "not configured"}), 503

    payload = request.get_data()  # raw bytes: required for signature check
    sig_header = request.headers.get("Stripe-Signature", "")
    try:
        event = service.construct_event(payload, sig_header)
    except Exception:
        logger.warning(
            f"Stripe webhook signature verification failed from {request.remote_addr}"
        )
        return jsonify({"error": "invalid signature"}), 400

    result = service.handle_event(event)
    # Always 200 for verified events so Stripe stops retrying ones we
    # deliberately ignored; mishandled orders are logged + audited.
    return jsonify(result), 200


@store_bp.route("/store/checkout/prefill", methods=["GET"])
@require_auth
def checkout_prefill():
    """Pre-populate the checkout form from the user's profile and last order.

    Google users get name + email from their profile; repeat buyers of
    either provider get their most recent shipping address.
    """
    user_id = str(session.get("user_id", 0))
    provider = session.get("auth_provider", "discord")

    prefill = {
        "username": session.get("username"),
        "auth_provider": provider,
        "name": None,
        "email": None,
        "address": None,
    }

    try:
        from repositories.user_profiles import UserProfileRepository
        profile = UserProfileRepository().get_by_user_id(user_id)
        if profile:
            prefill["email"] = profile.get("email")
            given = profile.get("given_name") or ""
            family = profile.get("family_name") or ""
            full = f"{given} {family}".strip()
            prefill["name"] = full or profile.get("display_name")
    except Exception:
        logger.exception("Prefill profile lookup failed")

    last = _repo().last_shipping_address(user_id)
    if last:
        prefill["address"] = {k: last[k] for k in
                              ("name", "line1", "line2", "city",
                               "state", "postal", "country")}
        prefill["email"] = prefill["email"] or last.get("email")
        prefill["name"] = prefill["name"] or last.get("name")

    return jsonify(prefill)


# ----------------------------------------------------------------------
# Product image upload (same pattern as banner uploads)
# ----------------------------------------------------------------------

import os as _os  # noqa: E402
import uuid as _uuid  # noqa: E402
from webapp_config import STORE_UPLOADS_DIR  # noqa: E402

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB


@store_bp.route("/store/admin/products/upload-image", methods=["POST"])
@require_store_admin
def upload_product_image():
    """Upload a product image. Returns the URL path to store on the product."""
    file = request.files.get("image")
    if not file or not file.filename:
        return jsonify({"success": False, "error": "No image file provided"}), 400

    ext = _os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        return jsonify({
            "success": False,
            "error": f"Invalid format. Allowed: {', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))}",
        }), 400

    file.seek(0, _os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > MAX_IMAGE_SIZE:
        return jsonify({"success": False, "error": "Image too large. Maximum 5MB"}), 400

    filename = f"{_uuid.uuid4()}{ext}"
    file.save(str(STORE_UPLOADS_DIR / filename))

    actor_id, actor_name = _actor()
    _repo().log_action(actor_id, actor_name, "upload_product_image", filename)
    return jsonify({"success": True, "url": f"/static/uploads/store/{filename}"})
