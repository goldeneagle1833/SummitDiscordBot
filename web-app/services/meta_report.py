"""Meta Report: a twice-monthly look at what the Summit plays and wins with.

Each report covers one half-month period (the 1st-15th, or the 16th-month end)
and comes out at 01:00 UTC on the 1st or 15th of the next month, in step with
the ranked card data Play Sorcery Online releases for Card Win Rates:

    Sep 1-15   -> published Oct 1
    Sep 16-30  -> published Oct 15

Data sources, all held to the report's period:
  - Summit ranked games (match_records.db): Avatar + element pair share, win
    rates, tiers and matchups. Totals only; no ranked deck lists or player
    names ever leave this module.
  - PSO ranked card analytics (services/ranked_analytics): card play rates,
    risers and fallers, the sleeper pick.
  - Top 8 page events (repositories/events): tournaments in the period and the
    public deck list shown as "Deck to try".

Publishing a report (automatically on its publish day, or by an admin) posts
it to the Discord content channel, puts a banner on the home page and emails
confirmed subscribers. A background thread in each gunicorn worker does the
automatic build and the deliveries; a file lock keeps it to one worker.
"""

from __future__ import annotations

import calendar
import fcntl
import json
import logging
import math
import os
import smtplib
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from html import escape

import webapp_config
from repositories.meta_reports import MetaReportRepository

logger = logging.getLogger(__name__)

PUBLISH_HOUR_UTC = 1       # reports come out at 01:00 UTC on the 1st and 15th
MIN_ARCHETYPE_GAMES = 20   # deck-games before an Avatar + element pair is listed...
MIN_ARCHETYPE_SHARE = 0.01  # ...and at least 1% of the period's decks
MIN_MATCHUP_GAMES = 10     # games before a matchup cell shows a number
MIN_SLEEPER_GAMES = 20    # PSO hides played win rates under 20 games, so this is its own floor
SLEEPER_MAX_SHARE = 0.10   # sleeper cards are in fewer than 10% of decks
MATCHUP_SIZE = 6           # most-played archetypes in the matchup grid
MOVERS = 5                 # risers and fallers shown
TIERS = ("S", "A", "B", "C")
AUTO_PUBLISH_GRACE_DAYS = 7  # don't auto-announce a period this far past its publish day
PSO_WAIT_DAYS = 3            # publish without card data if PSO hasn't released it by then
BANNER_CREATOR = "meta-report"
BANNER_DAYS = 14


# ---------------------------------------------------------------------- #
# Periods                                                                  #
# ---------------------------------------------------------------------- #

@dataclass(frozen=True)
class Period:
    year: int
    month: int
    half: str  # "a" = 1st-15th, "b" = 16th-month end

    @classmethod
    def from_slug(cls, slug: str) -> "Period":
        try:
            y, m, h = slug.split("-")
            period = cls(int(y), int(m), h)
        except (ValueError, AttributeError):
            raise ValueError(f"Bad report period: {slug!r}")
        if h not in ("a", "b") or not 1 <= period.month <= 12 or not 2020 <= period.year <= 2100:
            raise ValueError(f"Bad report period: {slug!r}")
        return period

    @classmethod
    def containing(cls, day: date) -> "Period":
        return cls(day.year, day.month, "a" if day.day <= 15 else "b")

    @property
    def slug(self) -> str:
        return f"{self.year:04d}-{self.month:02d}-{self.half}"

    @property
    def start(self) -> date:
        return date(self.year, self.month, 1 if self.half == "a" else 16)

    @property
    def end(self) -> date:
        last = calendar.monthrange(self.year, self.month)[1]
        return date(self.year, self.month, 15 if self.half == "a" else last)

    @property
    def publish_day(self) -> date:
        """The 1st (for the 1st-15th) or the 15th (for the 16th-month end) of the next month."""
        y, m = (self.year + 1, 1) if self.month == 12 else (self.year, self.month + 1)
        return date(y, m, 1 if self.half == "a" else 15)

    def previous(self) -> "Period":
        if self.half == "b":
            return Period(self.year, self.month, "a")
        y, m = (self.year - 1, 12) if self.month == 1 else (self.year, self.month - 1)
        return Period(y, m, "b")

    def label(self) -> str:
        return f"{calendar.month_abbr[self.month]} {self.start.day}–{self.end.day}, {self.year}"

    def publish_label(self) -> str:
        d = self.publish_day
        return f"{calendar.month_abbr[d.month]} {d.day}, {d.year}"


def latest_due_period(today: date) -> Period:
    """The newest period whose publish day has arrived."""
    period = Period.containing(today)
    while period.publish_day > today:
        period = period.previous()
    return period


def report_today(now: datetime | None = None) -> date:
    """Today's date on the report clock: UTC, rolling over at 01:00 UTC.

    Before 01:00 UTC on the 1st or 15th it is still the day before, so the
    new period isn't due yet.
    """
    now = now or datetime.now(timezone.utc)
    return (now.astimezone(timezone.utc) - timedelta(hours=PUBLISH_HOUR_UTC)).date()


def _utc_day(timestamp: str | None) -> str | None:
    """UTC "YYYY-MM-DD" for a match timestamp (naive values are server-local time)."""
    if not timestamp:
        return None
    try:
        return datetime.fromisoformat(str(timestamp)).astimezone(timezone.utc).date().isoformat()
    except ValueError:
        return str(timestamp)[:10]


# ---------------------------------------------------------------------- #
# Summit ranked games                                                      #
# ---------------------------------------------------------------------- #

def _archetype(raw_json: str | None) -> tuple[str, str] | None:
    """(avatar, "Air / Fire") for a stored ranked deck, or None if unreadable."""
    if not raw_json or raw_json in ("", "{}"):
        return None
    try:
        raw = json.loads(raw_json)
    except (TypeError, ValueError):
        return None
    from repositories.archetype_decks import deck_from_json

    deck = deck_from_json(raw, "x", None)
    if deck is None or deck.avatar in (None, "", "Unknown") or deck.elements == "None":
        return None
    return deck.avatar, deck.elements


