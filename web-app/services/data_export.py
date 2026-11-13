"""Build a player's "export my data" download.

Everything here is read-only. The export holds the logged-in player's own
data from every site database: profile and settings, ratings and season
finishes, every match they played (Discord, web, Limited, Rumble and any
match table added later), decks they saved, kudos, articles, feedback,
store orders and so on.

Other players' private data never goes in:

* Match rows are turned around to the player's point of view ("my_*" and
  "opponent_*" columns). For the opponent only their id, name, avatar and
  elements are kept, so opponent deck lists, deck links and ratings stay out.
* Old single-deck columns (``curiosa_url``, ``json_deck_data``) and the
  match comment are kept only when this player reported the match.
* Blocks, reports and kudos only include the rows the player made, except
  kudos they received, which keep the giver's name only when the giver was
  not anonymous.
* Internal columns (admin notes, raw OAuth data, tokens) are left out.

Match tables are found by their columns, not their names: any table with
``winner_id`` plus ``losser_id`` / ``loser_id`` is read. A new season's
match table (for example the Glicko-2 one) is picked up without changes
here as long as it keeps those column names.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import webapp_config

logger = logging.getLogger(__name__)

# Database label -> webapp_config attribute holding its path. Read at call
# time so tests (and env overrides) that repoint webapp_config are honoured.
DATABASES = {
    "match_records": "MATCH_RECORDS_DB_PATH",
    "elo": "ELO_DB_PATH",
    "fart_scores": "FART_SCORES_DB_PATH",
    "community": "COMMUNITY_DB_PATH",
    "explorer": "EXPLORER_DB_PATH",
    "rumble": "RUMBLE_DB_PATH",
    "deck_builder": "DECK_BUILDER_DB_PATH",
    "feedback": "FEEDBACK_DB_PATH",
    "articles": "ARTICLES_DB_PATH",
    "meta_reports": "META_REPORTS_DB_PATH",
}

# Non-match tables: (section, table, columns that hold the owner's id).
# A row is exported when any of those columns is the player's id.
OWNED_TABLES = [
    ("profile", "user_profiles", ("user_id",)),
    ("ratings", "overall_standings", ("user_id",)),
    ("ratings", "paper_standings", ("user_id",)),
    ("ratings", "limited_elo", ("user_id",)),
    ("ratings", "avatar_standings", ("user_id",)),
    ("ratings", "lifetime_avatar_standings", ("user_id",)),
    ("seasons", "event_rating_adjustments", ("user_id",)),
    ("ratings", "lifetime_rating_adjustments", ("user_id",)),
    ("seasons", "event_standings_archive", ("user_id",)),
    ("seasons", "event_avatar_standings", ("user_id",)),
    ("seasons", "limited_event_standings_archive", ("user_id",)),
    ("seasons", "season_members", ("user_id",)),
    ("seasons", "season_feedback", ("user_id",)),
    ("seasons", "bracket_entrants", ("user_id",)),
    ("limited", "limited_arena_runs", ("user_id",)),
    ("limited", "limited_arena_runs_archive", ("user_id",)),
    ("match_related", "solo_match_reports", ("reporter_id", "user_id")),
    ("paper", "paper_manual_finishes", ("user_id",)),
    ("paper", "paper_name_links", ("user_id",)),
    ("paper", "paper_result_assignments", ("user_id",)),
    ("decks", "saved_decks", ("user_id",)),
    ("settings", "blocked_users", ("user_id",)),
    ("settings", "voice_only_players", ("user_id",)),
    ("settings", "creator_access", ("user_id",)),
    ("settings", "ticket_holders", ("user_id",)),
    ("settings", "meta_report_dm_subscribers", ("discord_id",)),
    ("community", "player_reports", ("reporter_id",)),
    ("community", "feedback", ("user_id",)),
    ("community", "fart_scores", ("user_id",)),
    ("community", "rumble_bones", ("discord_user_id",)),
    ("community", "rumble_bone_transactions", ("discord_user_id",)),
    ("articles", "articles", ("author_id",)),
    ("articles", "article_public_comments", ("user_id",)),
    ("store", "orders", ("user_id",)),
    ("explorer", "explorer_applications", ("discord_user_id",)),
]

# Columns never exported from any table: staff-only notes, raw login data,
# secrets, and who on staff set something.
DROP_COLUMNS = {
    "raw_oauth_data", "admin_notes", "token", "access_token", "refresh_token",
    "password", "secret", "api_key", "last_error", "reviewed_by", "set_by",
    "admin_user_id", "granted_by", "hidden_by",
}

# Opponent fields that are public on the site; every other opponent column
# (deck links, deck lists, ratings) is dropped.
OPPONENT_KEEP = {"id", "display_name", "avatar", "user_id"}

# Match columns that don't say whose they are. Kept only when this player
# reported the match (the old single-deck format stored the reporter's deck).
REPORTER_ONLY = {"curiosa_url", "json_deck_data", "curiosa_link", "match_comment", "old_json_deck"}

# Columns that are ambiguous once the row is turned around.
MATCH_DROP = {"did_win", "first_player"}

# Winner/loser tables that aren't the played-match history itself (pending
# confirmations, per-season rating copies). Exported under "match_related"
# so they don't double-count games.
SECONDARY_MATCH_TABLES = {"match_confirmations", "season_match_elo", "pairings", "limited_active_pairings"}

_SIDE_RE = re.compile(r"^(winner|loser|losser)_(.+)$|^(.+)_(winner|loser|losser)$")


def id_variants(user_id: str) -> list[str]:
    """Every way this player's id is stored (Google ids with/without prefix)."""
    raw = str(user_id)
    bare = raw[7:] if raw.startswith("google_") else raw
    out = [raw, bare, f"google_{bare}"]
    return list(dict.fromkeys(out))


