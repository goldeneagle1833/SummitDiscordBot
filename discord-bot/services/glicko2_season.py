"""Glicko-2 season ratings (Season 9 on).

A season is rated with Elo or Glicko-2, chosen when it starts and locked from
then on (``events.rating_system``). Elo seasons, paper and Limited ratings are
untouched by this module.

How a Glicko-2 season is stored:

- ``overall_standings``: each player's season rating (``online_event_rating``,
  ``online_event_rd``, ``online_event_vol``, ``online_event_last_at``).
  ``online_event_elo`` keeps holding the rounded rating, so every leaderboard
  that already reads it shows the Glicko-2 number unchanged.
- ``event_avatar_standings`` (Avatar mode): the same per (player, avatar)
  entry (``rating``, ``rd``, ``vol``), with ``event_elo`` the rounded rating.
- ``season_match_records`` (created when the first Glicko-2 season starts;
  see ``create_season_match_table``): every match from then on, never
  archived. Each rated match carries ``event_id`` and
  ``rating_system = 'glicko2'``. Its ``*_elo_change`` / ``*_avatar_elo_*``
  columns hold the change in the rounded rating, so they add up to the
  number on the leaderboard.
- ``event_rating_adjustments``: admin spot resets, replayed at their time.

The lifetime ladder moves to Glicko-2 too when the first Glicko-2 season starts
(``freeze_lifetime``): everyone's Elo lifetime is kept in
``overall_standings.legacy_online_elo`` ("Legacy ELO, Seasons 1-8") and
lifetime restarts at 1500. From then on ``online_elo`` is the rounded Glicko-2
lifetime rating (``online_rating`` / ``online_rd`` / ``online_vol``), rated
across seasons from every match marked ``lifetime_system = 'glicko2'``, and
rebuilt the same way after a fix (``rebuild_lifetime``). Ladder challenge
stakes scale the rating move (``*_lifetime_mult``).

Recording a match updates the two entries in place (``apply_match``). Anything
that changes the past (removing, correcting, removing a player) rebuilds the
whole season from its matches (``rebuild_season``): a Glicko-2 result can't be
undone by subtracting it, because every later game depends on it. Both give
the same numbers, since the replay walks the same matches at the same times.

This file is kept identical in discord-bot/services and web-app/services
(the web app can't import the bot); a test checks that the copies match.
"""

from __future__ import annotations

import datetime
import math
import sqlite3
from dataclasses import dataclass

ELO = "elo"
GLICKO2 = "glicko2"
RATING_SYSTEMS = (ELO, GLICKO2)

START_RATING = 1500.0
START_RD = 200.0       # new entries move fast for their first games
RD_FLOOR = 80.0        # ratings never go stiff late in the season
START_VOL = 0.06
TAU = 0.5
PERIOD_DAYS = 1.0      # uncertainty grows a little for each day without games
TOP_CUT_MIN_GAMES = 8  # an entry needs this many games to count for top cut
# Until then the entry is provisional: its rating and its per-game changes are
# not shown (they swing a lot while it settles). The rating shows from this
# game on, and per-game changes from the game after it.
PROVISIONAL_GAMES = TOP_CUT_MIN_GAMES

_SCALE = 173.7178
_NON_RATED_TYPES = ("testing", "rumble", "points")
_NON_SEASON_SOURCES = ("Bracket",)


@dataclass
class Rating:
    rating: float = START_RATING
    rd: float = START_RD
    vol: float = START_VOL
    last_at: str | None = None  # ISO time of the last game (or reset)

    @property
    def display(self) -> int:
        return int(round(self.rating))