def _deck_info(raw_json: str | None) -> tuple[tuple[str, str] | None, frozenset, float | None]:
    """(archetype, spellbook card names, average spell cost) for a stored ranked deck."""
    arch = _archetype(raw_json)
    if arch is None:
        return None, frozenset(), None
    try:
        spellbook = json.loads(raw_json).get("spellbook") or []
    except (TypeError, ValueError, AttributeError):
        return arch, frozenset(), None
    names, total, copies = set(), 0.0, 0
    for card in spellbook:
        if not isinstance(card, dict) or not card.get("name"):
            continue
        names.add(card["name"])
        try:
            cost = float(card.get("cost"))
            qty = max(1, int(card.get("quantity") or 1))
        except (TypeError, ValueError):
            continue
        total += cost * qty
        copies += qty
    return arch, frozenset(names), (total / copies if copies else None)


def _went_first(value) -> bool | None:
    v = str(value or "").strip().lower()
    return True if v in ("y", "yes", "true", "1") else False if v in ("n", "no", "false", "0") else None


def _shift_day(day: str, days: int) -> str:
    try:
        return (date.fromisoformat(day) + timedelta(days=days)).isoformat()
    except ValueError:
        return day


def ranked_games(period_from: str, period_through: str, db_path=None) -> list[dict]:
    """Every ranked game in the period as {winner, loser}, each an archetype or None."""
    path = db_path or webapp_config.MATCH_RECORDS_DB_PATH
    if not os.path.exists(path):
        return []
    games: list[dict] = []
    seen_ids: set = set()
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        for table, id_col in (("match_records", "match_id"), ("match_records_archive", "original_match_id")):
            try:
                cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            except sqlite3.Error:
                continue
            if not {"json_deck_data_winner", "json_deck_data_loser", "timestamp"} <= cols:
                continue
            ranked = " AND (match_type = 'ranked' OR match_type IS NULL)" if "match_type" in cols else ""
            ident = id_col if id_col in cols else "NULL"
            minutes = "match_time" if "match_time" in cols else "NULL"
            first = "winner_went_first" if "winner_went_first" in cols else "NULL"
            # Periods are UTC days; timestamps are server-local, so widen by a day and convert.
            rows = conn.execute(
                f"""SELECT {ident}, json_deck_data_winner, json_deck_data_loser,
                           timestamp, {minutes}, {first}
                    FROM {table}
                    WHERE substr(timestamp, 1, 10) BETWEEN ? AND ? {ranked}""",
                (_shift_day(period_from, -1), _shift_day(period_through, 1)),
            )
            for match_id, winner_json, loser_json, stamp, mins, went_first in rows:
                day = _utc_day(stamp)
                if day is None or not period_from <= day <= period_through:
                    continue
                if match_id is not None:
                    if match_id in seen_ids:
                        continue  # archived copy of a live row
                    seen_ids.add(match_id)
                w, w_cards, w_cost = _deck_info(winner_json)
                l, l_cards, l_cost = _deck_info(loser_json)
                try:
                    mins = int(mins) if mins is not None and 0 < int(mins) < 240 else None
                except (TypeError, ValueError):
                    mins = None
                # Only totals ever leave this module: card names feed counts, never lists.
                games.append({"winner": w, "loser": l, "day": day, "minutes": mins,
                              "winnerFirst": _went_first(went_first),
                              "winnerCards": w_cards, "loserCards": l_cards,
                              "winnerCost": w_cost, "loserCost": l_cost})
    finally:
        conn.close()
    return games


def _tier_score(wins: int, games: int, share: float) -> float:
    """Win rate pulled toward 50% on small samples, plus a little credit for popularity."""
    adjusted = (wins + 15) / (games + 30)
    return (adjusted - 0.5) * 100 + math.log2(share * 100 + 1) * 1.5


def archetype_stats(games: list[dict]) -> dict:
    # Grouped by Avatar only (Bruce's call): element pairs split the tiers too thin.
    counts: dict[tuple, list[int]] = {}
    for g in games:
        for side, won in (("winner", True), ("loser", False)):
            arch = g[side]
            if arch is None:
                continue
            c = counts.setdefault((arch[0], ""), [0, 0])
            c[0] += 1
            c[1] += 1 if won else 0
    deck_games = sum(c[0] for c in counts.values())
    rows = []
    minimum = max(MIN_ARCHETYPE_GAMES, math.ceil(deck_games * MIN_ARCHETYPE_SHARE))
    for (avatar, elements), (n, wins) in counts.items():
        if n < minimum:
            continue
        share = n / deck_games if deck_games else 0.0
        rows.append({
            "avatar": avatar,
            "elements": elements,
            "games": n,
            "wins": wins,
            "winRate": round(wins / n * 100, 1),
            "share": round(share * 100, 1),
            "score": round(_tier_score(wins, n, share), 2),
        })
    rows.sort(key=lambda r: -r["score"])
    total = len(rows)
    # Proportional tiers, capped so a fragmented meta doesn't flood the top.
    s_cut = min(4, max(1, round(total * 0.10)))
    a_cut = s_cut + min(8, round(total * 0.20))
    b_cut = a_cut + min(12, round(total * 0.30))
    cuts = (s_cut, a_cut, b_cut)
    for i, row in enumerate(rows):
        row["tier"] = TIERS[0] if i < cuts[0] else TIERS[1] if i < cuts[1] else TIERS[2] if i < cuts[2] else TIERS[3]
    return {"rankedGames": len(games), "deckGames": deck_games, "minArchetypeGames": minimum,
            "archetypes": rows}


