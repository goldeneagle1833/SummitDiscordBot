"""Community management cog - admin commands to manage Discord servers, YouTube channels, and websites."""

import discord
from discord.ext import commands
import logging

from repositories.community_repo import (
    create_community_tables,
    add_discord_server,
    add_youtube_channel,
    add_website,
    remove_entry,
    get_all_discord_servers,
    get_all_youtube_channels,
    get_all_websites,
)
from repositories.audit_repo import log_admin_action
from utils.checks import is_bot_admin

logger = logging.getLogger("discord_bot")


class CommunityCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        create_community_tables()
        logger.info("CommunityCog initialized")

    async def _add_discord_server(self, ctx, name: str, invite_url: str, location: str, description: str = ""):
        """Internal method to add a Discord server."""
        entry_id = add_discord_server(name, invite_url, location, description, added_by=ctx.author.id)
        log_admin_action(
            ctx.author.id, ctx.author.display_name, "add_community_discord",
            target_id=entry_id, target_name=name,
            new_state={"name": name, "invite_url": invite_url, "location": location},
            details=f"Added Discord server '{name}' ({location})",
        )
        await ctx.send(f"✅ Added Discord server **{name}** (ID: {entry_id}, Location: {location})")

    @commands.command(name="add_discord")
    @is_bot_admin()
    async def add_discord_cmd(self, ctx, *, args: str):
        """[ADMIN] Add a Discord server. Usage: !add_discord Name | invite_url | location | description"""
        parts = [p.strip() for p in args.split("|")]
        if len(parts) < 3:
            await ctx.send(
                "Usage: `!add_discord Name | invite_url | location | description`\n"
                "Example: `!add_discord SoCal Sorcery | https://discord.gg/abc123 | CA | Southern California community`"
            )
            return

        name = parts[0]
        invite_url = parts[1]
        location = parts[2]
        description = parts[3] if len(parts) > 3 else ""

        await self._add_discord_server(ctx, name, invite_url, location, description)

    async def _add_youtube_channel(self, ctx, name: str, channel_id: str, channel_url: str):
        """Internal method to add a YouTube channel."""
        entry_id = add_youtube_channel(name, channel_id, channel_url, added_by=ctx.author.id)
        log_admin_action(
            ctx.author.id, ctx.author.display_name, "add_community_youtube",
            target_id=entry_id, target_name=name,
            new_state={"name": name, "channel_id": channel_id, "channel_url": channel_url},
            details=f"Added YouTube channel '{name}'",
        )
        await ctx.send(f"✅ Added YouTube channel **{name}** (ID: {entry_id})")

    @commands.command(name="add_youtube")
    @is_bot_admin()
    async def add_youtube_cmd(self, ctx, *, args: str):
        """[ADMIN] Add a YouTube channel. Usage: !add_youtube Name | channel_id | channel_url"""
        parts = [p.strip() for p in args.split("|")]
        if len(parts) < 3:
            await ctx.send(
                "Usage: `!add_youtube Name | channel_id | channel_url`\n"
                "Example: `!add_youtube GoldenEagle | UCzWglR4ytbyq0aAfWrNaMHw | https://www.youtube.com/channel/UCzWglR4ytbyq0aAfWrNaMHw`"
            )
            return

        name = parts[0]
        channel_id = parts[1]
        channel_url = parts[2]

        await self._add_youtube_channel(ctx, name, channel_id, channel_url)

    async def _add_website(self, ctx, name: str, url: str, description: str = ""):
        """Internal method to add a website."""
        entry_id = add_website(name, url, description, added_by=ctx.author.id)
        log_admin_action(
            ctx.author.id, ctx.author.display_name, "add_community_website",
            target_id=entry_id, target_name=name,
            new_state={"name": name, "url": url, "description": description},
            details=f"Added website '{name}'",
        )
        await ctx.send(f"✅ Added website **{name}** (ID: {entry_id})")

    @commands.command(name="add_website")
    @is_bot_admin()
    async def add_website_cmd(self, ctx, *, args: str):
        """[ADMIN] Add a website. Usage: !add_website Name | url | description"""
        parts = [p.strip() for p in args.split("|")]
        if len(parts) < 2:
            await ctx.send(
                "Usage: `!add_website Name | url | description`\n"
                "Example: `!add_website Curiosa | https://curiosa.io | Official deck builder`"
            )
            return

        name = parts[0]
        url = parts[1]
        description = parts[2] if len(parts) > 2 else ""

        await self._add_website(ctx, name, url, description)

    async def _remove_community_entry(self, ctx, table_type: str, entry_id: int):
        """Internal method to remove a community entry."""
        table_map = {
            "discord": "discord_servers",
            "youtube": "youtube_channels",
            "website": "websites",
        }

        table_name = table_map.get(table_type.lower())
        if not table_name:
            await ctx.send("❌ Invalid type. Use: `discord`, `youtube`, or `website`")
            return

        try:
            deleted = remove_entry(table_name, entry_id)
        except ValueError as e:
            await ctx.send(f"❌ {str(e)}")
            return

        if deleted:
            log_admin_action(
                ctx.author.id, ctx.author.display_name, "remove_community",
                target_id=entry_id,
                previous_state={"type": table_type, "entry_id": entry_id},
                new_state={"result": "entry deleted"},
                details=f"Removed {table_type} entry ID {entry_id}",
            )
            await ctx.send(f"✅ Removed {table_type} entry with ID {entry_id}.")
        else:
            await ctx.send(f"❌ No {table_type} entry found with ID {entry_id}.")

    @commands.command(name="remove_community")
    @is_bot_admin()
    async def remove_community_cmd(self, ctx, table: str, entry_id: int):
        """[ADMIN] Remove a community entry. Usage: !remove_community discord|youtube|website <id>"""
        await self._remove_community_entry(ctx, table, entry_id)

    @commands.command(name="list_community")
    @is_bot_admin()
    async def list_community_cmd(self, ctx):
        """[ADMIN] List all community entries with IDs."""
        servers = get_all_discord_servers()
        channels = get_all_youtube_channels()
        sites = get_all_websites()

        embed = discord.Embed(title="Community Entries", color=discord.Color.gold())

        # Discord servers
        if servers:
            lines = [f"**{s['id']}** - {s['name']} ({s['state']})" for s in servers]
            embed.add_field(name="Discord Servers (by Location)", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="Discord Servers (by Location)", value="None", inline=False)

        # YouTube channels
        if channels:
            lines = [f"**{c['id']}** - {c['name']}" for c in channels]
            embed.add_field(name="YouTube Channels", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="YouTube Channels", value="None", inline=False)

        # Websites
        if sites:
            lines = [f"**{s['id']}** - {s['name']}" for s in sites]
            embed.add_field(name="Websites", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="Websites", value="None", inline=False)

        embed.set_footer(text="Use !remove_community <discord|youtube|website> <id> to remove")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(CommunityCog(bot))
