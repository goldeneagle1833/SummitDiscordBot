"""Tests for Community Series (Explorer) leaderboard scoring."""

import json
from unittest.mock import patch

from services.explorer import ExplorerService


def _leaderboard(points_config, results):
    with patch("repositories.explorer.ExplorerRepository") as repo_cls:
        repo = repo_cls.return_value
        repo.get_season.return_value = {
            "name": "Test Series",
            "points_config": json.dumps(points_config),
        }
        repo.get_results_for_season.return_value = results
        repo.get_alias_map.return_value = {}
        return ExplorerService().compute_leaderboard(1)


def _result(user_id, wins, standing, event_id):
    return {
        "cardeio_user_id": user_id,
        "display_name": user_id,
        "wins": wins,
        "final_standing": standing,
        "event_id": event_id,
    }


def test_win_focused_scores_one_point_per_win():
    config = {
        "participation": 0,
        "points_per_win": 1,
        "bonus_pathfinder": {},
        "persecutor": {},
        "trials_threshold": 0,
    }
    results = [
        _result("alice", 5, 1, "e1"),
        _result("bob", 0, 8, "e1"),
        _result("alice", 12, 1, "e2"),
        _result("bob", 3, 2, "e2"),
    ]

    board = _leaderboard(config, results)
    totals = {p["cardeio_user_id"]: p["grand_explorer"] for p in board["players"]}

    assert totals == {"alice": 17, "bob": 3}
    assert board["players"][0]["cardeio_user_id"] == "alice"


def test_configs_without_points_per_win_are_unchanged():
    config = {
        "participation": 10,
        "bonus_pathfinder": {"0": 5, "1": 4, "2": 3},
        "persecutor": {"1": 10},
        "trials_threshold": 10,
    }

    board = _leaderboard(config, [_result("alice", 2, 1, "e1")])

    assert board["players"][0]["pathfinder_total"] == 13
    assert board["players"][0]["grand_explorer"] == 23
