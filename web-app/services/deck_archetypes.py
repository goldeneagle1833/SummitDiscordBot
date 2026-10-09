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
from datetime import datetime, timezone

import numpy as np

from repositories.archetype_decks import ZONES, ArchetypeDeck, ArchetypeDeckRepository

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


def _best_placement(deck: ArchetypeDeck) -> int | None:
    known = [e.placement for e in deck.entries if e.placement is not None]
    return min(known) if known else None


def deck_to_dict(deck: ArchetypeDeck) -> dict:
    out = {
        "id": deck.key,
        "name": deck.name or "Unnamed deck",
        "url": deck.url,
        "avatar": deck.avatar,
        "elements": deck.elements,
        "entries": [e.to_dict() for e in deck.entries],
    }
    if deck.ranked_games:
        out["ranked"] = {
            "wins": deck.ranked_wins,
            "losses": deck.ranked_losses,
            "player": deck.ranked_players.most_common(1)[0][0] if deck.ranked_players else None,
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
        out[zone] = rows[:PATTERN_LIMIT]
    return out


def _summarize(decks: list[ArchetypeDeck], sim: np.ndarray) -> tuple[dict, dict]:
    """(list entry, detail) for one archetype. `sim` is the members' similarity matrix."""
    centrality = sim.mean(axis=1) if len(decks) > 1 else np.ones(1)
    order = np.argsort(-centrality, kind="stable")
    representative = decks[int(order[0])]

    avatars = Counter(d.avatar for d in decks)
    elements = Counter(d.elements for d in decks)
    elements_label = elements.most_common(1)[0][0]
    avatar = avatars.most_common(1)[0][0]

    events = {e.event for d in decks for e in d.entries}
    ranked_wins = sum(d.ranked_wins for d in decks)
    ranked_losses = sum(d.ranked_losses for d in decks)
    ranked_games = ranked_wins + ranked_losses

    summary = {
        "id": f"{avatar.lower().replace(' ', '-')}-{elements_label.lower().replace(' / ', '-')}-{representative.key}",
        "name": f"{avatar} · {elements_label}",
        "avatar": avatar,
        "avatars": avatars.most_common(),
        "elements": elements.most_common(),
        "elementsLabel": elements_label,
        "size": len(decks),
        "tournamentDecks": sum(1 for d in decks if d.is_tournament),
        "wins": sum(1 for d in decks if _best_placement(d) == 1),
        "top8": sum(1 for d in decks if any(e.top8 for e in d.entries)),
        "topCut": sum(1 for d in decks if any(e.top_cut for e in d.entries)),
        "events": len(events),
        "rankedGames": ranked_games,
        "rankedWins": ranked_wins,
        "rankedLosses": ranked_losses,
        "rankedWinRate": round(ranked_wins / ranked_games, 4) if ranked_games else None,
        "players": len({e.player for d in decks for e in d.entries}
                       | {p for d in decks for p in d.ranked_players}),
    }

    picks = [(representative, "Representative deck")]
    placed = [d for d in decks if _best_placement(d) is not None]
    if placed:
        rank = {d.key: i for i, d in enumerate(decks[int(k)] for k in order)}
        finisher = min(placed, key=lambda d: (_best_placement(d), rank[d.key]))
        picks.append((finisher, f"Best finish: #{_best_placement(finisher)}"))
    ranked = [d for d in decks if d.ranked_games >= RANKED_PICK_MIN_GAMES and d.ranked_wins > d.ranked_losses]
    if ranked:
        top = max(ranked, key=lambda d: (d.ranked_wins - d.ranked_losses, d.ranked_games))
        picks.append((top, f"Best on ranked: {top.ranked_wins}-{top.ranked_losses}"))
    recommendations, seen = [], set()
    for deck, label in picks:
        if deck.key in seen:
            continue
        seen.add(deck.key)
        recommendations.append({"deckId": deck.key, "label": label})

    listed = sorted(
        decks,
        key=lambda d: (
            _best_placement(d) or 999,
            -d.ranked_games,
            (d.name or "").lower(),
        ),
    )[:MEMBER_LIMIT]
    picked = {r["deckId"] for r in recommendations}
    shown = listed + [d for d in decks if d.key in picked and d not in listed]
    detail = {
        "patterns": _patterns(decks),
        "recommendations": recommendations,
        "members": [d.key for d in listed],
        "decks": {d.key: deck_to_dict(d) for d in shown},
    }
    return summary, detail


def build_snapshot(decks: list[ArchetypeDeck], meta: dict, keep_singletons: bool) -> dict:
    """Cluster `decks` and summarize every archetype."""
    started = time.monotonic()
    vocab: dict = {}
    features = [_deck_features(d, vocab) for d in decks]
    weights = _feature_weights(vocab, features)

    by_identity: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, deck in enumerate(decks):
        by_identity[(deck.avatar, deck.elements)].append(i)

    groups, details = [], {}
    for indices in by_identity.values():
        sim = similarity_matrix([features[i] for i in indices], weights)
        for local in cluster(sim):
            members = [decks[indices[k]] for k in local]
            if len(members) == 1 and not keep_singletons and not members[0].is_tournament:
                continue
            summary, detail = _summarize(members, sim[np.ix_(local, local)])
            groups.append(summary)
            details[summary["id"]] = detail

    groups.sort(key=lambda g: (-g["size"], g["name"]))
    meta = {
        **meta,
        "generated": datetime.now(timezone.utc).isoformat(),
        "threshold": SIMILARITY_THRESHOLD,
        "fetchedDecks": len(decks),
        "archetypes": len(groups),
    }
    logger.info("Built %d archetypes from %d decks in %.1fs", len(groups), len(decks), time.monotonic() - started)
    return {"meta": meta, "groups": groups, "details": details}


def build_snapshots(repo: ArchetypeDeckRepository | None = None) -> dict[str, dict]:
    """Load every source once and build both snapshots."""
    repo = repo or ArchetypeDeckRepository()
    tournament, tournament_events = repo.load_tournament_decks()
    seeds, seed_events, pending, unavailable = repo.load_seed_decks()
    ranked, ranked_games = repo.load_ranked_decks()

    merged: dict[str, ArchetypeDeck] = dict(tournament)
    for key, deck in seeds.items():
        if key in merged:
            merged[key].entries.extend(deck.entries)
        else:
            merged[key] = deck
    tournament_keys = set(merged)
    for key, deck in ranked.items():
        if key in merged:
            target = merged[key]
            target.ranked_wins += deck.ranked_wins
            target.ranked_losses += deck.ranked_losses
            target.ranked_players.update(deck.ranked_players)
        else:
            merged[key] = deck

    base_meta = {
        "tournamentCount": tournament_events + len(seed_events),
        "tournamentDecks": len(tournament_keys),
        "rankedDecks": len(ranked),
        "rankedGames": ranked_games,
        "pendingDecks": len(pending),
        "unavailableDecks": unavailable,
    }
    all_decks = list(merged.values())
    return {
        "tournament": build_snapshot(
            [merged[k] for k in sorted(tournament_keys)], {**base_meta, "source": "tournament"}, True
        ),
        "all": build_snapshot(all_decks, {**base_meta, "source": "all"}, False),
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