def matchup_grid(games: list[dict], archetypes: list[dict] | None = None) -> dict:
    """Avatar against Avatar. Element pairs split the games too thin for matchups."""
    totals: dict[str, int] = {}
    for g in games:
        for side in ("winner", "loser"):
            if g[side]:
                totals[g[side][0]] = totals.get(g[side][0], 0) + 1
    keys = [a for a, _n in sorted(totals.items(), key=lambda kv: -kv[1])][:MATCHUP_SIZE]
    index = {k: i for i, k in enumerate(keys)}
    wins = [[0] * len(keys) for _ in keys]
    for g in games:
        w, l = g["winner"], g["loser"]
        if w and l and w[0] in index and l[0] in index and w[0] != l[0]:
            wins[index[w[0]]][index[l[0]]] += 1
    cells = []
    for i in range(len(keys)):
        row = []
        for j in range(len(keys)):
            n = wins[i][j] + wins[j][i]
            if i == j:
                row.append(None)
            elif n < MIN_MATCHUP_GAMES:
                row.append({"games": n, "winRate": None})
            else:
                row.append({"games": n, "winRate": round(wins[i][j] / n * 100, 1)})
        cells.append(row)
    return {"archetypes": [{"avatar": a, "elements": ""} for a in keys], "cells": cells,
            "minGames": MIN_MATCHUP_GAMES, "by": "avatar"}


ELEMENTS = ("Air", "Earth", "Fire", "Water")
MIN_SIGNAL_GAMES = 5       # games each side of a comparison needs before a counter signal shows
MIN_KEY_CARD_DECKS = 10    # winning decks that must run a card before it's named


def element_shares(games: list[dict]) -> dict[str, float]:
    sides = [g[s] for g in games for s in ("winner", "loser") if g[s]]
    if not sides:
        return {}
    return {e: round(sum(1 for a in sides if e in a[1].split(" / ")) / len(sides) * 100, 1) for e in ELEMENTS}


def element_trend(games: list[dict], previous_games: list[dict], period: "Period") -> dict:
    """Each element's share of ranked decks, day by day across the period."""
    by_day: dict[str, list[dict]] = {}
    for g in games:
        if g.get("day"):
            by_day.setdefault(g["day"], []).append(g)
    days = []
    d = period.start
    while d <= period.end:
        days.append(d.isoformat())
        d += timedelta(days=1)
    series = {e: [] for e in ELEMENTS}
    counts = []
    for day in days:
        shares = element_shares(by_day.get(day, []))
        counts.append(sum(1 for g in by_day.get(day, []) for s in ("winner", "loser") if g[s]))
        for e in ELEMENTS:
            series[e].append(shares.get(e))
    now, before = element_shares(games), element_shares(previous_games)
    return {
        "days": days,
        "decks": counts,
        "series": series,
        "share": now,
        "change": {e: round(now[e] - before[e], 1) for e in now if e in before},
    }


def _rate(wins: int, n: int) -> float:
    return round(wins / n * 100, 1)


def _avg(values: list) -> float | None:
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def _counter_signals(target: str, counter: str, games: list[dict]) -> tuple[list[dict], str | None]:
    """Why a counter works, worked out from game length, turn order, curve, elements and cards."""
    head = [g for g in games if g["winner"] and g["loser"]
            and {g["winner"][0], g["loser"][0]} == {target, counter}]
    signals = []

    # Speed: how long the counter's wins take, against the target's other games.
    fast = [g["minutes"] for g in head if g["winner"][0] == counter]
    other = [g["minutes"] for g in games if g["winner"] and g["loser"]
             and target in (g["winner"][0], g["loser"][0])
             and counter not in (g["winner"][0], g["loser"][0])]
    fast, other = [m for m in fast if m], [m for m in other if m]
    if len(fast) >= MIN_SIGNAL_GAMES and len(other) >= MIN_SIGNAL_GAMES:
        a, b = round(_avg(fast)), round(_avg(other))
        if abs(a - b) >= 3:
            signals.append({"kind": "speed", "faster": a < b,
                            "text": f"{'Faster' if a < b else 'Longer'} games: {a} min vs {b} for {target}'s other games"})

    # Turn order: the counter's win rate on the play and on the draw.
    play = [(g["winner"][0] == counter) for g in head
            if g["winnerFirst"] is not None and ((g["winner"][0] == counter) == g["winnerFirst"])]
    draw = [(g["winner"][0] == counter) for g in head
            if g["winnerFirst"] is not None and ((g["winner"][0] == counter) != g["winnerFirst"])]
    if len(play) >= MIN_SIGNAL_GAMES and len(draw) >= MIN_SIGNAL_GAMES:
        p, d = _rate(sum(play), len(play)), _rate(sum(draw), len(draw))
        if abs(p - d) >= 10:
            signals.append({"kind": "turn", "first": p > d,
                            "text": f"On the play: {round(p)}% · on the draw: {round(d)}%"})

    # Curve: average spell cost of each side in these games.
    def costs(name):
        return [g["winnerCost"] if g["winner"][0] == name else g["loserCost"] for g in head]
    c_cost, t_cost = [x for x in costs(counter) if x is not None], [x for x in costs(target) if x is not None]
    if len(c_cost) >= MIN_SIGNAL_GAMES and len(t_cost) >= MIN_SIGNAL_GAMES:
        a, b = _avg(c_cost), _avg(t_cost)
        if abs(a - b) >= 0.4:
            signals.append({"kind": "curve", "lower": a < b,
                            "text": f"{'Lower' if a < b else 'Higher'} curve: {a:.1f} average cost vs {b:.1f}"})

    # Element pair the counter brings to this matchup.
    pairs: dict[str, int] = {}
    for g in head:
        side = g["winner"] if g["winner"][0] == counter else g["loser"]
        pairs[side[1]] = pairs.get(side[1], 0) + 1
    if pairs:
        pair, n = max(pairs.items(), key=lambda kv: kv[1])
        if n / len(head) >= 0.6:
            signals.append({"kind": "elements", "text": f"Mostly {pair} {counter} ({round(n / len(head) * 100)}% of these games)"})

    # Key card: run far more often by the counter's winning decks here than by its decks overall.
    winning = [g["winnerCards"] for g in head if g["winner"][0] == counter and g["winnerCards"]]
    all_decks = [g[f"{s}Cards"] for g in games for s in ("winner", "loser")
                 if g[s] and g[s][0] == counter and g[f"{s}Cards"]]
    best = None
    if len(winning) >= MIN_KEY_CARD_DECKS and all_decks:
        seen: dict[str, int] = {}
        for cards in winning:
            for c in cards:
                seen[c] = seen.get(c, 0) + 1
        for card, n in seen.items():
            if n < MIN_KEY_CARD_DECKS:
                continue
            base = sum(1 for cards in all_decks if card in cards) / len(all_decks)
            ratio = (n / len(winning)) / base if base else 0
            if ratio >= 1.5 and (best is None or ratio > best[1]):
                best = (card, ratio)
    if best:
        signals.append({"kind": "card", "card": best[0],
                        "text": f"Winning {counter} decks ran {best[0]} {best[1]:.1f}× as often as {counter} decks overall"})

    parts = []
    for sig in signals:
        if sig["kind"] == "speed" and sig["faster"]:
            parts.append("wins it fast")
        elif sig["kind"] == "speed":
            parts.append("wins the long game")
        elif sig["kind"] == "curve":
            parts.append("does it on a lower curve" if sig["lower"] else "goes over the top with bigger spells")
        elif sig["kind"] == "turn":
            parts.append("wants to go first" if sig["first"] else "does fine on the draw")
        elif sig["kind"] == "card":
            parts.append(f"the winning lists lean on {sig['card']}")
    if not parts:
        return signals, None
    text = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    return signals, f"{counter} {text}."


