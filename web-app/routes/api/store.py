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
from functools import wraps
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file, session

from repositories.store import (
    StoreRepository, ORDER_STATUSES, STORE_DB_PATH, STOREFRONT_ROLES, slugify,
    DEFAULT_STOREFRONT_SLUG,
)
from utils.store_auth import is_store_admin, require_store_admin

logger = logging.getLogger(__name__)

store_bp = Blueprint("store", __name__)

# Orders above this total can't be marked shipped without a tracking number
TRACKING_REQUIRED_OVER_CENTS = 5000


def _repo() -> StoreRepository:
    return StoreRepository()


def _actor():
    return str(session.get("user_id", 0)), session.get("username", "API/localhost")


# ----------------------------------------------------------------------
# Storefront scope
#
# Full store admins (STORE_ADMIN_IDS) manage every storefront. Everyone
# else in storefront_admins manages only their own: a manager handles
# products and orders, fulfillment handles orders only.
# ----------------------------------------------------------------------

def _storefront_roles() -> dict[int, str]:
    user_id = session.get("user_id")
    if user_id is None:
        return {}
    return _repo().storefront_roles_for_user(str(user_id))


def _scope_ids(need: str = "orders") -> list[int] | None:
    """Storefront ids the current user may act on, or None for all of them."""
    if is_store_admin():
        return None
    roles = _storefront_roles()
    if need == "products":
        return [sid for sid, role in roles.items() if role == "manager"]
    return list(roles)


def _can(storefront_id, need: str = "orders") -> bool:
    ids = _scope_ids(need)
    return ids is None or storefront_id in ids


