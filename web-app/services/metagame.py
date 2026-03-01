"""Metagame solver service using linear programming for Nash equilibrium."""

import io
import json
import logging
import sqlite3
from collections import Counter

import numpy as np
import pandas as pd
from pulp import PULP_CBC_CMD, LpMaximize, LpProblem, LpVariable, lpSum, value

from webapp_config import MATCH_RECORDS_DB_PATH

# Suppress CBC solver output
_SOLVER = PULP_CBC_CMD(msg=0)

logger = logging.getLogger(__name__)


def parse_matchup_csv(file_stream):
    """Parse an uploaded CSV file into a matchup matrix DataFrame.

    Expects a square matrix CSV where:
    - First column contains row strategy names
    - First row (header) contains column strategy names
    - Values are win probabilities (0 to 1) for the row player
    """
    content = file_stream.read().decode("utf-8")
    df = pd.read_csv(io.StringIO(content), index_col=0)
    df.index.name = "row_strategy"
    df.columns.name = "col_strategy"
    # Ensure numeric
    df = df.apply(pd.to_numeric, errors="coerce")
    return df


def _setup_basic_problem(matrix):
    """Set up the LP for solving a two-player zero-sum game.

    Finds the maximin mixed strategy for the row player.
    """
    prob = LpProblem("metagame_solver", LpMaximize)
    all_vars = list(matrix.index.values) + ["w"]
    lp_vars = LpVariable.dicts("v", all_vars)

    # Objective: maximize the guaranteed payoff w
    prob += lpSum([lp_vars["w"]])

    # Non-negativity for strategy probabilities
    for strat in matrix.index.values:
        prob += lpSum([1.0 * lp_vars[strat]]) >= 0

    # Probabilities sum to 1
    prob += lpSum([1.0 * lp_vars[x] for x in matrix.index.values]) == 1

    # For each opponent strategy, expected payoff >= w
    for col_strat in matrix.columns.values:
        terms = [
            matrix.loc[row_strat, col_strat] * lp_vars[row_strat]
            for row_strat in matrix.index.values
        ]
        terms.append(-1 * lp_vars["w"])
        prob += lpSum(terms) >= 0

    return prob, lp_vars


def solve_game(matrix):
    """Solve for the Nash equilibrium mixed strategy.

    Returns (game_value, strategy_probabilities_dict).
    """
    prob, lp_vars = _setup_basic_problem(matrix)
    prob.solve(_SOLVER)

    game_val = value(lp_vars["w"])
    strat_probs = {}
    for strat in matrix.index.values:
        strat_probs[strat] = value(lp_vars[strat])

    return game_val, strat_probs


def _solve_with_constraint(matrix, strategy_name, constraint_value):
    """Solve game with one strategy's probability fixed."""
    prob, lp_vars = _setup_basic_problem(matrix)
    prob += lpSum([lp_vars[strategy_name]]) == constraint_value
    prob.solve(_SOLVER)

    game_val = value(lp_vars["w"])
    strat_probs = {}
    for strat in matrix.index.values:
        strat_probs[strat] = value(lp_vars[strat])

    return game_val, strat_probs


def get_win_rates_for_strategy(strategy_name, matrix, divisions=10):
    """Compute game value as a function of one strategy's probability."""
    probs = np.linspace(0, 1, divisions + 1)
    values = []
    for p in probs:
        game_val, _ = _solve_with_constraint(matrix, strategy_name, p)
        values.append(game_val)
    return pd.Series(values, index=probs, name=strategy_name)


def get_all_win_rates(matrix, divisions=10):
    """Compute win rate curves for all strategies."""
    series = [
        get_win_rates_for_strategy(strat, matrix, divisions)
        for strat in matrix.index.values
    ]
    return pd.concat(series, axis=1)


def compute_intervals(win_rates, threshold=-0.02):
    """Compute viable probability intervals for each strategy.

    A strategy is "viable" at probability p if the game value >= threshold.
    Returns list of dicts with strategy name, min, max viable probabilities.
    """
    intervals = []
    for col in win_rates.columns:
        series = win_rates[col]
        viable = series[series >= threshold]
        if viable.empty:
            intervals.append({"name": col, "min": 0.0, "max": 0.0})
        else:
            intervals.append({
                "name": col,
                "min": round(float(viable.index[0]), 4),
                "max": round(float(viable.index[-1]), 4),
            })

    # Sort by max descending, then min descending
    intervals.sort(key=lambda x: (x["max"], x["min"]), reverse=True)
    return intervals


def analyze_matchups(file_stream, divisions=10, threshold=-0.02):
    """Full analysis pipeline: parse CSV, solve, compute intervals.

    Returns dict with all results ready for JSON serialization.
    """
    matchups = parse_matchup_csv(file_stream)

    # Convert to payoffs (2*p - 1 maps [0,1] win prob to [-1,1] payoff)
    payoffs = 2 * matchups - 1

    # Solve for Nash equilibrium
    game_value, strategy_probs = solve_game(payoffs)

    # Compute win rate intervals
    win_rates = get_all_win_rates(payoffs, divisions)
    intervals = compute_intervals(win_rates, threshold)

    # Build strategy list sorted by probability descending
    strategies = [
        {"name": name, "probability": round(prob, 4)}
        for name, prob in sorted(
            strategy_probs.items(), key=lambda x: x[1], reverse=True
        )
    ]

    # Build the raw matchup matrix for display
    matchup_data = {
        "rows": list(matchups.index),
        "cols": list(matchups.columns),
        "values": matchups.values.tolist(),
    }

    return {
        "game_value": round(game_value, 4),
        "strategies": strategies,
        "intervals": intervals,
        "matchups": matchup_data,
    }