def counter_picks(games: list[dict], archetypes: list[dict]) -> list[dict]:
    """For each S tier Avatar, the Avatar that beats it most often."""
    picks = []
    for target in [a["avatar"] for a in archetypes if a.get("tier") == "S"]:
        vs: dict[str, list[int]] = {}
        rest = [0, 0]
        for g in games:
            w, l = g["winner"], g["loser"]
            if not (w and l) or w[0] == l[0] or target not in (w[0], l[0]):
                continue
            other = l[0] if w[0] == target else w[0]
            rec = vs.setdefault(other, [0, 0])
            rec[0] += 1
            rec[1] += 1 if w[0] == other else 0
        best = None
        for other, (n, other_wins) in vs.items():
            if n < MIN_MATCHUP_GAMES:
                continue
            rate = other_wins / n
            if rate > 0.5 and (best is None or rate > best[1]):
                best = (other, rate, n, other_wins)
        if not best:
            continue
        counter, rate, n, _wins = best
        for other, (m, other_wins) in vs.items():
            if other != counter:
                rest[0] += m
                rest[1] += m - other_wins
        signals, why = _counter_signals(target, counter, games)
        picks.append({
            "target": target,
            "counter": counter,
            "winRate": round(rate * 100, 1),
            "games": n,
            "targetElsewhere": _rate(rest[1], rest[0]) if rest[0] else None,
            "targetVsCounter": round((1 - rate) * 100, 1),
            "signals": [sig["text"] for sig in signals],
            "why": why,
        })
    return picks


def tournament_vs_ladder(games: list[dict], top8_avatars: list[str]) -> dict:
    """Avatars whose Top 8 share is far from their ranked share."""
    if len(top8_avatars) < 8:
        return {"available": False}
    sides = [g[s][0] for g in games for s in ("winner", "loser") if g[s]]
    if not sides:
        return {"available": False}
    ranked: dict[str, int] = {}
    for a in sides:
        ranked[a] = ranked.get(a, 0) + 1
    top8: dict[str, int] = {}
    for a in top8_avatars:
        top8[a] = top8.get(a, 0) + 1
    rows = []
    for a in set(ranked) | set(top8):
        t, r = top8.get(a, 0), ranked.get(a, 0) / len(sides) * 100
        rows.append({"avatar": a, "top8": t, "top8Total": len(top8_avatars),
                     "top8Share": round(t / len(top8_avatars) * 100, 1), "rankedShare": round(r, 1),
                     "gap": t / len(top8_avatars) * 100 - r})
    tournament = sorted((x for x in rows if x["top8"] >= 2 and x["gap"] >= 5), key=lambda x: -x["gap"])[:3]
    ladder = sorted((x for x in rows if x["rankedShare"] >= 3 and x["gap"] <= -5), key=lambda x: x["gap"])[:3]
    for x in tournament + ladder:
        x.pop("gap")
    return {"available": bool(tournament or ladder), "tournament": tournament, "ladder": ladder,
            "top8Decks": len(top8_avatars)}


def _with_moves(current: list[dict], previous: list[dict]) -> None:
    before = {(r["avatar"], r["elements"]): TIERS.index(r["tier"]) for r in previous}
    for row in current:
        key = (row["avatar"], row["elements"])
        row["move"] = "new" if key not in before else before[key] - TIERS.index(row["tier"])


# ---------------------------------------------------------------------- #
# PSO ranked card data                                                     #
# ---------------------------------------------------------------------- #

def fetch_pso_cards(period_from: str, period_through: str) -> dict | None:
    """PSO's card rows for the period, or None when PSO can't answer."""
    from services import ranked_analytics

    try:
        result = ranked_analytics.forward(
            "GET", "cards",
            params={"format": "constructed", "from": period_from, "through": period_through},
        )
    except ranked_analytics.AnalyticsUnavailable as exc:
        logger.info("Meta report: PSO card data unavailable: %s", exc)
        return None
    if result.status != 200 or not isinstance(result.body, dict):
        return None
    return result.body


def pso_has_period(period: "Period") -> bool:
    """Whether PSO has released its card data for the whole period."""
    body = fetch_pso_cards(period.start.isoformat(), period.end.isoformat())
    if not body or not body.get("dataAvailable", True):
        return False
    released = body.get("releasedThrough")
    return released is None or released >= period.end.isoformat()


def _card_rows(body: dict | None) -> dict[str, dict]:
    rows = {}
    for card in (body or {}).get("cards") or []:
        key = card.get("cardKey")
        if not key:
            continue
        played = card.get("played") or {}
        unplayed = card.get("inDeckUnplayed") or {}
        opening = card.get("openingHand") or {}
        rows[key] = {
            "name": card.get("cardName") or key,
            "share": card.get("deckShare"),
            "playedGames": played.get("playerGames"),
            "playedWinRate": played.get("winRate"),
            "unplayedGames": unplayed.get("playerGames"),
            "unplayedWinRate": unplayed.get("winRate"),
            "openingGames": opening.get("playerGames"),
            "openingWinRate": opening.get("winRate"),
        }
    return rows


