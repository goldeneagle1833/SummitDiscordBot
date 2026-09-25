import discord
import random
import datetime
import hashlib
import logging
import sqlite3
import time

import config
from cogs.lfg.state import lfg_queue, lfg_queue_lock, matching_web_users, pending_web_matches
from cogs.lfg.queue_definitions import queue_definition, queue_is_enabled
from cogs.lfg.helpers import correction_tip, match_type_presentation
from cogs.lfg.voice import (
    ANY_VOICE,
    VOICE,
    VOICE_LABELS,
    NO_VOICE,
    normalize_voice_preference,
    queue_supports_voice,
    resolve_match_voice,
)
from cogs.lfg.persistent_confirm import create_match_card_view, update_match_card_message_ref
from cogs.lfg.pairing_messages import (
    WEB_MATCH_TTL_SECONDS,
    PairingPlayer,
    announce_pairing,
    ladder_stakes_note,
    match_delivery_extras,  # re-exported: tests import it from here
    send_pairing_messages,
)
from utils.constants import SORCERY_NICKNAMES
from utils.database import save_pairing, get_pairing_ban, pairing_ban_message
from repositories.limited_repo import save_limited_pairing, get_active_arena_run
from services.card_points_service import validate_deck_points
from services.limited_service import auto_start_arena_run
from services.sorcery_online_matchmaking import provision_sorcery_online_match
from utils.deck_checker import clean_deck_url

logger = logging.getLogger("discord_bot")


def _clear_matching_web_users(*user_ids):
    for user_id in user_ids:
        matching_web_users.pop(user_id, None)


async def provision_match_and_publish_results(guild_id, pairing_id, queue_type, players, voice=False):
    """Provision seats and publish stable results for website-origin players."""
    provisioned_links = await provision_sorcery_online_match(
        guild_id, pairing_id, queue_type, players
    ) or {}
    result_id_base = f"{guild_id}:{pairing_id}"
    matched_at = int(time.time() * 1000)
    for player in players:
        user_id = player["discord_user_id"]
        if player.get("origin") == "sorcery_online":
            pending_web_matches.pop(user_id, None)
            game_url = provisioned_links.get(user_id)
            if game_url:
                result_id = hashlib.sha256(f"{result_id_base}:{user_id}".encode()).hexdigest()
                pending_web_matches[user_id] = {
                    "id": result_id,
                    "queue_type": queue_type,
                    "opponent_name": player["opponent_name"],
                    "matched_at": matched_at,
                    "game_url": game_url,
                    "voice": bool(voice),
                    "expires_at": time.time() + WEB_MATCH_TTL_SECONDS,
                }
        matching_web_users.pop(user_id, None)
    return provisioned_links


LIMITED_RUN_REQUIRED_MESSAGE = (
    "You don't have an active Limited run. "
    "Paste your DraftSorcery draft URL (e.g. `https://draftsorcery.com/?deck=...`) "
    "in the **DraftSorcery Draft URL** field and we'll start your run automatically."
)


def parse_queue_timeframe(raw_value):
    """Parse and clamp queue timeframe values."""

    try:
        timeframe_value = int(raw_value) if raw_value else 30
        if timeframe_value < 5:
            timeframe_value = 5
        elif timeframe_value > 240:
            timeframe_value = 240
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


VOICE_SELECT_DESCRIPTIONS = {
    VOICE: "Only match players who want voice (or don't mind)",
    NO_VOICE: "Only match players who want no voice (or don't mind)",
    ANY_VOICE: "Match with anyone",
}


def build_voice_select():
    """Voice-preference dropdown for the Ranked/Casual join modal.

    Voice is preselected so joining takes no extra clicks; players who want a
    different preference pick it from the dropdown.
    """
    return discord.ui.Select(
        placeholder="Voice, no voice, or either?",
        min_values=1,
        max_values=1,
        required=True,
        options=[
            discord.SelectOption(
                label=VOICE_LABELS[value],
                value=value,
                description=VOICE_SELECT_DESCRIPTIONS[value],
                default=value == VOICE,
            )
            for value in (VOICE, NO_VOICE, ANY_VOICE)
        ],
    )


