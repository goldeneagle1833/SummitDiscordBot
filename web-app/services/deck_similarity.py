"""Deck similarity service for Sorcery Deck Rec feature.

Provides Jaccard-based clustering of community decks around top-8 archetype seeds,
and aggregates card frequency statistics across each cluster.
"""

import logging
from array import array
from collections import Counter
from itertools import chain
from typing import Iterator

from repositories.deck_rec_repo import DeckRecord

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.3


# ------------------------------------------------------------------ #
# Core similarity math                                                #
# ------------------------------------------------------------------ #


def jaccard(set_a: frozenset, set_b: frozenset) -> float:
    """Compute Jaccard similarity between two card sets.

    Returns |A ∩ B| / |A ∪ B|, or 0.0 if the union is empty.

    Derived from the intersection alone — |A ∪ B| == |A| + |B| - |A ∩ B| — so
    only one set has to be materialised instead of two.
    """
    shared = len(set_a & set_b)
    union = len(set_a) + len(set_b) - shared
    if union == 0:
        return 0.0
    return shared / union


# ------------------------------------------------------------------ #
# Inverted card index                                                 #
# ------------------------------------------------------------------ #
#
# Scoring one deck against every deck in a corpus is the hot path behind both
# clustering and the per-archetype recommendation query. Done pairwise it costs
# len(corpus) set intersections; at production scale (~800 seeds, ~17k community
# decks) that is over 13 million of them and takes the better part of a minute.
#
# An inverted card name -> position index turns it into a single pass over the
# querying deck's ~50 cards: the Counter tallies how many cards each corpus deck
# shares, which is exactly the intersection size, and corpus decks sharing no
# card are never visited at all. Results are identical, an order of magnitude
# cheaper.


def build_card_index(decks: list[DeckRecord]) -> tuple[dict[str, array], array]:
    """Return (card_name -> positions in `decks`, card count per deck).

    Positions go in int arrays rather than lists: the corpus runs to 17k decks
    of ~50 cards each, and that is a few MB of difference for a fraction of a
    millisecond per query. The keys are the interned card names the decks
    already hold, so the index adds no strings of its own.
    """
    index: dict[str, array] = {}
    lengths = array("i")
    for position, deck in enumerate(decks):
        lengths.append(len(deck.card_names))
        for card_name in deck.card_names:
            postings = index.get(card_name)
            if postings is None:
                postings = index[card_name] = array("i")
            postings.append(position)
    return index, lengths


def score_against_index(
    card_names: frozenset,
    index: dict[str, array],
    lengths: array,
) -> Iterator[tuple[int, float]]:
    """Yield (position, jaccard) for every indexed deck sharing at least one card.

    Decks sharing nothing score 0.0 and are simply not yielded.
    """
    size = len(card_names)
    if not size:
        return
    shared_counts = Counter(chain.from_iterable(index.get(name, ()) for name in card_names))
    for position, shared in shared_counts.items():
        union = size + lengths[position] - shared
        if union:
            yield position, shared / union


# ------------------------------------------------------------------ #
# Clustering                                                          #
# ------------------------------------------------------------------ #


def build_clusters(
    seeds: list[DeckRecord],
    community: list[DeckRecord],
    threshold: float = SIMILARITY_THRESHOLD,
) -> dict[str, list[DeckRecord]]:
    """Assign each community deck to its most similar top-8 seed.

    Each community deck is assigned to exactly one seed (the highest-scoring
    match). Decks that score below threshold against all seeds are excluded.

    Args:
        seeds: Top-8 tournament decks acting as archetype anchors.
        community: Community decks from the match archive.
        threshold: Minimum Jaccard score for cluster membership (default 0.3).

    Returns:
        Dict mapping seed deck_id → list of matching community DeckRecords.
    """
    clusters: dict[str, list[DeckRecord]] = {s.deck_id: [] for s in seeds}

    if not seeds:
        return clusters

    seed_index, seed_lengths = build_card_index(seeds)

    for deck in community:
        best_position = len(seeds)
        best_score = 0.0

        for position, score in score_against_index(deck.card_names, seed_index, seed_lengths):
            # Ties go to the earlier seed, so a deck's archetype doesn't depend
            # on the order the index happened to visit equally good matches in.
            if score > best_score or (score == best_score and 0 <= position < best_position):
                best_position = position
                best_score = score

        if best_position < len(seeds) and best_score >= threshold:
            clusters[seeds[best_position].deck_id].append(deck)

    total_assigned = sum(len(v) for v in clusters.values())
    logger.info(
        "Clustered %d community decks across %d seeds (threshold=%.2f)",
        total_assigned,
        len(seeds),
        threshold,
    )
    return clusters