def require_store_staff(f):
    """Full store admins, plus anyone who runs at least one storefront.

    Handlers must still narrow what they return or change with
    _scope_ids() / _can().
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_store_admin() and not _storefront_roles():
            logger.warning(
                f"Non-store-staff access attempt to {request.path} "
                f"from {request.remote_addr}"
            )
            return jsonify({"error": "Store admin access required"}), 403
        return f(*args, **kwargs)

    decorated_function._auth_required = True
    return decorated_function


def _not_found(what: str):
    # Same answer for "doesn't exist" and "not yours", so storefront admins
    # can't probe other storefronts' ids.
    return jsonify({"error": f"{what} not found"}), 404


# ----------------------------------------------------------------------
# Public catalog
# ----------------------------------------------------------------------

@store_bp.route("/store/products", methods=["GET"])
def list_products():
    repo = _repo()
    products = repo.list_products(include_inactive=False)

    # Logged-in buyers also get what's left of each monthly limit, so the
    # storefront can cap quantities instead of failing at checkout.
    user_id = session.get("user_id")
    if user_id:
        counts = repo.user_monthly_product_counts(str(user_id))
        for p in products:
            cap = p["max_per_user_monthly"]
            if cap is not None:
                p["remaining_this_month"] = max(0, cap - counts.get(p["id"], 0))

    return jsonify({"products": products})


# ----------------------------------------------------------------------
# Store admin: product management
# ----------------------------------------------------------------------

@store_bp.route("/store/admin/products", methods=["GET"])
@require_store_staff
def admin_list_products():
    # Fulfillment staff see the list too: the order queue filters by product
    ids = _scope_ids("orders")
    wanted = request.args.get("storefront_id", type=int)
    if wanted is not None:
        if ids is not None and wanted not in ids:
            return jsonify({"products": []})
        ids = [wanted]
    return jsonify({
        "products": _repo().list_products(include_inactive=True, storefront_ids=ids)
    })


@store_bp.route("/store/admin/products", methods=["POST"])
@require_store_staff
def admin_create_product():
    data = request.get_json(silent=True) or {}
    repo = _repo()
    storefront_id = data.get("storefront_id")
    if storefront_id in (None, ""):
        storefront_id = repo.default_storefront_id()
    try:
        storefront_id = int(storefront_id)
    except (TypeError, ValueError):
        return jsonify({"error": "storefront_id must be an integer"}), 400
    if not _can(storefront_id, "products"):
        return jsonify({"error": "You can't add products to that storefront"}), 403

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

    max_monthly = data.get("max_per_user_monthly")
    if max_monthly is not None:
        try:
            max_monthly = int(max_monthly)
            if max_monthly < 1:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"error": "max_per_user_monthly must be a positive integer"}), 400

    try:
        product_id = repo.create_product(
            sku=str(data["sku"]).strip(),
            name=str(data["name"]).strip(),
            price_cents=price_cents,
            description=str(data.get("description", "")),
            image_url=data.get("image_url"),
            stock_quantity=stock,
            max_per_user_monthly=max_monthly,
            images=data.get("images"),
            storefront_id=storefront_id,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except sqlite3.IntegrityError:
        return jsonify({"error": "A product with that SKU already exists"}), 409

    actor_id, actor_name = _actor()
    repo.log_action(actor_id, actor_name, "create_product",
                    f"id={product_id} sku={data['sku']} storefront={storefront_id}")
    return jsonify({"id": product_id}), 201


def _validate_product_patch(data: dict) -> tuple[dict, str | None]:
    """Coerce an admin PATCH body into repo fields. Returns (fields, error)."""
    fields: dict = {}
    for key in ("sku", "name"):
        if key in data:
            value = str(data[key] or "").strip()
            if not value:
                return {}, f"{key} cannot be empty"
            fields[key] = value
    if "description" in data:
        fields["description"] = str(data["description"] or "")
    for key in ("price_cents", "stock_quantity"):
        if key in data:
            try:
                value = int(data[key])
                if value < 0:
                    raise ValueError
            except (TypeError, ValueError):
                return {}, f"{key} must be a non-negative integer"
            fields[key] = value
    if "is_active" in data:
        fields["is_active"] = 1 if data["is_active"] in (1, True, "1", "true") else 0
    if "max_per_user_monthly" in data:
        value = data["max_per_user_monthly"]
        if value in (None, ""):
            fields["max_per_user_monthly"] = None
        else:
            try:
                value = int(value)
                if value < 1:
                    raise ValueError
            except (TypeError, ValueError):
                return {}, "max_per_user_monthly must be a positive integer"
            fields["max_per_user_monthly"] = value
    if "storefront_id" in data:
        try:
            fields["storefront_id"] = int(data["storefront_id"])
        except (TypeError, ValueError):
            return {}, "storefront_id must be an integer"
    if "images" in data:
        fields["images"] = data["images"]
    elif "image_url" in data:
        fields["image_url"] = (data["image_url"] or "").strip() or None
    return fields, None


@store_bp.route("/store/admin/products/<int:product_id>", methods=["PATCH"])
@require_store_staff
def admin_update_product(product_id: int):
    data = request.get_json(silent=True) or {}
    repo = _repo()
    product = repo.get_product(product_id)
    if not product or not _can(product["storefront_id"], "orders"):
        return _not_found("Product")
    if not _can(product["storefront_id"], "products"):
        return jsonify({"error": "Only storefront managers can edit products"}), 403
    fields, error = _validate_product_patch(data)
    if error:
        return jsonify({"error": error}), 400
    if ("storefront_id" in fields and fields["storefront_id"] != product["storefront_id"]
            and not is_store_admin()):
        return jsonify({"error": "Only full store admins can move products"}), 403
    try:
        updated = repo.update_product(product_id, **fields)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except sqlite3.IntegrityError:
        return jsonify({"error": "A product with that SKU already exists"}), 409
    if not updated:
        return jsonify({"error": "No valid fields to update"}), 400

    actor_id, actor_name = _actor()
    repo.log_action(actor_id, actor_name, "update_product",
                    f"id={product_id} fields={sorted(data.keys())}")
    return jsonify({"success": True})


@store_bp.route("/store/admin/products/<int:product_id>/deactivate", methods=["POST"])
@require_store_staff
def admin_deactivate_product(product_id: int):
    """Soft delete: products referenced by orders must never be hard-deleted."""
    repo = _repo()
    product = repo.get_product(product_id)
    if not product or not _can(product["storefront_id"], "orders"):
        return _not_found("Product")
    if not _can(product["storefront_id"], "products"):
        return jsonify({"error": "Only storefront managers can edit products"}), 403
    if not repo.update_product(product_id, is_active=0):
        return _not_found("Product")
    actor_id, actor_name = _actor()
    repo.log_action(actor_id, actor_name, "deactivate_product", f"id={product_id}")
    return jsonify({"success": True})


# ----------------------------------------------------------------------
# Store admin: order queue
# ----------------------------------------------------------------------

def _order_scope_from_args() -> list[int] | None:
    """Storefront ids for an order list: the user's scope, optionally narrowed
    by ?storefront_id=."""
    ids = _scope_ids("orders")
    wanted = request.args.get("storefront_id", type=int)
    if wanted is None:
        return ids
    return [wanted] if ids is None or wanted in ids else []


@store_bp.route("/store/admin/orders", methods=["GET"])
@require_store_staff
def admin_list_orders():
    status = request.args.get("status") or None
    product_id = request.args.get("product_id", type=int)
    search = request.args.get("search") or None
    date_from = request.args.get("date_from") or None
    date_to = request.args.get("date_to") or None
    try:
        limit = min(int(request.args.get("limit", 100)), 500)
        orders = _repo().list_orders_filtered(
            status=status, product_id=product_id, search=search,
            date_from=date_from, date_to=date_to, limit=limit,
            storefront_ids=_order_scope_from_args(),
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"orders": orders, "statuses": ORDER_STATUSES})


def _scoped_order(repo: StoreRepository, order_id: int) -> dict | None:
    order = repo.get_order(order_id)
    if order and _can(order["storefront_id"], "orders"):
        return order
    return None


@store_bp.route("/store/admin/orders/<int:order_id>", methods=["GET"])
@require_store_staff
def admin_get_order(order_id: int):
    order = _scoped_order(_repo(), order_id)
    if not order:
        return _not_found("Order")
    return jsonify({"order": order})


@store_bp.route("/store/admin/orders/<int:order_id>/ship", methods=["POST"])
@require_store_staff
def admin_ship_order(order_id: int):
    data = request.get_json(silent=True) or {}
    tracking = (data.get("tracking_number") or "").strip() or None
    carrier = (data.get("tracking_carrier") or "").strip() or None

    repo = _repo()
    order = _scoped_order(repo, order_id)
    if not order:
        return _not_found("Order")
    if not tracking and order["total_cents"] > TRACKING_REQUIRED_OVER_CENTS:
        return jsonify({
            "error": f"Tracking is required for orders over "
                     f"${TRACKING_REQUIRED_OVER_CENTS / 100:.0f}"
        }), 400
    if not tracking:
        carrier = None

    if not repo.mark_shipped(order_id, tracking, carrier):
        return jsonify({"error": "Order not found or not in 'paid' status"}), 409

    actor_id, actor_name = _actor()
    repo.log_action(actor_id, actor_name, "ship_order",
                    f"id={order_id} tracking={tracking or 'none'}")
    try:
        from services.store_notifications import StoreNotificationService
        StoreNotificationService(repo).notify_order_shipped(repo.get_order(order_id))
    except Exception:
        logger.exception(f"Shipped notification failed for order {order_id}")
    return jsonify({"success": True})


@store_bp.route("/store/admin/orders/<int:order_id>/status", methods=["POST"])
@require_store_staff
def admin_set_order_status(order_id: int):
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    repo = _repo()
    order = _scoped_order(repo, order_id)
    if not order:
        return _not_found("Order")

    if status == "cancelled":
        try:
            cancelled = StoreCheckoutService(repo).cancel_order(order)
        except ValueError as e:
            return jsonify({"error": str(e)}), 409
        except Exception:
            logger.exception(f"Could not close Stripe session for order {order_id}")
            return jsonify({
                "error": "Could not close the Stripe checkout session; order not cancelled"
            }), 502
        if not cancelled:
            return jsonify({
                "error": "Only unpaid or paid (unshipped) orders can be cancelled"
            }), 409
    else:
        try:
            if not repo.set_status(order_id, status):
                return jsonify({"error": "Order not found"}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    actor_id, actor_name = _actor()
    repo.log_action(actor_id, actor_name, "set_order_status",
                    f"id={order_id} status={status}")
    return jsonify({"success": True})


@store_bp.route("/store/admin/orders/export", methods=["GET"])
@require_store_staff
def admin_export_orders():
    """Export orders as CSV for the current filter."""
    import csv
    import io

    status = request.args.get("status") or None
    product_id = request.args.get("product_id", type=int)
    search = request.args.get("search") or None
    date_from = request.args.get("date_from") or None
    date_to = request.args.get("date_to") or None
    repo = _repo()
    try:
        orders = repo.list_orders_filtered(
            status=status, product_id=product_id, search=search,
            date_from=date_from, date_to=date_to, limit=500,
            storefront_ids=_order_scope_from_args(),
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "order_number", "storefront", "status", "username", "email",
        "total", "currency", "ship_name", "ship_line1", "ship_line2",
        "ship_city", "ship_state", "ship_postal", "ship_country",
        "tracking_number", "tracking_carrier",
        "created_at", "paid_at", "shipped_at",
    ])
    for o in orders:
        writer.writerow([
            o.get("order_number"), o.get("storefront_name"), o.get("status"),
            o.get("username"), o.get("email"),
            f"{o.get('total_cents', 0) / 100:.2f}", o.get("currency"),
            o.get("ship_name"), o.get("ship_line1"), o.get("ship_line2"),
            o.get("ship_city"), o.get("ship_state"), o.get("ship_postal"), o.get("ship_country"),
            o.get("tracking_number"), o.get("tracking_carrier"),
            o.get("created_at"), o.get("paid_at"), o.get("shipped_at"),
        ])

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    actor_id, actor_name = _actor()
    repo.log_action(actor_id, actor_name, "export_orders", f"status={status or 'all'} count={len(orders)}")

    from flask import Response
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=orders-{stamp}.csv"},
    )


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
import stripe  # noqa: E402
from services.store_checkout import StoreCheckoutService, _site_url  # noqa: E402
from webapp_config import FREE_SHIPPING_ROLE_IDS  # noqa: E402


@store_bp.route("/store/checkout", methods=["POST"])
@require_auth
def create_checkout():
    """Create a pending order and return a Stripe hosted checkout URL.

    Body: {
      items: [{product_id, quantity}],
      email?: str
    }

    Shipping address is collected by Stripe Checkout (with autocomplete)
    and saved via webhook when payment completes.
    """
    data = request.get_json(silent=True) or {}
    items = data.get("items") or []

    if not items:
        return jsonify({"error": "Cart is empty"}), 400

    provider = session.get("auth_provider", "discord")
    if provider != "discord" and not (data.get("email") or "").strip():
        # Email is the only way to reach non-Discord buyers about their order
        return jsonify({"error": "Email address is required"}), 400

    service = StoreCheckoutService()
    if not service.is_configured():
        return jsonify({"error": "Payments are not configured"}), 503

    user_id = str(session.get("user_id", 0))
    username = session.get("username", "unknown")

    discord_roles = session.get("discord_roles", [])

    try:
        result = service.create_checkout(
            user_id=user_id,
            username=username,
            items=items,
            email=data.get("email"),
            auth_provider=provider,
            discord_roles=discord_roles,
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
    orders = repo.list_orders_by_user(user_id, limit=50)

    # Build a product image lookup for all items across orders
    order_ids = [o["id"] for o in orders]
    items_by_order = repo.get_items_for_orders(order_ids) if order_ids else {}

    # Buyers don't need internal/admin fields
    public_fields = (
        "order_number", "status", "total_cents", "currency",
        "tracking_number", "tracking_carrier", "created_at", "paid_at", "shipped_at",
        "storefront_slug", "storefront_name", "storefront_contact_email",
    )
    result = []
    for o in orders:
        entry = {k: o.get(k) for k in public_fields}
        entry["items"] = items_by_order.get(o["id"], [])
        result.append(entry)

    return jsonify({"orders": result})


@store_bp.route("/store/orders/<order_number>/cancel", methods=["POST"])
@require_auth
def cancel_my_order(order_number: str):
    """Buyer backs out of an unpaid checkout (called from the Stripe cancel page).

    Releases the reserved stock and the buyer's monthly allowance right away
    instead of waiting up to an hour for the Stripe session to expire.
    Idempotent: cancelling an already-cancelled order succeeds.
    """
    user_id = str(session.get("user_id", 0))
    repo = _repo()
    order = repo.get_order_by_number(order_number)
    if not order or str(order["user_id"]) != user_id:
        return jsonify({"error": "Order not found"}), 404

    if order["status"] == "cancelled":
        return jsonify({"success": True, "status": "cancelled"})
    if order["status"] != "pending_payment":
        return jsonify({"error": "This order has already been paid"}), 409

    try:
        cancelled = StoreCheckoutService(repo).cancel_order(order)
    except ValueError:
        # Stripe says the buyer completed payment after all
        return jsonify({"error": "This order has already been paid"}), 409
    except Exception:
        logger.exception(f"Buyer cancel could not close Stripe session for {order_number}")
        return jsonify({"error": "Could not cancel the checkout, please try again"}), 502

    if not cancelled:
        # Status changed underneath us (expiry webhook or payment)
        status = repo.get_order(order["id"])["status"]
        if status != "cancelled":
            return jsonify({"error": "This order has already been paid"}), 409
    else:
        repo.log_action(user_id, session.get("username", "unknown"),
                        "buyer_cancel_order", f"order={order_number}")
    return jsonify({"success": True, "status": "cancelled"})


@store_bp.route("/store/orders/user/<user_id>", methods=["GET"])
@require_store_admin
def admin_user_orders(user_id: str):
    """View a specific user's orders (admin only)."""
    orders = _repo().list_orders_by_user(user_id, limit=50)
    return jsonify({"orders": orders})


