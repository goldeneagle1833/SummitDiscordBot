"""Admin pairing bans: !ban modal flow, !unban, and enforcement at every pairing entry point."""

import datetime
import sqlite3
import sys
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import discord
import pytest

sys.modules.setdefault("config", MagicMock(GUILD_ID=1, BOT_ADMIN_ROLE_ID=1001, JUDGE_ROLE_ID=1002))

from cogs.lfg.challenge import ChallengeButtons
from cogs.lfg.cog import LFGCog
from cogs.lfg.queue import JoinQueueButtons, _process_queue_join
from cogs.lfg.state import lfg_queue, matching_web_users
from cogs.pairing_bans import (
    BanInitView,
    PairingBanCog,
    PairingBanModal,
    member_is_admin,
)
from repositories.pairing_bans_repo import (
    BAN_DURATIONS,
    format_time_remaining,
    get_active_pairing_bans,
    get_pairing_ban,
    is_pairing_banned,
    pairing_ban_message,
    remove_pairing_ban,
    set_pairing_ban,
)

ADMIN_ID = 111
TARGET_ID = 222


@pytest.fixture(autouse=True)
def clear_state():
    lfg_queue.clear()
    matching_web_users.clear()
    yield
    lfg_queue.clear()
    matching_web_users.clear()


def make_member(user_id, name="Player", admin=False, roles=(), bot=False):
    member = MagicMock()
    member.id = user_id
    member.global_name = name
    member.display_name = name
    member.mention = f"<@{user_id}>"
    member.bot = bot
    member.guild_permissions.administrator = admin
    member.roles = [MagicMock(id=r) for r in roles]
    member.send = AsyncMock()
    return member


@pytest.fixture
def admin():
    return make_member(ADMIN_ID, "Admin", admin=True)


@pytest.fixture
def target():
    return make_member(TARGET_ID, "Target")


@pytest.fixture
def ban_bot():
    bot = MagicMock()
    lfg_cog = MagicMock()
    lfg_cog.update_lfg_status = AsyncMock()
    ban_cog_holder = {}

    def get_cog(name):
        if name == "LFGCog":
            return lfg_cog
        return ban_cog_holder.get(name)

    bot.get_cog = MagicMock(side_effect=get_cog)
    bot._lfg_cog = lfg_cog
    bot._holder = ban_cog_holder
    return bot


@pytest.fixture
def ban_cog(ban_bot):
    cog = PairingBanCog(ban_bot)
    ban_bot._holder["PairingBanCog"] = cog
    return cog


# ── Repository ──────────────────────────────────────────────────────


