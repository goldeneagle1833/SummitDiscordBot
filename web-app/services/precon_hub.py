"""Precon ladder summary for the /standings hub (reads our own database only)."""

import logging
import sqlite3

import webapp_config
from services import precon_ladder

logger = logging.getLogger(__name__)

HUB_LINK = "/?ladder=precon#leaderboard"


def hub_summary(db_path=None, limit=10):
    """{"system": {...}, "players": [...]} for the hub card, or None before any precon ladder."""
    try:
        conn = sqlite3.connect(str(db_path or webapp_config.MATCH_RECORDS_DB_PATH), timeout=10)
        try:
            season = precon_ladder.current_or_latest_season(conn)
            if not season:
                return None
            rows = precon_ladder.standings(conn, season["season_id"])
            stats = precon_ladder.season_stats(conn, season["season_id"])
        finally:
            conn.close()
    except sqlite3.Error:
        logger.error("Could not read the precon ladder for the standings hub", exc_info=True)
        return None
    matchup = stats["lm_vs_fm"]
    status = "live" if season["is_open"] else ("finished" if season.get("ended_at") or rows else "coming_soon")
    return {
        "system": {
            "title": season["name"],
            "status": status,
            "blurb": "Lavamancer vs Frostmage precon ladder, rated with Glicko-2. Four weeks per ladder.",
            "link": HUB_LINK,
            "ends_at": season["last_day"],
            "facts": [
                {"label": "Players", "value": stats["players"]},
                {"label": "Games", "value": stats["games"]},
                {"label": "LM vs FM", "value": f"{matchup['lm_wins']}-{matchup['fm_wins']}"},
            ],
        },
        "players": [
            {
                "user_id": row["user_id"],
                "display_name": row["name"],
                "rating": row["rating"],
                "rank": row["rank"],
                "games": row["games"],
                "provisional": not row["ranked"],
            }
            for row in rows[:limit]
        ],
    }