def _body_from_report(history: list[dict], period_from: str) -> dict | None:
    """The previous period's card shares from its saved report, when PSO can't give them again."""
    for report in history:
        if report.get("from") != period_from:
            continue
        index = ((report.get("payload") or {}).get("cards") or {}).get("index") or {}
        if not index:
            return None
        return {"cards": [
            {"cardKey": k, "deckShare": None if v[0] is None else v[0] / 100,
             "played": {"winRate": None if v[1] is None else v[1] / 100}}
            for k, v in index.items()
        ]}
    return None


def _pct(x):
    return None if x is None else round(x * 100, 1)


def _enough(games) -> bool:
    return (games or 0) >= MIN_SLEEPER_GAMES


def spotlights(now: dict[str, dict], skip: set[str]) -> list[dict]:
    """Three angles on the card data that change from report to report.

    A card featured in the last report's spotlights sits out, so each report
    puts new names forward.
    """
    def pick(candidates, key, kind, label, detail):
        options = [k for k in candidates if k not in skip]
        if not options:
            return None
        k = max(options, key=key)
        row = now[k]
        return {"kind": kind, "label": label, "key": k, "name": row["name"], "detail": detail(row)}

    def swing(row):
        return row["playedWinRate"] - row["unplayedWinRate"]

    both = [k for k, r in now.items()
            if r["playedWinRate"] is not None and r["unplayedWinRate"] is not None
            and _enough(r["playedGames"]) and _enough(r["unplayedGames"])]
    changers = [k for k in both if swing(now[k]) > 0]
    traps = [k for k in both if swing(now[k]) < 0 and (now[k]["share"] or 0) >= SLEEPER_MAX_SHARE]
    openers = [k for k, r in now.items()
               if r["openingWinRate"] is not None and r["openingWinRate"] > 0.5 and _enough(r["openingGames"])]

    def pp(row):
        return round(abs(swing(row)) * 100, 1)

    tiles = [
        pick(changers, lambda k: swing(now[k]), "changer", "Game changer",
             lambda r: f"Wins {_pct(r['playedWinRate'])}% when played, {_pct(r['unplayedWinRate'])}% when it stays in hand (+{pp(r)} pts)."),
        pick(traps, lambda k: -swing(now[k]), "trap", "Trap card",
             lambda r: f"In {_pct(r['share'])}% of decks, but wins {_pct(r['playedWinRate'])}% when played vs {_pct(r['unplayedWinRate'])}% when held (-{pp(r)} pts)."),
        pick(openers, lambda k: now[k]["openingWinRate"], "opener", "Opening hand star",
             lambda r: f"Wins {_pct(r['openingWinRate'])}% of games when it's in the opening hand ({r['openingGames']} games)."),
    ]
    return [t for t in tiles if t]


def card_section(body: dict | None, prev_body: dict | None, history: list[dict], period_through: str) -> dict:
    if not body or not body.get("dataAvailable", True):
        return {"available": False}
    released = body.get("releasedThrough")
    if released and released < period_through:
        return {"available": False, "releasedThrough": released}
    now, before = _card_rows(body), _card_rows(prev_body)
    if not any(r["share"] for r in now.values()):
        return {"available": False, "empty": True, "releasedThrough": released}
    # Each earlier report keeps a compact index so trend lines need no extra PSO calls.
    older = [((h.get("payload") or {}).get("cards") or {}).get("index") or {} for h in reversed(history)]

    def trend(key):
        points = [o.get(key, [None, None])[1] for o in older]
        points.append(_pct(now[key]["playedWinRate"]))
        return points[-6:]

    deltas = []
    for key, row in now.items():
        if row["share"] is None or key not in before or before[key]["share"] is None:
            continue
        deltas.append((row["share"] - before[key]["share"], key))
    deltas.sort()

    def mover(delta, key):
        row = now[key]
        return {"name": row["name"], "share": _pct(row["share"]), "change": round(delta * 100, 1),
                "winRate": _pct(row["playedWinRate"]), "trend": trend(key)}

    rising = [mover(d, k) for d, k in reversed(deltas) if d > 0][:MOVERS]
    falling = [mover(d, k) for d, k in deltas if d < 0][:MOVERS]
    mode = "movers"
    if not rising and not falling:
        # No earlier period to compare with: show what's played most and what wins most.
        mode = "top"

        def plain(key):
            row = now[key]
            return {"name": row["name"], "share": _pct(row["share"]), "change": None,
                    "winRate": _pct(row["playedWinRate"]), "games": row["playedGames"], "trend": trend(key)}

        by_share = sorted((k for k, r in now.items() if r["share"]), key=lambda k: -now[k]["share"])
        # Only winning cards, so a 47% card never shows up under "best".
        by_wins = sorted(
            (k for k, r in now.items()
             if r["playedWinRate"] is not None and r["playedWinRate"] > 0.5
             and (r["playedGames"] or 0) >= MIN_SLEEPER_GAMES),
            key=lambda k: -now[k]["playedWinRate"],
        )
        rising = [plain(k) for k in by_share[:MOVERS]]
        falling = [plain(k) for k in by_wins[:MOVERS]]
    sleepers = [
        (row["playedWinRate"], key) for key, row in now.items()
        if row["share"] is not None and row["share"] < SLEEPER_MAX_SHARE
        and (row["playedGames"] or 0) >= MIN_SLEEPER_GAMES and row["playedWinRate"] is not None
        and row["playedWinRate"] > 0.5
    ]
    sleeper = None
    if sleepers:
        _wr, key = max(sleepers)
        row = now[key]
        sleeper = {"name": row["name"], "winRate": _pct(row["playedWinRate"]),
                   "share": _pct(row["share"]), "games": row["playedGames"]}
    index = {k: [_pct(r["share"]), _pct(r["playedWinRate"])] for k, r in now.items()}
    last = ((history[0].get("payload") or {}).get("cards") or {}) if history else {}
    skip = {t.get("key") for t in last.get("spotlights") or []}
    staples = [{"name": now[k]["name"], "share": _pct(now[k]["share"])}
               for k in sorted((k for k, r in now.items() if r["share"]), key=lambda k: -now[k]["share"])[:MOVERS]]
    return {
        "available": True,
        "mode": mode,
        "totalGames": body.get("totalGames"),
        "releasedThrough": released,
        "rising": rising,
        "falling": falling,
        "sleeper": sleeper,
        "staples": staples,
        "spotlights": spotlights(now, skip),
        "minGames": MIN_SLEEPER_GAMES,
        "maxSleeperShare": _pct(SLEEPER_MAX_SHARE),
        "index": index,
    }


