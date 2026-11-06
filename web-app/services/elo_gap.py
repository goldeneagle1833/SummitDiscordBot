"""Average ELO gap between the two players in online games, for the admin dashboard.

Each side's pre-match rating is its stored rating after the match minus the
change it took. Avatar seasons use the avatar entries' ratings; other games
fall back to lifetime ELO, since a player's event ELO before a match is not
stored on the record. Games missing either side's rating are skipped.
"""

PROVISIONAL_GAMES = 8  # same as services.glicko2_season.PROVISIONAL_GAMES

_AVATAR = ("winner_avatar_elo_after", "winner_avatar_elo_change",
           "loser_avatar_elo_after", "loser_avatar_elo_change")
_LIFETIME = ("winner_lifetime_elo_after", "winner_lifetime_elo_change",
             "loser_lifetime_elo_after", "loser_lifetime_elo_change")


def _gap_sql(cols):
    wa, wc, la, lc = cols
    return f"ABS(({wa} - {wc}) - ({la} - {lc}))", " AND ".join(f"{c} IS NOT NULL" for c in cols)


def pre_match_sql(columns):
    """(winner, loser) SQL for each side's pre-match rating, or None if the table can't say.

    Newer games store each side's rating just before the game
    (``*_avatar_before`` / ``*_event_before`` / ``*_lifetime_before``); a
    Glicko-2 rating from an entry's first 8 games is provisional and skipped.
    Older games fall back to the stored rating after the game minus its
    change: avatar ratings when the game has them, else lifetime, else NULL.
    """
    columns = set(columns)
    old_sources = [c for c in (_AVATAR, _LIFETIME) if set(c) <= columns]
    sides = []
    for side in ("winner", "loser"):
        whens = []

        def settled(kind):
            games = f"{side}_{kind}_games"
            return f" AND ({games} IS NULL OR {games} > {PROVISIONAL_GAMES})" if games in columns else ""

        def stored(kind):
            col = f"{side}_{kind}_before"
            if col in columns:
                whens.append(f"WHEN {col} IS NOT NULL{settled(kind)} THEN {col}")

        def derived(cols, kind):
            after, change = (cols[0], cols[1]) if side == "winner" else (cols[2], cols[3])
            guard = f" AND {side}_{kind}_before IS NULL" if f"{side}_{kind}_before" in columns else ""
            cond = " AND ".join(f"{c} IS NOT NULL" for c in cols)
            whens.append(f"WHEN {cond}{guard} THEN {after} - {change}")

        stored("avatar")
        if _AVATAR in old_sources:
            derived(_AVATAR, "avatar")
        stored("event")
        stored("lifetime")
        if _LIFETIME in old_sources:
            derived(_LIFETIME, "lifetime")
        if not whens:
            return None
        sides.append(f"CASE {' '.join(whens)} END")
    return tuple(sides)


def elo_gap_by_day(cur, tables) -> list[list]:
    """[date, games, total gap] rows (oldest first) across the given match tables."""
    totals = {}
    for table in tables:
        columns = {row[1] for row in cur.execute(f"PRAGMA table_info({table})")}
        sources = [c for c in (_AVATAR, _LIFETIME) if set(c) <= columns]
        if not sources:
            continue
        # Prefer the avatar gap when the game has avatar ratings, else lifetime.
        gaps = [_gap_sql(c) for c in sources]
        gap_expr = "CASE " + " ".join(f"WHEN {cond} THEN {expr}" for expr, cond in gaps) + " END"
        cur.execute(f"""
            SELECT substr(timestamp, 1, 10) AS day, COUNT(gap), SUM(gap) FROM (
                SELECT timestamp, {gap_expr} AS gap FROM {table}
                WHERE timestamp IS NOT NULL
            ) WHERE gap IS NOT NULL GROUP BY day
        """)
        for day, games, gap_sum in cur.fetchall():
            g, s = totals.get(day, (0, 0))
            totals[day] = (g + games, s + gap_sum)
    return [[day, g, s] for day, (g, s) in sorted(totals.items())]


# --- Rating at game time, for the skill matrices -----------------------------

_BEFORE = tuple(f"{side}_{kind}_before" for side in ("winner", "loser") for kind in ("event", "avatar", "lifetime"))


def pre_match_select(columns) -> str:
    """``winner_pre, loser_pre, has_snapshot`` SELECT fragment for a match table.

    ``has_snapshot`` is 1 when the game stored either side's standing before
    it (newer games). There a NULL pre-game rating means that side's rating
    was still provisional; on older games it means nothing was stored.
    """
    columns = set(columns)
    pre = pre_match_sql(columns) or ("NULL", "NULL")
    stored = [f"{c} IS NOT NULL" for c in _BEFORE if c in columns]
    snapshot = f"({' OR '.join(stored)})" if stored else "0"
    return f"{pre[0]} AS winner_pre, {pre[1]} AS loser_pre, {snapshot} AS has_snapshot"


def ratings_then(winner_pre, loser_pre, has_snapshot, winner_now, loser_now):
    """(winner, loser) rating at game time for a skill matrix.

    The stored pre-game rating where there is one. A newer game (it stored
    standings) leaves a side None when that side was provisional. An older game
    with nothing stored falls back to both players' current ratings, so old
    seasons read as they always have (None, None when either is unknown).
    """
    if winner_pre is not None and loser_pre is not None:
        return winner_pre, loser_pre
    if has_snapshot:
        return winner_pre, loser_pre
    if winner_now is None or loser_now is None:
        return None, None
    return winner_now, loser_now


def current_ratings(elo_conn, paper: bool = False, default=1500) -> dict:
    """{user_id (str): today's rating}: the fallback for games that stored nothing.

    Online reads ``overall_standings.elo`` where the live database has it (as
    these views always have), else the Seasons 1-8 lifetime (``legacy_online_elo``)
    or lifetime ELO. A player with no rating gets ``default``. Raises
    sqlite3.OperationalError when the table is missing.
    """
    if paper:
        sql = "SELECT user_id, paper_elo FROM paper_standings"
    else:
        cols = {row[1] for row in elo_conn.execute("PRAGMA table_info(overall_standings)")}
        if "elo" in cols:
            expr = "elo"
        elif "legacy_online_elo" in cols:
            expr = "COALESCE(legacy_online_elo, online_elo)"
        else:
            expr = "online_elo"
        sql = f"SELECT user_id, {expr} FROM overall_standings"
    return {str(uid): rating or default for uid, rating in elo_conn.execute(sql).fetchall()}
