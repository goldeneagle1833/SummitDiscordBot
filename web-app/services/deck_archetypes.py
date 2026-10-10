"""Groups decks into archetypes for the Deck Archetypes page.

Two snapshots are built from the same load:
  "tournament" — decks from tournaments only (the Top 8 page plus seed events)
  "all"        — those plus every deck reported in a ranked match

How decks are compared
----------------------
Each deck becomes a set of weighted features, one per copy of each card in its
spellbook, atlas and collection ("3x Grapple Shot" is three features). Two decks
are compared with weighted Jaccard similarity: the weight of the features they
share divided by the weight of the features either has. Copies are capped at
MAX_COPIES so a stack of one card can't dominate.

Feature weights:
  - zone: spellbook cards count fully, atlas and collection cards count less
    (ZONE_WEIGHTS), because sites and collections overlap a lot between
    unrelated decks.
  - rarity in the corpus: a card most decks play says little about the deck,
    so its weight is scaled by how rare it is across the loaded decks
    (inverse document frequency), mapped into [RARITY_MIN, RARITY_MAX] so no
    single card swings the score.

How decks are grouped
---------------------
Decks are only grouped with decks of the same Avatar and the same element
pair (their top two elements by Spellbook copies), so every archetype is one
"Avatar · Elements" identity. Within each, average-linkage agglomerative clustering repeatedly merges the two most similar
groups (similarity of two groups = the mean similarity of all their deck pairs)
until no two groups are at least SIMILARITY_THRESHOLD alike.
"""

import fcntl
import logging
import math
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

from services.curiosa import get_curiosa_deck_id
from utils.card_images import resolve_card_image
from repositories.archetype_decks import ZONES, ArchetypeDeck, ArchetypeDeckRepository, TournamentEntry

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.35
MAX_COPIES = 4
ZONE_WEIGHTS = {"spellbook": 1.0, "atlas": 0.5, "collection": 0.5}
RARITY_MIN = 0.5
RARITY_MAX = 1.5
# Card patterns listed per zone on an archetype's detail panel.
PATTERN_LIMIT = 40
# Decks listed on an archetype's detail panel.
MEMBER_LIMIT = 500
# A ranked deck needs this many games before it can be "Best on ranked".
RANKED_PICK_MIN_GAMES = 5

SOURCES = ("all", "tournament")


# ---------------------------------------------------------------------- #
# Similarity                                                              #
# ---------------------------------------------------------------------- #


def _deck_features(deck: ArchetypeDeck, vocab: dict) -> list[int]:
    features = []
    for zone in ZONES:
        for name, copies in deck.cards.get(zone, {}).items():
            for copy in range(1, min(copies, MAX_COPIES) + 1):
                key = (zone, name.lower(), copy)
                index = vocab.get(key)
                if index is None:
                    index = vocab[key] = len(vocab)
                features.append(index)
    return features


def _feature_weights(vocab: dict, deck_features: list[list[int]]) -> np.ndarray:
    """Zone weight x capped rarity weight for every feature in the vocabulary."""
    n = max(1, len(deck_features))
    df = np.zeros(len(vocab), dtype=np.float64)
    for features in deck_features:
        df[features] += 1
    idf = np.log((1 + n) / (1 + df))
    top = math.log(1 + n) or 1.0
    rarity = RARITY_MIN + (RARITY_MAX - RARITY_MIN) * np.clip(idf / top, 0.0, 1.0)
    zone = np.empty(len(vocab), dtype=np.float64)
    for (zone_name, _card, _copy), index in vocab.items():
        zone[index] = ZONE_WEIGHTS[zone_name]
    return (zone * rarity).astype(np.float32)


def similarity_matrix(feature_lists: list[list[int]], weights: np.ndarray) -> np.ndarray:
    """Pairwise weighted Jaccard similarity, diagonal included (1.0)."""
    n = len(feature_lists)
    if n == 0:
        return np.zeros((0, 0), dtype=np.float32)
    totals = np.array([weights[f].sum() for f in feature_lists], dtype=np.float32)

    # Only features two or more decks share can add to an intersection; the
    # rest only add to each deck's total, which is already counted.
    counts = Counter(i for f in feature_lists for i in f)
    shared = sorted(i for i, c in counts.items() if c > 1)
    if not shared:
        sim = np.zeros((n, n), dtype=np.float32)
        np.fill_diagonal(sim, 1.0)
        return sim
    column = {feature: col for col, feature in enumerate(shared)}
    x = np.zeros((n, len(shared)), dtype=np.float32)
    for row, features in enumerate(feature_lists):
        cols = [column[f] for f in features if f in column]
        x[row, cols] = 1.0
    inter = (x * weights[shared]) @ x.T
    union = totals[:, None] + totals[None, :] - inter
    with np.errstate(divide="ignore", invalid="ignore"):
        sim = np.where(union > 0, inter / union, 0.0).astype(np.float32)
    np.fill_diagonal(sim, 1.0)
    return sim


