"""!fart_court while the Supreme Court order stands.

The first filing each season takes 100 points. A later filing is refused
with no charge. A player who cannot cover the fee is turned away and can
still file once they can pay. The old 50/50 stake case stays in shop.py,
commented out.
"""

import sqlite3
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


def _filed(user_id):
    conn = sqlite3.connect("fart_scores.db")
    try:
        row = conn.execute(
            "SELECT 1 FROM fart_court_filing WHERE user_id = ?", (user_id,)
        ).fetchone()
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()
    return row is not None


@pytest.fixture()
def shop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch.object(ShopCog, "setup_purchase_database"):
        cog = ShopCog(MagicMock())
    cog.fart_channel_id = 1
    return cog


def _ctx(user_id=7, channel_id=1):
    ctx = MagicMock()
    ctx.channel.id = channel_id
    ctx.author.id = user_id
    ctx.author.mention = f"<@{user_id}>"
    ctx.send = AsyncMock()
    return ctx


async def _court(shop, ctx, *args):
    await ShopCog.fart_court.callback(shop, ctx, *args)


def _sent(ctx):
    parts = []
    for call in ctx.send.await_args_list:
        if call.args:
            parts.append(str(call.args[0]))
    return "\n".join(parts)


class TestFartCourtOrder:
    def test_aliases_still_reach_the_command(self):
        aliases = set(ShopCog.fart_court.aliases)
        assert {"fartcourt", "court_fart", "courtfart"} <= aliases

    @pytest.mark.asyncio
    async def test_first_filing_takes_100_and_overturns_the_court(self, shop):
        _insert_score(7, 250)
        ctx = _ctx()
        await _court(shop, ctx, "@someone", "40")

        assert _score(7) == 150
        assert _filed(7) is True
        body = _sent(ctx)
        assert "⚖️" in body
        assert "overturns" in body
        assert "100 points" in body
        assert "Order of the Court" in body
        assert "🔨" not in body
        assert "WON" not in body
        assert "LOST" not in body

    @pytest.mark.asyncio
    async def test_exact_fee_empties_the_score(self, shop):
        _insert_score(7, 100)
        await _court(shop, _ctx())
        assert _score(7) == 0
        assert _filed(7) is True

    @pytest.mark.asyncio
    async def test_later_filing_is_overruled_and_free(self, shop):
        _insert_score(7, 250)
        await _court(shop, _ctx())
        ctx = _ctx()
        await _court(shop, ctx)

        assert _score(7) == 150
        assert _filed(7) is True
        body = _sent(ctx)
        assert "overruled" in body
        assert "banned" in body
        assert "Appeals are closed" in body
        assert "🔨" not in body
        assert "100 points" not in body

    @pytest.mark.asyncio
    async def test_short_fee_does_not_file_or_charge(self, shop):
        _insert_score(7, 99)
        ctx = _ctx()
        await _court(shop, ctx)

        assert _score(7) == 99
        assert _filed(7) is False
        body = _sent(ctx)
        assert "100 point" in body
        assert "You have 99" in body
        assert "Come back when you can pay the court" in body
        assert "🔨" not in body

    @pytest.mark.asyncio
    async def test_short_player_can_file_once_they_can_pay(self, shop):
        _insert_score(7, 40)
        await _court(shop, _ctx())
        assert _filed(7) is False

        conn = sqlite3.connect("fart_scores.db")
        conn.execute("UPDATE fart_scores SET score = 180 WHERE user_id = 7")
        conn.commit()
        conn.close()

        ctx = _ctx()
        await _court(shop, ctx)
        assert _score(7) == 80
        assert _filed(7) is True
        assert "overturns" in _sent(ctx)

    @pytest.mark.asyncio
    async def test_another_player_still_owes_their_own_fee(self, shop):
        _insert_score(7, 200)
        _insert_score(8, 200)
        await _court(shop, _ctx(7))
        await _court(shop, _ctx(8))
        assert _score(7) == 100
        assert _score(8) == 100
        assert _filed(7) is True
        assert _filed(8) is True

    @pytest.mark.asyncio
    async def test_wrong_channel_does_not_charge(self, shop):
        _insert_score(7, 250)
        ctx = _ctx(channel_id=99)
        await _court(shop, ctx)
        assert _score(7) == 250
        assert _filed(7) is False
        assert "<#1>" in _sent(ctx)

    @pytest.mark.asyncio
    async def test_yourt_does_not_waive_the_fee(self, shop):
        _insert_score(7, 250)
        with patch.object(shop, "yourt_waives_shop_limits", return_value=True):
            await _court(shop, _ctx())
        assert _score(7) == 150
        assert _filed(7) is True

    @pytest.mark.asyncio
    async def test_player_with_no_score_row_is_turned_away(self, shop):
        conn = sqlite3.connect("fart_scores.db")
        _scores_table(conn)
        conn.close()

        ctx = _ctx()
        await _court(shop, ctx)
        assert _score(7) is None
        assert _filed(7) is False
        assert "You have 0" in _sent(ctx)
        assert "dropped the file" not in _sent(ctx)

    @pytest.mark.asyncio
    async def test_shop_card_names_the_order_and_keeps_the_fee_during_yourt(self, shop):
        ctx = _ctx()
        await ShopCog.fart_shop.callback(shop, ctx)
        field = _court_field(ctx)
        assert field.name.startswith("Fart Court (!fart_court / !fartcourt)")
        assert "100 points" in field.name
        assert "Supreme Court overturned it" in field.value
        assert "unfun" in field.value
        assert "@user" not in field.name

        yourt = _ctx()
        with patch.object(shop, "yourt_waives_shop_limits", return_value=True):
            await ShopCog.fart_shop.callback(shop, yourt)
        yourt_field = _court_field(yourt)
        assert "100 points" in yourt_field.name
        assert "FREE" not in yourt_field.name


def _court_field(ctx):
    embed = ctx.send.await_args.kwargs["embed"]
    return next(field for field in embed.fields if field.name.startswith("Fart Court"))
