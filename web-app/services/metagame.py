"""Metagame solver service using linear programming for Nash equilibrium."""

import io
import logging

import numpy as np
import pandas as pd
from pulp import PULP_CBC_CMD, LpMaximize, LpProblem, LpVariable, lpSum, value

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