def _parse(ts: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(str(ts).replace("Z", ""))


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


def win_chance(a: Rating, b: Rating, at: str) -> float:
    """Chance that ``a`` beats ``b`` at ``at``."""
    phi = math.hypot(rd_at(a, at), rd_at(b, at)) / _SCALE
    return 1 / (1 + math.exp(-_g(phi) * (a.rating - b.rating) / _SCALE))


# --- Schema ---------------------------------------------------------------


def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _table_exists(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _add_columns(conn, table, columns):
    if not _table_exists(conn, table):
        return
    have = _columns(conn, table)
    for name, decl in columns:
        if name not in have:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def ensure_elo_schema(conn: sqlite3.Connection) -> None:
    """Add the rating-system setting, its lock and the Glicko-2 columns to elo.db."""
    if _table_exists(conn, "events"):
        if "rating_system" not in _columns(conn, "events"):
            conn.execute(
                "ALTER TABLE events ADD COLUMN rating_system TEXT NOT NULL DEFAULT 'elo' "
                "CHECK (rating_system IN ('elo', 'glicko2'))"
            )
        conn.execute(
            """CREATE TRIGGER IF NOT EXISTS events_rating_system_locked
               BEFORE UPDATE OF rating_system ON events
               WHEN OLD.rating_system IS NOT NEW.rating_system
               BEGIN
                   SELECT RAISE(ABORT, 'rating_system cannot change after an event starts');
               END"""
        )
    _add_columns(conn, "overall_standings", (
        ("online_event_games", "INTEGER DEFAULT 0"),  # the bot's own migration adds it too
        ("online_event_rating", "REAL"),
        ("online_event_rd", "REAL"),
        ("online_event_vol", "REAL"),
        ("online_event_last_at", "TEXT"),
    ))
    ensure_lifetime_schema(conn)
    _add_columns(conn, "event_avatar_standings", (
        ("rating", "REAL"),
        ("rd", "REAL"),
        ("vol", "REAL"),
    ))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS event_rating_adjustments (
               adjustment_id INTEGER PRIMARY KEY AUTOINCREMENT,
               event_id      INTEGER NOT NULL,
               user_id       INTEGER NOT NULL,
               avatar        TEXT,
               rating        REAL    NOT NULL,
               created_at    TEXT    NOT NULL
           )"""
    )


# Seasons 1-8 live in match_records / match_records_archive and never change.
# The first Glicko-2 season creates SEASON_MATCH_TABLE; from then on every
# new match goes there (tagged with its event) and is never archived.
LEGACY_MATCH_TABLE = "match_records"
SEASON_MATCH_TABLE = "season_match_records"


def live_match_table(conn: sqlite3.Connection) -> str:
    """The table current matches are read from and written to."""
    return SEASON_MATCH_TABLE if _table_exists(conn, SEASON_MATCH_TABLE) else LEGACY_MATCH_TABLE


def ensure_match_schema(conn: sqlite3.Connection) -> None:
    """Add the season and rating-system columns, and keep the season table in step."""
    _add_columns(conn, LEGACY_MATCH_TABLE, (
        ("event_id", "INTEGER"),
        ("rating_system", "TEXT"),
        ("winner_lifetime_elo_change", "INTEGER"),
        ("loser_lifetime_elo_change", "INTEGER"),
        # Lifetime on Glicko-2 (from the first Glicko-2 season): which rows it
        # replays, and the ladder challenge stakes each side played at
        ("lifetime_system", "TEXT"),
        ("winner_lifetime_mult", "REAL"),
        ("loser_lifetime_mult", "REAL"),
        # Each side's game count after this match (Glicko-2 ladders only), so
        # a change made while still provisional can be kept out of sight
        ("winner_event_games", "INTEGER"),
        ("loser_event_games", "INTEGER"),
        ("winner_avatar_games", "INTEGER"),
        ("loser_avatar_games", "INTEGER"),
        ("winner_lifetime_games", "INTEGER"),
        ("loser_lifetime_games", "INTEGER"),
    ))
    if _table_exists(conn, LEGACY_MATCH_TABLE):
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_match_records_event ON match_records (event_id, rating_system)"
        )
    sync_season_match_table(conn)


def sync_season_match_table(conn: sqlite3.Connection) -> None:
    """Give the season table every column and index match_records has.

    Column migrations are written against match_records; this repeats them
    on the season table so both always have the same layout.
    """
    if not (_table_exists(conn, SEASON_MATCH_TABLE) and _table_exists(conn, LEGACY_MATCH_TABLE)):
        return
    have = _columns(conn, SEASON_MATCH_TABLE)
    for row in conn.execute(f"PRAGMA table_info({LEGACY_MATCH_TABLE})").fetchall():
        name, decl = row[1], row[2] or ""
        if name not in have:
            conn.execute(f"ALTER TABLE {SEASON_MATCH_TABLE} ADD COLUMN {name} {decl}")
    indexes = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type = 'index' AND tbl_name = ? AND sql IS NOT NULL",
        (LEGACY_MATCH_TABLE,),
    ).fetchall()
    for name, sql in indexes:
        new_name = f"season_{name}"
        conn.execute(
            sql.replace(f"INDEX {name}", f"INDEX IF NOT EXISTS {new_name}", 1)
               .replace(f"INDEX IF NOT EXISTS {name}", f"INDEX IF NOT EXISTS {new_name}", 1)
               .replace(f" ON {LEGACY_MATCH_TABLE}", f" ON {SEASON_MATCH_TABLE}", 1)
        )


def create_season_match_table(conn: sqlite3.Connection) -> bool:
    """Create the Season 9+ match table (once). Returns True if it was created now.

    Same layout as match_records. Match ids continue above every id used so
    far (live and archived), so a match number never points at two games.
    Rows still in match_records at this point (games reported between seasons,
    after the last Elo season was archived) move across with their ids.
    Does not commit.
    """
    if _table_exists(conn, SEASON_MATCH_TABLE):
        return False
    ensure_match_schema(conn)
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (LEGACY_MATCH_TABLE,)
    ).fetchone()[0]
    head, rest = sql.split("(", 1)
    conn.execute(f"CREATE TABLE {SEASON_MATCH_TABLE} ({rest}")

    top = conn.execute(f"SELECT COALESCE(MAX(rowid), 0) FROM {LEGACY_MATCH_TABLE}").fetchone()[0]
    if _table_exists(conn, "match_records_archive") and "original_match_id" in _columns(
        conn, "match_records_archive"
    ):
        archived = conn.execute(
            "SELECT COALESCE(MAX(original_match_id), 0) FROM match_records_archive"
        ).fetchone()[0]
        top = max(top, archived or 0)
    if _table_exists(conn, "sqlite_sequence"):
        seq = conn.execute(
            "SELECT seq FROM sqlite_sequence WHERE name = ?", (LEGACY_MATCH_TABLE,)
        ).fetchone()
        top = max(top, seq[0] if seq else 0)
        if "AUTOINCREMENT" in rest.upper():
            conn.execute("DELETE FROM sqlite_sequence WHERE name = ?", (SEASON_MATCH_TABLE,))
            conn.execute(
                "INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)", (SEASON_MATCH_TABLE, top)
            )

    info = conn.execute(f"PRAGMA table_info({LEGACY_MATCH_TABLE})").fetchall()
    cols = ", ".join(row[1] for row in info)
    # Keep each row's id: copy rowid unless a column already is the rowid
    has_rowid_alias = any(row[5] and (row[2] or "").upper() == "INTEGER" for row in info)
    ids = "" if has_rowid_alias else "rowid, "
    conn.execute(
        f"INSERT INTO {SEASON_MATCH_TABLE} ({ids}{cols}) SELECT {ids}{cols} FROM {LEGACY_MATCH_TABLE}"
    )
    conn.execute(f"DELETE FROM {LEGACY_MATCH_TABLE}")
    sync_season_match_table(conn)
    return True


# --- Reading and writing one entry ------------------------------------------


def get_event(elo_conn: sqlite3.Connection, event_id: int | None = None) -> dict | None:
    """An event (the active one by default) with its mode and rating system."""
    cols = _columns(elo_conn, "events")
    system = "rating_system" if "rating_system" in cols else "'elo'"
    mode = "elo_mode" if "elo_mode" in cols else "'player'"
    where = "event_id = ?" if event_id is not None else "is_active = 1"
    row = elo_conn.execute(
        f"SELECT event_id, event_name, start_date, end_date, {mode}, {system} FROM events "
        f"WHERE {where} ORDER BY event_id DESC LIMIT 1",
        (event_id,) if event_id is not None else (),
    ).fetchone()
    if not row:
        return None
    return {
        "event_id": row[0], "event_name": row[1], "start_date": row[2], "end_date": row[3],
        "elo_mode": row[4] or "player", "rating_system": row[5] or ELO,
    }


def is_glicko2(event: dict | None) -> bool:
    return bool(event) and event.get("rating_system") == GLICKO2


def is_provisional(games) -> bool:
    """A Glicko-2 entry with fewer than PROVISIONAL_GAMES games: rating not shown."""
    return (games or 0) < PROVISIONAL_GAMES


def change_hidden(games_after) -> bool:
    """A match change made while that side was provisional (Glicko-2 rows only).

    ``games_after`` is the side's game count after the match, stored on the
    row; None (Elo rows, older rows) is always shown.
    """
    return games_after is not None and games_after <= PROVISIONAL_GAMES


def provisional_label(games) -> str:
    return f"Provisional ({min(games or 0, PROVISIONAL_GAMES)}/{PROVISIONAL_GAMES})"


def load_player(elo_conn, user_id) -> Rating:
    row = elo_conn.execute(
        "SELECT online_event_rating, online_event_rd, online_event_vol, online_event_last_at "
        "FROM overall_standings WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if not row or row[0] is None:
        return Rating()
    return Rating(row[0], row[1] or START_RD, row[2] or START_VOL, row[3])


def load_avatar(elo_conn, event_id, user_id, avatar) -> Rating:
    row = elo_conn.execute(
        "SELECT rating, rd, vol, last_played_at FROM event_avatar_standings "
        "WHERE event_id = ? AND user_id = ? AND avatar = ?",
        (event_id, user_id, avatar),
    ).fetchone()
    if not row or row[0] is None:
        return Rating()
    return Rating(row[0], row[1] or START_RD, row[2] or START_VOL, row[3])


def _save_player(elo_conn, user_id, name, entry: Rating, games_delta=1):
    elo_conn.execute(
        "INSERT OR IGNORE INTO overall_standings (user_id, user_display_name) VALUES (?, ?)",
        (user_id, name),
    )
    elo_conn.execute(
        """UPDATE overall_standings SET
               online_event_elo = ?, online_event_rating = ?, online_event_rd = ?,
               online_event_vol = ?, online_event_last_at = ?,
               online_event_games = COALESCE(online_event_games, 0) + ?,
               user_display_name = COALESCE(?, user_display_name)
           WHERE user_id = ?""",
        (entry.display, entry.rating, entry.rd, entry.vol, entry.last_at, games_delta, name, user_id),
    )


def _save_avatar(elo_conn, event_id, user_id, name, avatar, entry: Rating, games_delta=1):
    elo_conn.execute(
        """INSERT INTO event_avatar_standings
               (event_id, user_id, avatar, user_display_name, event_elo, games_played,
                last_played_at, rating, rd, vol)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (event_id, user_id, avatar) DO UPDATE SET
               event_elo = excluded.event_elo,
               user_display_name = COALESCE(excluded.user_display_name, user_display_name),
               games_played = games_played + ?,
               last_played_at = excluded.last_played_at,
               rating = excluded.rating, rd = excluded.rd, vol = excluded.vol""",
        (event_id, user_id, avatar, name, entry.display, games_delta, entry.last_at,
         entry.rating, entry.rd, entry.vol, games_delta),
    )


def apply_match(elo_conn, event, winner_id, winner_name, loser_id, loser_name, at,
                winner_avatar=None, loser_avatar=None) -> dict:
    """Rate one new match in place and return its changes for the match record.

    Updates the player ladder always, and the two avatar entries when both
    avatars are known in an Avatar-mode season. Does not commit.
    """
    w_before, l_before = load_player(elo_conn, winner_id), load_player(elo_conn, loser_id)
    w_after, l_after = play(w_before, l_before, at)
    _save_player(elo_conn, winner_id, winner_name, w_after)
    _save_player(elo_conn, loser_id, loser_name, l_after)
    out = {
        "winner_change": w_after.display - w_before.display,
        "loser_change": l_after.display - l_before.display,
        "winner_rating": w_after.display,
        "loser_rating": l_after.display,
        "winner_games": _player_games(elo_conn, winner_id),
        "loser_games": _player_games(elo_conn, loser_id),
        "winner_avatar_change": None, "loser_avatar_change": None,
        "winner_avatar_after": None, "loser_avatar_after": None,
        "winner_avatar_games": None, "loser_avatar_games": None,
    }
    if event.get("elo_mode") == "avatar" and winner_avatar and loser_avatar:
        eid = event["event_id"]
        wa_before = load_avatar(elo_conn, eid, winner_id, winner_avatar)
        la_before = load_avatar(elo_conn, eid, loser_id, loser_avatar)
        wa_after, la_after = play(wa_before, la_before, at)
        _save_avatar(elo_conn, eid, winner_id, winner_name, winner_avatar, wa_after)
        _save_avatar(elo_conn, eid, loser_id, loser_name, loser_avatar, la_after)
        out.update({
            "winner_avatar_change": wa_after.display - wa_before.display,
            "loser_avatar_change": la_after.display - la_before.display,
            "winner_avatar_after": wa_after.display,
            "loser_avatar_after": la_after.display,
            "winner_avatar_games": _avatar_games(elo_conn, eid, winner_id, winner_avatar),
            "loser_avatar_games": _avatar_games(elo_conn, eid, loser_id, loser_avatar),
        })
    return out


def _player_games(elo_conn, user_id) -> int:
    row = elo_conn.execute(
        "SELECT online_event_games FROM overall_standings WHERE user_id = ?", (user_id,)
    ).fetchone()
    return (row[0] or 0) if row else 0


def _avatar_games(elo_conn, event_id, user_id, avatar) -> int:
    row = elo_conn.execute(
        "SELECT games_played FROM event_avatar_standings WHERE event_id = ? AND user_id = ? AND avatar = ?",
        (event_id, user_id, avatar),
    ).fetchone()
    return (row[0] or 0) if row else 0


def add_adjustment(elo_conn, event, user_id, name, rating, avatar=None, at=None) -> None:
    """An admin spot reset: set an entry's rating, uncertainty back to the start value.

    Stored so a later season rebuild applies it again at the same point.
    Does not commit.
    """
    at = at or datetime.datetime.now().isoformat()
    elo_conn.execute(
        "INSERT INTO event_rating_adjustments (event_id, user_id, avatar, rating, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (event["event_id"], user_id, avatar, float(rating), at),
    )
    entry = Rating(float(rating), START_RD, START_VOL, at)
    if avatar:
        _save_avatar(elo_conn, event["event_id"], user_id, name, avatar, entry, games_delta=0)
    else:
        _save_player(elo_conn, user_id, name, entry, games_delta=0)


# --- Rebuilding a season -----------------------------------------------------


def season_matches(match_conn, event) -> list[dict]:
    """The season's rated Glicko-2 matches, oldest first."""
    conn_factory = match_conn.row_factory
    match_conn.row_factory = sqlite3.Row
    try:
        params = [event["event_id"]]
        rows = match_conn.execute(
            f"""SELECT rowid AS row_id, winner_id, losser_id, winner_display_name,
                       losser_display_name, timestamp, winner_avatar, loser_avatar
                FROM {live_match_table(match_conn)}
                WHERE event_id = ? AND rating_system = '{GLICKO2}'
                  AND (match_type IS NULL OR match_type NOT IN
                       ({", ".join(f"'{t}'" for t in _NON_RATED_TYPES)}))
                  AND (source IS NULL OR source NOT IN
                       ({", ".join(f"'{s}'" for s in _NON_SEASON_SOURCES)}))
                ORDER BY timestamp ASC, rowid ASC""",
            params,
        ).fetchall()
    finally:
        match_conn.row_factory = conn_factory
    return [dict(r) for r in rows]


def rebuild_season(elo_conn, match_conn, event) -> dict:
    """Replay a Glicko-2 season from its matches and admin resets, and rewrite it.

    Rewrites every player's season rating, the season's avatar entries and
    each match's change columns. Does not commit either connection.
    Returns {"matches": n, "players": n, "entries": n, "moved": {key: (before, after)}}.
    """
    if not is_glicko2(event):
        raise ValueError("rebuild_season only rebuilds Glicko-2 seasons")
    event_id = event["event_id"]
    avatar_mode = event.get("elo_mode") == "avatar"
    matches = season_matches(match_conn, event)
    adjustments = elo_conn.execute(
        "SELECT user_id, avatar, rating, created_at FROM event_rating_adjustments "
        "WHERE event_id = ? ORDER BY created_at, adjustment_id",
        (event_id,),
    ).fetchall()

    # Merge matches and resets into one timeline (a reset at the same moment goes first)
    timeline = [(str(a[3]), 0, i, "adj", a) for i, a in enumerate(adjustments)]
    timeline += [(str(m["timestamp"]), 1, i, "match", m) for i, m in enumerate(matches)]
    timeline.sort(key=lambda item: (item[0], item[1], item[2]))

    players: dict[int, Rating] = {}
    avatars: dict[tuple[int, str], Rating] = {}
    player_games: dict[int, int] = {}
    avatar_games: dict[tuple[int, str], int] = {}
    names: dict[int, str] = {}
    match_updates = []
    for at, _, _, kind, item in timeline:
        if kind == "adj":
            user_id, avatar, rating, created_at = item
            fresh = Rating(float(rating), START_RD, START_VOL, created_at)
            if avatar:
                avatars[(user_id, avatar)] = fresh
            else:
                players[user_id] = fresh
            continue
        m = item
        w, l = m["winner_id"], m["losser_id"]
        names[w], names[l] = m["winner_display_name"], m["losser_display_name"]
        w_before, l_before = players.get(w, Rating()), players.get(l, Rating())
        players[w], players[l] = play(w_before, l_before, m["timestamp"])
        player_games[w] = player_games.get(w, 0) + 1
        player_games[l] = player_games.get(l, 0) + 1
        change = [players[w].display - w_before.display, players[l].display - l_before.display,
                  None, None, None, None, player_games[w], player_games[l], None, None]
        if avatar_mode and m["winner_avatar"] and m["loser_avatar"]:
            wk, lk = (w, m["winner_avatar"]), (l, m["loser_avatar"])
            wa_before, la_before = avatars.get(wk, Rating()), avatars.get(lk, Rating())
            avatars[wk], avatars[lk] = play(wa_before, la_before, m["timestamp"])
            avatar_games[wk] = avatar_games.get(wk, 0) + 1
            avatar_games[lk] = avatar_games.get(lk, 0) + 1
            change[2:6] = [avatars[wk].display - wa_before.display, avatars[lk].display - la_before.display,
                           avatars[wk].display, avatars[lk].display]
            change[8:10] = [avatar_games[wk], avatar_games[lk]]
        match_updates.append((*change, m["row_id"]))

    # event_k is the Elo K a match was played at; a Glicko-2 match has none
    table = live_match_table(match_conn)
    clear_k = ", event_k = NULL" if "event_k" in _columns(match_conn, table) else ""
    match_conn.executemany(
        f"UPDATE {table} SET winner_elo_change = ?, loser_elo_change = ?, "
        "winner_avatar_elo_change = ?, loser_avatar_elo_change = ?, "
        f"winner_avatar_elo_after = ?, loser_avatar_elo_after = ?, "
        "winner_event_games = ?, loser_event_games = ?, "
        f"winner_avatar_games = ?, loser_avatar_games = ?{clear_k} WHERE rowid = ?",
        match_updates,
    )

    # Player ladder: everyone back to the start, then the replayed ratings
    before = {
        uid: elo for uid, elo in elo_conn.execute(
            "SELECT user_id, online_event_elo FROM overall_standings"
        ).fetchall()
    }
    elo_conn.execute(
        "UPDATE overall_standings SET online_event_elo = 1500, online_event_games = 0, "
        "online_event_rating = NULL, online_event_rd = NULL, online_event_vol = NULL, "
        "online_event_last_at = NULL"
    )
    for uid, entry in players.items():
        elo_conn.execute(
            "INSERT OR IGNORE INTO overall_standings (user_id, user_display_name) VALUES (?, ?)",
            (uid, names.get(uid)),
        )
        elo_conn.execute(
            """UPDATE overall_standings SET online_event_elo = ?, online_event_games = ?,
                   online_event_rating = ?, online_event_rd = ?, online_event_vol = ?,
                   online_event_last_at = ?
               WHERE user_id = ?""",
            (entry.display, player_games.get(uid, 0), entry.rating, entry.rd, entry.vol,
             entry.last_at, uid),
        )
    moved = {
        uid: (before.get(uid, 1500), entry.display)
        for uid, entry in players.items()
        if before.get(uid, 1500) != entry.display
    }

    if avatar_mode:
        avatar_names = {
            (row[0], row[1]): row[2] for row in elo_conn.execute(
                "SELECT user_id, avatar, user_display_name FROM event_avatar_standings WHERE event_id = ?",
                (event_id,),
            ).fetchall()
        }
        elo_conn.execute("DELETE FROM event_avatar_standings WHERE event_id = ?", (event_id,))
        elo_conn.executemany(
            """INSERT INTO event_avatar_standings
                   (event_id, user_id, avatar, user_display_name, event_elo, games_played,
                    last_played_at, rating, rd, vol)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (event_id, uid, avatar, names.get(uid) or avatar_names.get((uid, avatar)),
                 entry.display, avatar_games.get((uid, avatar), 0), entry.last_at,
                 entry.rating, entry.rd, entry.vol)
                for (uid, avatar), entry in avatars.items()
            ],
        )

    return {
        "matches": len(matches),
        "players": len(players),
        "entries": len(avatars) if avatar_mode else len(players),
        "moved": moved,
    }


# --- Lifetime ladder ---------------------------------------------------------

LIFETIME_SETTING = "lifetime_rating_system"
LIFETIME_SINCE_SETTING = "lifetime_glicko2_since"


def ensure_lifetime_schema(conn: sqlite3.Connection) -> None:
    _add_columns(conn, "overall_standings", (
        ("legacy_online_elo", "INTEGER"),  # Elo lifetime frozen at the switch (Seasons 1-8)
        ("online_rating", "REAL"),
        ("online_rd", "REAL"),
        ("online_vol", "REAL"),
        ("online_last_at", "TEXT"),
        ("online_games", "INTEGER DEFAULT 0"),
    ))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS rating_settings (key TEXT PRIMARY KEY, value TEXT)"
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS lifetime_rating_adjustments (
               adjustment_id INTEGER PRIMARY KEY AUTOINCREMENT,
               user_id       INTEGER NOT NULL,
               rating        REAL    NOT NULL,
               created_at    TEXT    NOT NULL
           )"""
    )


def _setting(elo_conn, key):
    if not _table_exists(elo_conn, "rating_settings"):
        return None
    row = elo_conn.execute("SELECT value FROM rating_settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def lifetime_is_glicko2(elo_conn: sqlite3.Connection) -> bool:
    """True once the lifetime ladder has moved to Glicko-2 (first Glicko-2 season on)."""
    return _setting(elo_conn, LIFETIME_SETTING) == GLICKO2


def freeze_lifetime(elo_conn: sqlite3.Connection, at: str | None = None) -> bool:
    """Keep everyone's Elo lifetime as Legacy ELO and restart lifetime at 1500 on Glicko-2.

    Runs once, when the first Glicko-2 season starts. Returns True if it ran now.
    Does not commit.
    """
    ensure_lifetime_schema(elo_conn)
    if lifetime_is_glicko2(elo_conn):
        return False
    at = at or datetime.datetime.now().isoformat()
    if _table_exists(elo_conn, "overall_standings"):
        elo_conn.execute(
            """UPDATE overall_standings SET
                   legacy_online_elo = COALESCE(online_elo, 1500),
                   online_elo = 1500, online_rating = NULL, online_rd = NULL,
                   online_vol = NULL, online_last_at = NULL, online_games = 0"""
        )
    elo_conn.executemany(
        "INSERT OR REPLACE INTO rating_settings (key, value) VALUES (?, ?)",
        ((LIFETIME_SETTING, GLICKO2), (LIFETIME_SINCE_SETTING, at)),
    )
    return True


def load_lifetime(elo_conn, user_id) -> Rating:
    row = elo_conn.execute(
        "SELECT online_rating, online_rd, online_vol, online_last_at FROM overall_standings "
        "WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if not row or row[0] is None:
        return Rating()
    return Rating(row[0], row[1] or START_RD, row[2] or START_VOL, row[3])


def _save_lifetime(elo_conn, user_id, name, entry: Rating, games_delta=1):
    elo_conn.execute(
        "INSERT OR IGNORE INTO overall_standings (user_id, user_display_name) VALUES (?, ?)",
        (user_id, name),
    )
    elo_conn.execute(
        """UPDATE overall_standings SET
               online_elo = ?, online_rating = ?, online_rd = ?, online_vol = ?,
               online_last_at = ?, online_games = COALESCE(online_games, 0) + ?,
               user_display_name = COALESCE(?, user_display_name)
           WHERE user_id = ?""",
        (entry.display, entry.rating, entry.rd, entry.vol, entry.last_at, games_delta, name, user_id),
    )


def _staked(before: Rating, after: Rating, mult) -> Rating:
    """A ladder challenge's stakes scale how far the rating moves."""
    if mult is None or mult == 1:
        return after
    return Rating(before.rating + (after.rating - before.rating) * mult, after.rd, after.vol, after.last_at)


def play_lifetime(w_before: Rating, l_before: Rating, at: str, winner_mult=1.0, loser_mult=1.0):
    w_after, l_after = play(w_before, l_before, at)
    return _staked(w_before, w_after, winner_mult), _staked(l_before, l_after, loser_mult)


def apply_lifetime_match(elo_conn, winner_id, winner_name, loser_id, loser_name, at,
                         winner_mult=1.0, loser_mult=1.0) -> dict:
    """Rate one new match on the Glicko-2 lifetime ladder. Does not commit.

    The caller marks the match row ``lifetime_system = 'glicko2'`` with the
    changes and multipliers returned, so a rebuild replays it.
    """
    w_before, l_before = load_lifetime(elo_conn, winner_id), load_lifetime(elo_conn, loser_id)
    w_after, l_after = play_lifetime(w_before, l_before, at, winner_mult, loser_mult)
    _save_lifetime(elo_conn, winner_id, winner_name, w_after)
    _save_lifetime(elo_conn, loser_id, loser_name, l_after)
    return {
        "winner_change": w_after.display - w_before.display,
        "loser_change": l_after.display - l_before.display,
        "winner_rating": w_after.display,
        "loser_rating": l_after.display,
        "winner_games": lifetime_games(elo_conn, winner_id),
        "loser_games": lifetime_games(elo_conn, loser_id),
    }


def lifetime_games(elo_conn, user_id) -> int:
    row = elo_conn.execute(
        "SELECT online_games FROM overall_standings WHERE user_id = ?", (user_id,)
    ).fetchone()
    return (row[0] or 0) if row else 0


def add_lifetime_adjustment(elo_conn, user_id, name, rating, at=None) -> None:
    """An admin reset of a Glicko-2 lifetime rating, kept so rebuilds apply it again."""
    at = at or datetime.datetime.now().isoformat()
    ensure_lifetime_schema(elo_conn)
    elo_conn.execute(
        "INSERT INTO lifetime_rating_adjustments (user_id, rating, created_at) VALUES (?, ?, ?)",
        (user_id, float(rating), at),
    )
    _save_lifetime(elo_conn, user_id, name, Rating(float(rating), START_RD, START_VOL, at), games_delta=0)


def lifetime_matches(match_conn) -> list[dict]:
    """Every match rated on the Glicko-2 lifetime ladder, oldest first."""
    table = live_match_table(match_conn)
    if "lifetime_system" not in _columns(match_conn, table):
        return []
    conn_factory = match_conn.row_factory
    match_conn.row_factory = sqlite3.Row
    try:
        rows = match_conn.execute(
            f"""SELECT rowid AS row_id, winner_id, losser_id, winner_display_name,
                       losser_display_name, timestamp, winner_lifetime_mult, loser_lifetime_mult
                FROM {table} WHERE lifetime_system = '{GLICKO2}'
                ORDER BY timestamp ASC, rowid ASC"""
        ).fetchall()
    finally:
        match_conn.row_factory = conn_factory
    return [dict(r) for r in rows]


def rebuild_lifetime(elo_conn, match_conn) -> dict:
    """Replay the Glicko-2 lifetime ladder from its matches and admin resets.

    Rewrites everyone's lifetime rating and each match's lifetime change.
    Legacy ELO is never touched. Does not commit.
    """
    if not lifetime_is_glicko2(elo_conn):
        raise ValueError("the lifetime ladder is still Elo")
    matches = lifetime_matches(match_conn)
    adjustments = elo_conn.execute(
        "SELECT user_id, rating, created_at FROM lifetime_rating_adjustments "
        "ORDER BY created_at, adjustment_id"
    ).fetchall()
    timeline = [(str(a[2]), 0, i, "adj", a) for i, a in enumerate(adjustments)]
    timeline += [(str(m["timestamp"]), 1, i, "match", m) for i, m in enumerate(matches)]
    timeline.sort(key=lambda item: (item[0], item[1], item[2]))

    players: dict[int, Rating] = {}
    games: dict[int, int] = {}
    names: dict[int, str] = {}
    updates = []
    for _, _, _, kind, item in timeline:
        if kind == "adj":
            user_id, rating, created_at = item
            players[user_id] = Rating(float(rating), START_RD, START_VOL, created_at)
            continue
        m = item
        w, l = m["winner_id"], m["losser_id"]
        names[w], names[l] = m["winner_display_name"], m["losser_display_name"]
        w_before, l_before = players.get(w, Rating()), players.get(l, Rating())
        players[w], players[l] = play_lifetime(
            w_before, l_before, m["timestamp"], m["winner_lifetime_mult"], m["loser_lifetime_mult"]
        )
        games[w] = games.get(w, 0) + 1
        games[l] = games.get(l, 0) + 1
        w_change = players[w].display - w_before.display
        l_change = players[l].display - l_before.display
        updates.append((w_change, l_change, players[w].display, players[l].display,
                        games[w], games[l], m["row_id"]))

    table = live_match_table(match_conn)
    cols = _columns(match_conn, table)
    if "winner_lifetime_elo_after" in cols:
        match_conn.executemany(
            f"UPDATE {table} SET winner_lifetime_elo_change = ?, loser_lifetime_elo_change = ?, "
            "winner_lifetime_elo_after = ?, loser_lifetime_elo_after = ?, "
            "winner_lifetime_games = ?, loser_lifetime_games = ? WHERE rowid = ?",
            updates,
        )
    else:
        match_conn.executemany(
            f"UPDATE {table} SET winner_lifetime_elo_change = ?, loser_lifetime_elo_change = ?, "
            "winner_lifetime_games = ?, loser_lifetime_games = ? WHERE rowid = ?",
            [(u[0], u[1], u[4], u[5], u[6]) for u in updates],
        )

    existing = {row[0] for row in elo_conn.execute("SELECT user_id FROM overall_standings")}
    elo_conn.execute(
        "UPDATE overall_standings SET online_elo = 1500, online_rating = NULL, online_rd = NULL, "
        "online_vol = NULL, online_last_at = NULL, online_games = 0"
    )
    for uid, entry in players.items():
        if uid not in existing and not games.get(uid):
            continue  # a removed player's reset alone doesn't bring them back
        elo_conn.execute(
            "INSERT OR IGNORE INTO overall_standings (user_id, user_display_name) VALUES (?, ?)",
            (uid, names.get(uid)),
        )
        elo_conn.execute(
            """UPDATE overall_standings SET online_elo = ?, online_rating = ?, online_rd = ?,
                   online_vol = ?, online_last_at = ?, online_games = ? WHERE user_id = ?""",
            (entry.display, entry.rating, entry.rd, entry.vol, entry.last_at, games.get(uid, 0), uid),
        )
    return {"matches": len(matches), "players": len(players)}


def rebuild_after_fix(elo_conn, match_conn, event) -> dict:
    """After any change to past matches: replay whatever is rated by Glicko-2.

    The running season (if it is a Glicko-2 season) and the lifetime ladder
    (once it is Glicko-2). Elo ladders are left to the caller. Does not commit.
    """
    out = {}
    if is_glicko2(event):
        out["season"] = rebuild_season(elo_conn, match_conn, event)
    if lifetime_is_glicko2(elo_conn):
        out["lifetime"] = rebuild_lifetime(elo_conn, match_conn)
    return out
