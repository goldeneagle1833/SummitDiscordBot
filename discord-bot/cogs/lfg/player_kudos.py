"""The **Give Kudos** button that sits on every match message.

The friendly opposite of Report Player: a player thanks their opponent,
ticks why (good sport, great on voice, ...) and can add a short public
message. Kudos are stored in ``player_kudos`` and the website's homepage
Player of the Day features players who received them.

A kudos is tied to the recorded result of a match between the two players,
so the button only works once the result is in, and only once per match.
Like Report Player, the button is a DynamicItem (survives bot restarts) and
stays on the match message after the result is reported.
"""

import asyncio
import logging

import discord

from repositories.player_kudos_repo import KudosError, find_kudos_match, save_player_kudos

logger = logging.getLogger("discord_bot")

KUDOS_PREFIX = "pkd:"
ANONYMOUS_VALUE = "anonymous"
MAX_MESSAGE_LENGTH = 200

# (value, label). Same values as web-app/repositories/player_kudos_repo.py.
KUDOS_REASONS = [
    ("good_sport", "Good sport, win or lose"),
    ("friendly", "Friendly and fun to play with"),
    ("great_voice", "Great to talk with on voice"),
    ("helpful", "Helped me learn or explained a rule"),
    ("good_pace", "Played at a good pace"),
    ("fair_play", "Honest and fair, reported the result right"),
    ("great_game", "Great game, well played"),
]
KUDOS_LABELS = dict(KUDOS_REASONS)

# Discord gives a button press 3 seconds to answer. The "can you give kudos
# yet?" check must finish well inside that, or the form opens anyway and the
# save step decides.
PRECHECK_TIMEOUT_SECONDS = 1.5

NO_RESULT_YET = (
    "You can give kudos once this match's result has been reported and confirmed."
)
ALREADY_GIVEN = "You already gave kudos for this match. Thanks for spreading the good vibes!"


def _player_name(user) -> str:
    return getattr(user, "global_name", None) or getattr(user, "display_name", None) or str(user.id)


def _receiver_dm_text(giver_name, reasons, message, anonymous) -> str:
    who = "Someone you played" if anonymous else f"**{giver_name}**"
    lines = [f"👏 {who} gave you kudos after your match!"]
    for value in reasons:
        if value in KUDOS_LABELS:
            lines.append(f"• {KUDOS_LABELS[value]}")
    if message:
        lines.append(f"> {message}")
    lines.append("Players with kudos can be picked as Player of the Day on sorcererssummit.com.")
    return "\n".join(lines)


