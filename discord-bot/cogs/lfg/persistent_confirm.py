"""Persistent match confirmation views that survive bot restarts.

Uses discord.py DynamicItem so Confirm/Dispute buttons keep working
even after a deploy or crash.  Confirmation data is stored in SQLite
(pending_confirmations table) and looked up by row-id encoded in the
button's custom_id.
"""

import discord
import datetime
import json
import logging
import sqlite3

import config
from cogs.lfg.state import pending_match_reports, processed_matches
from cogs.lfg.helpers import (
    scrub_urls,
    send_milestone_announcement,
    generate_ladder_challenge_announcement,
)
from utils.database import (
    winner_report,
    update_elo_db,
    mark_pairing_reported,
)
from repositories.limited_repo import mark_limited_pairing_reported
from services.limited_service import limited_winner_report, get_run_summary

logger = logging.getLogger("discord_bot")

DB_PATH = "match_records.db"


# ──────────────────────────────────────────────
#  Validation helpers
# ──────────────────────────────────────────────

def _is_valid_discord_id(value) -> bool:
    """Check if a value is a valid Discord snowflake (numeric string or int).

    Returns False for Google OAuth IDs like 'google_110599992080215394616'.
    """
    try:
        int(value)
        return True
    except (ValueError, TypeError):
        return False


# ──────────────────────────────────────────────
#  Database helpers
# ──────────────────────────────────────────────

