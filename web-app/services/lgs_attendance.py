"""Local game store attendance for Explorer applications.

Applicants tell us roughly how many players their store draws. This looks the
store up on sorcerytcg.com and works out what actually happened, so the
Council can compare the two while scoring.

The scraping itself already exists as ExplorerService.fetch_venue_attendance —
this adds the window, the median and the storage.
"""

import json
import logging
import sqlite3
import statistics
import threading
from datetime import date, datetime, timedelta

import webapp_config

logger = logging.getLogger(__name__)

# How far back to look. Long enough to smooth out a quiet month, short enough
# that a store's ancient history doesn't flatter it.
WINDOW_MONTHS = 9
WINDOW_DAYS = WINDOW_MONTHS * 30


def _parse_date(value) -> date | None:
    if not value:
        return None
    text = str(value)[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def recent_events(events: list[dict], today: date | None = None) -> list[dict]:
    """Events inside the window that actually recorded a player count."""
    cutoff = (today or date.today()) - timedelta(days=WINDOW_DAYS)
    kept = []
    for event in events or []:
        event_date = _parse_date(event.get("date"))
        count = event.get("player_count")
        if event_date and event_date >= cutoff and isinstance(count, int) and count > 0:
            kept.append({"date": event_date.isoformat(), "player_count": count})
    kept.sort(key=lambda e: e["date"])
    return kept


def summarise(attendance: dict, today: date | None = None) -> dict:
    """Turn a venue-attendance payload into what we store on the application."""
    history = recent_events(attendance.get("events"), today=today)
    counts = [e["player_count"] for e in history]
    return {
        "lgs_store_name": attendance.get("store_name") or None,
        "lgs_median_players": int(statistics.median(counts)) if counts else None,
        "lgs_event_count": len(counts),
        "lgs_history": json.dumps(history),
        "lgs_lookup_error": None if counts else "No events with attendance in the last 9 months",
    }


def _save(application_id: int, summary: dict) -> None:
    conn = sqlite3.connect(str(webapp_config.EXPLORER_DB_PATH))
    try:
        conn.execute(
            """UPDATE explorer_applications
               SET lgs_store_name = ?, lgs_median_players = ?, lgs_event_count = ?,
                   lgs_history = ?, lgs_lookup_error = ?,
                   lgs_checked_at = datetime('now')
               WHERE id = ?""",
            (
                summary.get("lgs_store_name"),
                summary.get("lgs_median_players"),
                summary.get("lgs_event_count"),
                summary.get("lgs_history"),
                summary.get("lgs_lookup_error"),
                application_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def lookup_attendance(application_id: int, lgs_url: str | None) -> dict | None:
    """Fetch and store the store's recent attendance. Never raises.

    Returns the stored summary, or None when there is nothing to look up.
    """
    url = (lgs_url or "").strip()
    if not url or not url.lower().startswith("http"):
        # Applicants are told to type "not registered" when the store has no page.
        return None

    from services.explorer import ExplorerService

    try:
        attendance = ExplorerService().fetch_venue_attendance(url)
    except ValueError as exc:
        summary = {
            "lgs_store_name": None, "lgs_median_players": None, "lgs_event_count": 0,
            "lgs_history": json.dumps([]), "lgs_lookup_error": str(exc),
        }
        _save(application_id, summary)
        return summary
    except Exception as exc:
        logger.warning("LGS attendance lookup failed for application %s: %s",
                       application_id, exc)
        summary = {
            "lgs_store_name": None, "lgs_median_players": None, "lgs_event_count": 0,
            "lgs_history": json.dumps([]),
            "lgs_lookup_error": "Could not reach sorcerytcg.com",
        }
        _save(application_id, summary)
        return summary

    summary = summarise(attendance)
    _save(application_id, summary)
    return summary


def lookup_attendance_in_background(application_id: int, lgs_url: str | None) -> None:
    """Run the lookup off the request path.

    It is several calls to sorcerytcg.com, and the app runs on a small number
    of sync workers — an applicant should never wait on it.
    """
    def run():
        try:
            lookup_attendance(application_id, lgs_url)
        except Exception:
            logger.exception("Background LGS lookup failed for %s", application_id)

    threading.Thread(target=run, daemon=True).start()
