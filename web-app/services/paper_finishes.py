"""Paper tournament finishes on Summit profiles.

Every event on the Top 8 page keeps its top cut in order of finish (the
import sorts it by standings, and admins can drag it into order). Each entry
there is matched to a Summit player by name, and a match earns that player a
badge: "Winner", "Finalist", "Top 4", "Top 8" (and Top 16 / 32 / 64 for the
longer cuts) at that event.

Whose name a result carries:
- An event imported from its sorcerytcg.com page has its pairings saved, so
  each deck has the name its pilot registered with. That name is used first.
- Otherwise it is the account that posted the deck. When one account posted
  two or more decks in the same top cut it is an organiser, not the pilot,
  so those results only count once an admin gives them to someone.

How a name becomes a Summit player, first rule that applies wins:
1. An admin gave this one result to a player (or to nobody).
2. An admin linked the name to a player.
3. The name, ignoring case, accents, spaces and punctuation, is exactly one
   Summit player's name: their Discord username, Discord display name, the
   name they chose on the site, or their leaderboard name. Names shorter
   than four letters never link on their own; neither does a name two
   players share, nor one an admin marked "not this player".
Anything else waits on the admin page, with close names offered to confirm.

Nothing is stored except the admin decisions: finishes are worked out from
the event files when read, like the season honours.
"""

import difflib
import json
import logging
import os
import re
import sqlite3
import threading
import unicodedata

import webapp_config
from repositories.events import EventRepository
from repositories.paper_links import PaperLinkRepository

logger = logging.getLogger(__name__)

MIN_AUTO_LENGTH = 4
SUGGEST_CUTOFF = 0.8

# Summit's own seasons and the TTS leagues already show as postseason
# badges; they start switched off here, and an admin can switch them on.
_ONLINE_EVENT = re.compile(r"summit|tts", re.IGNORECASE)

_cache = {}
_cache_lock = threading.Lock()


def name_key(name) -> str:
    """'Peter The-Great ' -> 'peterthegreat'. Accents dropped, letters and digits kept."""
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def bare_id(user_id) -> str:
    user_id = str(user_id or "")
    return user_id[7:] if user_id.startswith("google_") else user_id


def finish_label(place: int) -> str:
    if place == 1:
        return "Winner"
    if place == 2:
        return "Finalist"
    for cut in (4, 8, 16, 32, 64, 128):
        if place <= cut:
            return f"Top {cut}"
    return f"#{place}"


def finish_rank(place: int) -> int:
    """Places that share a label share a rank (3rd and 4th are both Top 4)."""
    if place <= 2:
        return place
    for cut in (4, 8, 16, 32, 64, 128):
        if place <= cut:
            return cut
    return place


def event_default_on(event: dict) -> bool:
    return not (_ONLINE_EVENT.search(event["folder"]) or _ONLINE_EVENT.search(event.get("name") or ""))


def _db_signature() -> tuple:
    """Changes whenever elo.db or match_records.db (or their WAL files) are written."""
    parts = []
    for path in (webapp_config.ELO_DB_PATH, webapp_config.MATCH_RECORDS_DB_PATH):
        for suffix in ("", "-wal"):
            try:
                st = os.stat(f"{path}{suffix}")
                parts.append((str(path), suffix, st.st_mtime_ns, st.st_size))
            except OSError:
                parts.append((str(path), suffix, None))
    return tuple(parts)


# -- event results --------------------------------------------------------

def _events_signature(repo: EventRepository) -> tuple:
    parts = []
    root = repo._events_dir
    try:
        for entry in os.scandir(root):
            st = entry.stat()
            parts.append((entry.name, "", st.st_mtime_ns, st.st_size))
            if entry.is_dir():
                for child in os.scandir(entry.path):
                    cst = child.stat()
                    parts.append((entry.name, child.name, cst.st_mtime_ns, cst.st_size))
    except OSError:
        pass
    return tuple(sorted(parts))


def _avatar(deck: dict) -> str:
    avatars = deck.get("avatar") or [{}]
    first = avatars[0] if isinstance(avatars, list) and avatars else {}
    return (first or {}).get("name") or ""


