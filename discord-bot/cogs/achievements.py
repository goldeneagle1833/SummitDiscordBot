"""
Achievements Cog
================
Handles all achievement-related Discord commands.
"""

import discord
from discord import app_commands
from discord.ext import commands
import logging

from utils.achievements import (
    ACHIEVEMENTS,
    get_user_achievements,
    get_earned_achievements,
    get_or_create_profile
)

logger = logging.getLogger("discord_bot")


class AchievementsCog(commands.Cog):
    """Commands for viewing and managing achievements."""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(
        name="profile",
        description="View a user's profile and achievements"
    )
    @app_commands.describe(user="The user whose profile you want to view (leave empty for yourself)")
    async def profile(self, interaction: discord.Interaction, user: discord.Member = None):
        """
        Display a user's profile with achievement status.
        
        Args:
            interaction: Discord interaction
            user: Optional user to check (defaults to command invoker)
        """
        target_user = user if user else interaction.user
        discord_id = str(target_user.id)
        username = target_user.display_name
        
        # Get user achievements
        achievement_status, profile = get_user_achievements(discord_id, username)
        
        # Count earned achievements
        total_achievements = len(ACHIEVEMENTS)
        earned_count = sum(1 for status in achievement_status.values() if status)
        
        # Create embed
        embed = discord.Embed(
            title=f"🎮 {username}'s Profile",
            description=f"**Discord ID:** {target_user.mention}\n**Achievements:** {earned_count}/{total_achievements}",
            color=discord.Color.blue()
        )
        
        # Add achievement progress bar
        progress_bar_length = 10
        filled = int((earned_count / total_achievements) * progress_bar_length)
        progress_bar = "█" * filled + "░" * (progress_bar_length - filled)
        embed.add_field(
            name="Progress",
            value=f"{progress_bar} {(earned_count/total_achievements)*100:.1f}%",
            inline=False
        )
        
        # Group achievements by category
        win_achievements = []
        elo_achievements = []
        avatar_achievements = []
        special_achievements = []
        
        for achievement_id, config in ACHIEVEMENTS.items():
            earned = achievement_status.get(achievement_id, False)
            status_icon = "✅" if earned else "❌"
            
            achievement_line = f"{status_icon} {config['emoji']} **{config['name']}**"
            
            if "win" in achievement_id or "play" in achievement_id:
                win_achievements.append(achievement_line)
            elif "elo" in achievement_id:
                elo_achievements.append(achievement_line)
            elif "avatar" in achievement_id:
                avatar_achievements.append(achievement_line)
            else:
                special_achievements.append(achievement_line)
        
        # Add fields for each category
        if win_achievements:
            embed.add_field(
                name="📊 Victory & Participation",
                value="\n".join(win_achievements),
                inline=False
            )
        
        if elo_achievements:
            embed.add_field(
                name="⚡ Elo Milestones",
                value="\n".join(elo_achievements),
                inline=False
            )
        
        if avatar_achievements:
            embed.add_field(
                name="🎭 Avatar Collection",
                value="\n".join(avatar_achievements),
                inline=False
            )
        
        if special_achievements:
            embed.add_field(
                name="🌟 Special Achievements",
                value="\n".join(special_achievements),
                inline=False
            )
        
        embed.set_footer(text="Use /achievements list to see all available achievements")
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(
        name="achievements",
        description="View achievement information"
    )
    @app_commands.describe(
        action="What do you want to do?",
        user="User to check earned achievements for (only used with 'earned' action)"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="List all achievements", value="list"),
        app_commands.Choice(name="Show earned achievements", value="earned")
    ])
    async def achievements(
        self, 
        interaction: discord.Interaction, 
        action: str,
        user: discord.Member = None
    ):
        """
        Display achievement information.
        
        Args:
            interaction: Discord interaction
            action: Either 'list' (all achievements) or 'earned' (user's earned achievements)
            user: Optional user to check (defaults to command invoker for 'earned')
        """
        if action == "list":
            await self._list_achievements(interaction)
        elif action == "earned":
            await self._earned_achievements(interaction, user)
    
    async def _list_achievements(self, interaction: discord.Interaction):
        """Display all available achievements."""
        embed = discord.Embed(
            title="🏆 All Available Achievements",
            description="Complete these challenges to unlock achievements!",
            color=discord.Color.gold()
        )
        
        # Group achievements by category
        categories = {
            "📊 Victory & Participation": [],
            "⚡ Elo Milestones": [],
            "🎭 Avatar Collection": [],
            "🌟 Special Achievements": []
        }
        
        for achievement_id, config in ACHIEVEMENTS.items():
            achievement_line = f"{config['emoji']} **{config['name']}**\n*{config['description']}*"
            
            if "win" in achievement_id or "play" in achievement_id:
                categories["📊 Victory & Participation"].append(achievement_line)
            elif "elo" in achievement_id:
                categories["⚡ Elo Milestones"].append(achievement_line)
            elif "avatar" in achievement_id:
                categories["🎭 Avatar Collection"].append(achievement_line)
            else:
                categories["🌟 Special Achievements"].append(achievement_line)
        
        # Add fields for each category
        for category_name, achievements in categories.items():
            if achievements:
                # Split into multiple fields if too long
                chunk_size = 5
                for i in range(0, len(achievements), chunk_size):
                    chunk = achievements[i:i + chunk_size]
                    field_name = category_name if i == 0 else f"{category_name} (cont.)"
                    embed.add_field(
                        name=field_name,
                        value="\n\n".join(chunk),
                        inline=False
                    )
        
        embed.set_footer(text="Use /profile to see your achievement progress!")
        
        await interaction.response.send_message(embed=embed)
    
    async def _earned_achievements(self, interaction: discord.Interaction, user: discord.Member = None):
        """Display earned achievements for a user."""
        target_user = user if user else interaction.user
        discord_id = str(target_user.id)
        username = target_user.display_name
        
        # Get earned achievements
        earned_ids = get_earned_achievements(discord_id, username)
        
        if not earned_ids:
            await interaction.response.send_message(
                f"{target_user.mention} hasn't earned any achievements yet! "
                "Play some matches to start unlocking achievements!",
                ephemeral=True
            )
            return
        
        # Create embed
        embed = discord.Embed(
            title=f"🏆 {username}'s Earned Achievements",
            description=f"{target_user.mention} has earned {len(earned_ids)} out of {len(ACHIEVEMENTS)} achievements!",
            color=discord.Color.green()
        )
        
        # Add each earned achievement
        for achievement_id in earned_ids:
            config = ACHIEVEMENTS[achievement_id]
            embed.add_field(
                name=f"{config['emoji']} {config['name']}",
                value=config['description'],
                inline=True
            )
        
        # Calculate completion percentage
        completion = (len(earned_ids) / len(ACHIEVEMENTS)) * 100
        embed.set_footer(text=f"Achievement Completion: {completion:.1f}%")
        
        await interaction.response.send_message(embed=embed)
    
    @commands.command(name="checkachievements")
    @commands.has_permissions(administrator=True)
    async def check_achievements_manual(self, ctx, user: discord.Member = None):
        """
        Manually trigger achievement check for a user (Admin only).
        
        This command is for testing or fixing stuck achievements.
        """
        from utils.achievements import evaluate_achievements
        
        target_user = user if user else ctx.author
        discord_id = str(target_user.id)
        username = target_user.display_name
        
        await ctx.send(f"🔍 Checking achievements for {target_user.mention}...")
        
        # Get achievement announcement channel ID from config if available
        announcement_channel_id = None
        try:
            from utils.config import ACHIEVEMENT_CHANNEL_ID
            announcement_channel_id = ACHIEVEMENT_CHANNEL_ID
        except ImportError:
            pass
        
        newly_unlocked = await evaluate_achievements(
            discord_id,
            username,
            self.bot,
            announcement_channel_id
        )
        
        if newly_unlocked:
            achievement_names = [ACHIEVEMENTS[aid]["name"] for aid in newly_unlocked]
            await ctx.send(
                f"✅ {target_user.mention} earned {len(newly_unlocked)} new achievement(s):\n"
                + "\n".join(f"• {name}" for name in achievement_names)
            )
        else:
            await ctx.send(f"No new achievements for {target_user.mention}.")


async def setup(bot):
    """Load the AchievementsCog."""
    await bot.add_cog(AchievementsCog(bot))
