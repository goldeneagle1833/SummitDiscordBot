"""Precon ladder: Lavamancer (LM) vs Frostmage (FM), rated per player with Glicko-2.

A precon season is a fixed window (four weeks by default). Every precon queue
game reported inside it moves both players' Glicko-2 rating on that season's
ladder. One rating per player, whichever precon they played; each player's
record with each precon is kept beside it.

Tables (all in match_records.db, created on first use):

- ``precon_seasons``: one row per ladder window (``starts_at`` .. ``ends_at``,
  ISO server-local time; ``ended_at`` set when an admin ends it early).
- ``precon_match_records``: every precon game, never in ``match_records``, so
  precon games stay out of ranked, avatar and card stats. ``season_id`` is
  NULL for a game reported while no season was open (kept, not rated).
  Removed games stay with ``removed = 1`` so a removal can be checked later.
- ``precon_ratings``: each player's current rating on each season, rebuilt
  from the season's games whenever the past changes (``rebuild_season``).
- ``precon_settings``: the rules admins can change on the Admin page (queue
  switch, games needed to be ranked, rematch block, default season length).

Glicko-2 settings match the Season 9 plan: 1500 start, RD 200, RD floor 80,
tau 0.5, uncertainty grows a little for each day without games.

This file is kept identical in discord-bot/services and web-app/services
(the web app can't import the bot); a test checks that the copies match.
"""

from __future__ import annotations

import datetime
import math
import sqlite3
from dataclasses import dataclass

# --- Precons ----------------------------------------------------------------

LAVAMANCER = "lavamancer"
FROSTMAGE = "frostmage"
PRECONS = {
    LAVAMANCER: {"key": LAVAMANCER, "label": "Lavamancer", "short": "LM"},
    FROSTMAGE: {"key": FROSTMAGE, "label": "Frostmage", "short": "FM"},
}
_PRECON_ALIASES = {
    "lavamancer": LAVAMANCER, "lm": LAVAMANCER, "lava": LAVAMANCER,
    "frostmage": FROSTMAGE, "fm": FROSTMAGE, "frost": FROSTMAGE,
}

SEASON_DAYS = 28
# Below this many games a player is listed under "Not yet ranked".
MIN_RANKED_GAMES = 5


def normalize_precon(value) -> str | None:
    """'LM', 'Lavamancer', 'lavamancer' -> 'lavamancer'; anything else -> None."""
    if value is None:
        return None
    return _PRECON_ALIASES.get(str(value).strip().lower().replace(" ", ""))


def precon_label(value) -> str | None:
    key = normalize_precon(value)
    return PRECONS[key]["label"] if key else None


def precon_choices() -> list[dict]:
    return [dict(PRECONS[LAVAMANCER]), dict(PRECONS[FROSTMAGE])]


# --- Glicko-2 ---------------------------------------------------------------

START_RATING = 1500.0
START_RD = 200.0
RD_FLOOR = 80.0
START_VOL = 0.06
TAU = 0.5
PERIOD_DAYS = 1.0
_SCALE = 173.7178


@dataclass
class Rating:
    rating: float = START_RATING
    rd: float = START_RD
    vol: float = START_VOL
    last_at: str | None = None

    @property
    def display(self) -> int:
        return int(round(self.rating))


def _parse(ts) -> datetime.datetime:
    return datetime.datetime.fromisoformat(str(ts).replace("Z", "").replace(" ", "T"))


def _g(phi: float) -> float:
    return 1 / math.sqrt(1 + 3 * phi ** 2 / math.pi ** 2)


def rd_at(entry: Rating, at: str) -> float:
    """The entry's uncertainty at ``at``: it grows with time away, up to the start value."""
    if not entry.last_at:
        return entry.rd
    days = max((_parse(at) - _parse(entry.last_at)).total_seconds() / 86400, 0)
    phi = entry.rd / _SCALE
    grown = math.sqrt(phi ** 2 + entry.vol ** 2 * days / PERIOD_DAYS) * _SCALE
    return min(grown, START_RD)


