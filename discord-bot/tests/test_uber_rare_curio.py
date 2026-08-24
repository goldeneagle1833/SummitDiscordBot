"""Tests for uber-rare Curio Shart (lavashart / frostshart) permanent odds."""

import asyncio
import os
import sqlite3
import sys
from unittest.mock import AsyncMock, MagicMock, patch

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

from cogs.fun import (  # noqa: E402
    FunCog,
    UBER_RARE_CURIO_VARIANTS,
)


@pytest.fixture()
def fart_db(tmp_path, monkeypatch):
    """Run uber-rare helpers against a temp fart_scores.db in cwd."""
    monkeypatch.chdir(tmp_path)
    cog = FunCog(MagicMock())
    yield cog
    if os.path.exists("fart_scores.db"):
        os.remove("fart_scores.db")


class TestUberRareCurioPermanent:
    def test_not_claimed_initially(self, fart_db):
        assert fart_db.is_uber_rare_guaranteed_claimed() is False

    def test_first_curio_always_special(self, fart_db):
        with patch("cogs.fun.randrange", side_effect=[0]):  # lavashart
            variant = fart_db.roll_uber_rare_curio_variant(user_id=42)
        assert variant == "lavashart"
        assert fart_db.is_uber_rare_guaranteed_claimed() is True

    def test_first_curio_can_be_frostshart(self, fart_db):
        with patch("cogs.fun.randrange", side_effect=[1]):  # frostshart
            variant = fart_db.roll_uber_rare_curio_variant(user_id=7)
        assert variant == "frostshart"
        assert fart_db.is_uber_rare_guaranteed_claimed() is True

    def test_after_claim_10_percent_miss(self, fart_db):
        fart_db.mark_uber_rare_guaranteed_claimed(1, "lavashart")
        # claimed path: randrange(1, 101) → 11 means miss (>10)
        with patch("cogs.fun.randrange", return_value=11):
            assert fart_db.roll_uber_rare_curio_variant(user_id=99) is None

    def test_after_claim_10_percent_hit(self, fart_db):
        fart_db.mark_uber_rare_guaranteed_claimed(1, "lavashart")
        # claimed path: randrange(1,101)=5 → hit; then randrange(2)=1 → frostshart
        with patch("cogs.fun.randrange", side_effect=[5, 1]):
            assert fart_db.roll_uber_rare_curio_variant(user_id=99) == "frostshart"
        # Flag stays set (still claimed)
        assert fart_db.is_uber_rare_guaranteed_claimed() is True

    def test_boundary_10_percent_hit(self, fart_db):
        fart_db.mark_uber_rare_guaranteed_claimed(1, "lavashart")
        # Exactly 10 should still hit (miss only when > 10)
        with patch("cogs.fun.randrange", side_effect=[10, 0]):
            assert fart_db.roll_uber_rare_curio_variant(user_id=3) == "lavashart"

    def test_mark_is_idempotent_singleton(self, fart_db):
        fart_db.mark_uber_rare_guaranteed_claimed(1, "lavashart")
        fart_db.mark_uber_rare_guaranteed_claimed(2, "frostshart")
        conn = sqlite3.connect("fart_scores.db")
        rows = conn.execute(
            "SELECT claimed_by_user_id, variant FROM uber_rare_curio_claimed"
        ).fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0] == (1, "lavashart")

    def test_flag_persists_when_other_tables_wiped(self, fart_db):
        """Guaranteed flag must remain after a season-style wipe of other tables."""
        fart_db.mark_uber_rare_guaranteed_claimed(1, "lavashart")
        assert fart_db.is_uber_rare_guaranteed_claimed() is True

        conn = sqlite3.connect("fart_scores.db")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS fart_scores ("
            "user_id INTEGER PRIMARY KEY, user_display_name TEXT, "
            "date_last_updated TEXT, score INTEGER)"
        )
        conn.execute(
            "INSERT OR IGNORE INTO fart_scores VALUES (1, 'A', '2026-01-01', 10)"
        )
        conn.execute("DELETE FROM fart_scores")
        # Intentionally do NOT delete uber_rare_curio_claimed (preserved on reset)
        conn.commit()
        conn.close()

        assert fart_db.is_uber_rare_guaranteed_claimed() is True
        # Still on 10% path — 100% never comes back
        with patch("cogs.fun.randrange", return_value=11):
            assert fart_db.roll_uber_rare_curio_variant(user_id=5) is None

    def test_maybe_uber_rare_skips_non_curio(self, fart_db):
        prefix, embed, variant = fart_db.maybe_uber_rare_curio("unique", user_id=1)
        assert prefix == ""
        assert embed is None
        assert variant is None

    def test_highlight_and_embed_colors(self, fart_db):
        lava_text = fart_db.format_uber_rare_highlight("lavashart")
        frost_text = fart_db.format_uber_rare_highlight("frostshart")
        assert "LAVASHART" in lava_text
        assert "UBER-RARE" in lava_text
        assert "🌋" in lava_text
        assert "FROSTSHART" in frost_text
        assert "❄" in frost_text or "🥶" in frost_text

        lava_embed = fart_db.build_uber_rare_embed("lavashart")
        frost_embed = fart_db.build_uber_rare_embed("frostshart")
        assert lava_embed.color.value == UBER_RARE_CURIO_VARIANTS["lavashart"]["color"]
        assert frost_embed.color.value == UBER_RARE_CURIO_VARIANTS["frostshart"]["color"]

    def test_classify_curio_threshold(self):
        msg, typ = FunCog.classify_fart_roll(96)
        assert typ == "curio_shart"
        assert "Curio Shart" in msg
        _, typ95 = FunCog.classify_fart_roll(95)
        assert typ95 == "unique"

    def test_farthelp_keeps_curio_shart_but_hides_variants(self):
        """Uber-rare variants must never appear in public help text."""
        fun_path = os.path.join(os.path.dirname(__file__), "..", "cogs", "fun.py")
        with open(fun_path, encoding="utf-8") as f:
            source = f.read()
        help_section = source.split("Fart Types Section", 1)[1].split("embed.set_footer", 1)[0]
        assert "Curio Shart" in help_section
        assert "Lavashart" not in help_section
        assert "Frostshart" not in help_section
        assert "Uber-rare Curio" not in help_section
        assert "10% of Curios" not in help_section