def cluster(sim: np.ndarray, threshold: float = SIMILARITY_THRESHOLD) -> list[list[int]]:
    """Average-linkage agglomerative clustering; returns groups of row indices."""
    n = sim.shape[0]
    if n <= 1:
        return [list(range(n))]
    s = sim.astype(np.float64, copy=True)
    np.fill_diagonal(s, -np.inf)
    sizes = np.ones(n)
    members = {i: [i] for i in range(n)}
    best = s.argmax(axis=1)
    best_val = s[np.arange(n), best]

    while members:
        i = int(best_val.argmax())
        if best_val[i] < threshold:
            break
        j = int(best[i])
        # Merge j into i (Lance-Williams update for average linkage).
        merged = (sizes[i] * s[i] + sizes[j] * s[j]) / (sizes[i] + sizes[j])
        s[i, :] = merged
        s[:, i] = merged
        s[i, i] = -np.inf
        s[j, :] = -np.inf
        s[:, j] = -np.inf
        sizes[i] += sizes[j]
        members[i].extend(members.pop(j))
        best_val[j] = -np.inf

        # Rows whose best partner was i or j must look again; others only
        # need to know if the merged group is now their best.
        stale = np.where((best == i) | (best == j))[0]
        for k in stale:
            if k == j:
                continue
            best[k] = s[k].argmax()
            best_val[k] = s[k, best[k]]
        improved = s[:, i] > best_val
        improved[i] = False
        best[improved] = i
        best_val[improved] = s[improved, i]
        best[i] = s[i].argmax()
        best_val[i] = s[i, best[i]]
    return list(members.values())


# ---------------------------------------------------------------------- #
# Archetype summaries                                                     #
# ---------------------------------------------------------------------- #
#
# Clustering runs once per build over every deck. Filters (date range,
# minimum event size) don't regroup decks; they decide which of a group's
# decks, tournament results and ranked games count, so a group's numbers
# and its place in the list change while its identity stays put.


@dataclass(frozen=True)
class Filters:
    start: str | None = None  # ISO date, inclusive
    end: str | None = None  # ISO date, inclusive
    min_event_decks: int = 0

    @property
    def dated(self) -> bool:
        return bool(self.start or self.end)

    def keeps_entry(self, entry: TournamentEntry) -> bool:
        if entry.event_size < self.min_event_decks:
            return False
        if not self.dated:
            return True
        span = entry.date_span()
        if span is None:
            return False
        first, last = span
        return (not self.start or last >= self.start) and (not self.end or first <= self.end)

    def keeps_day(self, day: str | None) -> bool:
        if not self.dated:
            return True
        if not day:
            return False
        return (not self.start or day >= self.start) and (not self.end or day <= self.end)


NO_FILTERS = Filters()


@dataclass
class DeckView:
    """One deck with only the results the current filters count."""

    deck: ArchetypeDeck
    entries: list
    wins: int
    losses: int
    players: Counter

    @property
    def key(self) -> str:
        return self.deck.key

    @property
    def games(self) -> int:
        return self.wins + self.losses

    @property
    def best_placement(self) -> int | None:
        known = [e.placement for e in self.entries if e.placement is not None]
        return min(known) if known else None


def view_deck(deck: ArchetypeDeck, filters: Filters, with_ranked: bool) -> DeckView | None:
    """The deck as `filters` see it, or None if nothing about it is left to count."""
    entries = [e for e in deck.entries if filters.keeps_entry(e)]
    wins = losses = 0
    players: Counter = Counter()
    if with_ranked:
        for game in deck.games:
            if filters.keeps_day(game.day):
                if game.won:
                    wins += 1
                else:
                    losses += 1
                if game.player:
                    players[game.player] += 1
    if not entries and not (wins or losses):
        return None
    return DeckView(deck, entries, wins, losses, players)


