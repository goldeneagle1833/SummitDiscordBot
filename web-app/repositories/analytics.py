"""Repository for site analytics data access."""

import json
import sqlite3
import logging
from datetime import datetime, timedelta

from webapp_config import ANALYTICS_DB_PATH

logger = logging.getLogger(__name__)


class AnalyticsRepository:
    """Data access for page views and banner clicks."""

    def _connect(self):
        return sqlite3.connect(str(ANALYTICS_DB_PATH))

    def log_page_view(self, path: str, user_agent: str | None, referrer: str | None):
        """Record a page view."""
        try:
            conn = self._connect()
            conn.execute(
                "INSERT INTO page_views (path, user_agent, referrer) VALUES (?, ?, ?)",
                (path, user_agent, referrer),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"Failed to log page view: {e}")

    def log_banner_click(self, banner_type: str):
        """Record a banner click."""
        try:
            conn = self._connect()
            conn.execute(
                "INSERT INTO banner_clicks (banner_type) VALUES (?)",
                (banner_type,),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"Failed to log banner click: {e}")

    def get_page_view_stats(self, hours: int | None = None) -> dict:
        """Get page view statistics, optionally filtered by time range.

        Returns dict with total count, top pages, and daily breakdown.
        """
        conn = self._connect()
        cur = conn.cursor()

        where = ""
        params = ()
        if hours:
            cutoff = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
            where = "WHERE timestamp >= ?"
            params = (cutoff,)

        # Total views
        cur.execute(f"SELECT COUNT(*) FROM page_views {where}", params)
        total = cur.fetchone()[0]

        # Top pages
        cur.execute(
            f"SELECT path, COUNT(*) as cnt FROM page_views {where} GROUP BY path ORDER BY cnt DESC LIMIT 15",
            params,
        )
        top_pages = [{"path": r[0], "count": r[1]} for r in cur.fetchall()]

        # Daily breakdown
        cur.execute(
            f"SELECT date(timestamp) as day, COUNT(*) as cnt FROM page_views {where} GROUP BY day ORDER BY day DESC LIMIT 30",
            params,
        )
        daily = [{"date": r[0], "count": r[1]} for r in cur.fetchall()]

        conn.close()
        return {"total": total, "top_pages": top_pages, "daily": daily}

    def get_banner_click_stats(self) -> dict:
        """Get banner click counts grouped by type."""
        conn = self._connect()
        cur = conn.cursor()

        cur.execute(
            "SELECT banner_type, COUNT(*) as cnt FROM banner_clicks GROUP BY banner_type ORDER BY cnt DESC"
        )
        by_type = [{"banner_type": r[0], "count": r[1]} for r in cur.fetchall()]

        cur.execute("SELECT COUNT(*) FROM banner_clicks")
        total = cur.fetchone()[0]

        conn.close()
        return {"total": total, "by_type": by_type}

    # --- Promo Banners ---

    def _ensure_promo_table(self):
        """Create promo_banners table if it doesn't exist, and add images column if missing."""
        conn = self._connect()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS promo_banners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                subtitle TEXT,
                link TEXT NOT NULL,
                badge_text TEXT NOT NULL DEFAULT 'NEW',
                color TEXT NOT NULL DEFAULT 'blue',
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
                expires_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_by TEXT,
                images TEXT
            )
        """)
        # Add images column if table existed before this migration
        cur = conn.execute("PRAGMA table_info(promo_banners)")
        columns = {row[1] for row in cur.fetchall()}
        if "images" not in columns:
            conn.execute("ALTER TABLE promo_banners ADD COLUMN images TEXT")
        conn.commit()
        conn.close()

    def create_banner(self, title: str, link: str, expires_at: str,
                      subtitle: str | None = None, badge_text: str = "NEW",
                      color: str = "blue", created_by: str | None = None,
                      images: str | None = None) -> int:
        """Create a new promo banner. Returns the banner ID.

        images: JSON array string of image URLs, e.g. '["url1","url2"]'
        """
        self._ensure_promo_table()
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO promo_banners (title, subtitle, link, badge_text, color, expires_at, created_by, images)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (title, subtitle, link, badge_text, color, expires_at, created_by, images),
        )
        conn.commit()
        banner_id = cur.lastrowid
        conn.close()
        return banner_id

    def get_active_banners(self) -> list[dict]:
        """Get all active, non-expired banners."""
        self._ensure_promo_table()
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """SELECT id, title, subtitle, link, badge_text, color, created_at, expires_at, images
               FROM promo_banners
               WHERE active = 1 AND expires_at > strftime('%Y-%m-%d %H:%M:%S', 'now')
               ORDER BY created_at DESC""",
        )
        banners = []
        for r in cur.fetchall():
            images = json.loads(r[8]) if r[8] else []
            banners.append({
                "id": r[0], "title": r[1], "subtitle": r[2], "link": r[3],
                "badge_text": r[4], "color": r[5], "created_at": r[6], "expires_at": r[7],
                "images": images,
            })
        conn.close()
        return banners

    def get_all_banners(self) -> list[dict]:
        """Get all banners (for admin view)."""
        self._ensure_promo_table()
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """SELECT id, title, subtitle, link, badge_text, color, created_at, expires_at, active, created_by, images
               FROM promo_banners ORDER BY created_at DESC""",
        )
        banners = []
        for r in cur.fetchall():
            images = json.loads(r[10]) if r[10] else []
            banners.append({
                "id": r[0], "title": r[1], "subtitle": r[2], "link": r[3],
                "badge_text": r[4], "color": r[5], "created_at": r[6], "expires_at": r[7],
                "active": bool(r[8]), "created_by": r[9], "images": images,
            })
        conn.close()
        return banners

    def delete_banner(self, banner_id: int) -> bool:
        """Delete a banner by ID. Returns True if found and deleted."""
        self._ensure_promo_table()
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM promo_banners WHERE id = ?", (banner_id,))
        conn.commit()
        deleted = cur.rowcount > 0
        conn.close()
        return deleted

    def toggle_banner(self, banner_id: int) -> bool | None:
        """Toggle a banner's active state. Returns new state or None if not found."""
        self._ensure_promo_table()
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT active FROM promo_banners WHERE id = ?", (banner_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return None
        new_state = 0 if row[0] else 1
        cur.execute("UPDATE promo_banners SET active = ? WHERE id = ?", (new_state, banner_id))
        conn.commit()
        conn.close()
        return bool(new_state)