# ----------------------------------------------------------------------
# Web notifications (in-app bell)
# ----------------------------------------------------------------------

@store_bp.route("/store/notifications", methods=["GET"])
@require_auth
def list_web_notifications():
    """Return undismissed web notifications for the logged-in user."""
    user_id = str(session.get("user_id", 0))
    notifications = _repo().list_web_notifications(user_id)
    return jsonify({"notifications": notifications})


@store_bp.route("/store/notifications/<int:nid>/dismiss", methods=["POST"])
@require_auth
def dismiss_web_notification(nid: int):
    user_id = str(session.get("user_id", 0))
    if not _repo().dismiss_web_notification(nid, user_id):
        return jsonify({"error": "Notification not found"}), 404
    return jsonify({"success": True})


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

    try:
        result = service.handle_event(event)
    except Exception:
        logger.exception(f"Unhandled error processing Stripe event {event['type']}")
        # Non-2xx makes Stripe retry with backoff. Handlers are idempotent
        # (mark_paid / cancel_order only transition once), so a retry after
        # a transient failure (e.g. database locked) finishes the job instead
        # of leaving a charged order stuck in pending_payment.
        return jsonify({"error": "internal error processing event"}), 500

    # 200 for events we handled or deliberately ignored so Stripe stops
    # retrying them; flagged orders are logged + audited.
    return jsonify(result), 200


