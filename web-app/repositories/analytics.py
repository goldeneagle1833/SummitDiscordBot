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
        limit = " LIMIT 30" if hours else ""
        cur.execute(
            f"SELECT date(timestamp) as day, COUNT(*) as cnt FROM page_views {where} GROUP BY day ORDER BY day DESC{limit}",
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

    # --- Active Sessions ---

    def _ensure_active_sessions_table(self):
        """Create active_sessions table if it doesn't exist, with all columns."""
        conn = self._connect()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS active_sessions (
                session_id TEXT PRIMARY KEY,
                first_seen TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
                last_seen TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
                ip TEXT,
                user_agent TEXT,
                path TEXT,
                timezone TEXT
            )
        """)
        # Add columns if upgrading from old schema
        cur = conn.execute("PRAGMA table_info(active_sessions)")
        columns = {row[1] for row in cur.fetchall()}
        for col, col_type in [("first_seen", "TEXT"), ("ip", "TEXT"),
                              ("user_agent", "TEXT"), ("path", "TEXT"),
                              ("timezone", "TEXT")]:
            if col not in columns:
                conn.execute(f"ALTER TABLE active_sessions ADD COLUMN {col} {col_type}")
        conn.commit()
        conn.close()

    def record_heartbeat(self, session_id: str, ip: str | None = None,
                         user_agent: str | None = None, path: str | None = None,
                         timezone: str | None = None):
        """Record or update a session heartbeat with metadata."""
        try:
            self._ensure_active_sessions_table()
            conn = self._connect()
            conn.execute(
                """INSERT INTO active_sessions (session_id, first_seen, last_seen, ip, user_agent, path, timezone)
                   VALUES (?, strftime('%Y-%m-%d %H:%M:%S', 'now'), strftime('%Y-%m-%d %H:%M:%S', 'now'), ?, ?, ?, ?)
                   ON CONFLICT(session_id)
                   DO UPDATE SET last_seen = strftime('%Y-%m-%d %H:%M:%S', 'now'),
                                ip = COALESCE(excluded.ip, active_sessions.ip),
                                user_agent = COALESCE(excluded.user_agent, active_sessions.user_agent),
                                path = COALESCE(excluded.path, active_sessions.path),
                                timezone = COALESCE(excluded.timezone, active_sessions.timezone)""",
                (session_id, ip, user_agent, path, timezone),
            )
            # Clean up stale sessions older than 2 minutes
            conn.execute(
                "DELETE FROM active_sessions WHERE last_seen < strftime('%Y-%m-%d %H:%M:%S', 'now', '-120 seconds')"
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"Failed to record heartbeat: {e}")

    def get_active_user_count(self) -> int:
        """Get the number of active users (heartbeat within last 60 seconds)."""
        try:
            self._ensure_active_sessions_table()
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM active_sessions WHERE last_seen >= strftime('%Y-%m-%d %H:%M:%S', 'now', '-60 seconds')"
            )
            count = cur.fetchone()[0]
            conn.close()
            return count
        except Exception:
            return 0

    def get_active_sessions(self) -> list[dict]:
        """Get all active sessions with full metadata."""
        try:
            self._ensure_active_sessions_table()
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(
                """SELECT session_id, first_seen, last_seen, ip, user_agent, path, timezone
                   FROM active_sessions
                   WHERE last_seen >= strftime('%Y-%m-%d %H:%M:%S', 'now', '-120 seconds')
                   ORDER BY last_seen DESC"""
            )
            sessions = []
            for r in cur.fetchall():
                sessions.append({
                    "session_id": r[0][:8] + "...",
                    "first_seen": r[1],
                    "last_seen": r[2],
                    "ip": r[3],
                    "user_agent": r[4],
                    "path": r[5],
                    "timezone": r[6],
                })
            conn.close()
            return sessions
        except Exception:
            return []

    # --- Unique Visitors (IP-based) ---

    _unique_visitors_ready = False

    def _ensure_unique_visitors_table(self):
        """Create unique_visitors table if it doesn't exist."""
        if AnalyticsRepository._unique_visitors_ready:
            return
        conn = self._connect()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS unique_visitors (
                ip TEXT PRIMARY KEY,
                first_seen TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
                last_seen TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
                visit_count INTEGER NOT NULL DEFAULT 1,
                user_agent TEXT,
                timezone TEXT
            )
        """)
        conn.commit()
        conn.close()
        AnalyticsRepository._unique_visitors_ready = True

    def record_unique_visitor(self, ip: str, user_agent: str | None = None,
                              timezone: str | None = None):
        """Record a visitor IP. Increments visit_count for returning visitors."""
        if not ip:
            return
        try:
            self._ensure_unique_visitors_table()
            conn = self._connect()
            conn.execute(
                """INSERT INTO unique_visitors (ip, user_agent, timezone)
                   VALUES (?, ?, ?)
                   ON CONFLICT(ip)
                   DO UPDATE SET last_seen = strftime('%Y-%m-%d %H:%M:%S', 'now'),
                                visit_count = visit_count + 1,
                                user_agent = COALESCE(excluded.user_agent, unique_visitors.user_agent),
                                timezone = COALESCE(excluded.timezone, unique_visitors.timezone)""",
                (ip, user_agent, timezone),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"Failed to record unique visitor: {e}")

    def get_unique_visitor_stats(self) -> dict:
        """Get unique visitor statistics."""
        try:
            self._ensure_unique_visitors_table()
            conn = self._connect()
            cur = conn.cursor()

            cur.execute("SELECT COUNT(*) FROM unique_visitors")
            total = cur.fetchone()[0]

            cur.execute(
                "SELECT COUNT(*) FROM unique_visitors WHERE date(first_seen) = date('now')"
            )
            today = cur.fetchone()[0]

            cur.execute(
                "SELECT COUNT(*) FROM unique_visitors WHERE first_seen >= date('now', '-7 days')"
            )
            this_week = cur.fetchone()[0]

            cur.execute(
                "SELECT COUNT(*) FROM unique_visitors WHERE first_seen >= date('now', '-30 days')"
            )
            this_month = cur.fetchone()[0]

            cur.execute(
                """SELECT date(first_seen) as day, COUNT(*) as cnt
                   FROM unique_visitors
                   WHERE first_seen >= date('now', '-30 days')
                   GROUP BY day ORDER BY day"""
            )
            daily_new = [{"date": r[0], "count": r[1]} for r in cur.fetchall()]

            cur.execute(
                """SELECT strftime('%Y-%W', first_seen) as week, COUNT(*) as cnt
                   FROM unique_visitors
                   GROUP BY week ORDER BY week"""
            )
            weekly_new = [{"week": r[0], "count": r[1]} for r in cur.fetchall()]

            cur.execute("SELECT COUNT(*) FROM unique_visitors WHERE visit_count > 1")
            returning = cur.fetchone()[0]

            cur.execute(
                """SELECT ip, first_seen, last_seen, visit_count, user_agent, timezone
                   FROM unique_visitors ORDER BY visit_count DESC LIMIT 20"""
            )
            top_visitors = [{
                "ip": r[0], "first_seen": r[1], "last_seen": r[2],
                "visit_count": r[3], "user_agent": r[4], "timezone": r[5],
            } for r in cur.fetchall()]

            conn.close()
            return {
                "total": total, "today": today, "this_week": this_week,
                "this_month": this_month, "returning": returning,
                "daily_new": daily_new, "weekly_new": weekly_new,
                "top_visitors": top_visitors,
            }
        except Exception as e:
            logger.debug(f"Failed to get unique visitor stats: {e}")
            return {"total": 0, "today": 0, "this_week": 0, "this_month": 0,
                    "returning": 0, "daily_new": [], "weekly_new": [], "top_visitors": []}

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
