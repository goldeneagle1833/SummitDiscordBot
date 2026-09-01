"""Tests for shop item peel-out rate limit (5 uses / 30 minutes)."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.modules.setdefault(
    "config",
    MagicMock(
        OPENAI_API_KEY="test",
        FART_CHANNEL_ID=1,
        GUILD_ID=1,
        LEADER_ROLE_ID=1,
        DM_DISABLED_ROLE_ID=1,
    ),
)

from cogs.shop import ShopCog  # noqa: E402


@pytest.fixture()
def shop_cog():
    with patch.object(ShopCog, "setup_purchase_database"):
        cog = ShopCog(MagicMock())
    return cog


class TestFormatRateLimitRemaining:
    def test_seconds_only(self):
        assert ShopCog.format_rate_limit_remaining(45) == "45s"

    def test_minutes_and_seconds(self):
        assert ShopCog.format_rate_limit_remaining(125) == "2m 5s"

    def test_rounds_up_partial_second(self):
        assert ShopCog.format_rate_limit_remaining(0.1) == "1s"

    def test_hours(self):
        assert ShopCog.format_rate_limit_remaining(3700) == "1h 1m"


class TestShopRateLimit:
    def test_allows_under_limit(self, shop_cog):
        now = 1_000_000.0
        for i in range(5):
            allowed, remaining = shop_cog.check_shop_rate_limit(42, now=now + i)
            assert allowed is True
            assert remaining is None
            shop_cog.record_shop_usage(42, now=now + i)

    def test_blocks_sixth_use_within_window(self, shop_cog):
        now = 1_000_000.0
        for i in range(5):
            shop_cog.record_shop_usage(42, now=now + i)

        allowed, remaining = shop_cog.check_shop_rate_limit(42, now=now + 10)
        assert allowed is False
        assert remaining is not None
        # Oldest use at now; window is 30 min → ~1790s left
        assert 1790 <= remaining <= 1800

    def test_allows_again_after_oldest_expires(self, shop_cog):
        now = 1_000_000.0
        for i in range(5):
            shop_cog.record_shop_usage(42, now=now + i)

        # Just after the oldest use falls outside the 30-minute window
        later = now + ShopCog.SHOP_RATE_LIMIT_WINDOW_SECONDS + 0.1
        allowed, remaining = shop_cog.check_shop_rate_limit(42, now=later)
        assert allowed is True
        assert remaining is None

    def test_users_tracked_independently(self, shop_cog):
        now = 1_000_000.0
        for i in range(5):
            shop_cog.record_shop_usage(1, now=now + i)

        allowed_a, _ = shop_cog.check_shop_rate_limit(1, now=now + 10)
        allowed_b, _ = shop_cog.check_shop_rate_limit(2, now=now + 10)
        assert allowed_a is False
        assert allowed_b is True

    def test_gas_gamble_and_fart_shop_are_exempt(self, shop_cog):
        assert "gas_gamble" in ShopCog.RATE_LIMIT_EXEMPT
        assert "fart_shop" in ShopCog.RATE_LIMIT_EXEMPT
        assert "banana" not in ShopCog.RATE_LIMIT_EXEMPT
        assert "blue_shell" not in ShopCog.RATE_LIMIT_EXEMPT

    def test_peel_out_message_includes_wait_time(self, shop_cog):
        msg = shop_cog.peel_out_message("<@123>", 125)
        assert "PEEL OUT!!!!" in msg
        assert "<@123>" in msg
        assert "2m 5s" in msg
        assert "too many shop items" in msg


@pytest.mark.asyncio
class TestCogCheckRateLimit:
    async def test_cog_check_blocks_and_sends_peel_out(self, shop_cog, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        now = 1_000_000.0
        for i in range(5):
            shop_cog.record_shop_usage(99, now=now + i)

        ctx = MagicMock()
        ctx.command.name = "banana"
        ctx.author.id = 99
        ctx.author.mention = "<@99>"
        ctx.send = AsyncMock()

        with patch("cogs.shop.time.time", return_value=now + 10):
            result = await shop_cog.cog_check(ctx)

        assert result is False
        ctx.send.assert_awaited_once()
        sent = ctx.send.await_args.args[0]
        assert "PEEL OUT!!!!" in sent
        assert "too many shop items" in sent

    async def test_cog_check_allows_gas_gamble_when_limited(self, shop_cog, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        now = 1_000_000.0
        for i in range(5):
            shop_cog.record_shop_usage(99, now=now + i)

        ctx = MagicMock()
        ctx.command.name = "gas_gamble"
        ctx.author.id = 99
        ctx.author.mention = "<@99>"
        ctx.send = AsyncMock()

        with patch("cogs.shop.time.time", return_value=now + 10):
            # Stink cloud table must exist / empty — use temp cwd
            result = await shop_cog.cog_check(ctx)

        assert result is True
        ctx.send.assert_not_called()
        # gas_gamble must not consume another rate-limit slot
        assert len(shop_cog.prune_shop_usage(99, now=now + 10)) == 5

    async def test_cog_check_allows_and_records_under_limit(self, shop_cog, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ctx = MagicMock()
        ctx.command.name = "red_shell"
        ctx.author.id = 7
        ctx.author.mention = "<@7>"
        ctx.send = AsyncMock()
        shop_cog.check_fart_trap = AsyncMock(return_value=False)

        with patch("cogs.shop.time.time", return_value=5_000.0):
            result = await shop_cog.cog_check(ctx)

        assert result is True
        assert len(shop_cog._shop_usage.get(7, [])) == 1


class TestYourtShopChaos:
    def test_peel_out_skipped_during_yourt(self, shop_cog):
        shop_cog.yourt_waives_shop_limits = MagicMock(return_value=True)
        now = 1_000_000.0
        for i in range(5):
            shop_cog.record_shop_usage(42, now=now + i)
        # Would be blocked normally; waive helper is what cog_check consults
        assert shop_cog.yourt_waives_shop_limits() is True

    @pytest.mark.asyncio
    async def test_cog_check_skips_peel_out_during_yourt(
        self, shop_cog, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        now = 1_000_000.0
        for i in range(5):
            shop_cog.record_shop_usage(99, now=now + i)

        shop_cog.yourt_waives_shop_limits = MagicMock(return_value=True)
        shop_cog.check_fart_trap = AsyncMock(return_value=False)
        ctx = MagicMock()
        ctx.command.name = "banana"
        ctx.command.reset_cooldown = MagicMock()
        ctx.author.id = 99
        ctx.author.mention = "<@99>"
        ctx.send = AsyncMock()

        with patch("cogs.shop.time.time", return_value=now + 10):
            result = await shop_cog.cog_check(ctx)

        assert result is True
        ctx.send.assert_not_called()
        # Must not consume another peel-out slot during Yourt
        assert len(shop_cog.prune_shop_usage(99, now=now + 10)) == 5

    @pytest.mark.asyncio
    async def test_points_and_cooldowns_waived(self, shop_cog):
        shop_cog.yourt_waives_shop_limits = MagicMock(return_value=True)
        assert await shop_cog.check_points(1, "blue") is True
        await shop_cog.deduct_points(1, "blue")  # no-op, no DB
        allowed, msg = await shop_cog.check_usage_cooldown(1, "blue_shell", "daily")
        assert allowed is True
        assert msg is None
        await shop_cog.mark_usage_cooldown(1, "blue_shell")  # no-op

    @pytest.mark.asyncio
    async def test_loot_message_after_invoke(self, shop_cog):
        shop_cog.yourt_waives_shop_limits = MagicMock(return_value=True)
        ctx = MagicMock()
        ctx.command.name = "banana"
        ctx.author.mention = "<@7>"
        ctx.send = AsyncMock()

        await shop_cog.cog_after_invoke(ctx)

        ctx.send.assert_awaited_once()
        sent = ctx.send.await_args.args[0]
        assert "looted" in sent.lower() or "LoOtEd" in sent
        assert "shopkeeper" in sent.lower() or "ShOpKeEpEr" in sent
        assert ":yourt:" in sent

    @pytest.mark.asyncio
    async def test_loot_skipped_for_fart_shop(self, shop_cog):
        shop_cog.yourt_waives_shop_limits = MagicMock(return_value=True)
        ctx = MagicMock()
        ctx.command.name = "fart_shop"
        ctx.send = AsyncMock()
        await shop_cog.cog_after_invoke(ctx)
        ctx.send.assert_not_called()


@pytest.mark.asyncio
class TestFrostshartShopCogCheck:
    async def _frozen_shop(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from cogs.fun import FunCog

        fun = FunCog(MagicMock())
        fun.apply_frost_shart_freeze(99)
        bot = MagicMock()
        bot.get_cog.side_effect = lambda name: fun if name == "FunCog" else None
        with patch.object(ShopCog, "setup_purchase_database"):
            shop = ShopCog(bot)
        return shop, fun

    async def test_blocks_catalog_and_purchases(self, tmp_path, monkeypatch):
        shop, _ = await self._frozen_shop(tmp_path, monkeypatch)
        for name in ("fart_shop", "banana", "gas_gamble", "star"):
            ctx = MagicMock()
            ctx.command.name = name
            ctx.author.id = 99
            ctx.author.mention = "<@99>"
            ctx.send = AsyncMock()
            assert await shop.cog_check(ctx) is False
            sent = ctx.send.await_args.args[0]
            assert "frozen solid by a Frostshart" in sent
            assert "No shop items" in sent

    async def test_allows_unlisted_giga_cannon(self, tmp_path, monkeypatch):
        shop, _ = await self._frozen_shop(tmp_path, monkeypatch)
        shop.check_fart_trap = AsyncMock(return_value=False)
        ctx = MagicMock()
        ctx.command.name = "giga_fart_cannon"
        ctx.author.id = 99
        ctx.author.mention = "<@99>"
        ctx.send = AsyncMock()
        assert await shop.cog_check(ctx) is True
        ctx.send.assert_not_called()

    async def test_unfrozen_player_can_browse_shop(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from cogs.fun import FunCog

        fun = FunCog(MagicMock())
        bot = MagicMock()
        bot.get_cog.side_effect = lambda name: fun if name == "FunCog" else None
        with patch.object(ShopCog, "setup_purchase_database"):
            shop = ShopCog(bot)
        ctx = MagicMock()
        ctx.command.name = "fart_shop"
        ctx.author.id = 99
        ctx.author.mention = "<@99>"
        ctx.send = AsyncMock()
        assert await shop.cog_check(ctx) is True
        ctx.send.assert_not_called()

