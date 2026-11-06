"""Glicko-2 season ratings (Season 9 on).

A season is rated with Elo or Glicko-2, chosen when it starts and locked from
then on (``events.rating_system``). Elo seasons, the lifetime ladder, paper and
Limited ratings are untouched by this module.

How a Glicko-2 season is stored:

- ``overall_standings``: each player's season rating (``online_event_rating``,
  ``online_event_rd``, ``online_event_vol``, ``online_event_last_at``).
  ``online_event_elo`` keeps holding the rounded rating, so every leaderboard
  that already reads it shows the Glicko-2 number unchanged.
- ``event_avatar_standings`` (Avatar mode): the same per (player, avatar)
  entry (``rating``, ``rd``, ``vol``), with ``event_elo`` the rounded rating.
- ``match_records``: each rated match carries ``event_id`` and
  ``rating_system = 'glicko2'``. Its ``*_elo_change`` / ``*_avatar_elo_*``
  columns hold the change in the rounded rating, so they add up to the
  number on the leaderboard.
- ``event_rating_adjustments``: admin spot resets, replayed at their time.

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


def ensure_match_schema(conn: sqlite3.Connection) -> None:
    """Add the season and rating-system columns to match_records."""
    _add_columns(conn, "match_records", (
        ("event_id", "INTEGER"),
        ("rating_system", "TEXT"),
    ))
    if _table_exists(conn, "match_records"):
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_match_records_event ON match_records (event_id, rating_system)"
        )


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
        "winner_avatar_change": None, "loser_avatar_change": None,
        "winner_avatar_after": None, "loser_avatar_after": None,
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
        })
    return out


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
                FROM match_records
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
                  None, None, None, None]
        if avatar_mode and m["winner_avatar"] and m["loser_avatar"]:
            wk, lk = (w, m["winner_avatar"]), (l, m["loser_avatar"])
            wa_before, la_before = avatars.get(wk, Rating()), avatars.get(lk, Rating())
            avatars[wk], avatars[lk] = play(wa_before, la_before, m["timestamp"])
            avatar_games[wk] = avatar_games.get(wk, 0) + 1
            avatar_games[lk] = avatar_games.get(lk, 0) + 1
            change[2:] = [avatars[wk].display - wa_before.display, avatars[lk].display - la_before.display,
                          avatars[wk].display, avatars[lk].display]
        match_updates.append((*change, m["row_id"]))

    # event_k is the Elo K a match was played at; a Glicko-2 match has none
    clear_k = ", event_k = NULL" if "event_k" in _columns(match_conn, "match_records") else ""
    match_conn.executemany(
        "UPDATE match_records SET winner_elo_change = ?, loser_elo_change = ?, "
        "winner_avatar_elo_change = ?, loser_avatar_elo_change = ?, "
        f"winner_avatar_elo_after = ?, loser_avatar_elo_after = ?{clear_k} WHERE rowid = ?",
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
