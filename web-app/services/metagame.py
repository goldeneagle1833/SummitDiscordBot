"""Metagame solver service using linear programming for Nash equilibrium."""

import io
import json
import logging
import sqlite3
from collections import Counter

import numpy as np
import pandas as pd
from pulp import PULP_CBC_CMD, LpMaximize, LpProblem, LpVariable, lpSum, value

from webapp_config import MATCH_RECORDS_DB_PATH, ALL_CARDS_PATH

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
# Archetype classification & matchup matrix from match history
# ---------------------------------------------------------------------------

# Friendly labels for element combinations
_ARCHETYPE_LABELS = {
    frozenset(["Air"]): "Mono Air",
    frozenset(["Earth"]): "Mono Earth",
    frozenset(["Fire"]): "Mono Fire",
    frozenset(["Water"]): "Mono Water",
    frozenset(["Air", "Earth"]): "Air/Earth",
    frozenset(["Air", "Fire"]): "Air/Fire",
    frozenset(["Air", "Water"]): "Air/Water",
    frozenset(["Earth", "Fire"]): "Earth/Fire",
    frozenset(["Earth", "Water"]): "Earth/Water",
    frozenset(["Fire", "Water"]): "Fire/Water",
    frozenset(["Air", "Earth", "Fire"]): "Air/Earth/Fire",
    frozenset(["Air", "Earth", "Water"]): "Air/Earth/Water",
    frozenset(["Air", "Fire", "Water"]): "Air/Fire/Water",
    frozenset(["Earth", "Fire", "Water"]): "Earth/Fire/Water",
    frozenset(["Air", "Earth", "Fire", "Water"]): "4-Element",
}


def _load_card_elements():
    """Load card name -> set of elements from All_Cards_Array.json."""
    card_elements = {}
    try:
        with open(ALL_CARDS_PATH, "r", encoding="utf-8") as f:
            for card in json.load(f):
                name = card.get("name", "")
                elements_str = card.get("elements", "None")
                if name and elements_str and elements_str != "None":
                    card_elements[name.lower()] = set(
                        e.strip() for e in elements_str.split(",") if e.strip()
                    )
    except Exception as e:
        logger.error(f"Failed to load card elements: {e}")
    return card_elements


def _classify_deck(deck_json, card_elements):
    """Classify a deck JSON string into an archetype label.

    Uses spellbook cards only (no sites) to determine the element combination,
    then maps to a friendly label.  Returns None if the deck can't be parsed.
    """
    if not deck_json or deck_json in ("", "{}"):
        return None
    try:
        deck_data = json.loads(deck_json)
        deck = deck_data[0] if isinstance(deck_data, list) else deck_data
    except (json.JSONDecodeError, TypeError, IndexError):
        return None

    element_counts = Counter()
    for card in deck.get("spellbook", []) or []:
        card_name = (card.get("name") or "").lower()
        if card_name in card_elements:
            qty = card.get("quantity", 1) or 1
            for el in card_elements[card_name]:
                element_counts[el] += qty

    if not element_counts:
        return None

    elements = frozenset(element_counts.keys())
    return _ARCHETYPE_LABELS.get(elements, "/".join(sorted(elements)))


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


def build_archetype_matchup_matrix(min_games=3):
    """Build an archetype-vs-archetype matchup matrix from match history.

    Only includes matches where *both* players submitted deck data so we can
    classify both sides.  Archetypes with fewer than ``min_games`` total
    appearances are folded into an "Other" bucket.

    Returns a dict ready for JSON serialization::

        {
            "archetypes": ["Mono Fire", "Mono Water", ...],
            "matrix": [[wins, ...], ...],       # raw win counts (row beat col)
            "win_rates": [[0.55, ...], ...],     # win rate as 0-1 float
            "totals": {"Mono Fire": {"wins": N, "losses": N, "total": N}, ...},
            "match_count": N,                    # total matches used
        }
    """
    card_elements = _load_card_elements()
    match_rows = _fetch_match_rows()

    # --- classify each match --------------------------------------------------
    # matchups[winner_arch][loser_arch] = count of wins
    matchups = {}
    archetype_games = Counter()  # total appearances per archetype

    for winner_deck, loser_deck in match_rows:
        w_arch = _classify_deck(winner_deck, card_elements)
        l_arch = _classify_deck(loser_deck, card_elements)
        if w_arch is None or l_arch is None:
            continue

        archetype_games[w_arch] += 1
        archetype_games[l_arch] += 1

        matchups.setdefault(w_arch, Counter())[l_arch] += 1

    # --- bucket rare archetypes into "Other" ----------------------------------
    valid_archetypes = {a for a, n in archetype_games.items() if n >= min_games}
    has_other = False

    def _resolve(arch):
        nonlocal has_other
        if arch in valid_archetypes:
            return arch
        has_other = True
        return "Other"

    resolved_matchups = {}
    for w_arch, opponents in matchups.items():
        rw = _resolve(w_arch)
        for l_arch, count in opponents.items():
            rl = _resolve(l_arch)
            resolved_matchups.setdefault(rw, Counter())[rl] += count

    # --- build ordered archetype list -----------------------------------------
    all_archetypes = set()
    for w, opponents in resolved_matchups.items():
        all_archetypes.add(w)
        all_archetypes.update(opponents.keys())

    # Sort: mono first (alpha), then dual (alpha), then triple+, Other last
    def _sort_key(name):
        if name == "Other":
            return (4, name)
        parts = name.replace("Mono ", "").split("/")
        return (len(parts), name)

    archetype_list = sorted(all_archetypes, key=_sort_key)

    n = len(archetype_list)
    idx = {name: i for i, name in enumerate(archetype_list)}

    # --- fill matrices --------------------------------------------------------
    win_matrix = [[0] * n for _ in range(n)]  # win_matrix[i][j] = times i beat j
    for w_arch, opponents in resolved_matchups.items():
        for l_arch, count in opponents.items():
            win_matrix[idx[w_arch]][idx[l_arch]] += count

    # Win rate matrix
    wr_matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            total = win_matrix[i][j] + win_matrix[j][i]
            if total > 0:
                wr_matrix[i][j] = round(win_matrix[i][j] / total, 4)
            elif i == j:
                wr_matrix[i][j] = 0.5  # mirror match

    # Per-archetype totals
    totals = {}
    for a in archetype_list:
        i = idx[a]
        wins = sum(win_matrix[i])
        losses = sum(win_matrix[j][i] for j in range(n))
        total = wins + losses
        totals[a] = {
            "wins": wins,
            "losses": losses,
            "total": total,
            "win_rate": round(wins / total * 100, 1) if total > 0 else 0.0,
        }

    match_count = sum(sum(row) for row in win_matrix)

    return {
        "archetypes": archetype_list,
        "matrix": win_matrix,
        "win_rates": wr_matrix,
        "totals": totals,
        "match_count": match_count,
    }
