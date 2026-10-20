import logging
import os
import sqlite3
from pathlib import Path

import discord
from discord.ext import commands, tasks

import config

logger = logging.getLogger("discord_bot")

# Web app owns store.db; default assumes the standard repo layout.
STORE_DB_PATH = Path(
    os.environ.get(
        "STORE_DB_PATH",
        Path(__file__).resolve().parent.parent.parent / "web-app" / "store.db",
    )
)

MAX_ATTEMPTS = 5

# Discord role products in the Summit Store (e.g. a season ticket): the web
# app queues one row per role, recipient = buyer's Discord id, body = role id
ROLE_CHANNELS = ("discord_role_add", "discord_role_remove")


class RoleGrantProblem(Exception):
    """A role change that retrying won't fix (not in the server, no such role)."""


class StoreNotificationsCog(commands.Cog):
    """Delivers store order notifications (buyer DMs + admin channel pings).

    The web app enqueues rows into the notifications table in store.db when
    orders are paid or shipped; this cog polls for pending Discord rows and
    delivers them. Email rows are handled by the web app, not the bot.
    It also gives (or, after a refund, takes back) Discord roles bought in
    the Summit Store.
    """

    def __init__(self, bot):
        self.bot = bot
        self.store_channel_id = getattr(config, "STORE_ORDERS_CHANNEL_ID", 0)
        self.deliver_notifications.start()
        logger.info("StoreNotificationsCog initialized")

    def cog_unload(self):
        self.deliver_notifications.cancel()

    # ------------------------------------------------------------------

    def _fetch_pending(self):
        if not STORE_DB_PATH.exists():
            return []
        conn = sqlite3.connect(STORE_DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            return [
                dict(r) for r in conn.execute(
                    """SELECT * FROM notifications
                       WHERE status = 'pending'
                         AND channel IN ('discord_dm', 'discord_admin', ?, ?)
                         AND attempts < ?
                       ORDER BY created_at ASC LIMIT 10""",
                    (*ROLE_CHANNELS, MAX_ATTEMPTS),
                ).fetchall()
            ]
        except sqlite3.OperationalError:
            # Table not created yet (store never used) - nothing to do.
            return []
        finally:
            conn.close()

    def _mark(self, notification_id: int, success: bool, error: str | None = None,
              final: bool = False):
        conn = sqlite3.connect(STORE_DB_PATH)
        try:
            if final:
                conn.execute(
                    """UPDATE notifications
                       SET attempts = attempts + 1, last_error = ?, status = 'failed'
                       WHERE id = ?""",
                    (error, notification_id),
                )
            elif success:
                conn.execute(
                    """UPDATE notifications
                       SET status = 'sent', sent_at = datetime('now'),
                           attempts = attempts + 1
                       WHERE id = ?""",
                    (notification_id,),
                )
            else:
                conn.execute(
                    """UPDATE notifications
                       SET attempts = attempts + 1, last_error = ?,
                           status = CASE WHEN attempts + 1 >= ?
                                    THEN 'failed' ELSE 'pending' END
                       WHERE id = ?""",
                    (error, MAX_ATTEMPTS, notification_id),
                )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _build_embed(n: dict) -> discord.Embed:
        return discord.Embed(
            title=n["subject"],
            description=n["body"][:4000],
            color=discord.Color.green(),
        )

    # ------------------------------------------------------------------

    @tasks.loop(seconds=30)
    async def deliver_notifications(self):
        try:
            pending = self._fetch_pending()
        except Exception as e:
            logger.error(f"Store notifications: fetch failed: {e}")
            return

        for n in pending:
            if n["channel"] in ROLE_CHANNELS:
                await self._deliver_role(n)
                continue
            try:
                if n["channel"] == "discord_admin":
                    await self._send_admin(n)
                else:
                    await self._send_dm(n)
                self._mark(n["id"], success=True)
            except discord.Forbidden:
                # DMs closed. Permanent for this user: fail immediately so
                # the buyer's email fallback (if any) is the record.
                self._mark(n["id"], success=False, error="DMs closed (Forbidden)")
                logger.info(
                    f"Store DM blocked for user {n['recipient']} "
                    f"(notification {n['id']})"
                )
            except discord.NotFound:
                self._mark(n["id"], success=False, error="Recipient not found")
            except Exception as e:
                self._mark(n["id"], success=False, error=str(e)[:500])
                logger.warning(
                    f"Store notification {n['id']} delivery error: {e}"
                )

    async def _deliver_role(self, n: dict):
        try:
            await self._change_role(n)
            self._mark(n["id"], success=True)
            return
        except RoleGrantProblem as e:
            error = str(e)
            final = True
        except discord.Forbidden:
            error = ("The bot isn't allowed to manage this role. Give it Manage Roles "
                     "and move its role above this one in Server Settings > Roles.")
            final = True
        except Exception as e:
            error = str(e)[:500]
            final = n["attempts"] + 1 >= MAX_ATTEMPTS
        self._mark(n["id"], success=False, error=error, final=final)
        logger.warning(f"Store role change {n['id']} failed: {error}")
        if final:
            # Someone has to do it by hand, so tell the store admins
            try:
                await self._send_admin({
                    "subject": f"Couldn't {n['subject'][0].lower()}{n['subject'][1:]}",
                    "body": f"Buyer: <@{n['recipient']}> ({n['recipient']})\n"
                            f"Role: <@&{n['body']}> ({n['body']})\n"
                            f"Problem: {error}\n\nPlease do it by hand in Discord.",
                })
            except Exception as e:
                logger.error(f"Store role failure alert not sent: {e}")

    async def _change_role(self, n: dict):
        guild = self.bot.get_guild(config.GUILD_ID)
        if guild is None:
            guild = await self.bot.fetch_guild(config.GUILD_ID)
        role = guild.get_role(int(n["body"]))
        if role is None:
            raise RoleGrantProblem(f"No role with ID {n['body']} in the server")
        member = guild.get_member(int(n["recipient"]))
        if member is None:
            try:
                member = await guild.fetch_member(int(n["recipient"]))
            except discord.NotFound:
                raise RoleGrantProblem("The buyer isn't in the Summit Discord server")
        reason = f"Summit Store: {n['subject']}"
        if n["channel"] == "discord_role_add":
            if role not in member.roles:
                await member.add_roles(role, reason=reason)
        elif role in member.roles:
            await member.remove_roles(role, reason=reason)

    async def _send_dm(self, n: dict):
        user = self.bot.get_user(int(n["recipient"]))
        if user is None:
            user = await self.bot.fetch_user(int(n["recipient"]))
        await user.send(embed=self._build_embed(n))

    async def _send_admin(self, n: dict):
        if not self.store_channel_id:
            raise RuntimeError("STORE_ORDERS_CHANNEL_ID not configured")
        channel = self.bot.get_channel(self.store_channel_id)
        if channel is None:
            channel = await self.bot.fetch_channel(self.store_channel_id)
        await channel.send(embed=self._build_embed(n))

    @deliver_notifications.before_loop
    async def before_deliver(self):
        await self.bot.wait_until_ready()