# ------------------------------------------------------------------ #
# Archetype aggregation                                               #
# ------------------------------------------------------------------ #

TIER_CORE = "core"
TIER_COMMON = "common"
TIER_TECH = "tech"
TIER_FRINGE = "fringe"


def aggregate_archetype(members: list[DeckRecord]) -> dict:
    """Compute card inclusion rates across all cluster members.

    Cards are grouped into four tiers by inclusion rate:
      - core   : >= 80%
      - common : 50–79%
      - tech   : 20–49%
      - fringe : 5–19%  (cards below 5% are excluded)

    Args:
        members: Community decks in the cluster (excludes the seed itself).

    Returns:
        Dict with keys "core", "common", "tech", "fringe", each containing
        a list of {card_name, count, inclusion_rate, inclusion_pct, tier}
        sorted descending by inclusion_rate.
    """
    empty = {TIER_CORE: [], TIER_COMMON: [], TIER_TECH: [], TIER_FRINGE: []}

    if not members:
        return empty

    n = len(members)
    # presence_counter: how many decks include each card (for inclusion rate)
    presence_counter: Counter = Counter()
    # total_copies_counter: total copies summed across all decks
    total_copies_counter: Counter = Counter()
    for deck in members:
        presence_counter.update(deck.card_names)  # frozenset — each card once per deck
        if deck.card_quantities:
            total_copies_counter.update(deck.card_quantities)
        else:
            total_copies_counter.update(deck.card_names)  # fallback: 1 copy per deck

    tiers: dict[str, list] = {
        TIER_CORE: [],
        TIER_COMMON: [],
        TIER_TECH: [],
        TIER_FRINGE: [],
    }

    for card_name, count in presence_counter.items():
        rate = count / n
        pct = f"{round(rate * 100)}%"
        total_copies = total_copies_counter.get(card_name, count)
        avg_copies = round(total_copies / count, 2)  # avg among decks that play it

        if rate >= 0.8:
            tier = TIER_CORE
        elif rate >= 0.5:
            tier = TIER_COMMON
        elif rate >= 0.2:
            tier = TIER_TECH
        elif rate >= 0.05:
            tier = TIER_FRINGE
        else:
            continue  # skip cards below 5% inclusion

        tiers[tier].append(
            {
                "card_name": card_name.title(),  # restore readable casing
                "count": count,
                "inclusion_rate": round(rate, 4),
                "inclusion_pct": pct,
                "avg_copies": avg_copies,
                "tier": tier,
            }
        )

    # Sort each tier descending by inclusion rate, ties alphabetical so the
    # card order on a deck page stays put between rebuilds.
    for tier_list in tiers.values():
        tier_list.sort(key=lambda x: (-x["inclusion_rate"], x["card_name"]))

    return tiers


# ------------------------------------------------------------------ #
# Convenience helpers                                                 #
# ------------------------------------------------------------------ #


def similar_members(
    seed: DeckRecord,
    community: list[DeckRecord],
    index: dict[str, list[int]],
    lengths: list[int],
    threshold: float = SIMILARITY_THRESHOLD,
) -> list[tuple[DeckRecord, float]]:
    """Return (deck, score) for every community deck at or above threshold to seed.

    Inclusive matching — a deck can qualify for several archetypes, unlike
    build_clusters() which assigns each deck to its single best seed.
    """
    return [
        (community[position], score)
        for position, score in score_against_index(seed.card_names, index, lengths)
        if score >= threshold
    ]


def average_similarity(seed: DeckRecord, members: list[DeckRecord]) -> float:
    """Compute mean Jaccard similarity of cluster members to the seed."""
    if not members:
        return 0.0
    scores = [jaccard(seed.card_names, m.card_names) for m in members]
    return round(sum(scores) / len(scores), 4)
