"""Repository for site analytics data access."""

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