@store_bp.route("/store/checkout/prefill", methods=["GET"])
@require_auth
def checkout_prefill():
    """Return email for pre-filling the checkout form."""
    user_id = str(session.get("user_id", 0))
    provider = session.get("auth_provider", "discord")

    discord_roles = session.get("discord_roles", [])
    free_shipping = bool(FREE_SHIPPING_ROLE_IDS.intersection(discord_roles))

    prefill = {
        "username": session.get("username"),
        "auth_provider": provider,
        "email": None,
        "free_shipping": free_shipping,
    }

    try:
        from repositories.user_profiles import UserProfileRepository
        profile = UserProfileRepository().get_by_user_id(user_id)
        if profile:
            prefill["email"] = profile.get("email")
    except Exception:
        logger.exception("Prefill profile lookup failed")

    if not prefill["email"]:
        last = _repo().last_shipping_address(user_id)
        if last:
            prefill["email"] = last.get("email")

    return jsonify(prefill)


# ----------------------------------------------------------------------
# Product image upload (same pattern as banner uploads)
# ----------------------------------------------------------------------

import os as _os  # noqa: E402
import uuid as _uuid  # noqa: E402
from webapp_config import STORE_UPLOADS_DIR  # noqa: E402

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB


MAX_IMAGES_PER_UPLOAD = 10