def _update(mu, phi, vol, mu_j, phi_j, score):
    """One Glicko-2 rating period with a single game (Glickman, 2012)."""
    g = _g(phi_j)
    expected = 1 / (1 + math.exp(-g * (mu - mu_j)))
    v = 1 / (g ** 2 * expected * (1 - expected))
    delta = v * g * (score - expected)
    a = math.log(vol ** 2)

    def f(x):
        ex = math.exp(x)
        return (ex * (delta ** 2 - phi ** 2 - v - ex) / (2 * (phi ** 2 + v + ex) ** 2)
                - (x - a) / TAU ** 2)

    big_a = a
    if delta ** 2 > phi ** 2 + v:
        big_b = math.log(delta ** 2 - phi ** 2 - v)
    else:
        k = 1
        while f(a - k * TAU) < 0:
            k += 1
        big_b = a - k * TAU
    f_a, f_b = f(big_a), f(big_b)
    while abs(big_b - big_a) > 1e-6:
        big_c = big_a + (big_a - big_b) * f_a / (f_b - f_a)
        f_c = f(big_c)
        if f_c * f_b <= 0:
            big_a, f_a = big_b, f_b
        else:
            f_a /= 2
        big_b, f_b = big_c, f_c
    new_vol = math.exp(big_a / 2)
    phi_star = math.sqrt(phi ** 2 + new_vol ** 2)
    new_phi = 1 / math.sqrt(1 / phi_star ** 2 + 1 / v)
    new_phi = max(new_phi, RD_FLOOR / _SCALE)
    new_mu = mu + new_phi ** 2 * g * (score - expected)
    return new_mu, new_phi, new_vol


def play(winner: Rating, loser: Rating, at: str) -> tuple[Rating, Rating]:
    """Both entries after ``winner`` beat ``loser`` at time ``at`` (ISO)."""
    w_mu, w_phi = (winner.rating - START_RATING) / _SCALE, rd_at(winner, at) / _SCALE
    l_mu, l_phi = (loser.rating - START_RATING) / _SCALE, rd_at(loser, at) / _SCALE
    nw = _update(w_mu, w_phi, winner.vol, l_mu, l_phi, 1)
    nl = _update(l_mu, l_phi, loser.vol, w_mu, w_phi, 0)
    return (
        Rating(START_RATING + nw[0] * _SCALE, nw[1] * _SCALE, nw[2], at),
        Rating(START_RATING + nl[0] * _SCALE, nl[1] * _SCALE, nl[2], at),
    )


# --- Schema -----------------------------------------------------------------


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS precon_seasons (
            season_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            starts_at TEXT NOT NULL,
            ends_at TEXT NOT NULL,
            ended_at TEXT,
            created_by TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            final_posted_at TEXT
        )
    """)
    season_columns = {row[1] for row in conn.execute("PRAGMA table_info(precon_seasons)")}
    if "final_posted_at" not in season_columns:
        conn.execute("ALTER TABLE precon_seasons ADD COLUMN final_posted_at TEXT")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS precon_match_records (
            match_id INTEGER PRIMARY KEY AUTOINCREMENT,
            season_id INTEGER,
            pairing_id INTEGER,
            reporter_id INTEGER,
            winner_id INTEGER NOT NULL,
            winner_display_name TEXT,
            loser_id INTEGER NOT NULL,
            loser_display_name TEXT,
            winner_precon TEXT,
            loser_precon TEXT,
            timestamp TEXT NOT NULL,
            source TEXT,
            first_player TEXT,
            winner_went_first TEXT,
            loser_went_first TEXT,
            match_time INTEGER,
            match_comment TEXT,
            winner_rating_before INTEGER,
            winner_rating_after INTEGER,
            loser_rating_before INTEGER,
            loser_rating_after INTEGER,
            removed INTEGER NOT NULL DEFAULT 0,
            replay_url TEXT
        )
    """)
    match_columns = {row[1] for row in conn.execute("PRAGMA table_info(precon_match_records)")}
    if "replay_url" not in match_columns:
        conn.execute("ALTER TABLE precon_match_records ADD COLUMN replay_url TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_precon_matches_season ON precon_match_records (season_id, timestamp)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_precon_matches_pairing ON precon_match_records (pairing_id)"
    )
    conn.execute("""
        CREATE TABLE IF NOT EXISTS precon_ratings (
            season_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            display_name TEXT,
            rating REAL NOT NULL,
            rd REAL NOT NULL,
            vol REAL NOT NULL,
            last_at TEXT,
            games INTEGER NOT NULL DEFAULT 0,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            lm_wins INTEGER NOT NULL DEFAULT 0,
            lm_losses INTEGER NOT NULL DEFAULT 0,
            fm_wins INTEGER NOT NULL DEFAULT 0,
            fm_losses INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (season_id, user_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS precon_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_by TEXT,
            updated_at TEXT
        )
    """)


