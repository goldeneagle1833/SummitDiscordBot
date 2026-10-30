"""Ask waiting voice players whether they'd play a no-voice game.

Voice and no-voice players never pair on their own. When someone joins a queue
as no voice and voice players are already waiting there, each of those voice
players gets a DM: someone is looking for a no-voice game, want to play it?
Accepting re-joins them to that queue as no voice, which pairs them with the
waiting no-voice player through the normal join flow. Declining (or ignoring
it) leaves them queued for voice. A voice player is asked at most once about
the same no-voice player in the same queue.

Players who only play on voice can tap "Mark me as voice only" on the offer
(or use ``!voice_only`` / ``/voice-only``, or their website profile) and are
never asked again until they turn it off.
"""

import asyncio

import datetime
import logging

import discord

import config
from cogs.lfg.queue_definitions import queue_definition
from cogs.lfg.state import lfg_queue, lfg_queue_lock
from cogs.lfg.voice import NO_VOICE, VOICE, normalize_voice_preference, queue_has_voice_choice
from repositories.voice_only_repo import set_voice_only, voice_only_ids

logger = logging.getLogger("discord_bot")

# (voice_player_id, no_voice_player_id, queue_type) -> when the offer was sent
sent_offers = {}
OFFER_MEMORY = datetime.timedelta(hours=6)
MIN_REJOIN_MINUTES = 5


def _queue_label(queue_type):
    definition = queue_definition(queue_type)
    return definition["label"] if definition else queue_type.capitalize()


def _entry_voice(entry):
    return normalize_voice_preference(entry.get("voice")) or VOICE


def _minutes_left(entry, now):
    elapsed = (now - entry["timestamp"]).total_seconds() / 60
    return entry["timeframe"] - elapsed


def waiting_voice_players(queue_type, no_voice_player_id, now=None, skip_ids=()):
    """Voice players waiting in this queue who haven't been asked about this no-voice player.

    Ladder challenges are left out: accepting re-joins the queue as a plain game,
    which would drop the challenge stakes. ``skip_ids`` are voice-only players.
    """
    now = now or datetime.datetime.now()
    for key, sent_at in list(sent_offers.items()):
        if now - sent_at > OFFER_MEMORY:
            del sent_offers[key]

    players = []
    for user_id, user_data in lfg_queue.items():
        if user_id == no_voice_player_id or user_id in skip_ids:
            continue
        entry = user_data.get("queues", {}).get(queue_type)
        if not entry or entry.get("ladder_info") or _entry_voice(entry) != VOICE:
            continue
        if _minutes_left(entry, now) <= 0:
            continue
        if (user_id, no_voice_player_id, queue_type) in sent_offers:
            continue
        players.append((entry["timestamp"], user_id))
    return [user_id for _, user_id in sorted(players)]


async def offer_no_voice_game(bot, queue_type, no_voice_player_id):
    """DM every waiting voice player in the queue about a new no-voice player."""
    if not queue_has_voice_choice(queue_type):
        return
    try:
        skip_ids = await asyncio.to_thread(voice_only_ids, list(lfg_queue))
    except Exception as e:
        logger.warning(f"Could not read voice-only players: {e}")
        skip_ids = set()
    async with lfg_queue_lock:
        voice_player_ids = waiting_voice_players(queue_type, no_voice_player_id, skip_ids=skip_ids)
        now = datetime.datetime.now()
        for user_id in voice_player_ids:
            sent_offers[(user_id, no_voice_player_id, queue_type)] = now

    label = _queue_label(queue_type)
    for user_id in voice_player_ids:
        try:
            user = bot.get_user(user_id) or await bot.fetch_user(user_id)
            await user.send(
                f"🔇 Someone just joined the **{label}** queue looking for a **no-voice** game. "
                f"You're queued for voice. Would you like to play them without voice?\n"
                f"-# Only play on voice? Tap **Mark me as voice only** and I'll stop asking.",
                view=NoVoiceOfferView(bot, queue_type, user_id, no_voice_player_id),
            )
            logger.info(
                f"No-voice offer sent to {user_id} for {no_voice_player_id} in {queue_type}"
            )
        except Exception as e:
            logger.warning(f"Could not send no-voice offer to {user_id}: {e}")


class _OfferFollowup:
    """Followup messages from the join flow go back to the player's DM."""

    def __init__(self, interaction):
        self._interaction = interaction

    async def send(self, *args, **kwargs):
        kwargs.pop("ephemeral", None)
        return await self._interaction.followup.send(*args, **kwargs)


class _OfferInteraction:
    """Run the queue join flow for a DM button click as if it came from the server."""

    def __init__(self, bot, interaction, member, guild):
        self.user = member
        self.guild = guild
        self.channel = bot.get_channel(getattr(bot.get_cog("LFGCog"), "lfg_channel_id", 0))
        self.followup = _OfferFollowup(interaction)