def _db_paths() -> dict[str, Path]:
    paths = {}
    for label, attr in DATABASES.items():
        p = getattr(webapp_config, attr, None)
        if p and Path(p).exists():
            paths[label] = Path(p)
    try:  # the store keeps its own path in its repository module
        from repositories import store as store_repo
        p = Path(store_repo.STORE_DB_PATH)
        if p.exists():
            paths["store"] = p
    except Exception:  # pragma: no cover - store module missing/broken
        pass
    return paths


def _clean(value):
    if isinstance(value, bytes):
        return None
    if isinstance(value, int) and not isinstance(value, bool) and abs(value) > 2**53:
        return str(value)  # Discord ids: JSON readers would round them
    if isinstance(value, str) and value[:1] in "[{":
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _columns(cur, table: str) -> list[str]:
    cur.execute(f'PRAGMA table_info("{table}")')
    return [r[1] for r in cur.fetchall()]


def _tables(cur) -> list[str]:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    return [r[0] for r in cur.fetchall()]


def _match_side_columns(cols: list[str]) -> tuple[str, str] | None:
    """(winner id column, loser id column) if this is a match table."""
    if "winner_id" not in cols:
        return None
    for loser in ("losser_id", "loser_id"):
        if loser in cols:
            return "winner_id", loser
    return None


def _deck_json(row: dict, side: str):
    """The raw deck JSON for one side ("winner" / "loser"), if stored."""
    for col in (f"json_deck_data_{side}", f"{side}_json", f"{side}_deck_json"):
        if row.get(col):
            return row[col]
    return None


def _avatar_and_elements(deck_json) -> tuple[str | None, list[str]]:
    """Avatar name and elements of a deck, the same way the profile shows them."""
    if not isinstance(deck_json, str) or not deck_json.strip():
        return None, []
    from routes.api.players import _extract_deck_info  # lazy: avoid import cycle
    return _extract_deck_info(deck_json)


def _as_player_view(row: dict, i_won: bool, i_reported: bool) -> dict:
    """Turn a winner/loser match row into my_* / opponent_* fields."""
    me = "winner" if i_won else "loser"
    them = "loser" if i_won else "winner"
    out = {"result": "win" if i_won else "loss"}
    # Avatar and elements for both sides, read from the deck lists before the
    # opponent's list is dropped (the profile's Matches tab shows the same).
    for who, side in (("my", me), ("opponent", them)):
        avatar, elements = _avatar_and_elements(_deck_json(row, side))
        out[f"{who}_elements"] = elements
        if avatar:
            out[f"{who}_deck_avatar"] = avatar
    for col, value in row.items():
        if col in DROP_COLUMNS or col in MATCH_DROP:
            continue
        m = _SIDE_RE.match(col)
        if m:
            side = m.group(1) or m.group(4)
            field = m.group(2) or m.group(3)
            side = "loser" if side == "losser" else side
            if side == me:
                out[f"my_{field}"] = _clean(value)
            elif field in OPPONENT_KEEP:
                out[f"opponent_{field}"] = _clean(value)
            continue
        if col in REPORTER_ONLY:
            if i_reported:
                out[col] = _clean(value)
            continue
        out[col] = _clean(value)
    for who in ("my", "opponent"):
        deck_avatar = out.pop(f"{who}_deck_avatar", None)
        if not out.get(f"{who}_avatar") and deck_avatar:
            out[f"{who}_avatar"] = deck_avatar
    return out


