"""
Anti-Spam Cog
=============
Monitors message rates and takes action against spam bots and users.
"""

import discord
from discord.ext import commands
import logging
from collections import defaultdict, deque
import time
import asyncio

logger = logging.getLogger("discord_bot")


class AntiSpamCog(commands.Cog):
    """Monitor and prevent spam in the server."""
    
    def __init__(self, bot):
        self.bot = bot
        
        # Configuration - adjust these values as needed
        self.MESSAGE_THRESHOLD = 5  # Number of messages
        self.TIME_WINDOW = 5  # Within this many seconds
        self.DUPLICATE_THRESHOLD = 3  # Same message repeated this many times
        self.MUTE_DURATION = 600  # Mute for 10 minutes (in seconds)
        
        # Track user messages: {user_id: deque of (timestamp, message_content)}
        self.user_messages = defaultdict(lambda: deque(maxlen=10))
        
        # Track muted users: {user_id: unmute_timestamp}
        self.muted_users = {}
        
        # Start cleanup task
        self.cleanup_task = self.bot.loop.create_task(self.cleanup_old_data())
    
    def cog_unload(self):
        """Cancel cleanup task when cog is unloaded."""
        self.cleanup_task.cancel()
    
    async def cleanup_old_data(self):
        """Periodically clean up old tracking data."""
        while True:
            try:
                await asyncio.sleep(60)  # Run every minute
                
                current_time = time.time()
                
                # Clean up old message records
                for user_id in list(self.user_messages.keys()):
                    messages = self.user_messages[user_id]
                    # Remove messages older than time window
                    while messages and current_time - messages[0][0] > self.TIME_WINDOW:
                        messages.popleft()
                    
                    # Remove empty entries
                    if not messages:
                        del self.user_messages[user_id]
                
                # Clean up expired mutes
                for user_id in list(self.muted_users.keys()):
                    if current_time >= self.muted_users[user_id]:
                        del self.muted_users[user_id]
                        logger.info(f"Removed expired mute for user {user_id}")
                
            except Exception as e:
                logger.error(f"Error in cleanup_old_data: {e}")
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Monitor all messages for spam patterns."""
        
        # Ignore bot messages and DMs
        if message.author.bot or not message.guild:
            return
        
        # Ignore messages from admins/mods
        if message.author.guild_permissions.administrator or message.author.guild_permissions.manage_messages:
            return
        
        user_id = message.author.id
        current_time = time.time()
        
        # Check if user is already muted
        if user_id in self.muted_users:
            try:
                await message.delete()
                logger.info(f"Deleted message from muted user {message.author.name}")
            except discord.Forbidden:
                logger.warning(f"Cannot delete message from {message.author.name} - insufficient permissions")
            return
        
        # Add message to tracking
        self.user_messages[user_id].append((current_time, message.content))
        
        # Get recent messages from this user
        recent_messages = self.user_messages[user_id]
        
        # Check for spam patterns
        spam_detected = False
        spam_reason = ""
        
        # Pattern 1: Too many messages in time window
        messages_in_window = [
            msg for msg in recent_messages 
            if current_time - msg[0] <= self.TIME_WINDOW
        ]
        
        if len(messages_in_window) >= self.MESSAGE_THRESHOLD:
            spam_detected = True
            spam_reason = f"Sent {len(messages_in_window)} messages in {self.TIME_WINDOW} seconds"
        
        # Pattern 2: Duplicate message spam
        if not spam_detected and len(messages_in_window) >= self.DUPLICATE_THRESHOLD:
            message_contents = [msg[1] for msg in messages_in_window]
            # Check if same message repeated
            if len(set(message_contents)) == 1:
                spam_detected = True
                spam_reason = f"Repeated same message {len(message_contents)} times"
        
        # Take action if spam detected
        if spam_detected:
            await self.handle_spam(message, spam_reason)
    
    async def handle_spam(self, message: discord.Message, reason: str):
        """Take action against a spam user."""
        
        user_id = message.author.id
        
        try:
            # Log the spam detection
            logger.warning(
                f"SPAM DETECTED: {message.author.name} (ID: {user_id}) in #{message.channel.name} - {reason}"
            )
            
            # Delete recent messages from this user in this channel
            deleted_count = 0
            async for msg in message.channel.history(limit=50):
                if msg.author.id == user_id:
                    try:
                        await msg.delete()
                        deleted_count += 1
                    except discord.NotFound:
                        pass
                    except discord.Forbidden:
                        logger.warning(f"Cannot delete messages - insufficient permissions")
                        break
            
            logger.info(f"Deleted {deleted_count} messages from {message.author.name}")
            
            # Try to timeout the user (requires timeout permission)
            try:
                timeout_until = discord.utils.utcnow() + discord.timedelta(seconds=self.MUTE_DURATION)
                await message.author.timeout(timeout_until, reason=f"Anti-spam: {reason}")
                logger.info(f"Timed out {message.author.name} until {timeout_until}")
                
                # Track muted user
                self.muted_users[user_id] = time.time() + self.MUTE_DURATION
                
            except discord.Forbidden:
                logger.warning(f"Cannot timeout {message.author.name} - insufficient permissions")
            except Exception as e:
                logger.error(f"Error timing out user: {e}")
            
            # Get owner ID from config
            try:
                from utils.config import LFGConfig
                owner_id = LFGConfig.OWNER_ID
            except:
                owner_id = None
            
            # Send alert to channel with owner tag
            owner_mention = f"<@{owner_id}> " if owner_id else ""
            alert_message = await message.channel.send(
                f"{owner_mention}🚨 **Anti-Spam Action Taken**\n"
                f"User: {message.author.mention}\n"
                f"Reason: {reason}\n"
                f"Action: Messages deleted and user timed out for {self.MUTE_DURATION // 60} minutes"
            )
            
            # Delete alert after 30 seconds
            await asyncio.sleep(30)
            try:
                await alert_message.delete()
            except:
                pass
            
        except Exception as e:
            logger.error(f"Error handling spam: {e}")


async def setup(bot):
    """Load the AntiSpamCog."""
    await bot.add_cog(AntiSpamCog(bot))