class DeckURLModal(discord.ui.Modal, title="Join LFG Queue"):
    """Modal for entering a deck URL when joining the LFG queue"""

    deck_url = discord.ui.TextInput(
        label="Deck URL",
        placeholder="https://sorcerytcg.com/decks/... (optional)",
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

    def __init__(self, bot, is_button_join=True, queue_type="ranked"):
        super().__init__()
        self.bot = bot
        self.is_button_join = (
            is_button_join  # True if from button, False if from !lfg command
        )
        self.queue_type = queue_type
        self.voice_select = None
        if queue_supports_voice(queue_type):
            self.voice_select = build_voice_select()
            # Keep the voice choice next to the deck URL, above the duration.
            self.remove_item(self.timeframe)
            self.add_item(
                discord.ui.Label(
                    text="Voice chat",
                    component=self.voice_select,
                )
            )
            self.add_item(self.timeframe)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        timeframe_value = parse_queue_timeframe(self.timeframe.value)
        voice = (
            normalize_voice_preference(self.voice_select.values[0])
            if self.voice_select is not None and self.voice_select.values
            else ANY_VOICE
        ) or ANY_VOICE

        deck_url = clean_deck_url(self.deck_url.value.strip()) if self.deck_url.value else None

        # For limited queue, player must have an active arena run.
        # If none exists, attempt to auto-create one from the provided DraftSorcery URL.
        run_id = None
        if self.queue_type == "limited":
            active_run = get_active_arena_run(interaction.user.id)
            if active_run and active_run["status"] == "active" and active_run["wins"] < 4 and active_run["losses"] < 2:
                run_id = active_run["run_id"]
                deck_url = active_run["deck_url"]
            elif deck_url and "draftsorcery.com" in deck_url.lower():
                try:
                    display_name = interaction.user.global_name or interaction.user.display_name
                    active_run = await interaction.client.loop.run_in_executor(
                        None, auto_start_arena_run, interaction.user.id, display_name, deck_url
                    )
                    run_id = active_run["run_id"]
                    deck_url = active_run["deck_url"]
                except ValueError as e:
                    await interaction.followup.send(str(e), ephemeral=True)
                    return
                except Exception as e:
                    logger.error("Failed to auto-start arena run for %s: %s", interaction.user.id, e)
                    await interaction.followup.send(
                        "Failed to start your Limited run. Please check the URL or contact an admin.",
                        ephemeral=True,
                    )
                    return
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
            voice=voice,
        )


class LimitedQueueModal(discord.ui.Modal, title="Join Limited Queue"):
    """Modal for joining the Limited queue.

    If the player has no active run in the DB, they can paste their DraftSorcery
    draft URL and we'll validate it via the SorceryDraft API and auto-create the run.
    """

    timeframe = discord.ui.TextInput(
        label="Queue Duration (minutes)",
        placeholder="30",
        required=False,
        default="30",
        max_length=3,
    )

    draft_url = discord.ui.TextInput(
        label="DraftSorcery Draft URL (if no active run)",
        placeholder="https://draftsorcery.com/?deck=...",
        required=False,
        max_length=200,
    )

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        timeframe_value = parse_queue_timeframe(self.timeframe.value)

        active_run = get_active_arena_run(interaction.user.id)
        if active_run and active_run["status"] == "active" and active_run["wins"] < 4 and active_run["losses"] < 2:
            run_id = int(active_run["run_id"])
            deck_url = active_run["deck_url"]
        else:
            # No active run — try to auto-create one from the provided DraftSorcery URL
            url_value = self.draft_url.value.strip() if self.draft_url.value else ""
            if not url_value or "draftsorcery.com" not in url_value.lower():
                await interaction.followup.send(LIMITED_RUN_REQUIRED_MESSAGE, ephemeral=True)
                return
            try:
                display_name = interaction.user.global_name or interaction.user.display_name
                active_run = await interaction.client.loop.run_in_executor(
                    None, auto_start_arena_run, interaction.user.id, display_name, url_value
                )
                run_id = int(active_run["run_id"])
                deck_url = active_run["deck_url"]
            except ValueError as e:
                await interaction.followup.send(str(e), ephemeral=True)
                return
            except Exception as e:
                logger.error("Failed to auto-start arena run for %s: %s", interaction.user.id, e)
                await interaction.followup.send(
                    "Failed to start your Limited run. Please check the URL or contact an admin.",
                    ephemeral=True,
                )
                return

        await _process_queue_join(
            self.bot,
            interaction,
            "limited",
            timeframe_value,
            deck_url,
            run_id,
        )


