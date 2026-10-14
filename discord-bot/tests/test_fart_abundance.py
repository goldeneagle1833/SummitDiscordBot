"""!fartabundance: 500 cost, 400 refund, next !fart keeps both rolls.

The weekly lock is its own row, separate from !mushroom. The two buffs
do not apply to the same fart.
"""

import sqlite3
import sys
from datetime import datetime, timedelta
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

from cogs.fun import FunCog  # noqa: E402
from cogs.shop import ShopCog  # noqa: E402


def _scores_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fart_scores (
            user_id INTEGER PRIMARY KEY,
            user_display_name TEXT,
            date_last_updated TEXT,
            score INTEGER
        )
    """)


def _score(user_id):
    conn = sqlite3.connect("fart_scores.db")
    row = conn.execute(
        "SELECT score FROM fart_scores WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return None if row is None else row[0]


def _insert_score(user_id, score):
    conn = sqlite3.connect("fart_scores.db")
    _scores_table(conn)
    conn.execute(
        "INSERT INTO fart_scores (user_id, user_display_name, date_last_updated, score) "
        "VALUES (?, 'Tester', NULL, ?)",
        (user_id, score),
    )
    conn.commit()
    conn.close()


def _charm(table, user_id, when=None):
    when = when or datetime.now().isoformat()
    conn = sqlite3.connect("fart_scores.db")
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {table} (
            user_id INTEGER PRIMARY KEY,
            activated_at TEXT
        )
    """)
    conn.execute(
        f"INSERT OR REPLACE INTO {table} (user_id, activated_at) VALUES (?, ?)",
        (user_id, when),
    )
    conn.commit()
    conn.close()


