"""Precon ladder (Lavamancer vs Frostmage): season commands, standings and the final post."""

import datetime
import logging

import discord
from discord.ext import commands, tasks

import config
from services import precon_service
from services.precon_ladder import normalize_precon, precon_label
from utils.checks import is_bot_admin

logger = logging.getLogger("discord_bot")

WEB_APP_URL = str(getattr(config, "WEB_APP_URL", "") or "https://sorcererssummit.com").rstrip("/")
STANDINGS_URL = f"{WEB_APP_URL}/precon"  # short link to the home page LM / FM tab


def _when(iso) -> str:
    """Discord timestamp for a naive server-local ISO time."""
    try:
        return f"<t:{int(datetime.datetime.fromisoformat(iso).timestamp())}:f>"
    except (TypeError, ValueError):
        return str(iso)


def _record(row) -> str:
    return f"{row['wins']}-{row['losses']}"


def _precon_records(row) -> str:
    parts = []
    if row["lm_wins"] or row["lm_losses"]:
        parts.append(f"LM {row['lm_wins']}-{row['lm_losses']}")
    if row["fm_wins"] or row["fm_losses"]:
        parts.append(f"FM {row['fm_wins']}-{row['fm_losses']}")
    return " · ".join(parts)


def standings_lines(rows, limit=10) -> list[str]:
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = []
    for row in [r for r in rows if r["ranked"]][:limit]:
        badge = medals.get(row["rank"], f"**#{row['rank']}**")
        extra = _precon_records(row)
        lines.append(
            f"{badge} {row['name']} — **{row['rating']}** ({_record(row)}){f' · {extra}' if extra else ''}"
        )
    return lines