class TestPairingBansRepo:
    def test_set_and_get_timed_ban(self):
        ban = set_pairing_ban(TARGET_ID, ADMIN_ID, "Griefing", "24h", user_name="T", banned_by_name="A")
        assert ban["duration_label"] == "24 hours"
        delta = ban["expires_at"] - ban["banned_at"]
        assert delta == datetime.timedelta(hours=24)

        stored = get_pairing_ban(TARGET_ID)
        assert stored is not None
        assert stored["user_id"] == TARGET_ID
        assert stored["banned_by_id"] == ADMIN_ID
        assert stored["reason"] == "Griefing"
        assert stored["expires_at"] == ban["expires_at"]
        assert is_pairing_banned(TARGET_ID) is True
        assert is_pairing_banned(999) is False

    @pytest.mark.parametrize("key,hours", [("24h", 24), ("48h", 48), ("72h", 72)])
    def test_each_duration_option(self, key, hours):
        ban = set_pairing_ban(TARGET_ID, ADMIN_ID, "r", key)
        assert ban["expires_at"] - ban["banned_at"] == datetime.timedelta(hours=hours)
        assert BAN_DURATIONS[key][0] == ban["duration_label"]

    def test_lifetime_ban_has_no_expiry(self):
        ban = set_pairing_ban(TARGET_ID, ADMIN_ID, "Forever", "lifetime")
        assert ban["expires_at"] is None
        assert get_pairing_ban(TARGET_ID)["expires_at"] is None
        assert format_time_remaining(ban) == "permanent"
        assert "does not expire" in pairing_ban_message(ban)

    def test_unknown_duration_rejected(self):
        with pytest.raises(ValueError):
            set_pairing_ban(TARGET_ID, ADMIN_ID, "r", "1h")

    def test_reban_replaces_existing(self):
        set_pairing_ban(TARGET_ID, ADMIN_ID, "first", "24h")
        set_pairing_ban(TARGET_ID, ADMIN_ID, "second", "lifetime")
        ban = get_pairing_ban(TARGET_ID)
        assert ban["reason"] == "second"
        assert ban["expires_at"] is None
        assert len(get_active_pairing_bans()) == 1

    def test_expired_ban_is_cleared(self):
        set_pairing_ban(TARGET_ID, ADMIN_ID, "old", "24h")
        past = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=1)).isoformat()
        conn = sqlite3.connect("match_records.db")
        conn.execute("UPDATE pairing_bans SET expires_at = ? WHERE user_id = ?", (past, str(TARGET_ID)))
        conn.commit()
        conn.close()

        assert get_pairing_ban(TARGET_ID) is None
        assert is_pairing_banned(TARGET_ID) is False
        conn = sqlite3.connect("match_records.db")
        assert conn.execute("SELECT COUNT(*) FROM pairing_bans").fetchone()[0] == 0
        conn.close()

    def test_remove_ban(self):
        set_pairing_ban(TARGET_ID, ADMIN_ID, "r", "48h")
        removed = remove_pairing_ban(TARGET_ID)
        assert removed["reason"] == "r"
        assert get_pairing_ban(TARGET_ID) is None
        assert remove_pairing_ban(TARGET_ID) is None

    def test_active_bans_order_timed_before_lifetime(self):
        set_pairing_ban(1, ADMIN_ID, "a", "lifetime")
        set_pairing_ban(2, ADMIN_ID, "b", "72h")
        set_pairing_ban(3, ADMIN_ID, "c", "24h")
        assert [b["user_id"] for b in get_active_pairing_bans()] == [3, 2, 1]

    def test_time_remaining_and_message(self):
        ban = set_pairing_ban(TARGET_ID, ADMIN_ID, "Be nice", "48h")
        remaining = format_time_remaining(ban)
        assert remaining.startswith("1 day, 23 hours") or remaining.startswith("2 days")
        msg = pairing_ban_message(ban)
        assert "blocked from the Summit pairing service" in msg
        assert "Be nice" in msg
        assert "Time remaining" in msg
        assert f"<t:{int(ban['expires_at'].timestamp())}:R>" in msg


# ── Admin check ─────────────────────────────────────────────────────


class TestMemberIsAdmin:
    def test_server_admin(self):
        assert member_is_admin(make_member(1, admin=True))

    def test_bot_admin_role(self):
        import config

        with patch.object(config, "BOT_ADMIN_ROLE_ID", 1001, create=True), patch.object(
            config, "JUDGE_ROLE_ID", 1002, create=True
        ):
            assert member_is_admin(make_member(1, roles=[1001]))
            assert member_is_admin(make_member(1, roles=[1002]))
            assert not member_is_admin(make_member(1, roles=[5]))

    def test_none(self):
        assert not member_is_admin(None)


# ── !ban flow ───────────────────────────────────────────────────────


