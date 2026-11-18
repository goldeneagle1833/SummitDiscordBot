"""Top avatar badges for one paper event on the Top 8 page.

An admin presses "Award top avatar badges" on an event's Top 8 page. For each
avatar played anywhere in the event (the whole field, not only the top cut),
the best-finishing player on that avatar earns "Top <avatar>" at that event,
e.g. "Top Sparkmage · Avatar of the Realm 2026".

Where the order of finish comes from:
- The top cut keeps its order on the Top 8 page (the order admins can fix by
  dragging), so a Top 8 deck finishes at its position there.
- Everyone else finishes by their standing in the imported match history
  (sorcerytcg.com). An event without match history only knows its top cut,
  so only those decks count; the preview says so.

Players are matched to Summit accounts exactly like the paper finish badges
(services/paper_finishes.py): admin links and per-result picks first, then
an exact name match. Only a Summit account can hold a badge: when an avatar's
best finisher has none, nobody gets that avatar's badge (the next player on
it did not top it). The admin can link that player and award again.

Unlike the paper finishes, these are stored when awarded (table
event_avatar_badges in match_records.db), so they stay as the admin saw them
in the preview; awarding again replaces the event's badges, and Undo removes
them.
"""

import datetime
import json
import logging
import sqlite3
import threading

import webapp_config
from repositories.events import EventRepository
from services import paper_finishes as pf

logger = logging.getLogger(__name__)

