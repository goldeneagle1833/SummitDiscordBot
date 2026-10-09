"""The **Report Player** button that sits on every match message.

Each player's match message carries a button that opens a modal: a list of
checkboxes for common problems plus a free-text box. Reports are stored in
``player_reports`` and shown to admins on the web app's admin log page,
under Blocked Users.

The button is a DynamicItem so it keeps working after a bot restart, and it
stays on the message after the result is reported or the match is cancelled.
"""

import logging

import discord

from repositories.player_reports_repo import save_player_report

logger = logging.getLogger("discord_bot")

REPORT_PLAYER_PREFIX = "prp:"

# (value, label) — values are stored, labels are what the player ticks.
REPORT_REASONS = [
    ("voice_refused", "Opponent joined voice but didn't want to use voice"),
    ("left_early", "Opponent left the match early without conceding"),
    ("no_show", "Opponent never showed up or joined the game"),
    ("toxic", "Opponent was rude, toxic, or harassing"),
    ("stalling", "Opponent stalled or played unreasonably slowly"),
    ("wrong_result", "Opponent reported the wrong result"),
    ("deck_mismatch", "Opponent played a different deck than they submitted"),
    ("cheating", "Suspected cheating"),
    ("other", "Something else (explain below)"),
]
REASON_LABELS = dict(REPORT_REASONS)


def _player_name(user) -> str:
    return getattr(user, "global_name", None) or getattr(user, "display_name", None) or str(user.id)


class PlayerReportModal(discord.ui.Modal, title="Report Player"):
    def __init__(self, *, reported_id: int, pairing_id: int, match_type: str):
        super().__init__()
        self.reported_id = reported_id
        self.pairing_id = pairing_id
        self.match_type = match_type

        self.reasons = discord.ui.CheckboxGroup(
            required=False,
            min_values=0,
            max_values=len(REPORT_REASONS),
            options=[
                discord.CheckboxGroupOption(label=label, value=value)
                for value, label in REPORT_REASONS
            ],
        )
        self.details = discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=1000,
            placeholder="Anything else admins should know about this match?",
        )
        self.add_item(discord.ui.Label(text="What happened?", component=self.reasons))
        self.add_item(discord.ui.Label(text="More feedback", component=self.details))

    async def on_submit(self, interaction: discord.Interaction):
        reasons = list(self.reasons.values)
        details = (self.details.value or "").strip()
        if not reasons and not details:
            await interaction.response.send_message(
                "Nothing was reported. Tick at least one box or add some feedback.",
                ephemeral=True,
            )
            return

        reported_name = None
        try:
            reported = interaction.client.get_user(self.reported_id) or await interaction.client.fetch_user(
                self.reported_id
            )
            reported_name = _player_name(reported)
        except Exception:
            pass

        try:
            save_player_report(
                reporter_id=interaction.user.id,
                reporter_name=_player_name(interaction.user),
                reported_id=self.reported_id,
                reported_name=reported_name,
                pairing_id=self.pairing_id,
                match_type=self.match_type,
                reasons=reasons,
                details=details,
            )
        except Exception as e:
            logger.error(f"Failed to save player report: {e}", exc_info=True)
            await interaction.response.send_message(
                "Something went wrong saving your report. Please try again or contact an admin.",
                ephemeral=True,
            )
            return

        logger.info(
            "Player report filed: %s reported %s (pairing %s, %s): %s",
            interaction.user.id, self.reported_id, self.pairing_id, self.match_type, reasons,
        )
        await interaction.response.send_message(
            "Thanks, your report was sent to the admins.", ephemeral=True
        )


class PersistentReportPlayerButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"prp:(?P<reporter>\d+):(?P<reported>\d+):(?P<pairing>\d+):(?P<mtype>\w*)",
):
    """Report Player button that survives bot restarts.

    The custom id carries who may press it (``reporter``), who they are
    reporting, and the pairing it came from.
    """

    def __init__(self, reporter_id: int, reported_id: int, pairing_id: int = 0, match_type: str = ""):
        self.reporter_id = int(reporter_id)
        self.reported_id = int(reported_id)
        self.pairing_id = int(pairing_id or 0)
        self.match_type = match_type or ""
        super().__init__(
            discord.ui.Button(
                label="Report Player",
                style=discord.ButtonStyle.secondary,
                emoji="🚩",
                custom_id=(
                    f"{REPORT_PLAYER_PREFIX}{self.reporter_id}:{self.reported_id}"
                    f":{self.pairing_id}:{self.match_type}"
                ),
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(
            reporter_id=int(match["reporter"]),
            reported_id=int(match["reported"]),
            pairing_id=int(match["pairing"]),
            match_type=match["mtype"],
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.reporter_id:
            await interaction.response.send_message(
                "This button is for the player this match message was sent to.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(
            PlayerReportModal(
                reported_id=self.reported_id,
                pairing_id=self.pairing_id,
                match_type=self.match_type,
            )
        )


def _as_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def report_player_button(reporter_id, reported_id, pairing_id=None, match_type=None):
    """Build the button for ``reporter_id``'s copy of a match message."""
    match_type = match_type if isinstance(match_type, str) else ""
    return PersistentReportPlayerButton(
        reporter_id, reported_id, _as_int(pairing_id), match_type
    )


def is_report_player_item(item) -> bool:
    return str(getattr(item, "custom_id", "") or "").startswith(REPORT_PLAYER_PREFIX)


def report_player_only_view(message):
    """Return a view holding just the Report Player button from ``message``.

    Used when a match message is edited to show the result, so the other
    buttons go away but Report Player stays. Returns None if the message
    never had one.
    """
    try:
        old = discord.ui.View.from_message(message, timeout=None)
    except Exception:
        return None
    keep = [item for item in old.children if is_report_player_item(item)]
    if not keep:
        return None
    view = discord.ui.View(timeout=None)
    for item in keep:
        item.disabled = False
        view.add_item(item)
    return view