def _usage(user_id, command_name, when=None):
    when = when or datetime.now().isoformat()
    conn = sqlite3.connect("fart_scores.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lucky_charm_usage (
            user_id INTEGER,
            command_name TEXT,
            last_used TEXT,
            PRIMARY KEY (user_id, command_name)
        )
    """)
    conn.execute(
        "INSERT OR REPLACE INTO lucky_charm_usage (user_id, command_name, last_used) "
        "VALUES (?, ?, ?)",
        (user_id, command_name, when),
    )
    conn.commit()
    conn.close()


def _count(table):
    conn = sqlite3.connect("fart_scores.db")
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def _usage_names(user_id):
    conn = sqlite3.connect("fart_scores.db")
    try:
        rows = conn.execute(
            "SELECT command_name FROM lucky_charm_usage WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return set()
    finally:
        conn.close()
    return {row[0] for row in rows}


@pytest.fixture()
def shop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch.object(ShopCog, "setup_purchase_database"):
        cog = ShopCog(MagicMock())
    return cog


def _ctx(user_id=7):
    ctx = MagicMock()
    ctx.author.id = user_id
    ctx.author.mention = f"<@{user_id}>"
    ctx.send = AsyncMock()
    return ctx


async def _invoke(cog, name, ctx):
    command = getattr(cog, name)
    await command.callback(cog, ctx)


def _sent(ctx):
    return " ".join(call.args[0] for call in ctx.send.await_args_list if call.args)


class TestFartAbundancePurchase:
    def test_aliases(self):
        aliases = set(ShopCog.fartabundance.aliases)
        assert "abundancefart" in aliases
        assert "fart_abundance" in aliases
        assert "abundance_fart" in aliases

    @pytest.mark.asyncio
    async def test_costs_500_and_refunds_400(self, shop):
        _insert_score(7, 1000)
        ctx = _ctx()
        await _invoke(shop, "fartabundance", ctx)

        assert _score(7) == 900
        assert _count("abundance_charms") == 1
        assert _usage_names(7) == {"fartabundance"}
        assert "400" in _sent(ctx)
        assert "both" in _sent(ctx).lower()

    @pytest.mark.asyncio
    async def test_requires_500_on_hand(self, shop):
        _insert_score(7, 499)
        ctx = _ctx()
        await _invoke(shop, "fartabundance", ctx)

        assert _score(7) == 499
        assert _count("abundance_charms") == 0
        assert "500" in _sent(ctx)

    @pytest.mark.asyncio
    async def test_exact_500_leaves_the_refund(self, shop):
        _insert_score(7, 500)
        await _invoke(shop, "fartabundance", _ctx())
        assert _score(7) == 400

    @pytest.mark.asyncio
    async def test_weekly_lock_is_separate_from_mushroom(self, shop):
        _insert_score(7, 1000)
        _usage(7, "mushroom")
        ctx = _ctx()
        await _invoke(shop, "fartabundance", ctx)

        assert _score(7) == 900
        assert _usage_names(7) == {"mushroom", "fartabundance"}
        assert _count("abundance_charms") == 1
        assert _count("lucky_charms") == 0

    @pytest.mark.asyncio
    async def test_second_use_same_week_does_not_charge(self, shop):
        _insert_score(7, 1000)
        await _invoke(shop, "fartabundance", _ctx())
        conn = sqlite3.connect("fart_scores.db")
        conn.execute("DELETE FROM abundance_charms")
        conn.commit()
        conn.close()

        ctx = _ctx()
        await _invoke(shop, "fartabundance", ctx)
        assert _score(7) == 900
        assert "once per week" in _sent(ctx)
        assert _count("abundance_charms") == 0

    @pytest.mark.asyncio
    async def test_does_not_stack_with_active_mushroom(self, shop):
        _insert_score(7, 1000)
        _charm("lucky_charms", 7)
        ctx = _ctx()
        await _invoke(shop, "fartabundance", ctx)

        assert _score(7) == 1000
        assert _count("abundance_charms") == 0
        assert "fartabundance" not in _usage_names(7)
        assert "Mushroom" in _sent(ctx)

    @pytest.mark.asyncio
    async def test_already_active_does_not_charge_again(self, shop):
        _insert_score(7, 1000)
        old = (datetime.now() - timedelta(days=8)).isoformat()
        _charm("abundance_charms", 7, old)
        _usage(7, "fartabundance", old)
        ctx = _ctx()
        await _invoke(shop, "fartabundance", ctx)

        assert _score(7) == 1000
        assert "already have" in _sent(ctx).lower()

    @pytest.mark.asyncio
    async def test_mushroom_still_works_the_same_week(self, shop):
        _insert_score(7, 1000)
        await _invoke(shop, "fartabundance", _ctx())
        conn = sqlite3.connect("fart_scores.db")
        conn.execute("DELETE FROM abundance_charms")
        conn.commit()
        conn.close()

        ctx = _ctx()
        await _invoke(shop, "mushroom", ctx)
        assert _score(7) == 895
        assert _count("lucky_charms") == 1
        assert _usage_names(7) == {"mushroom", "fartabundance"}
        assert "higher" in _sent(ctx)

    @pytest.mark.asyncio
    async def test_mushroom_blocked_while_abundance_is_active(self, shop):
        _insert_score(7, 1000)
        _charm("abundance_charms", 7)
        ctx = _ctx()
        await _invoke(shop, "mushroom", ctx)
        assert _score(7) == 1000
        assert _count("lucky_charms") == 0
        assert "Fart Abundance" in _sent(ctx)

    @pytest.mark.asyncio
    async def test_yourt_waives_cost_and_weekly_lock(self, shop):
        _insert_score(7, 80)
        _usage(7, "fartabundance")
        with patch.object(shop, "yourt_waives_shop_limits", return_value=True):
            await _invoke(shop, "fartabundance", _ctx())
        assert _score(7) == 80
        assert _count("abundance_charms") == 1
        assert _usage_names(7) == {"fartabundance"}


class TestAbundanceRoll:
    @pytest.fixture()
    def fun(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cog = FunCog(MagicMock())
        cog.bot.get_guild = MagicMock(return_value=None)
        return cog

    def test_sums_both_rolls_and_leaves_mushroom_armed(self, fun):
        _charm("abundance_charms", 5)
        _charm("lucky_charms", 5)
        mode, points, rolls = fun.consume_fart_roll_buff(
            5, 40, 70, allow_abundance=True
        )
        assert mode == "abundance"
        assert points == 110
        assert rolls == (40, 70)
        assert _count("abundance_charms") == 0
        assert _count("lucky_charms") == 1

    def test_gift_and_prediction_do_not_consume_abundance(self, fun):
        _charm("abundance_charms", 5)
        _charm("lucky_charms", 5)
        mode, points, _rolls = fun.consume_fart_roll_buff(
            5, 40, 70, allow_abundance=False
        )
        assert mode == "mushroom"
        assert points == 70
        assert _count("abundance_charms") == 1
        assert _count("lucky_charms") == 0

    def test_plain_roll_ignores_the_second_die(self, fun):
        mode, points, rolls = fun.consume_fart_roll_buff(
            5, 40, 70, allow_abundance=True
        )
        assert mode is None
        assert points == 40
        assert rolls == (40,)

    @pytest.mark.asyncio
    async def test_fart_command_awards_both_and_uses_the_daily(self, fun, monkeypatch):
        _charm("abundance_charms", 5)
        _charm("lucky_charms", 5)
        rolls = iter([40, 70])
        monkeypatch.setattr("cogs.fun.randrange", lambda a, b: next(rolls))

        ctx = MagicMock()
        ctx.channel.id = fun.fart_channel_id
        ctx.author.id = 5
        ctx.author.global_name = "Tester"
        ctx.author.mention = "<@5>"
        ctx.send = AsyncMock()
        fun.update_fart_leader_role = AsyncMock()

        await fun.fart.callback(fun, ctx)

        assert _score(5) == 110
        assert _count("abundance_charms") == 0
        assert _count("lucky_charms") == 1
        conn = sqlite3.connect("fart_scores.db")
        history = conn.execute(
            "SELECT fart_type, roll FROM fart_history ORDER BY timestamp"
        ).fetchall()
        conn.close()
        assert history == [("exceptional", 40), ("elite", 70)]
        assert fun.get_latest_fart_type(5) == "elite"
        body = ctx.send.await_args.args[0]
        assert "FART ABUNDANCE" in body
        assert "110" in body

        ctx.send.reset_mock()
        await fun.fart.callback(fun, ctx)
        assert _score(5) == 110
        assert "already used" in ctx.send.await_args.args[0]