class PointsQueueModal(discord.ui.Modal, title="Join Rumble (Omens) Queue"):
    """Modal for joining the Rumble (Omens) queue — requires a Curiosa or DraftSorcery deck URL."""

    deck_url = discord.ui.TextInput(
        label="Deck URL (required)",
        placeholder="Curiosa, Sorcery Online, or DraftSorcery deck link",
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

        deck_url = clean_deck_url(self.deck_url.value.strip())
        if not deck_url or not any(host in deck_url.lower() for host in (
            "curiosa.io", "sorcerytcg.com", "draftsorcery.com", "playsorceryonline.com"
        )):
            await interaction.followup.send(
                "Please provide a valid deck URL (Curiosa, Sorcery Online, or DraftSorcery).",
                ephemeral=True,
            )
            return

        timeframe_value = parse_queue_timeframe(self.timeframe.value)

        # Validate deck against point budget
        is_valid, message, total_points, max_budget = await validate_deck_points(deck_url)
        if not is_valid:
            await interaction.followup.send(
                f"**Deck not allowed in Rumble (Omens) queue.**\n{message}",
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
    bot, interaction, queue_type, timeframe_value, deck_url, run_id=None, origin="discord",
    voice=ANY_VOICE,
):
    """Handle queue join flow after modal validation."""
    voice = (normalize_voice_preference(voice) or ANY_VOICE) if queue_supports_voice(queue_type) else ANY_VOICE

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

    # Admin pairing ban (covers modals opened before the ban landed, and the website)
    ban = get_pairing_ban(interaction.user.id)
    if ban:
        await interaction.followup.send(pairing_ban_message(ban), ephemeral=True)
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
        matched_user_id = lfg_cog.check_if_someone_is_lfg(ctx, queue_type, voice=voice)

        if matched_user_id and matched_user_id != interaction.user.id:
            matched_entry = lfg_queue.get(matched_user_id, {}).get("queues", {}).get(queue_type, {})
            matched_user_deck_url = matched_entry.get("deck_url")
            matched_queue_type = queue_type
            matched_ladder_info = matched_entry.get("ladder_info")
            matched_run_id = int(matched_entry.get("run_id") or 0)
            matched_user_origin = matched_entry.get("origin", "discord")
            match_type = lfg_cog.resolve_match_type(queue_type, matched_queue_type)
            match_voice = queue_supports_voice(queue_type) and resolve_match_voice(
                voice, matched_entry.get("voice", ANY_VOICE)
            )

            if matched_ladder_info:
                from utils.database import get_user_event_elo, save_ladder_challenge, delete_ladder_challenge

                if not matched_ladder_info.get("challenge_id"):
                    challenge_id = save_ladder_challenge(matched_ladder_info["challenger_id"])
                    matched_ladder_info["challenge_id"] = challenge_id
                    logger.info(
                        f"Ladder challenge saved on match for challenger {matched_ladder_info['challenger_id']}, challenge_id: {challenge_id}"
                    )

                try:
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
            if origin == "sorcery_online":
                matching_web_users[interaction.user.id] = queue_type
            if matched_user_origin == "sorcery_online":
                matching_web_users[matched_user_id] = queue_type
            logger.info(
                f"Lock acquired: Matching {interaction.user.id} with {matched_user_id} (match_type={match_type})"
            )
        else:
            matched_user_id = None
            matched_user_deck_url = None
            matched_ladder_info = None
            matched_run_id = None
            matched_user_origin = None
            match_type = None
            match_voice = False
            lfg_cog.add_to_lfg_queue(
                ctx,
                timeframe_value,
                deck_url,
                queue_type,
                run_id=run_id,
                origin=origin,
                voice=voice,
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
        match_type_emoji, match_type_label = match_type_presentation(match_type)

        try:
            # Website-origin joins still represent Summit Discord members. Use
            # the guild cache first so a transient Discord API lookup failure
            # cannot prevent the Summit Bot match messages from being sent.
            matched_user = (
                interaction.guild.get_member(matched_user_id)
                if interaction.guild
                else None
            )
            if matched_user is None:
                matched_user = await bot.fetch_user(matched_user_id)
        except Exception as e:
            logger.error(f"Failed to fetch matched user {matched_user_id}: {e}")
            _clear_matching_web_users(interaction.user.id, matched_user_id)
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
            _clear_matching_web_users(interaction.user.id, matched_user_id)
            # Rollback ladder challenge so daily usage is not consumed
            if matched_ladder_info and matched_ladder_info.get("challenge_id"):
                delete_ladder_challenge(matched_ladder_info["challenge_id"])
            await interaction.followup.send(
                "Error: Could not save match pairing. Please try using !lfg command instead.",
                ephemeral=True,
            )
            return

        try:
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
                    voice=match_voice,
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
            _clear_matching_web_users(interaction.user.id, matched_user_id)
            # Rollback ladder challenge so daily usage is not consumed
            if matched_ladder_info and matched_ladder_info.get("challenge_id"):
                delete_ladder_challenge(matched_ladder_info["challenge_id"])
            await interaction.followup.send(
                "Error: Could not save match pairing to database. Please contact an admin.",
                ephemeral=True,
            )
            return

        provisioned_links = await provision_match_and_publish_results(
            interaction.guild.id,
            pairing_id,
            queue_type,
            [
                {
                    "discord_user_id": interaction.user.id,
                    "display_name": joiner_global,
                    "deck_url": deck_url,
                    "origin": origin,
                    "opponent_name": matched_global,
                },
                {
                    "discord_user_id": matched_user_id,
                    "display_name": matched_global,
                    "deck_url": matched_user_deck_url,
                    "origin": matched_user_origin,
                    "opponent_name": joiner_global,
                },
            ],
            voice=match_voice,
        )

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
            (interaction.user.id, joiner_global, interaction.user, deck_url, True),
            (matched_user_id, matched_global, matched_user, matched_user_deck_url, False),
        ]
        reporter_player, other_player = random.sample(players, 2)
        reporter_id, reporter_global, reporter_user, reporter_deck_url, reporter_is_joiner = reporter_player
        other_id, other_global, other_user, other_deck_url, _ = other_player

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

        match_card_view = create_match_card_view(
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
        )

        delivery = await send_pairing_messages(
            bot,
            reporter=PairingPlayer(
                reporter_id, reporter_global, reporter_user, reporter_deck_url
            ),
            other=PairingPlayer(other_id, other_global, other_user, other_deck_url),
            match_card_view=match_card_view,
            match_type=match_type,
            provisioned_links=provisioned_links,
            voice=match_voice,
        )

        ladder_note = ""
        if matched_ladder_info:
            ladder_note = ladder_stakes_note(
                matched_ladder_info["challenger_id"], interaction.user.id
            )
        await announce_pairing(
            lfg_channel,
            player_a=interaction.user,
            player_b=matched_user,
            match_type=match_type,
            note=ladder_note,
        )

        await lfg_cog.update_lfg_status()

        where = (
            f"<#{config.DM_DISABLED_CHANNEL_ID}>"
            if delivery.fell_back_for(interaction.user.id)
            else "your DMs"
        )
        await interaction.followup.send(
            f"{match_type_emoji} {match_type_label} match found! "
            f"You've been paired with {matched_global}. Check {where}!",
            ephemeral=True,
        )
    else:
        queue_label = "Rumble (Omens)" if queue_type == "points" else queue_type.capitalize()
        deck_msg = f"\n**Deck:** {deck_url}" if deck_url else ""
        if queue_supports_voice(queue_type):
            deck_msg += f"\n**Voice:** {VOICE_LABELS[voice]}"
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
        buttons = {
            "points": self.join_points_button,
            "ranked": self.join_ranked_button,
            "testing": self.join_testing_button,
            "limited": self.join_limited_button,
            "rumble": self.join_rumble_button,
        }
        for queue_type, button in buttons.items():
            definition = queue_definition(queue_type)
            if definition:
                button.label = f'{definition["emoji"]} Join {definition["label"]}'
            if not queue_is_enabled(queue_type):
                self.remove_item(button)

    async def _handle_join(self, interaction: discord.Interaction, queue_type: str):
        """Shared handler for all join buttons"""
        # Admin pairing ban: tell them why and how long is left, don't open the modal
        ban = get_pairing_ban(interaction.user.id)
        if ban:
            await interaction.response.send_message(pairing_ban_message(ban), ephemeral=True)
            return
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
        label="📊 Join Rumble (Omens)",
        style=discord.ButtonStyle.primary,
        custom_id="join_lfg_points",
    )
    async def join_points_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not queue_is_enabled("points"):
            await interaction.response.send_message(
                "Rumble (Omens) queue is not currently available.", ephemeral=True
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
        if not queue_is_enabled("ranked"):
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
        if not queue_is_enabled("testing"):
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
        if not queue_is_enabled("limited"):
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
        if not queue_is_enabled("rumble"):
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
            match_type_emoji, match_type_label = match_type_presentation(match_type)

            pairing_id = pairing.get('pairing_id', 0)
            match_card_view = create_match_card_view(
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
            )

            # Try to send to DM first
            try:
                dm_msg = await interaction.user.send(
                    f"{match_type_emoji} **{match_type_label} Match Report**\n\n"
                    f"**Opponent:** {opponent_user.mention}{reporter_deck_text}\n\n"
                    f"Use the button below to report the result.\n\n"
                    f"{correction_tip()}",
                    view=match_card_view,
                )
                try:
                    update_match_card_message_ref(match_card_view.card_id, dm_msg.id, dm_msg.channel.id)
                except Exception:
                    logger.warning("Could not save match card message ref for card %s", match_card_view.card_id)
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

                        # No deck line here: this channel is public.
                        fb_msg = await dm_channel.send(
                            f"{interaction.user.mention} {match_type_emoji} **{match_type_label} Match Report**\n\n"
                            f"**Opponent:** {opponent_user.mention}\n\n"
                            f"Use the button below to report the result.\n\n"
                            f"{correction_tip()}",
                            view=match_card_view,
                        )
                        try:
                            update_match_card_message_ref(match_card_view.card_id, fb_msg.id, fb_msg.channel.id)
                        except Exception:
                            logger.warning("Could not save match card message ref for card %s", match_card_view.card_id)
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