# ---------------------------------------------------------------------------
# Card-similarity clustering & matchup matrix from match history
# ---------------------------------------------------------------------------


def _deck_to_card_map(deck_json):
    """Extract {card_name: quantity} from a deck JSON string (spellbook only).

    Returns None if the deck can't be parsed or has no spellbook cards.
    """
    if not deck_json or deck_json in ("", "{}"):
        return None
    try:
        deck_data = json.loads(deck_json)
        deck = deck_data[0] if isinstance(deck_data, list) else deck_data
    except (json.JSONDecodeError, TypeError, IndexError):
        return None

    card_map = {}
    for card in deck.get("spellbook", []) or []:
        name = card.get("name")
        if not name:
            continue
        qty = card.get("quantity", 1) or 1
        card_map[name] = card_map.get(name, 0) + qty

    return card_map if card_map else None


def _card_map_fingerprint(card_map):
    """Create a hashable fingerprint from a card map for de-duplication."""
    return tuple(sorted(card_map.items()))


def _build_card_vectors(card_maps):
    """Convert a list of card maps into a numpy matrix.

    Returns (matrix, card_index) where matrix rows are decks and columns are
    unique card names, values are quantities normalised by L2 norm.
    """
    all_cards = sorted({card for cm in card_maps for card in cm})
    card_idx = {name: i for i, name in enumerate(all_cards)}
    n_decks = len(card_maps)
    n_cards = len(all_cards)

    matrix = np.zeros((n_decks, n_cards))
    for i, cm in enumerate(card_maps):
        for card, qty in cm.items():
            matrix[i, card_idx[card]] = qty

    # L2-normalise each row for cosine similarity
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1  # avoid division by zero
    matrix = matrix / norms

    return matrix, all_cards


def _cosine_distance_matrix(vectors):
    """Compute pairwise cosine distance (1 - cosine_similarity)."""
    sim = vectors @ vectors.T
    # Clamp to [0, 2] to handle floating-point drift
    return np.clip(1.0 - sim, 0.0, 2.0)


def _agglomerative_cluster(dist_matrix, n_clusters):
    """Average-linkage agglomerative clustering (UPGMA).

    Uses Lance-Williams matrix updates so each merge is O(n) instead of
    recomputing all pairwise member distances.  Total runtime is O(n^2).

    Returns a list of lists, where each inner list contains the indices of
    items belonging to that cluster.
    """
    n = dist_matrix.shape[0]
    if n <= n_clusters:
        return [[i] for i in range(n)]

    # Working copy — inactive rows/cols are set to inf
    dists = dist_matrix.astype(np.float64).copy()
    np.fill_diagonal(dists, np.inf)

    clusters = {i: [i] for i in range(n)}
    sizes = np.ones(n, dtype=np.float64)
    active = set(range(n))

    while len(active) > n_clusters:
        # Find closest pair (numpy vectorised argmin)
        flat_idx = np.argmin(dists)
        i, j = divmod(int(flat_idx), n)

        # Ensure i < j for consistency
        if i > j:
            i, j = j, i

        # Lance-Williams update for UPGMA (average linkage):
        # d(i∪j, k) = (n_i * d(i,k) + n_j * d(j,k)) / (n_i + n_j)
        ni, nj = sizes[i], sizes[j]
        for k in active:
            if k == i or k == j:
                continue
            new_d = (ni * dists[i, k] + nj * dists[j, k]) / (ni + nj)
            dists[i, k] = new_d
            dists[k, i] = new_d

        # Merge j into i
        clusters[i].extend(clusters[j])
        sizes[i] = ni + nj
        del clusters[j]
        active.remove(j)

        # Deactivate row/col j
        dists[j, :] = np.inf
        dists[:, j] = np.inf

    return [clusters[k] for k in active]


def _name_clusters(clusters, card_maps):
    """Name each cluster using its most distinctive cards.

    Uses a TF-IDF-like score: for each card in a cluster, the score is
    (proportion of cluster decks containing the card) /
    (proportion of ALL decks containing the card).
    The top 2 scoring cards become the cluster name.
    """
    all_deck_count = sum(len(c) for c in clusters)

    # Global frequency: proportion of all decks containing each card
    global_freq = Counter()
    for cluster in clusters:
        for deck_idx in cluster:
            for card in card_maps[deck_idx]:
                global_freq[card] += 1

    names = []
    for cluster in clusters:
        cluster_size = len(cluster)
        # Count how many decks in this cluster have each card
        cluster_freq = Counter()
        for deck_idx in cluster:
            for card in card_maps[deck_idx]:
                cluster_freq[card] += 1

        # TF-IDF-like score
        scores = {}
        for card, count in cluster_freq.items():
            tf = count / cluster_size  # proportion in cluster
            idf = all_deck_count / max(global_freq[card], 1)  # inverse doc freq
            scores[card] = tf * idf

        top_cards = sorted(scores, key=scores.get, reverse=True)[:2]
        names.append(" / ".join(top_cards) if top_cards else "Unknown")

    return names