class TestBanCommand:
    @pytest.mark.asyncio
    async def test_ban_posts_button_view(self, ban_cog, admin, target):
        ctx = MagicMock()
        ctx.author = admin
        ctx.send = AsyncMock()

        await ban_cog.ban.callback(ban_cog, ctx, target)

        ctx.send.assert_awaited_once()
        view = ctx.send.await_args.kwargs["view"]
        assert isinstance(view, BanInitView)
        assert isinstance(view.modal, PairingBanModal)
        assert view.modal.target is target
        assert "Click below" in ctx.send.await_args.args[0]

    @pytest.mark.asyncio
    async def test_ban_warns_about_existing_ban(self, ban_cog, admin, target):
        set_pairing_ban(TARGET_ID, ADMIN_ID, "earlier", "72h")
        ctx = MagicMock(author=admin, send=AsyncMock())

        await ban_cog.ban.callback(ban_cog, ctx, target)

        assert "already has a **72 hours** ban" in ctx.send.await_args.args[0]

    @pytest.mark.asyncio
    async def test_ban_rejects_bad_targets(self, ban_cog, admin):
        ctx = MagicMock(author=admin, send=AsyncMock())

        await ban_cog.ban.callback(ban_cog, ctx, None)
        assert "mention a user" in ctx.send.await_args.args[0]

        await ban_cog.ban.callback(ban_cog, ctx, admin)
        assert "yourself" in ctx.send.await_args.args[0]

        await ban_cog.ban.callback(ban_cog, ctx, make_member(5, bot=True))
        assert "bot" in ctx.send.await_args.args[0]

        await ban_cog.ban.callback(ban_cog, ctx, make_member(6, admin=True))
        assert "another admin" in ctx.send.await_args.args[0]
        assert ctx.send.await_args.kwargs.get("view") is None

    @pytest.mark.asyncio
    async def test_ban_requires_admin(self, ban_cog):
        import config
        from discord.ext import commands

        ctx = MagicMock()
        ctx.author = make_member(5, roles=[7])
        predicate = ban_cog.ban.checks[0]

        with patch.object(config, "BOT_ADMIN_ROLE_ID", 1001, create=True), patch.object(
            config, "JUDGE_ROLE_ID", 1002, create=True
        ):
            with pytest.raises(commands.MissingPermissions):
                await predicate(ctx)
            ctx.author = make_member(6, roles=[1002])
            assert await predicate(ctx) is True

    def test_modal_layout(self, ban_cog, admin, target):
        modal = ban_cog.build_ban_modal(target, admin)
        assert modal.title == "Block from Pairing Service"
        labels = [type(c).__name__ for c in modal.children]
        assert labels == ["Label", "TextInput"]
        assert modal.children[0].text == "Time out"
        assert [o.value for o in modal.duration_select.options] == ["24h", "48h", "72h", "lifetime"]
        assert [o.label for o in modal.duration_select.options] == ["24 hours", "48 hours", "72 hours", "Lifetime"]
        assert modal.reason.label == "Reasoning"
        assert modal.reason.required is True

    @pytest.mark.asyncio
    async def test_open_form_button_sends_modal_only_to_admin(self, ban_cog, admin, target):
        modal = ban_cog.build_ban_modal(target, admin)
        view = BanInitView(modal)

        stranger = MagicMock(user=make_member(9))
        stranger.response.send_message = AsyncMock()
        assert await view.interaction_check(stranger) is False
        stranger.response.send_message.assert_awaited_once()
        assert stranger.response.send_message.await_args.kwargs["ephemeral"] is True

        interaction = MagicMock(user=admin)
        interaction.response.send_modal = AsyncMock()
        interaction.message.delete = AsyncMock()
        assert await view.interaction_check(interaction) is True
        await view.open_form_button.callback(interaction)
        interaction.response.send_modal.assert_awaited_once_with(modal)

    @pytest.mark.asyncio
    async def test_modal_submit_bans_dms_and_removes_from_queue(self, ban_bot, ban_cog, admin, target):
        lfg_queue[TARGET_ID] = {"queues": {"ranked": {"timestamp": datetime.datetime.now(), "timeframe": 30}}}
        matching_web_users[TARGET_ID] = "ranked"

        modal = ban_cog.build_ban_modal(target, admin)
        modal.duration_select._values = ["48h"]
        modal.reason._value = "  Repeated no-shows  "
        interaction = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()

        with patch("cogs.pairing_bans.log_admin_action") as log:
            await modal.on_submit(interaction)

        ban = get_pairing_ban(TARGET_ID)
        assert ban["reason"] == "Repeated no-shows"
        assert ban["duration_label"] == "48 hours"
        assert ban["banned_by_id"] == ADMIN_ID
        assert TARGET_ID not in lfg_queue
        assert TARGET_ID not in matching_web_users
        ban_bot._lfg_cog.update_lfg_status.assert_awaited_once()

        # DM to the player carries the time out and the reasoning
        target.send.assert_awaited_once()
        dm_embed = target.send.await_args.kwargs["embed"]
        assert "blocked from the Summit pairing service" in dm_embed.title
        fields = {f.name: f.value for f in dm_embed.fields}
        assert fields["Time out"] == "48 hours"
        assert fields["Reasoning"] == "Repeated no-shows"
        assert "<t:" in fields["Lifts"]

        # Audit log + ephemeral confirmation to the admin
        log.assert_called_once()
        assert log.call_args.args[2] == "pairing_ban"
        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        interaction.followup.send.assert_awaited_once()
        assert interaction.followup.send.await_args.kwargs["ephemeral"] is True
        admin_embed = interaction.followup.send.await_args.kwargs["embed"]
        assert admin_embed.title == "Pairing ban applied"
        assert "Player was DMed" in {f.name: f.value for f in admin_embed.fields}["Notes"]

    @pytest.mark.asyncio
    async def test_modal_submit_lifetime_and_closed_dms(self, ban_cog, admin, target):
        target.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403), "closed"))
        modal = ban_cog.build_ban_modal(target, admin)
        modal.duration_select._values = ["lifetime"]
        modal.reason._value = "Cheating"
        interaction = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()

        with patch("cogs.pairing_bans.log_admin_action"):
            await modal.on_submit(interaction)

        ban = get_pairing_ban(TARGET_ID)
        assert ban["expires_at"] is None
        admin_embed = interaction.followup.send.await_args.kwargs["embed"]
        fields = {f.name: f.value for f in admin_embed.fields}
        assert fields["Lifts"] == "Never (lifetime)"
        assert "Could not DM" in fields["Notes"]

    @pytest.mark.asyncio
    async def test_modal_submit_without_duration(self, ban_cog, admin, target):
        modal = ban_cog.build_ban_modal(target, admin)
        modal.reason._value = "x"
        interaction = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()

        await modal.on_submit(interaction)

        assert get_pairing_ban(TARGET_ID) is None
        assert "pick a time out" in interaction.followup.send.await_args.args[0]


