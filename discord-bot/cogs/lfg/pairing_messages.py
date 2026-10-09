"""Shared wording and delivery for the messages a new pairing produces.

Queue matches (:mod:`cogs.lfg.queue`), ladder auto-matches (:mod:`cogs.lfg.cog`)
and accepted direct challenges (:mod:`cogs.lfg.challenge`) all send the same
three things: a match card to the randomly chosen reporter, an informational
copy to the other player, and an announcement in the LFG channel.  Those
blocks were copy-pasted in all three modules and had drifted apart, so the
wording lives here and each path only supplies the players.
"""

import logging

import discord

import config
from cogs.lfg.helpers import (
    correction_tip,
    match_type_presentation,
    scrub_urls,
)
from cogs.lfg.persistent_confirm import update_match_card_message_ref
from cogs.lfg.player_report import report_player_button
from utils.database import (
    delete_pairing_announcement,
    get_pairing_announcement,
    save_pairing_announcement,
)
from cogs.lfg.voice import voice_match_tag, voice_match_text

logger = logging.getLogger("discord_bot")

WEB_MATCH_TTL_SECONDS = 30 * 60


class PrivateSeatLinkButton(discord.ui.Button):
    def __init__(self, user_id, game_url):
        super().__init__(
            label="Open my Sorcery Online seat", style=discord.ButtonStyle.success
        )
        self.user_id = int(user_id)
        self.game_url = game_url

    async def callback(self, interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "That private seat belongs to the matched player.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f"Your private Sorcery Online seat: <{self.game_url}>",
            ephemeral=True,
        )


class PrivateSeatLinkView(discord.ui.View):
    def __init__(self, user_id, game_url):
        super().__init__(timeout=WEB_MATCH_TTL_SECONDS)
        self.add_item(PrivateSeatLinkButton(user_id, game_url))


def match_delivery_extras(provisioned_links, reporter_id, other_id, is_voice_match=False):
    """Add Sorcery Online details only after both private seats were provisioned.

    The voice room link is shown for voice matches only, whether or not the
    seats were provisioned.
    """
    reporter_game_url = provisioned_links.get(reporter_id)
    other_game_url = provisioned_links.get(other_id)
    voice_text = voice_match_text(is_voice_match)
    if not reporter_game_url or not other_game_url:
        return None, None, "", "", voice_text
    reporter_game_text = (
        f"\n\n🎴 **Play on Sorcery Online:** <{reporter_game_url}>"
        if reporter_game_url
        else ""
    )
    other_game_text = (
        f"\n\n🎴 **Play on Sorcery Online:** <{other_game_url}>"
        if other_game_url
        else ""
    )
    return (
        reporter_game_url,
        other_game_url,
        reporter_game_text,
        other_game_text,
        voice_text,
    )


class PairingPlayer:
    """One side of a fresh pairing, plus how to reach them.

    ``interaction`` is set only when the player is mid-interaction and should
    be answered ephemerally instead of DMed (the accepter of a challenge).
    """

    def __init__(self, user_id, display_name, user, deck_url=None, interaction=None, avatar=None):
        self.user_id = int(user_id)
        self.display_name = display_name
        self.user = user
        self.deck_url = deck_url
        self.interaction = interaction
        # Avatar-mode events: the avatar read from their deck and locked to the match
        self.avatar = avatar


def _refresh_tip(is_reporter):
    where = f"in <#{config.LFG_CHANNEL_ID}>"
    if is_reporter:
        return (
            f"💡 **Tip:** If these buttons expire, click "
            f"**📋 Report Last Match** {where} for fresh ones."
        )
    return (
        f"💡 **Tip:** If you need your own reporting buttons, click "
        f"**📋 Report Last Match** {where}."
    )