def _fetch_match_rows():
    """Fetch all match rows with both winner and loser deck data.

    Returns list of (winner_deck_json, loser_deck_json) tuples.
    """
    rows = []
    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()

        for table in ("match_records", "match_records_archive"):
            try:
                cur.execute(f"""
                    SELECT json_deck_data_winner, json_deck_data_loser
                    FROM {table}
                    WHERE json_deck_data_winner IS NOT NULL
                      AND json_deck_data_winner != '' AND json_deck_data_winner != '{{}}'
                      AND json_deck_data_loser IS NOT NULL
                      AND json_deck_data_loser != '' AND json_deck_data_loser != '{{}}'
                """)
                rows.extend(cur.fetchall())
            except sqlite3.OperationalError:
                continue

        conn.close()
    except sqlite3.OperationalError as e:
        logger.error(f"DB error fetching match rows: {e}")
    return rows


def build_archetype_matchup_matrix(min_games=3, n_clusters=5):
    """Build a cluster-vs-cluster matchup matrix from match history.

    Decks are grouped by card similarity using agglomerative clustering
    rather than element combinations.  Only includes matches where *both*
    players submitted deck data.

    Args:
        min_games: Unused (kept for API compatibility).
        n_clusters: Number of deck groups to produce (2-8, default 5).

    Returns a dict ready for JSON serialization::

        {
            "archetypes": ["Card A / Card B", ...],
            "matrix": [[wins, ...], ...],       # raw win counts (row beat col)
            "win_rates": [[0.55, ...], ...],     # win rate as 0-1 float
            "totals": {"Card A / Card B": {"wins": N, ...}, ...},
            "match_count": N,
        }
    """
    match_rows = _fetch_match_rows()

    # --- parse every deck into a card map ------------------------------------
    # Each match produces two card maps (winner, loser).  We also keep the
    # raw JSON index so we can map matches back to cluster labels later.
    all_card_maps = []         # index → card_map
    match_deck_indices = []    # [(winner_idx, loser_idx), ...]

    fingerprint_to_idx = {}    # de-dup identical decks

    def _get_or_add(deck_json):
        cm = _deck_to_card_map(deck_json)
        if cm is None:
            return None
        fp = _card_map_fingerprint(cm)
        if fp in fingerprint_to_idx:
            return fingerprint_to_idx[fp]
        idx = len(all_card_maps)
        all_card_maps.append(cm)
        fingerprint_to_idx[fp] = idx
        return idx

    for winner_json, loser_json in match_rows:
        w_idx = _get_or_add(winner_json)
        l_idx = _get_or_add(loser_json)
        if w_idx is not None and l_idx is not None:
            match_deck_indices.append((w_idx, l_idx))

    if not all_card_maps:
        return {
            "archetypes": [],
            "matrix": [],
            "win_rates": [],
            "totals": {},
            "match_count": 0,
        }

    # --- cluster decks by card similarity ------------------------------------
    actual_clusters = min(n_clusters, len(all_card_maps))
    vectors, _ = _build_card_vectors(all_card_maps)
    dist_matrix = _cosine_distance_matrix(vectors)
    clusters = _agglomerative_cluster(dist_matrix, actual_clusters)

    # Map deck index → cluster index
    deck_to_cluster = {}
    for ci, members in enumerate(clusters):
        for deck_idx in members:
            deck_to_cluster[deck_idx] = ci

    # Name each cluster
    cluster_names = _name_clusters(clusters, all_card_maps)

    # --- build matchup data from matches -------------------------------------
    n = len(clusters)
    win_matrix = [[0] * n for _ in range(n)]

    for w_idx, l_idx in match_deck_indices:
        wc = deck_to_cluster[w_idx]
        lc = deck_to_cluster[l_idx]
        win_matrix[wc][lc] += 1

    # Win rate matrix
    wr_matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            total = win_matrix[i][j] + win_matrix[j][i]
            if total > 0:
                wr_matrix[i][j] = round(win_matrix[i][j] / total, 4)
            elif i == j:
                wr_matrix[i][j] = 0.5

    # Per-cluster totals
    totals = {}
    for ci, name in enumerate(cluster_names):
        wins = sum(win_matrix[ci])
        losses = sum(win_matrix[j][ci] for j in range(n))
        total = wins + losses
        totals[name] = {
            "wins": wins,
            "losses": losses,
            "total": total,
            "win_rate": round(wins / total * 100, 1) if total > 0 else 0.0,
        }

    match_count = sum(sum(row) for row in win_matrix)

    return {
        "archetypes": cluster_names,
        "matrix": win_matrix,
        "win_rates": wr_matrix,
        "totals": totals,
        "match_count": match_count,
    }
