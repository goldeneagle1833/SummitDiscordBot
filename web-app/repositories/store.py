"""Repository for the real-money store: products, orders, order items.

Uses a dedicated store.db, isolated from game/ELO databases so that
real-money order records can be backed up and audited independently.
"""

import os
import re
import secrets
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from webapp_config import BASE_DIR

STORE_DB_PATH = Path(os.environ.get("STORE_DB_PATH", BASE_DIR / "store.db"))

ORDER_STATUSES = (
    "pending_payment",
    "paid",
    "shipped",
    "delivered",
    "cancelled",
    "refunded",
)

# Orders whose items haven't left the building, so cancelling returns stock
CANCELLABLE_STATUSES = ("pending_payment", "paid")

# Every product and order belongs to a storefront (a tab in the store).
# Rows from before storefronts existed belong to this one.
DEFAULT_STOREFRONT_SLUG = "summit"
DEFAULT_STOREFRONT_NAME = "Summit Store"

# manager: products and orders. fulfillment: orders only.
STOREFRONT_ROLES = ("manager", "fulfillment")

APPLICATION_STATUSES = ("pending", "approved", "declined")

SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")


def slugify(name: str) -> str:
    """'Explorer Store!' -> 'explorer-store'."""
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug[:40].strip("-")


class StoreRepository:
    """Data access for the token-card store."""

    def __init__(self, db_path: Path = STORE_DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
                    currency TEXT NOT NULL DEFAULT 'USD',
                    image_url TEXT,
                    stock_quantity INTEGER NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0),
                    is_active INTEGER NOT NULL DEFAULT 1,
                    max_per_user_monthly INTEGER,  -- NULL = unlimited
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_number TEXT UNIQUE NOT NULL,
                    user_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    email TEXT,
                    auth_provider TEXT DEFAULT 'discord',   -- discord | google
                    status TEXT NOT NULL DEFAULT 'pending_payment',
                    subtotal_cents INTEGER NOT NULL DEFAULT 0,
                    shipping_cents INTEGER NOT NULL DEFAULT 0,
                    tax_cents INTEGER NOT NULL DEFAULT 0,
                    total_cents INTEGER NOT NULL DEFAULT 0,
                    currency TEXT NOT NULL DEFAULT 'USD',
                    payment_provider TEXT,          -- stripe | paypal | crypto
                    payment_ref TEXT,               -- provider session/txn id
                    tracking_number TEXT,
                    tracking_carrier TEXT,
                    ship_name TEXT,
                    ship_line1 TEXT,
                    ship_line2 TEXT,
                    ship_city TEXT,
                    ship_state TEXT,
                    ship_postal TEXT,
                    ship_country TEXT DEFAULT 'US',
                    address_validated INTEGER NOT NULL DEFAULT 0,
                    admin_notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    paid_at TEXT,
                    shipped_at TEXT
                );

                CREATE TABLE IF NOT EXISTS order_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL REFERENCES orders(id),
                    product_id INTEGER NOT NULL REFERENCES products(id),
                    product_name TEXT NOT NULL,      -- snapshot at purchase time
                    unit_price_cents INTEGER NOT NULL,
                    quantity INTEGER NOT NULL CHECK (quantity > 0)
                );

                CREATE TABLE IF NOT EXISTS store_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor_id TEXT NOT NULL,
                    actor_name TEXT NOT NULL,
                    action TEXT NOT NULL,
                    details TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER REFERENCES orders(id),
                    channel TEXT NOT NULL,      -- discord_dm | discord_admin | email
                    recipient TEXT NOT NULL,    -- discord user id, channel id, or email
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',  -- pending | sent | failed
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    sent_at TEXT
                );

                CREATE TABLE IF NOT EXISTS web_notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    type TEXT NOT NULL,          -- order_paid | order_shipped
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    dismissed INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS storefronts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slug TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    contact_email TEXT,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                -- People who run one storefront. Full store admins
                -- (STORE_ADMIN_IDS) are not listed here: they see everything.
                CREATE TABLE IF NOT EXISTS storefront_admins (
                    storefront_id INTEGER NOT NULL REFERENCES storefronts(id),
                    user_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    role TEXT NOT NULL,          -- manager | fulfillment
                    added_by TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (storefront_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS storefront_applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    name TEXT NOT NULL,
                    contact_email TEXT NOT NULL,
                    website TEXT,
                    description TEXT NOT NULL,
                    shipping TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    storefront_id INTEGER REFERENCES storefronts(id),
                    reviewed_by TEXT,
                    reviewed_at TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_notif_pending
                    ON notifications(status, channel);
                CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
                CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
                CREATE INDEX IF NOT EXISTS idx_items_order ON order_items(order_id);
                CREATE INDEX IF NOT EXISTS idx_web_notif_user
                    ON web_notifications(user_id, dismissed);
                """
            )
            # Migrations for columns added after initial schema
            try:
                conn.execute("ALTER TABLE products ADD COLUMN max_per_user_monthly INTEGER")
            except sqlite3.OperationalError:
                pass  # column already exists
            try:
                # JSON list of image URLs, in display order. image_url stays
                # in sync as the first entry so older readers keep working.
                conn.execute("ALTER TABLE products ADD COLUMN images TEXT")
            except sqlite3.OperationalError:
                pass  # column already exists
            for table in ("products", "orders"):
                try:
                    conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN storefront_id INTEGER "
                        f"REFERENCES storefronts(id)"
                    )
                except sqlite3.OperationalError:
                    pass  # column already exists

            try:
                # JSON list of {user_id, username, role}: the managers and
                # shippers the applicant picked, added when it's approved
                conn.execute("ALTER TABLE storefront_applications ADD COLUMN team TEXT")
            except sqlite3.OperationalError:
                pass  # column already exists

            # Each storefront other than Summit takes payments through its
            # own Stripe account, connected to Summit's platform account.
            for column in ("stripe_account_id TEXT",
                           "stripe_charges_enabled INTEGER NOT NULL DEFAULT 0",
                           "shipping_cents INTEGER"):
                try:
                    conn.execute(f"ALTER TABLE storefronts ADD COLUMN {column}")
                except sqlite3.OperationalError:
                    pass  # column already exists

            now = self._now()
            conn.execute(
                """INSERT OR IGNORE INTO storefronts (slug, name, created_at, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (DEFAULT_STOREFRONT_SLUG, DEFAULT_STOREFRONT_NAME, now, now),
            )
            default_id = conn.execute(
                "SELECT id FROM storefronts WHERE slug = ?", (DEFAULT_STOREFRONT_SLUG,)
            ).fetchone()["id"]
            for table in ("products", "orders"):
                conn.execute(
                    f"UPDATE {table} SET storefront_id = ? WHERE storefront_id IS NULL",
                    (default_id,),
                )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_products_storefront ON products(storefront_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_orders_storefront ON orders(storefront_id)"
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    @staticmethod
    def _product_from_row(row) -> dict:
        """Row -> dict with ``images`` always a list of URL strings.

        Products created before the images column exist with only
        image_url, so fall back to that as a one-item gallery.
        """
        product = dict(row)
        raw = product.get("images")
        images: list[str] = []
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    images = [str(u) for u in parsed if u]
            except (TypeError, ValueError):
                images = []
        if not images and product.get("image_url"):
            images = [product["image_url"]]
        product["images"] = images
        return product

    @staticmethod
    def _clean_images(images) -> list[str]:
        """Validate an images value from the API into a list of URL strings."""
        if images is None:
            return []
        if not isinstance(images, (list, tuple)):
            raise ValueError("images must be a list of URLs")
        cleaned: list[str] = []
        for url in images:
            if not isinstance(url, str):
                raise ValueError("images must be a list of URLs")
            url = url.strip()
            if url and url not in cleaned:
                cleaned.append(url)
        return cleaned

    def list_products(self, include_inactive: bool = False,
                      storefront_ids: list[int] | None = None) -> list[dict]:
        """Products, optionally limited to some storefronts.

        Without include_inactive, hidden products and products of hidden
        storefronts are left out (the public catalog).
        """
        conditions = []
        params: list = []
        if not include_inactive:
            conditions.append(
                "p.is_active = 1 AND p.storefront_id IN "
                "(SELECT id FROM storefronts WHERE is_active = 1)"
            )
        if storefront_ids is not None:
            if not storefront_ids:
                return []
            conditions.append(
                f"p.storefront_id IN ({','.join('?' for _ in storefront_ids)})"
            )
            params.extend(storefront_ids)
        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        query = f"SELECT p.* FROM products p{where} ORDER BY p.name ASC"
        with self._connect() as conn:
            return [self._product_from_row(r)
                    for r in conn.execute(query, params).fetchall()]

    def get_product(self, product_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM products WHERE id = ?", (product_id,)
            ).fetchone()
            return self._product_from_row(row) if row else None

    def create_product(
        self,
        sku: str,
        name: str,
        price_cents: int,
        description: str = "",
        image_url: str | None = None,
        stock_quantity: int = 0,
        max_per_user_monthly: int | None = None,
        images: list[str] | None = None,
        storefront_id: int | None = None,
    ) -> int:
        images = self._clean_images(images)
        if not images and image_url:
            images = [image_url]
        if storefront_id is None:
            storefront_id = self.default_storefront_id()
        elif not self.get_storefront(storefront_id):
            raise ValueError("Unknown storefront")
        now = self._now()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO products
                   (sku, name, description, price_cents, image_url, images,
                    stock_quantity, max_per_user_monthly, storefront_id,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (sku, name, description, price_cents,
                 images[0] if images else None, json.dumps(images),
                 stock_quantity, max_per_user_monthly, storefront_id, now, now),
            )
            return cur.lastrowid

    def update_product(self, product_id: int, **fields) -> bool:
        allowed = {"sku", "name", "description", "price_cents", "image_url",
                   "stock_quantity", "is_active", "max_per_user_monthly", "images",
                   "storefront_id"}
        if "storefront_id" in fields and not self.get_storefront(fields["storefront_id"]):
            raise ValueError("Unknown storefront")
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return False
        if "images" in updates:
            images = self._clean_images(updates["images"])
            updates["images"] = json.dumps(images)
            updates["image_url"] = images[0] if images else None
        elif "image_url" in updates:
            # Legacy single-image writers keep the gallery consistent
            updates["images"] = json.dumps([updates["image_url"]] if updates["image_url"] else [])
        updates["updated_at"] = self._now()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        with self._connect() as conn:
            cur = conn.execute(
                f"UPDATE products SET {set_clause} WHERE id = ?",
                (*updates.values(), product_id),
            )
            return cur.rowcount > 0

    def adjust_stock(self, product_id: int, delta: int) -> bool:
        """Atomically adjust stock; refuses to go below zero."""
        with self._connect() as conn:
            cur = conn.execute(
                """UPDATE products
                   SET stock_quantity = stock_quantity + ?, updated_at = ?
                   WHERE id = ? AND stock_quantity + ? >= 0""",
                (delta, self._now(), product_id, delta),
            )
            return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_order_number() -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        return f"SUM-{stamp}-{secrets.token_hex(3).upper()}"

    def create_order(
        self,
        user_id: str,
        username: str,
        items: list[dict],          # [{product_id, quantity}]
        shipping_address: dict,     # keys: name, line1, line2, city, state, postal, country
        email: str | None = None,
        auth_provider: str = "discord",
        shipping_cents: int = 0,
        tax_cents: int = 0,
        address_validated: bool = False,
    ) -> dict:
        """Create a pending order, snapshotting product names and prices.

        Decrements stock atomically; raises ValueError on insufficient stock
        or unknown/inactive products.
        """
        now = self._now()
        order_number = self._generate_order_number()

        # Check monthly per-user limits before reserving stock
        monthly_counts = self.user_monthly_product_counts(user_id)

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                subtotal = 0
                snapshots = []
                storefront_id = None
                for item in items:
                    row = conn.execute(
                        "SELECT * FROM products WHERE id = ? AND is_active = 1",
                        (item["product_id"],),
                    ).fetchone()
                    if row is None:
                        raise ValueError(f"Product {item['product_id']} not available")
                    # Each storefront is its own order and its own checkout
                    if storefront_id is None:
                        storefront_id = row["storefront_id"]
                    elif row["storefront_id"] != storefront_id:
                        raise ValueError(
                            "Items from different storefronts have to be "
                            "checked out separately"
                        )
                    qty = int(item["quantity"])
                    if qty <= 0:
                        raise ValueError("Quantity must be positive")
                    # Enforce per-user monthly limit
                    cap = row["max_per_user_monthly"]
                    if cap is not None:
                        already = monthly_counts.get(row["id"], 0)
                        if already + qty > cap:
                            remaining = max(0, cap - already)
                            raise ValueError(
                                f"You can only buy {cap} of {row['name']} per month "
                                f"({remaining} remaining)"
                            )
                    updated = conn.execute(
                        """UPDATE products
                           SET stock_quantity = stock_quantity - ?, updated_at = ?
                           WHERE id = ? AND stock_quantity >= ?""",
                        (qty, now, row["id"], qty),
                    )
                    if updated.rowcount == 0:
                        raise ValueError(f"Insufficient stock for {row['name']}")
                    subtotal += row["price_cents"] * qty
                    snapshots.append((row["id"], row["name"], row["price_cents"], qty))

                total = subtotal + shipping_cents + tax_cents
                cur = conn.execute(
                    """INSERT INTO orders
                       (order_number, user_id, username, email, auth_provider, status,
                        storefront_id,
                        subtotal_cents, shipping_cents, tax_cents, total_cents,
                        ship_name, ship_line1, ship_line2, ship_city, ship_state,
                        ship_postal, ship_country, address_validated,
                        created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, 'pending_payment', ?,
                               ?, ?, ?, ?,
                               ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        order_number, str(user_id), username, email, auth_provider,
                        storefront_id,
                        subtotal, shipping_cents, tax_cents, total,
                        shipping_address.get("name"),
                        shipping_address.get("line1"),
                        shipping_address.get("line2"),
                        shipping_address.get("city"),
                        shipping_address.get("state"),
                        shipping_address.get("postal"),
                        shipping_address.get("country", "US"),
                        1 if address_validated else 0,
                        now, now,
                    ),
                )
                order_id = cur.lastrowid
                for product_id, name, price, qty in snapshots:
                    conn.execute(
                        """INSERT INTO order_items
                           (order_id, product_id, product_name, unit_price_cents, quantity)
                           VALUES (?, ?, ?, ?, ?)""",
                        (order_id, product_id, name, price, qty),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        return {"id": order_id, "order_number": order_number, "total_cents": total}

    def get_order(self, order_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
            if row is None:
                return None
            order = dict(row)
            order["items"] = [
                dict(r) for r in conn.execute(
                    """SELECT oi.*, p.image_url, p.sku
                       FROM order_items oi
                       LEFT JOIN products p ON p.id = oi.product_id
                       WHERE oi.order_id = ?""",
                    (order_id,),
                ).fetchall()
            ]
            return order

    def get_order_by_number(self, order_number: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM orders WHERE order_number = ?", (order_number,)
            ).fetchone()
        return self.get_order(row["id"]) if row else None

    def get_order_by_payment_ref(self, provider: str, payment_ref: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM orders WHERE payment_provider = ? AND payment_ref = ?",
                (provider, payment_ref),
            ).fetchone()
            return dict(row) if row else None

    def list_orders(self, status: str | None = None, limit: int = 100) -> list[dict]:
        query = "SELECT * FROM orders"
        params: tuple = ()
        if status:
            if status not in ORDER_STATUSES:
                raise ValueError(f"Unknown status: {status}")
            query += " WHERE status = ?"
            params = (status,)
        query += " ORDER BY created_at DESC LIMIT ?"
        params += (limit,)
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(query, params).fetchall()]

    def list_orders_by_user(self, user_id: str, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            return [
                dict(r) for r in conn.execute(
                    """SELECT o.*, s.slug AS storefront_slug, s.name AS storefront_name,
                              s.contact_email AS storefront_contact_email
                       FROM orders o
                       LEFT JOIN storefronts s ON s.id = o.storefront_id
                       WHERE o.user_id = ? ORDER BY o.created_at DESC LIMIT ?""",
                    (str(user_id), limit),
                ).fetchall()
            ]

    def update_shipping_address(self, order_id: int, address: dict) -> bool:
        """Update the shipping address on an order (e.g. from Stripe shipping_details)."""
        with self._connect() as conn:
            cur = conn.execute(
                """UPDATE orders SET
                   ship_name = ?, ship_line1 = ?, ship_line2 = ?,
                   ship_city = ?, ship_state = ?, ship_postal = ?,
                   ship_country = ?, address_validated = 1, updated_at = ?
                   WHERE id = ?""",
                (
                    address.get("name", ""),
                    address.get("line1", ""),
                    address.get("line2", ""),
                    address.get("city", ""),
                    address.get("state", ""),
                    address.get("postal", ""),
                    address.get("country", "US"),
                    self._now(),
                    order_id,
                ),
            )
            return cur.rowcount > 0

    def attach_payment(self, order_id: int, provider: str, payment_ref: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                """UPDATE orders SET payment_provider = ?, payment_ref = ?, updated_at = ?
                   WHERE id = ? AND status = 'pending_payment'""",
                (provider, payment_ref, self._now(), order_id),
            )
            return cur.rowcount > 0

    def mark_paid(self, order_id: int) -> bool:
        """Idempotent: only transitions pending_payment -> paid."""
        now = self._now()
        with self._connect() as conn:
            cur = conn.execute(
                """UPDATE orders SET status = 'paid', paid_at = ?, updated_at = ?
                   WHERE id = ? AND status = 'pending_payment'""",
                (now, now, order_id),
            )
            return cur.rowcount > 0

    def mark_shipped(self, order_id: int, tracking_number: str | None,
                     tracking_carrier: str | None = None) -> bool:
        now = self._now()
        with self._connect() as conn:
            cur = conn.execute(
                """UPDATE orders
                   SET status = 'shipped', tracking_number = ?, tracking_carrier = ?,
                       shipped_at = ?, updated_at = ?
                   WHERE id = ? AND status = 'paid'""",
                (tracking_number, tracking_carrier, now, now, order_id),
            )
            return cur.rowcount > 0

    def set_status(self, order_id: int, status: str) -> bool:
        if status not in ORDER_STATUSES:
            raise ValueError(f"Unknown status: {status}")
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE orders SET status = ?, updated_at = ? WHERE id = ?",
                (status, self._now(), order_id),
            )
            return cur.rowcount > 0

    def cancel_order(self, order_id: int,
                     from_statuses: tuple[str, ...] = CANCELLABLE_STATUSES) -> bool:
        """Cancel an order and return its stock, exactly once.

        The status transition and the restock happen in one transaction, and
        only when the order is currently in one of `from_statuses`. A repeat
        cancel (double click, admin cancel racing the Stripe expiry webhook)
        is a no-op returning False, so stock is never returned twice.
        """
        now = self._now()
        placeholders = ",".join("?" for _ in from_statuses)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cur = conn.execute(
                    f"""UPDATE orders SET status = 'cancelled', updated_at = ?
                        WHERE id = ? AND status IN ({placeholders})""",
                    (now, order_id, *from_statuses),
                )
                if cur.rowcount == 0:
                    conn.rollback()
                    return False
                items = conn.execute(
                    "SELECT product_id, quantity FROM order_items WHERE order_id = ?",
                    (order_id,),
                ).fetchall()
                for item in items:
                    conn.execute(
                        """UPDATE products SET stock_quantity = stock_quantity + ?,
                           updated_at = ? WHERE id = ?""",
                        (item["quantity"], now, item["product_id"]),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return True

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    def log_action(self, actor_id: str, actor_name: str, action: str,
                   details: str = "") -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO store_audit (actor_id, actor_name, action, details, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (str(actor_id), actor_name, action, details, self._now()),
            )

    def list_audit(self, limit: int = 200) -> list[dict]:
        with self._connect() as conn:
            return [
                dict(r) for r in conn.execute(
                    "SELECT * FROM store_audit ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            ]

    # ------------------------------------------------------------------
    # Notifications outbox (web app writes, bot/email sender consumes)
    # ------------------------------------------------------------------

    def enqueue_notification(self, order_id: int | None, channel: str,
                             recipient: str, subject: str, body: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO notifications
                   (order_id, channel, recipient, subject, body, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (order_id, channel, str(recipient), subject, body, self._now()),
            )
            return cur.lastrowid

    def fetch_pending_notifications(self, channels: tuple[str, ...],
                                    max_attempts: int = 5,
                                    limit: int = 20) -> list[dict]:
        placeholders = ",".join("?" for _ in channels)
        with self._connect() as conn:
            return [
                dict(r) for r in conn.execute(
                    f"""SELECT * FROM notifications
                        WHERE status = 'pending' AND channel IN ({placeholders})
                          AND attempts < ?
                        ORDER BY created_at ASC LIMIT ?""",
                    (*channels, max_attempts, limit),
                ).fetchall()
            ]

    def mark_notification(self, notification_id: int, success: bool,
                          error: str | None = None) -> None:
        with self._connect() as conn:
            if success:
                conn.execute(
                    """UPDATE notifications SET status = 'sent', sent_at = ?,
                       attempts = attempts + 1 WHERE id = ?""",
                    (self._now(), notification_id),
                )
            else:
                conn.execute(
                    """UPDATE notifications
                       SET attempts = attempts + 1, last_error = ?,
                           status = CASE WHEN attempts + 1 >= 5
                                    THEN 'failed' ELSE 'pending' END
                       WHERE id = ?""",
                    (error, notification_id),
                )

    # ------------------------------------------------------------------
    # Prefill helpers
    # ------------------------------------------------------------------

    def user_monthly_product_counts(self, user_id: str) -> dict[int, int]:
        """Count how many of each product this user ordered this calendar month.

        Only counts non-cancelled/refunded orders.
        Returns {product_id: total_quantity}.
        """
        month_start = datetime.now(timezone.utc).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT oi.product_id, SUM(oi.quantity) as total
                   FROM order_items oi
                   JOIN orders o ON o.id = oi.order_id
                   WHERE o.user_id = ?
                     AND o.status NOT IN ('cancelled', 'refunded')
                     AND o.created_at >= ?
                   GROUP BY oi.product_id""",
                (str(user_id), month_start),
            ).fetchall()
            return {r["product_id"]: r["total"] for r in rows}

    # ------------------------------------------------------------------
    # Web notifications (in-app bell)
    # ------------------------------------------------------------------

    def create_web_notification(self, user_id: str, ntype: str,
                                title: str, body: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO web_notifications
                   (user_id, type, title, body, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (str(user_id), ntype, title, body, self._now()),
            )
            return cur.lastrowid

    def list_web_notifications(self, user_id: str,
                               limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            return [
                dict(r) for r in conn.execute(
                    """SELECT * FROM web_notifications
                       WHERE user_id = ? AND dismissed = 0
                       ORDER BY created_at DESC LIMIT ?""",
                    (str(user_id), limit),
                ).fetchall()
            ]

    def dismiss_web_notification(self, notification_id: int,
                                 user_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                """UPDATE web_notifications SET dismissed = 1
                   WHERE id = ? AND user_id = ?""",
                (notification_id, str(user_id)),
            )
            return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Admin order filtering
    # ------------------------------------------------------------------

    def list_orders_filtered(self, status: str | None = None,
                             product_id: int | None = None,
                             search: str | None = None,
                             date_from: str | None = None,
                             date_to: str | None = None,
                             limit: int = 100,
                             storefront_ids: list[int] | None = None) -> list[dict]:
        """List orders with optional filters for admin views.

        storefront_ids limits the result to those storefronts (a storefront
        admin's scope); None means every storefront.
        """
        conditions = []
        params: list = []

        if storefront_ids is not None:
            if not storefront_ids:
                return []
            conditions.append(
                f"o.storefront_id IN ({','.join('?' for _ in storefront_ids)})"
            )
            params.extend(storefront_ids)

        if status:
            if status not in ORDER_STATUSES:
                raise ValueError(f"Unknown status: {status}")
            conditions.append("o.status = ?")
            params.append(status)

        if product_id:
            conditions.append(
                "o.id IN (SELECT order_id FROM order_items WHERE product_id = ?)"
            )
            params.append(product_id)

        if search:
            conditions.append(
                "(o.username LIKE ? OR o.order_number LIKE ?)"
            )
            params.extend([f"%{search}%", f"%{search}%"])

        if date_from:
            conditions.append("o.created_at >= ?")
            params.append(date_from)

        if date_to:
            conditions.append("o.created_at <= ?")
            params.append(date_to)

        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        query = (
            f"SELECT o.*, s.slug AS storefront_slug, s.name AS storefront_name "
            f"FROM orders o LEFT JOIN storefronts s ON s.id = o.storefront_id"
            f"{where} ORDER BY o.created_at DESC LIMIT ?"
        )
        params.append(limit)

        with self._connect() as conn:
            return [dict(r) for r in conn.execute(query, params).fetchall()]

    def get_items_for_orders(self, order_ids: list[int]) -> dict[int, list[dict]]:
        """Return order items grouped by order_id, with product image_url."""
        if not order_ids:
            return {}
        placeholders = ",".join("?" for _ in order_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""SELECT oi.order_id, oi.product_name, oi.unit_price_cents,
                           oi.quantity, p.image_url
                    FROM order_items oi
                    LEFT JOIN products p ON p.id = oi.product_id
                    WHERE oi.order_id IN ({placeholders})
                    ORDER BY oi.id""",
                order_ids,
            ).fetchall()
        result: dict[int, list[dict]] = {}
        for r in rows:
            d = dict(r)
            oid = d.pop("order_id")
            result.setdefault(oid, []).append(d)
        return result

    def last_shipping_address(self, user_id: str) -> dict | None:
        """Most recent shipping address this user checked out with."""
        with self._connect() as conn:
            row = conn.execute(
                """SELECT ship_name, ship_line1, ship_line2, ship_city,
                          ship_state, ship_postal, ship_country, email
                   FROM orders WHERE user_id = ?
                   ORDER BY created_at DESC LIMIT 1""",
                (str(user_id),),
            ).fetchone()
            if row is None:
                return None
            d = dict(row)
            return {
                "name": d["ship_name"], "line1": d["ship_line1"],
                "line2": d["ship_line2"], "city": d["ship_city"],
                "state": d["ship_state"], "postal": d["ship_postal"],
                "country": d["ship_country"], "email": d["email"],
            }

    # ------------------------------------------------------------------
    # Storefronts (the tabs in the store)
    # ------------------------------------------------------------------

    def list_storefronts(self, include_inactive: bool = False) -> list[dict]:
        query = "SELECT * FROM storefronts"
        if not include_inactive:
            query += " WHERE is_active = 1"
        query += " ORDER BY sort_order ASC, id ASC"
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(query).fetchall()]

    def get_storefront(self, storefront_id) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM storefronts WHERE id = ?", (storefront_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_storefront_by_slug(self, slug: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM storefronts WHERE slug = ?", (slug,)
            ).fetchone()
            return dict(row) if row else None

    def default_storefront_id(self) -> int:
        return self.get_storefront_by_slug(DEFAULT_STOREFRONT_SLUG)["id"]

    @staticmethod
    def _create_storefront(conn, slug: str, name: str, description: str,
                           contact_email: str | None, now: str) -> int:
        if not SLUG_PATTERN.match(slug or ""):
            raise ValueError(
                "Web address must be 2-40 lowercase letters, numbers or dashes"
            )
        if not (name or "").strip():
            raise ValueError("Storefront name is required")
        next_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM storefronts"
        ).fetchone()[0]
        try:
            cur = conn.execute(
                """INSERT INTO storefronts
                   (slug, name, description, contact_email, sort_order,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (slug, name.strip(), description or "", contact_email,
                 next_order, now, now),
            )
        except sqlite3.IntegrityError:
            raise ValueError(f"A storefront already uses /{slug}")
        return cur.lastrowid

    def create_storefront(self, slug: str, name: str, description: str = "",
                          contact_email: str | None = None) -> int:
        with self._connect() as conn:
            return self._create_storefront(
                conn, slug, name, description, contact_email, self._now()
            )

    def update_storefront(self, storefront_id: int, **fields) -> bool:
        allowed = {"name", "description", "contact_email", "sort_order", "is_active",
                   "shipping_cents"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return False
        if "name" in updates and not str(updates["name"] or "").strip():
            raise ValueError("Storefront name is required")
        updates["updated_at"] = self._now()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        with self._connect() as conn:
            cur = conn.execute(
                f"UPDATE storefronts SET {set_clause} WHERE id = ?",
                (*updates.values(), storefront_id),
            )
            return cur.rowcount > 0

    def delete_storefront(self, storefront_id: int) -> dict:
        """Delete a storefront with its products, admins and Stripe link.

        Refused for Summit Store, and for any storefront that has orders:
        order history has to stay, so those can only be hidden. Returns
        what was removed.
        """
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                storefront = conn.execute(
                    "SELECT * FROM storefronts WHERE id = ?", (storefront_id,)
                ).fetchone()
                if storefront is None:
                    raise LookupError("Storefront not found")
                if storefront["slug"] == DEFAULT_STOREFRONT_SLUG:
                    raise ValueError("Summit Store can't be deleted")
                orders = conn.execute(
                    "SELECT COUNT(*) FROM orders WHERE storefront_id = ?", (storefront_id,)
                ).fetchone()[0]
                if orders:
                    raise ValueError(
                        f"{storefront['name']} has {orders} "
                        f"order{'s' if orders != 1 else ''}, so it can't be deleted. "
                        f"Hide it instead to keep its order history."
                    )
                products = conn.execute(
                    "DELETE FROM products WHERE storefront_id = ?", (storefront_id,)
                ).rowcount
                admins = conn.execute(
                    "DELETE FROM storefront_admins WHERE storefront_id = ?", (storefront_id,)
                ).rowcount
                # Keep the application on record, just unlinked
                conn.execute(
                    "UPDATE storefront_applications SET storefront_id = NULL "
                    "WHERE storefront_id = ?", (storefront_id,)
                )
                conn.execute("DELETE FROM storefronts WHERE id = ?", (storefront_id,))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return {"name": storefront["name"], "products": products, "admins": admins,
                "stripe_account_id": storefront["stripe_account_id"]}

    def set_storefront_stripe(self, storefront_id: int, account_id: str | None,
                              charges_enabled: bool) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                """UPDATE storefronts SET stripe_account_id = ?,
                   stripe_charges_enabled = ?, updated_at = ? WHERE id = ?""",
                (account_id, 1 if charges_enabled else 0, self._now(), storefront_id),
            )
            return cur.rowcount > 0

    def set_stripe_charges_enabled(self, account_id: str, charges_enabled: bool) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                """UPDATE storefronts SET stripe_charges_enabled = ?, updated_at = ?
                   WHERE stripe_account_id = ?""",
                (1 if charges_enabled else 0, self._now(), account_id),
            )
            return cur.rowcount > 0

    @staticmethod
    def stripe_account_for(storefront: dict | None) -> str | None:
        """The connected Stripe account that takes this storefront's payments.

        None means Summit's own (platform) account.
        """
        if not storefront or storefront.get("slug") == DEFAULT_STOREFRONT_SLUG:
            return None
        return storefront.get("stripe_account_id") or None

    @staticmethod
    def accepts_payments(storefront: dict | None) -> bool:
        if not storefront:
            return False
        if storefront.get("slug") == DEFAULT_STOREFRONT_SLUG:
            return True
        return bool(storefront.get("stripe_account_id")
                    and storefront.get("stripe_charges_enabled"))

    # ------------------------------------------------------------------
    # Storefront admins
    # ------------------------------------------------------------------

    def list_storefront_admins(self, storefront_id: int) -> list[dict]:
        with self._connect() as conn:
            return [
                dict(r) for r in conn.execute(
                    """SELECT * FROM storefront_admins WHERE storefront_id = ?
                       ORDER BY role ASC, username COLLATE NOCASE ASC""",
                    (storefront_id,),
                ).fetchall()
            ]

    def add_storefront_admin(self, storefront_id: int, user_id: str, username: str,
                             role: str, added_by: str | None = None) -> None:
        """Add someone to a storefront, or change their role if already there."""
        if role not in STOREFRONT_ROLES:
            raise ValueError(f"Role must be one of: {', '.join(STOREFRONT_ROLES)}")
        if not self.get_storefront(storefront_id):
            raise ValueError("Unknown storefront")
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO storefront_admins
                   (storefront_id, user_id, username, role, added_by, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(storefront_id, user_id)
                   DO UPDATE SET role = excluded.role, username = excluded.username""",
                (storefront_id, str(user_id), username, role, added_by, self._now()),
            )

    def remove_storefront_admin(self, storefront_id: int, user_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM storefront_admins WHERE storefront_id = ? AND user_id = ?",
                (storefront_id, str(user_id)),
            )
            return cur.rowcount > 0

    def storefront_roles_for_user(self, user_id: str) -> dict[int, str]:
        """{storefront_id: role} for every storefront this user helps run."""
        with self._connect() as conn:
            return {
                r["storefront_id"]: r["role"]
                for r in conn.execute(
                    "SELECT storefront_id, role FROM storefront_admins WHERE user_id = ?",
                    (str(user_id),),
                ).fetchall()
            }

    # ------------------------------------------------------------------
    # Storefront applications
    # ------------------------------------------------------------------

    def create_storefront_application(self, user_id: str, username: str, name: str,
                                      contact_email: str, description: str,
                                      shipping: str, website: str | None = None,
                                      team: list[dict] | None = None) -> int:
        with self._connect() as conn:
            pending = conn.execute(
                """SELECT 1 FROM storefront_applications
                   WHERE user_id = ? AND status = 'pending'""",
                (str(user_id),),
            ).fetchone()
            if pending:
                raise ValueError("You already have an application waiting for review")
            cur = conn.execute(
                """INSERT INTO storefront_applications
                   (user_id, username, name, contact_email, website, description,
                    shipping, team, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(user_id), username, name, contact_email, website,
                 description, shipping, json.dumps(team or []), self._now()),
            )
            return cur.lastrowid

    def list_storefront_applications(self, status: str | None = None) -> list[dict]:
        query = "SELECT * FROM storefront_applications"
        params: tuple = ()
        if status:
            if status not in APPLICATION_STATUSES:
                raise ValueError(f"Unknown status: {status}")
            query += " WHERE status = ?"
            params = (status,)
        query += " ORDER BY created_at DESC"
        with self._connect() as conn:
            return [self._application_from_row(r)
                    for r in conn.execute(query, params).fetchall()]

    @staticmethod
    def _application_from_row(row) -> dict:
        app = dict(row)
        try:
            app["team"] = json.loads(app.get("team") or "[]")
        except (TypeError, ValueError):
            app["team"] = []
        return app

    def list_applications_by_user(self, user_id: str) -> list[dict]:
        with self._connect() as conn:
            return [
                self._application_from_row(r) for r in conn.execute(
                    """SELECT a.*, s.slug AS storefront_slug
                       FROM storefront_applications a
                       LEFT JOIN storefronts s ON s.id = a.storefront_id
                       WHERE a.user_id = ? ORDER BY a.created_at DESC""",
                    (str(user_id),),
                ).fetchall()
            ]

    def get_storefront_application(self, application_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM storefront_applications WHERE id = ?", (application_id,)
            ).fetchone()
            return self._application_from_row(row) if row else None

    def approve_storefront_application(self, application_id: int, slug: str,
                                       reviewer: str) -> int:
        """Create the storefront, make the applicant its manager, close the
        application. All or nothing. Returns the new storefront id."""
        now = self._now()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                app = conn.execute(
                    """SELECT * FROM storefront_applications
                       WHERE id = ? AND status = 'pending'""",
                    (application_id,),
                ).fetchone()
                if app is None:
                    raise ValueError("Application not found or already reviewed")
                storefront_id = self._create_storefront(
                    conn, slug, app["name"], app["description"],
                    app["contact_email"], now,
                )
                conn.execute(
                    """INSERT INTO storefront_admins
                       (storefront_id, user_id, username, role, added_by, created_at)
                       VALUES (?, ?, ?, 'manager', ?, ?)""",
                    (storefront_id, app["user_id"], app["username"], reviewer, now),
                )
                try:
                    team = json.loads(app["team"] or "[]")
                except (TypeError, ValueError):
                    team = []
                for member in team:
                    if member.get("role") not in STOREFRONT_ROLES:
                        continue
                    conn.execute(
                        """INSERT OR IGNORE INTO storefront_admins
                           (storefront_id, user_id, username, role, added_by, created_at)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (storefront_id, str(member["user_id"]),
                         member.get("username") or str(member["user_id"]),
                         member["role"], reviewer, now),
                    )
                conn.execute(
                    """UPDATE storefront_applications
                       SET status = 'approved', storefront_id = ?, reviewed_by = ?,
                           reviewed_at = ?
                       WHERE id = ?""",
                    (storefront_id, reviewer, now, application_id),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return storefront_id

    def decline_storefront_application(self, application_id: int, reviewer: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                """UPDATE storefront_applications
                   SET status = 'declined', reviewed_by = ?, reviewed_at = ?
                   WHERE id = ? AND status = 'pending'""",
                (reviewer, self._now(), application_id),
            )
            return cur.rowcount > 0