@store_bp.route("/store/admin/products/upload-image", methods=["POST"])
@require_store_staff
def upload_product_image():
    """Upload one or more product images under the ``image`` field.

    Returns ``urls`` in upload order plus ``url`` (the first) for older
    callers. Every file is validated before any is saved, so a bad file in
    the batch rejects the whole request.
    """
    if _scope_ids("products") == []:
        return jsonify({"success": False, "error": "Only storefront managers can upload images"}), 403
    files = [f for f in request.files.getlist("image") if f and f.filename]
    if not files:
        return jsonify({"success": False, "error": "No image file provided"}), 400
    if len(files) > MAX_IMAGES_PER_UPLOAD:
        return jsonify({
            "success": False,
            "error": f"Too many files. Maximum {MAX_IMAGES_PER_UPLOAD} per upload",
        }), 400

    staged = []
    allowed = ", ".join(sorted(ALLOWED_IMAGE_EXTENSIONS))
    for file in files:
        ext = _os.path.splitext(file.filename)[1].lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            return jsonify({"success": False, "error": f"Invalid format. Allowed: {allowed}"}), 400

        file.seek(0, _os.SEEK_END)
        size = file.tell()
        file.seek(0)
        if size > MAX_IMAGE_SIZE:
            return jsonify({"success": False, "error": "Image too large. Maximum 5MB"}), 400
        staged.append((file, f"{_uuid.uuid4()}{ext}"))

    actor_id, actor_name = _actor()
    repo = _repo()
    urls = []
    for file, filename in staged:
        file.save(str(STORE_UPLOADS_DIR / filename))
        repo.log_action(actor_id, actor_name, "upload_product_image", filename)
        urls.append(f"/static/uploads/store/{filename}")

    return jsonify({"success": True, "url": urls[0], "urls": urls})


# ----------------------------------------------------------------------
# Storefronts
# ----------------------------------------------------------------------

PUBLIC_STOREFRONT_FIELDS = ("id", "slug", "name", "description", "sort_order")


@store_bp.route("/store/storefronts", methods=["GET"])
def list_storefronts():
    """Active storefronts, in tab order."""
    return jsonify({
        "storefronts": [
            {**{k: s[k] for k in PUBLIC_STOREFRONT_FIELDS},
             "accepts_payments": StoreRepository.accepts_payments(s)}
            for s in _repo().list_storefronts()
        ]
    })


@store_bp.route("/store/admin/me", methods=["GET"])
@require_store_staff
def admin_me():
    """What the Store Admin page should show this user."""
    repo = _repo()
    full = is_store_admin()
    roles = {} if full else _storefront_roles()
    storefronts = []
    for s in repo.list_storefronts(include_inactive=True):
        if full or s["id"] in roles:
            storefronts.append({
                **s,
                "role": "owner" if full else roles[s["id"]],
                "accepts_payments": repo.accepts_payments(s),
                "uses_summit_stripe": s["slug"] == DEFAULT_STOREFRONT_SLUG,
            })
    return jsonify({"is_full_admin": full, "storefronts": storefronts})


def _clean_text(data: dict, key: str, max_len: int) -> str:
    return str(data.get(key) or "").strip()[:max_len]