def _now_iso(now=None) -> str:
    return (now or datetime.datetime.now()).replace(microsecond=0).isoformat()


def _row(cursor, row):
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


# --- Settings ---------------------------------------------------------------

# name -> (default, type, min, max). The queue starts switched off, so merging
# never opens it; an admin turns it on from the Admin page or with !precon_queue.
SETTINGS = {
    "queue_enabled": (False, bool, None, None),
    "min_ranked_games": (MIN_RANKED_GAMES, int, 1, 50),
    "block_rematch": (True, bool, None, None),
    "season_days": (SEASON_DAYS, int, 1, 120),
    # Play Sorcery Online test mode: while the real queue is closed, the precon
    # endpoints answer 200 with sample data so PSO can build against them.
    # Nobody is queued and nothing is rated.
    "pso_test_mode": (False, bool, None, None),
}


def _parse_setting(name, raw):
    default, kind, low, high = SETTINGS[name]
    if kind is bool:
        if isinstance(raw, bool):
            return raw
        text = str(raw).strip().lower()
        if text in ("1", "true", "yes", "on"):
            return True
        if text in ("0", "false", "no", "off"):
            return False
        raise ValueError(f"{name} must be on or off")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a whole number") from None
    if isinstance(raw, bool) or value < low or value > high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return value


def get_settings(conn) -> dict:
    """Every setting, with defaults filled in for ones never changed."""
    ensure_schema(conn)
    stored = dict(conn.execute("SELECT key, value FROM precon_settings").fetchall())
    out = {}
    for name, (default, _kind, _low, _high) in SETTINGS.items():
        try:
            out[name] = _parse_setting(name, stored[name]) if name in stored else default
        except ValueError:
            out[name] = default
    return out


def update_settings(conn, changes: dict, updated_by=None, now=None) -> dict:
    """Change some settings (all checked before any is saved). Returns every setting."""
    ensure_schema(conn)
    unknown = [name for name in changes if name not in SETTINGS]
    if unknown:
        raise ValueError(f"Unknown setting: {unknown[0]}")
    parsed = {name: _parse_setting(name, value) for name, value in changes.items()}
    for name, value in parsed.items():
        stored = ("1" if value else "0") if isinstance(value, bool) else str(value)
        conn.execute(
            """INSERT INTO precon_settings (key, value, updated_by, updated_at) VALUES (?, ?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                   updated_by = excluded.updated_by, updated_at = excluded.updated_at""",
            (name, stored, str(updated_by) if updated_by is not None else None, _now_iso(now)),
        )
    conn.commit()
    return get_settings(conn)


def min_ranked_games(conn) -> int:
    return get_settings(conn)["min_ranked_games"]


# --- Seasons ----------------------------------------------------------------


def get_season(conn, season_id) -> dict | None:
    ensure_schema(conn)
    cur = conn.execute("SELECT * FROM precon_seasons WHERE season_id = ?", (season_id,))
    row = cur.fetchone()
    return _with_open(_row(cur, row)) if row else None


def _with_open(season: dict, now=None) -> dict:
    now_iso = _now_iso(now)
    season["is_open"] = bool(
        not season.get("ended_at")
        and season["starts_at"] <= now_iso < season["ends_at"]
    )
    season["last_day"] = season.get("ended_at") or season["ends_at"]
    return season


