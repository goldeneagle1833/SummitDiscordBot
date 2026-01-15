"""
Rules Assistant Cog - Integrates SorceryAI for answering Sorcery: Contested Realm rules questions.
Uses RAG (Retrieval-Augmented Generation) to provide accurate answers based on official rules.
"""

import sys
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
import logging
import config  # Shared config with SorceryAI settings

logger = logging.getLogger("discord_bot")

# Path to SorceryAI directory for imports
SORCERY_AI_PATH = config.SORCERY_AI_DIR


class RulesAssistantCog(commands.Cog):
    """
    AI-powered rules assistant for Sorcery: Contested Realm.
    Uses RAG to retrieve relevant rules and generate accurate answers.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.generator = None
        self.retriever = None
        self.initialized = False
        self.initialization_error = None

    async def cog_load(self):
        """Initialize SorceryAI when cog loads."""
        logger.info("RulesAssistantCog loading - initializing SorceryAI...")
        await self._initialize_sorcery_ai()

    async def _initialize_sorcery_ai(self):
        """Initialize the SorceryAI system (runs in background)."""
        try:
            # Add SorceryAI to path for its internal imports
            sorcery_ai_str = str(SORCERY_AI_PATH)
            if sorcery_ai_str not in sys.path:
                sys.path.insert(0, sorcery_ai_str)

            # Import SorceryAI components (they use the shared config)
            from core.retriever import RulesRetriever
            from core.generator import RulesGenerator

            logger.info("Initializing SorceryAI components...")

            # Create instances
            self.retriever = RulesRetriever()
            self.generator = RulesGenerator()

            # Trigger auto-initialization (indexes knowledge base if needed)
            self.generator.ensure_initialized()

            self.initialized = True
            logger.info("✅ SorceryAI initialized successfully!")
            print("✅ SorceryAI Rules Assistant ready!")

        except ImportError as e:
            self.initialization_error = f"Failed to import SorceryAI: {e}"
            logger.error(self.initialization_error)
            print(f"❌ SorceryAI import error: {e}")

        except Exception as e:
            self.initialization_error = f"Failed to initialize SorceryAI: {e}"
            logger.error(self.initialization_error)
            print(f"❌ SorceryAI initialization error: {e}")

    def _is_ready(self) -> tuple[bool, str]:
        """Check if the system is ready to answer questions."""
        if not self.initialized:
            if self.initialization_error:
                return (
                    False,
                    f"SorceryAI failed to initialize: {self.initialization_error}",
                )
            return (
                False,
                "SorceryAI is still initializing. Please try again in a moment.",
            )
        return True, ""

    @app_commands.command(
        name="rules",
        description="🎲 Ask a rules question about Sorcery: Contested Realm",
    )
    @app_commands.describe(
        question="Your rules question (e.g., 'How does Stealth work?')"
    )
    async def rules_slash(self, interaction: discord.Interaction, question: str):
        """Answer rules questions using AI-powered RAG system."""
        # Check if system is ready
        ready, error_msg = self._is_ready()
        if not ready:
            await interaction.response.send_message(f"⚠️ {error_msg}", ephemeral=True)
            return

        # Defer response since AI processing takes time
        await interaction.response.defer()

        try:
            # Retrieve relevant context
            context = self.retriever.search(question, top_k=5)

            # Generate answer
            response = self.generator.generate(question, context)

            # Build embed response
            embed = discord.Embed(
                title="📖 Rules Answer",
                description=response.answer,
                color=discord.Color.blue(),
            )

            # Add sources if available
            if response.sources:
                sources_text = "\n".join(
                    f"• {source}" for source in response.sources[:5]
                )
                embed.add_field(name="📚 Sources", value=sources_text, inline=False)

            embed.set_footer(
                text="Powered by SorceryAI • Answers based on official rules and FAQs"
            )

            await interaction.followup.send(embed=embed)

            # Log usage
            logger.info(
                f"Rules question answered: '{question[:50]}...' for {interaction.user}"
            )

        except Exception as e:
            logger.error(f"Error answering rules question: {e}")
            await interaction.followup.send(
                "❌ Sorry, I encountered an error processing your question. Please try again.",
                ephemeral=True,
            )

    @app_commands.command(
        name="rules_status", description="🔧 Check SorceryAI status (admin only)"
    )
    @app_commands.default_permissions(administrator=True)
    async def rules_status(self, interaction: discord.Interaction):
        """Check the status of the SorceryAI system."""
        embed = discord.Embed(
            title="🤖 SorceryAI Status",
            color=discord.Color.green() if self.initialized else discord.Color.red(),
        )

        if self.initialized:
            embed.description = "✅ SorceryAI is online and ready!"
            embed.add_field(
                name="Components",
                value="• Retriever: ✅ Ready\n• Generator: ✅ Ready\n• Knowledge Base: ✅ Indexed",
                inline=False,
            )
        else:
            embed.description = "❌ SorceryAI is not initialized"
            if self.initialization_error:
                embed.add_field(
                    name="Error",
                    value=f"```{self.initialization_error}```",
                    inline=False,
                )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # Traditional command fallback
    @commands.command(name="rules", aliases=["rule", "ruling"])
    async def rules_command(self, ctx: commands.Context, *, question: str = None):
        """Answer rules questions (use /rules for better experience)."""
        if not question:
            await ctx.send(
                "❓ Please provide a question!\n"
                "**Usage:** `!rules How does Stealth work?`\n"
                "**Tip:** Use `/rules` for a better experience!"
            )
            return

        # Check if system is ready
        ready, error_msg = self._is_ready()
        if not ready:
            await ctx.send(f"⚠️ {error_msg}")
            return

        async with ctx.typing():
            try:
                # Retrieve and generate
                context = self.retriever.search(question, top_k=5)
                response = self.generator.generate(question, context)

                # Build embed
                embed = discord.Embed(
                    title="📖 Rules Answer",
                    description=response.answer,
                    color=discord.Color.blue(),
                )

                if response.sources:
                    sources_text = "\n".join(
                        f"• {source}" for source in response.sources[:5]
                    )
                    embed.add_field(name="📚 Sources", value=sources_text, inline=False)

                embed.set_footer(
                    text="Powered by SorceryAI • Use /rules for slash command"
                )

                await ctx.send(embed=embed)

            except Exception as e:
                logger.error(f"Error in !rules command: {e}")
                await ctx.send("❌ Sorry, I encountered an error. Please try again.")


async def setup(bot: commands.Bot):
    """Setup function for loading the cog."""
    await bot.add_cog(RulesAssistantCog(bot))