# ---------------------------------------------------------------------- #
# Top 8 page events                                                        #
# ---------------------------------------------------------------------- #

def _pair(elements) -> str:
    if isinstance(elements, str):
        return elements
    parts = sorted(e for e in (elements or []) if e)
    return " / ".join(parts) if parts else "None"


def tournament_section(period_from: str, period_through: str, archetypes: list[dict]) -> dict:
    from repositories.events import EventRepository

    repo = EventRepository()
    events = []
    candidates = []
    top8_avatars = []
    for ev in repo.get_all_events():
        day = ev.get("event_date")
        if not day or not (period_from <= day <= period_through):
            continue
        decks = (repo.get_event_decks(ev["folder"]) or {}).get("top8_decks") or []
        winner = decks[0] if decks else {}
        events.append({
            "name": ev.get("name"),
            "folder": ev["folder"],
            "date": day,
            "players": ev.get("player_count"),
            "rating": ev.get("rating"),
            "winner": ev.get("winner_username") or winner.get("player"),
            "winnerAvatar": winner.get("avatar") or ev.get("winner_avatar"),
            "winnerElements": _pair(winner.get("elements")) if winner else None,
        })
        for place, deck in enumerate(decks, start=1):
            if deck.get("avatar"):
                top8_avatars.append(deck["avatar"])
            if deck.get("deck_id"):
                candidates.append((place, day, ev, deck))
    events.sort(key=lambda e: e["date"], reverse=True)

    # Deck to try: a public Top 8 list from the archetype that climbed most.
    rank = {a["avatar"]: (a["move"] if isinstance(a.get("move"), int) else 1, -TIERS.index(a["tier"]))
            for a in archetypes}
    pick = None
    best = None
    for place, day, ev, deck in candidates:
        key = deck.get("avatar")
        score = (rank.get(key, (-99, -99)), -place, day)
        if best is None or score > best:
            best, pick = score, (place, ev, deck, key in rank)
    deck_to_try = None
    if pick:
        place, ev, deck, ranked = pick
        deck_to_try = {
            "deckId": deck["deck_id"],
            "deckName": deck.get("deck_name"),
            "avatar": deck.get("avatar"),
            "elements": _pair(deck.get("elements")),
            "placement": place,
            "player": deck.get("player"),
            "event": ev.get("name"),
            "eventFolder": ev["folder"],
        }
    return {"events": events, "deckToTry": deck_to_try, "top8Avatars": top8_avatars}


# ---------------------------------------------------------------------- #
# Building a report                                                        #
# ---------------------------------------------------------------------- #

def draft_story(payload: dict) -> list[dict]:
    """Three plain-language takeaways an admin can edit before or after publishing."""
    story = []
    archetypes = payload["ranked"]["archetypes"]
    if archetypes:
        top = archetypes[0]
        story.append({
            "headline": f"{top['avatar']} is the deck to beat.",
            "detail": f"{top['winRate']}% win rate on {top['share']}% of decks.",
        })
        quiet = [a for a in archetypes[1:] if a["share"] < 6 and a["games"] >= 20]
        if quiet:
            q = max(quiet, key=lambda a: a["winRate"])
            if q["winRate"] > 50:
                story.append({
                    "headline": f"{q['avatar']} is the best deck few people play.",
                    "detail": f"{q['winRate']}% win rate on only {q['share']}% of decks.",
                })
        climbers = [a for a in archetypes if isinstance(a.get("move"), int) and a["move"] > 0]
        if climbers and len(story) < 2:
            c = max(climbers, key=lambda a: a["move"])
            story.append({
                "headline": f"{c['avatar']} climbs to {c['tier']} tier.",
                "detail": f"Up {c['move']} tier{'s' if c['move'] > 1 else ''} since the last report.",
            })
    cards = payload.get("cards") or {}
    if cards.get("available") and cards.get("rising"):
        r = cards["rising"][0]
        story.append({
            "headline": f"{r['name']} is on the rise.",
            "detail": f"In {r['share']}% of decks, up {r['change']} points since the last report.",
        })
    elif cards.get("available") and cards.get("sleeper"):
        s = cards["sleeper"]
        story.append({
            "headline": f"{s['name']} is the sleeper pick.",
            "detail": f"{s['winRate']}% win rate when played, in only {s['share']}% of decks.",
        })
    events = payload["tournaments"]["events"]
    if events and len(story) < 3 and events[0].get("winnerAvatar"):
        e = events[0]
        story.append({
            "headline": f"{e['winnerAvatar']} won {e['name']}.",
            "detail": f"{e['players']} players." if e.get("players") else "",
        })
    return story[:3]


def build_payload(period: Period, repo: MetaReportRepository | None = None,
                  db_path=None, pso=fetch_pso_cards) -> dict:
    repo = repo or MetaReportRepository()
    f, t = period.start.isoformat(), period.end.isoformat()
    prev = period.previous()
    pf, pt = prev.start.isoformat(), prev.end.isoformat()

    games = ranked_games(f, t, db_path)
    previous_games = ranked_games(pf, pt, db_path)
    ranked = archetype_stats(games)
    previous = archetype_stats(previous_games)
    _with_moves(ranked["archetypes"], previous["archetypes"])
    ranked["matchups"] = matchup_grid(games, ranked["archetypes"])
    ranked["counters"] = counter_picks(games, ranked["archetypes"])
    ranked["elementTrend"] = element_trend(games, previous_games, period)

    history = repo.reports_before(f, limit=4)
    prev_cards = pso(pf, pt)
    if not _card_rows(prev_cards) or not any(r["share"] for r in _card_rows(prev_cards).values()):
        prev_cards = _body_from_report(history, pf)
    cards = card_section(pso(f, t), prev_cards, history, t)
    tournaments = tournament_section(f, t, ranked["archetypes"])
    tournaments["vsLadder"] = tournament_vs_ladder(games, tournaments.pop("top8Avatars", []))
    return {
        "period": {"slug": period.slug, "from": f, "through": t, "label": period.label(),
                   "publishDay": period.publish_day.isoformat(), "publishLabel": period.publish_label()},
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ranked": ranked,
        "cards": cards,
        "tournaments": tournaments,
    }