def ensure_pending_confirmations_table():
    """Create the pending_confirmations table if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pending_confirmations (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            reporter_id       INTEGER NOT NULL,
            opponent_id       INTEGER NOT NULL,
            winner_id         INTEGER NOT NULL,
            winner_global     TEXT    NOT NULL,
            loser_id          INTEGER NOT NULL,
            loser_global      TEXT    NOT NULL,
            is_winner         INTEGER NOT NULL,
            reporter_global   TEXT,
            opponent_global   TEXT,
            match_start_time  TEXT,
            first_player      TEXT    DEFAULT 'n',
            match_time        INTEGER DEFAULT 0,
            match_comment     TEXT    DEFAULT '',
            winner_deck_url   TEXT,
            loser_deck_url    TEXT,
            ladder_info_json  TEXT,
            match_type        TEXT    DEFAULT 'ranked',
            guild_id          INTEGER,
            winner_run_id     INTEGER,
            loser_run_id      INTEGER,
            created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


def save_pending_confirmation(data: dict) -> int:
    """Persist confirmation data and return the new row id."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    match_start = None
    ms = data.get("match_start_time")
    if ms:
        match_start = ms.isoformat() if isinstance(ms, datetime.datetime) else str(ms)

    cursor.execute(
        """
        INSERT INTO pending_confirmations (
            reporter_id, opponent_id, winner_id, winner_global,
            loser_id, loser_global, is_winner, reporter_global,
            opponent_global, match_start_time, first_player,
            match_time, match_comment, winner_deck_url, loser_deck_url,
            ladder_info_json, match_type, guild_id,
            winner_run_id, loser_run_id
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            data["reporter_id"],
            data["opponent_id"],
            data["winner_id"],
            data["winner_global"],
            data["loser_id"],
            data["loser_global"],
            1 if data.get("is_winner") else 0,
            data.get("reporter_global"),
            data.get("opponent_global"),
            match_start,
            data.get("first_player", "n"),
            data.get("match_time", 0),
            data.get("match_comment", ""),
            data.get("winner_deck_url"),
            data.get("loser_deck_url"),
            json.dumps(data.get("ladder_info")) if data.get("ladder_info") else None,
            data.get("match_type", "ranked"),
            data.get("guild_id"),
            data.get("winner_run_id"),
            data.get("loser_run_id"),
        ),
    )
    confirmation_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return confirmation_id


def load_pending_confirmation(confirmation_id: int):
    """Return confirmation dict or None."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pending_confirmations WHERE id = ?", (confirmation_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None

    data = dict(row)
    data["is_winner"] = bool(data["is_winner"])

    if data.get("ladder_info_json"):
        data["ladder_info"] = json.loads(data["ladder_info_json"])
    else:
        data["ladder_info"] = None

    if data.get("match_start_time"):
        try:
            data["match_start_time"] = datetime.datetime.fromisoformat(data["match_start_time"])
        except (ValueError, TypeError):
            data["match_start_time"] = None
    else:
        data["match_start_time"] = None

    return data


def delete_pending_confirmation(confirmation_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM pending_confirmations WHERE id = ?", (confirmation_id,))
    conn.commit()
    conn.close()


def update_confirmation_deck_url(confirmation_id: int, is_winner_deck: bool, deck_url: str):
    col = "winner_deck_url" if is_winner_deck else "loser_deck_url"
    conn = sqlite3.connect(DB_PATH)
    conn.execute(f"UPDATE pending_confirmations SET {col} = ? WHERE id = ?", (deck_url, confirmation_id))
    conn.commit()
    conn.close()


# ──────────────────────────────────────────────
#  Shared confirmation / dispute logic
# ──────────────────────────────────────────────

async def _execute_match_confirmation(interaction: discord.Interaction, confirmation_id: int, data: dict, *, interaction_valid: bool = True):
    """Run the full confirm-and-record flow (called after defer).

    If interaction_valid is False, skips all interaction.followup/message.edit
    calls since the webhook is dead (expired interaction).
    """
    # Lazy import to avoid circular dependency
    from cogs.lfg.match_reporting import _apply_ladder_elo

    bot = interaction.client

    # ── duplicate guard ──
    match_key = frozenset({data["winner_id"], data["loser_id"]})
    now = datetime.datetime.now()
    if match_key in processed_matches:
        last_report_time = processed_matches[match_key]
        if (now - last_report_time).total_seconds() < 300:
            if interaction_valid:
                try:
                    await interaction.followup.send(
                        "This match has already been recorded. Duplicate report prevented.",
                        ephemeral=True,
                    )
                except Exception:
                    pass
                try:
                    await interaction.message.edit(
                        content="Match already recorded (duplicate prevented).", view=None
                    )
                except Exception:
                    pass
            delete_pending_confirmation(confirmation_id)
            return

    processed_matches[match_key] = now

    # ── match time ──
    match_time = data.get("match_time", 0)
    if match_time == 0 and data.get("match_start_time"):
        time_diff = datetime.datetime.now() - data["match_start_time"]
        match_time = int(time_diff.total_seconds() / 60)

    # ── deck URLs ──
    winner_deck = data.get("winner_deck_url") or "No URL provided"
    loser_deck = data.get("loser_deck_url") or "No URL provided"
    combined_comment = f"Winner deck: {winner_deck} | Loser deck: {loser_deck}"
    if data.get("match_comment"):
        combined_comment = f"{data['match_comment']} | {combined_comment}"

    # ── first player ──
    reporter_went_first = data.get("first_player") and "y" in str(data["first_player"]).lower()
    reporter_is_winner = data["reporter_id"] == data["winner_id"]
    if reporter_is_winner:
        winner_went_first = "y" if reporter_went_first else "n"
        loser_went_first = "n" if reporter_went_first else "y"
    else:
        winner_went_first = "n" if reporter_went_first else "y"
        loser_went_first = "y" if reporter_went_first else "n"

    # ── record the match ──
    logger.info(
        f"Recording match confirmation: {data['winner_global']} (ID: {data['winner_id']}) "
        f"vs {data['loser_global']} (ID: {data['loser_id']}), Type: {data.get('match_type', 'ranked')}"
    )

    winner_run_complete = False
    loser_run_complete = False
    stakes_msg = ""
    elo_msg = ""

    if data["match_type"] == "limited":
        try:
            match_id, winner_run_complete, loser_run_complete = limited_winner_report(
                reporter_id=data["reporter_id"],
                winner_id=data["winner_id"],
                winner_display_name=data["winner_global"],
                loser_id=data["loser_id"],
                loser_display_name=data["loser_global"],
                first_player=data.get("first_player", "n"),
                match_time=match_time,
                curiosa_url_winner=winner_deck,
                curiosa_url_loser=loser_deck,
                match_comment=combined_comment,
                winner_went_first=winner_went_first,
                loser_went_first=loser_went_first,
                winner_run_id=data.get("winner_run_id"),
                loser_run_id=data.get("loser_run_id"),
            )
        except Exception as e:
            logger.error(f"Failed to report limited match: {e}", exc_info=True)
            processed_matches.pop(match_key, None)
            await interaction.followup.send(
                f"An error occurred while recording the match. Please try again or contact an admin.\nError: {e}",
                ephemeral=True,
            )
            return
        elo_msg = " *(🎲 Limited match - Limited ELO updated)*"
    else:
        match_id, _, _, event_active = await winner_report(
            data["reporter_id"],
            data["winner_id"],
            data["winner_global"],
            True,
            data["loser_id"],
            data["loser_global"],
            data.get("first_player", "n"),
            match_time,
            winner_deck,
            combined_comment,
            data["winner_id"],
            data["winner_global"],
            winner_deck_url=data.get("winner_deck_url"),
            loser_deck_url=data.get("loser_deck_url"),
            winner_went_first=winner_went_first,
            loser_went_first=loser_went_first,
            match_type=data.get("match_type", "ranked"),
        )

        if data["match_type"] == "testing":
            pass
        elif data.get("ladder_info"):
            stakes_msg = await _apply_ladder_elo(
                bot,
                data["ladder_info"],
                data["winner_id"],
                data["winner_global"],
                data["loser_id"],
                data["loser_global"],
                match_id,
                event_active,
            )
        else:
            update_elo_db(data["loser_id"], data["loser_global"], False, data["winner_id"])

        if data["match_type"] == "testing":
            elo_msg = " *(⭐ Casual match - ELO not affected)*"
        elif not event_active:
            elo_msg = " *(No active event - ELO not affected)*"

    # Log successful match save
    logger.info(
        f"Match #{match_id} successfully saved: {data['winner_global']} defeated {data['loser_global']}"
    )

    # ── update confirmation message ──
    if interaction_valid:
        try:
            await interaction.message.edit(
                content=(
                    f"Match confirmed! **Match ID: #{match_id}** - "
                    f"{data['winner_global']} won against {data['loser_global']}.{elo_msg}{stakes_msg}"
                ),
                view=None,
            )
        except Exception as e:
            logger.warning(f"Could not edit confirmation message: {e}")

        # ── feedback to confirmer ──
        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    f"Match report confirmed and submitted! **Match ID: #{match_id}**\n"
                    f"**Winner:** {data['winner_global']}\n**Loser:** {data['loser_global']}{elo_msg}{stakes_msg}",
                    ephemeral=True,
                )
        except discord.errors.NotFound as e:
            logger.warning(f"Could not send confirmation followup (interaction expired): {e}")
        except Exception as e:
            logger.warning(f"Could not send confirmation followup: {e}")
    else:
        logger.info(f"Interaction expired for confirmation {confirmation_id} — match #{match_id} saved successfully, skipping UI updates")

    # ── notify reporter ──
    try:
        reporter = await bot.fetch_user(data["reporter_id"])
        await reporter.send(
            f"{data['opponent_global']} has confirmed your match report! Match has been recorded.{stakes_msg}"
        )
    except discord.Forbidden:
        match_report_channel = bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
        if match_report_channel:
            await match_report_channel.send(
                scrub_urls(
                    f"<@{data['reporter_id']}> {data['opponent_global']} has confirmed your match report! "
                    f"Match has been recorded.{stakes_msg}"
                )
            )
    except Exception:
        pass

    # ── cleanup in-memory + DB ──
    guild_id = data.get("guild_id")
    pending_match_reports.pop((data["reporter_id"], data["opponent_id"]), None)
    delete_pending_confirmation(confirmation_id)

    # ── mark pairing reported ──
    if data["match_type"] == "limited":
        if guild_id:
            mark_limited_pairing_reported(guild_id, data["winner_id"], data["loser_id"])
    elif guild_id and not data.get("ladder_info"):
        mark_pairing_reported(guild_id, data["winner_id"], data["loser_id"])

    # ── limited run status DMs ──
    if data["match_type"] == "limited":
        for player_id, run_id, run_complete in [
            (data["winner_id"], data.get("winner_run_id"), winner_run_complete),
            (data["loser_id"], data.get("loser_run_id"), loser_run_complete),
        ]:
            if not run_id:
                continue
            try:
                user = await bot.fetch_user(player_id)
                summary = get_run_summary(run_id)
                if run_complete:
                    await user.send(f"🏁 **Arena Run Complete!**\n\n{summary}")
                else:
                    await user.send(
                        f"🎲 **Limited Match Recorded**\n\n{summary}\n\n"
                        f"If you would like to forfeit the run, use `!forfeit`."
                    )
            except discord.Forbidden:
                logger.warning("Could not DM limited run status to user %s", player_id)
            except Exception as e:
                logger.error("Error sending limited run status to %s: %s", player_id, e)

    # ── leaderboard ──
    lfg_cog = bot.get_cog("LFGCog")
    if lfg_cog:
        try:
            await lfg_cog.update_leaderboard()
        except Exception as e:
            logger.error(f"Failed to update leaderboard: {e}")

    # ── ladder announcement ──
    if data.get("ladder_info") and lfg_cog:
        try:
            lfg_channel = bot.get_channel(lfg_cog.lfg_channel_id)
            if lfg_channel:
                challenger_id = data["ladder_info"].get("challenger_id")
                underdog_won = data["winner_id"] != challenger_id
                winner_mult = data["ladder_info"].get("elo_multiplier_winner", 1.0)
                loser_mult = data["ladder_info"].get("elo_multiplier_loser", 1.0)
                stakes_text = (
                    f"{winner_mult}x/{loser_mult}x"
                    if winner_mult != 1.0 or loser_mult != 1.0
                    else "Normal"
                )
                announcement = generate_ladder_challenge_announcement(
                    underdog_won=underdog_won,
                    winner_name=data["winner_global"],
                    loser_name=data["loser_global"],
                    stakes_multiplier=stakes_text,
                )
                announcement = announcement.replace("WINNER", f"<@{data['winner_id']}>")
                announcement = announcement.replace("LOSER", f"<@{data['loser_id']}>")
                await lfg_channel.send(
                    announcement + " Top 16: use `!issue_challenge` for special stakes!"
                )
        except Exception as e:
            logger.error(f"Failed to send ladder challenge announcement: {e}", exc_info=True)

    # ── milestone ──
    try:
        await send_milestone_announcement(bot, data["winner_id"], data["loser_id"], match_id)
    except Exception as e:
        logger.error(f"Failed to send milestone announcement: {e}", exc_info=True)


async def _execute_match_dispute(interaction: discord.Interaction, confirmation_id: int, data: dict):
    """Process a dispute."""
    bot = interaction.client

    await interaction.response.send_message(
        f"You have disputed the match report. This dispute will not log an entry.\n\n"
        f"To submit a corrected report, use `!challenge @{data['reporter_global']}` to trigger a new report.",
        ephemeral=True,
    )

    try:
        await interaction.message.edit(
            content=(
                f"Match report disputed by {data['opponent_global']}. No entry was logged.\n\n"
                f"To submit a corrected report, use `!challenge @opponent` to trigger a new report."
            ),
            view=None,
        )
    except Exception:
        pass

    # notify reporter
    try:
        reporter = await bot.fetch_user(data["reporter_id"])
        await reporter.send(
            f"{data['opponent_global']} has disputed your match report. The dispute did not log an entry.\n\n"
            f"To submit a corrected report, use `!challenge @{data['opponent_global']}` to trigger a new report."
        )
    except discord.Forbidden:
        match_report_channel = bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
        if match_report_channel:
            await match_report_channel.send(
                scrub_urls(
                    f"<@{data['reporter_id']}> {data['opponent_global']} has disputed your match report. "
                    f"The dispute did not log an entry.\n\n"
                    f"To submit a corrected report, use `!challenge @{data['opponent_global']}` to trigger a new report."
                )
            )
    except Exception:
        pass

    pending_match_reports.pop((data["reporter_id"], data["opponent_id"]), None)
    delete_pending_confirmation(confirmation_id)


# ──────────────────────────────────────────────
#  DynamicItem buttons  (survive bot restarts)
# ──────────────────────────────────────────────

class PersistentConfirmButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"pconfirm:(?P<id>\d+)",
):
    def __init__(self, confirmation_id: int):
        super().__init__(
            discord.ui.Button(
                label="Confirm",
                style=discord.ButtonStyle.success,
                custom_id=f"pconfirm:{confirmation_id}",
            )
        )
        self.confirmation_id = confirmation_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(confirmation_id=int(match["id"]))

    async def callback(self, interaction: discord.Interaction):
        try:
            data = load_pending_confirmation(self.confirmation_id)
            if not data:
                await interaction.response.send_message(
                    "This match confirmation has expired or was already processed.",
                    ephemeral=True,
                )
                return

            # If confirmer still needs a deck URL, show the modal
            confirmer_deck_url = data["winner_deck_url"] if data["is_winner"] else data["loser_deck_url"]
            if not confirmer_deck_url and data.get("match_type") != "testing":
                modal = PersistentConfirmDeckModal(self.confirmation_id, data["is_winner"])
                await interaction.response.send_modal(modal)
                return

            # Try to defer, but handle expired interactions gracefully
            interaction_valid = True
            try:
                await interaction.response.defer()
            except discord.errors.NotFound:
                # Interaction expired (>15 minutes old) - still process the confirmation
                logger.warning(f"Interaction expired for confirmation {self.confirmation_id}, processing match without UI feedback")
                interaction_valid = False

            # Disable buttons (only if interaction is valid)
            if interaction_valid and self.view:
                for child in self.view.children:
                    child.disabled = True
                try:
                    await interaction.message.edit(view=self.view)
                except Exception:
                    pass

            # Execute the confirmation (this saves the match and updates ELO)
            await _execute_match_confirmation(interaction, self.confirmation_id, data, interaction_valid=interaction_valid)
        except Exception as e:
            logger.error(f"Error in PersistentConfirmButton: {e}", exc_info=True)
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(
                        "An error occurred while confirming. Please try again or contact an admin.",
                        ephemeral=True,
                    )
                else:
                    await interaction.response.send_message(
                        "An error occurred while confirming. Please try again or contact an admin.",
                        ephemeral=True,
                    )
            except Exception:
                pass


class PersistentDisputeButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"pdispute:(?P<id>\d+)",
):
    def __init__(self, confirmation_id: int):
        super().__init__(
            discord.ui.Button(
                label="Dispute",
                style=discord.ButtonStyle.danger,
                custom_id=f"pdispute:{confirmation_id}",
            )
        )
        self.confirmation_id = confirmation_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(confirmation_id=int(match["id"]))

    async def callback(self, interaction: discord.Interaction):
        try:
            data = load_pending_confirmation(self.confirmation_id)
            if not data:
                await interaction.response.send_message(
                    "This match confirmation has expired or was already processed.",
                    ephemeral=True,
                )
                return

            await _execute_match_dispute(interaction, self.confirmation_id, data)

        except Exception as e:
            logger.error(f"Error in PersistentDisputeButton: {e}", exc_info=True)
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(
                        "An error occurred while disputing. Please try again or contact an admin.",
                        ephemeral=True,
                    )
                else:
                    await interaction.response.send_message(
                        "An error occurred while disputing. Please try again or contact an admin.",
                        ephemeral=True,
                    )
            except Exception:
                pass


