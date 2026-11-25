"""Tests for monthly ranked metagame evolution and missing deck coverage."""

import json
import sqlite3

from services.archetype_trends import classify_deck, monthly_ranked_trends


def deck(avatar, element):
    return json.dumps({
        "avatar": [{"name": avatar}],
        "spellbook": [{"name": "Test spell", "quantity": 3, "elements": element}],
    })


def test_classification_requires_known_avatar_and_spellbook():
    assert classify_deck(deck("Pathfinder", "Fire")) == ("Pathfinder", "Fire")
    assert classify_deck("{}") is None
    assert classify_deck("not-json") is None
    assert classify_deck(json.dumps({"avatar": [{"name": "Pathfinder"}]})) is None


def test_monthly_shares_ignore_missing_data_and_deduplicate_archives(tmp_path):
    path = tmp_path / "matches.db"
    with sqlite3.connect(path) as connection:
        connection.execute("""CREATE TABLE match_records (
            match_id TEXT, timestamp TEXT, match_type TEXT,
            json_deck_data_winner TEXT, json_deck_data_loser TEXT
        )""")
        connection.execute("""CREATE TABLE match_records_archive (
            original_match_id TEXT, timestamp TEXT, match_type TEXT,
            json_deck_data_winner TEXT, json_deck_data_loser TEXT
        )""")
        rows = [
            ("m1", "2026-01-10 12:00:00", "ranked", deck("Pathfinder", "Fire"), deck("Imposter", "Earth,Fire")),
            ("m2", "2026-01-12 12:00:00", "ranked", "{}", deck("Pathfinder", "Fire")),
            ("m3", "2026-02-08 12:00:00", "ranked", deck("Imposter", "Earth,Fire"), deck("Imposter", "Earth,Fire")),
            ("casual", "2026-02-09 12:00:00", "casual", deck("Pathfinder", "Fire"), deck("Pathfinder", "Fire")),
        ]
        connection.executemany("INSERT INTO match_records VALUES (?, ?, ?, ?, ?)", rows)
        connection.execute("INSERT INTO match_records_archive VALUES (?, ?, ?, ?, ?)", rows[0])
    result = monthly_ranked_trends(path)
    assert result["totalMatches"] == 3
    assert result["possibleAppearances"] == 6
    assert result["classifiedAppearances"] == 5
    assert result["coverage"] == 83.3
    january = next(month for month in result["months"] if month["month"] == "2026-01")
    february = next(month for month in result["months"] if month["month"] == "2026-02")
    assert result["months"][0]["month"] == "2025-12"
    assert result["months"][0]["matches"] == 0
    assert january["classifiedAppearances"] == 3
    assert january["counts"]["pathfinder-fire"] == 2
    assert january["counts"]["imposter-earth-fire"] == 1
    assert february["counts"]["imposter-earth-fire"] == 2
    assert january["coverage"] == 75.0
    assert february["coverage"] == 100.0


def _one_table(path, rows):
    with sqlite3.connect(path) as connection:
        connection.execute("""CREATE TABLE match_records (
            match_id TEXT, timestamp TEXT, match_type TEXT,
            json_deck_data_winner TEXT, json_deck_data_loser TEXT
        )""")
        connection.executemany("INSERT INTO match_records VALUES (?, ?, ?, ?, ?)", rows)


def test_games_after_the_released_day_are_left_out(tmp_path):
    path = tmp_path / "matches.db"
    _one_table(path, [
        ("m1", "2026-01-10 12:00:00", "ranked", deck("Pathfinder", "Fire"), deck("Pathfinder", "Fire")),
        ("m2", "2026-01-20 12:00:00", "ranked", deck("Imposter", "Earth"), deck("Imposter", "Earth")),
    ])
    result = monthly_ranked_trends(path, through="2026-01-15")
    assert result["through"] == "2026-01-15"
    assert result["totalMatches"] == 1
    assert result["months"][-1]["month"] == "2026-01"
    assert "imposter-earth" not in result["months"][-1]["counts"]


def test_public_trends_stop_at_the_release_and_are_shared(tmp_path, monkeypatch):
    import services.archetype_trends as trends

    path = tmp_path / "matches.db"
    _one_table(path, [
        ("m1", "2026-01-10 12:00:00", "ranked", deck("Pathfinder", "Fire"), deck("Pathfinder", "Fire")),
        ("m2", "2026-01-20 12:00:00", "ranked", deck("Imposter", "Earth"), deck("Imposter", "Earth")),
    ])
    monkeypatch.setattr(trends, "MATCH_RECORDS_DB_PATH", str(path))
    monkeypatch.setattr(trends, "release_info", lambda: {
        "through": "2026-01-15", "period": "2026-01-a", "next_release": "2026-01-15"})
    builds = []
    real = trends.monthly_ranked_trends
    monkeypatch.setattr(trends, "monthly_ranked_trends",
                        lambda *a, **k: builds.append(k) or real(*a, **k))

    first = trends.get_ranked_trends()
    assert first["totalMatches"] == 1
    assert first["nextRelease"] == "2026-01-15"
    trends._trends_cache.clear()  # a restarted worker reads the saved file
    assert trends.get_ranked_trends() == first
    assert len(builds) == 1
