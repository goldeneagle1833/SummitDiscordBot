"""Meta Report: a twice-monthly look at what the Summit plays and wins with.

Each report covers one half-month period (the 1st-15th, or the 16th-month end)
and comes out one month after the period starts, the same lag as the ranked
card data Play Sorcery Online releases for Card Win Rates:

    Sep 1-15   -> published Oct 1
    Sep 16-30  -> published Oct 16

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
from zoneinfo import ZoneInfo

import webapp_config
from repositories.meta_reports import MetaReportRepository

logger = logging.getLogger(__name__)

EASTERN = ZoneInfo("America/New_York")
MIN_ARCHETYPE_GAMES = 20   # deck-games before an Avatar + element pair is listed...
MIN_ARCHETYPE_SHARE = 0.01  # ...and at least 1% of the period's decks
MIN_MATCHUP_GAMES = 20     # games before a matchup cell shows a number
MIN_SLEEPER_GAMES = 50     # player-games before a card can be the sleeper pick
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
        """One month after the period starts: the 1st or the 16th."""
        y, m = (self.year + 1, 1) if self.month == 12 else (self.year, self.month + 1)
        return date(y, m, 1 if self.half == "a" else 16)

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


def today_eastern() -> date:
    return datetime.now(EASTERN).date()


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
            rows = conn.execute(
                f"""SELECT {ident}, json_deck_data_winner, json_deck_data_loser
                    FROM {table}
                    WHERE substr(timestamp, 1, 10) BETWEEN ? AND ? {ranked}""",
                (period_from, period_through),
            )
            for match_id, winner_json, loser_json in rows:
                if match_id is not None:
                    if match_id in seen_ids:
                        continue  # archived copy of a live row
                    seen_ids.add(match_id)
                games.append({"winner": _archetype(winner_json), "loser": _archetype(loser_json)})
    finally:
        conn.close()
    return games


def _tier_score(wins: int, games: int, share: float) -> float:
    """Win rate pulled toward 50% on small samples, plus a little credit for popularity."""
    adjusted = (wins + 15) / (games + 30)
    return (adjusted - 0.5) * 100 + math.log2(share * 100 + 1) * 1.5


def archetype_stats(games: list[dict]) -> dict:
    counts: dict[tuple, list[int]] = {}
    for g in games:
        for side, won in (("winner", True), ("loser", False)):
            arch = g[side]
            if arch is None:
                continue
            c = counts.setdefault(arch, [0, 0])
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


def matchup_grid(games: list[dict], archetypes: list[dict]) -> dict:
    top = sorted(archetypes, key=lambda r: -r["games"])[:MATCHUP_SIZE]
    keys = [(r["avatar"], r["elements"]) for r in top]
    index = {k: i for i, k in enumerate(keys)}
    wins = [[0] * len(keys) for _ in keys]
    for g in games:
        w, l = g["winner"], g["loser"]
        if w in index and l in index and w != l:
            wins[index[w]][index[l]] += 1
    cells = []
    for i in range(len(keys)):
        row = []
        for j in range(len(keys)):
            n = wins[i][j] + wins[j][i]
            if i == j or n < MIN_MATCHUP_GAMES:
                row.append(None if i == j else {"games": n, "winRate": None})
            else:
                row.append({"games": n, "winRate": round(wins[i][j] / n * 100, 1)})
        cells.append(row)
    return {"archetypes": [{"avatar": a, "elements": e} for a, e in keys], "cells": cells,
            "minGames": MIN_MATCHUP_GAMES}


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
        rows[key] = {
            "name": card.get("cardName") or key,
            "share": card.get("deckShare"),
            "playedGames": played.get("playerGames"),
            "playedWinRate": played.get("winRate"),
        }
    return rows


def _pct(x):
    return None if x is None else round(x * 100, 1)


def card_section(body: dict | None, prev_body: dict | None, history: list[dict], period_through: str) -> dict:
    if not body or not body.get("dataAvailable", True):
        return {"available": False}
    released = body.get("releasedThrough")
    if released and released < period_through:
        return {"available": False, "releasedThrough": released}
    now, before = _card_rows(body), _card_rows(prev_body)
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
    sleepers = [
        (row["playedWinRate"], key) for key, row in now.items()
        if row["share"] is not None and row["share"] < SLEEPER_MAX_SHARE
        and (row["playedGames"] or 0) >= MIN_SLEEPER_GAMES and row["playedWinRate"] is not None
    ]
    sleeper = None
    if sleepers:
        _wr, key = max(sleepers)
        row = now[key]
        sleeper = {"name": row["name"], "winRate": _pct(row["playedWinRate"]),
                   "share": _pct(row["share"]), "games": row["playedGames"]}
    index = {k: [_pct(r["share"]), _pct(r["playedWinRate"])] for k, r in now.items()}
    return {
        "available": True,
        "totalGames": body.get("totalGames"),
        "releasedThrough": released,
        "rising": rising,
        "falling": falling,
        "sleeper": sleeper,
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
            if deck.get("deck_id"):
                candidates.append((place, day, ev, deck))
    events.sort(key=lambda e: e["date"], reverse=True)

    # Deck to try: a public Top 8 list from the archetype that climbed most.
    rank = {(a["avatar"], a["elements"]): (a["move"] if isinstance(a.get("move"), int) else 1, -TIERS.index(a["tier"]))
            for a in archetypes}
    pick = None
    best = None
    for place, day, ev, deck in candidates:
        key = (deck.get("avatar"), _pair(deck.get("elements")))
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
    return {"events": events, "deckToTry": deck_to_try}


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
            "headline": f"{top['avatar']} in {top['elements']} is the deck to beat.",
            "detail": f"{top['winRate']}% win rate on {top['share']}% of decks.",
        })
        quiet = [a for a in archetypes[1:] if a["share"] < 6 and a["games"] >= 20]
        if quiet:
            q = max(quiet, key=lambda a: a["winRate"])
            if q["winRate"] > 50:
                story.append({
                    "headline": f"{q['avatar']} in {q['elements']} is the best deck few people play.",
                    "detail": f"{q['winRate']}% win rate on only {q['share']}% of decks.",
                })
        climbers = [a for a in archetypes if isinstance(a.get("move"), int) and a["move"] > 0]
        if climbers and len(story) < 2:
            c = max(climbers, key=lambda a: a["move"])
            story.append({
                "headline": f"{c['avatar']} in {c['elements']} climbs to {c['tier']} tier.",
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
    ranked = archetype_stats(games)
    previous = archetype_stats(ranked_games(pf, pt, db_path))
    _with_moves(ranked["archetypes"], previous["archetypes"])
    ranked["matchups"] = matchup_grid(games, ranked["archetypes"])

    history = repo.published_before(f, limit=4)
    cards = card_section(pso(f, t), pso(pf, pt), history, t)
    tournaments = tournament_section(f, t, ranked["archetypes"])
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


def post_to_discord(report: dict) -> bool:
    from routes.api.matchmaking import relay_to_bot

    payload = report.get("payload") or {}
    archetypes = (payload.get("ranked") or {}).get("archetypes") or []
    body = {
        "title": f"Meta Report: {payload.get('period', {}).get('label', report['slug'])}",
        "url": report_url(report["slug"]),
        "story": report.get("story") or [],
        "topTier": [f"{a['avatar']} ({a['elements']})" for a in archetypes if a.get("tier") == "S"][:4],
        "rankedGames": (payload.get("ranked") or {}).get("rankedGames"),
        "events": len((payload.get("tournaments") or {}).get("events") or []),
    }
    result, status = relay_to_bot("POST", "/meta-report-notify", body, {"status": "unavailable"}, timeout=10)
    if status >= 300:
        logger.warning("Meta report Discord post failed (%s): %s", status, result)
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
    today = today or today_eastern()
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