# ──────────────────────────────────────────────
#  Modal for deck URL during confirm
# ──────────────────────────────────────────────

class PersistentConfirmDeckModal(discord.ui.Modal, title="Enter Your Deck"):
    deck_url = discord.ui.TextInput(
        label="Curiosa Deck URL",
        placeholder="https://curiosa.io/decks/...",
        required=True,
    )

    def __init__(self, confirmation_id: int, is_winner: bool):
        super().__init__()
        self.confirmation_id = confirmation_id
        self.is_winner = is_winner

    async def on_submit(self, interaction: discord.Interaction):
        try:
            logger.info(f"Processing deck URL modal submission for confirmation {self.confirmation_id}")

            deck_url = self.deck_url.value.strip() if self.deck_url.value else None

            if deck_url:
                update_confirmation_deck_url(self.confirmation_id, self.is_winner, deck_url)
                logger.info(f"Updated deck URL for confirmation {self.confirmation_id}")

            data = load_pending_confirmation(self.confirmation_id)
            if not data:
                await interaction.response.send_message(
                    "This match confirmation has expired or was already processed.",
                    ephemeral=True,
                )
                return

            await interaction.response.defer()

            # Try to disable buttons on the original message
            try:
                if interaction.message:
                    await interaction.message.edit(view=None)
            except Exception as edit_error:
                logger.warning(f"Could not edit message to disable buttons: {edit_error}")

            await _execute_match_confirmation(interaction, self.confirmation_id, data)

        except Exception as e:
            logger.error(f"Unexpected error in PersistentConfirmDeckModal: {e}", exc_info=True)
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(
                        "An unexpected error occurred while processing your confirmation. Please try again.",
                        ephemeral=True,
                    )
                else:
                    await interaction.response.send_message(
                        "An unexpected error occurred while processing your confirmation. Please try again.",
                        ephemeral=True,
                    )
            except Exception:
                logger.error("Failed to send error message to user")


