"""!fartabundance: pay 500, get 400 back, seven doubled farts once per season.

Core farts ask first. Yes doubles the scored points and stacks with mushroom.
No and a timeout leave the charge and the daily unused.
"""

import datetime
import sqlite3
import sys
from pathlib import Path
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

from cogs.fun import (  # noqa: E402
    ABUNDANCE_CHARGES,
    AbundantFartView,
    FartPredictionView,
    FunCog,
    PREGNANT_MAN,
    format_fart_admin_help,
    format_fart_inventory,
)
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


def _insert_score(user_id, score, date_last_updated=None):
    conn = sqlite3.connect("fart_scores.db")
    _scores_table(conn)
    conn.execute(
        "INSERT INTO fart_scores (user_id, user_display_name, date_last_updated, score) "
        "VALUES (?, 'Tester', ?, ?)",
        (user_id, date_last_updated, score),
    )
    conn.commit()
    conn.close()


def _charm(user_id):
    conn = sqlite3.connect("fart_scores.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lucky_charms (
            user_id INTEGER PRIMARY KEY,
            activated_at TEXT
        )
    """)
    conn.execute(
        "INSERT OR REPLACE INTO lucky_charms (user_id, activated_at) VALUES (?, ?)",
        (user_id, "2026-01-01T00:00:00"),
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


def _charges(user_id):
    conn = sqlite3.connect("fart_scores.db")
    try:
        row = conn.execute(
            "SELECT charges_remaining, charges_granted FROM abundance_buff WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()
    return row


def _set_charges(user_id, remaining):
    conn = sqlite3.connect("fart_scores.db")
    conn.execute(
        "UPDATE abundance_buff SET charges_remaining = ? WHERE user_id = ?",
        (remaining, user_id),
    )
    conn.commit()
    conn.close()


def _history(user_id):
    conn = sqlite3.connect("fart_scores.db")
    try:
        rows = conn.execute(
            "SELECT fart_type, roll FROM fart_history WHERE user_id = ? ORDER BY timestamp",
            (user_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
    return rows


def _date_last_updated(user_id):
    conn = sqlite3.connect("fart_scores.db")
    row = conn.execute(
        "SELECT date_last_updated FROM fart_scores WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return None if row is None else row[0]


@pytest.fixture()
def fun(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cog = FunCog(MagicMock())
    cog.bot.get_guild = MagicMock(return_value=None)
    return cog


@pytest.fixture()
def shop(fun):
    fun.bot.get_cog.return_value = fun
    with patch.object(ShopCog, "setup_purchase_database"):
        cog = ShopCog(fun.bot)
    return cog


def _ctx(user_id=7, channel_id=1):
    ctx = MagicMock()
    ctx.channel.id = channel_id
    ctx.author.id = user_id
    ctx.author.global_name = "Tester"
    ctx.author.mention = f"<@{user_id}>"
    ctx.send = AsyncMock()
    return ctx


def _admin(ctx):
    ctx.author.guild_permissions.administrator = True
    return ctx


def _player(ctx):
    ctx.author.guild_permissions.administrator = False
    ctx.author.roles = []
    return ctx


async def _invoke(cog, name, ctx):
    command = getattr(cog, name)
    await command.callback(cog, ctx)


def _sent(ctx):
    parts = []
    for call in ctx.send.await_args_list:
        if call.args:
            parts.append(str(call.args[0]))
    return " ".join(parts)


def _patch_offer(monkeypatch, result):
    async def _offer(self, ctx, user_id):
        return result

    monkeypatch.setattr(FunCog, "offer_abundant_fart", _offer)


class TestFartAbundancePurchase:
    def test_aliases(self):
        aliases = set(ShopCog.fartabundance.aliases)
        assert "abundancefart" in aliases
        assert "fart_abundance" in aliases
        assert "abundance_fart" in aliases

    def test_inventory_aliases(self):
        aliases = set(FunCog.inventory.aliases)
        assert {"fartinventory", "fart_inventory", "inv"} <= aliases

    @pytest.mark.asyncio
    async def test_costs_500_and_refunds_400(self, shop):
        _insert_score(7, 1000)
        ctx = _ctx()
        await _invoke(shop, "fartabundance", ctx)

        assert _score(7) == 900
        assert _charges(7) == (ABUNDANCE_CHARGES, ABUNDANCE_CHARGES)
        body = _sent(ctx)
        assert "400" in body
        assert "Abundantly" in body
        assert PREGNANT_MAN in body
        assert str(ABUNDANCE_CHARGES) in body

    @pytest.mark.asyncio
    async def test_requires_500_on_hand(self, shop):
        _insert_score(7, 499)
        ctx = _ctx()
        await _invoke(shop, "fartabundance", ctx)

        assert _score(7) == 499
        assert _charges(7) is None
        assert "500" in _sent(ctx)

    @pytest.mark.asyncio
    async def test_exact_500_leaves_the_refund(self, shop):
        _insert_score(7, 500)
        await _invoke(shop, "fartabundance", _ctx())
        assert _score(7) == 400
        assert _charges(7) == (7, 7)

    @pytest.mark.asyncio
    async def test_second_purchase_same_season_does_not_charge(self, shop):
        _insert_score(7, 1000)
        await _invoke(shop, "fartabundance", _ctx())
        ctx = _ctx()
        await _invoke(shop, "fartabundance", ctx)
        assert _score(7) == 900
        assert _charges(7) == (7, 7)
        body = _sent(ctx).lower()
        assert "already bought" in body
        assert "7" in _sent(ctx)
        assert "left this season" in body

    @pytest.mark.asyncio
    async def test_spent_charges_still_block_a_rebuy(self, shop):
        _insert_score(7, 1000)
        await _invoke(shop, "fartabundance", _ctx())
        _set_charges(7, 0)
        ctx = _ctx()
        await _invoke(shop, "fartabundance", ctx)
        assert _score(7) == 900
        assert _charges(7) == (0, 7)
        assert "already used every" in _sent(ctx).lower()

    @pytest.mark.asyncio
    async def test_mushroom_can_be_bought_while_abundance_is_owned(self, shop):
        _insert_score(7, 1000)
        await _invoke(shop, "fartabundance", _ctx())
        ctx = _ctx()
        await _invoke(shop, "mushroom", ctx)
        assert _score(7) == 895
        assert _count("lucky_charms") == 1
        assert _charges(7) == (7, 7)
        assert "higher" in _sent(ctx)

    @pytest.mark.asyncio
    async def test_yourt_waives_cost_but_not_the_season_lock(self, shop):
        _insert_score(7, 80)
        with patch.object(shop, "yourt_waives_shop_limits", return_value=True):
            await _invoke(shop, "fartabundance", _ctx())
            assert _score(7) == 80
            assert _charges(7) == (7, 7)
            ctx = _ctx()
            await _invoke(shop, "fartabundance", ctx)
        assert _score(7) == 80
        assert "already bought" in _sent(ctx).lower()


class TestAbundanceRoll:
    @pytest.mark.asyncio
    async def test_yes_doubles_the_roll_and_spends_one_charge(self, fun, monkeypatch):
        fun.grant_abundance(5)
        _patch_offer(monkeypatch, "yes")
        rolls = iter([40, 70])
        monkeypatch.setattr("cogs.fun.randrange", lambda a, b: next(rolls))
        ctx = _ctx(5, fun.fart_channel_id)
        fun.update_fart_leader_role = AsyncMock()

        await fun.fart.callback(fun, ctx)

        assert _score(5) == 80
        assert _charges(5) == (6, 7)
        assert _history(5) == [("exceptional", 40)]
        body = _sent(ctx)
        assert "ABUNDANT" in body
        assert "doubled" in body.lower()
        assert PREGNANT_MAN in body

    @pytest.mark.asyncio
    async def test_no_keeps_the_charge_and_the_normal_roll(self, fun, monkeypatch):
        fun.grant_abundance(5)
        _patch_offer(monkeypatch, "no")
        rolls = iter([40, 70])
        monkeypatch.setattr("cogs.fun.randrange", lambda a, b: next(rolls))
        ctx = _ctx(5, fun.fart_channel_id)
        fun.update_fart_leader_role = AsyncMock()

        await fun.fart.callback(fun, ctx)

        assert _score(5) == 40
        assert _charges(5) == (7, 7)
        assert "ABUNDANT" not in _sent(ctx)

    @pytest.mark.asyncio
    async def test_timeout_does_not_use_the_daily_or_a_charge(self, fun, monkeypatch):
        fun.grant_abundance(5)
        _insert_score(5, 100)
        _patch_offer(monkeypatch, "timeout")
        ctx = _ctx(5, fun.fart_channel_id)

        await fun.fart.callback(fun, ctx)

        assert _score(5) == 100
        assert _date_last_updated(5) is None
        assert _charges(5) == (7, 7)
        assert _history(5) == []
        assert "not used" in _sent(ctx)

    @pytest.mark.asyncio
    async def test_mushroom_then_abundance_doubles_the_higher_roll(
        self, fun, monkeypatch
    ):
        fun.grant_abundance(5)
        _charm(5)
        _patch_offer(monkeypatch, "yes")
        rolls = iter([40, 70])
        monkeypatch.setattr("cogs.fun.randrange", lambda a, b: next(rolls))
        ctx = _ctx(5, fun.fart_channel_id)
        fun.update_fart_leader_role = AsyncMock()

        await fun.fart.callback(fun, ctx)

        assert _score(5) == 140
        assert _charges(5) == (6, 7)
        assert _count("lucky_charms") == 0
        assert _history(5) == [("elite", 70)]
        body = _sent(ctx)
        assert "MUSHROOM" in body
        assert "ABUNDANT" in body

    def test_forced_yes_does_nothing_when_the_bank_is_empty(self, fun):
        fun.grant_abundance(5, charges=1)
        points, doubled = fun.spend_abundance_double(5, 40, True)
        assert (points, doubled) == (80, True)
        points, doubled = fun.spend_abundance_double(5, 40, True)
        assert (points, doubled) == (40, False)
        assert _charges(5) == (0, 1)

    @pytest.mark.asyncio
    async def test_gift_yes_doubles_what_the_recipient_gets(self, fun, monkeypatch):
        fun.grant_abundance(5)
        _insert_score(5, 100)
        _patch_offer(monkeypatch, "yes")
        rolls = iter([40, 12])
        monkeypatch.setattr("cogs.fun.randrange", lambda a, b: next(rolls))
        ctx = _ctx(5, fun.fart_channel_id)
        target = MagicMock()
        target.id = 9
        target.bot = False
        target.global_name = "Giftee"
        target.display_name = "Giftee"
        fun.update_fart_leader_role = AsyncMock()

        await fun.fart_gift.callback(fun, ctx, target)

        assert _score(5) == 100
        assert _score(9) == 80
        assert _charges(5) == (6, 7)
        assert "ABUNDANT GIFT" in _sent(ctx)

    @pytest.mark.asyncio
    async def test_prediction_correct_then_abundance_is_four_times(
        self, fun, monkeypatch
    ):
        fun.grant_abundance(5)
        _insert_score(5, 0)
        rolls = iter([40, 12])
        monkeypatch.setattr("cogs.fun.randrange", lambda a, b: next(rolls))
        prediction = FartPredictionView(fun, 5, wants_abundant=True)
        interaction = MagicMock()
        interaction.user.global_name = "Tester"
        interaction.user.display_name = "Tester"
        interaction.followup.send = AsyncMock()
        fun.update_fart_leader_role = AsyncMock()

        await prediction.process_fart(interaction, "exceptional")

        # 40 is exceptional: correct is 80, Abundance doubles that to 160.
        assert _score(5) == 160
        assert _charges(5) == (6, 7)
        body = interaction.followup.send.await_args.args[0]
        assert "doubled it again" in body

    @pytest.mark.asyncio
    async def test_prediction_prompt_comes_before_the_dropdown(self, fun, monkeypatch):
        fun.grant_abundance(5)
        _insert_score(5, 0)
        seen = []

        async def _offer(self, ctx, user_id):
            seen.append(len(ctx.send.await_args_list))
            return "yes"

        monkeypatch.setattr(FunCog, "offer_abundant_fart", _offer)
        ctx = _ctx(5, fun.fart_channel_id)
        await fun.fartprediction.callback(fun, ctx)

        assert seen == [0]
        embed = ctx.send.await_args.kwargs["embed"]
        assert "Abundance is armed" in embed.description
        assert ctx.send.await_args.kwargs["view"].wants_abundant is True


class TestInventory:
    def test_lists_charges_reign_and_curios(self, fun):
        fun.grant_abundance(5)
        fun.record_uber_rare_hit(5, "lavashart")
        fun.record_uber_rare_hit(5, "lavashart")
        fun.record_uber_rare_hit(5, "frostshart")
        text = format_fart_inventory(fun.collect_fart_inventory(5))

        assert text.startswith("```\n")
        assert text.endswith("\n```")
        assert "INVENTORY" in text
        assert "Abundance: 7/7" in text
        assert "Lavashart: 2" in text
        assert "Frostshart: 1" in text
        assert "Yourt: 0" in text
        assert "Reign: open" in text
        assert "Evil Star: open" in text
        assert "Mushroom: none" in text
        assert "Actions" in text
        assert "Today" not in text
        assert "Daily fart: open" in text
        assert "Weekly bullfart: open" in text
        assert "blue shell" not in text.lower()
        assert "Weekly star" not in text
        assert "!rank: none yet" in text
        body_lines = [ln for ln in text.splitlines() if ln and ln != "```"]
        assert body_lines[-2].startswith("!rank:")
        assert body_lines[-1] == "================"
        assert "trap" not in text.lower()
        assert "***" not in text
        for line in text.strip("`").splitlines():
            assert len(line) <= 32

        conn = sqlite3.connect("fart_scores.db")
        flags = conn.execute(
            "SELECT variant, COUNT(*) FROM uber_rare_curio_season "
            "WHERE user_id = 5 GROUP BY variant ORDER BY variant"
        ).fetchall()
        hits = conn.execute(
            "SELECT COUNT(*) FROM uber_rare_hits WHERE user_id = 5 AND variant = 'lavashart'"
        ).fetchone()[0]
        conn.close()
        assert flags == [("frostshart", 1), ("lavashart", 1)]
        assert hits == 2

    def test_spent_reign_and_spent_abundance(self, fun):
        fun.grant_abundance(5)
        _set_charges(5, 0)
        conn = sqlite3.connect("fart_scores.db")
        conn.execute("""
            CREATE TABLE fart_leader_only_once (
                user_id INTEGER PRIMARY KEY,
                user_display_name TEXT
            )
        """)
        conn.execute(
            "INSERT INTO fart_leader_only_once (user_id, user_display_name) VALUES (5, 'Tester')"
        )
        conn.commit()
        conn.close()

        text = format_fart_inventory(fun.collect_fart_inventory(5))
        assert "Abundance: spent" in text
        assert "Reign: SPENT" in text

    def test_actions_are_only_fart_and_bullfart(self, fun):
        now = datetime.datetime.now()
        _insert_score(5, 120, date_last_updated=now.isoformat())
        _insert_score(9, 400)
        fun.mark_bullfart_used(5, when=now)
        conn = sqlite3.connect("fart_scores.db")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS command_usage (
                user_id INTEGER,
                command_name TEXT,
                last_used TEXT,
                PRIMARY KEY (user_id, command_name)
            )
        """)
        conn.execute(
            "INSERT INTO command_usage VALUES (5, 'star', ?)",
            (now.isoformat(),),
        )
        conn.execute(
            "INSERT INTO command_usage VALUES (5, 'blue_shell', ?)",
            (now.isoformat(),),
        )
        conn.commit()
        conn.close()

        text = format_fart_inventory(fun.collect_fart_inventory(5))
        assert "Daily fart: used" in text
        assert "Weekly bullfart: used" in text
        assert "blue shell" not in text.lower()
        assert "Weekly star" not in text
        assert "leech" not in text.lower()
        assert "Mushroom: none" in text
        assert "Abundance: not bought" in text
        assert "!rank: #2 · 120" in text
        rank_at = text.rfind("!rank:")
        assert rank_at > text.rfind("Uber curios")
        for line in text.strip("`").splitlines():
            assert len(line) <= 32

    def test_backfill_turns_old_hits_into_seasonal_flags(self, fun):
        conn = sqlite3.connect("fart_scores.db")
        conn.execute("""
            CREATE TABLE uber_rare_hits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                variant TEXT NOT NULL,
                hit_at TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO uber_rare_hits (user_id, variant, hit_at) VALUES (5, 'yourt', ?)",
            (datetime.datetime.now().isoformat(),),
        )
        conn.commit()
        conn.close()

        info = fun.collect_fart_inventory(5)
        assert "yourt" in info["curio_flags"]
        assert info["curios"]["yourt"] == 1

    @pytest.mark.asyncio
    async def test_inventory_command_sends_the_block(self, fun):
        ctx = _player(_ctx(5, fun.fart_channel_id))
        await fun.inventory.callback(fun, ctx)
        body = ctx.send.await_args.args[0]
        assert body.startswith("```")
        assert "INVENTORY" in body
        assert "Abundance: not bought" in body

    @pytest.mark.asyncio
    async def test_inventory_lookup_requires_the_admin_role(self, fun):
        fun.grant_abundance(9)
        ctx = _player(_ctx(5, fun.fart_channel_id))
        target = MagicMock()
        target.id = 9
        target.display_name = "Giftee"
        await fun.inventory.callback(fun, ctx, target)
        body = ctx.send.await_args.args[0]
        assert "your own inventory" in body
        assert "7/7" not in body

    @pytest.mark.asyncio
    async def test_inventory_can_look_up_another_player(self, fun):
        fun.grant_abundance(9)
        ctx = _admin(_ctx(5, fun.fart_channel_id))
        target = MagicMock()
        target.id = 9
        target.display_name = "Giftee With A Very Long Name"
        target.global_name = None
        await fun.inventory.callback(fun, ctx, target)
        body = ctx.send.await_args.args[0]
        assert "Abundance: 7/7" in body
        assert "For:" in body
        assert "Very Long Name" not in body
        for line in body.strip("`").splitlines():
            assert len(line) <= 32

    def test_guide_and_shop_name_only_fartabundance(self):
        root = Path(__file__).resolve().parents[1]
        fun_src = (root / "cogs" / "fun.py").read_text(encoding="utf-8")
        shop_src = (root / "cogs" / "shop.py").read_text(encoding="utf-8")
        help_fn = fun_src.split("async def helpfart", 1)[1].split(
            "def _ensure_roll_buff_tables", 1
        )[0]
        assert "Admin Commands" not in help_fn
        assert "!abundancefart" not in help_fn
        assert "!fartadmin" not in help_fn
        assert "`!inventory`" in help_fn
        note = (
            "Any new curio must be flagged the same way: a per-player "
            "seasonal flag that the Reset Fart Game button wipes."
        )
        assert note in fun_src
        repo = (root.parent / "web-app" / "repositories" / "fart.py").read_text(
            encoding="utf-8"
        )
        ui = (
            root.parent / "web-app" / "frontend" / "src" / "pages" / "Rumble.jsx"
        ).read_text(encoding="utf-8")
        assert note in repo
        assert note in ui
        assert "`!fartabundance`" in help_fn
        assert "!abundancefart" not in shop_src
        assert "!fartabundance / " not in shop_src


class TestGiveFart:
    @pytest.mark.asyncio
    async def test_admin_adds_points(self, fun):
        _insert_score(9, 10)
        ctx = _admin(_ctx(5, fun.fart_channel_id))
        user = MagicMock()
        user.id = 9
        user.bot = False
        user.mention = "<@9>"
        user.global_name = "Giftee"
        user.display_name = "Giftee"
        fun.update_fart_leader_role = AsyncMock()

        await fun.givefart.callback(fun, ctx, user, 25)

        assert _score(9) == 35
        body = _sent(ctx)
        assert "25" in body
        assert "35" in body

    @pytest.mark.asyncio
    async def test_non_admin_cannot_give_points(self, fun):
        _insert_score(9, 10)
        ctx = _player(_ctx(5, fun.fart_channel_id))
        user = MagicMock()
        user.id = 9
        user.bot = False
        user.mention = "<@9>"
        await fun.givefart.callback(fun, ctx, user, 25)
        assert _score(9) == 10
        assert "admin role" in _sent(ctx)

    @pytest.mark.asyncio
    async def test_rejects_non_positive_points(self, fun):
        _insert_score(9, 10)
        ctx = _admin(_ctx(5, fun.fart_channel_id))
        user = MagicMock()
        user.id = 9
        user.bot = False
        user.mention = "<@9>"
        await fun.givefart.callback(fun, ctx, user, 0)
        assert _score(9) == 10
        assert "positive" in _sent(ctx).lower()


class TestFartAdmin:
    def test_help_lines_stay_short(self):
        text = format_fart_admin_help()
        assert "FART ADMIN" in text
        assert "!givefart" in text
        assert "!reset_fart_cooldown" in text
        for line in text.strip("`").splitlines():
            assert len(line) <= 32

    @pytest.mark.asyncio
    async def test_admin_sees_the_list(self, fun):
        ctx = _admin(_ctx(5, fun.fart_channel_id))
        await fun.fartadmin.callback(fun, ctx)
        body = ctx.send.await_args.args[0]
        assert "FART ADMIN" in body
        assert "!givefart" in body

    @pytest.mark.asyncio
    async def test_player_cannot_open_the_list(self, fun):
        ctx = _player(_ctx(5, fun.fart_channel_id))
        await fun.fartadmin.callback(fun, ctx)
        body = ctx.send.await_args.args[0]
        assert "admin role" in body
        assert "FART ADMIN" not in body

    def test_abundant_view_buttons(self):
        view = AbundantFartView(5)
        labels = [child.label for child in view.children]
        emojis = [str(getattr(child.emoji, "name", child.emoji)) for child in view.children]
        assert "Fart Abundantly" in labels
        assert "Not this one" in labels
        assert "✅" in emojis
        assert "❌" in emojis