def _export_matches(label: str, cur, table: str, cols: list[str], ids: list[str]) -> list[dict]:
    win_col, lose_col = _match_side_columns(cols)
    marks = ",".join("?" * len(ids))
    cur.execute(
        f'SELECT rowid AS _rowid, * FROM "{table}" WHERE "{win_col}" IN ({marks}) OR "{lose_col}" IN ({marks})',
        (*ids, *ids),
    )
    names = [d[0] for d in cur.description]
    id_set = set(ids)
    rows = []
    for raw in cur.fetchall():
        row = dict(zip(names, raw))
        rowid = row.pop("_rowid", None)
        if "id" not in row and row.get("match_id") is None:
            row["match_id"] = rowid  # the bot's match id is the rowid
        i_won = str(row.get(win_col)) in id_set
        reporter = row.get("reporter_id")
        i_reported = reporter is not None and str(reporter) in id_set
        view = _as_player_view(row, i_won, i_reported)
        view["table"] = table if label == "match_records" else f"{label}.{table}"
        rows.append(view)
    return rows


def _export_owned(cur, table: str, cols: list[str], owner_cols, ids: list[str]) -> list[dict]:
    present = [c for c in owner_cols if c in cols]
    if not present:
        return []
    marks = ",".join("?" * len(ids))
    where = " OR ".join(f'"{c}" IN ({marks})' for c in present)
    cur.execute(f'SELECT * FROM "{table}" WHERE {where}', tuple(ids) * len(present))
    names = [d[0] for d in cur.description]
    return [
        {k: _clean(v) for k, v in zip(names, raw) if k not in DROP_COLUMNS}
        for raw in cur.fetchall()
    ]


def _export_kudos(cur, cols: list[str], ids: list[str]) -> dict:
    marks = ",".join("?" * len(ids))
    out = {"given": [], "received": []}
    if "giver_id" in cols:
        cur.execute(f"SELECT * FROM player_kudos WHERE giver_id IN ({marks})", ids)
        names = [d[0] for d in cur.description]
        out["given"] = [{k: _clean(v) for k, v in zip(names, r) if k not in DROP_COLUMNS} for r in cur.fetchall()]
    if "receiver_id" in cols:
        hidden = " AND COALESCE(hidden, 0) = 0" if "hidden" in cols else ""
        cur.execute(f"SELECT * FROM player_kudos WHERE receiver_id IN ({marks}){hidden}", ids)
        names = [d[0] for d in cur.description]
        for r in cur.fetchall():
            row = dict(zip(names, r))
            item = {k: _clean(row.get(k)) for k in ("id", "match_id", "match_type", "reasons", "message", "source", "created_at") if k in row}
            if not row.get("anonymous"):
                item["giver_id"] = row.get("giver_id")
                item["giver_name"] = row.get("giver_name")
            else:
                item["giver_name"] = "Anonymous"
            out["received"].append(item)
    return out


def _order_items(cur, order_ids: list) -> list[dict]:
    if not order_ids:
        return []
    cols = _columns(cur, "order_items")
    if "order_id" not in cols:
        return []
    marks = ",".join("?" * len(order_ids))
    cur.execute(f"SELECT * FROM order_items WHERE order_id IN ({marks})", order_ids)
    names = [d[0] for d in cur.description]
    return [{k: _clean(v) for k, v in zip(names, r) if k not in DROP_COLUMNS} for r in cur.fetchall()]


