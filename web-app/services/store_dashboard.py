"""Sales numbers for the Store Admin dashboard and the monthly sales CSV.

Everything is read from store.db (orders, order items, products, audit log);
nothing calls Stripe. A "sale" is an order that was paid and not refunded
(status paid, shipped or delivered), dated by when it was paid. Refunded
orders are reported separately. Every query is limited to the storefronts
the viewer may see.
"""

import re
from datetime import datetime, timedelta, timezone

from repositories.store import StoreRepository

SOLD_STATUSES = ("paid", "shipped", "delivered")
LOW_STOCK = 3  # products at or below this many left show under Needs attention
FLAG_ACTIONS = ("amount_mismatch", "paid_after_cancel", "account_mismatch")
TOP_N = 5


def _in(column: str, values) -> tuple[str, list]:
    values = list(values)
    return f"{column} IN ({','.join('?' for _ in values)})", values


class StoreDashboard:
    def __init__(self, repo: StoreRepository | None = None):
        self.repo = repo or StoreRepository()

    def _scope(self, storefront_ids: list[int] | None, alias: str = "o") -> tuple[str, list]:
        """SQL condition limiting rows to these storefronts (None = all)."""
        if storefront_ids is None:
            return "1 = 1", []
        if not storefront_ids:
            return "1 = 0", []
        return _in(f"{alias}.storefront_id", storefront_ids)

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    def summary(self, storefront_ids: list[int] | None, days: int,
                now: datetime | None = None) -> dict:
        now = now or datetime.now(timezone.utc)
        start = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0) \
            + timedelta(days=1)
        prev_start = start - timedelta(days=days)
        s, p, e = start.isoformat(), prev_start.isoformat(), now.isoformat()
        scope, args = self._scope(storefront_ids)

        with self.repo._connect() as conn:
            return {
                "days": days,
                "from": start.date().isoformat(),
                "to": now.date().isoformat(),
                "totals": self._totals(conn, scope, args, s, e),
                "previous": self._totals(conn, scope, args, p, s),
                "daily": self._daily(conn, scope, args, start, now),
                "attention": self._attention(conn, scope, args, storefront_ids, now),
                "top_products": self._top_products(conn, scope, args, s, e),
                "money": self._money(conn, scope, args, s, e),
                "repeat_buyers": self._repeat_buyers(conn, scope, args, s, e),
                "ship_time": self._ship_time(conn, scope, args, s, e),
                "limit_hits": self._limit_hits(conn, storefront_ids, s, e),
            }

    def _totals(self, conn, scope, args, start, end) -> dict:
        sold, sold_args = _in("o.status", SOLD_STATUSES)
        row = conn.execute(
            f"""SELECT COUNT(*) AS orders, COALESCE(SUM(o.total_cents), 0) AS sales,
                       COALESCE(SUM((SELECT SUM(quantity) FROM order_items
                                     WHERE order_id = o.id)), 0) AS units
                FROM orders o
                WHERE {sold} AND o.paid_at >= ? AND o.paid_at < ? AND {scope}""",
            (*sold_args, start, end, *args),
        ).fetchone()
        orders = row["orders"]
        return {
            "sales_cents": row["sales"],
            "orders": orders,
            "units": row["units"],
            "average_cents": round(row["sales"] / orders) if orders else 0,
        }

    def _daily(self, conn, scope, args, start, now) -> list[dict]:
        sold, sold_args = _in("o.status", SOLD_STATUSES)
        paid = {
            r["day"]: r["cents"] for r in conn.execute(
                f"""SELECT substr(o.paid_at, 1, 10) AS day, SUM(o.total_cents) AS cents
                    FROM orders o
                    WHERE {sold} AND o.paid_at >= ? AND {scope}
                    GROUP BY day""",
                (*sold_args, start.isoformat(), *args),
            )
        }
        # Checkouts that were started but never paid (expired or cancelled)
        unpaid = {
            r["day"]: r["cents"] for r in conn.execute(
                f"""SELECT substr(o.created_at, 1, 10) AS day, SUM(o.total_cents) AS cents
                    FROM orders o
                    WHERE o.status = 'cancelled' AND o.paid_at IS NULL
                      AND o.created_at >= ? AND {scope}
                    GROUP BY day""",
                (start.isoformat(), *args),
            )
        }
        out, day = [], start.date()
        while day <= now.date():
            key = day.isoformat()
            out.append({"date": key, "sales_cents": paid.get(key, 0),
                        "unfinished_cents": unpaid.get(key, 0)})
            day += timedelta(days=1)
        return out

    def _attention(self, conn, scope, args, storefront_ids, now) -> dict:
        to_ship = conn.execute(
            f"""SELECT COUNT(*) AS n, MIN(o.paid_at) AS oldest FROM orders o
                WHERE o.status = 'paid' AND {scope}""", args,
        ).fetchone()
        awaiting = conn.execute(
            f"SELECT COUNT(*) FROM orders o WHERE o.status = 'pending_payment' AND {scope}",
            args,
        ).fetchone()[0]
        week_ago = (now - timedelta(days=7)).isoformat()
        unfinished = conn.execute(
            f"""SELECT COUNT(*) AS n, COALESCE(SUM(o.total_cents), 0) AS cents FROM orders o
                WHERE o.status = 'cancelled' AND o.paid_at IS NULL
                  AND o.created_at >= ? AND {scope}""",
            (week_ago, *args),
        ).fetchone()
        p_scope, p_args = self._scope(storefront_ids, "p")
        low = [
            {"id": r["id"], "name": r["name"], "stock": r["stock_quantity"]}
            for r in conn.execute(
                f"""SELECT p.id, p.name, p.stock_quantity FROM products p
                    WHERE p.is_active = 1 AND p.stock_quantity <= ? AND {p_scope}
                    ORDER BY p.stock_quantity, p.name""",
                (LOW_STOCK, *p_args),
            )
        ]
        return {
            "to_ship": to_ship["n"],
            "oldest_to_ship_at": to_ship["oldest"],
            "awaiting_payment": awaiting,
            "unfinished_week": unfinished["n"],
            "unfinished_week_cents": unfinished["cents"],
            "low_stock": low,
            "flagged": self._flagged(conn, storefront_ids, now),
        }

    def _flagged(self, conn, storefront_ids, now) -> int:
        """Payment problems logged by the webhook in the last 30 days."""
        actions, a_args = _in("action", FLAG_ACTIONS)
        rows = conn.execute(
            f"SELECT details FROM store_audit WHERE {actions} AND created_at >= ?",
            (*a_args, (now - timedelta(days=30)).isoformat()),
        ).fetchall()
        if storefront_ids is None:
            return len(rows)
        count = 0
        for r in rows:
            m = re.search(r"order=(\S+)", r["details"] or "")
            if not m:
                continue
            order = conn.execute(
                "SELECT storefront_id FROM orders WHERE order_number = ?", (m.group(1),)
            ).fetchone()
            if order and order["storefront_id"] in storefront_ids:
                count += 1
        return count

    def _top_products(self, conn, scope, args, start, end) -> list[dict]:
        sold, sold_args = _in("o.status", SOLD_STATUSES)
        return [
            dict(r) for r in conn.execute(
                f"""SELECT oi.product_id, MAX(oi.product_name) AS name,
                           SUM(oi.quantity) AS units,
                           SUM(oi.quantity * oi.unit_price_cents) AS sales_cents
                    FROM order_items oi JOIN orders o ON o.id = oi.order_id
                    WHERE {sold} AND o.paid_at >= ? AND o.paid_at < ? AND {scope}
                    GROUP BY oi.product_id
                    ORDER BY sales_cents DESC, units DESC LIMIT ?""",
                (*sold_args, start, end, *args, TOP_N),
            )
        ]

    def _money(self, conn, scope, args, start, end) -> dict:
        sold, sold_args = _in("o.status", SOLD_STATUSES)
        row = conn.execute(
            f"""SELECT COALESCE(SUM(o.subtotal_cents), 0) AS products,
                       COALESCE(SUM(o.shipping_cents), 0) AS shipping,
                       COALESCE(SUM(o.tax_cents), 0) AS tax
                FROM orders o
                WHERE {sold} AND o.paid_at >= ? AND o.paid_at < ? AND {scope}""",
            (*sold_args, start, end, *args),
        ).fetchone()
        refunded = conn.execute(
            f"""SELECT COUNT(*) AS n, COALESCE(SUM(o.total_cents), 0) AS cents FROM orders o
                WHERE o.status = 'refunded' AND o.paid_at >= ? AND o.paid_at < ? AND {scope}""",
            (start, end, *args),
        ).fetchone()
        return {
            "products_cents": row["products"],
            "shipping_cents": row["shipping"],
            "tax_cents": row["tax"],
            "refunded_cents": refunded["cents"],
            "refunded_orders": refunded["n"],
        }

    def _repeat_buyers(self, conn, scope, args, start, end) -> dict:
        sold, sold_args = _in("o.status", SOLD_STATUSES)
        buyers = [
            dict(r) for r in conn.execute(
                f"""SELECT o.user_id, MAX(o.username) AS username,
                           COUNT(*) AS orders, SUM(o.total_cents) AS spent_cents
                    FROM orders o
                    WHERE {sold} AND o.paid_at >= ? AND o.paid_at < ? AND {scope}
                    GROUP BY o.user_id
                    ORDER BY spent_cents DESC, orders DESC""",
                (*sold_args, start, end, *args),
            )
        ]
        return {
            "buyers": len(buyers),
            "repeat": sum(1 for b in buyers if b["orders"] > 1),
            "best": buyers[:TOP_N],
        }

    def _ship_time(self, conn, scope, args, start, end) -> dict:
        hours = sorted(
            r["h"] for r in conn.execute(
                f"""SELECT (julianday(o.shipped_at) - julianday(o.paid_at)) * 24 AS h
                    FROM orders o
                    WHERE o.shipped_at >= ? AND o.shipped_at < ?
                      AND o.paid_at IS NOT NULL AND {scope}""",
                (start, end, *args),
            ) if r["h"] is not None and r["h"] >= 0
        )
        if not hours:
            return {"shipped": 0, "average_hours": None, "median_hours": None,
                    "within_2_days": 0}
        mid = len(hours) // 2
        median = hours[mid] if len(hours) % 2 else (hours[mid - 1] + hours[mid]) / 2
        return {
            "shipped": len(hours),
            "average_hours": round(sum(hours) / len(hours), 1),
            "median_hours": round(median, 1),
            "within_2_days": sum(1 for h in hours if h <= 48),
        }

    def _limit_hits(self, conn, storefront_ids, start, end) -> list[dict]:
        """Products with a monthly cap, and how often a buyer reached it.

        A hit is one buyer reaching the product's current cap in one
        calendar month, counted for months with orders in the range.
        """
        p_scope, p_args = self._scope(storefront_ids, "p")
        rows = conn.execute(
            f"""SELECT p.id, p.name, p.max_per_user_monthly AS cap,
                       o.user_id, substr(o.created_at, 1, 7) AS month,
                       SUM(oi.quantity) AS qty
                FROM products p
                JOIN order_items oi ON oi.product_id = p.id
                JOIN orders o ON o.id = oi.order_id
                WHERE p.max_per_user_monthly IS NOT NULL AND {p_scope}
                  AND o.status NOT IN ('cancelled', 'refunded')
                  AND o.created_at >= ? AND o.created_at < ?
                GROUP BY p.id, o.user_id, month""",
            (*p_args, start, end),
        ).fetchall()
        caps = {
            r["id"]: {"product_id": r["id"], "name": r["name"],
                      "cap": r["max_per_user_monthly"], "buyers": 0, "hits": 0}
            for r in conn.execute(
                f"""SELECT p.id, p.name, p.max_per_user_monthly FROM products p
                    WHERE p.max_per_user_monthly IS NOT NULL AND p.is_active = 1
                      AND {p_scope}""", p_args,
            )
        }
        buyers: dict[int, set] = {}
        for r in rows:
            entry = caps.setdefault(r["id"], {"product_id": r["id"], "name": r["name"],
                                              "cap": r["cap"], "buyers": 0, "hits": 0})
            buyers.setdefault(r["id"], set()).add(r["user_id"])
            if r["qty"] >= r["cap"]:
                entry["hits"] += 1
        for pid, users in buyers.items():
            caps[pid]["buyers"] = len(users)
        return sorted(caps.values(), key=lambda c: (-c["hits"], c["name"]))

    # ------------------------------------------------------------------
    # Monthly sales CSV
    # ------------------------------------------------------------------

    def monthly_rows(self, storefront_ids: list[int] | None) -> list[dict]:
        """One row per storefront per month, newest first."""
        scope, args = self._scope(storefront_ids)
        sold, sold_args = _in("o.status", SOLD_STATUSES)
        with self.repo._connect() as conn:
            rows = conn.execute(
                f"""SELECT substr(o.paid_at, 1, 7) AS month, s.name AS storefront,
                           SUM(CASE WHEN {sold} THEN 1 ELSE 0 END) AS orders,
                           SUM(CASE WHEN {sold} THEN (SELECT SUM(quantity) FROM order_items
                                                     WHERE order_id = o.id) ELSE 0 END) AS units,
                           SUM(CASE WHEN {sold} THEN o.subtotal_cents ELSE 0 END) AS products,
                           SUM(CASE WHEN {sold} THEN o.shipping_cents ELSE 0 END) AS shipping,
                           SUM(CASE WHEN {sold} THEN o.tax_cents ELSE 0 END) AS tax,
                           SUM(CASE WHEN {sold} THEN o.total_cents ELSE 0 END) AS sales,
                           SUM(CASE WHEN o.status = 'refunded' THEN 1 ELSE 0 END) AS refunds,
                           SUM(CASE WHEN o.status = 'refunded' THEN o.total_cents ELSE 0 END)
                               AS refunded
                    FROM orders o LEFT JOIN storefronts s ON s.id = o.storefront_id
                    WHERE o.paid_at IS NOT NULL AND {scope}
                    GROUP BY month, o.storefront_id
                    ORDER BY month DESC, s.sort_order, s.name""",
                (*sold_args, *sold_args, *sold_args, *sold_args, *sold_args, *sold_args,
                 *args),
            ).fetchall()
        return [dict(r) for r in rows]