def list_seasons(conn, now=None) -> list[dict]:
    ensure_schema(conn)
    cur = conn.execute("SELECT * FROM precon_seasons ORDER BY starts_at DESC, season_id DESC")
    return [_with_open(_row(cur, r), now) for r in cur.fetchall()]


def open_season(conn, now=None) -> dict | None:
    """The season whose window is open right now, if any."""
    ensure_schema(conn)
    now_iso = _now_iso(now)
    cur = conn.execute(
        """SELECT * FROM precon_seasons
           WHERE ended_at IS NULL AND starts_at <= ? AND ends_at > ?
           ORDER BY starts_at DESC LIMIT 1""",
        (now_iso, now_iso),
    )
    row = cur.fetchone()
    return _with_open(_row(cur, row), now) if row else None


def current_or_latest_season(conn, now=None) -> dict | None:
    """The open season, else the next one scheduled, else the most recent one."""
    season = open_season(conn, now)
    if season:
        return season
    now_iso = _now_iso(now)
    cur = conn.execute(
        """SELECT * FROM precon_seasons WHERE ended_at IS NULL AND starts_at > ?
           ORDER BY starts_at LIMIT 1""",
        (now_iso,),
    )
    row = cur.fetchone()
    if row:
        return _with_open(_row(cur, row), now)
    seasons = list_seasons(conn, now)
    return seasons[0] if seasons else None


def start_season(conn, name, created_by=None, days=SEASON_DAYS, starts_at=None, now=None) -> dict:
    """Open a new precon ladder window. Refuses while another window is open or scheduled."""
    ensure_schema(conn)
    name = (name or "").strip()
    if not name:
        raise ValueError("A season name is required")
    if days < 1 or days > 120:
        raise ValueError("A precon season runs between 1 and 120 days")
    start = starts_at or (now or datetime.datetime.now())
    start_iso = _now_iso(start)
    if open_season(conn, now):
        raise ValueError("A precon season is already running")
    scheduled = conn.execute(
        "SELECT name FROM precon_seasons WHERE ended_at IS NULL AND starts_at > ?",
        (_now_iso(now),),
    ).fetchone()
    if scheduled:
        raise ValueError(f"A precon season is already scheduled ({scheduled[0]})")
    end_iso = _now_iso(start + datetime.timedelta(days=days))
    cur = conn.execute(
        "INSERT INTO precon_seasons (name, starts_at, ends_at, created_by) VALUES (?, ?, ?, ?)",
        (name, start_iso, end_iso, str(created_by) if created_by is not None else None),
    )
    conn.commit()
    return get_season(conn, cur.lastrowid)


def parse_when(value, field):
    """A date and time as naive server-local time. A time with a UTC offset (what
    the Admin page sends) is converted; a naive one is taken as server-local."""
    if not isinstance(value, datetime.datetime):
        try:
            value = datetime.datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(f"{field} must be a date and time") from None
    if value.tzinfo is not None:
        value = value.astimezone().replace(tzinfo=None)
    return value.replace(microsecond=0)


def with_offset(iso):
    """A stored naive server-local time with its UTC offset, so browsers in any
    time zone read it right."""
    if not iso:
        return None
    try:
        return datetime.datetime.fromisoformat(iso).astimezone().isoformat()
    except ValueError:
        return None


