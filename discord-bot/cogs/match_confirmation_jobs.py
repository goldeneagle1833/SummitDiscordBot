"""
Match Confirmation Background Jobs Cog

This cog handles scheduled background tasks for match confirmations:
1. 24-hour reminder job - Sends reminders to opponents who haven't confirmed
2. 48-hour expiration job - Auto-confirms expired pending confirmations
"""

import discord
from discord.ext import commands, tasks
import logging
import sqlite3

logger = logging.getLogger("discord_bot.match_confirmation_jobs")


class MatchConfirmationJobs(commands.Cog):
    """Background jobs for match confirmation reminders and expiration."""

    def __init__(self, bot):
        self.bot = bot
        self.db_path = "match_records.db"

        # Start background tasks
        self.reminder_job.start()
        self.expiration_job.start()

        logger.info("Match confirmation background jobs started")

    def cog_unload(self):
        """Stop background tasks when cog is unloaded."""
        self.reminder_job.cancel()
        self.expiration_job.cancel()
        logger.info("Match confirmation background jobs stopped")

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        return sqlite3.connect(self.db_path)

    def _get_confirmations_needing_reminder(self):
        """
        Get confirmations that need 24-hour reminders.

        Returns confirmations where:
        - status is 'pending'
        - reminder_sent_at is NULL
        - created_at is more than 24 hours ago
        - expires_at is still in the future

        Returns:
            list[dict]: List of confirmation records
        """
        import time

        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        current_time = int(time.time())
        twenty_four_hours_ago = current_time - (24 * 60 * 60)

        cursor.execute(
            """
            SELECT * FROM match_confirmations
            WHERE status = 'pending'
              AND reminder_sent_at IS NULL
              AND created_at <= ?
              AND expires_at > ?
            ORDER BY created_at ASC
            """,
            (twenty_four_hours_ago, current_time),
        )

        rows = cursor.fetchall()
        confirmations = [dict(row) for row in rows]

        conn.close()
        return confirmations

    def _get_expired_confirmations(self):
        """
        Get confirmations that have expired.

        Returns confirmations where:
        - status is 'pending'
        - expires_at is in the past

        Returns:
            list[dict]: List of expired confirmation records
        """
        import time

        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        current_time = int(time.time())

        cursor.execute(
            """
            SELECT * FROM match_confirmations
            WHERE status = 'pending'
              AND expires_at <= ?
            ORDER BY expires_at ASC
            """,
            (current_time,),
        )

        rows = cursor.fetchall()
        confirmations = [dict(row) for row in rows]

        conn.close()
        return confirmations

    def _update_reminder_sent(self, confirmation_id: int):
        """Mark that a reminder has been sent."""
        import time

        conn = self._get_connection()
        cursor = conn.cursor()

        reminder_sent_at = int(time.time())

        cursor.execute(
            """
            UPDATE match_confirmations
            SET reminder_sent_at = ?
            WHERE id = ?
            """,
            (reminder_sent_at, confirmation_id),
        )

        conn.commit()
        conn.close()

    def _update_confirmation_status(
        self, confirmation_id: int, status: str, confirmed_at: int = None
    ):
        """Update confirmation status."""
        import time

        if confirmed_at is None:
            confirmed_at = int(time.time())

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE match_confirmations
            SET status = ?, confirmed_at = ?
            WHERE id = ?
            """,
            (status, confirmed_at, confirmation_id),
        )

        conn.commit()
        conn.close()

    def _is_valid_discord_id(self, value) -> bool:
        """Check if a value is a valid Discord snowflake (numeric string or int)."""
        try:
            int(value)
            return True
        except (ValueError, TypeError):
            return False

    async def _send_reminder_dm(self, confirmation: dict):
        """
        Send a Discord DM reminder to the opponent.

        Args:
            confirmation: Confirmation record dict
        """
        opponent_id = confirmation["opponent_discord_id"]
        submitter_id = confirmation["submitter_discord_id"]
        confirmation_id = confirmation["id"]

        if not self._is_valid_discord_id(opponent_id):
            logger.warning(f"Skipping reminder for confirmation {confirmation_id}: invalid opponent_id '{opponent_id}'")
            return

        try:
            # Get opponent user
            opponent = await self.bot.fetch_user(int(opponent_id))

            if not opponent:
                logger.warning(f"Could not find opponent user: {opponent_id}")
                return

            # Get submitter user (for display name)
            try:
                if self._is_valid_discord_id(submitter_id):
                    submitter = await self.bot.fetch_user(int(submitter_id))
                    submitter_name = submitter.display_name if submitter else f"User {submitter_id}"
                else:
                    submitter_name = f"User {submitter_id}"
            except Exception:
                submitter_name = f"User {submitter_id}"

            # Determine result text
            you_won = confirmation["winner_discord_id"] == opponent_id
            result_text = "you won" if you_won else "you lost"

            # Build reminder message
            embed = discord.Embed(
                title="⏰ Match Confirmation Reminder",
                description=f"{submitter_name} reported a match where {result_text}.",
                color=discord.Color.orange()
            )

            embed.add_field(
                name="Final Life",
                value=f"Winner: {confirmation['final_life_winner']} | Loser: {confirmation['final_life_loser']}",
                inline=False
            )

            embed.add_field(
                name="Action Required",
                value="Please confirm or deny this match report on the web app within 24 hours.",
                inline=False
            )

            embed.add_field(
                name="Expires",
                value="In approximately 24 hours (48 hours from submission)",
                inline=False
            )

            embed.set_footer(text=f"Confirmation ID: {confirmation_id}")

            # Send DM
            await opponent.send(embed=embed)

            logger.info(f"Sent reminder DM: confirmation_id={confirmation_id}, opponent={opponent_id}")

        except discord.Forbidden:
            logger.warning(f"Could not send DM to user {opponent_id} (DMs disabled)")
        except Exception as e:
            logger.error(f"Error sending reminder DM: {e}", exc_info=True)

    async def _send_expiration_notification(self, confirmation: dict, status: str):
        """
        Send Discord DM notifications about expired confirmation.

        Args:
            confirmation: Confirmation record dict
            status: 'auto_confirmed' or 'expired'
        """
        submitter_id = confirmation["submitter_discord_id"]
        opponent_id = confirmation["opponent_discord_id"]
        confirmation_id = confirmation["id"]

        # Skip if either ID is not a valid Discord snowflake (e.g. Google OAuth IDs)
        if not self._is_valid_discord_id(submitter_id) or not self._is_valid_discord_id(opponent_id):
            logger.warning(f"Skipping expiration notification for confirmation {confirmation_id}: invalid discord IDs (submitter='{submitter_id}', opponent='{opponent_id}')")
            return

        # Determine result
        you_won = confirmation["winner_discord_id"] == submitter_id
        result_text = "You won" if you_won else "You lost"

        try:
            # Get both users
            submitter = await self.bot.fetch_user(int(submitter_id))
            opponent = await self.bot.fetch_user(int(opponent_id))

            submitter_name = submitter.display_name if submitter else f"User {submitter_id}"
            opponent_name = opponent.display_name if opponent else f"User {opponent_id}"

            # Message for submitter
            if status == "auto_confirmed":
                submitter_embed = discord.Embed(
                    title="✅ Match Auto-Confirmed",
                    description=f"Your match report against {opponent_name} has been automatically confirmed (48-hour timeout).",
                    color=discord.Color.green()
                )
                submitter_embed.add_field(
                    name="Result",
                    value=result_text,
                    inline=False
                )
                submitter_embed.add_field(
                    name="ELO Update",
                    value="Your rating will be updated shortly.",
                    inline=False
                )
            else:  # expired
                submitter_embed = discord.Embed(
                    title="⏱️ Match Report Expired",
                    description=f"Your match report against {opponent_name} has expired (48-hour timeout).",
                    color=discord.Color.dark_gray()
                )
                submitter_embed.add_field(
                    name="No Action Taken",
                    value="No rating changes have been made.",
                    inline=False
                )

            submitter_embed.set_footer(text=f"Confirmation ID: {confirmation_id}")

            # Message for opponent
            if status == "auto_confirmed":
                opponent_result = "You lost" if you_won else "You won"
                opponent_embed = discord.Embed(
                    title="✅ Match Auto-Confirmed",
                    description=f"{submitter_name}'s match report has been automatically confirmed (you didn't respond within 48 hours).",
                    color=discord.Color.green()
                )
                opponent_embed.add_field(
                    name="Result",
                    value=opponent_result,
                    inline=False
                )
                opponent_embed.add_field(
                    name="ELO Update",
                    value="Your rating will be updated shortly.",
                    inline=False
                )
            else:  # expired
                opponent_embed = discord.Embed(
                    title="⏱️ Match Report Expired",
                    description=f"{submitter_name}'s match report has expired (48-hour timeout).",
                    color=discord.Color.dark_gray()
                )
                opponent_embed.add_field(
                    name="No Action Taken",
                    value="No rating changes have been made.",
                    inline=False
                )

            opponent_embed.set_footer(text=f"Confirmation ID: {confirmation_id}")

            # Send DMs
            try:
                if submitter:
                    await submitter.send(embed=submitter_embed)
                    logger.info(f"Sent {status} notification to submitter: {submitter_id}")
            except discord.Forbidden:
                logger.warning(f"Could not send DM to submitter {submitter_id} (DMs disabled)")

            try:
                if opponent:
                    await opponent.send(embed=opponent_embed)
                    logger.info(f"Sent {status} notification to opponent: {opponent_id}")
            except discord.Forbidden:
                logger.warning(f"Could not send DM to opponent {opponent_id} (DMs disabled)")

        except Exception as e:
            logger.error(f"Error sending expiration notification: {e}", exc_info=True)

    @tasks.loop(hours=1)
    async def reminder_job(self):
        """
        Background job that runs every hour to send 24-hour reminders.

        Finds confirmations that:
        - Are pending
        - Were created 24+ hours ago
        - Haven't had a reminder sent yet
        - Haven't expired yet

        Sends a Discord DM to the opponent and marks reminder as sent.
        """
        try:
            confirmations = self._get_confirmations_needing_reminder()

            if not confirmations:
                logger.debug("No confirmations need reminders")
                return

            logger.info(f"Found {len(confirmations)} confirmations needing reminders")

            for confirmation in confirmations:
                # Send reminder DM
                await self._send_reminder_dm(confirmation)

                # Mark reminder as sent
                self._update_reminder_sent(confirmation["id"])

            logger.info(f"Sent {len(confirmations)} reminder DMs")

        except Exception as e:
            logger.error(f"Error in reminder job: {e}", exc_info=True)

    @reminder_job.before_loop
    async def before_reminder_job(self):
        """Wait until bot is ready before starting reminder job."""
        await self.bot.wait_until_ready()
        logger.info("Reminder job is ready")

    @tasks.loop(hours=1)
    async def expiration_job(self):
        """
        Background job that runs every hour to process expired confirmations.

        Finds confirmations that:
        - Are pending
        - Have expired (expires_at <= now)

        Auto-confirms the match and sends notifications to both players.
        """
        try:
            confirmations = self._get_expired_confirmations()

            if not confirmations:
                logger.debug("No expired confirmations")
                return

            logger.info(f"Found {len(confirmations)} expired confirmations")

            for confirmation in confirmations:
                confirmation_id = confirmation["id"]

                # Auto-confirm the match
                self._update_confirmation_status(confirmation_id, "auto_confirmed")

                # Send expiration notifications
                await self._send_expiration_notification(confirmation, "auto_confirmed")

                # TODO: Trigger ELO update (Phase 6)
                logger.info(f"Auto-confirmed expired match: confirmation_id={confirmation_id}")

            logger.info(f"Processed {len(confirmations)} expired confirmations")

        except Exception as e:
            logger.error(f"Error in expiration job: {e}", exc_info=True)

    @expiration_job.before_loop
    async def before_expiration_job(self):
        """Wait until bot is ready before starting expiration job."""
        await self.bot.wait_until_ready()
        logger.info("Expiration job is ready")


async def setup(bot):
    """Add cog to bot."""
    await bot.add_cog(MatchConfirmationJobs(bot))