class PlayerKudosModal(discord.ui.Modal, title="Give Kudos"):
    def __init__(self, *, receiver_id: int, pairing_id: int, receiver_name: str | None = None):
        super().__init__()
        self.receiver_id = receiver_id
        self.pairing_id = pairing_id
        self.receiver_name = receiver_name

        self.reasons = discord.ui.CheckboxGroup(
            required=False,
            min_values=0,
            max_values=len(KUDOS_REASONS),
            options=[
                discord.CheckboxGroupOption(label=label, value=value)
                for value, label in KUDOS_REASONS
            ],
        )
        self.message = discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=MAX_MESSAGE_LENGTH,
            placeholder="Say thanks in your own words. This can be shown on the website.",
        )
        self.privacy = discord.ui.CheckboxGroup(
            required=False,
            min_values=0,
            max_values=1,
            options=[
                discord.CheckboxGroupOption(
                    label="Keep my name off the website", value=ANONYMOUS_VALUE
                )
            ],
        )
        self.add_item(discord.ui.Label(text="What made this a good game?", component=self.reasons))
        self.add_item(discord.ui.Label(text="Your message (optional, public)", component=self.message))
        self.add_item(discord.ui.Label(text="Privacy", component=self.privacy))

    async def on_submit(self, interaction: discord.Interaction):
        reasons = [r for r in self.reasons.values if r in KUDOS_LABELS]
        message = (self.message.value or "").strip()
        anonymous = ANONYMOUS_VALUE in list(self.privacy.values)
        if not reasons and not message:
            await interaction.response.send_message(
                "No kudos sent. Tick at least one box or write a message.", ephemeral=True
            )
            return

        # Answer Discord right away (3-second limit); the lookups and the save
        # can then take as long as they need.
        await interaction.response.defer(ephemeral=True, thinking=True)

        receiver = None
        try:
            receiver = interaction.client.get_user(self.receiver_id) or await interaction.client.fetch_user(
                self.receiver_id
            )
        except Exception:
            pass
        receiver_name = _player_name(receiver) if receiver else self.receiver_name
        giver_name = _player_name(interaction.user)

        try:
            await asyncio.to_thread(
                save_player_kudos,
                giver_id=interaction.user.id,
                giver_name=giver_name,
                receiver_id=self.receiver_id,
                receiver_name=receiver_name,
                pairing_id=self.pairing_id or None,
                reasons=reasons,
                message=message,
                anonymous=anonymous,
            )
        except KudosError as e:
            text = ALREADY_GIVEN if e.code == "already_given" else NO_RESULT_YET
            await interaction.followup.send(text, ephemeral=True)
            return
        except Exception as e:
            logger.error(f"Failed to save kudos: {e}", exc_info=True)
            await interaction.followup.send(
                "Something went wrong saving your kudos. Please try again.", ephemeral=True
            )
            return

        logger.info(
            "Kudos given: %s -> %s (pairing %s): %s",
            interaction.user.id, self.receiver_id, self.pairing_id, reasons,
        )
        await interaction.followup.send(
            f"👏 Kudos sent to {receiver_name or 'your opponent'}. Thanks for making the Summit a friendly place!",
            ephemeral=True,
        )

        if receiver is not None:
            try:
                await receiver.send(_receiver_dm_text(giver_name, reasons, message, anonymous))
            except Exception as e:  # DMs closed, etc. The kudos is saved anyway.
                logger.info("Could not DM kudos to %s: %s", self.receiver_id, e)


class PersistentKudosButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"pkd:(?P<giver>\d+):(?P<receiver>\d+):(?P<pairing>\d+)",
):
    """Give Kudos button that survives bot restarts.

    The custom id carries who may press it (``giver``), who they thank, and
    the pairing it came from.
    """

    def __init__(self, giver_id: int, receiver_id: int, pairing_id: int = 0):
        self.giver_id = int(giver_id)
        self.receiver_id = int(receiver_id)
        self.pairing_id = int(pairing_id or 0)
        super().__init__(
            discord.ui.Button(
                label="Give Kudos",
                style=discord.ButtonStyle.success,
                emoji="👏",
                custom_id=f"{KUDOS_PREFIX}{self.giver_id}:{self.receiver_id}:{self.pairing_id}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(
            giver_id=int(match["giver"]),
            receiver_id=int(match["receiver"]),
            pairing_id=int(match["pairing"]),
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.giver_id:
            await interaction.response.send_message(
                "This button is for the player this match message was sent to.",
                ephemeral=True,
            )
            return
        # Check before opening the form so nobody fills it in for nothing.
        # Run off the event loop with a time limit: a slow database must never
        # make Discord say "The application didn't respond in time".
        try:
            match = await asyncio.wait_for(
                asyncio.to_thread(find_kudos_match, self.giver_id, self.receiver_id, self.pairing_id or None),
                timeout=PRECHECK_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("Kudos pre-check took over %ss; opening the form anyway", PRECHECK_TIMEOUT_SECONDS)
            match = {}  # let the save step decide
        except KudosError:
            await interaction.response.send_message(ALREADY_GIVEN, ephemeral=True)
            return
        except Exception as e:
            logger.error(f"Kudos match lookup failed: {e}", exc_info=True)
            match = {}  # let the save step decide
        if match is None:
            await interaction.response.send_message(NO_RESULT_YET, ephemeral=True)
            return
        await interaction.response.send_modal(
            PlayerKudosModal(receiver_id=self.receiver_id, pairing_id=self.pairing_id)
        )


def _as_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def kudos_button(giver_id, receiver_id, pairing_id=None):
    """Build the Give Kudos button for ``giver_id``'s copy of a match message."""
    return PersistentKudosButton(giver_id, receiver_id, _as_int(pairing_id))


def is_kudos_item(item) -> bool:
    return str(getattr(item, "custom_id", "") or "").startswith(KUDOS_PREFIX)