_lock = threading.Lock()


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _conn():
    conn = sqlite3.connect(str(webapp_config.MATCH_RECORDS_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS event_avatar_badges (
               folder TEXT NOT NULL,
               avatar TEXT NOT NULL,
               user_id TEXT NOT NULL,
               event_name TEXT,
               event_date TEXT,
               place INTEGER,
               deck_id TEXT,
               wins INTEGER,
               losses INTEGER,
               draws INTEGER,
               avatar_players INTEGER,
               field_size INTEGER,
               awarded_by TEXT,
               awarded_at TEXT NOT NULL,
               PRIMARY KEY (folder, avatar)
           )"""
    )
    return conn


def _find_event(repo: EventRepository, folder: str) -> dict | None:
    for event in repo.get_all_events():
        if event["folder"] == folder:
            return event
    return None


def _field(repo: EventRepository, folder: str) -> tuple[list[dict], str]:
    """Every deck in the event with its finish, best first, and where the order came from.

    Each row: place, deck_id, avatar, names, shared_uploader, wins/losses/draws.
    """
    decks = repo._load_all_decks(folder) or []
    avatar_of = {d.get("id"): pf._avatar(d) for d in decks if isinstance(d, dict) and d.get("id")}

    files = repo._find_json_files(folder) or {}
    top8 = []
    if files.get("top8"):
        try:
            with open(files["top8"], "r", encoding="utf-8") as f:
                loaded = json.load(f)
            top8 = [d for d in loaded if isinstance(d, dict)] if isinstance(loaded, list) else []
        except Exception as e:
            logger.warning("Could not read top cut for %s: %s", folder, e)

    history = repo._load_match_history(folder) or {}
    registered = {p.get("deck_id"): p for p in history.get("players", []) if p.get("deck_id")}

    owners = {}
    for deck in top8:
        key = pf.name_key(deck.get("username"))
        if key:
            owners[key] = owners.get(key, 0) + 1

    def names_of(reg, owner):
        if reg:
            return [n for n in (reg.get("display_name"), reg.get("username")) if n and n != "Unknown"]
        return [owner] if owner else []

    rows, seen = [], set()
    for deck in top8:
        deck_id = deck.get("id") or ""
        if deck_id and deck_id in seen:
            continue  # a top cut file listing the same deck twice
        if deck_id:
            seen.add(deck_id)
        place = len(rows) + 1
        owner = (deck.get("username") or "").strip()
        reg = registered.get(deck_id)
        rows.append({
            "place": place,
            "deck_id": deck_id,
            "avatar": pf._avatar(deck) or avatar_of.get(deck_id, ""),
            "names": names_of(reg, owner),
            "shared_uploader": not reg and owners.get(pf.name_key(owner), 0) > 1,
            "wins": reg.get("wins") if reg else None,
            "losses": reg.get("losses") if reg else None,
            "draws": reg.get("draws") if reg else None,
        })

    if not registered:
        return rows, "top_cut"

    rest = [p for p in registered.values() if p.get("deck_id") not in seen]
    rest.sort(key=lambda p: (p.get("standing") or 99999, (p.get("display_name") or "").casefold()))
    for offset, reg in enumerate(rest, start=len(rows) + 1):
        rows.append({
            "place": offset,
            "deck_id": reg["deck_id"],
            "avatar": avatar_of.get(reg["deck_id"], ""),
            "names": names_of(reg, ""),
            "shared_uploader": False,
            "wins": reg.get("wins"),
            "losses": reg.get("losses"),
            "draws": reg.get("draws"),
        })
    return rows, "standings"


def preview(folder: str) -> dict | None:
    """Who would earn each avatar's badge at this event. None if no such event."""
    repo = EventRepository()
    event = _find_event(repo, folder)
    if event is None:
        return None
    rows, source = _field(repo, folder)

    players = pf._summit_players()
    index = pf._name_index(players)
    linked, rejected, assignments, _ = pf._decisions()

    best, counts = {}, {}
    for row in rows:
        if not row["avatar"]:
            continue
        counts[row["avatar"]] = counts.get(row["avatar"], 0) + 1
        if row["avatar"] not in best:  # rows are best finish first
            best[row["avatar"]] = row

    avatars = []
    for avatar, row in sorted(best.items(), key=lambda kv: (kv[1]["place"], kv[0])):
        match = pf._resolve(
            {"folder": folder, **row}, index, linked, rejected, assignments
        )
        user_id = match["user_id"] if match["status"] in pf.EARNS_BADGE else None
        entry = players.get(user_id) if user_id else None
        avatars.append({
            "avatar": avatar,
            "place": row["place"],
            "finish": pf.finish_label(row["place"]),
            "deck_id": row["deck_id"],
            "paper_name": row["names"][0] if row["names"] else "",
            "wins": row["wins"],
            "losses": row["losses"],
            "draws": row["draws"],
            "avatar_players": counts[avatar],
            "status": match["status"],
            "player": (
                {"user_id": user_id, "name": entry["name"] if entry else f"Player {user_id}"}
                if user_id else None
            ),
        })

    return {
        "folder": folder,
        "event": event["name"],
        "event_date": event.get("event_date"),
        "source": source,
        "field_size": len(rows),
        "avatars": avatars,
        "awarded": awarded_for_event(folder),
    }


def award(folder: str, admin: str) -> dict | None:
    """Save this event's badges as the preview shows them (replacing earlier ones)."""
    result = preview(folder)
    if result is None:
        return None
    winners = [a for a in result["avatars"] if a["player"]]
    with _lock:
        conn = _conn()
        try:
            conn.execute("DELETE FROM event_avatar_badges WHERE folder = ?", (folder,))
            now = _now()
            conn.executemany(
                """INSERT INTO event_avatar_badges (folder, avatar, user_id, event_name, event_date,
                       place, deck_id, wins, losses, draws, avatar_players, field_size,
                       awarded_by, awarded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (folder, a["avatar"], a["player"]["user_id"], result["event"],
                     result["event_date"], a["place"], a["deck_id"], a["wins"], a["losses"],
                     a["draws"], a["avatar_players"], result["field_size"], admin, now)
                    for a in winners
                ],
            )
            conn.commit()
        finally:
            conn.close()
    result["awarded"] = awarded_for_event(folder)
    return result


def undo(folder: str) -> int:
    """Remove every badge this event gave. Returns how many were removed."""
    with _lock:
        conn = _conn()
        try:
            cur = conn.execute("DELETE FROM event_avatar_badges WHERE folder = ?", (folder,))
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()


def _badge(row) -> dict:
    label = f"Top {row['avatar']}"
    return {
        "folder": row["folder"],
        "event": row["event_name"],
        "event_date": row["event_date"],
        "event_date_display": pf.format_date_display(row["event_date"]),
        "avatar": row["avatar"],
        "label": label,
        "title": f"{label} · {row['event_name']}",
        "place": row["place"],
        "finish": pf.finish_label(row["place"]) if row["place"] else None,
        "wins": row["wins"],
        "losses": row["losses"],
        "draws": row["draws"],
        "avatar_players": row["avatar_players"],
        "field_size": row["field_size"],
        "user_id": row["user_id"],
        "awarded_at": row["awarded_at"],
    }


def awarded_for_event(folder: str) -> list[dict]:
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM event_avatar_badges WHERE folder = ? ORDER BY place, avatar", (folder,)
        ).fetchall()
    finally:
        conn.close()
    return [_badge(r) for r in rows]


def get_badges_by_player() -> dict:
    """{player_id: [badge, ...]}, newest event first."""
    conn = _conn()
    try:
        rows = conn.execute("SELECT * FROM event_avatar_badges").fetchall()
    finally:
        conn.close()
    out = {}
    for row in rows:
        out.setdefault(pf.bare_id(row["user_id"]), []).append(_badge(row))
    for badges in out.values():
        badges.sort(key=lambda b: (b["event_date"] or "", b["avatar"]), reverse=True)
    return out