# ──────────────────────────────────────────────
#  View  +  helper to create one
# ──────────────────────────────────────────────

class PersistentMatchConfirmView(discord.ui.View):
    """Confirm / Dispute view whose buttons survive bot restarts."""

    def __init__(self, confirmation_id: int):
        super().__init__(timeout=None)
        self.add_item(PersistentConfirmButton(confirmation_id))
        self.add_item(PersistentDisputeButton(confirmation_id))


def create_confirmation_view(
    *,
    reporter_id,
    reporter_global,
    opponent_id,
    opponent_global,
    winner_id,
    winner_global,
    loser_id,
    loser_global,
    is_winner,
    match_start_time=None,
    first_player="n",
    match_time=0,
    match_comment="",
    winner_deck_url=None,
    loser_deck_url=None,
    ladder_info=None,
    match_type="ranked",
    guild_id=None,
    winner_run_id=None,
    loser_run_id=None,
) -> PersistentMatchConfirmView:
    """Persist confirmation data and return a view that works across restarts."""
    # Validate that reporter_id and opponent_id are valid Discord snowflakes
    # This prevents Google OAuth IDs from causing crashes in background jobs
    if not _is_valid_discord_id(reporter_id):
        logger.warning(
            f"create_confirmation_view called with invalid reporter_id '{reporter_id}' "
            f"(reporter: {reporter_global}, opponent: {opponent_global}). "
            f"This likely indicates a web app user without a linked Discord account."
        )
        # Still create the view, but background jobs will skip invalid IDs

    if not _is_valid_discord_id(opponent_id):
        logger.warning(
            f"create_confirmation_view called with invalid opponent_id '{opponent_id}' "
            f"(reporter: {reporter_global}, opponent: {opponent_global}). "
            f"This likely indicates a web app user without a linked Discord account."
        )
        # Still create the view, but background jobs will skip invalid IDs

    data = {
        "reporter_id": reporter_id,
        "opponent_id": opponent_id,
        "winner_id": winner_id,
        "winner_global": winner_global,
        "loser_id": loser_id,
        "loser_global": loser_global,
        "is_winner": is_winner,
        "reporter_global": reporter_global,
        "opponent_global": opponent_global,
        "match_start_time": match_start_time,
        "first_player": first_player,
        "match_time": match_time,
        "match_comment": match_comment,
        "winner_deck_url": winner_deck_url,
        "loser_deck_url": loser_deck_url,
        "ladder_info": ladder_info,
        "match_type": match_type,
        "guild_id": guild_id,
        "winner_run_id": winner_run_id,
        "loser_run_id": loser_run_id,
    }
    confirmation_id = save_pending_confirmation(data)
    return PersistentMatchConfirmView(confirmation_id)