def deck_to_dict(view: DeckView) -> dict:
    deck = view.deck
    out = {
        "id": deck.key,
        "name": deck.name or "Unnamed deck",
        "url": deck.url,
        # Deck Rec opens any sorcerytcg.com list by id; PSO and unlinked decks have none.
        "deckRecId": get_curiosa_deck_id(deck.url) if deck.url else None,
        "avatar": deck.avatar,
        "elements": deck.elements,
        "entries": [e.to_dict() for e in view.entries],
    }
    if view.games:
        out["ranked"] = {
            "wins": view.wins,
            "losses": view.losses,
            "player": view.players.most_common(1)[0][0] if view.players else None,
        }
    return out


def _patterns(decks: list[ArchetypeDeck]) -> dict:
    n = len(decks)
    out = {}
    for zone in ZONES:
        present: Counter = Counter()
        copies: Counter = Counter()
        for deck in decks:
            for name, qty in deck.cards.get(zone, {}).items():
                present[name] += 1
                copies[name] += qty
        rows = [
            {
                "name": name,
                "count": count,
                "rate": round(count / n, 4),
                "avgCopies": round(copies[name] / count, 1),
            }
            for name, count in present.items()
        ]
        rows.sort(key=lambda r: (-r["count"], r["name"]))
        rows = rows[:PATTERN_LIMIT]
        for row in rows:
            row["image"] = resolve_card_image(row["name"])
        out[zone] = rows
    return out


@dataclass
class Cluster:
    id: str
    avatar: str
    elements: str
    decks: list  # most central first


def summarize(cluster_: Cluster, views: list[DeckView]) -> dict:
    """The list entry for one archetype; `views` keep the cluster's central-first order."""
    events = {e.event for v in views for e in v.entries}
    ranked_wins = sum(v.wins for v in views)
    ranked_losses = sum(v.losses for v in views)
    ranked_games = ranked_wins + ranked_losses
    return {
        "id": cluster_.id,
        "name": f"{cluster_.avatar} · {cluster_.elements}",
        "avatar": cluster_.avatar,
        "avatars": [[cluster_.avatar, len(views)]],
        "elements": [[cluster_.elements, len(views)]],
        "elementsLabel": cluster_.elements,
        "size": len(views),
        "tournamentDecks": sum(1 for v in views if v.entries),
        "wins": sum(1 for v in views if v.best_placement == 1),
        "top8": sum(1 for v in views if any(e.top8 for e in v.entries)),
        "topCut": sum(1 for v in views if any(e.top_cut for e in v.entries)),
        "events": len(events),
        "rankedGames": ranked_games,
        "rankedWins": ranked_wins,
        "rankedLosses": ranked_losses,
        "rankedWinRate": round(ranked_wins / ranked_games, 4) if ranked_games else None,
        "players": len({e.player for v in views for e in v.entries} | {p for v in views for p in v.players}),
    }


def detail(views: list[DeckView]) -> dict:
    """Cards, picks and decks for one archetype's panel.

    Recommended lists only come from decks on the Top 8 page."""
    top8_page = [v for v in views if v.deck.on_top8_page and v.entries]
    picks = [(top8_page[0], "Representative deck")] if top8_page else []
    placed = [v for v in top8_page if v.best_placement is not None]
    if placed:
        # min() keeps the first of equals, and views are central-first.
        finisher = min(placed, key=lambda v: v.best_placement)
        picks.append((finisher, f"Best finish: #{finisher.best_placement}"))
    ranked = [v for v in top8_page if v.games >= RANKED_PICK_MIN_GAMES and v.wins > v.losses]
    if ranked:
        top = max(ranked, key=lambda v: (v.wins - v.losses, v.games))
        picks.append((top, f"Best on ranked: {top.wins}-{top.losses}"))
    recommendations, seen = [], set()
    for view, label in picks:
        if view.key in seen:
            continue
        seen.add(view.key)
        recommendations.append({"deckId": view.key, "label": label})

    listed = sorted(
        views,
        key=lambda v: (v.best_placement or 999, -v.games, (v.deck.name or "").lower()),
    )[:MEMBER_LIMIT]
    listed_keys = {v.key for v in listed}
    shown = listed + [v for v in views if v.key in seen and v.key not in listed_keys]
    return {
        "patterns": _patterns([v.deck for v in views]),
        "recommendations": recommendations,
        "members": [v.key for v in listed],
        "decks": {v.key: deck_to_dict(v) for v in shown},
    }


