"""Tests for uber-rare Curio Shart (frost / lava / Yourt) roll odds."""

import asyncio
import datetime
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
    YOURT_ATTACKS_TOTAL,
    YOURT_ATTACK_EVERY_SECONDS,
    drunken_case,
)


@pytest.fixture()
def fart_db(tmp_path, monkeypatch):
    """Run uber-rare helpers against a temp fart_scores.db in cwd."""
    monkeypatch.chdir(tmp_path)
    cog = FunCog(MagicMock())
    yield cog
    if os.path.exists("fart_scores.db"):
        os.remove("fart_scores.db")


class TestUberRareCurioOdds:
    def test_frost_hits_on_1_through_10(self, fart_db):
        for bucket in (1, 5, 10):
            with patch("cogs.fun.randrange", return_value=bucket):
                assert fart_db.roll_uber_rare_curio_variant(user_id=99) == "frostshart"

    def test_lava_hits_on_11_through_20(self, fart_db):
        for bucket in (11, 15, 20):
            with patch("cogs.fun.randrange", return_value=bucket):
                assert fart_db.roll_uber_rare_curio_variant(user_id=7) == "lavashart"

    def test_yourt_hits_on_21_through_25(self, fart_db):
        for bucket in (21, 23, 25):
            with patch("cogs.fun.randrange", return_value=bucket):
                assert fart_db.roll_uber_rare_curio_variant(user_id=3) == "yourt"

    def test_miss_from_26(self, fart_db):
        for bucket in (26, 50, 100):
            with patch("cogs.fun.randrange", return_value=bucket):
                assert fart_db.roll_uber_rare_curio_variant(user_id=1) is None

    def test_same_player_can_roll_the_same_variant_again(self, fart_db):
        with patch("cogs.fun.randrange", return_value=1):
            assert fart_db.roll_uber_rare_curio_variant(user_id=42) == "frostshart"
        with patch("cogs.fun.randrange", return_value=1):
            assert fart_db.roll_uber_rare_curio_variant(user_id=42) == "frostshart"

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
        yourt_embed = fart_db.build_uber_rare_embed("yourt")
        assert lava_embed.color.value == UBER_RARE_CURIO_VARIANTS["lavashart"]["color"]
        assert frost_embed.color.value == UBER_RARE_CURIO_VARIANTS["frostshart"]["color"]
        assert yourt_embed.color.value == UBER_RARE_CURIO_VARIANTS["yourt"]["color"]
        # Flavor belongs on the embed once — not repeated in the chat banner.
        frost_flavor = UBER_RARE_CURIO_VARIANTS["frostshart"]["flavor"]
        assert frost_flavor in frost_embed.description
        assert frost_flavor not in frost_text
        assert "UNLOCKED" not in frost_text
        assert frost_embed.footer.text is None or frost_embed.footer.text == ""

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
        assert "Yourt" not in help_section
        assert "Yourtshart" not in help_section
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

        assert "LAVASHART!" in msg
        assert "Scorched for 50" in msg
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

        assert "FROSTSHART!" in msg
        assert "<@2>" in msg
        assert "<@99>" in msg
        assert "<@3>" in msg
        assert "Frozen 24h" in msg
        assert "`!fart` still works" in msg
        assert "Star-shielded" in msg
        assert cog.is_frost_frozen(2) is True
        assert cog.is_frost_frozen(99) is True
        assert cog.is_frost_frozen(3) is False

        conn = sqlite3.connect("fart_scores.db")
        bob_last = conn.execute(
            "SELECT date_last_updated FROM fart_scores WHERE user_id = 2"
        ).fetchone()[0]
        until = conn.execute(
            "SELECT frozen_until FROM frost_shart_freeze WHERE user_id = 2"
        ).fetchone()[0]
        conn.close()
        assert bob_last is None  # default !fart is not consumed
        parsed = (
            until
            if isinstance(until, datetime.datetime)
            else datetime.datetime.fromisoformat(until)
        )
        remaining = parsed - datetime.datetime.now()
        assert datetime.timedelta(hours=23, minutes=50) < remaining < datetime.timedelta(
            hours=24, minutes=10
        )
        assert cog.is_frost_frozen(1) is False  # roller not frozen


