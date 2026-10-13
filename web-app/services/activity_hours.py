"""Peak activity hours for the admin dashboard, in Eastern time.

Match timestamps are naive ``datetime.now()`` values written on the server
(the bot and the web app share the same host and database), so they are read
as the server's local time and converted to America/New_York, daylight
saving included.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")


def eastern_slot(slot: str) -> tuple[str, int, int]:
    """("YYYY-MM-DD", day of week 0=Sun, hour) in Eastern for a server-local "YYYY-MM-DD HH" slot."""
    local = datetime.strptime(slot, "%Y-%m-%d %H").astimezone()
    eastern = local.astimezone(EASTERN)
    return eastern.date().isoformat(), (eastern.weekday() + 1) % 7, eastern.hour


def activity_by_hour(slot_counts) -> tuple[list[list], list[list[int]]]:
    """Eastern [date, hour, count] rows (oldest first) plus the all-time 7x24 grid.

    ``slot_counts`` is an iterable of ("YYYY-MM-DD HH" server-local slot, count).
    """
    totals = {}
    for slot, count in slot_counts:
        if not slot:
            continue
        try:
            day, _, hour = eastern_slot(slot)
        except ValueError:
            continue
        totals[(day, hour)] = totals.get((day, hour), 0) + int(count)

    grid = [[0] * 24 for _ in range(7)]
    rows = []
    for (day, hour), count in sorted(totals.items()):
        rows.append([day, hour, count])
        dow = (datetime.fromisoformat(day).weekday() + 1) % 7
        grid[dow][hour] += count
    return rows, grid
