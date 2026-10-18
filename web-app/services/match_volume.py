"""Games by type in recent windows vs the window before, for the admin dashboard.

Two comparisons: the last 24 hours vs the 24 hours before that, and the last
7 days vs the 7 days before that. Timestamps are naive server-local time, so
the windows are measured from the server's datetime.now().
"""
from datetime import datetime, timedelta

# (key, label) in display order.
GAME_TYPES = [
    ("ranked", "Ranked"),
    ("casual", "Casual"),
    ("limited", "Limited"),
    ("rumble", "Rumble"),
    ("omens", "Omens"),
    ("postseason", "Postseason"),
    ("paper", "Paper"),
]

# match_records.match_type -> game type; anything else (NULL, 'ranked') is ranked.
_MATCH_TYPE_KEYS = {"testing": "casual", "points": "omens", "limited": "limited", "rumble": "rumble"}

_FMT = "%Y-%m-%d %H:%M:%S"


def _windows(now):
    day, week = timedelta(days=1), timedelta(days=7)
    return {
        "day": ((now - day, now), (now - 2 * day, now - day)),
        "week": ((now - week, now), (now - 2 * week, now - week)),
    }


def _type_expr(columns):
    """SQL giving each match_records row its game type key."""
    whens = " ".join(f"WHEN '{mt}' THEN '{key}'" for mt, key in _MATCH_TYPE_KEYS.items())
    expr = f"CASE match_type {whens} ELSE 'ranked' END" if "match_type" in columns else "'ranked'"
    if "source" in columns:
        expr = f"CASE WHEN source = 'Bracket' THEN 'postseason' ELSE {expr} END"
    return expr


def match_volume(cur, existing_tables, now=None) -> dict:
    """{"types": [...], "windows": {"day"|"week": {"current", "previous", "start", "end"}}}.

    "current" and "previous" map each game type key to its game count.
    """
    now = now or datetime.now()
    windows = _windows(now)
    oldest = windows["week"][1][0].strftime(_FMT)

    sources = []
    for table in ("match_records", "match_records_archive"):
        if table in existing_tables:
            columns = {row[1] for row in cur.execute(f"PRAGMA table_info({table})")}
            sources.append((table, _type_expr(columns)))
    for table, key in (
        ("limited_match_records", "limited"),
        ("limited_match_records_archive", "limited"),
        ("rumble_match_records", "rumble"),
        ("match_reports_web", "paper"),
    ):
        if table in existing_tables:
            sources.append((table, f"'{key}'"))

    result = {
        name: {"current": {k: 0 for k, _ in GAME_TYPES}, "previous": {k: 0 for k, _ in GAME_TYPES}}
        for name in windows
    }
    for table, type_expr in sources:
        # datetime() normalizes ISO 'T' and space-separated timestamps alike.
        cur.execute(f"""
            SELECT {type_expr} AS game_type, datetime(timestamp) AS ts FROM {table}
            WHERE timestamp IS NOT NULL AND datetime(timestamp) >= ?
        """, (oldest,))
        for game_type, ts in cur.fetchall():
            if ts is None or game_type not in result["day"]["current"]:
                continue
            when = datetime.strptime(ts, _FMT)
            for name, periods in windows.items():
                for label, (start, end) in zip(("current", "previous"), periods):
                    if start <= when < end:
                        result[name][label][game_type] += 1

    for name, ((start, end), _) in windows.items():
        result[name]["start"] = start.strftime(_FMT)
        result[name]["end"] = end.strftime(_FMT)
    return {"types": [{"key": k, "label": label} for k, label in GAME_TYPES], "windows": result}