@store_bp.route("/store/admin/storefronts", methods=["POST"])
@require_store_admin
def admin_create_storefront():
    data = request.get_json(silent=True) or {}
    name = _clean_text(data, "name", 80)
    slug = _clean_text(data, "slug", 40).lower() or slugify(name)
    repo = _repo()
    try:
        storefront_id = repo.create_storefront(
            slug=slug, name=name,
            description=_clean_text(data, "description", 1000),
            contact_email=_clean_text(data, "contact_email", 200) or None,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    actor_id, actor_name = _actor()
    repo.log_action(actor_id, actor_name, "create_storefront",
                    f"id={storefront_id} slug={slug}")
    return jsonify({"id": storefront_id, "slug": slug}), 201


@store_bp.route("/store/admin/storefronts/<int:storefront_id>", methods=["PATCH"])
@require_store_admin
def admin_update_storefront(storefront_id: int):
    data = request.get_json(silent=True) or {}
    fields: dict = {}
    if "name" in data:
        fields["name"] = _clean_text(data, "name", 80)
    if "description" in data:
        fields["description"] = _clean_text(data, "description", 1000)
    if "contact_email" in data:
        fields["contact_email"] = _clean_text(data, "contact_email", 200) or None
    if "is_active" in data:
        fields["is_active"] = 1 if data["is_active"] in (1, True, "1", "true") else 0
    if "sort_order" in data:
        try:
            fields["sort_order"] = int(data["sort_order"])
        except (TypeError, ValueError):
            return jsonify({"error": "sort_order must be an integer"}), 400
    if "shipping_cents" in data:
        if data["shipping_cents"] in (None, ""):
            fields["shipping_cents"] = None
        else:
            try:
                fields["shipping_cents"] = int(data["shipping_cents"])
            except (TypeError, ValueError):
                return jsonify({"error": "shipping_cents must be an integer"}), 400
            if fields["shipping_cents"] < 0:
                return jsonify({"error": "shipping_cents can't be negative"}), 400
    repo = _repo()
    if not repo.get_storefront(storefront_id):
        return _not_found("Storefront")
    try:
        if not repo.update_storefront(storefront_id, **fields):
            return jsonify({"error": "No valid fields to update"}), 400
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    actor_id, actor_name = _actor()
    repo.log_action(actor_id, actor_name, "update_storefront",
                    f"id={storefront_id} fields={sorted(fields)}")
    return jsonify({"success": True})


@store_bp.route("/store/admin/storefronts/<int:storefront_id>", methods=["DELETE"])
@require_store_admin
def admin_delete_storefront(storefront_id: int):
    """Delete a storefront that has never had an order."""
    repo = _repo()
    try:
        removed = repo.delete_storefront(storefront_id)
    except LookupError:
        return _not_found("Storefront")
    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    actor_id, actor_name = _actor()
    repo.log_action(
        actor_id, actor_name, "delete_storefront",
        f"id={storefront_id} name={removed['name']} products={removed['products']} "
        f"admins={removed['admins']} stripe={removed['stripe_account_id']}",
    )
    return jsonify({"success": True, **removed})


# ----------------------------------------------------------------------
# Storefront payments: each storefront besides Summit connects its own
# Stripe account. Its managers (or a full admin) run the onboarding.
# ----------------------------------------------------------------------

def _payments_status(storefront: dict) -> dict:
    return {
        "uses_summit_stripe": storefront["slug"] == DEFAULT_STOREFRONT_SLUG,
        "stripe_account_id": storefront.get("stripe_account_id"),
        "charges_enabled": bool(storefront.get("stripe_charges_enabled")),
        "accepts_payments": StoreRepository.accepts_payments(storefront),
    }


@store_bp.route("/store/admin/storefronts/<int:storefront_id>/stripe", methods=["GET"])
@require_store_staff
def admin_storefront_payments(storefront_id: int):
    repo = _repo()
    storefront = repo.get_storefront(storefront_id)
    if not storefront or not _can(storefront_id, "orders"):
        return _not_found("Storefront")
    if storefront.get("stripe_account_id") and request.args.get("refresh"):
        try:
            StoreCheckoutService(repo).refresh_account_status(storefront)
        except Exception:
            logger.exception(f"Stripe status check failed for storefront {storefront_id}")
            return jsonify({"error": "Couldn't reach Stripe, please try again"}), 502
        storefront = repo.get_storefront(storefront_id)
    return jsonify(_payments_status(storefront))


@store_bp.route("/store/admin/storefronts/<int:storefront_id>/stripe/onboard",
                methods=["POST"])
@require_store_staff
def admin_storefront_stripe_onboard(storefront_id: int):
    """Start (or resume) Stripe onboarding; returns the Stripe URL to visit."""
    repo = _repo()
    storefront = repo.get_storefront(storefront_id)
    if not storefront or not _can(storefront_id, "products"):
        return _not_found("Storefront")
    if storefront["slug"] == DEFAULT_STOREFRONT_SLUG:
        return jsonify({"error": "Summit Store uses Summit's own Stripe account"}), 400
    service = StoreCheckoutService(repo)
    if not service.is_configured():
        return jsonify({"error": "Payments are not configured"}), 503
    back = _site_url(f"/admin/store?storefront={storefront_id}&stripe=return")
    try:
        url = service.start_onboarding(storefront, return_url=back, refresh_url=back)
    except stripe.StripeError as e:
        # Stripe's own reason (e.g. Connect not turned on) tells the admin
        # what to fix; it carries no secrets.
        logger.exception(f"Stripe onboarding failed for storefront {storefront_id}")
        reason = e.user_message or str(e) or "unknown error"
        return jsonify({"error": f"Stripe said: {reason}"}), 502
    except Exception:
        logger.exception(f"Stripe onboarding failed for storefront {storefront_id}")
        return jsonify({"error": "Couldn't reach Stripe, please try again"}), 502
    actor_id, actor_name = _actor()
    repo.log_action(actor_id, actor_name, "stripe_onboard", f"storefront={storefront_id}")
    return jsonify({"url": url})


@store_bp.route("/store/admin/storefronts/<int:storefront_id>/stripe", methods=["DELETE"])
@require_store_admin
def admin_storefront_stripe_disconnect(storefront_id: int):
    """Forget a storefront's Stripe account (it stops taking orders)."""
    repo = _repo()
    storefront = repo.get_storefront(storefront_id)
    if not storefront:
        return _not_found("Storefront")
    repo.set_storefront_stripe(storefront_id, None, False)
    actor_id, actor_name = _actor()
    repo.log_action(actor_id, actor_name, "stripe_disconnect",
                    f"storefront={storefront_id} account={storefront.get('stripe_account_id')}")
    return jsonify({"success": True})


# ----------------------------------------------------------------------
# Storefront admins (only full store admins assign them)
# ----------------------------------------------------------------------

@store_bp.route("/store/admin/storefronts/<int:storefront_id>/admins", methods=["GET"])
@require_store_staff
def admin_list_storefront_admins(storefront_id: int):
    repo = _repo()
    if not repo.get_storefront(storefront_id) or not _can(storefront_id, "orders"):
        return _not_found("Storefront")
    return jsonify({"admins": repo.list_storefront_admins(storefront_id)})


@store_bp.route("/store/admin/storefronts/<int:storefront_id>/admins", methods=["POST"])
@require_store_admin
def admin_add_storefront_admin(storefront_id: int):
    """Body: {user_id, username?, role}. Re-adding someone changes their role."""
    data = request.get_json(silent=True) or {}
    user_id = _clean_text(data, "user_id", 40)
    role = data.get("role") or "manager"
    if not user_id.isdigit():
        return jsonify({"error": "Pick a user, or enter their Discord user ID"}), 400
    if role not in STOREFRONT_ROLES:
        return jsonify({"error": f"Role must be one of: {', '.join(STOREFRONT_ROLES)}"}), 400

    username = _clean_text(data, "username", 80)
    if not username:
        try:
            from repositories.user_profiles import UserProfileRepository
            profile = UserProfileRepository().get_by_user_id(user_id)
            username = (profile or {}).get("display_name") or ""
        except Exception:
            logger.exception("Profile lookup failed while adding a storefront admin")
    username = username or user_id

    repo = _repo()
    if not repo.get_storefront(storefront_id):
        return _not_found("Storefront")
    actor_id, actor_name = _actor()
    repo.add_storefront_admin(storefront_id, user_id, username, role, added_by=actor_name)
    repo.log_action(actor_id, actor_name, "add_storefront_admin",
                    f"storefront={storefront_id} user={user_id} role={role}")
    return jsonify({"success": True}), 201


@store_bp.route("/store/admin/storefronts/<int:storefront_id>/admins/<user_id>",
                methods=["DELETE"])
@require_store_admin
def admin_remove_storefront_admin(storefront_id: int, user_id: str):
    repo = _repo()
    if not repo.remove_storefront_admin(storefront_id, user_id):
        return _not_found("Admin")
    actor_id, actor_name = _actor()
    repo.log_action(actor_id, actor_name, "remove_storefront_admin",
                    f"storefront={storefront_id} user={user_id}")
    return jsonify({"success": True})


@store_bp.route("/store/admin/user-search", methods=["GET"])
@require_store_admin
def admin_user_search():
    """Find people to add as storefront admins (people who've logged in or played)."""
    return _user_search()


@store_bp.route("/store/user-search", methods=["GET"])
@require_auth
def user_search():
    """Find Summit members to name as managers or shippers on an application."""
    return _user_search()


def _user_search():
    query = (request.args.get("q") or "").strip()
    if len(query) < 2:
        return jsonify({"users": []})
    from repositories.user_profiles import UserProfileRepository
    users = UserProfileRepository().search_users(query, limit=10)
    return jsonify({
        "users": [
            {"user_id": str(u.get("user_id")), "display_name": u.get("display_name")}
            for u in users
            if str(u.get("user_id") or "").isdigit()  # Discord accounts only
        ]
    })


# ----------------------------------------------------------------------
# Storefront applications
# ----------------------------------------------------------------------

@store_bp.route("/store/storefront-applications", methods=["POST"])
@require_auth
def apply_for_storefront():
    data = request.get_json(silent=True) or {}
    name = _clean_text(data, "name", 80)
    contact_email = _clean_text(data, "contact_email", 200)
    description = _clean_text(data, "description", 2000)
    shipping = _clean_text(data, "shipping", 1000)
    website = _clean_text(data, "website", 300) or None

    missing = [label for label, value in (
        ("storefront name", name), ("contact email", contact_email),
        ("what you'd sell", description), ("shipping", shipping),
    ) if not value]
    if missing:
        return jsonify({"error": f"Please fill in: {', '.join(missing)}"}), 400
    if "@" not in contact_email:
        return jsonify({"error": "Please enter a valid contact email"}), 400
    if data.get("agreed") is not True:
        return jsonify({"error": "Please accept the storefront agreement"}), 400

    user_id = str(session.get("user_id"))
    username = session.get("username", "unknown")
    team, error = _clean_team(data.get("team"), applicant_id=user_id)
    if error:
        return jsonify({"error": error}), 400

    repo = _repo()
    try:
        application_id = repo.create_storefront_application(
            user_id=user_id, username=username, name=name,
            contact_email=contact_email, description=description,
            shipping=shipping, website=website, team=team,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    repo.log_action(user_id, username, "storefront_application",
                    f"id={application_id} name={name}")
    try:
        repo.enqueue_notification(
            None, "discord_admin", "store-admins",
            f"New storefront application: {name}",
            f"**{username}** applied for a storefront called **{name}**. "
            f"Review it in Store Admin under Storefronts.",
        )
    except Exception:
        logger.exception("Could not queue storefront application notification")
    return jsonify({"id": application_id}), 201


MAX_APPLICATION_TEAM = 10


def _clean_team(raw, applicant_id: str) -> tuple[list[dict], str | None]:
    """Validate the managers and shippers named on an application.

    Names come from Summit profiles, never from the request, so nobody can
    be listed under a made-up name. The applicant is always a manager and
    isn't listed again.
    """
    if raw in (None, ""):
        return [], None
    if not isinstance(raw, list):
        return [], "Team must be a list"
    if len(raw) > MAX_APPLICATION_TEAM:
        return [], f"You can name up to {MAX_APPLICATION_TEAM} people"
    from repositories.user_profiles import UserProfileRepository
    profiles = UserProfileRepository()
    team: dict[str, dict] = {}
    for member in raw:
        if not isinstance(member, dict):
            return [], "Each team member needs a user and a role"
        member_id = str(member.get("user_id") or "")
        role = member.get("role")
        if not member_id.isdigit():
            return [], "Pick team members from the search"
        if role not in STOREFRONT_ROLES:
            return [], f"Role must be one of: {', '.join(STOREFRONT_ROLES)}"
        if member_id == applicant_id:
            continue
        try:
            profile = profiles.get_by_user_id(member_id)
        except Exception:
            logger.exception("Profile lookup failed for an application team member")
            profile = None
        if not profile:
            return [], "One of the people you picked doesn't have a Summit profile"
        team[member_id] = {
            "user_id": member_id,
            "username": profile.get("display_name") or member_id,
            "role": role,
        }
    return list(team.values()), None


@store_bp.route("/store/storefront-applications/mine", methods=["GET"])
@require_auth
def my_storefront_applications():
    apps = _repo().list_applications_by_user(str(session.get("user_id")))
    fields = ("id", "name", "status", "created_at", "reviewed_at", "storefront_slug", "team")
    return jsonify({"applications": [{k: a.get(k) for k in fields} for a in apps]})


@store_bp.route("/store/admin/storefront-applications", methods=["GET"])
@require_store_admin
def admin_list_storefront_applications():
    try:
        apps = _repo().list_storefront_applications(request.args.get("status") or None)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"applications": apps})