class TestFrostshartFartMessaging:
    def test_frozen_player_gets_shop_block_message(self, fart_db):
        fart_db.apply_frost_shart_freeze(2, "Bob")
        msg = fart_db.frostshart_shop_block_message("<@2>")
        assert "frozen solid by a Frostshart" in msg
        assert "No shop items for 24 hours" in msg
        assert "No farting" not in msg
        assert "midnight EST" not in msg

    def test_default_fart_command_does_not_frost_block(self):
        fun_path = os.path.join(os.path.dirname(__file__), "..", "cogs", "fun.py")
        with open(fun_path, encoding="utf-8") as f:
            source = f.read()
        fart_cmd = source.split("async def fart(self, ctx):", 1)[1].split(
            "async def fart_gift", 1
        )[0]
        assert "frostshart_fart_block_message" not in fart_cmd
        assert "is_frost_frozen" not in fart_cmd
        assert "async def cog_check" not in source.split("class FunCog", 1)[1].split(
            "async def fart(self, ctx):", 1
        )[0]

    def test_fun_cog_does_not_frost_block_lookups_or_specials(self, fart_db):
        """Frostshart no longer uses a FunCog deny-list (lookups/admin stay up)."""
        for name in (
            "helpfart",
            "fartrank",
            "fartleaderboard",
            "reset_fart_cooldown",
            "fartprediction",
            "taxes",
        ):
            assert fart_db.frostshart_blocks_shop_command(name) is False

    def test_shop_commands_are_frost_blocked_including_catalog(self, fart_db):
        from cogs.fun import FROSTSHART_BLOCKED_SHOP_COMMANDS

        for name in (
            "fart_shop",
            "blue_shell",
            "red_shell",
            "green_shell",
            "banana",
            "big_banana",
            "star",
            "mushroom",
            "bobomb",
            "fart_star",
            "evil_star",
            "thunder_fart",
            "gas_shield",
            "stink_bomb",
            "fart_rocket",
            "fart_lance",
            "fart_trap",
            "fart_twister",
            "stink_cloud",
            "gas_gamble",
            "fart_leech",
            "fart_donation",
            "fart_court",
        ):
            assert name in FROSTSHART_BLOCKED_SHOP_COMMANDS
            assert fart_db.frostshart_blocks_shop_command(name) is True
        # Not in the freeze list — leave usable while frozen
        assert fart_db.frostshart_blocks_shop_command("giga_fart_cannon") is False

    def test_past_freeze_is_not_active(self, fart_db):
        conn = sqlite3.connect("fart_scores.db")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS frost_shart_freeze (
                user_id INTEGER PRIMARY KEY,
                frozen_until TEXT NOT NULL
            )
            """
        )
        past = datetime.datetime.now() - datetime.timedelta(minutes=1)
        conn.execute(
            "INSERT INTO frost_shart_freeze VALUES (?, ?)",
            (2, past.strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
        conn.close()
        assert fart_db.is_frost_frozen(2) is False

    def test_old_est_midnight_iso_freeze_expires_correctly(self, fart_db):
        """Legacy tz-aware EST midnight strings must not linger via SQLite string compare."""
        expired = datetime.datetime(
            2026, 8, 26, 0, 0, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=-4))
        )
        conn = sqlite3.connect("fart_scores.db")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS frost_shart_freeze (
                user_id INTEGER PRIMARY KEY,
                frozen_until TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO frost_shart_freeze VALUES (?, ?)",
            (2, expired.isoformat()),
        )
        conn.commit()
        conn.close()
        now = datetime.datetime(
            2026, 8, 27, 12, 0, 0, tzinfo=datetime.timezone.utc
        )
        assert fart_db.is_frost_frozen(2, now=now) is False


class TestFrostshartLegacyRepair:
    def _seed_frozen_player(self, user_id, name, score, last_updated, with_history_today=False):
        conn = sqlite3.connect("fart_scores.db")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS fart_scores ("
            "user_id INTEGER PRIMARY KEY, user_display_name TEXT, "
            "date_last_updated TEXT, score INTEGER)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS fart_history ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
            "username TEXT NOT NULL, fart_type TEXT NOT NULL, "
            "roll INTEGER NOT NULL, timestamp TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO fart_scores VALUES (?, ?, ?, ?)",
            (user_id, name, last_updated, score),
        )
        if with_history_today:
            conn.execute(
                "INSERT INTO fart_history (user_id, username, fart_type, roll, timestamp) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, name, "ordinary", 10, last_updated),
            )
        conn.commit()
        conn.close()

    def test_repair_clears_freezes_and_restores_unused_daily(self, fart_db):
        now = datetime.datetime(2026, 8, 27, 15, 0, 0)
        self._seed_frozen_player(2, "Bob", 80, now.isoformat(), with_history_today=False)
        fart_db.apply_frost_shart_freeze(2)
        assert fart_db.is_frost_frozen(2) is True

        result = fart_db.repair_legacy_frostshart_locks(now=now)
        assert result["ran"] is True
        assert result["cleared_freezes"] == 1
        assert result["restored_dailies"] == 1
        assert fart_db.is_frost_frozen(2) is False
        assert fart_db.has_frostshart_legacy_repair_ran() is True

        conn = sqlite3.connect("fart_scores.db")
        last = conn.execute(
            "SELECT date_last_updated FROM fart_scores WHERE user_id = 2"
        ).fetchone()[0]
        freeze_count = conn.execute("SELECT COUNT(*) FROM frost_shart_freeze").fetchone()[0]
        conn.close()
        assert last is None
        assert freeze_count == 0

    def test_repair_keeps_daily_if_real_fart_logged_today(self, fart_db):
        now = datetime.datetime(2026, 8, 27, 15, 0, 0)
        self._seed_frozen_player(3, "Casey", 60, now.isoformat(), with_history_today=True)
        fart_db.apply_frost_shart_freeze(3)

        result = fart_db.repair_legacy_frostshart_locks(now=now)
        assert result["ran"] is True
        assert result["cleared_freezes"] == 1
        assert result["restored_dailies"] == 0

        conn = sqlite3.connect("fart_scores.db")
        last = conn.execute(
            "SELECT date_last_updated FROM fart_scores WHERE user_id = 3"
        ).fetchone()[0]
        conn.close()
        assert last == now.isoformat()
        assert fart_db.is_frost_frozen(3) is False

    def test_repair_does_not_clear_freezes_applied_after_one_shot(self, fart_db):
        now = datetime.datetime(2026, 8, 27, 15, 0, 0)
        self._seed_frozen_player(2, "Bob", 80, now.isoformat())
        fart_db.apply_frost_shart_freeze(2)
        first = fart_db.repair_legacy_frostshart_locks(now=now)
        assert first["ran"] is True

        fart_db.apply_frost_shart_freeze(2)
        assert fart_db.is_frost_frozen(2) is True
        second = fart_db.repair_legacy_frostshart_locks(now=now)
        assert second["ran"] is False
        assert second["cleared_freezes"] == 0
        assert fart_db.is_frost_frozen(2) is True


class TestYourtCurioOdds:
    def test_yourt_skipped_while_rampage_active(self, fart_db):
        assert fart_db.start_yourt_rampage(channel_id=1, summoned_by_user_id=1) is True
        with patch("cogs.fun.randrange", return_value=21):
            assert fart_db.roll_uber_rare_curio_variant(user_id=2) is None

    def test_yourt_highlight_is_green_and_drunken(self, fart_db):
        text = fart_db.format_uber_rare_highlight("yourt")
        assert ":yourt:" in text
        assert drunken_case("YOURTSHART") in text
        embed = fart_db.build_uber_rare_embed("yourt")
        assert embed.color.value == 0x2ECC71


class TestYourtRampage:
    def test_start_and_active_window(self, fart_db):
        assert fart_db.is_yourt_rampage_active() is False
        assert fart_db.start_yourt_rampage(99, 7) is True
        assert fart_db.is_yourt_rampage_active() is True
        assert fart_db.start_yourt_rampage(99, 8) is False

    def test_expected_attacks_every_ten_minutes(self, fart_db):
        fart_db.start_yourt_rampage(1, 1)
        state = fart_db.get_yourt_rampage_state()
        started = datetime.datetime.fromisoformat(state["started_at"])
        assert fart_db.expected_yourt_attacks(state, now=started) == 0
        assert (
            fart_db.expected_yourt_attacks(
                state, now=started + datetime.timedelta(minutes=10)
            )
            == 1
        )
        assert (
            fart_db.expected_yourt_attacks(
                state, now=started + datetime.timedelta(minutes=59)
            )
            == 5
        )
        assert (
            fart_db.expected_yourt_attacks(
                state, now=started + datetime.timedelta(minutes=60)
            )
            == YOURT_ATTACKS_TOTAL
        )
        assert YOURT_ATTACK_EVERY_SECONDS == 600

    def test_apply_yourt_sends_here_ping(self, fart_db):
        ctx = MagicMock()
        ctx.channel.id = 123
        ctx.channel.send = AsyncMock()
        ctx.guild = None
        msg = asyncio.run(
            fart_db.apply_uber_rare_variant_effect(ctx, roller_id=1, variant="yourt")
        )
        assert fart_db.is_yourt_rampage_active() is True
        assert "YOURT wrecked the shop".lower() in msg.lower() or "wrecked" in msg.lower()
        ctx.channel.send.assert_awaited()
        sent = ctx.channel.send.await_args.args[0]
        assert "@here" in sent
        assert ":yourt:" in sent
        assert "YOURT" in sent.upper() or "YoUrT" in sent

    def test_retreat_clears_window(self, fart_db):
        fart_db.start_yourt_rampage(1, 1)
        state = fart_db.get_yourt_rampage_state()
        asyncio.run(fart_db._yourt_retreat(state))
        assert fart_db.is_yourt_rampage_active() is False
        assert fart_db.get_yourt_rampage_state() is None

    def test_ticker_fires_due_attacks_then_retreats(self, fart_db):
        fart_db.start_yourt_rampage(1, 1)
        state = fart_db.get_yourt_rampage_state()
        started = datetime.datetime.fromisoformat(state["started_at"])
        past_end = started + datetime.timedelta(hours=1, seconds=1)
        fart_db._yourt_random_attack = AsyncMock()
        fart_db._yourt_retreat = AsyncMock()
        asyncio.run(fart_db._tick_yourt_rampage(now=past_end))
        assert fart_db._yourt_random_attack.await_count == YOURT_ATTACKS_TOTAL
        fart_db._yourt_retreat.assert_awaited()


class TestYourtAttacks:
    def test_yourt_banana_hits_unprotected_player(self, fart_db):
        shop = MagicMock()
        shop.get_sorted_players = AsyncMock(return_value=[(1, 100), (2, 80)])
        shop.is_protected = AsyncMock(return_value=False)
        shop.deduct_damage = AsyncMock(return_value=7)
        shop.roll_damage = MagicMock(return_value=7)
        shop.roll_d10_damage = MagicMock(return_value=12)
        fart_db.bot.get_cog.return_value = shop
        fart_db._send_yourt_channel_message = AsyncMock()
        with patch("cogs.fun.random.choice", side_effect=["banana", 2]):
            asyncio.run(
                fart_db._yourt_random_attack(
                    {"channel_id": 1, "started_at": "x", "ends_at": "y", "attacks_done": 0}
                )
            )
        shop.deduct_damage.assert_awaited()
        fart_db._send_yourt_channel_message.assert_awaited()
        sent = fart_db._send_yourt_channel_message.await_args.args[1]
        assert "<@2>" in sent
        assert "YOURT" in sent.upper() or "YoUrT" in sent


