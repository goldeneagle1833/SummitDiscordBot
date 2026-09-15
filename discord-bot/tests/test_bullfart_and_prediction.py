"""!bullfart uses its own daily timer; !fartprediction scoring is independent."""

import datetime
import os
import sqlite3
import sys
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

sys.modules.setdefault(
    "config",
    MagicMock(
        OPENAI_API_KEY="test",
        FART_CHANNEL_ID=1,
        GUILD_ID=1,
        LEADER_ROLE_ID=1,
    ),
)

from cogs.fun import (  # noqa: E402
    FunCog,
    FartPredictionView,
    is_same_est_calendar_day,
)


EST = ZoneInfo("America/New_York")


@pytest.fixture()
def fart_db(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cog = FunCog(MagicMock())
    yield cog
    if os.path.exists("fart_scores.db"):
        os.remove("fart_scores.db")


def _seed_player(user_id=1, name="Alice", score=100, last_updated=None, fart_type="elite"):
    conn = sqlite3.connect("fart_scores.db")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS fart_scores
           (user_id INTEGER PRIMARY KEY, user_display_name TEXT,
            date_last_updated TEXT, score INTEGER)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS fart_history
           (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            username TEXT NOT NULL, fart_type TEXT NOT NULL, roll INTEGER NOT NULL,
            timestamp TEXT NOT NULL)"""
    )
    conn.execute(
        "INSERT INTO fart_scores VALUES (?, ?, ?, ?)",
        (user_id, name, last_updated, score),
    )
    conn.execute(
        "INSERT INTO fart_history (user_id, username, fart_type, roll, timestamp) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, name, fart_type, 70, "2026-01-01T00:00:00"),
    )
    conn.commit()
    conn.close()


def _score_and_daily(user_id=1):
    conn = sqlite3.connect("fart_scores.db")
    row = conn.execute(
        "SELECT score, date_last_updated FROM fart_scores WHERE user_id=?",
        (user_id,),
    ).fetchone()
    conn.close()
    return row


class TestBullfartSeparateCooldown:
    def test_add_score_points_does_not_consume_daily(self, fart_db):
        yesterday = (datetime.datetime.now(EST) - datetime.timedelta(days=2)).isoformat()
        _seed_player(last_updated=yesterday)
        fart_db.add_score_points(1, "Alice", 25)
        score, last_updated = _score_and_daily()
        assert score == 125
        assert last_updated == yesterday
        assert fart_db.has_used_daily_fart_action(1) is False

    def test_save_fart_score_would_consume_daily(self, fart_db):
        yesterday = (datetime.datetime.now(EST) - datetime.timedelta(days=2)).isoformat()
        _seed_player(last_updated=yesterday)
        fart_db.save_fart_score(datetime.datetime.now(), 1, "Alice", 25)
        assert fart_db.has_used_daily_fart_action(1) is True

    def test_bullfart_mark_does_not_block_daily_fart(self, fart_db):
        yesterday = (datetime.datetime.now(EST) - datetime.timedelta(days=2)).isoformat()
        _seed_player(last_updated=yesterday)
        points, label = fart_db.bullfart_bonus_for_type(fart_db.get_latest_fart_type(1))
        assert points == 25
        assert label == "Elite Fart"
        fart_db.add_score_points(1, "Alice", points)
        fart_db.mark_bullfart_used(1)
        assert fart_db.has_used_bullfart_today(1) is True
        assert fart_db.has_used_daily_fart_action(1) is False
        score, last_updated = _score_and_daily()
        assert score == 125
        assert last_updated == yesterday

    def test_bullfart_today_blocks_only_bullfart(self, fart_db):
        yesterday = (datetime.datetime.now(EST) - datetime.timedelta(days=2)).isoformat()
        _seed_player(last_updated=yesterday)
        fart_db.mark_bullfart_used(1)
        assert fart_db.has_used_bullfart_today(1) is True
        assert fart_db.has_used_daily_fart_action(1) is False

    def test_yesterday_bullfart_is_available_again(self, fart_db):
        yesterday = datetime.datetime.now(EST) - datetime.timedelta(days=1, hours=1)
        _seed_player(last_updated=None)
        fart_db.mark_bullfart_used(1, when=yesterday.replace(tzinfo=None))
        # last_used stored as naive ISO; EST calendar day should not be today
        assert is_same_est_calendar_day(yesterday.isoformat()) is False
        assert fart_db.has_used_bullfart_today(1) is False

    def test_daily_fart_does_not_block_bullfart(self, fart_db):
        _seed_player(last_updated=datetime.datetime.now().isoformat())
        assert fart_db.has_used_daily_fart_action(1) is True
        assert fart_db.has_used_bullfart_today(1) is False


class TestFartPredictionScoring:
    def test_legacy_dropdown_values_map_to_roll_types(self):
        assert FunCog.resolve_prediction_type("unique_fart") == "unique"
        assert FunCog.resolve_prediction_type("elite_fart") == "elite"
        assert FunCog.resolve_prediction_type("ordinary") == "ordinary"
        assert FunCog.resolve_prediction_type("curio_shart") == "curio_shart"

    def test_correct_prediction_doubles(self):
        points, ok = FunCog.score_fart_prediction("elite", "elite", 70)
        assert ok is True
        assert points == 140

    def test_wrong_prediction_halves(self):
        points, ok = FunCog.score_fart_prediction("ordinary", "elite", 70)
        assert ok is False
        assert points == 35

    def test_old_message_string_match_was_fragile(self):
        """Previously compared full emoji strings; type match is what matters."""
        _, actual_type = FunCog.classify_fart_roll(70)
        assert actual_type == "elite"
        chosen = FunCog.resolve_prediction_type("elite_fart")
        points, ok = FunCog.score_fart_prediction(chosen, actual_type, 70)
        assert ok is True
        assert points == 140

    def test_prediction_view_has_dropdown_only(self, fart_db):
        view = FartPredictionView(fart_db, user_id=1)
        assert len(view.children) == 1
        select = view.children[0]
        values = [opt.value for opt in select.options]
        assert values == ["curio_shart", "unique", "elite", "exceptional", "ordinary"]
        assert not any(type(child).__name__ == "Button" for child in view.children)

    def test_prediction_awards_points_without_double_stamping_via_save_fart_score(
        self, fart_db
    ):
        yesterday = (datetime.datetime.now(EST) - datetime.timedelta(days=2)).isoformat()
        _seed_player(last_updated=yesterday)
        fart_db.add_score_points(1, "Alice", 140)
        fart_db.mark_daily_action_used(1, "Alice", datetime.datetime.now())
        score, last_updated = _score_and_daily()
        assert score == 240
        assert fart_db.has_used_daily_fart_action(1) is True
        assert fart_db.has_used_bullfart_today(1) is False