def _build_body(
    *,
    title,
    opponent_user,
    self_deck_url,
    reporter_name,
    is_reporter,
    game_text="",
    voice_text="",
    self_mention=None,
    self_avatar=None,
    opponent_avatar=None,
):
    """Compose one player's match message.

    ``self_mention`` is used by the DM-disabled fallback, where the message is
    posted in a public channel and has to ping its recipient.
    """
    opening = f"{title} You've been matched with {opponent_user.mention}!"
    if self_mention:
        opening = f"{self_mention} {opening}"
    if self_deck_url:
        opening = f"{opening}\n**Your Deck:** <{self_deck_url}>"
    if self_avatar or opponent_avatar:
        opening = (
            f"{opening}\n**Avatars (locked for this match):** "
            f"you — {self_avatar or 'unknown'} · opponent — {opponent_avatar or 'unknown'}"
        )

    if is_reporter:
        role_line = (
            "You have the match report buttons — use them to report the result "
            "when your match is done."
        )
    else:
        role_line = (
            f"**{reporter_name}** has the match report buttons. When they report "
            f"the result, you'll receive a confirmation to verify the outcome."
        )

    return (
        f"{opening}\n\n{role_line}\n\n"
        f"{_refresh_tip(is_reporter)}\n{correction_tip()}"
        f"{game_text}{voice_text}"
    )


def _remember_card_message(match_card_view, message):
    try:
        update_match_card_message_ref(
            match_card_view.card_id, message.id, message.channel.id
        )
    except Exception:
        logger.warning(
            "Could not save match card message ref for card %s",
            getattr(match_card_view, "card_id", "?"),
        )


async def _open_dm_disabled_channel(bot, user_id):
    """Return the fallback channel, granting the player access to it first."""
    dm_channel = bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
    if not dm_channel:
        logger.error(
            "DM-disabled fallback channel %s not found", config.DM_DISABLED_CHANNEL_ID
        )
        return None

    guild = bot.get_guild(config.GUILD_ID)
    if guild:
        member = guild.get_member(user_id)
        if member:
            await dm_channel.set_permissions(
                member, read_messages=True, send_messages=True
            )
            role = guild.get_role(config.DM_DISABLED_ROLE_ID)
            if role and role not in member.roles:
                await member.add_roles(role)
            logger.info(
                "Granted fallback channel access to %s (%s) - can't receive DMs",
                member.display_name,
                user_id,
            )
    return dm_channel


async def _send_reporter(
    bot, reporter, other, *, title, match_card_view, game_url, game_text, voice_text
):
    """Deliver the match card. Returns True if it had to go to the fallback channel."""
    content = _build_body(
        title=title,
        opponent_user=other.user,
        self_deck_url=reporter.deck_url,
        reporter_name=reporter.display_name,
        is_reporter=True,
        game_text=game_text,
        voice_text=voice_text,
        self_avatar=reporter.avatar,
        opponent_avatar=other.avatar,
    )

    if reporter.interaction is not None:
        try:
            await reporter.interaction.followup.send(
                content, view=match_card_view, ephemeral=True
            )
        except Exception as e:
            logger.error(
                "Failed to send match card to reporter %s: %s", reporter.user_id, e
            )
        return False

    try:
        dm_msg = await reporter.user.send(content, view=match_card_view)
        _remember_card_message(match_card_view, dm_msg)
        return False
    except discord.HTTPException:
        pass

    try:
        dm_channel = await _open_dm_disabled_channel(bot, reporter.user_id)
        if dm_channel:
            # Deck and seat links are stripped so a public channel never leaks
            # them; the seat comes back as an ephemeral-only button instead.
            fallback = scrub_urls(
                _build_body(
                    title=title,
                    opponent_user=other.user,
                    self_deck_url=None,
                    reporter_name=reporter.display_name,
                    is_reporter=True,
                    self_mention=reporter.user.mention,
                )
            )
            if game_url:
                match_card_view.add_item(
                    PrivateSeatLinkButton(reporter.user_id, game_url)
                )
            fb_msg = await dm_channel.send(fallback + voice_text, view=match_card_view)
            _remember_card_message(match_card_view, fb_msg)
    except Exception as e:
        logger.error(
            "Failed to handle DM failure for reporter %s: %s", reporter.user_id, e
        )
    return True


def _report_player_view(other, reporter, pairing_id, match_type, view=None):
    """The other player's message gets just the Report Player button."""
    view = view or discord.ui.View(timeout=None)
    view.add_item(report_player_button(other.user_id, reporter.user_id, pairing_id, match_type))
    return view