@store_bp.route("/store/admin/storefront-applications/<int:application_id>/approve",
                methods=["POST"])
@require_store_admin
def admin_approve_storefront_application(application_id: int):
    """Creates the storefront and makes the applicant its manager.
    Body: {slug?} (defaults to one made from the storefront name)."""
    data = request.get_json(silent=True) or {}
    repo = _repo()
    app = repo.get_storefront_application(application_id)
    if not app:
        return _not_found("Application")
    slug = _clean_text(data, "slug", 40).lower() or slugify(app["name"])
    actor_id, actor_name = _actor()
    try:
        storefront_id = repo.approve_storefront_application(application_id, slug, actor_name)
    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    repo.log_action(actor_id, actor_name, "approve_storefront_application",
                    f"id={application_id} storefront={storefront_id} slug={slug}")
    try:
        repo.enqueue_notification(
            None, "discord_dm", app["user_id"],
            f"Your storefront {app['name']} is approved",
            f"Your storefront **{app['name']}** is approved. You can add products "
            f"from Store Admin on the Sorcerers Summit site.",
        )
    except Exception:
        logger.exception("Could not queue storefront approval DM")
    return jsonify({"storefront_id": storefront_id, "slug": slug})


@store_bp.route("/store/admin/storefront-applications/<int:application_id>/decline",
                methods=["POST"])
@require_store_admin
def admin_decline_storefront_application(application_id: int):
    repo = _repo()
    actor_id, actor_name = _actor()
    if not repo.decline_storefront_application(application_id, actor_name):
        return jsonify({"error": "Application not found or already reviewed"}), 409
    repo.log_action(actor_id, actor_name, "decline_storefront_application",
                    f"id={application_id}")
    return jsonify({"success": True})