def build(period: Period, repo: MetaReportRepository | None = None, **kwargs) -> dict:
    repo = repo or MetaReportRepository()
    payload = build_payload(period, repo, **kwargs)
    return repo.save_build(period.slug, payload["period"]["from"], payload["period"]["through"],
                           payload, draft_story(payload))


def public_report(report: dict | None) -> dict | None:
    """What the page and API show: no internal delivery fields, no card index."""
    if not report:
        return None
    payload = json.loads(json.dumps(report.get("payload") or {}))
    (payload.get("cards") or {}).pop("index", None)
    notes = (report.get("notes") or {}).get("counters") or {}
    for pick in (payload.get("ranked") or {}).get("counters") or []:
        if notes.get(pick["target"]):
            pick["why"] = notes[pick["target"]]
            pick["whyBy"] = "team"
    return {"slug": report["slug"], "from": report["from"], "through": report["through"],
            "publishedAt": report["publishedAt"], "story": report["story"], **payload}


# ---------------------------------------------------------------------- #
# Announcing: Discord, home page banner, email                             #
# ---------------------------------------------------------------------- #

def site_url() -> str:
    from services.store_notifications import PUBLIC_SITE_URL

    return (os.environ.get("META_REPORT_SITE_URL") or PUBLIC_SITE_URL or "https://sorcererssummit.com").rstrip("/")


def report_url(slug: str) -> str:
    return f"{site_url()}/meta-report/{slug}"


def _announcement(report: dict) -> dict:
    payload = report.get("payload") or {}
    archetypes = (payload.get("ranked") or {}).get("archetypes") or []
    return {
        "title": f"Meta Report: {payload.get('period', {}).get('label', report['slug'])}",
        "url": report_url(report["slug"]),
        "story": report.get("story") or [],
        "topTier": [a["avatar"] for a in archetypes if a.get("tier") == "S"][:4],
        "rankedGames": (payload.get("ranked") or {}).get("rankedGames"),
        "events": len((payload.get("tournaments") or {}).get("events") or []),
    }


def post_to_discord(report: dict) -> bool:
    from routes.api.matchmaking import relay_to_bot

    result, status = relay_to_bot("POST", "/meta-report-notify", _announcement(report),
                                  {"status": "unavailable"}, timeout=10)
    if status >= 300:
        logger.warning("Meta report Discord post failed (%s): %s", status, result)
        return False
    return True


def send_dms(report: dict, discord_ids: list[str]) -> bool:
    """Hand the subscriber list to the bot, which DMs them in the background."""
    from routes.api.matchmaking import relay_to_bot

    result, status = relay_to_bot("POST", "/meta-report-dm", {**_announcement(report), "user_ids": discord_ids},
                                  {"status": "unavailable"}, timeout=10)
    if status >= 300:
        logger.warning("Meta report DMs failed (%s): %s", status, result)
        return False
    return True