async def _send_other(
    bot, reporter, other, *, title, game_url, game_text, voice_text,
    pairing_id=None, match_type="ranked",
):
    """Deliver the informational copy to the player without the report buttons.

    It still carries Report Player, like every match message.

    Returns True if it had to go to the fallback channel.
    """
    content = _build_body(
        title=title,
        opponent_user=reporter.user,
        self_deck_url=other.deck_url,
        reporter_name=reporter.display_name,
        is_reporter=False,
        game_text=game_text,
        voice_text=voice_text,
        self_avatar=other.avatar,
        opponent_avatar=reporter.avatar,
    )

    if other.interaction is not None:
        try:
            await other.interaction.followup.send(
                content,
                view=_report_player_view(other, reporter, pairing_id, match_type),
                ephemeral=True,
            )
        except Exception as e:
            logger.error("Failed to send match info to %s: %s", other.user_id, e)
        return False

    try:
        await other.user.send(
            content, view=_report_player_view(other, reporter, pairing_id, match_type)
        )
        return False
    except discord.HTTPException:
        pass

    try:
        dm_channel = await _open_dm_disabled_channel(bot, other.user_id)
        if dm_channel:
            fallback = scrub_urls(
                _build_body(
                    title=title,
                    opponent_user=reporter.user,
                    self_deck_url=None,
                    reporter_name=reporter.display_name,
                    is_reporter=False,
                    self_mention=other.user.mention,
                )
            )
            if game_url:
                await dm_channel.send(
                    fallback + voice_text,
                    view=_report_player_view(
                        other, reporter, pairing_id, match_type,
                        view=PrivateSeatLinkView(other.user_id, game_url),
                    ),
                )
            else:
                await dm_channel.send(
                    fallback + voice_text,
                    view=_report_player_view(other, reporter, pairing_id, match_type),
                )
    except Exception as e:
        logger.error(
            "Failed to handle DM failure for other player %s: %s", other.user_id, e
        )
    return True


class PairingDelivery:
    """Where each player's match message ended up.

    ``fell_back_for`` lets a caller tell the player who triggered the match
    whether to look in their DMs or in the DM-disabled channel, whichever side
    of the pairing they turned out to be.
    """

    def __init__(self, reporter_id, reporter_fell_back, other_id, other_fell_back):
        self.reporter_id = reporter_id
        self.reporter_fell_back = reporter_fell_back
        self.other_id = other_id
        self.other_fell_back = other_fell_back

    def fell_back_for(self, user_id):
        if int(user_id) == self.reporter_id:
            return self.reporter_fell_back
        return self.other_fell_back


async def send_pairing_messages(
    bot,
    *,
    reporter,
    other,
    match_card_view,
    match_type="ranked",
    provisioned_links=None,
    headline=None,
    voice=None,
):
    """Send both players their match message.

    ``reporter`` and ``other`` are :class:`PairingPlayer` instances; the
    reporter is the one who received ``match_card_view``.  ``headline``
    overrides the default "<Label> Match Found!" title.  ``voice`` is True/False
    for Ranked/Casual queue matches: the title says voice or no voice, and only
    voice matches get the room link.  None (direct challenges) leaves both out
    unless Sorcery Online seats were provisioned.  Returns a
    :class:`PairingDelivery` saying which players had to be reached through
    the DM-disabled channel.
    """
    emoji, label = match_type_presentation(match_type)
    title = f"{emoji} **{headline or f'{label} Match Found!'}**"
    # Queue pairings say whether the match is on voice; direct challenges (voice=None) don't.
    if voice is not None:
        title = f"{title} {voice_match_tag(voice)}"
    (
        reporter_game_url,
        other_game_url,
        reporter_game_text,
        other_game_text,
        voice_text,
    ) = match_delivery_extras(
        provisioned_links or {},
        reporter.user_id,
        other.user_id,
        is_voice_match=bool(voice),
    )

    # Every match message carries Report Player, so each side can flag the other.
    pairing_id = getattr(match_card_view, "pairing_id", None)
    match_card_view.add_item(
        report_player_button(reporter.user_id, other.user_id, pairing_id, match_type)
    )

    reporter_fell_back = await _send_reporter(
        bot,
        reporter,
        other,
        title=title,
        match_card_view=match_card_view,
        game_url=reporter_game_url,
        game_text=reporter_game_text,
        voice_text=voice_text,
    )
    other_fell_back = await _send_other(
        bot,
        reporter,
        other,
        title=title,
        game_url=other_game_url,
        game_text=other_game_text,
        voice_text=voice_text,
        pairing_id=pairing_id,
        match_type=match_type,
    )
    return PairingDelivery(
        reporter.user_id, reporter_fell_back, other.user_id, other_fell_back
    )