def _event_results(repo: EventRepository, event: dict) -> list[dict]:
    """The top cut of one event, in order of finish, with the names it carries."""
    files = repo._find_json_files(event["folder"])
    if not files or not files["top8"]:
        return []
    try:
        with open(files["top8"], "r", encoding="utf-8") as f:
            decks = json.load(f)
    except Exception as e:
        logger.warning("Could not read top cut for %s: %s", event["folder"], e)
        return []
    if not isinstance(decks, list):
        return []

    registered = {}
    history = repo._load_match_history(event["folder"]) or {}
    for player in history.get("players", []):
        if player.get("deck_id"):
            registered[player["deck_id"]] = player

    owners = {}
    for deck in decks:
        key = name_key(deck.get("username"))
        if key:
            owners[key] = owners.get(key, 0) + 1

    results = []
    for place, deck in enumerate(decks, start=1):
        if not isinstance(deck, dict):
            continue
        deck_id = deck.get("id") or ""
        owner = (deck.get("username") or "").strip()
        reg = registered.get(deck_id)
        if reg:
            names = [n for n in (reg.get("display_name"), reg.get("username")) if n and n != "Unknown"]
            source = "registration"
        else:
            names = [owner] if owner else []
            source = "deck owner"
        shared = source == "deck owner" and owners.get(name_key(owner), 0) > 1
        results.append(
            {
                "folder": event["folder"],
                "event": event["name"],
                "event_date": event.get("event_date"),
                "event_date_display": event.get("event_date_display"),
                "rating": event.get("rating", 1),
                "place": place,
                "label": finish_label(place),
                "cut_size": len(decks),
                "deck_id": deck_id,
                "deck_name": deck.get("name") or "",
                "avatar": _avatar(deck),
                "names": names,
                "name_source": source,
                "posted_by": owner,
                "shared_uploader": shared,
            }
        )
    return results


def _all_results() -> tuple[list[dict], list[dict]]:
    """(events with a top cut, every top cut result), cached on the event files."""
    repo = EventRepository()
    key = ("events", _events_signature(repo))
    with _cache_lock:
        if key in _cache:
            return _cache[key]
    events, results = [], []
    for event in repo.get_all_events():
        if not event.get("has_top8"):
            continue
        rows = _event_results(repo, event)
        if rows:
            events.append(event)
            results.extend(rows)
    with _cache_lock:
        for k in [k for k in _cache if k[0] == "events"]:
            del _cache[k]
        _cache[key] = (events, results)
    return events, results


# -- Summit players -------------------------------------------------------

