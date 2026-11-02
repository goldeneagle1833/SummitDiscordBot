"""Batch data release for public stats pages (Avatars, Popular Cards).

These pages follow the Meta Report schedule: data comes out in half-month
batches on the Meta Report publish days (00:01 UTC on the 1st and 15th), so a
page shows games only up to the end of the newest released period, never live.

``released_connection`` opens match_records.db with temporary views named after
the match tables. SQLite looks up TEMP objects before ``main``, so every
existing query on that connection only sees games from released periods,
without touching each query.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime, time, timedelta, timezone

from services.meta_report import Period, latest_due_period, report_today

# table -> timestamp column. Each is cut off only if it exists in the database.
RELEASED_TABLES = {
    "match_records": "timestamp",
    "match_records_archive": "timestamp",
    "external_matches": "timestamp",
    "solo_match_reports": "report_date",
}

_CUTOFF_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


def latest_released_period(now: datetime | None = None) -> Period:
    return latest_due_period(report_today(now))


def released_through(now: datetime | None = None) -> date:
    """Last UTC day whose games are public."""
    return latest_released_period(now).end


def next_release(now: datetime | None = None) -> date:
    """Publish day of the next batch."""
    period = latest_released_period(now)
    nxt = Period(period.year, period.month, "b") if period.half == "a" else (
        Period(period.year + 1, 1, "a") if period.month == 12 else Period(period.year, period.month + 1, "a"))
    return nxt.publish_day


def cutoff_timestamp(now: datetime | None = None) -> str:
    """First timestamp that is NOT released yet, in the stored format.

    Match timestamps are naive server-local ISO strings
    (``datetime.now().isoformat()``), so UTC midnight after the released period
    is converted to server-local time before comparing.
    """
    first_hidden = datetime.combine(released_through(now) + timedelta(days=1), time(0), tzinfo=timezone.utc)
    return first_hidden.astimezone().replace(tzinfo=None).isoformat(timespec="seconds")


def release_info(now: datetime | None = None) -> dict:
    period = latest_released_period(now)
    return {
        "through": period.end.isoformat(),
        "period": period.slug,
        "next_release": next_release(now).isoformat(),
    }


class ReleasedConnection(sqlite3.Connection):
    """sqlite3 connection whose match tables stop at the release cutoff."""

    release_cutoff: str | None = None


def released_connection(path, now: datetime | None = None) -> ReleasedConnection:
    conn = sqlite3.connect(str(path), factory=ReleasedConnection)
    cutoff = cutoff_timestamp(now)
    if not _CUTOFF_RE.match(cutoff):  # it goes into SQL as a literal
        raise ValueError(f"Bad release cutoff: {cutoff!r}")
    existing = {r[0] for r in conn.execute("SELECT name FROM main.sqlite_master WHERE type = 'table'")}
    for table, column in RELEASED_TABLES.items():
        if table in existing:
            # rowid is carried through because some queries use it as a match id.
            conn.execute(
                f"CREATE TEMP VIEW {table} AS SELECT rowid AS rowid, * FROM main.{table}"
                f" WHERE {column} < '{cutoff}'"
            )
    conn.release_cutoff = cutoff
    return conn
