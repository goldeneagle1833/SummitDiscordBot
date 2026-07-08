"""Repository for the real-money store: products, orders, order items.

Uses a dedicated store.db, isolated from game/ELO databases so that
real-money order records can be backed up and audited independently.
"""

import os
import secrets
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

                CREATE INDEX IF NOT EXISTS idx_notif_pending
                    ON notifications(status, channel);
                CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
                CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
                CREATE INDEX IF NOT EXISTS idx_items_order ON order_items(order_id);
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    def list_products(self, include_inactive: bool = False) -> list[dict]:
        query = "SELECT * FROM products"
        if not include_inactive:
            query += " WHERE is_active = 1"
        query += " ORDER BY name ASC"
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(query).fetchall()]

    def get_product(self, product_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM products WHERE id = ?", (product_id,)
            ).fetchone()
            return dict(row) if row else None

    def create_product(
        self,
        sku: str,
        name: str,
        price_cents: int,
        description: str = "",
        image_url: str | None = None,
        stock_quantity: int = 0,
    ) -> int:
        now = self._now()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO products
                   (sku, name, description, price_cents, image_url,
                    stock_quantity, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (sku, name, description, price_cents, image_url,
                 stock_quantity, now, now),
            )
            return cur.lastrowid

    def update_product(self, product_id: int, **fields) -> bool:
        allowed = {"sku", "name", "description", "price_cents", "image_url",
                   "stock_quantity", "is_active"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return False
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

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                subtotal = 0
                snapshots = []
                for item in items:
                    row = conn.execute(
                        "SELECT * FROM products WHERE id = ? AND is_active = 1",
                        (item["product_id"],),
                    ).fetchone()
                    if row is None:
                        raise ValueError(f"Product {item['product_id']} not available")
                    qty = int(item["quantity"])
                    if qty <= 0:
                        raise ValueError("Quantity must be positive")
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
                        subtotal_cents, shipping_cents, tax_cents, total_cents,
                        ship_name, ship_line1, ship_line2, ship_city, ship_state,
                        ship_postal, ship_country, address_validated,
                        created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, 'pending_payment',
                               ?, ?, ?, ?,
                               ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        order_number, str(user_id), username, email, auth_provider,
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
                    "SELECT * FROM order_items WHERE order_id = ?", (order_id,)
                ).fetchall()
            ]
            return order

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

    def mark_shipped(self, order_id: int, tracking_number: str,
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

    def restock_order_items(self, order_id: int) -> None:
        """Return stock for a cancelled/expired order."""
        with self._connect() as conn:
            items = conn.execute(
                "SELECT product_id, quantity FROM order_items WHERE order_id = ?",
                (order_id,),
            ).fetchall()
            for item in items:
                conn.execute(
                    """UPDATE products SET stock_quantity = stock_quantity + ?,
                       updated_at = ? WHERE id = ?""",
                    (item["quantity"], self._now(), item["product_id"]),
                )

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