def update_season(conn, season_id, name=None, starts_at=None, ends_at=None, now=None) -> dict:
    """Rename a season or move its dates. Moving the dates re-rates the season,
    since only games inside the window count."""
    season = get_season(conn, season_id)
    if not season:
        raise ValueError("No such precon season")
    new_name = season["name"] if name is None else (name or "").strip()
    if not new_name:
        raise ValueError("A season name is required")
    start = parse_when(starts_at, "Start") if starts_at else parse_when(season["starts_at"], "Start")
    end = parse_when(ends_at, "End") if ends_at else parse_when(season["ends_at"], "End")
    if end <= start:
        raise ValueError("The end must be after the start")
    if (end - start).days > 120:
        raise ValueError("A precon season runs between 1 and 120 days")
    start_iso, end_iso = _now_iso(start), _now_iso(end)
    overlap = conn.execute(
        """SELECT name FROM precon_seasons
           WHERE season_id != ? AND starts_at < ? AND COALESCE(ended_at, ends_at) > ?""",
        (season_id, end_iso, start_iso),
    ).fetchone()
    if overlap:
        raise ValueError(f"Those dates overlap another precon season ({overlap[0]})")
    dates_changed = (start_iso, end_iso) != (season["starts_at"], season["ends_at"])
    conn.execute(
        "UPDATE precon_seasons SET name = ?, starts_at = ?, ends_at = ? WHERE season_id = ?",
        (new_name, start_iso, end_iso, season_id),
    )
    if dates_changed:
        # A season pushed back into the future (or reopened) gets a fresh final post
        if not season.get("ended_at") and end_iso > _now_iso(now):
            conn.execute("UPDATE precon_seasons SET final_posted_at = NULL WHERE season_id = ?", (season_id,))
        _reassign_games(conn, season_id, start_iso, end_iso, season.get("ended_at"))
    conn.commit()
    return _with_open(get_season(conn, season_id), now)


def _reassign_games(conn, season_id, start_iso, end_iso, ended_at):
    """After a date change: games outside the window leave the season, games
    inside it with no season join it, then the season is re-rated."""
    last = min(end_iso, ended_at) if ended_at else end_iso
    conn.execute(
        """UPDATE precon_match_records SET season_id = NULL, winner_rating_before = NULL,
               winner_rating_after = NULL, loser_rating_before = NULL, loser_rating_after = NULL
           WHERE season_id = ? AND (timestamp < ? OR timestamp >= ?)""",
        (season_id, start_iso, last),
    )
    conn.execute(
        """UPDATE precon_match_records SET season_id = ?
           WHERE season_id IS NULL AND timestamp >= ? AND timestamp < ?""",
        (season_id, start_iso, last),
    )
    rebuild_season(conn, season_id)


def seasons_needing_final_post(conn, now=None) -> list[dict]:
    """Seasons that have finished but whose final standings haven't been posted yet."""
    ensure_schema(conn)
    now_iso = _now_iso(now)
    cur = conn.execute(
        """SELECT * FROM precon_seasons
           WHERE final_posted_at IS NULL AND (ended_at IS NOT NULL OR ends_at <= ?)
           ORDER BY season_id""",
        (now_iso,),
    )
    return [_with_open(_row(cur, r), now) for r in cur.fetchall()]


def mark_final_posted(conn, season_id, now=None) -> None:
    conn.execute(
        "UPDATE precon_seasons SET final_posted_at = ? WHERE season_id = ?",
        (_now_iso(now), season_id),
    )
    conn.commit()


def end_season(conn, now=None) -> dict | None:
    """End the open season now. Returns it, or None when nothing was open."""
    season = open_season(conn, now)
    if not season:
        return None
    conn.execute(
        "UPDATE precon_seasons SET ended_at = ? WHERE season_id = ?",
        (_now_iso(now), season["season_id"]),
    )
    conn.commit()
    return get_season(conn, season["season_id"])


# --- Ratings ----------------------------------------------------------------


_RECORD_COLUMNS = {
    LAVAMANCER: ("lm_wins", "lm_losses"),
    FROSTMAGE: ("fm_wins", "fm_losses"),
}


def _load_rating(conn, season_id, user_id):
    row = conn.execute(
        "SELECT rating, rd, vol, last_at FROM precon_ratings WHERE season_id = ? AND user_id = ?",
        (season_id, user_id),
    ).fetchone()
    return Rating(row[0], row[1], row[2], row[3]) if row else Rating()


