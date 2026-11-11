"""Rules for the in-person "find a player" page.

A person's spot is only shown while their event is on: between the event's
start and end dates, and only during its daily hours (8 a.m. to 8 p.m. by
default) in the venue's own time zone. Outside that, or when they switch
sharing off, viewers see that they aren't sharing, never an old pin.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

MAX_SPOTS = 30
MAX_LABEL = 60
MAX_NOTE = 140


def _zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "America/New_York")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("America/New_York")


def _hm(value: str, default: str) -> time:
    m = _TIME_RE.match(value or "") or _TIME_RE.match(default)
    return time(int(m.group(1)), int(m.group(2)))


def window_status(event_map: dict | None, now: datetime | None = None) -> dict:
    """Whether sharing is shown right now on this map.

    Returns ``{"open": bool, "reason": str, "local_time": "HH:MM"}`` where
    reason is one of open, no_map, before, after, closed_today.
    """
    if not event_map:
        return {"open": False, "reason": "no_map", "local_time": None}
    tz = _zone(event_map.get("timezone"))
    now = (now or datetime.now(timezone.utc)).astimezone(tz)
    local = now.strftime("%H:%M")
    try:
        start = date.fromisoformat(event_map["start_date"])
        end = date.fromisoformat(event_map["end_date"])
    except (KeyError, TypeError, ValueError):
        return {"open": False, "reason": "no_map", "local_time": local}
    today = now.date()
    if today < start:
        return {"open": False, "reason": "before", "local_time": local}
    if today > end:
        return {"open": False, "reason": "after", "local_time": local}
    opens = _hm(event_map.get("daily_start"), "08:00")
    closes = _hm(event_map.get("daily_end"), "20:00")
    if not (opens <= now.time() < closes):
        if today == end and now.time() >= closes:
            return {"open": False, "reason": "after", "local_time": local}
        return {"open": False, "reason": "closed_today", "local_time": local}
    return {"open": True, "reason": "open", "local_time": local}


def _pct(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError("Map position must be a number")
    if not 0 <= v <= 100:
        raise ValueError("Map position must be on the map")
    return round(v, 2)


def clean_spots(raw) -> list[dict]:
    """Admin quick spots: [{label, x, y}] with x/y optional (label only)."""
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        raise ValueError("Spots must be a list")
    out = []
    for item in raw[:MAX_SPOTS]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()[:MAX_LABEL]
        if not label:
            continue
        out.append({"label": label, "x": _pct(item.get("x")), "y": _pct(item.get("y"))})
    return out


def clean_map_fields(data: dict, partial: bool = False) -> dict:
    """Validate the admin's map form. Raises ValueError with a plain message."""
    out = {}
    if "name" in data or not partial:
        name = str(data.get("name") or "").strip()[:100]
        if not name:
            raise ValueError("Give the event a name")
        out["name"] = name
    for key in ("start_date", "end_date"):
        if key in data or not partial:
            value = str(data.get(key) or "").strip()
            if not _DATE_RE.match(value):
                raise ValueError("Dates must look like 2026-11-13")
            date.fromisoformat(value)
            out[key] = value
    if out.get("start_date") and out.get("end_date") and out["end_date"] < out["start_date"]:
        raise ValueError("The last day can't be before the first day")
    for key, default in (("daily_start", "08:00"), ("daily_end", "20:00")):
        if key in data:
            value = str(data.get(key) or default).strip()
            if not _TIME_RE.match(value):
                raise ValueError("Times must look like 08:00 or 20:00")
            out[key] = value
    if out.get("daily_start") and out.get("daily_end") and out["daily_end"] <= out["daily_start"]:
        raise ValueError("Sharing has to end after it starts each day")
    if "timezone" in data:
        tz = str(data.get("timezone") or "").strip()
        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Unknown time zone")
        out["timezone"] = tz
    if "image_url" in data:
        url = str(data.get("image_url") or "").strip()
        if url and not url.startswith("/static/uploads/event-maps/"):
            raise ValueError("Upload the map image here first")
        out["image_url"] = url or None
    if "spots" in data:
        out["spots"] = clean_spots(data.get("spots"))
    return out


def clean_share_fields(data: dict) -> dict:
    """Validate a person's own update. Raises ValueError."""
    out = {}
    if "map_id" in data:
        out["map_id"] = int(data["map_id"]) if data["map_id"] not in (None, "") else None
    for key in ("sharing", "listed"):
        if key in data:
            out[key] = 1 if data[key] else 0
    if "x" in data or "y" in data:
        x, y = _pct(data.get("x")), _pct(data.get("y"))
        if (x is None) != (y is None):
            raise ValueError("Pick a spot on the map")
        out["x"], out["y"] = x, y
    if "label" in data:
        out["label"] = (str(data.get("label") or "").strip()[:MAX_LABEL]) or None
    if "note" in data:
        out["note"] = (str(data.get("note") or "").strip()[:MAX_NOTE]) or None
    return out


def public_person(share: dict, event_map: dict | None, now: datetime | None = None) -> dict:
    """What a viewer may see. The spot is left out unless live right now."""
    status = window_status(event_map, now)
    live = bool(share.get("sharing")) and status["open"]
    person = {
        "username": share.get("username") or "Player",
        "avatar": share.get("avatar"),
        "live": live,
        "reason": status["reason"] if share.get("sharing") else "off",
        "map": public_map(event_map) if event_map else None,
    }
    if live:
        person.update({
            "x": share.get("x"),
            "y": share.get("y"),
            "label": share.get("label"),
            "note": share.get("note"),
            "updated_at": share.get("updated_at"),
        })
    return person


def public_map(event_map: dict, now: datetime | None = None) -> dict:
    status = window_status(event_map, now)
    return {
        "id": event_map["id"],
        "name": event_map["name"],
        "image_url": event_map.get("image_url"),
        "start_date": event_map["start_date"],
        "end_date": event_map["end_date"],
        "daily_start": event_map.get("daily_start"),
        "daily_end": event_map.get("daily_end"),
        "timezone": event_map.get("timezone"),
        "spots": event_map.get("spots") or [],
        "open": status["open"],
        "reason": status["reason"],
    }