def build_export(user_id: str) -> dict:
    """Collect everything the player owns into one JSON-ready dict."""
    ids = id_variants(user_id)
    owned = {}
    for section, table, owner_cols in OWNED_TABLES:
        owned.setdefault(table, (section, owner_cols))

    data: dict = {
        "player_id": str(user_id),
        "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "site": "sorcererssummit.com",
        "matches": [],
    }

    for label, path in _db_paths().items():
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        except sqlite3.Error as e:
            logger.warning("Export: could not open %s: %s", label, e)
            continue
        try:
            cur = conn.cursor()
            try:
                tables = _tables(cur)
            except sqlite3.Error as e:
                logger.warning("Export: could not read %s: %s", label, e)
                continue
            for table in tables:
                if table.startswith("sqlite_"):
                    continue
                try:
                    cols = _columns(cur, table)
                    if table == "player_kudos":
                        data["kudos"] = _export_kudos(cur, cols, ids)
                    elif _match_side_columns(cols):
                        rows = _export_matches(label, cur, table, cols, ids)
                        if table in SECONDARY_MATCH_TABLES:
                            if rows:
                                data.setdefault("match_related", {})[table] = rows
                        else:
                            data["matches"].extend(rows)
                    elif table in owned:
                        section, owner_cols = owned[table]
                        rows = _export_owned(cur, table, cols, owner_cols, ids)
                        if not rows:
                            continue
                        data.setdefault(section, {})
                        key = table if table not in data[section] else f"{label}.{table}"
                        data[section][key] = rows
                        if table == "orders":
                            items = _order_items(cur, [r.get("id") for r in rows if r.get("id") is not None])
                            if items:
                                data[section]["order_items"] = items
                except Exception as e:  # one odd table must never sink the whole export
                    logger.warning("Export: skipped %s.%s: %s", label, table, e, exc_info=True)
        finally:
            conn.close()

    data["matches"].sort(key=lambda m: str(m.get("timestamp") or m.get("created_at") or ""), reverse=True)
    data["summary"] = {
        "matches": len(data["matches"]),
        "wins": sum(1 for m in data["matches"] if m["result"] == "win"),
        "losses": sum(1 for m in data["matches"] if m["result"] == "loss"),
    }
    return data


MATCH_CSV_COLUMNS = [
    "timestamp", "table", "match_id", "result", "match_type", "source",
    "opponent_id", "opponent_display_name", "my_avatar", "my_elements",
    "opponent_avatar", "opponent_elements",
    "my_elo_change", "my_lifetime_elo_change", "my_lifetime_elo_after",
    "my_avatar_elo_change", "my_went_first", "match_time", "voice",
    "my_curiosa_url", "my_deck_url", "replay_url",
]

README = """Your Sorcerers Summit data
==========================

Exported {exported_at} for player id {player_id}.

summit-data.json  Everything we hold for you, grouped by section:
                  profile, ratings, seasons, matches, limited, paper,
                  decks, kudos, settings, community, articles, store.
matches.csv       Your match history as a spreadsheet, newest first.

In matches, "my_" fields are yours and "opponent_" fields are the other
player's. You get your opponent's avatar and elements, but not their deck
list or deck link.
"""


def matches_csv(matches: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=MATCH_CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for m in matches:
        row = {k: m.get(k) for k in MATCH_CSV_COLUMNS}
        for k in ("my_elements", "opponent_elements"):
            row[k] = " ".join(m.get(k) or [])
        writer.writerow(row)
    return buf.getvalue()


def export_stats(data: dict) -> dict:
    """What went into an export, for the admin Data Exports tile."""
    sections = sorted(
        k for k, v in data.items()
        if k not in ("player_id", "exported_at", "site", "summary") and v
    )
    return {"matches": len(data.get("matches") or []), "sections": sections}


def build_export_zip(user_id: str) -> tuple[bytes, str]:
    """Return (zip bytes, file name) for the player's export."""
    payload, filename, _ = build_export_zip_with_stats(user_id)
    return payload, filename


def build_export_zip_with_stats(user_id: str) -> tuple[bytes, str, dict]:
    """Return (zip bytes, file name, stats) for the player's export."""
    data = build_export(user_id)
    stamp = data["exported_at"][:10]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("summit-data.json", json.dumps(data, indent=2, default=str))
        zf.writestr("matches.csv", matches_csv(data["matches"]))
        zf.writestr("README.txt", README.format(**data))
    payload = buf.getvalue()
    stats = export_stats(data)
    stats["bytes"] = len(payload)
    return payload, f"sorcerers-summit-data-{stamp}.zip", stats
