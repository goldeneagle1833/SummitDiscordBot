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
from cogs.lfg.state import pending_match_reports, processed_matches, processed_matches_lock
from cogs.lfg.helpers import (
    scrub_urls,
    send_milestone_announcement,
    generate_ladder_challenge_announcement,
)
from utils.database import (
    record_match,
    mark_pairing_reported,
    get_active_event,
)
from repositories.elo_repo import NON_ELO_MATCH_TYPES
from services.dust_service import try_dust_drop, try_alter_card_drop
from repositories.dust_repo import get_available_code_count
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
            winner_avatar     TEXT,
            loser_avatar      TEXT,
            ladder_info_json  TEXT,
            match_type        TEXT    DEFAULT 'ranked',
            guild_id          INTEGER,
            winner_run_id     INTEGER,
            loser_run_id      INTEGER,
            confirmer_comment TEXT    DEFAULT '',
            created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # Migrate: add confirmer_comment if missing (table may predate this column)
    cursor = conn.execute("PRAGMA table_info(pending_confirmations)")
    columns = {row[1] for row in cursor.fetchall()}
    if "confirmer_comment" not in columns:
        conn.execute("ALTER TABLE pending_confirmations ADD COLUMN confirmer_comment TEXT DEFAULT ''")
    if "winner_avatar" not in columns:
        conn.execute("ALTER TABLE pending_confirmations ADD COLUMN winner_avatar TEXT")
    if "loser_avatar" not in columns:
        conn.execute("ALTER TABLE pending_confirmations ADD COLUMN loser_avatar TEXT")

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
            winner_avatar, loser_avatar, ladder_info_json, match_type, guild_id,
            winner_run_id, loser_run_id
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
            data.get("winner_avatar"),
            data.get("loser_avatar"),
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