def create_banner(report: dict) -> None:
    from repositories.analytics import AnalyticsRepository

    analytics = AnalyticsRepository()
    analytics._ensure_promo_table()
    conn = sqlite3.connect(str(webapp_config.ANALYTICS_DB_PATH))
    try:
        conn.execute("UPDATE promo_banners SET active = 0 WHERE created_by = ?", (BANNER_CREATOR,))
        conn.commit()
    finally:
        conn.close()
    label = ((report.get("payload") or {}).get("period") or {}).get("label") or report["slug"]
    story = report.get("story") or []
    expires = (datetime.now(timezone.utc) + timedelta(days=BANNER_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    analytics.create_banner(
        title=f"New Meta Report: {label}",
        link=f"/meta-report/{report['slug']}",
        expires_at=expires,
        subtitle=story[0]["headline"] if story else "What the Summit is playing and winning with.",
        badge_text="META",
        color="gold",
        created_by=BANNER_CREATOR,
    )


def smtp_settings() -> dict:
    from services import store_notifications as s

    return {"host": s.SMTP_HOST, "port": s.SMTP_PORT, "user": s.SMTP_USER,
            "password": s.SMTP_PASSWORD, "from": s.SMTP_FROM}


def email_configured() -> bool:
    cfg = smtp_settings()
    return bool(cfg["host"] and cfg["from"])


def send_email(to_addr: str, subject: str, text: str, html: str | None = None,
               unsubscribe_url: str | None = None) -> None:
    cfg = smtp_settings()
    msg = EmailMessage()
    msg["From"] = cfg["from"]
    msg["To"] = to_addr
    msg["Subject"] = subject
    if unsubscribe_url:
        msg["List-Unsubscribe"] = f"<{unsubscribe_url}>"
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as smtp:
        smtp.starttls()
        if cfg["user"]:
            smtp.login(cfg["user"], cfg["password"])
        smtp.send_message(msg)


def unsubscribe_url(token: str) -> str:
    return f"{site_url()}/meta-report/email?unsubscribe={token}"


def confirm_url(token: str) -> str:
    return f"{site_url()}/meta-report/email?confirm={token}"


def send_confirmation(subscriber: dict) -> bool:
    if not email_configured():
        return False
    link = confirm_url(subscriber["token"])
    text = (
        "Confirm that you want the Sorcerers Summit Meta Report by email:\n\n"
        f"{link}\n\n"
        "If you didn't ask for this, ignore this email and you won't hear from us."
    )
    html = (
        "<p>Confirm that you want the Sorcerers Summit Meta Report by email.</p>"
        f'<p><a href="{escape(link)}">Yes, send me the Meta Report</a></p>'
        "<p>If you didn't ask for this, ignore this email and you won't hear from us.</p>"
    )
    try:
        send_email(subscriber["email"], "Confirm your Meta Report emails", text, html)
        return True
    except Exception as exc:
        logger.warning("Meta report confirmation email failed: %s", exc)
        return False


def report_email(report: dict, token: str) -> tuple[str, str, str]:
    payload = report.get("payload") or {}
    label = (payload.get("period") or {}).get("label") or report["slug"]
    url = report_url(report["slug"])
    unsub = unsubscribe_url(token)
    story = report.get("story") or []
    subject = f"Summit Meta Report: {label}"
    lines = [f"Summit Meta Report: {label}", ""]
    for i, s in enumerate(story, start=1):
        lines.append(f"{i}. {s.get('headline', '')} {s.get('detail', '')}".rstrip())
    lines += ["", f"Read the full report: {url}", "", f"Unsubscribe: {unsub}"]
    items = "".join(
        f"<li><strong>{escape(s.get('headline', ''))}</strong> {escape(s.get('detail', ''))}</li>"
        for s in story
    )
    html = (
        '<div style="font-family:Arial,sans-serif;max-width:560px;color:#111">'
        f'<h2 style="margin:0 0 4px">Summit Meta Report</h2><p style="margin:0 0 16px;color:#555">{escape(label)}</p>'
        f"<ol>{items}</ol>"
        f'<p><a href="{escape(url)}" style="background:#ffd700;color:#0d1117;padding:10px 16px;'
        'border-radius:6px;text-decoration:none;font-weight:bold">Read the full report</a></p>'
        f'<p style="font-size:12px;color:#777">You get this because you signed up on sorcererssummit.com. '
        f'<a href="{escape(unsub)}">Unsubscribe</a></p></div>'
    )
    return subject, "\n".join(lines), html


def send_pending_emails(repo: MetaReportRepository | None = None, limit: int = 40, pause: float = 1.0) -> int:
    repo = repo or MetaReportRepository()
    if not email_configured():
        return 0
    sent = 0
    reports: dict[str, dict] = {}
    for row in repo.pending_emails(limit=limit):
        report = reports.get(row["slug"]) or repo.get(row["slug"])
        reports[row["slug"]] = report
        subject, text, html = report_email(report, row["token"])
        try:
            send_email(row["email"], subject, text, html, unsubscribe_url(row["token"]))
            repo.mark_email(row["id"], True)
            sent += 1
        except Exception as exc:
            repo.mark_email(row["id"], False, str(exc))
            logger.warning("Meta report email failed: %s", exc)
        if pause:
            time.sleep(pause)
    return sent


def deliver(report: dict, repo: MetaReportRepository | None = None) -> dict:
    """Send whatever announcement steps a published report still needs. Safe to repeat."""
    repo = repo or MetaReportRepository()
    done = {}
    if not report.get("bannerCreatedAt"):
        try:
            create_banner(report)
            repo.mark_delivery(report["slug"], "banner_created_at")
            done["banner"] = True
        except Exception:
            logger.exception("Meta report banner failed")
    if not report.get("emailsQueuedAt"):
        queued = repo.queue_report_emails(report["id"])
        repo.mark_delivery(report["slug"], "emails_queued_at")
        done["emailsQueued"] = queued
    if not report.get("discordPostedAt"):
        if post_to_discord(report):
            repo.mark_delivery(report["slug"], "discord_posted_at")
            done["discord"] = True
    if not report.get("dmsSentAt"):
        ids = repo.dm_subscriber_ids()
        if not ids or send_dms(report, ids):
            repo.mark_delivery(report["slug"], "dms_sent_at")
            done["dms"] = len(ids)
    return done


def publish(slug: str, published_by: str, announce: bool = True,
            repo: MetaReportRepository | None = None) -> dict | None:
    repo = repo or MetaReportRepository()
    report = repo.publish(slug, published_by, announce)
    if report and announce:
        deliver(report, repo)
        report = repo.get(slug)
    return report


# ---------------------------------------------------------------------- #
# Background schedule                                                      #
# ---------------------------------------------------------------------- #

def auto_publish_due(today: date | None = None, repo: MetaReportRepository | None = None,
                     pso_ready=pso_has_period) -> dict | None:
    """Build and publish the newest due period once, if it hasn't been made yet."""
    if os.environ.get("META_REPORT_AUTOPUBLISH", "1") != "1":
        return None
    repo = repo or MetaReportRepository()
    today = today or report_today()
    period = latest_due_period(today)
    late = (today - period.publish_day).days
    if late > AUTO_PUBLISH_GRACE_DAYS or repo.get(period.slug):
        return None
    if late < PSO_WAIT_DAYS and not pso_ready(period):
        return None  # give PSO a few days to release the period's card data
    build(period, repo)
    return publish(period.slug, "auto", announce=True, repo=repo)


def tick(repo: MetaReportRepository | None = None) -> None:
    repo = repo or MetaReportRepository()
    try:
        auto_publish_due(repo=repo)
    except Exception:
        logger.exception("Meta report auto-publish failed")
    for report in repo.undelivered():
        try:
            deliver(report, repo)
        except Exception:
            logger.exception("Meta report delivery failed for %s", report["slug"])
    try:
        send_pending_emails(repo)
    except Exception:
        logger.exception("Meta report emails failed")


TICK_SECONDS = 15 * 60
_scheduler_pid = None
_scheduler_lock = threading.Lock()


def _loop() -> None:
    lock_path = webapp_config.META_REPORTS_DB_PATH.with_suffix(".lock")
    time.sleep(30)  # let the worker finish starting
    while True:
        try:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            with open(lock_path, "w") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    pass  # another worker is on it
                else:
                    tick()
        except Exception:
            logger.exception("Meta report scheduler iteration failed")
        time.sleep(TICK_SECONDS)


def start_scheduler() -> None:
    """Start the background thread once per process (gunicorn forks workers)."""
    global _scheduler_pid
    pid = os.getpid()
    if _scheduler_pid == pid:
        return
    with _scheduler_lock:
        if _scheduler_pid == pid:
            return
        threading.Thread(target=_loop, name="meta-report", daemon=True).start()
        _scheduler_pid = pid
