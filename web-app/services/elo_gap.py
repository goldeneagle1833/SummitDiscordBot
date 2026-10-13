"""Average ELO gap between the two players in online games, for the admin dashboard.

Each side's pre-match rating is its stored rating after the match minus the
change it took. Avatar seasons use the avatar entries' ratings; other games
fall back to lifetime ELO, since a player's event ELO before a match is not
stored on the record. Games missing either side's rating are skipped.
"""

_AVATAR = ("winner_avatar_elo_after", "winner_avatar_elo_change",
           "loser_avatar_elo_after", "loser_avatar_elo_change")
_LIFETIME = ("winner_lifetime_elo_after", "winner_lifetime_elo_change",
             "loser_lifetime_elo_after", "loser_lifetime_elo_change")


def _gap_sql(cols):
    wa, wc, la, lc = cols
    return f"ABS(({wa} - {wc}) - ({la} - {lc}))", " AND ".join(f"{c} IS NOT NULL" for c in cols)


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