def _cluster_views(snapshot: dict, cluster_: Cluster, filters: Filters) -> list[DeckView]:
    with_ranked = snapshot["meta"]["source"] == "all"
    views = [v for v in (view_deck(d, filters, with_ranked) for d in cluster_.decks) if v]
    # A lone ranked deck that matches nothing else isn't an archetype.
    if with_ranked and len(views) == 1 and not views[0].entries and len(cluster_.decks) == 1:
        return []
    return views


def filtered_list(snapshot: dict, filters: Filters = NO_FILTERS) -> dict:
    """{meta, groups} with every count limited to what `filters` keep."""
    groups = []
    events: set[str] = set()
    tournament_decks = ranked_decks = 0
    for cluster_ in snapshot["clusters"]:
        views = _cluster_views(snapshot, cluster_, filters)
        if not views:
            continue
        groups.append(summarize(cluster_, views))
        for v in views:
            events.update(e.event for e in v.entries)
            tournament_decks += 1 if v.entries else 0
            ranked_decks += 1 if v.games else 0
    groups.sort(key=lambda g: (-g["size"], g["name"]))
    meta = {
        **snapshot["meta"],
        "tournamentCount": len(events),
        "tournamentDecks": tournament_decks,
        "rankedDecks": ranked_decks,
        "rankedGames": sum(1 for day in snapshot["game_days"] if filters.keeps_day(day)),
        "fetchedDecks": sum(g["size"] for g in groups),
        "archetypes": len(groups),
        "filters": {"from": filters.start, "to": filters.end, "minEventDecks": filters.min_event_decks},
    }
    return {"meta": meta, "groups": groups}


def filtered_detail(snapshot: dict, group_id: str, filters: Filters = NO_FILTERS) -> dict | None:
    cluster_ = snapshot["by_id"].get(group_id)
    if cluster_ is None:
        return None
    views = _cluster_views(snapshot, cluster_, filters)
    return detail(views) if views else None


def build_snapshot(decks: list[ArchetypeDeck], meta: dict, game_days: list | None = None) -> dict:
    """Cluster `decks`; numbers are worked out per request by filtered_list()."""
    started = time.monotonic()
    vocab: dict = {}
    features = [_deck_features(d, vocab) for d in decks]
    weights = _feature_weights(vocab, features)

    by_identity: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, deck in enumerate(decks):
        by_identity[(deck.avatar, deck.elements)].append(i)

    clusters = []
    for (avatar, elements), indices in by_identity.items():
        sim = similarity_matrix([features[i] for i in indices], weights)
        for local in cluster(sim):
            sub = sim[np.ix_(local, local)]
            centrality = sub.mean(axis=1) if len(local) > 1 else np.ones(1)
            order = np.argsort(-centrality, kind="stable")
            members = [decks[indices[local[int(k)]]] for k in order]
            slug = f"{avatar}-{elements}".lower().replace(" / ", "-").replace(" ", "-")
            clusters.append(Cluster(f"{slug}-{members[0].key}", avatar, elements, members))

    snapshot = {
        "meta": {
            **meta,
            "generated": datetime.now(timezone.utc).isoformat(),
            "threshold": SIMILARITY_THRESHOLD,
        },
        "clusters": clusters,
        "by_id": {c.id: c for c in clusters},
        "game_days": game_days or [],
    }
    logger.info("Grouped %d decks into %d clusters in %.1fs", len(decks), len(clusters), time.monotonic() - started)
    return snapshot


def build_snapshots(repo: ArchetypeDeckRepository | None = None) -> dict[str, dict]:
    """Load every source once and build both snapshots."""
    repo = repo or ArchetypeDeckRepository()
    tournament, _tournament_events = repo.load_tournament_decks()
    seeds, _seed_events, pending, unavailable = repo.load_seed_decks()
    ranked, game_days = repo.load_ranked_decks()

    merged: dict[str, ArchetypeDeck] = dict(tournament)
    for key, deck in seeds.items():
        if key in merged:
            merged[key].entries.extend(deck.entries)
        else:
            merged[key] = deck
    tournament_keys = set(merged)
    for key, deck in ranked.items():
        if key in merged:
            merged[key].games.extend(deck.games)
        else:
            merged[key] = deck

    base_meta = {
        "pendingDecks": len(pending),
        "unavailableDecks": unavailable,
    }
    return {
        "tournament": build_snapshot(
            [merged[k] for k in sorted(tournament_keys)], {**base_meta, "source": "tournament"}
        ),
        "all": build_snapshot(list(merged.values()), {**base_meta, "source": "all"}, game_days),
    }