class PreconLadderCog(commands.Cog):
    """Commands for the four-week Lavamancer vs Frostmage ladder."""

    def __init__(self, bot):
        self.bot = bot
        self.post_final_standings.start()

    def cog_unload(self):
        self.post_final_standings.cancel()

    async def _refresh_lfg_status(self):
        lfg_cog = self.bot.get_cog("LFGCog")
        if lfg_cog:
            try:
                await lfg_cog.update_lfg_status()
            except Exception as e:
                logger.warning("Could not refresh LFG status after precon change: %s", e)

    @commands.command()
    @is_bot_admin()
    async def start_precon_season(self, ctx, *, season_name: str = None):
        """Start a Lavamancer vs Frostmage ladder (length from the precon settings).

        The queue has its own switch: !precon_queue on (or Admin > Precon Ladder).
        Usage: !start_precon_season <name>
        """
        if not season_name:
            await ctx.send("Please give the ladder a name: `!start_precon_season <name>`")
            return
        try:
            season = precon_service.start_season(season_name, created_by=ctx.author.id)
        except ValueError as e:
            await ctx.send(f"Couldn't start the precon ladder: {e}")
            return
        await self._refresh_lfg_status()
        embed = discord.Embed(
            title=f"🧙 {season['name']} has started!",
            description=(
                "The **Lavamancer vs Frostmage** precon ladder is open. Click **🧙 Join Precon (LM/FM)** "
                f"in <#{config.LFG_CHANNEL_ID}> (or queue on Play Sorcery Online). Summit hands one player Lavamancer and the other Frostmage at random, "
                "and every game moves your ladder rating."
            ),
            color=discord.Color.purple(),
        )
        embed.add_field(name="Runs until", value=_when(season["ends_at"]), inline=True)
        embed.add_field(name="Rating", value="Glicko-2, everyone starts at 1500", inline=True)
        embed.add_field(name="Standings", value=STANDINGS_URL, inline=False)
        await ctx.send(embed=embed)
        if not precon_service.settings(use_cache=False)["queue_enabled"]:
            await ctx.send(
                "ℹ️ The precon queue is switched **off**, so players can't queue yet. "
                "Turn it on with `!precon_queue on` or on the Admin page (Precon Ladder)."
            )

    @start_precon_season.error
    async def start_precon_season_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You don't have permission to use this command.")
        else:
            logger.error("start_precon_season error: %s", error, exc_info=True)
            await ctx.send(f"An error occurred: {error}")

    @commands.command()
    @is_bot_admin()
    async def end_precon_season(self, ctx):
        """End the running precon ladder now (the queue closes with it)."""
        season = precon_service.end_season()
        await self._refresh_lfg_status()
        if not season:
            await ctx.send("No precon ladder is running. The precon queue is closed.")
            return
        await ctx.send(f"🧙 **{season['name']}** has ended. Final standings will be posted shortly.")
        await self.post_final_standings()

    @end_precon_season.error
    async def end_precon_season_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You don't have permission to use this command.")
        else:
            logger.error("end_precon_season error: %s", error, exc_info=True)
            await ctx.send(f"An error occurred: {error}")

    @commands.command()
    @is_bot_admin()
    async def precon_queue(self, ctx, state: str = None):
        """Switch the precon queue on or off (it also needs a ladder running).

        Usage: !precon_queue on|off
        """
        current = precon_service.settings(use_cache=False)
        if state is None:
            running = precon_service.season_is_open()
            await ctx.send(
                f"Precon queue switch is **{'on' if current['queue_enabled'] else 'off'}**"
                f"{'' if running else ' (no precon ladder is running, so the queue is hidden either way)'}. "
                "Usage: `!precon_queue on|off`"
            )
            return
        try:
            current = precon_service.update_settings({"queue_enabled": state}, updated_by=ctx.author.id)
        except ValueError:
            await ctx.send("Usage: `!precon_queue on|off`")
            return
        await self._refresh_lfg_status()
        await ctx.send(f"🧙 Precon queue switched **{'on' if current['queue_enabled'] else 'off'}**.")

    @precon_queue.error
    async def precon_queue_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You don't have permission to use this command.")
        else:
            logger.error("precon_queue error: %s", error, exc_info=True)
            await ctx.send(f"An error occurred: {error}")

    @commands.command(aliases=["precon_rank", "lmfm"])
    async def precon(self, ctx, member: discord.Member = None):
        """Show the LM/FM ladder top 10 and where you (or someone) stand.

        Usage: !precon [@player]
        """
        season = precon_service.current_or_latest_season()
        if not season:
            await ctx.send("No precon ladder has run yet.")
            return
        rows = precon_service.standings(season["season_id"])
        target = member or ctx.author
        mine = next((r for r in rows if r["user_id"] == str(target.id)), None)
        status = (
            f"Runs until {_when(season['ends_at'])}" if season["is_open"]
            else f"Ended {_when(season['last_day'])}"
        )
        embed = discord.Embed(
            title=f"🧙 {season['name']} — LM/FM ladder",
            description=status,
            color=discord.Color.purple(),
        )
        lines = standings_lines(rows)
        needed = precon_service.settings()["min_ranked_games"]
        embed.add_field(
            name="Top 10",
            value="\n".join(lines) if lines else f"Nobody has {needed} games yet.",
            inline=False,
        )
        if mine:
            where = (
                f"#{mine['rank']}" if mine["ranked"]
                else f"not ranked yet ({mine['games']}/{needed} games)"
            )
            extra = _precon_records(mine)
            embed.add_field(
                name=target.display_name,
                value=f"**{mine['rating']}** · {where} · {_record(mine)}{f' · {extra}' if extra else ''}",
                inline=False,
            )
        else:
            embed.add_field(name=target.display_name, value="No precon games yet.", inline=False)
        embed.add_field(name="Full standings", value=STANDINGS_URL, inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    @is_bot_admin()
    async def remove_precon_match(self, ctx, match_id: int = None):
        """Take a precon game off the ladder and re-rate the season.

        Usage: !remove_precon_match <precon match id>
        """
        if not match_id:
            await ctx.send("Usage: `!remove_precon_match <precon match id>`")
            return
        game = precon_service.remove_match(match_id)
        if not game:
            await ctx.send(f"No precon match #{match_id} to remove (or it was already removed).")
            return
        await ctx.send(
            f"🗑️ Precon match #{match_id} removed ({game['winner_display_name']} beat "
            f"{game['loser_display_name']}). The LM/FM ladder has been recalculated."
        )

    @remove_precon_match.error
    async def remove_precon_match_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You don't have permission to use this command.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("Usage: `!remove_precon_match <precon match id>`")
        else:
            logger.error("remove_precon_match error: %s", error, exc_info=True)
            await ctx.send(f"An error occurred: {error}")

    @commands.command()
    @is_bot_admin()
    async def admin_precon_report(
        self, ctx, winner: discord.Member = None, winner_precon: str = None,
        loser: discord.Member = None, loser_precon: str = None,
    ):
        """Record a precon game by hand.

        Usage: !admin_precon_report @winner LM @loser FM
        """
        w_key, l_key = normalize_precon(winner_precon), normalize_precon(loser_precon)
        if not winner or not loser or not w_key or not l_key:
            await ctx.send("Usage: `!admin_precon_report @winner LM|FM @loser LM|FM`")
            return
        if winner.id == loser.id:
            await ctx.send("The winner and loser must be different players.")
            return
        result = precon_service.record_match(
            winner_id=winner.id,
            loser_id=loser.id,
            winner_name=winner.global_name or winner.display_name,
            loser_name=loser.global_name or loser.display_name,
            winner_precon=w_key,
            loser_precon=l_key,
            reporter_id=ctx.author.id,
            source="admin",
            match_comment=f"Reported by admin {ctx.author.display_name}",
        )
        await ctx.send(
            f"✅ Precon match #{result['match_id']}: {winner.display_name} ({precon_label(w_key)}) beat "
            f"{loser.display_name} ({precon_label(l_key)})."
            + precon_service.rating_change_text(result, winner.display_name, loser.display_name)
        )

    @admin_precon_report.error
    async def admin_precon_report_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You don't have permission to use this command.")
        elif isinstance(error, (commands.BadArgument, commands.MemberNotFound)):
            await ctx.send("Usage: `!admin_precon_report @winner LM|FM @loser LM|FM`")
        else:
            logger.error("admin_precon_report error: %s", error, exc_info=True)
            await ctx.send(f"An error occurred: {error}")

    @tasks.loop(minutes=10)
    async def post_final_standings(self):
        """When a ladder's time is up, refresh the LFG status (the queue closes) and post the final top 10."""
        try:
            finished = precon_service.seasons_needing_final_post()
        except Exception:
            logger.error("Could not check finished precon seasons", exc_info=True)
            return
        if not finished:
            return
        if not precon_service.open_season(use_cache=False):
            precon_service.clear_cache()
            await self._refresh_lfg_status()
        channel = self.bot.get_channel(config.LFG_CHANNEL_ID)
        for season in finished:
            rows = precon_service.standings(season["season_id"])
            stats = precon_service.season_stats(season["season_id"])
            lines = standings_lines(rows)
            embed = discord.Embed(
                title=f"🏁 {season['name']} — final LM/FM standings",
                description="\n".join(lines) if lines else "No player reached the game minimum.",
                color=discord.Color.gold(),
            )
            matchup = stats["lm_vs_fm"]
            embed.add_field(name="Games", value=str(stats["games"]), inline=True)
            embed.add_field(name="Players", value=str(stats["players"]), inline=True)
            embed.add_field(
                name="Lavamancer vs Frostmage",
                value=f"LM {matchup['lm_wins']} – {matchup['fm_wins']} FM",
                inline=True,
            )
            embed.add_field(name="Full standings", value=STANDINGS_URL, inline=False)
            try:
                if channel:
                    await channel.send(embed=embed)
                precon_service.mark_final_posted(season["season_id"])
            except Exception:
                logger.error("Could not post final precon standings", exc_info=True)

    @post_final_standings.before_loop
    async def before_post_final_standings(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(PreconLadderCog(bot))