# ── !unban / !bans ──────────────────────────────────────────────────


class TestUnbanCommand:
    @pytest.mark.asyncio
    async def test_unban_lifts_ban_and_dms(self, ban_cog, admin, target):
        set_pairing_ban(TARGET_ID, ADMIN_ID, "r", "24h")
        ctx = MagicMock(author=admin, send=AsyncMock())

        with patch("cogs.pairing_bans.log_admin_action") as log:
            await ban_cog.unban.callback(ban_cog, ctx, target)

        assert get_pairing_ban(TARGET_ID) is None
        target.send.assert_awaited_once()
        assert "lifted" in target.send.await_args.kwargs["embed"].title
        assert log.call_args.args[2] == "pairing_unban"
        embed = ctx.send.await_args.kwargs["embed"]
        assert embed.title == "Pairing ban lifted"

    @pytest.mark.asyncio
    async def test_unban_without_ban(self, ban_cog, admin, target):
        ctx = MagicMock(author=admin, send=AsyncMock())

        with patch("cogs.pairing_bans.log_admin_action") as log:
            await ban_cog.unban.callback(ban_cog, ctx, target)

        log.assert_not_called()
        target.send.assert_not_awaited()
        assert ctx.send.await_args.kwargs["embed"].title == "No active pairing ban"

    @pytest.mark.asyncio
    async def test_bans_list(self, ban_cog, admin):
        ctx = MagicMock(author=admin, send=AsyncMock())
        await ban_cog.bans.callback(ban_cog, ctx)
        assert "Nobody" in ctx.send.await_args.kwargs["embed"].description

        set_pairing_ban(TARGET_ID, ADMIN_ID, "Salt", "lifetime", user_name="Target")
        await ban_cog.bans.callback(ban_cog, ctx)
        desc = ctx.send.await_args.kwargs["embed"].description
        assert f"<@{TARGET_ID}>" in desc and "Lifetime" in desc and "Salt" in desc


# ── Enforcement ─────────────────────────────────────────────────────


