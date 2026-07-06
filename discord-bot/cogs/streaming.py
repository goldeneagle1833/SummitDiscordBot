"""
Streaming Detection Cog

Monitors Discord presence updates to detect when members are streaming.
Stores streaming status in a shared database for the web app to display.
"""

import discord
from discord.ext import commands, tasks
import sqlite3
import datetime
import json
import logging
from pathlib import Path

import config
from repositories.audit_repo import log_admin_action
from repositories.elo_repo import get_user_latest_deck_url
from utils.checks import is_bot_admin
from utils.deck_checker import scrape_curosa_async

logger = logging.getLogger("discord_bot")

# Database path - shared location for web app access
DB_PATH = Path(__file__).parent.parent.parent / "data" / "streamers.db"


def init_database():
    """Initialize the streamers database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS active_streamers (
            user_id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            display_name TEXT NOT NULL,
            avatar_url TEXT,
            stream_url TEXT,
            stream_title TEXT,
            game_name TEXT,
            platform TEXT,
            started_at TEXT NOT NULL,
            last_seen TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    logger.info(f"Streamers database initialized at {DB_PATH}")


class StreamingCog(commands.Cog):
    """Cog for detecting and tracking streaming members."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        init_database()
        self.cleanup_stale_streamers.start()
        # Track avatar channel notifications so we can delete them when streaming stops
        # {user_id: (channel_id, message_id)}
        self._avatar_notifications: dict[int, tuple[int, int]] = {}
        logger.info("StreamingCog initialized")

    def cog_unload(self):
        self.cleanup_stale_streamers.cancel()

    def _get_streaming_activity(
        self, member: discord.Member
    ) -> discord.Streaming | None:
        """Extract streaming activity from a member's activities."""
        for activity in member.activities:
            if isinstance(activity, discord.Streaming):
                return activity
        return None

    def _get_avatar_from_deck_json(self, deck_json: str) -> str | None:
        """Extract avatar name from a JSON deck data string."""
        try:
            deck_data = json.loads(deck_json)
            avatar = deck_data.get("avatar", [])
            if avatar and len(avatar) > 0:
                name = avatar[0].get("name")
                if name and name != "Unknown":
                    return name
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            pass
        return None

    def _get_channel_for_avatar(self, avatar_name: str) -> int | None:
        """Look up the private channel ID for an avatar name (case-insensitive)."""
        avatar_lower = avatar_name.lower()
        for name, channel_id in config.AVATAR_CHANNEL_MAP.items():
            if name.lower() == avatar_lower:
                return channel_id
        return None

    async def _notify_avatar_channel(
        self,
        member: discord.Member,
        stream_title: str | None = None,
        stream_url: str | None = None,
    ):
        """Send a notification to the avatar's private channel when a member starts streaming."""
        deck_url = get_user_latest_deck_url(member.id)
        if not deck_url:
            logger.debug(f"No recent pairing deck URL found for streamer {member.display_name}")
            return

        deck_json = await scrape_curosa_async(deck_url)
        if not deck_json or deck_json == "{}":
            logger.debug(f"Could not fetch deck data from {deck_url} for {member.display_name}")
            return

        avatar_name = self._get_avatar_from_deck_json(deck_json)
        if not avatar_name:
            logger.debug(f"Could not extract avatar from deck data for {member.display_name}")
            return

        channel_id = self._get_channel_for_avatar(avatar_name)
        if not channel_id:
            logger.debug(f"No private channel mapped for avatar '{avatar_name}'")
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception:
                logger.error(f"Could not fetch avatar channel {channel_id} for '{avatar_name}'")
                return

        stream_link = f"\n[Watch Stream]({stream_url})" if stream_url else ""

        embed = discord.Embed(
            title=f"🎮 {avatar_name} Player Streaming!",
            description=(
                f"**{member.display_name}** is now live playing with **{avatar_name}**!{stream_link}"
            ),
            color=discord.Color.purple(),
        )
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
        if stream_title:
            embed.add_field(name="Stream Title", value=stream_title, inline=False)

        try:
            msg = await channel.send(embed=embed)
            self._avatar_notifications[member.id] = (channel_id, msg.id)
            logger.info(f"Sent streaming notification to '{avatar_name}' channel for {member.display_name}")
        except Exception as e:
            logger.error(f"Failed to send streaming notification to channel {channel_id}: {e}")

    async def _delete_avatar_notification(self, user_id: int):
        """Delete the avatar channel notification for a streamer who stopped."""
        notif = self._avatar_notifications.pop(user_id, None)
        if not notif:
            return
        channel_id, message_id = notif
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                channel = await self.bot.fetch_channel(channel_id)
            msg = await channel.fetch_message(message_id)
            await msg.delete()
            logger.info(f"Deleted streaming notification (msg {message_id}) from channel {channel_id}")
        except (discord.NotFound, discord.Forbidden):
            pass
        except Exception as e:
            logger.warning(f"Could not delete streaming notification: {e}")

    def _add_streamer(self, member: discord.Member, activity: discord.Streaming):
        """Add or update a streamer in the database (for Twitch/YouTube streaming)."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        now = datetime.datetime.utcnow().isoformat()
        avatar_url = str(member.display_avatar.url) if member.display_avatar else None

        # Determine platform from URL
        platform = "Unknown"
        if activity.url:
            if "twitch.tv" in activity.url.lower():
                platform = "Twitch"
            elif (
                "youtube.com" in activity.url.lower()
                or "youtu.be" in activity.url.lower()
            ):
                platform = "YouTube"

        cursor.execute(
            """
            INSERT INTO active_streamers 
                (user_id, username, display_name, avatar_url, stream_url, stream_title, game_name, platform, started_at, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                display_name = excluded.display_name,
                avatar_url = excluded.avatar_url,
                stream_url = excluded.stream_url,
                stream_title = excluded.stream_title,
                game_name = excluded.game_name,
                platform = excluded.platform,
                last_seen = excluded.last_seen
        """,
            (
                member.id,
                member.name,
                member.display_name,
                avatar_url,
                activity.url,
                activity.name,  # Stream title
                activity.game,  # Game being played
                platform,
                now,
                now,
            ),
        )

        conn.commit()
        conn.close()
        logger.info(f"Added/updated streamer: {member.display_name} - {activity.url}")

    def _add_voice_streamer(
        self, member: discord.Member, channel: discord.VoiceChannel
    ):
        """Add a member who is Go Live in a voice channel."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        now = datetime.datetime.utcnow().isoformat()
        avatar_url = str(member.display_avatar.url) if member.display_avatar else None

        # Check what game they're playing (if any)
        game_name = None
        for activity in member.activities:
            if isinstance(activity, (discord.Game, discord.Activity)):
                game_name = activity.name
                break

        cursor.execute(
            """
            INSERT INTO active_streamers 
                (user_id, username, display_name, avatar_url, stream_url, stream_title, game_name, platform, started_at, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                display_name = excluded.display_name,
                avatar_url = excluded.avatar_url,
                stream_url = excluded.stream_url,
                stream_title = excluded.stream_title,
                game_name = excluded.game_name,
                platform = excluded.platform,
                last_seen = excluded.last_seen
        """,
            (
                member.id,
                member.name,
                member.display_name,
                avatar_url,
                None,  # No external URL for Discord Go Live
                f"Live in #{channel.name}",  # Stream title
                game_name,
                "Discord",  # Platform
                now,
                now,
            ),
        )

        conn.commit()
        conn.close()
        logger.info(f"Added voice streamer: {member.display_name} in #{channel.name}")

    async def _remove_streamer(self, user_id: int):
        """Remove a streamer from the database and delete their avatar channel notification."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM active_streamers WHERE user_id = ?", (user_id,))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        if affected > 0:
            logger.info(f"Removed streamer with user_id: {user_id}")
        await self._delete_avatar_notification(user_id)

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        """Detect when a member starts or stops streaming."""
        before_streaming = self._get_streaming_activity(before)
        after_streaming = self._get_streaming_activity(after)

        # Started streaming
        if after_streaming and not before_streaming:
            logger.info(
                f"{after.display_name} started streaming: {after_streaming.url}"
            )
            self._add_streamer(after, after_streaming)

        # Stopped streaming
        elif before_streaming and not after_streaming:
            logger.info(f"{after.display_name} stopped streaming")
            await self._remove_streamer(after.id)

        # Updated stream info (e.g., changed game)
        elif after_streaming and before_streaming:
            if (
                after_streaming.url != before_streaming.url
                or after_streaming.game != before_streaming.game
                or after_streaming.name != before_streaming.name
            ):
                self._add_streamer(after, after_streaming)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        """Detect when a member starts or stops Go Live (screen sharing) in a voice channel."""
        # Started streaming in voice channel
        if after.self_stream and not before.self_stream:
            if after.channel:
                logger.info(
                    f"{member.display_name} started Go Live in #{after.channel.name}"
                )
                self._add_voice_streamer(member, after.channel)
                await self._notify_avatar_channel(
                    member,
                    stream_title=f"Live in #{after.channel.name}",
                )

        # Stopped streaming (turned off Go Live or left channel)
        elif before.self_stream and not after.self_stream:
            logger.info(f"{member.display_name} stopped Go Live")
            await self._remove_streamer(member.id)

        # Left voice channel while streaming
        elif before.self_stream and before.channel and not after.channel:
            logger.info(f"{member.display_name} left voice channel while streaming")
            await self._remove_streamer(member.id)

    @tasks.loop(minutes=5)
    async def cleanup_stale_streamers(self):
        """Clean up streamers who haven't been seen in a while (in case we missed an update)."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Remove streamers not seen in the last 30 minutes
        cutoff = (
            datetime.datetime.utcnow() - datetime.timedelta(minutes=30)
        ).isoformat()
        cursor.execute("DELETE FROM active_streamers WHERE last_seen < ?", (cutoff,))
        removed = cursor.rowcount

        conn.commit()
        conn.close()

        if removed > 0:
            logger.info(f"Cleaned up {removed} stale streamer entries")

    @cleanup_stale_streamers.before_loop
    async def before_cleanup(self):
        """Wait for bot to be ready before starting the cleanup loop."""
        await self.bot.wait_until_ready()

    @commands.command(name="streamers")
    async def list_streamers(self, ctx: commands.Context):
        """List all currently streaming members."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT display_name, stream_url, game_name, stream_title, platform, started_at
            FROM active_streamers
            ORDER BY started_at DESC
        """)
        streamers = cursor.fetchall()
        conn.close()

        if not streamers:
            embed = discord.Embed(
                title="📺 Active Streams",
                description="No one is currently streaming!",
                color=discord.Color.greyple(),
            )
            await ctx.send(embed=embed)
            return

        embed = discord.Embed(
            title="📺 Active Streams",
            description=f"**{len(streamers)}** member(s) are currently live!",
            color=discord.Color.purple(),
        )

        for (
            display_name,
            stream_url,
            game_name,
            stream_title,
            platform,
            started_at,
        ) in streamers:
            game_text = f"🎮 {game_name}" if game_name else "🎮 Unknown game"
            platform_emoji = (
                "🟣"
                if platform == "Twitch"
                else "🔴"
                if platform == "YouTube"
                else "📺"
            )

            field_value = f"{platform_emoji} **{platform}**\n{game_text}"
            if stream_url:
                field_value += f"\n[Watch Stream]({stream_url})"

            embed.add_field(name=f"{display_name}", value=field_value, inline=True)

        embed.set_footer(text="Check sorcererssummit.com for the live stream banner!")
        await ctx.send(embed=embed)

    @commands.command(name="refresh_streamers")
    @is_bot_admin()
    async def refresh_streamers(self, ctx: commands.Context):
        """Manually refresh the streamers list by checking all members."""
        await ctx.send("🔄 Refreshing streamers list...")

        # Clear the database first
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM active_streamers")
        conn.commit()
        conn.close()

        stream_count = 0
        voice_count = 0

        for guild in self.bot.guilds:
            # Check for Twitch/YouTube streaming presence
            for member in guild.members:
                streaming = self._get_streaming_activity(member)
                if streaming:
                    self._add_streamer(member, streaming)
                    stream_count += 1

            # Check for Go Live in voice channels
            for channel in guild.voice_channels:
                for member in channel.members:
                    if member.voice and member.voice.self_stream:
                        self._add_voice_streamer(member, channel)
                        voice_count += 1

        total = stream_count + voice_count
        log_admin_action(
            ctx.author.id, ctx.author.display_name, "refresh_streamers",
            new_state={"stream_count": stream_count, "voice_count": voice_count, "total": total},
            details=f"Refreshed streamers: {total} found ({stream_count} Twitch/YouTube, {voice_count} Go Live)",
        )
        await ctx.send(
            f"✅ Found **{total}** active streamer(s)! ({stream_count} Twitch/YouTube, {voice_count} Discord Go Live)"
        )

    @commands.command(name="debug_activities")
    @is_bot_admin()
    async def debug_activities(self, ctx: commands.Context):
        """Debug: Show all members with any activity (to diagnose streaming detection)."""
        lines = []
        streaming_count = 0
        activity_count = 0

        for member in ctx.guild.members:
            if member.bot:
                continue
            if member.activities:
                activity_count += 1
                for activity in member.activities:
                    activity_type = type(activity).__name__
                    if isinstance(activity, discord.Streaming):
                        streaming_count += 1
                        lines.append(
                            f"🟣 **{member.display_name}**: STREAMING - {activity.url}"
                        )
                    elif isinstance(activity, discord.Game):
                        lines.append(
                            f"🎮 {member.display_name}: Playing {activity.name}"
                        )
                    elif isinstance(activity, discord.Activity):
                        lines.append(
                            f"📌 {member.display_name}: {activity.type.name} {activity.name}"
                        )
                    elif isinstance(activity, discord.CustomActivity):
                        lines.append(
                            f"💬 {member.display_name}: Custom - {activity.name}"
                        )
                    else:
                        lines.append(f"❓ {member.display_name}: {activity_type}")

        if not lines:
            await ctx.send(
                "⚠️ **No activities detected!**\n\nThis likely means the **Presence Intent** is not enabled.\n\n"
                "Go to Discord Developer Portal → Your App → Bot → Privileged Gateway Intents → Enable **Presence Intent**"
            )
            return

        # Truncate if too long
        output = "\n".join(lines[:30])
        if len(lines) > 30:
            output += f"\n... and {len(lines) - 30} more"

        embed = discord.Embed(
            title="🔍 Activity Debug", description=output, color=discord.Color.blue()
        )
        embed.add_field(
            name="Members with activities", value=str(activity_count), inline=True
        )
        embed.add_field(
            name="Streaming detected", value=str(streaming_count), inline=True
        )
        embed.set_footer(text="Only discord.Streaming type counts as 'streaming'")

        await ctx.send(embed=embed)

    @commands.command(name="debug_voice")
    @is_bot_admin()
    async def debug_voice(self, ctx: commands.Context):
        """Debug: Show all members in voice channels and their streaming status."""
        lines = []
        streaming_count = 0

        for channel in ctx.guild.voice_channels:
            if channel.members:
                lines.append(f"\n**#{channel.name}**")
                for member in channel.members:
                    if member.bot:
                        continue
                    voice = member.voice
                    if voice:
                        status = []
                        if voice.self_stream:
                            status.append("🔴 GO LIVE")
                            streaming_count += 1
                        if voice.self_video:
                            status.append("📹 Camera")
                        if voice.self_mute:
                            status.append("🔇 Muted")
                        if voice.self_deaf:
                            status.append("🔈 Deafened")

                        status_str = " | ".join(status) if status else "🎤 In voice"
                        lines.append(f"  • {member.display_name}: {status_str}")

        if not lines:
            await ctx.send("⚠️ No one is in voice channels!")
            return

        output = "\n".join(lines[:40])
        if len(lines) > 40:
            output += f"\n... and {len(lines) - 40} more"

        embed = discord.Embed(
            title="🎙️ Voice Channel Debug",
            description=output,
            color=discord.Color.green(),
        )
        embed.add_field(
            name="Go Live detected", value=str(streaming_count), inline=True
        )
        embed.set_footer(text="🔴 GO LIVE = Screen sharing in Discord")

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(StreamingCog(bot))
