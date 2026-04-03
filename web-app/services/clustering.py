"""Deck clustering service using Hierarchical Agglomerative Clustering."""

import json
import numpy as np
from repositories.matches import MatchRepository

# Skip sending the full distance matrix if more decks than this
_HEATMAP_MAX_DECKS = 300


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

        result = {
            "total_decks": len(decks),
            "num_clusters": n_clusters,
            "threshold": threshold,
            "metric": metric,
            "scope": scope,
            "clusters": clusters,
            "deck_labels": deck_labels,
        }

        # Only include the full distance matrix if the deck count is manageable
        if len(decks) <= _HEATMAP_MAX_DECKS:
            result["distance_matrix"] = np.round(dist_matrix, 4).tolist()
        else:
            result["distance_matrix"] = []
            result["heatmap_skipped"] = True

        return result

    def _load_match_report_decks(self):
        """Load and deduplicate decks from all match reports."""
        raw_matches = self._match_repo.get_matches_with_deck_data()
        seen = set()  # (player_id, deck_fingerprint) for dedup
        decks = []

        for entry in raw_matches:
            row = entry["row"]
            use_new = entry["use_new_columns"]

            if use_new:
                winner_id = str(row[0])
                winner_name = row[1] or "Unknown"
                loser_id = str(row[2])
                loser_name = row[3] or "Unknown"
                winner_json = row[9]
                loser_json = row[10]

                self._try_add_deck(decks, seen, winner_json, winner_id, winner_name)
                self._try_add_deck(decks, seen, loser_json, loser_id, loser_name)
            else:
                winner_id = str(row[0])
                winner_name = row[1] or "Unknown"
                deck_json = row[9]
                self._try_add_deck(decks, seen, deck_json, winner_id, winner_name)

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

        spellbook = deck_data.get("spellbook", [])
        if not spellbook:
            return

        fingerprint = tuple(sorted(c.get("name", "") for c in spellbook))
        key = (player_id, fingerprint)
        if key in seen:
            return
        seen.add(key)

        deck_data["_player_id"] = player_id
        deck_data["_player_name"] = player_name
        avatar_list = deck_data.get("avatar", [])
        avatar_name = avatar_list[0].get("name", "Unknown") if avatar_list else "Unknown"
        deck_data["username"] = player_name
        deck_data["name"] = f"{player_name}'s {avatar_name}"
        deck_data["id"] = ""

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
        """Compute NxN pairwise Jaccard distance matrix (vectorized)."""
        if metric == "distinct":
            return self._jaccard_distinct_vectorized(vectors)
        return self._jaccard_total_vectorized(vectors)

    def _jaccard_distinct_vectorized(self, vectors):
        """Vectorized Jaccard distance for binary (distinct) card presence."""
        binary = (vectors > 0).astype(np.float64)
        # intersection[i,j] = number of cards shared between deck i and j
        intersection = binary @ binary.T
        # sizes[i] = number of distinct cards in deck i
        sizes = binary.sum(axis=1)
        # union[i,j] = |A| + |B| - |A ∩ B|
        union = sizes[:, None] + sizes[None, :] - intersection
        # Jaccard distance = 1 - intersection/union
        with np.errstate(divide="ignore", invalid="ignore"):
            dist = np.where(union > 0, 1.0 - intersection / union, 1.0)
        np.fill_diagonal(dist, 0.0)
        return dist

    def _jaccard_total_vectorized(self, vectors):
        """Vectorized Jaccard distance for quantity-weighted cards.

        For each pair (i,j): J = sum(min(a,b)) / sum(max(a,b)).
        Uses chunked computation to avoid creating a full (n,n,d) tensor.
        """
        n = vectors.shape[0]
        dist = np.zeros((n, n), dtype=np.float64)
        chunk_size = 64  # Process 64 rows at a time to limit memory

        for start in range(0, n, chunk_size):
            end = min(start + chunk_size, n)
            # chunk shape: (chunk, 1, d) vs (1, n, d) -> (chunk, n, d)
            chunk = vectors[start:end, np.newaxis, :]
            all_v = vectors[np.newaxis, :, :]
            mins = np.minimum(chunk, all_v).sum(axis=2)
            maxs = np.maximum(chunk, all_v).sum(axis=2)
            with np.errstate(divide="ignore", invalid="ignore"):
                d = np.where(maxs > 0, 1.0 - mins / maxs, 1.0)
            dist[start:end, :] = d

        np.fill_diagonal(dist, 0.0)
        return dist

    def _hierarchical_cluster(self, dist_matrix, threshold):
        """Agglomerative clustering with complete linkage (vectorized)."""
        n = dist_matrix.shape[0]
        clusters = {i: [i] for i in range(n)}
        active = np.ones(n, dtype=bool)
        cd = dist_matrix.copy()
        np.fill_diagonal(cd, np.inf)

        while np.sum(active) > 1:
            # Mask inactive rows/cols by setting them to inf
            mask = np.outer(active, active)
            masked = np.where(mask, cd, np.inf)

            # Find global minimum using numpy (C-speed scan)
            flat_idx = np.argmin(masked)
            min_dist = masked.flat[flat_idx]

            if min_dist > threshold:
                break

            merge_a, merge_b = divmod(int(flat_idx), n)

            # Merge b into a
            clusters[merge_a].extend(clusters[merge_b])
            del clusters[merge_b]
            active[merge_b] = False

            # Complete linkage: new distance = max of old distances (vectorized)
            cd[merge_a, :] = np.maximum(cd[merge_a, :], cd[merge_b, :])
            cd[:, merge_a] = cd[merge_a, :]
            cd[merge_a, merge_a] = np.inf

            # Invalidate merge_b
            cd[merge_b, :] = np.inf
            cd[:, merge_b] = np.inf

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
            mi = member_indices
            for i_idx in range(len(mi)):
                for j_idx in range(i_idx + 1, len(mi)):
                    avg_sim += 1.0 - dist_matrix[mi[i_idx], mi[j_idx]]
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
