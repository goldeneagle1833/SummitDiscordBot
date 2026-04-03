"""Deck clustering service using Hierarchical Agglomerative Clustering."""

import json
import numpy as np
from repositories.matches import MatchRepository


class ClusteringService:
    """Cluster decks from match reports by card similarity."""

    def __init__(self, match_repo=None):
        self._match_repo = match_repo or MatchRepository()

    def cluster_match_reports(self, threshold=0.6, metric="distinct", scope="spells"):
        """Cluster all decks from match reports by card similarity.

        Args:
            threshold: Distance threshold for cutting dendrogram (0-1). Lower = more clusters.
            metric: 'distinct' (binary card presence) or 'total' (card quantities).
            scope: 'spells' (spellbook only) or 'full' (spellbook + atlas).

        Returns:
            dict with clusters, distance matrix, and metadata, or None if not enough decks.
        """
        decks = self._load_match_report_decks()
        if not decks or len(decks) < 2:
            return None

        card_names, vectors = self._build_card_vectors(decks, metric, scope)
        dist_matrix = self._compute_jaccard_distance_matrix(vectors, metric)
        labels, n_clusters = self._hierarchical_cluster(dist_matrix, threshold)

        clusters = self._build_cluster_data(decks, labels, n_clusters, dist_matrix, scope)
        deck_labels = [
            f"{d.get('_player_name', 'Unknown')} - {d.get('avatar', [{}])[0].get('name', '?')}"
            for d in decks
        ]

        return {
            "total_decks": len(decks),
            "num_clusters": n_clusters,
            "threshold": threshold,
            "metric": metric,
            "scope": scope,
            "clusters": clusters,
            "distance_matrix": np.round(dist_matrix, 4).tolist(),
            "deck_labels": deck_labels,
        }

    def _load_match_report_decks(self):
        """Load and deduplicate decks from all match reports.

        Returns a list of deck dicts in the same format as tournament decks,
        with extra _player_name and _player_id fields.
        """
        raw_matches = self._match_repo.get_matches_with_deck_data()
        seen = set()  # (player_id, deck_fingerprint) for dedup
        decks = []

        for entry in raw_matches:
            row = entry["row"]
            use_new = entry["use_new_columns"]

            if use_new:
                # New schema: separate winner/loser deck columns
                winner_id = str(row[0])
                winner_name = row[1] or "Unknown"
                loser_id = str(row[2])
                loser_name = row[3] or "Unknown"
                winner_json = row[9]
                loser_json = row[10]

                self._try_add_deck(
                    decks, seen, winner_json, winner_id, winner_name
                )
                self._try_add_deck(
                    decks, seen, loser_json, loser_id, loser_name
                )
            else:
                # Old schema: single json_deck_data column (unknown owner)
                winner_id = str(row[0])
                winner_name = row[1] or "Unknown"
                deck_json = row[9]
                self._try_add_deck(
                    decks, seen, deck_json, winner_id, winner_name
                )

        return decks

    def _try_add_deck(self, decks, seen, deck_json, player_id, player_name):
        """Parse deck JSON and add to list if valid and not a duplicate."""
        if not deck_json or deck_json == "{}":
            return

        try:
            deck_data = json.loads(deck_json)
        except (json.JSONDecodeError, TypeError):
            return

        if not isinstance(deck_data, dict):
            return

        # Need at least a spellbook with cards
        spellbook = deck_data.get("spellbook", [])
        if not spellbook:
            return

        # Fingerprint: sorted card names for deduplication per player
        fingerprint = tuple(sorted(c.get("name", "") for c in spellbook))
        key = (player_id, fingerprint)
        if key in seen:
            return
        seen.add(key)

        # Add metadata fields the clustering code expects
        deck_data["_player_id"] = player_id
        deck_data["_player_name"] = player_name
        # Derive a display name from avatar + player
        avatar_list = deck_data.get("avatar", [])
        avatar_name = avatar_list[0].get("name", "Unknown") if avatar_list else "Unknown"
        deck_data["username"] = player_name
        deck_data["name"] = f"{player_name}'s {avatar_name}"
        deck_data["id"] = ""  # No Curiosa deck ID for match reports

        decks.append(deck_data)

    def _build_card_vectors(self, decks, metric, scope):
        """Convert decks to numerical vectors for Jaccard computation."""
        all_cards = {}
        for deck in decks:
            cards = self._get_deck_cards(deck, scope)
            for card in cards:
                name = card.get("name", "")
                if name and name not in all_cards:
                    all_cards[name] = len(all_cards)

        card_names = list(all_cards.keys())
        n_decks = len(decks)
        n_cards = len(card_names)
        vectors = np.zeros((n_decks, n_cards), dtype=np.float64)

        for i, deck in enumerate(decks):
            cards = self._get_deck_cards(deck, scope)
            for card in cards:
                name = card.get("name", "")
                if name in all_cards:
                    idx = all_cards[name]
                    if metric == "distinct":
                        vectors[i, idx] = 1.0
                    else:
                        vectors[i, idx] += card.get("quantity", 1)

        return card_names, vectors

    def _get_deck_cards(self, deck, scope):
        """Extract cards from a deck based on scope."""
        cards = list(deck.get("spellbook", []))
        if scope == "full":
            cards.extend(deck.get("atlas", []))
        return cards

    def _compute_jaccard_distance_matrix(self, vectors, metric):
        """Compute NxN pairwise Jaccard distance matrix."""
        n = vectors.shape[0]
        dist = np.zeros((n, n), dtype=np.float64)

        for i in range(n):
            for j in range(i + 1, n):
                a, b = vectors[i], vectors[j]
                if metric == "distinct":
                    union = np.sum((a > 0) | (b > 0))
                    intersection = np.sum((a > 0) & (b > 0))
                else:
                    intersection = np.sum(np.minimum(a, b))
                    union = np.sum(np.maximum(a, b))

                if union == 0:
                    d = 1.0
                else:
                    d = 1.0 - (intersection / union)

                dist[i, j] = d
                dist[j, i] = d

        return dist

    def _hierarchical_cluster(self, dist_matrix, threshold):
        """Agglomerative clustering with complete linkage."""
        n = dist_matrix.shape[0]
        clusters = {i: [i] for i in range(n)}
        active = set(range(n))
        cluster_dist = dist_matrix.copy()

        while len(active) > 1:
            min_dist = float("inf")
            merge_a, merge_b = -1, -1
            active_list = sorted(active)

            for idx_i in range(len(active_list)):
                for idx_j in range(idx_i + 1, len(active_list)):
                    ci, cj = active_list[idx_i], active_list[idx_j]
                    if cluster_dist[ci, cj] < min_dist:
                        min_dist = cluster_dist[ci, cj]
                        merge_a, merge_b = ci, cj

            if min_dist > threshold:
                break

            clusters[merge_a].extend(clusters[merge_b])
            del clusters[merge_b]
            active.discard(merge_b)

            for other in active:
                if other == merge_a:
                    continue
                new_dist = max(cluster_dist[merge_a, other], cluster_dist[merge_b, other])
                cluster_dist[merge_a, other] = new_dist
                cluster_dist[other, merge_a] = new_dist

        labels = [0] * n
        for cluster_id, (_, members) in enumerate(sorted(clusters.items())):
            for member in members:
                labels[member] = cluster_id

        return labels, len(clusters)

    def _build_cluster_data(self, decks, labels, n_clusters, dist_matrix, scope):
        """Build the response data for each cluster."""
        clusters = []

        for cluster_id in range(n_clusters):
            member_indices = [i for i, l in enumerate(labels) if l == cluster_id]
            member_decks = []
            element_counts = {"Fire": 0, "Water": 0, "Earth": 0, "Air": 0}
            avatar_counts = {}

            for idx in member_indices:
                deck = decks[idx]
                avatar_list = deck.get("avatar", [{}])
                avatar_name = avatar_list[0].get("name", "Unknown") if avatar_list else "Unknown"
                member_decks.append({
                    "name": deck.get("name", "Unnamed"),
                    "username": deck.get("username", "Unknown"),
                    "avatar": avatar_name,
                    "deck_id": deck.get("id", ""),
                })
                avatar_counts[avatar_name] = avatar_counts.get(avatar_name, 0) + 1

                for card in self._get_deck_cards(deck, scope):
                    for el in card.get("elements", "None").split(", "):
                        el = el.strip()
                        if el in element_counts:
                            element_counts[el] += 1

            # Average internal similarity
            avg_sim = 0.0
            pair_count = 0
            for i_idx in range(len(member_indices)):
                for j_idx in range(i_idx + 1, len(member_indices)):
                    avg_sim += 1.0 - dist_matrix[member_indices[i_idx], member_indices[j_idx]]
                    pair_count += 1
            if pair_count > 0:
                avg_sim /= pair_count

            core_cards = self._extract_core_cards(decks, member_indices, scope)
            label = self._generate_cluster_label(element_counts, avatar_counts)

            clusters.append({
                "id": cluster_id,
                "size": len(member_indices),
                "label": label,
                "avg_internal_similarity": round(avg_sim, 3),
                "decks": member_decks,
                "core_cards": core_cards,
                "elements": element_counts,
            })

        clusters.sort(key=lambda c: c["size"], reverse=True)
        return clusters

    def _extract_core_cards(self, decks, member_indices, scope):
        """Find cards present in >50% of cluster members."""
        card_presence = {}
        n_members = len(member_indices)

        for idx in member_indices:
            deck = decks[idx]
            seen = set()
            for card in self._get_deck_cards(deck, scope):
                name = card.get("name", "")
                if name and name not in seen:
                    seen.add(name)
                    if name not in card_presence:
                        card_presence[name] = {
                            "count": 0,
                            "type": card.get("type", "Unknown"),
                            "elements": card.get("elements", "None"),
                        }
                    card_presence[name]["count"] += 1

        threshold = n_members * 0.5
        core = []
        for name, info in card_presence.items():
            if info["count"] >= threshold:
                core.append({
                    "name": name,
                    "type": info["type"],
                    "elements": info["elements"],
                    "frequency": round(info["count"] / n_members, 2),
                })

        core.sort(key=lambda c: c["frequency"], reverse=True)
        return core

    def _generate_cluster_label(self, element_counts, avatar_counts):
        """Generate a human-readable label for a cluster."""
        max_el = max(element_counts.values()) if element_counts else 0
        if max_el > 0:
            top_elements = sorted(
                [el for el, c in element_counts.items() if c >= max_el * 0.25],
                key=lambda el: element_counts[el],
                reverse=True,
            )
        else:
            top_elements = []

        element_str = "/".join(top_elements[:2]) if top_elements else "Mixed"

        total_decks = sum(avatar_counts.values())
        top_avatar = max(avatar_counts, key=avatar_counts.get) if avatar_counts else None
        if top_avatar and avatar_counts[top_avatar] > total_decks * 0.5:
            return f"{element_str} - {top_avatar}"

        return element_str