class TestUberRareVariantEffects:
    @pytest.fixture()
    def effect_db(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        bot = MagicMock()
        shop = MagicMock()
        shop.get_sorted_players = AsyncMock(
            return_value=[(1, 100), (2, 80), (3, 60), (99, 40)]
        )
        shop.is_protected = AsyncMock(side_effect=lambda uid: uid == 3)
        shop.deduct_damage = AsyncMock(side_effect=lambda uid, dmg: dmg)
        shop.check_gas_shield = AsyncMock(return_value=None)
        bot.get_cog.return_value = shop
        cog = FunCog(bot)
        yield cog, shop
        if os.path.exists("fart_scores.db"):
            os.remove("fart_scores.db")

    def _seed_players(self):
        conn = sqlite3.connect("fart_scores.db")
        conn.execute(
            "CREATE TABLE fart_scores ("
            "user_id INTEGER PRIMARY KEY, user_display_name TEXT, "
            "date_last_updated TEXT, score INTEGER)"
        )
        for uid, name, score in [
            (1, "Roller", 100),
            (2, "Bob", 80),
            (3, "Star", 60),
            (99, "Other", 40),
        ]:
            conn.execute(
                "INSERT INTO fart_scores VALUES (?, ?, NULL, ?)",
                (uid, name, score),
            )
        conn.commit()
        conn.close()

    def test_lavashart_damages_all_except_roller_and_star(self, effect_db):
        cog, shop = effect_db
        self._seed_players()
        ctx = MagicMock()

        msg = asyncio.run(
            cog.apply_uber_rare_variant_effect(ctx, roller_id=1, variant="lavashart")
        )

        assert "LAVASHART ERUPTION" in msg
        assert "Scorched for 50 damage" in msg
        assert "<@2>" in msg
        assert "<@99>" in msg
        assert "<@3>" in msg  # star-protected mention
        assert "Star-shielded" in msg
        assert shop.deduct_damage.await_count == 2
        calls = [call.args for call in shop.deduct_damage.await_args_list]
        assert (2, 50) in calls
        assert (99, 50) in calls
        shop.check_gas_shield.assert_awaited()

    def test_frostshart_freezes_all_except_roller_and_star(self, effect_db):
        cog, shop = effect_db
        self._seed_players()

        msg = asyncio.run(
            cog.apply_uber_rare_variant_effect(
                MagicMock(), roller_id=1, variant="frostshart"
            )
        )

        assert "FROSTSHART BLIZZARD" in msg
        assert "<@2>" in msg
        assert "<@99>" in msg
        assert "<@3>" in msg
        assert "Frozen until midnight EST" in msg
        assert "Star-shielded" in msg
        assert cog.is_frost_frozen(2) is True
        assert cog.is_frost_frozen(99) is True
        assert cog.is_frost_frozen(3) is False

        conn = sqlite3.connect("fart_scores.db")
        bob_last = conn.execute(
            "SELECT date_last_updated FROM fart_scores WHERE user_id = 2"
        ).fetchone()[0]
        conn.close()
        assert bob_last is not None