def update_confirmation_confirmer_comment(confirmation_id: int, comment: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE pending_confirmations SET confirmer_comment = ? WHERE id = ?", (comment, confirmation_id))
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

    # ── duplicate guard (atomic check-and-set under lock) ──
    match_key = frozenset({data["winner_id"], data["loser_id"]})
    now = datetime.datetime.now()
    async with processed_matches_lock:
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

    # Merge reporter + confirmer comments
    reporter_comment = (data.get("match_comment") or "").strip()
    confirmer_comment = (data.get("confirmer_comment") or "").strip()
    if reporter_comment and confirmer_comment:
        combined_comment = f"{reporter_comment} | Opponent: {confirmer_comment} | {combined_comment}"
    elif reporter_comment:
        combined_comment = f"{reporter_comment} | {combined_comment}"
    elif confirmer_comment:
        combined_comment = f"Opponent: {confirmer_comment} | {combined_comment}"

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
            match_id, winner_run_complete, loser_run_complete, winner_elo_change, loser_elo_change = limited_winner_report(
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
        # Determine ELO multipliers upfront for ladder matches
        elo_multiplier_winner = 1.0
        elo_multiplier_loser = 1.0
        ladder_info = data.get("ladder_info")
        if ladder_info and data.get("match_type") not in (*NON_ELO_MATCH_TYPES, "limited"):
            challenger_id = ladder_info["challenger_id"]
            if data["winner_id"] != challenger_id:
                # Non-Top16 player won — apply stakes multipliers
                elo_multiplier_winner = ladder_info.get("elo_multiplier_winner", 1.0)
                elo_multiplier_loser = ladder_info.get("elo_multiplier_loser", 1.0)

        match_id, _, _, _, _, event_active = await record_match(
            reporter_id=data["reporter_id"],
            winner_id=data["winner_id"],
            winner_global=data["winner_global"],
            loser_id=data["loser_id"],
            loser_global=data["loser_global"],
            first_player=data.get("first_player", "n"),
            match_time=match_time,
            match_comment=combined_comment,
            winner_deck_url=data.get("winner_deck_url"),
            loser_deck_url=data.get("loser_deck_url"),
            winner_went_first=winner_went_first,
            loser_went_first=loser_went_first,
            match_type=data.get("match_type", "ranked"),
            elo_multiplier_winner=elo_multiplier_winner,
            elo_multiplier_loser=elo_multiplier_loser,
            winner_avatar=data.get("winner_avatar"),
            loser_avatar=data.get("loser_avatar"),
        )

        if ladder_info and data["match_type"] not in NON_ELO_MATCH_TYPES:
            stakes_msg = await _apply_ladder_elo(
                bot,
                ladder_info,
                data["winner_id"],
                data["winner_global"],
                data["loser_id"],
                data["loser_global"],
                match_id,
                event_active,
            )

        if data["match_type"] == "rumble":
            from utils.rumble_bones import award_match_bones
            win_bones, loss_bones = award_match_bones(
                data["winner_id"], data["winner_global"],
                data["loser_id"], data["loser_global"],
            )
            if win_bones or loss_bones:
                elo_msg = f" *(Rumble - {data['winner_global']} +{win_bones} bones, {data['loser_global']} +{loss_bones} bones)*"
            else:
                elo_msg = " *(Rumble match - ELO not affected)*"
        elif data["match_type"] == "points":
            elo_msg = " *(Omens match - ELO not affected)*"
        elif data["match_type"] in ("testing",):
            elo_msg = " *(Casual match - ELO not affected)*"
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
    correct_match_tip = (
        "\n\n**Tip:** If the result was reported incorrectly, use `!correct_match` "
        "in <#1456299008023728302> on the Summit server to request a correction."
    )
    try:
        reporter = await bot.fetch_user(data["reporter_id"])
        await reporter.send(
            f"{data['opponent_global']} has confirmed your match report! Match has been recorded.{stakes_msg}{correct_match_tip}"
        )
    except discord.Forbidden:
        match_report_channel = bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
        if match_report_channel:
            await match_report_channel.send(
                scrub_urls(
                    f"<@{data['reporter_id']}> {data['opponent_global']} has confirmed your match report! "
                    f"Match has been recorded.{stakes_msg}{correct_match_tip}"
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
    elif guild_id:
        mark_pairing_reported(guild_id, data["winner_id"], data["loser_id"])

    # ── limited run status DMs ──
    if data["match_type"] == "limited":
        for player_id, run_id, run_complete, match_elo_change in [
            (data["winner_id"], data.get("winner_run_id"), winner_run_complete, winner_elo_change),
            (data["loser_id"], data.get("loser_run_id"), loser_run_complete, loser_elo_change),
        ]:
            if not run_id:
                continue
            try:
                user = await bot.fetch_user(player_id)
                summary = get_run_summary(run_id, last_match_elo_change=match_elo_change)
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

        if data["match_type"] == "limited":
            try:
                await lfg_cog.update_limited_leaderboard()
            except Exception as e:
                logger.error(f"Failed to update limited leaderboard: {e}")

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
                embed = discord.Embed(
                    title="Ladder Challenge Result",
                    description=announcement,
                    color=discord.Color.orange(),
                )
                embed.add_field(
                    name="ELO Stakes", value=stakes_text, inline=True,
                )
                embed.set_footer(text="Top 16: use !issue_challenge for special stakes!")
                await lfg_channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed to send ladder challenge announcement: {e}", exc_info=True)

    # ── milestone ──
    try:
        await send_milestone_announcement(bot, data["winner_id"], data["loser_id"], match_id)
    except Exception as e:
        logger.error(f"Failed to send milestone announcement: {e}", exc_info=True)

    # ── dust code drop ──
    try:
        event = get_active_event()
        season_name = event["event_name"] if event else "no_season"
        result = try_dust_drop(
            data["winner_id"], data["winner_global"],
            data["loser_id"], data["loser_global"],
            season_name,
        )
        if result:
            winner_id, winner_name, code = result
            # DM the winner
            dm_sent = False
            try:
                winner_user = await bot.fetch_user(winner_id)
                await winner_user.send(
                    f"**You won a Dust Code!**\n\n"
                    f"Here is your code: `{code}`\n\n"
                    f"Redeem it for 100 Dust reward points. Enjoy!"
                )
                dm_sent = True
            except discord.Forbidden:
                logger.warning(f"Could not DM dust code to {winner_name} ({winner_id})")
            except Exception as e:
                logger.error(f"Error DMing dust code to {winner_name}: {e}")

            # Announce in LFG channel
            lfg_channel = bot.get_channel(config.LFG_CHANNEL_ID)
            if lfg_channel:
                embed = discord.Embed(
                    title="Dust Code Drop!",
                    color=discord.Color.green(),
                )
                if dm_sent:
                    embed.description = (
                        f"<@{winner_id}> just won a **Dust Code**!\n\n"
                        f"DM the bot with `!donatedust 11111 22222 33333 44444` "
                        f"if you'd like to donate a code."
                    )
                else:
                    embed.description = (
                        f"<@{winner_id}> just won a **Dust Code**!\n"
                        f"Please contact an admin to receive your code.\n\n"
                        f"DM the bot with `!donatedust 11111 22222 33333 44444` "
                        f"if you'd like to donate a code."
                    )
                embed.set_footer(text="Sorcery: Contested Realm")
                await lfg_channel.send(embed=embed)

            # Check if codes ran out
            if get_available_code_count() == 0:
                try:
                    owner = await bot.fetch_user(config.OWNER_ID)
                    await owner.send(
                        "**Dust Code Alert:** All dust codes have been claimed or given out. "
                        "No more codes are available for drops."
                    )
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"Error in dust code drop: {e}", exc_info=True)

    # ── alter card drop ──
    try:
        alter_result = try_alter_card_drop(
            data["winner_id"], data["winner_global"],
            data["loser_id"], data["loser_global"],
        )
        if alter_result:
            alter_winner_id, alter_winner_name, alter_description = alter_result

            # DM the owner
            try:
                owner = await bot.fetch_user(config.OWNER_ID)
                await owner.send(
                    f"**Alter Card Won!**\n\n"
                    f"**Winner:** {alter_winner_name} (<@{alter_winner_id}>)\n"
                    f"**Prize:** {alter_description}"
                )
            except Exception as e:
                logger.error(f"Could not DM owner about alter card win: {e}")

            # Announce in LFG channel
            lfg_channel = bot.get_channel(config.LFG_CHANNEL_ID)
            if lfg_channel:
                embed = discord.Embed(
                    title="Alter Card Won!",
                    description=(
                        f"<@{alter_winner_id}> just won an **Alter Card**!\n\n"
                        f"Congratulations! Contact an admin to claim your prize."
                    ),
                    color=discord.Color.purple(),
                )
                embed.set_footer(text="Sorcery: Contested Realm")
                await lfg_channel.send(embed=embed)
    except Exception as e:
        logger.error(f"Error in alter card drop: {e}", exc_info=True)


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
                try:
                    await interaction.response.send_message(
                        "This match confirmation has expired or was already processed.",
                        ephemeral=True,
                    )
                except discord.errors.NotFound:
                    pass
                return

            # If confirmer still needs a deck URL, show the deck+comment modal
            confirmer_deck_url = data["winner_deck_url"] if data["is_winner"] else data["loser_deck_url"]
            if not confirmer_deck_url and data.get("match_type") not in ("testing", "rumble", "limited"):
                modal = PersistentConfirmDeckModal(self.confirmation_id, data["is_winner"])
                try:
                    await interaction.response.send_modal(modal)
                except discord.errors.NotFound:
                    pass
                return

            # Confirmer already has a deck URL — show comment-only modal
            if data.get("match_type") not in ("testing", "rumble", "limited"):
                modal = PersistentConfirmCommentModal(self.confirmation_id)
                try:
                    await interaction.response.send_modal(modal)
                except discord.errors.NotFound:
                    pass
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

    match_comment = discord.ui.TextInput(
        label="Match Comments",
        placeholder="Any notes about the match? (optional)",
        style=discord.TextStyle.paragraph,
        required=False,
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

            comment = self.match_comment.value.strip() if self.match_comment.value else ""
            if comment:
                update_confirmation_confirmer_comment(self.confirmation_id, comment)
                logger.info(f"Updated confirmer comment for confirmation {self.confirmation_id}")

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
            error_detail = str(e) if str(e) else type(e).__name__
            try:
                msg = f"An error occurred while processing your confirmation: {error_detail}\nPlease try again or contact an admin."
                if interaction.response.is_done():
                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    await interaction.response.send_message(msg, ephemeral=True)
            except Exception:
                logger.error("Failed to send error message to user")


class PersistentConfirmCommentModal(discord.ui.Modal, title="Confirm Match"):
    """Comment-only modal shown when the confirmer already has a deck URL."""

    match_comment = discord.ui.TextInput(
        label="Match Comments (optional)",
        placeholder="Any notes about the match?",
        style=discord.TextStyle.paragraph,
        required=False,
    )

    def __init__(self, confirmation_id: int):
        super().__init__()
        self.confirmation_id = confirmation_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            comment = self.match_comment.value.strip() if self.match_comment.value else ""
            if comment:
                update_confirmation_confirmer_comment(self.confirmation_id, comment)
                logger.info(f"Updated confirmer comment for confirmation {self.confirmation_id}")

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
            logger.error(f"Unexpected error in PersistentConfirmCommentModal: {e}", exc_info=True)
            error_detail = str(e) if str(e) else type(e).__name__
            try:
                msg = f"An error occurred while processing your confirmation: {error_detail}\nPlease try again or contact an admin."
                if interaction.response.is_done():
                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    await interaction.response.send_message(msg, ephemeral=True)
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
    winner_avatar=None,
    loser_avatar=None,
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
        "winner_avatar": winner_avatar,
        "loser_avatar": loser_avatar,
        "ladder_info": ladder_info,
        "match_type": match_type,
        "guild_id": guild_id,
        "winner_run_id": winner_run_id,
        "loser_run_id": loser_run_id,
    }
    confirmation_id = save_pending_confirmation(data)
    return PersistentMatchConfirmView(confirmation_id)


# ──────────────────────────────────────────────
#  Match Correction Confirmation (non-admin flow)
# ──────────────────────────────────────────────

def ensure_pending_corrections_table():
    """Create the pending_corrections table if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pending_corrections (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id        INTEGER NOT NULL,
            requester_id    INTEGER NOT NULL,
            requester_name  TEXT    NOT NULL,
            other_player_id INTEGER NOT NULL,
            other_player_name TEXT  NOT NULL,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


def save_pending_correction(data: dict) -> int:
    """Persist correction request and return the new row id."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO pending_corrections (
            match_id, requester_id, requester_name,
            other_player_id, other_player_name
        ) VALUES (?,?,?,?,?)
        """,
        (
            data["match_id"],
            data["requester_id"],
            data["requester_name"],
            data["other_player_id"],
            data["other_player_name"],
        ),
    )
    correction_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return correction_id


def load_pending_correction(correction_id: int):
    """Return correction dict or None."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pending_corrections WHERE id = ?", (correction_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)


def delete_pending_correction(correction_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM pending_corrections WHERE id = ?", (correction_id,))
    conn.commit()
    conn.close()


class PersistentCorrectionConfirmButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"pcorrect_confirm:(?P<id>\d+)",
):
    def __init__(self, correction_id: int):
        super().__init__(
            discord.ui.Button(
                label="Confirm Correction",
                style=discord.ButtonStyle.success,
                custom_id=f"pcorrect_confirm:{correction_id}",
            )
        )
        self.correction_id = correction_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(correction_id=int(match["id"]))

    async def callback(self, interaction: discord.Interaction):
        from utils.database import correct_match_record, log_admin_action

        try:
            data = load_pending_correction(self.correction_id)
            if not data:
                await interaction.response.send_message(
                    "This correction request has expired or was already processed.",
                    ephemeral=True,
                )
                return

            # Only the other player can confirm
            if interaction.user.id != data["other_player_id"]:
                await interaction.response.send_message(
                    "Only the other player in this match can confirm this correction.",
                    ephemeral=True,
                )
                return

            await interaction.response.defer()

            # Execute the correction
            result = correct_match_record(data["match_id"])

            success_embed = discord.Embed(
                title="Match Corrected",
                description=(
                    f"**Match ID:** #{data['match_id']}\n\n"
                    f"**Original Result:**\n"
                    f"~~Winner: {result['original_winner_name']}~~\n"
                    f"~~Loser: {result['original_loser_name']}~~\n\n"
                    f"**Corrected Result:**\n"
                    f"Winner: **{result['new_winner_name']}** ({result['new_winner_elo_change']:+d} ELO)\n"
                    f"Loser: **{result['new_loser_name']}** ({result['new_loser_elo_change']:+d} ELO)"
                ),
                color=discord.Color.green(),
            )
            success_embed.add_field(
                name="Cascade Recalculation",
                value=f"Recalculated **{result['recalculated_count']}** subsequent matches\nAffected **{len(result['affected_players'])}** players",
                inline=False,
            )
            success_embed.set_footer(
                text=f"Requested by {data['requester_name']} | Confirmed by {interaction.user.display_name}"
            )

            await interaction.message.edit(embed=success_embed, view=None)

            log_admin_action(
                data["requester_id"],
                data["requester_name"],
                "correct_match",
                target_id=data["match_id"],
                previous_state={
                    "winner_name": result["original_winner_name"],
                    "loser_name": result["original_loser_name"],
                },
                new_state={
                    "winner_name": result["new_winner_name"],
                    "loser_name": result["new_loser_name"],
                    "recalculated_matches": result["recalculated_count"],
                },
                details=f"Corrected match #{data['match_id']} (player request confirmed by {interaction.user.display_name}): winner flipped from {result['original_winner_name']} to {result['new_winner_name']}, {result['recalculated_count']} subsequent matches recalculated",
            )

            # Notify requester
            try:
                requester = await interaction.client.fetch_user(data["requester_id"])
                await requester.send(
                    f"{data['other_player_name']} has confirmed your match correction request for Match #{data['match_id']}. "
                    f"The match has been corrected."
                )
            except Exception:
                pass

            # Update leaderboard
            lfg_cog = interaction.client.get_cog("LFGCog")
            if lfg_cog:
                try:
                    await lfg_cog.update_leaderboard()
                except Exception as e:
                    logger.error(f"Failed to update leaderboard after correction: {e}")

            delete_pending_correction(self.correction_id)

        except ValueError as e:
            await interaction.followup.send(str(e), ephemeral=True)
        except Exception as e:
            logger.error(f"Error in PersistentCorrectionConfirmButton: {e}", exc_info=True)
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(
                        "An error occurred while processing the correction. Please try again or contact an admin.",
                        ephemeral=True,
                    )
                else:
                    await interaction.response.send_message(
                        "An error occurred while processing the correction. Please try again or contact an admin.",
                        ephemeral=True,
                    )
            except Exception:
                pass


class PersistentCorrectionDenyButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"pcorrect_deny:(?P<id>\d+)",
):
    def __init__(self, correction_id: int):
        super().__init__(
            discord.ui.Button(
                label="Deny Correction",
                style=discord.ButtonStyle.danger,
                custom_id=f"pcorrect_deny:{correction_id}",
            )
        )
        self.correction_id = correction_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(correction_id=int(match["id"]))

    async def callback(self, interaction: discord.Interaction):
        try:
            data = load_pending_correction(self.correction_id)
            if not data:
                await interaction.response.send_message(
                    "This correction request has expired or was already processed.",
                    ephemeral=True,
                )
                return

            # Only the other player can deny
            if interaction.user.id != data["other_player_id"]:
                await interaction.response.send_message(
                    "Only the other player in this match can respond to this correction request.",
                    ephemeral=True,
                )
                return

            await interaction.response.send_message(
                "You have denied the match correction request.", ephemeral=True
            )

            await interaction.message.edit(
                content=f"Match correction for Match #{data['match_id']} was denied by {data['other_player_name']}.",
                embed=None,
                view=None,
            )

            # Notify requester
            try:
                requester = await interaction.client.fetch_user(data["requester_id"])
                await requester.send(
                    f"{data['other_player_name']} has denied your match correction request for Match #{data['match_id']}. "
                    f"If you believe this is an error, please contact an admin."
                )
            except Exception:
                pass

            delete_pending_correction(self.correction_id)

        except Exception as e:
            logger.error(f"Error in PersistentCorrectionDenyButton: {e}", exc_info=True)
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(
                        "An error occurred. Please try again or contact an admin.",
                        ephemeral=True,
                    )
                else:
                    await interaction.response.send_message(
                        "An error occurred. Please try again or contact an admin.",
                        ephemeral=True,
                    )
            except Exception:
                pass


class PersistentCorrectionConfirmView(discord.ui.View):
    """Confirm / Deny correction view whose buttons survive bot restarts."""

    def __init__(self, correction_id: int):
        super().__init__(timeout=None)
        self.add_item(PersistentCorrectionConfirmButton(correction_id))
        self.add_item(PersistentCorrectionDenyButton(correction_id))