# ---------------------------------------------------------------------- #
# Cache                                                                   #
# ---------------------------------------------------------------------- #
#
# Loading the ranked archive and clustering takes seconds, so it never happens
# on a request. The first request starts a build and gets "building"; after
# that a stale snapshot keeps being served while a fresh one builds.

CACHE_TTL = 3600

_snapshots: dict[str, dict] | None = None
_snapshots_time = 0.0
_lock = threading.Lock()
_building = False


def _build_in_background() -> None:
    global _building
    with _lock:
        if _building:
            return
        _building = True

    def run() -> None:
        global _snapshots, _snapshots_time, _building
        try:
            _snapshots = build_snapshots()
            start_seed_backfill(_snapshots["all"]["meta"]["pendingDecks"])
        except Exception:
            logger.exception("Deck archetype build failed; serving the previous snapshot")
        finally:
            _snapshots_time = time.monotonic()
            _building = False

    threading.Thread(target=run, name="deck-archetypes-build", daemon=True).start()


def get_snapshot(source: str) -> dict | None:
    """The current snapshot for `source`, or None while the first one builds."""
    snapshots = _snapshots
    if snapshots is None or (time.monotonic() - _snapshots_time) >= CACHE_TTL:
        _build_in_background()
    return snapshots.get(source) if snapshots else None


# Filtered views are cheap but not free (every ranked game is checked), so
# recent ones are kept per snapshot.
_VIEW_CACHE_SIZE = 64
_view_cache: dict = {}


def _cached(kind: str, snapshot: dict, filters: Filters, key, make):
    cache_key = (kind, snapshot["meta"]["source"], snapshot["meta"]["generated"], filters, key)
    hit = _view_cache.get(cache_key)
    if hit is None:
        hit = make()
        if len(_view_cache) >= _VIEW_CACHE_SIZE:
            _view_cache.pop(next(iter(_view_cache)))
        _view_cache[cache_key] = hit
    return hit


def get_list(source: str, filters: Filters = NO_FILTERS) -> dict | None:
    """{meta, groups} for `source` under `filters`, or None while the first build runs."""
    snapshot = get_snapshot(source)
    if snapshot is None:
        return None
    return _cached("list", snapshot, filters, None, lambda: filtered_list(snapshot, filters))


def get_detail(source: str, group_id: str, filters: Filters = NO_FILTERS) -> dict | None:
    """One archetype's panel, {} if the group is unknown or empty, None while building."""
    snapshot = get_snapshot(source)
    if snapshot is None:
        return None
    return _cached("detail", snapshot, filters, group_id,
                   lambda: filtered_detail(snapshot, group_id, filters) or {})


def is_building() -> bool:
    return _building


def warm_cache() -> None:
    _build_in_background()


def invalidate() -> None:
    """Rebuild on the next request, keeping the current snapshot until then."""
    global _snapshots_time
    _snapshots_time = 0.0


# ---------------------------------------------------------------------- #
# Seed backfill                                                           #
# ---------------------------------------------------------------------- #
#
# The seed events' card lists come from sorcerytcg.com, which allows one
# request every CURIOSA_REQUEST_DELAY seconds. They are fetched once, on a
# background thread, by whichever worker takes the lock file first, and
# written to the cache file as they arrive. Each rebuild picks up whatever has
# been fetched so far.

_backfill_started = False


def start_seed_backfill(pending: int, repo: ArchetypeDeckRepository | None = None) -> None:
    global _backfill_started
    if not pending or _backfill_started:
        return
    _backfill_started = True
    repo = repo or ArchetypeDeckRepository()

    def run() -> None:
        global _backfill_started
        lock_path = repo._seed_cache_path.with_suffix(".lock")
        try:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            with open(lock_path, "w") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return  # another worker is fetching
                from services.curiosa import CuriosaService

                service = CuriosaService()
                fetched = 0
                while True:
                    _decks, _events, todo, _unavailable = repo.load_seed_decks()
                    if not todo:
                        break
                    deck_id = todo[0]
                    raw = service.fetch_deck_by_id(deck_id)
                    repo.save_seed_cache_entry(deck_id, raw if raw else {"unavailable": True})
                    fetched += 1
                    if fetched % 25 == 0:
                        invalidate()
                logger.info("Deck archetype seed backfill finished (%d decks fetched)", fetched)
                invalidate()
        except Exception:
            logger.exception("Deck archetype seed backfill stopped")
        finally:
            _backfill_started = False

    threading.Thread(target=run, name="deck-archetypes-seed-backfill", daemon=True).start()