def ladder_stakes_note(challenger_id, opponent_id, challenger_avatar=None, opponent_avatar=None):
    """Return the ladder-challenge suffix for the public announcement.

    In Avatar mode the gap is between the two avatars' entries in this match.
    """
    from services.avatar_mode import ladder_elo

    try:
        elo_diff = abs(
            ladder_elo(challenger_id, challenger_avatar) - ladder_elo(opponent_id, opponent_avatar)
        )
    except Exception as e:
        logger.error("Could not read ladder ELO for the announcement note: %s", e)
        return " 🏆 **Ladder Challenge!** Top 16 player!"

    if elo_diff >= 100:
        return (
            " 🏆 **Ladder Challenge!** Top 16 player — special stakes (2x/0.5x ELO)!"
        )
    return " 🏆 **Ladder Challenge!** Top 16 player (normal stakes — ELO diff < 100)."


async def announce_pairing(
    channel,
    *,
    player_a,
    player_b,
    match_type="ranked",
    headline=None,
    note="",
    pairing_id=None,
):
    """Announce a new pairing in the LFG channel.

    The match id that ``!correct_match`` needs only exists once the result is
    recorded, so when ``pairing_id`` is given the message reference is stored
    and :func:`announce_match_id` appends the id at report time.
    """
    if not channel:
        return
    emoji, label = match_type_presentation(match_type)
    title = f"{emoji} **{headline or f'{label} Match Found!'}**"
    try:
        message = await channel.send(
            f"{title} {player_a.mention} matched with {player_b.mention}!{note}"
        )
    except Exception as e:
        logger.error(
            "Failed to announce pairing in channel %s: %s",
            getattr(channel, "id", "?"),
            e,
        )
        return
    if not pairing_id or message is None:
        return
    try:
        save_pairing_announcement(
            pairing_id, match_type, message.channel.id, message.id
        )
    except Exception as e:
        logger.warning(
            "Could not save announcement ref for pairing %s: %s", pairing_id, e
        )


def match_id_suffix(match_id):
    """The text appended to the announcement once the match is recorded."""
    return f" **Match ID:** #{match_id}"


async def announce_match_id(bot, pairing_id, match_type, match_id):
    """Append the recorded match id to the pairing's LFG channel announcement.

    Called when the result is recorded; the id shown is the match record id
    that ``!correct_match`` / ``!remove_match`` take.
    """
    if not pairing_id or not match_id:
        return
    try:
        ref = get_pairing_announcement(pairing_id, match_type)
    except Exception as e:
        logger.warning("Could not load announcement ref for pairing %s: %s", pairing_id, e)
        return
    if not ref:
        return
    try:
        channel = bot.get_channel(ref["channel_id"]) or await bot.fetch_channel(
            ref["channel_id"]
        )
        message = await channel.fetch_message(ref["message_id"])
        suffix = match_id_suffix(match_id)
        if suffix.strip() not in (message.content or ""):
            await message.edit(content=f"{message.content}{suffix}")
    except Exception as e:
        logger.warning(
            "Could not add match id %s to announcement for pairing %s: %s",
            match_id, pairing_id, e,
        )
        return
    try:
        delete_pairing_announcement(pairing_id, match_type)
    except Exception as e:
        logger.warning("Could not delete announcement ref for pairing %s: %s", pairing_id, e)
