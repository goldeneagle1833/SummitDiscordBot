"""Deck similarity service for Sorcery Deck Rec feature.

Provides Jaccard-based clustering of community decks around top-8 archetype seeds,
and aggregates card frequency statistics across each cluster.
"""

import logging
from collections import Counter

from repositories.deck_rec_repo import DeckRecord

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.3


# ------------------------------------------------------------------ #
# Core similarity math                                                #
# ------------------------------------------------------------------ #


def jaccard(set_a: frozenset, set_b: frozenset) -> float:
    """Compute Jaccard similarity between two card sets.

    Returns |A ∩ B| / |A ∪ B|, or 0.0 if the union is empty.
    """
    union = len(set_a | set_b)
    if union == 0:
        return 0.0
    return len(set_a & set_b) / union


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

    for deck in community:
        best_seed: DeckRecord | None = None
        best_score = 0.0

        for seed in seeds:
            score = jaccard(deck.card_names, seed.card_names)
            if score > best_score:
                best_seed = seed
                best_score = score

        if best_seed is not None and best_score >= threshold:
            clusters[best_seed.deck_id].append(deck)

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
      - fringe : < 20%

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
        avg_copies = round(total_copies / n, 2)

        if rate >= 0.8:
            tier = TIER_CORE
        elif rate >= 0.5:
            tier = TIER_COMMON
        elif rate >= 0.2:
            tier = TIER_TECH
        else:
            tier = TIER_FRINGE

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

    # Sort each tier descending by inclusion rate
    for tier_list in tiers.values():
        tier_list.sort(key=lambda x: x["inclusion_rate"], reverse=True)

    return tiers


# ------------------------------------------------------------------ #
# Convenience helpers                                                 #
# ------------------------------------------------------------------ #


def average_similarity(seed: DeckRecord, members: list[DeckRecord]) -> float:
    """Compute mean Jaccard similarity of cluster members to the seed."""
    if not members:
        return 0.0
    scores = [jaccard(seed.card_names, m.card_names) for m in members]
    return round(sum(scores) / len(scores), 4)
