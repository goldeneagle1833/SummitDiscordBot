"""Tests for !taxes — 20% from everyone else goes entirely to the fartlord."""

import os
import sqlite3
import sys
from unittest.mock import MagicMock

import pytest

# Minimal config stub so fun.py can import without discord-bot/config.py
sys.modules.setdefault(
    "config",
    MagicMock(
        OPENAI_API_KEY="test",
        FART_CHANNEL_ID=1,
        GUILD_ID=1,
        LEADER_ROLE_ID=1,
    ),
)

from cogs.fun import FunCog  # noqa: E402


def _seed_scores(rows):
    conn = sqlite3.connect("fart_scores.db")
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS fart_scores
           (user_id INTEGER PRIMARY KEY,
            user_display_name TEXT,
            date_last_updated TEXT,
            score INTEGER)"""
    )
    for user_id, name, score in rows:
        cur.execute(
            "INSERT INTO fart_scores (user_id, user_display_name, date_last_updated, score) "
            "VALUES (?, ?, ?, ?)",
            (user_id, name, "2026-01-01", score),
        )
    conn.commit()
    conn.close()


def _scores_by_id():
    conn = sqlite3.connect("fart_scores.db")
    rows = conn.execute(
        "SELECT user_id, score FROM fart_scores ORDER BY score DESC"
    ).fetchall()
    conn.close()
    return {user_id: score for user_id, score in rows}


@pytest.fixture()
def taxes_db(tmp_path, monkeypatch):
    """Run tax helpers against a temp fart_scores.db in cwd."""
    monkeypatch.chdir(tmp_path)
    cog = FunCog(MagicMock())
    yield cog
    if os.path.exists("fart_scores.db"):
        os.remove("fart_scores.db")


class TestCollectTaxesForFartlord:
    def test_all_tax_goes_to_fartlord_not_top_5(self, taxes_db):
        # Scores chosen so 20% math is exact integers
        _seed_scores(
            [
                (1, "Fartlord", 1000),
                (2, "Second", 500),
                (3, "Third", 400),
                (4, "Fourth", 300),
                (5, "Fifth", 200),
                (6, "Sixth", 100),
                (7, "Seventh", 50),
            ]
        )

        result = taxes_db.collect_taxes_for_fartlord()
        assert result is not None

        # 20% from everyone except fartlord: 100+80+60+40+20+10 = 310
        assert result["total_taken"] == 310
        assert result["fartlord_bonus"] == 310
        assert result["fartlord_name"] == "Fartlord"
        assert result["taxed_count"] == 6

        scores = _scores_by_id()
        assert scores[1] == 1000 + 310
        assert scores[2] == 400
        assert scores[3] == 320
        assert scores[4] == 240
        assert scores[5] == 160
        assert scores[6] == 80
        assert scores[7] == 40

        # Non-leaders must not gain points (old bug split the pool among top 5)
        for user_id in (2, 3, 4, 5, 6, 7):
            assert scores[user_id] < {
                2: 500,
                3: 400,
                4: 300,
                5: 200,
                6: 100,
                7: 50,
            }[user_id]

    def test_returns_none_with_fewer_than_two_players(self, taxes_db):
        _seed_scores([(1, "Solo", 100)])
        assert taxes_db.collect_taxes_for_fartlord() is None

    def test_taxes_players_inside_former_top_5(self, taxes_db):
        """#2–#5 used to be exempt; they must now be taxed."""
        _seed_scores(
            [
                (1, "Fartlord", 1000),
                (2, "Second", 100),
                (3, "Third", 100),
                (4, "Fourth", 100),
                (5, "Fifth", 100),
            ]
        )
        result = taxes_db.collect_taxes_for_fartlord()
        assert result["total_taken"] == 80  # 20 from each of 4 players
        scores = _scores_by_id()
        assert scores[1] == 1080
        assert scores[2] == 80
        assert scores[3] == 80
        assert scores[4] == 80
        assert scores[5] == 80