class NoVoiceOfferView(discord.ui.View):
    def __init__(self, bot, queue_type, voice_player_id, no_voice_player_id):
        super().__init__(timeout=4 * 60 * 60)
        self.bot = bot
        self.queue_type = queue_type
        self.voice_player_id = voice_player_id
        self.no_voice_player_id = no_voice_player_id

    async def _close(self, interaction, text):
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(content=text, view=self)

    @discord.ui.button(label="Play without voice", style=discord.ButtonStyle.success, emoji="🔇")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        label = _queue_label(self.queue_type)

        async with lfg_queue_lock:
            mine = lfg_queue.get(self.voice_player_id, {}).get("queues", {}).get(self.queue_type)
            theirs = lfg_queue.get(self.no_voice_player_id, {}).get("queues", {}).get(self.queue_type)
            if not mine:
                await self._close(interaction, f"You're no longer in the **{label}** queue, so this offer has closed.")
                return
            if not theirs or _entry_voice(theirs) != NO_VOICE:
                await self._close(
                    interaction,
                    f"That player already found a game. You're still in the **{label}** queue for voice.",
                )
                return
            minutes = max(MIN_REJOIN_MINUTES, round(_minutes_left(mine, datetime.datetime.now())))
            entry = dict(mine)
            # Leave this queue only; the join below puts them back in as no voice.
            del lfg_queue[self.voice_player_id]["queues"][self.queue_type]
            if not lfg_queue[self.voice_player_id]["queues"]:
                lfg_queue.pop(self.voice_player_id, None)

        await self._close(interaction, f"🔇 Pairing you for a no-voice **{label}** game...")

        guild = self.bot.get_guild(config.GUILD_ID)
        member = None
        if guild:
            member = guild.get_member(self.voice_player_id)
            if member is None:
                try:
                    member = await guild.fetch_member(self.voice_player_id)
                except Exception as e:
                    logger.error(f"No-voice offer: could not fetch member {self.voice_player_id}: {e}")
        if member is None:
            await interaction.followup.send(
                "Sorry, I couldn't reach the Summit server to pair you. Please join the queue again."
            )
            return

        from cogs.lfg.queue import _process_queue_join

        await _process_queue_join(
            self.bot,
            _OfferInteraction(self.bot, interaction, member, guild),
            self.queue_type,
            minutes,
            entry.get("deck_url"),
            run_id=entry.get("run_id"),
            origin=entry.get("origin", "discord"),
            voice=NO_VOICE,
            alert_avatar=entry.get("alert_avatar", False),
            deck_avatar=entry.get("deck_avatar"),
        )

    @discord.ui.button(label="No thanks", style=discord.ButtonStyle.secondary)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self._close(
            interaction,
            f"No problem. You're still in the **{_queue_label(self.queue_type)}** queue for voice.",
        )

    @discord.ui.button(label="Mark me as voice only", style=discord.ButtonStyle.primary, emoji="🔊")
    async def voice_only(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await asyncio.to_thread(set_voice_only, self.voice_player_id, True, "offer_button")
        await interaction.edit_original_response(
            content=voice_only_text(True, _queue_label(self.queue_type)),
            view=VoiceOnlyToggleView(self.voice_player_id, True),
        )


VOICE_ONLY_OFF_HINT = (
    "Turn it off any time with `/voice-only`, `!voice_only off`, "
    "or **Queue settings** on your sorcererssummit.com profile."
)


def voice_only_text(voice_only, queue_label=None):
    """What the bot says about a player's voice-only setting."""
    if voice_only:
        still_queued = f" You're still in the **{queue_label}** queue for voice." if queue_label else ""
        return (
            f"🔊 You're marked as a **voice-only** player. I won't ask you about "
            f"no-voice games anymore.{still_queued}\n{VOICE_ONLY_OFF_HINT}"
        )
    return (
        "🔇 Voice only is **off**. When you're queued for voice and someone joins "
        "looking for a no-voice game, I'll ask if you want to play them."
    )


class VoiceOnlyToggleView(discord.ui.View):
    """One button that flips the player's voice-only setting."""

    def __init__(self, user_id, voice_only):
        super().__init__(timeout=4 * 60 * 60)
        self.user_id = user_id
        self.voice_only = voice_only
        self._sync_button()

    def _sync_button(self):
        if self.voice_only:
            self.toggle.label = "Turn off voice only"
            self.toggle.emoji = "🔇"
            self.toggle.style = discord.ButtonStyle.secondary
        else:
            self.toggle.label = "Mark me as voice only"
            self.toggle.emoji = "🔊"
            self.toggle.style = discord.ButtonStyle.primary

    @discord.ui.button(label="Turn off voice only", style=discord.ButtonStyle.secondary)
    async def toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This button isn't for you.", ephemeral=True)
            return
        await interaction.response.defer()
        self.voice_only = await asyncio.to_thread(
            set_voice_only, self.user_id, not self.voice_only, "toggle_button"
        )
        self._sync_button()
        await interaction.edit_original_response(content=voice_only_text(self.voice_only), view=self)