class TestEnforcement:
    @pytest.mark.asyncio
    async def test_join_button_shows_ephemeral_ban_notice(self, mock_bot, mock_interaction):
        set_pairing_ban(mock_interaction.user.id, ADMIN_ID, "Toxic chat", "24h")
        view = JoinQueueButtons(mock_bot)

        with patch("cogs.lfg.queue.queue_is_enabled", return_value=True):
            await view._handle_join(mock_interaction, "ranked")

        mock_interaction.response.send_modal.assert_not_awaited()
        mock_interaction.response.send_message.assert_awaited_once()
        text = mock_interaction.response.send_message.await_args.args[0]
        assert mock_interaction.response.send_message.await_args.kwargs["ephemeral"] is True
        assert "Toxic chat" in text and "Time remaining" in text

    @pytest.mark.asyncio
    async def test_join_button_unaffected_without_ban(self, mock_bot, mock_interaction):
        view = JoinQueueButtons(mock_bot)
        with patch("cogs.lfg.queue.queue_is_enabled", return_value=True):
            await view._handle_join(mock_interaction, "ranked")
        mock_interaction.response.send_modal.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_process_queue_join_blocked(self, mock_bot, mock_interaction):
        set_pairing_ban(mock_interaction.user.id, ADMIN_ID, "r", "72h")
        lfg_cog = MagicMock()
        lfg_cog.add_to_lfg_queue = MagicMock()
        mock_bot.get_cog.return_value = lfg_cog

        await _process_queue_join(mock_bot, mock_interaction, "testing", 30, None)

        lfg_cog.add_to_lfg_queue.assert_not_called()
        assert mock_interaction.user.id not in lfg_queue
        mock_interaction.followup.send.assert_awaited_once()
        assert mock_interaction.followup.send.await_args.kwargs["ephemeral"] is True
        assert "blocked from the Summit pairing service" in mock_interaction.followup.send.await_args.args[0]

    def test_matching_skips_banned_queued_player(self):
        set_pairing_ban(555, ADMIN_ID, "r", "24h")
        now = datetime.datetime.now()
        lfg_queue[555] = {"queues": {"ranked": {"timestamp": now - datetime.timedelta(minutes=5), "timeframe": 30, "voice": "any"}}}
        lfg_queue[556] = {"queues": {"ranked": {"timestamp": now, "timeframe": 30, "voice": "any"}}}
        cog = object.__new__(LFGCog)
        cog.bot = Mock()
        cog.check_last_match_opponent = MagicMock(return_value=False)
        ctx = Mock()
        ctx.author.id = 999

        assert cog.check_if_someone_is_lfg(ctx, "ranked") == 556

    @pytest.mark.asyncio
    async def test_challenge_command_blocked_for_banned_challenger(self):
        set_pairing_ban(ADMIN_ID, 1, "No", "24h")
        cog = object.__new__(LFGCog)
        cog.bot = Mock()
        ctx = MagicMock()
        ctx.author = make_member(ADMIN_ID)
        ctx.send = AsyncMock()

        await cog.challenge.callback(cog, ctx, make_member(TARGET_ID))

        ctx.send.assert_awaited_once()
        assert "blocked from the Summit pairing service" in ctx.send.await_args.args[0]
        assert ctx.send.await_args.kwargs.get("view") is None

    @pytest.mark.asyncio
    async def test_challenge_command_blocked_for_banned_opponent(self):
        set_pairing_ban(TARGET_ID, 1, "No", "24h")
        cog = object.__new__(LFGCog)
        cog.bot = Mock()
        ctx = MagicMock()
        ctx.author = make_member(ADMIN_ID)
        ctx.send = AsyncMock()

        await cog.challenge.callback(cog, ctx, make_member(TARGET_ID))

        assert "can't be challenged" in ctx.send.await_args.args[0]

    @pytest.mark.asyncio
    async def test_accept_challenge_blocked_for_banned_accepter(self):
        set_pairing_ban(TARGET_ID, 1, "No", "lifetime")
        view = ChallengeButtons(challenger_id=ADMIN_ID, challenger_global="Admin")
        interaction = MagicMock()
        interaction.user = make_member(TARGET_ID)
        interaction.response.send_message = AsyncMock()
        interaction.response.send_modal = AsyncMock()

        await view.accept_button.callback(interaction)

        interaction.response.send_modal.assert_not_awaited()
        assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_issue_challenge_blocked(self):
        set_pairing_ban(TARGET_ID, 1, "No", "24h")
        cog = object.__new__(LFGCog)
        cog.bot = Mock()
        ctx = MagicMock()
        ctx.guild = None
        ctx.author = make_member(TARGET_ID)
        ctx.send = AsyncMock()

        with patch("utils.database.get_active_event") as get_active_event:
            await cog.issue_challenge.callback(cog, ctx)
            get_active_event.assert_not_called()

        ctx.author.send.assert_awaited_once()
        assert "blocked from the Summit pairing service" in ctx.author.send.await_args.args[0]