def _summit_players() -> dict:
    """{user_id: {"name": shown name, "names": {raw names}}} for every Summit player."""
    players = {}

    def add(user_id, name, shown=False):
        user_id = bare_id(user_id)
        if not user_id or not name:
            return
        entry = players.setdefault(user_id, {"name": None, "names": set()})
        entry["names"].add(str(name))
        if shown or not entry["name"]:
            entry["name"] = str(name)

    conn = sqlite3.connect(str(webapp_config.ELO_DB_PATH))
    try:
        for table in ("overall_standings", "paper_standings"):
            try:
                for uid, name in conn.execute(f"SELECT user_id, user_display_name FROM {table}"):
                    add(uid, name)
            except sqlite3.OperationalError:
                pass
    finally:
        conn.close()

    conn = sqlite3.connect(str(webapp_config.MATCH_RECORDS_DB_PATH))
    try:
        rows = conn.execute(
            "SELECT user_id, display_name, custom_display_name, raw_oauth_data FROM user_profiles"
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()
    for uid, display, custom, raw in rows:
        add(uid, display)
        if raw:
            try:
                data = json.loads(raw)
                add(uid, data.get("global_name"))
                add(uid, data.get("username"))
            except (ValueError, AttributeError):
                pass
        add(uid, custom, shown=True)
    return players


def _name_index(players: dict) -> dict:
    """{name_key: {user_id, ...}}"""
    index = {}
    for user_id, entry in players.items():
        for name in entry["names"]:
            key = name_key(name)
            if key:
                index.setdefault(key, set()).add(user_id)
    return index


# -- matching -------------------------------------------------------------

def _decisions():
    repo = PaperLinkRepository()
    linked, rejected = {}, {}
    for row in repo.get_name_links():
        if row["status"] == "linked":
            linked[row["name_key"]] = bare_id(row["user_id"])
        else:
            rejected.setdefault(row["name_key"], set()).add(bare_id(row["user_id"]))
    return linked, rejected, repo.get_assignments(), repo.get_event_settings()


def _resolve(result: dict, index: dict, linked: dict, rejected: dict, assignments: dict) -> dict:
    """How this result maps to a Summit player.

    status is one of: assigned, linked, auto (these earn the badge), nobody,
    shared_uploader, ambiguous, short_name, unmatched.
    """
    assigned = assignments.get((result["folder"], result["deck_id"]))
    if assigned is not None:
        if assigned:
            return {"status": "assigned", "user_id": bare_id(assigned)}
        return {"status": "nobody", "user_id": None}

    keys = [k for k in (name_key(n) for n in result["names"]) if k]
    for key in keys:
        if key in linked:
            return {"status": "linked", "user_id": linked[key], "name_key": key}

    if result["shared_uploader"]:
        return {"status": "shared_uploader", "user_id": None}

    for key in keys:
        candidates = index.get(key, set()) - rejected.get(key, set())
        if len(candidates) > 1:
            return {"status": "ambiguous", "user_id": None, "name_key": key, "candidates": sorted(candidates)}
        if len(candidates) == 1:
            user_id = next(iter(candidates))
            if len(key) < MIN_AUTO_LENGTH:
                return {"status": "short_name", "user_id": None, "name_key": key, "candidates": [user_id]}
            return {"status": "auto", "user_id": user_id, "name_key": key}
    return {"status": "unmatched", "user_id": None, "name_key": keys[0] if keys else ""}


EARNS_BADGE = {"assigned", "linked", "auto"}


def _awards_on(event_settings: dict, events: list[dict]) -> set:
    return {
        e["folder"] for e in events
        if event_settings.get(e["folder"], event_default_on(e))
    }


def get_finishes_by_player() -> dict:
    """{player_id: [finish, ...]}, best finish first, then newest.

    The same deck in two events (a "Top 32" page that repeats the Top 8) is
    counted once, at its best finish.
    """
    events, results = _all_results()
    key = ("finishes", id(results), _db_signature())
    with _cache_lock:
        if key in _cache:
            return _cache[key]
    players = _summit_players()
    index = _name_index(players)
    linked, rejected, assignments, settings = _decisions()
    on = _awards_on(settings, events)

    by_player = {}
    for result in results:
        if result["folder"] not in on:
            continue
        match = _resolve(result, index, linked, rejected, assignments)
        if match["status"] not in EARNS_BADGE:
            continue
        finishes = by_player.setdefault(match["user_id"], {})
        key = result["deck_id"] or (result["folder"], result["place"])
        current = finishes.get(key)
        better = current is None or (
            (finish_rank(result["place"]), result["cut_size"]) < (finish_rank(current["place"]), current["cut_size"])
        )
        if better:
            finishes[key] = {
                k: result[k] for k in (
                    "folder", "event", "event_date", "event_date_display", "rating",
                    "place", "label", "cut_size", "avatar",
                )
            } | {"title": f"{result['label']} · {result['event']}"}

    out = {}
    for user_id, finishes in by_player.items():
        # One badge per event: a player in an event twice keeps their best.
        per_event = {}
        for f in finishes.values():
            if f["folder"] not in per_event or f["place"] < per_event[f["folder"]]["place"]:
                per_event[f["folder"]] = f
        rows = sorted(per_event.values(), key=lambda f: f["event_date"] or "", reverse=True)
        rows.sort(key=lambda f: finish_rank(f["place"]))
        out[user_id] = rows
    with _cache_lock:
        for k in [k for k in _cache if k[0] == "finishes"]:
            del _cache[k]
        _cache[key] = out
    return out


def get_player_finishes(user_id) -> list[dict]:
    return get_finishes_by_player().get(bare_id(user_id), [])


# -- admin review ---------------------------------------------------------

def _suggest(key: str, index: dict, rejected: dict, limit: int = 3) -> list[str]:
    """Players whose names are close to this paper name, best first."""
    if len(key) < MIN_AUTO_LENGTH:
        return []
    found = []
    for close in difflib.get_close_matches(key, index.keys(), n=limit * 2, cutoff=SUGGEST_CUTOFF):
        for user_id in sorted(index[close]):
            if user_id not in found and user_id not in rejected.get(key, set()):
                found.append(user_id)
    return found[:limit]


def admin_review() -> dict:
    """Every top cut result with how it matched, for the admin page."""
    events, results = _all_results()
    players = _summit_players()
    index = _name_index(players)
    linked, rejected, assignments, settings = _decisions()
    on = _awards_on(settings, events)

    def who(user_id):
        entry = players.get(user_id)
        return {"user_id": user_id, "name": entry["name"] if entry else f"Player {user_id}"}

    rows = []
    for result in results:
        match = _resolve(result, index, linked, rejected, assignments)
        row = {**result, "status": match["status"], "name_key": match.get("name_key", "")}
        row["player"] = who(match["user_id"]) if match.get("user_id") else None
        candidates = match.get("candidates") or []
        if match["status"] == "unmatched" and row["name_key"]:
            candidates = _suggest(row["name_key"], index, rejected)
        row["candidates"] = [who(c) for c in candidates]
        row["earns_badge"] = match["status"] in EARNS_BADGE and result["folder"] in on
        rows.append(row)

    event_rows = [
        {
            "folder": e["folder"],
            "name": e["name"],
            "event_date": e.get("event_date"),
            "event_date_display": e.get("event_date_display"),
            "awards_badges": e["folder"] in on,
            "default_on": event_default_on(e),
            "has_pairings": any(r["folder"] == e["folder"] and r["name_source"] == "registration" for r in results),
        }
        for e in events
    ]
    links = [
        {**link, "player": who(bare_id(link["user_id"]))}
        for link in PaperLinkRepository().get_name_links()
    ]
    return {"events": event_rows, "results": rows, "links": links}


def reset_cache():
    with _cache_lock:
        _cache.clear()