def _save_result(conn, season_id, user_id, name, rating: Rating, won: bool, precon):
    conn.execute(
        """INSERT INTO precon_ratings (season_id, user_id, display_name, rating, rd, vol, last_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(season_id, user_id) DO UPDATE SET
               display_name = COALESCE(excluded.display_name, display_name),
               rating = excluded.rating, rd = excluded.rd, vol = excluded.vol,
               last_at = excluded.last_at""",
        (season_id, user_id, name, rating.rating, rating.rd, rating.vol, rating.last_at),
    )
    result_col = "wins" if won else "losses"
    sets = [f"games = games + 1", f"{result_col} = {result_col} + 1"]
    if precon in _RECORD_COLUMNS:
        col = _RECORD_COLUMNS[precon][0 if won else 1]
        sets.append(f"{col} = {col} + 1")
    conn.execute(
        f"UPDATE precon_ratings SET {', '.join(sets)} WHERE season_id = ? AND user_id = ?",
        (season_id, user_id),
    )


def record_match(
    conn,
    *,
    winner_id,
    loser_id,
    winner_name=None,
    loser_name=None,
    winner_precon=None,
    loser_precon=None,
    pairing_id=None,
    reporter_id=None,
    source="discord",
    first_player=None,
    winner_went_first=None,
    loser_went_first=None,
    match_time=None,
    match_comment=None,
    replay_url=None,
    now=None,
) -> dict:
    """Save one precon game and rate it on the open season.

    Returns {match_id, season_id, rated, winner_before, winner_after,
    loser_before, loser_after} (ratings rounded; None when unrated).
    """
    ensure_schema(conn)
    winner_id, loser_id = int(winner_id), int(loser_id)
    if winner_id == loser_id:
        raise ValueError("A player can't play themselves")
    winner_precon = normalize_precon(winner_precon)
    loser_precon = normalize_precon(loser_precon)
    at = _now_iso(now)
    season = open_season(conn, now)
    season_id = season["season_id"] if season else None
    before_w = before_l = after_w = after_l = None
    if season_id is not None:
        w0 = _load_rating(conn, season_id, winner_id)
        l0 = _load_rating(conn, season_id, loser_id)
        w1, l1 = play(w0, l0, at)
        before_w, before_l, after_w, after_l = w0.display, l0.display, w1.display, l1.display
    cur = conn.execute(
        """INSERT INTO precon_match_records
           (season_id, pairing_id, reporter_id, winner_id, winner_display_name,
            loser_id, loser_display_name, winner_precon, loser_precon, timestamp, source,
            first_player, winner_went_first, loser_went_first, match_time, match_comment,
            winner_rating_before, winner_rating_after, loser_rating_before, loser_rating_after,
            replay_url)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            season_id, pairing_id, reporter_id, winner_id, winner_name, loser_id, loser_name,
            winner_precon, loser_precon, at, source, first_player, winner_went_first,
            loser_went_first, match_time, match_comment, before_w, after_w, before_l, after_l,
            replay_url or None,
        ),
    )
    match_id = cur.lastrowid
    if season_id is not None:
        _save_result(conn, season_id, winner_id, winner_name, w1, True, winner_precon)
        _save_result(conn, season_id, loser_id, loser_name, l1, False, loser_precon)
    conn.commit()
    return {
        "match_id": match_id,
        "season_id": season_id,
        "season_name": season["name"] if season else None,
        "rated": season_id is not None,
        "winner_before": before_w,
        "winner_after": after_w,
        "loser_before": before_l,
        "loser_after": after_l,
    }


def match_for_pairing(conn, pairing_id) -> dict | None:
    """The live game already saved for this queue pairing, if any."""
    ensure_schema(conn)
    cur = conn.execute(
        "SELECT * FROM precon_match_records WHERE pairing_id = ? AND removed = 0 ORDER BY match_id DESC LIMIT 1",
        (pairing_id,),
    )
    row = cur.fetchone()
    return _row(cur, row) if row else None


def get_match(conn, match_id) -> dict | None:
    ensure_schema(conn)
    cur = conn.execute("SELECT * FROM precon_match_records WHERE match_id = ?", (match_id,))
    row = cur.fetchone()
    return _row(cur, row) if row else None


def rebuild_season(conn, season_id) -> int:
    """Re-rate a whole season from its games, in order. Returns the game count."""
    ensure_schema(conn)
    conn.execute("DELETE FROM precon_ratings WHERE season_id = ?", (season_id,))
    cur = conn.execute(
        """SELECT * FROM precon_match_records
           WHERE season_id = ? AND removed = 0 ORDER BY timestamp, match_id""",
        (season_id,),
    )
    games = [_row(cur, r) for r in cur.fetchall()]
    for game in games:
        w0 = _load_rating(conn, season_id, game["winner_id"])
        l0 = _load_rating(conn, season_id, game["loser_id"])
        w1, l1 = play(w0, l0, game["timestamp"])
        conn.execute(
            """UPDATE precon_match_records SET winner_rating_before = ?, winner_rating_after = ?,
                   loser_rating_before = ?, loser_rating_after = ? WHERE match_id = ?""",
            (w0.display, w1.display, l0.display, l1.display, game["match_id"]),
        )
        _save_result(conn, season_id, game["winner_id"], game["winner_display_name"], w1, True,
                     game["winner_precon"])
        _save_result(conn, season_id, game["loser_id"], game["loser_display_name"], l1, False,
                     game["loser_precon"])
    conn.commit()
    return len(games)


def remove_match(conn, match_id) -> dict | None:
    """Take a game off the ladder and re-rate its season. Returns the game, or None."""
    game = get_match(conn, match_id)
    if not game or game["removed"]:
        return None
    conn.execute("UPDATE precon_match_records SET removed = 1 WHERE match_id = ?", (match_id,))
    conn.commit()
    if game["season_id"] is not None:
        rebuild_season(conn, game["season_id"])
    return game


def played_last_game_together(conn, player_a, player_b) -> bool:
    """True when either player's most recent precon game was against the other."""
    ensure_schema(conn)
    for player in (int(player_a), int(player_b)):
        row = conn.execute(
            """SELECT winner_id, loser_id FROM precon_match_records
               WHERE removed = 0 AND (winner_id = ? OR loser_id = ?)
               ORDER BY timestamp DESC, match_id DESC LIMIT 1""",
            (player, player),
        ).fetchone()
        if row and {int(player_a), int(player_b)} == {int(row[0]), int(row[1])}:
            return True
    return False


# --- Standings --------------------------------------------------------------


def standings(conn, season_id) -> list[dict]:
    """Every player on the season, best rating first; ``rank`` only for ranked players."""
    ensure_schema(conn)
    cur = conn.execute(
        "SELECT * FROM precon_ratings WHERE season_id = ? ORDER BY rating DESC, games DESC",
        (season_id,),
    )
    rows = [_row(cur, r) for r in cur.fetchall()]
    needed = min_ranked_games(conn)
    rank = 0
    out = []
    for row in rows:
        ranked = row["games"] >= needed
        if ranked:
            rank += 1
        out.append({
            "user_id": str(row["user_id"]),
            "name": row["display_name"] or str(row["user_id"]),
            "rating": int(round(row["rating"])),
            "rd": int(round(row["rd"])),
            "games": row["games"],
            "wins": row["wins"],
            "losses": row["losses"],
            "lm_wins": row["lm_wins"],
            "lm_losses": row["lm_losses"],
            "fm_wins": row["fm_wins"],
            "fm_losses": row["fm_losses"],
            "ranked": ranked,
            "rank": rank if ranked else None,
        })
    # Ranked players first, then everyone still short of the minimum
    return [r for r in out if r["ranked"]] + [r for r in out if not r["ranked"]]


def player_standing(conn, season_id, user_id) -> dict | None:
    for row in standings(conn, season_id):
        if row["user_id"] == str(user_id):
            return row
    return None


def season_stats(conn, season_id) -> dict:
    """Players, games and how Lavamancer has done against Frostmage this season."""
    ensure_schema(conn)
    games = conn.execute(
        "SELECT COUNT(*) FROM precon_match_records WHERE season_id = ? AND removed = 0",
        (season_id,),
    ).fetchone()[0]
    players = conn.execute(
        "SELECT COUNT(*) FROM precon_ratings WHERE season_id = ?", (season_id,)
    ).fetchone()[0]
    matchup = {}
    for key in (LAVAMANCER, FROSTMAGE):
        other = FROSTMAGE if key == LAVAMANCER else LAVAMANCER
        matchup[key] = conn.execute(
            """SELECT COUNT(*) FROM precon_match_records
               WHERE season_id = ? AND removed = 0 AND winner_precon = ? AND loser_precon = ?""",
            (season_id, key, other),
        ).fetchone()[0]
    mirrors = {
        key: conn.execute(
            """SELECT COUNT(*) FROM precon_match_records
               WHERE season_id = ? AND removed = 0 AND winner_precon = ? AND loser_precon = ?""",
            (season_id, key, key),
        ).fetchone()[0]
        for key in (LAVAMANCER, FROSTMAGE)
    }
    return {
        "games": games,
        "players": players,
        "min_ranked_games": min_ranked_games(conn),
        "lm_vs_fm": {
            "lm_wins": matchup[LAVAMANCER],
            "fm_wins": matchup[FROSTMAGE],
            "lm_mirrors": mirrors[LAVAMANCER],
            "fm_mirrors": mirrors[FROSTMAGE],
        },
    }


def recent_matches(conn, season_id, limit=10) -> list[dict]:
    ensure_schema(conn)
    cur = conn.execute(
        """SELECT match_id, timestamp, winner_id, winner_display_name, loser_id, loser_display_name,
                  winner_precon, loser_precon, winner_rating_before, winner_rating_after,
                  loser_rating_before, loser_rating_after
           FROM precon_match_records WHERE season_id = ? AND removed = 0
           ORDER BY timestamp DESC, match_id DESC LIMIT ?""",
        (season_id, int(limit)),
    )
    out = []
    for r in cur.fetchall():
        row = _row(cur, r)
        for key in ("winner_id", "loser_id"):
            row[key] = str(row[key])
        out.append(row)
    return out


def player_summary(conn, user_id, game_limit=20) -> dict:
    """One player's precon ladders (newest first, with their standing) and latest games."""
    ensure_schema(conn)
    user_id = int(user_id)
    seasons = []
    for season in list_seasons(conn):
        rows = standings(conn, season["season_id"])
        mine = next((r for r in rows if r["user_id"] == str(user_id)), None)
        if mine:
            seasons.append({
                "season": season,
                "standing": mine,
                "ranked_players": sum(1 for r in rows if r["ranked"]),
            })
    cur = conn.execute(
        """SELECT match_id, season_id, timestamp, winner_id, winner_display_name, loser_id,
                  loser_display_name, winner_precon, loser_precon, winner_rating_before,
                  winner_rating_after, loser_rating_before, loser_rating_after, replay_url,
                  winner_went_first, loser_went_first
           FROM precon_match_records
           WHERE removed = 0 AND (winner_id = ? OR loser_id = ?)
           ORDER BY timestamp DESC, match_id DESC LIMIT ?""",
        (user_id, user_id, int(game_limit)),
    )
    games = []
    for r in cur.fetchall():
        row = _row(cur, r)
        won = row["winner_id"] == user_id
        games.append({
            "match_id": row["match_id"],
            "season_id": row["season_id"],
            "timestamp": row["timestamp"],
            "won": won,
            "precon": row["winner_precon"] if won else row["loser_precon"],
            "opponent_id": str(row["loser_id"] if won else row["winner_id"]),
            "opponent_name": row["loser_display_name"] if won else row["winner_display_name"],
            "opponent_precon": row["loser_precon"] if won else row["winner_precon"],
            "rating_before": row["winner_rating_before"] if won else row["loser_rating_before"],
            "rating_after": row["winner_rating_after"] if won else row["loser_rating_after"],
            "went_first": row["winner_went_first"] if won else row["loser_went_first"],
            "replay_url": row["replay_url"],
            "winner_id": str(row["winner_id"]),
            "loser_id": str(row["loser_id"]),
        })
    return {"seasons": seasons, "games": games, "min_ranked_games": min_ranked_games(conn)}
