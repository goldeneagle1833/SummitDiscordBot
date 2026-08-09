import discord
import random
import datetime
import logging
import sqlite3

import config
from cogs.lfg.state import lfg_queue, lfg_queue_lock
from cogs.lfg.helpers import scrub_urls
from cogs.lfg.match_reporting import MatchCardView
from utils.constants import SORCERY_NICKNAMES
from utils.database import get_active_event, save_pairing
from utils.avatar_elo import avatar_input_error, canonicalize_avatar_name
from repositories.limited_repo import save_limited_pairing, get_active_arena_run
from services.pilots_service import is_pilot_active
from services.card_points_service import validate_deck_points

logger = logging.getLogger("discord_bot")

LIMITED_RUN_REQUIRED_MESSAGE = (
    "You need an active Limited run to join the queue. "
    "Start a new run by drafting at https://draftsorcery.com/."
)


def parse_queue_timeframe(raw_value):
    """Parse and clamp queue timeframe values."""

    try:
        timeframe_value = int(raw_value) if raw_value else 30
        if timeframe_value < 5:
            timeframe_value = 5
        elif timeframe_value > 120:
            timeframe_value = 120
    except ValueError:
        timeframe_value = 30

    return timeframe_value


def get_last_unreported_pairing(user_id: int, guild_id: int):
    """Get the most recent unreported pairing for a user.

    Returns:
        dict with keys: pairing_id, player1_id, player2_id, player1_deck_url, player2_deck_url, match_type
        or None if no unreported pairing found
    """
    conn = sqlite3.connect("match_records.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Check regular pairings first
    cursor.execute(
        """
        SELECT * FROM active_pairings
        WHERE guild_id = ?
          AND (player1_id = ? OR player2_id = ?)
          AND status = 'active'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (guild_id, user_id, user_id)
    )

    row = cursor.fetchone()
    conn.close()

    if row:
        return dict(row)

    # Check limited pairings if no regular pairing found
    conn = sqlite3.connect("match_records.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM limited_active_pairings
        WHERE guild_id = ?
          AND (player1_id = ? OR player2_id = ?)
          AND status = 'active'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (guild_id, user_id, user_id)
    )

    row = cursor.fetchone()
    conn.close()

    if row:
        pairing_dict = dict(row)
        pairing_dict['match_type'] = 'limited'
        return pairing_dict

    return None


class DeckURLModal(discord.ui.Modal, title="Join LFG Queue"):
    """Modal for entering a deck URL when joining the LFG queue"""

    deck_url = discord.ui.TextInput(
        label="Curiosa Deck URL",
        placeholder="https://curiosa.io/decks/... (optional)",
        required=False,
        max_length=200,
    )

    timeframe = discord.ui.TextInput(
        label="Queue Duration (minutes)",
        placeholder="30",
        required=False,
        default="30",
        max_length=3,
    )

    avatar = discord.ui.TextInput(
        label="Avatar for this match",
        placeholder="Enter the exact Avatar card name",
        required=True,
        max_length=100,
    )

    def __init__(self, bot, is_button_join=True, queue_type="ranked"):
        super().__init__()
        self.bot = bot
        self.is_button_join = (
            is_button_join  # True if from button, False if from !lfg command
        )
        self.queue_type = queue_type
        active_event = get_active_event()
        self.avatar_specific = bool(
            queue_type == "ranked"
            and active_event
            and active_event.get("avatar_specific")
        )
        if not self.avatar_specific:
            self.remove_item(self.avatar)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        timeframe_value = parse_queue_timeframe(self.timeframe.value)

        deck_url = self.deck_url.value.strip() if self.deck_url.value else None
        selected_avatar = None
        if self.avatar_specific:
            selected_avatar = canonicalize_avatar_name(self.avatar.value)
            if not selected_avatar:
                await interaction.followup.send(
                    avatar_input_error("your avatar", self.avatar.value),
                    ephemeral=True,
                )
                return

        # For limited queue, player must have an active arena run (created via Draft Sorcery)
        run_id = None
        if self.queue_type == "limited":
            active_run = get_active_arena_run(interaction.user.id)
            if active_run and active_run["status"] == "active" and active_run["wins"] < 4 and active_run["losses"] < 2:
                run_id = active_run["run_id"]
                deck_url = active_run["deck_url"]
            else:
                await interaction.followup.send(
                    LIMITED_RUN_REQUIRED_MESSAGE,
                    ephemeral=True,
                )
                return

        await _process_queue_join(
            self.bot,
            interaction,
            self.queue_type,
            timeframe_value,
            deck_url,
            run_id,
            selected_avatar,
        )


class LimitedQueueModal(discord.ui.Modal, title="Join Limited Queue"):
    """Modal for joining the Limited queue with only a duration."""

    timeframe = discord.ui.TextInput(
        label="Queue Duration (minutes)",
        placeholder="30",
        required=False,
        default="30",
        max_length=3,
    )

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        timeframe_value = parse_queue_timeframe(self.timeframe.value)

        active_run = get_active_arena_run(interaction.user.id)
        if not (
            active_run
            and active_run["status"] == "active"
            and active_run["wins"] < 4
            and active_run["losses"] < 2
        ):
            await interaction.followup.send(
                LIMITED_RUN_REQUIRED_MESSAGE,
                ephemeral=True,
            )
            return

        queue_type = "limited"
        run_id = int(active_run["run_id"])
        deck_url = active_run["deck_url"]

        await _process_queue_join(
            self.bot,
            interaction,
            queue_type,
            timeframe_value,
            deck_url,
            run_id,
        )


class PointsQueueModal(discord.ui.Modal, title="Join Omens Queue"):
    """Modal for joining the Omens queue — requires a Curiosa deck URL."""

    deck_url = discord.ui.TextInput(
        label="Curiosa Deck URL (required)",
        placeholder="https://curiosa.io/decks/...",
        required=True,
        max_length=200,
    )

    timeframe = discord.ui.TextInput(
        label="Queue Duration (minutes)",
        placeholder="30",
        required=False,
        default="30",
        max_length=3,
    )

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        deck_url = self.deck_url.value.strip()
        if not deck_url or "curiosa.io" not in deck_url.lower():
            await interaction.followup.send(
                "Please provide a valid Curiosa deck URL (e.g. https://curiosa.io/decks/...).",
                ephemeral=True,
            )
            return

        timeframe_value = parse_queue_timeframe(self.timeframe.value)

        # Validate deck against point budget
        is_valid, message, total_points, max_budget = await validate_deck_points(deck_url)
        if not is_valid:
            await interaction.followup.send(
                f"**Deck not allowed in Omens queue.**\n{message}",
                ephemeral=True,
            )
            return

        await _process_queue_join(
            self.bot,
            interaction,
            "points",
            timeframe_value,
            deck_url,
        )


async def _process_queue_join(
    bot,
    interaction,
    queue_type,
    timeframe_value,
    deck_url,
    run_id=None,
    selected_avatar=None,
):
    """Handle queue join flow after modal validation."""

    class FakeContext:
        def __init__(self, bot, interaction):
            self.bot = bot
            self.author = interaction.user
            self.guild = interaction.guild
            self.channel = interaction.channel
            self.message = None

        async def send(self, *args, **kwargs):
            pass

    ctx = FakeContext(bot, interaction)
    lfg_cog = bot.get_cog("LFGCog")

    if not lfg_cog:
        await interaction.followup.send(
            "LFG system is not available.", ephemeral=True
        )
        return

    async with lfg_queue_lock:
        # Check if already in this specific queue type
        user_queues = lfg_queue.get(interaction.user.id, {}).get("queues", {})
        if queue_type in user_queues:
            await interaction.followup.send(
                f"You're already in the {queue_type.capitalize()} queue!", ephemeral=True
            )
            return

        lfg_cog.clean_expired_lfg()
        matched_user_id = lfg_cog.check_if_someone_is_lfg(ctx, queue_type)

        if matched_user_id and matched_user_id != interaction.user.id:
            matched_entry = lfg_queue.get(matched_user_id, {}).get("queues", {}).get(queue_type, {})
            matched_user_deck_url = matched_entry.get("deck_url")
            matched_user_avatar = matched_entry.get("avatar")
            matched_queue_type = queue_type
            matched_ladder_info = matched_entry.get("ladder_info")
            matched_run_id = int(matched_entry.get("run_id") or 0)
            match_type = lfg_cog.resolve_match_type(queue_type, matched_queue_type)

            if matched_ladder_info:
                from utils.database import (
                    delete_ladder_challenge,
                    get_active_event,
                    get_user_event_elo,
                    save_ladder_challenge,
                )

                if not matched_ladder_info.get("challenge_id"):
                    challenge_id = save_ladder_challenge(matched_ladder_info["challenger_id"])
                    matched_ladder_info["challenge_id"] = challenge_id
                    logger.info(
                        f"Ladder challenge saved on match for challenger {matched_ladder_info['challenger_id']}, challenge_id: {challenge_id}"
                    )

                try:
                    active_event = get_active_event()
                    if active_event and active_event.get("avatar_specific"):
                        matched_ladder_info["avatar_stakes_pending"] = True
                        logger.info(
                            "Queued ladder challenge: avatar stakes deferred until report confirmation"
                        )
                    else:
                        challenger_elo = get_user_event_elo(
                            matched_ladder_info["challenger_id"]
                        )
                        opponent_elo = get_user_event_elo(interaction.user.id)
                        elo_diff = abs(challenger_elo - opponent_elo)

                        if elo_diff < 100:
                            matched_ladder_info["elo_multiplier_winner"] = 1.0
                            matched_ladder_info["elo_multiplier_loser"] = 1.0
                            logger.info(
                                f"Ladder challenge match: ELO diff {elo_diff} < 100 - using normal stakes"
                            )
                        else:
                            logger.info(
                                f"Ladder challenge match: ELO diff {elo_diff} >= 100 - using special stakes (2x/0.5x)"
                            )
                except Exception as e:
                    # Rollback: delete the challenge so daily usage is not consumed
                    logger.error(
                        f"Error processing ladder ELO for challenge {matched_ladder_info.get('challenge_id')}: {e}",
                        exc_info=True,
                    )
                    if matched_ladder_info.get("challenge_id"):
                        delete_ladder_challenge(matched_ladder_info["challenge_id"])
                    matched_ladder_info = None

            lfg_queue.pop(matched_user_id, None)
            # Also remove the joiner from any other queues they may be in
            lfg_queue.pop(interaction.user.id, None)
            logger.info(
                f"Lock acquired: Matching {interaction.user.id} with {matched_user_id} (match_type={match_type})"
            )
        else:
            matched_user_id = None
            matched_user_deck_url = None
            matched_user_avatar = None
            matched_ladder_info = None
            matched_run_id = None
            match_type = None
            lfg_cog.add_to_lfg_queue(
                ctx,
                timeframe_value,
                deck_url,
                queue_type,
                run_id=run_id,
                avatar=selected_avatar,
            )

    # Notify limited ping channel when someone is waiting (no match found)
    if not matched_user_id and queue_type == "limited":
        try:
            limited_channel = bot.get_channel(config.LIMITED_PING_CHANNEL_ID)
            if not limited_channel:
                limited_channel = await bot.fetch_channel(config.LIMITED_PING_CHANNEL_ID)
            if limited_channel:
                await limited_channel.send(
                    f"<@&{config.LIMITED_PING_ROLE_ID}> There is a brave soul looking for a Limited game! "
                    f"Join the queue!"
                )
            else:
                logger.error(f"Limited ping channel {config.LIMITED_PING_CHANNEL_ID} not found")
        except Exception as e:
            logger.error(f"Failed to send limited queue notification: {e}")

    if matched_user_id:
        if match_type == "limited":
            match_type_emoji = "🎲"
            match_type_label = "Limited"
        elif match_type == "ranked":
            match_type_emoji = "⚔️"
            match_type_label = "Ranked"
        elif match_type == "rumble":
            match_type_emoji = "💥"
            match_type_label = "Rumble"
        elif match_type == "points":
            match_type_emoji = "📊"
            match_type_label = "Omens"
        else:
            match_type_emoji = "⭐"
            match_type_label = "Casual"

        try:
            matched_user = await bot.fetch_user(matched_user_id)
        except Exception as e:
            logger.error(f"Failed to fetch matched user {matched_user_id}: {e}")
            # Rollback ladder challenge so daily usage is not consumed
            if matched_ladder_info and matched_ladder_info.get("challenge_id"):
                delete_ladder_challenge(matched_ladder_info["challenge_id"])
            await interaction.followup.send(
                "Error: Could not find matched player. Please try again.",
                ephemeral=True,
            )
            return

        lfg_channel = bot.get_channel(lfg_cog.lfg_channel_id)
        joiner_global = interaction.user.global_name or interaction.user.display_name
        matched_global = matched_user.global_name or matched_user.display_name
        match_start_time = datetime.datetime.now()

        if not interaction.guild or not interaction.guild.id:
            logger.error(
                f"Cannot save pairing: guild_id is None for users {interaction.user.id} and {matched_user_id}"
            )
            # Rollback ladder challenge so daily usage is not consumed
            if matched_ladder_info and matched_ladder_info.get("challenge_id"):
                delete_ladder_challenge(matched_ladder_info["challenge_id"])
            await interaction.followup.send(
                "Error: Could not save match pairing. Please try using !lfg command instead.",
                ephemeral=True,
            )
            return

        try:
            event_snapshot = get_active_event()
            avatar_locked = bool(
                match_type == "ranked"
                and event_snapshot
                and event_snapshot.get("avatar_specific")
            )
            if avatar_locked and (not selected_avatar or not matched_user_avatar):
                raise ValueError(
                    "Both players must lock an avatar before an avatar-specific ranked match."
                )
            if match_type == "limited":
                pairing_id = save_limited_pairing(
                    guild_id=interaction.guild.id,
                    player1_id=interaction.user.id,
                    player2_id=matched_user_id,
                    player1_deck_url=deck_url or "",
                    player2_deck_url=matched_user_deck_url or "",
                    player1_run_id=run_id or 0,
                    player2_run_id=matched_run_id or 0,
                )
            else:
                pairing_id = save_pairing(
                    guild_id=interaction.guild.id,
                    player1_id=interaction.user.id,
                    player2_id=matched_user_id,
                    player1_deck_url=deck_url or "",
                    player2_deck_url=matched_user_deck_url or "",
                    match_type=match_type or "ranked",
                    player1_avatar=selected_avatar,
                    player2_avatar=matched_user_avatar,
                    event_snapshot=event_snapshot,
                )
            logger.info(
                f"Saved {'limited ' if match_type == 'limited' else ''}pairing {pairing_id} in guild {interaction.guild.id}: "
                f"{interaction.user.id} ({joiner_global}) vs {matched_user_id} ({matched_global})"
            )
        except Exception as e:
            logger.error(
                f"Failed to save pairing for users {interaction.user.id} and {matched_user_id}: {e}",
                exc_info=True,
            )
            # Rollback ladder challenge so daily usage is not consumed
            if matched_ladder_info and matched_ladder_info.get("challenge_id"):
                delete_ladder_challenge(matched_ladder_info["challenge_id"])
            await interaction.followup.send(
                "Error: Could not save match pairing to database. Please contact an admin.",
                ephemeral=True,
            )
            return

        try:
            guild = bot.get_guild(config.GUILD_ID)
            if guild:
                active_role = guild.get_role(config.ACTIVE_PLAYER_ROLE_ID)
                if active_role:
                    for player_id in (interaction.user.id, matched_user_id):
                        member = guild.get_member(player_id)
                        if member and active_role not in member.roles:
                            await member.add_roles(active_role)
                            logger.info(f"Added active player role to {member.display_name} ({player_id})")
        except Exception as e:
            logger.error(f"Failed to assign active player role: {e}")

        players = [
            (
                interaction.user.id,
                joiner_global,
                interaction.user,
                deck_url,
                selected_avatar,
                True,
            ),
            (
                matched_user_id,
                matched_global,
                matched_user,
                matched_user_deck_url,
                matched_user_avatar,
                False,
            ),
        ]
        reporter_player, other_player = random.sample(players, 2)
        (
            reporter_id,
            reporter_global,
            reporter_user,
            reporter_deck_url,
            reporter_avatar,
            reporter_is_joiner,
        ) = reporter_player
        (
            other_id,
            other_global,
            other_user,
            other_deck_url,
            other_avatar,
            _,
        ) = other_player

        reporter_deck_text = f"\n**Your Deck:** {reporter_deck_url}" if reporter_deck_url else ""
        avatar_text = ""
        if reporter_avatar and other_avatar:
            avatar_text = (
                f"\n**Your Avatar:** {reporter_avatar}"
                f"\n**Opponent Avatar:** {other_avatar}"
            )

        if match_type == "limited":
            if reporter_is_joiner:
                reporter_run_id = int(run_id or 0)
                other_run_id = int(matched_run_id or 0)
            else:
                reporter_run_id = int(matched_run_id or 0)
                other_run_id = int(run_id or 0)
        else:
            reporter_run_id = int(0)
            other_run_id = int(0)

        match_card_view = MatchCardView(
            bot=bot,
            pairing_id=pairing_id,
            player1_id=reporter_id,
            player1_global=reporter_global,
            player2_id=other_id,
            player2_global=other_global,
            player1_deck_url=reporter_deck_url,
            player2_deck_url=other_deck_url,
            match_start_time=match_start_time,
            guild_id=interaction.guild.id,
            ladder_info=matched_ladder_info or {},
            match_type=match_type or "ranked",
            player1_run_id=reporter_run_id,
            player2_run_id=other_run_id,
            player1_avatar=reporter_avatar,
            player2_avatar=other_avatar,
            event_snapshot=event_snapshot,
        )

        reporter_dm_failed = False
        try:
            await reporter_user.send(
                f"{match_type_emoji} **{match_type_label} Match Found!** You've been matched with {other_user.mention} (**{other_global}**)!{reporter_deck_text}{avatar_text}\n\n"
                f"Use the button below to report the result when your match is done.\n\n"
                f"💡 **Tip:** If these buttons expire, click **'📋 Report Last Match'** in the LFG channel for fresh ones!",
                view=match_card_view,
            )
        except discord.Forbidden:
            reporter_dm_failed = True
            try:
                dm_channel = bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
                if dm_channel:
                    guild = bot.get_guild(config.GUILD_ID)
                    if guild:
                        member = guild.get_member(reporter_user.id)
                        if member:
                            await dm_channel.set_permissions(
                                member, read_messages=True, send_messages=True
                            )
                            role = guild.get_role(config.DM_DISABLED_ROLE_ID)
                            if role and role not in member.roles:
                                await member.add_roles(role)
                            logger.info(
                                f"Granted channel access to {reporter_user.global_name} (can't receive DMs)"
                            )

                    await dm_channel.send(
                        scrub_urls(
                            f"{reporter_user.mention} {match_type_emoji} **{match_type_label} Match Found!**\n\nYou've been matched with {other_user.mention} (**{other_global}**)!\n\n"
                            f"Use the button below to report the result when your match is done.\n\n"
                            f"💡 **Tip:** If these buttons expire, click **'📋 Report Last Match'** for fresh ones!"
                        ),
                        view=match_card_view,
                    )
            except Exception as e:
                logger.error(f"Failed to handle DM failure for reporter: {e}")

        other_own_deck_text = f"\n**Your Deck:** {other_deck_url}" if other_deck_url else ""
        other_avatar_text = ""
        if other_avatar and reporter_avatar:
            other_avatar_text = (
                f"\n**Your Avatar:** {other_avatar}"
                f"\n**Opponent Avatar:** {reporter_avatar}"
            )

        try:
            await other_user.send(
                f"🎮 **Match Found!** You've been matched with {reporter_user.mention} (**{reporter_global}**)!{other_own_deck_text}{other_avatar_text}\n\n"
                f"**{reporter_global}** has the match report buttons. When they report the result, you'll receive a confirmation to verify the outcome.\n\n"
                f"💡 **Tip:** If you need fresh reporting buttons, click **'📋 Report Last Match'** in the LFG channel!"
            )
        except discord.Forbidden:
            try:
                dm_channel = bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
                if dm_channel:
                    guild = bot.get_guild(config.GUILD_ID)
                    if guild:
                        member = guild.get_member(other_user.id)
                        if member:
                            await dm_channel.set_permissions(
                                member, read_messages=True, send_messages=True
                            )
                            role = guild.get_role(config.DM_DISABLED_ROLE_ID)
                            if role and role not in member.roles:
                                await member.add_roles(role)
                            logger.info(
                                f"Granted channel access to {other_user.global_name} (can't receive DMs)"
                            )

                    await dm_channel.send(
                        scrub_urls(
                            f"{other_user.mention} 🎮 **Match Found!**\n\nYou've been matched with {reporter_user.mention} (**{reporter_global}**)!\n\n"
                            f"**{reporter_global}** has the match report buttons. When they report the result, you'll receive a confirmation to verify the outcome.\n\n"
                            f"💡 **Tip:** If you need fresh reporting buttons, click **'📋 Report Last Match'**!"
                        )
                    )
            except Exception as e:
                logger.error(f"Failed to handle DM failure for other player: {e}")

        if lfg_channel:
            ladder_note = ""
            if matched_ladder_info and matched_ladder_info.get("avatar_stakes_pending"):
                ladder_note = (
                    " 🏆 **Ladder Challenge!** Stakes are based on the "
                    "avatars locked for this match."
                )
            elif matched_ladder_info:
                from utils.database import get_user_event_elo

                elo_diff = abs(
                    get_user_event_elo(matched_ladder_info["challenger_id"])
                    - get_user_event_elo(interaction.user.id)
                )
                if elo_diff >= 100:
                    ladder_note = " 🏆 **Ladder Challenge!** Top 16 player - Special stakes (2x/0.5x ELO)!"
                else:
                    ladder_note = " 🏆 **Ladder Challenge!** Top 16 player (normal stakes - ELO diff < 100)"

            await lfg_channel.send(
                f"{match_type_emoji} **{match_type_label} Match Found!** {interaction.user.mention} matched with {matched_user.mention}!{ladder_note}"
            )

        await lfg_cog.update_lfg_status()

        if reporter_dm_failed:
            await interaction.followup.send(
                f"{match_type_emoji} {match_type_label} match found! You've been paired with {matched_global}. Check <#{config.DM_DISABLED_CHANNEL_ID}>!",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"{match_type_emoji} {match_type_label} match found! You've been paired with {matched_global}. Check your DMs!",
                ephemeral=True,
            )
    else:
        queue_label = "Omens" if queue_type == "points" else queue_type.capitalize()
        deck_msg = f"\n**Deck:** {deck_url}" if deck_url else ""
        try:
            await interaction.user.send(
                f"You have been added to the **{queue_label}** queue for {timeframe_value} minutes.{deck_msg}"
            )
        except Exception:
            pass

        try:
            await lfg_cog.update_lfg_status()
        except Exception as e:
            logger.error(f"Failed to update LFG status after queue join: {e}")

        await interaction.followup.send(
            f"You've joined the **{queue_label}** queue for {timeframe_value} minutes!{deck_msg}",
            ephemeral=True,
        )


class JoinQueueButtons(discord.ui.View):
    """Buttons for joining the LFG queue (Ranked, Testing, or Both) - for empty queue"""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        if not is_pilot_active("PointsQueue"):
            self.remove_item(self.join_points_button)
        if not is_pilot_active("RankedQueue"):
            self.remove_item(self.join_ranked_button)
        if not is_pilot_active("CasualQueue"):
            self.remove_item(self.join_testing_button)
        if not is_pilot_active("GrewWolves"):
            self.remove_item(self.join_limited_button)
        if not is_pilot_active("RumbleQueue"):
            self.remove_item(self.join_rumble_button)

    async def _handle_join(self, interaction: discord.Interaction, queue_type: str):
        """Shared handler for all join buttons"""
        # Check if already in this specific queue type
        user_queues = lfg_queue.get(interaction.user.id, {}).get("queues", {})
        if queue_type in user_queues:
            await interaction.response.send_message(
                f"You're already in the {queue_type.capitalize()} queue!", ephemeral=True
            )
            return
        if queue_type == "limited":
            modal = LimitedQueueModal(self.bot)
        elif queue_type == "points":
            modal = PointsQueueModal(self.bot)
        else:
            modal = DeckURLModal(self.bot, is_button_join=True, queue_type=queue_type)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="📊 Join Omens",
        style=discord.ButtonStyle.primary,
        custom_id="join_lfg_points",
    )
    async def join_points_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not is_pilot_active("PointsQueue"):
            await interaction.response.send_message(
                "Omens queue is not currently available.", ephemeral=True
            )
            return
        await self._handle_join(interaction, "points")

    @discord.ui.button(
        label="⚔️ Join Ranked",
        style=discord.ButtonStyle.primary,
        custom_id="join_lfg_ranked",
    )
    async def join_ranked_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not is_pilot_active("RankedQueue"):
            await interaction.response.send_message(
                "Ranked queue is not currently available.", ephemeral=True
            )
            return
        await self._handle_join(interaction, "ranked")

    @discord.ui.button(
        label="⭐ Join Casual",
        style=discord.ButtonStyle.primary,
        custom_id="join_lfg_testing",
    )
    async def join_testing_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not is_pilot_active("CasualQueue"):
            await interaction.response.send_message(
                "Casual queue is not currently available.", ephemeral=True
            )
            return
        await self._handle_join(interaction, "testing")

    @discord.ui.button(
        label="🎲 Join Limited",
        style=discord.ButtonStyle.primary,
        custom_id="join_lfg_limited",
    )
    async def join_limited_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not is_pilot_active("GrewWolves"):
            await interaction.response.send_message(
                "Limited queue is not currently available.", ephemeral=True
            )
            return
        await self._handle_join(interaction, "limited")

    @discord.ui.button(
        label="💥 Join Rumble",
        style=discord.ButtonStyle.primary,
        custom_id="join_lfg_rumble",
    )
    async def join_rumble_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not is_pilot_active("RumbleQueue"):
            await interaction.response.send_message(
                "Rumble queue is not currently available.", ephemeral=True
            )
            return
        await self._handle_join(interaction, "rumble")

    @discord.ui.button(
        label="📋 Report Last Match",
        style=discord.ButtonStyle.secondary,
        custom_id="report_last_match",
        row=1,
    )
    async def report_last_match_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Report the user's most recent unreported match (generates fresh reporting buttons)"""
        try:
            await interaction.response.defer(ephemeral=True)

            # Get guild ID from interaction
            if not interaction.guild:
                await interaction.followup.send(
                    "This command can only be used in a server.",
                    ephemeral=True,
                )
                return

            guild_id = interaction.guild.id
            logger.info(f"Report Last Match: User {interaction.user.id} ({interaction.user.global_name}) in guild {guild_id}")

            # Get the last unreported pairing
            try:
                pairing = get_last_unreported_pairing(interaction.user.id, guild_id)
                logger.info(f"Report Last Match: Found pairing: {pairing is not None}")
            except Exception as e:
                logger.error(f"Report Last Match: Database error getting pairing: {e}", exc_info=True)
                await interaction.followup.send(
                    "❌ Database error occurred. Please contact an admin.",
                    ephemeral=True,
                )
                return

            if not pairing:
                await interaction.followup.send(
                    "❌ No unreported matches found.\n\n**Tip:** Join the queue and play a match first!",
                    ephemeral=True,
                )
                return

            # Determine opponent
            if pairing['player1_id'] == interaction.user.id:
                opponent_id = pairing['player2_id']
                reporter_deck_url = pairing.get('player1_deck_url')
                opponent_deck_url = pairing.get('player2_deck_url')
            else:
                opponent_id = pairing['player1_id']
                reporter_deck_url = pairing.get('player2_deck_url')
                opponent_deck_url = pairing.get('player1_deck_url')

            # Fetch opponent user
            try:
                opponent_user = await self.bot.fetch_user(opponent_id)
            except Exception as e:
                logger.error(f"Failed to fetch opponent user {opponent_id}: {e}")
                await interaction.followup.send(
                    "Failed to fetch opponent information. Please try again.",
                    ephemeral=True,
                )
                return

            # Determine match type
            match_type = pairing.get('match_type', 'ranked')

            # Get run IDs for limited matches
            reporter_run_id = 0
            opponent_run_id = 0
            if match_type == 'limited':
                reporter_run = get_active_arena_run(interaction.user.id)
                opponent_run = get_active_arena_run(opponent_id)
                reporter_run_id = int(reporter_run['run_id']) if reporter_run else 0
                opponent_run_id = int(opponent_run['run_id']) if opponent_run else 0

            reporter_deck_text = f"\n**Your Deck:** {reporter_deck_url}" if reporter_deck_url else ""

            if match_type == "limited":
                match_type_emoji = "🎲"
                match_type_label = "Limited"
            elif match_type == "ranked":
                match_type_emoji = "⚔️"
                match_type_label = "Ranked"
            elif match_type == "rumble":
                match_type_emoji = "💥"
                match_type_label = "Rumble"
            elif match_type == "points":
                match_type_emoji = "📊"
                match_type_label = "Omens"
            else:
                match_type_emoji = "⭐"
                match_type_label = "Casual"

            pairing_id = pairing.get('pairing_id', 0)
            match_card_view = MatchCardView(
                bot=self.bot,
                pairing_id=pairing_id,
                player1_id=interaction.user.id,
                player1_global=interaction.user.global_name or interaction.user.display_name,
                player2_id=opponent_id,
                player2_global=opponent_user.global_name or opponent_user.display_name,
                player1_deck_url=reporter_deck_url,
                player2_deck_url=opponent_deck_url,
                match_start_time=datetime.datetime.now(),
                guild_id=guild_id,
                match_type=match_type,
                player1_run_id=reporter_run_id,
                player2_run_id=opponent_run_id,
                player1_avatar=(
                    pairing.get("player1_avatar")
                    if pairing["player1_id"] == interaction.user.id
                    else pairing.get("player2_avatar")
                ),
                player2_avatar=(
                    pairing.get("player2_avatar")
                    if pairing["player1_id"] == interaction.user.id
                    else pairing.get("player1_avatar")
                ),
                event_snapshot=(
                    {
                        "event_id": pairing.get("event_id"),
                        "start_date": pairing.get("event_started_at"),
                        "avatar_specific": pairing.get("event_avatar_specific"),
                    }
                    if pairing.get("event_id")
                    else None
                ),
            )

            # Try to send to DM first
            try:
                await interaction.user.send(
                    f"{match_type_emoji} **{match_type_label} Match Report**\n\n**Opponent:** {opponent_user.mention} (**{opponent_user.global_name or opponent_user.display_name}**){reporter_deck_text}\n\nUse the button below to report the result.",
                    view=match_card_view,
                )
                await interaction.followup.send(
                    "✅ Match reporting buttons sent! Check your DMs.",
                    ephemeral=True,
                )
            except discord.Forbidden:
                # DM failed, fall back to DM-disabled channel
                dm_channel = self.bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
                if dm_channel:
                    try:
                        # Grant permissions
                        guild = self.bot.get_guild(guild_id)
                        if guild:
                            member = guild.get_member(interaction.user.id)
                            if member:
                                await dm_channel.set_permissions(
                                    member, read_messages=True, send_messages=True
                                )

                        await dm_channel.send(
                            f"{interaction.user.mention} {match_type_emoji} **{match_type_label} Match Report**\n\n**Opponent:** {opponent_user.mention} (**{opponent_user.global_name or opponent_user.display_name}**){reporter_deck_text}\n\nUse the button below to report the result.",
                            view=match_card_view,
                        )
                        await interaction.followup.send(
                            f"✅ Match reporting buttons sent to <#{config.DM_DISABLED_CHANNEL_ID}>!",
                            ephemeral=True,
                        )
                    except Exception as e:
                        logger.error(f"Failed to send to DM-disabled channel: {e}")
                        await interaction.followup.send(
                            "❌ Failed to send match reporting buttons. Please try again.",
                            ephemeral=True,
                        )
                else:
                    await interaction.followup.send(
                        "❌ Could not send DM and fallback channel not found. Please contact an admin.",
                        ephemeral=True,
                    )

        except Exception as e:
            # Catch-all for any unexpected errors
            logger.error(f"Report Last Match: Unexpected error for user {interaction.user.id}: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    f"❌ An unexpected error occurred: {str(e)}\nPlease contact an admin.",
                    ephemeral=True,
                )
            except Exception:
                # If even the followup fails, at least we logged it
                pass


class ActiveQueueButtons(JoinQueueButtons):
    """Buttons for active queue (includes Leave Queue button)"""

    @discord.ui.button(
        label="Leave Queue",
        style=discord.ButtonStyle.danger,
        custom_id="leave_lfg_queue",
    )
    async def leave_queue_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Remove user from the LFG queue (reuses !cancel logic)"""
        async with lfg_queue_lock:
            was_in_queue = interaction.user.id in lfg_queue
            if was_in_queue:
                lfg_queue.pop(interaction.user.id)

        if was_in_queue:
            # Send ephemeral confirmation
            await interaction.response.send_message(
                "You have been removed from the LFG queue.", ephemeral=True
            )

            # Update status message after leaving queue (same as !cancel)
            cog = self.bot.get_cog("LFGCog")
            if cog:
                await cog.update_lfg_status()
        else:
            # User not in queue
            await interaction.response.send_message(
                "You are not currently in the LFG queue.", ephemeral=True
            )
