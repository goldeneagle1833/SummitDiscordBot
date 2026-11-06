import datetime
import discord
from discord.ext import commands
import sqlite3
import logging

import config
from utils.database import get_current_event_match_elo_snapshot
from services import glicko2_season as g2
from services import provisional
from utils.text import find_best_command_match

logger = logging.getLogger("discord_bot")


class EloCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Monitor for invalid commands and suggest elo-related corrections"""
        # Only handle CommandNotFound errors
        if not isinstance(error, commands.CommandNotFound):
            return

        # Extract the failed command from the message
        message_content = ctx.message.content.lower()
        if not message_content.startswith("!"):
            return

        failed_command = message_content.split()[0][1:]  # Remove the !

        # Common elo-related commands and suggestions
        command_suggestions = {
            # Rank variations
            "rating": "!rank",
            "elo": "!rank",
            "myrank": "!rank",
            "myrating": "!rank",
            "myelo": "!rank",
            "checkrank": "!rank",
            "checkrating": "!rank",
            "checkelo": "!rank",
            "gerank": "!rank",
            "getrating": "!rank",
            "getelo": "!rank",
            "ranking": "!rank",
            "elorank": "!rank",
            "elorating": "!rank",
            "score": "!rank",
            "myscore": "!rank",
            "points": "!rank",
            "mypoints": "!rank",
            # Leaderboard variations
            "leaderboards": "!leaderboard",
            "leaders": "!leaderboard",
            "ladder": "!leaderboard",
            "rankings": "!leaderboard",
            "top": "!leaderboard",
            "top16": "!leaderboard",
            "topplayers": "!leaderboard",
            "topranks": "!leaderboard",
            "topelo": "!leaderboard",
            "board": "!leaderboard",
            "lb": "!leaderboard",
            "leaderbord": "!leaderboard",
            "leaderborad": "!leaderboard",
            "eloleaderboard": "!leaderboard",
            "showleaderboard": "!leaderboard",
            "checkleaderboard": "!leaderboard",
            "viewleaderboard": "!leaderboard",
            # Masters bracket variations
            "masters": "!masters_bracket",
            "mastersbracket": "!masters_bracket",
            "master": "!masters_bracket",
            "masterbracket": "!masters_bracket",
            "mastersboard": "!masters_bracket",
            "mastersleaderboard": "!masters_bracket",
            "masterstop": "!masters_bracket",
            "mastersladder": "!masters_bracket",
            "masterranks": "!masters_bracket",
            "masterrankings": "!masters_bracket",
            "mastersrank": "!masters_bracket",
            "mastersranking": "!masters_bracket",
            "premium": "!masters_bracket",
            "premiumleaderboard": "!masters_bracket",
            # Mystats variations
            "stats": "!mystats",
            "statistics": "!mystats",
            "mystatistics": "!mystats",
            "matchstats": "!mystats",
            "mymatchstats": "!mystats",
            "playerstats": "!mystats",
            "myplayerstats": "!mystats",
            "profile": "!mystats",
            "myprofile": "!mystats",
            "record": "!mystats",
            "myrecord": "!mystats",
            "history": "!mystats",
            "myhistory": "!mystats",
            "winrate": "!mystats",
            "mywinrate": "!mystats",
            "performance": "!mystats",
            "myperformance": "!mystats",
            "stat": "!mystats",
            "mystat": "!mystats",
            # Event leaderboard variations
            "eventleaderboard": "!event_leaderboard",
            "eventboard": "!event_leaderboard",
            "eventlb": "!event_leaderboard",
            "eventranking": "!event_leaderboard",
            "eventrankings": "!event_leaderboard",
            "seasonleaderboard": "!event_leaderboard",
            "seasonboard": "!event_leaderboard",
            # Event status variations
            "eventstatus": "!event_status",
            "event": "!event_status",
            "currentevent": "!event_status",
            "season": "!event_status",
            # Match ELO lookup variations
            "matchelo": "!match_elo",
            "matchrating": "!match_elo",
            "gameelo": "!match_elo",
            "eloaftermatch": "!match_elo",
        }

        actual_commands = {
            "rank": "!rank",
            "leaderboard": "!leaderboard",
            "masters_bracket": "!masters_bracket",
            "mastersbracket": "!masters_bracket",
            "mystats": "!mystats",
            "event_leaderboard": "!event_leaderboard",
            "event_status": "!event_status",
            "match_elo": "!match_elo",
        }

        suggestion = find_best_command_match(failed_command, command_suggestions, actual_commands)
        if suggestion:
            await ctx.send(f"{ctx.author.mention}, did you mean `{suggestion}`?")
            return

    @commands.command()
    async def rank(self, ctx, user: discord.Member = None):
        """Check your current Elo ranking and event rank, or check another user's rank by tagging them."""
        from utils.database import get_active_event, has_player_played_event, get_event_participant_ids
        from utils.checks import check_is_admin

        # Determine which user to check
        target_user = user if user else ctx.author
        is_self = target_user == ctx.author
        target_name = target_user.display_name

        conn = sqlite3.connect("elo.db")
        cur = conn.cursor()

        # Get both lifetime and event ELO
        cur.execute(
            "SELECT online_elo, online_event_elo FROM overall_standings WHERE user_id=?", (target_user.id,)
        )
        row = cur.fetchone()

        if row:
            lifetime_elo = row[0] if row[0] else 1500
            event_elo = row[1] if row[1] else 1500

            # Lifetime rank; a Glicko-2 lifetime ranks settled players only
            lifetime_glicko2 = g2.lifetime_is_glicko2(conn)
            lifetime_games = legacy_elo = None
            if lifetime_glicko2:
                lifetime_games = provisional.lifetime_games([target_user.id])[target_user.id]
                cur.execute(
                    "SELECT COUNT(*) FROM overall_standings WHERE online_elo > ? "
                    "AND COALESCE(online_games, 0) >= ?",
                    (lifetime_elo, provisional.PROVISIONAL_GAMES),
                )
            else:
                cur.execute("SELECT COUNT(*) FROM overall_standings WHERE online_elo > ?", (lifetime_elo,))
            lifetime_rank = cur.fetchone()[0] + 1
            if "legacy_online_elo" in {c[1] for c in cur.execute("PRAGMA table_info(overall_standings)")}:
                cur.execute("SELECT legacy_online_elo FROM overall_standings WHERE user_id=?", (target_user.id,))
                legacy_elo = cur.fetchone()[0]

            # Check if there's an active event
            active_event = get_active_event()
            season_glicko2 = g2.is_glicko2(active_event)

            # Check event participation via match_records
            has_event_games = False
            event_rank = 1
            event_games = 0
            if active_event:
                event_start_str = active_event["start_date"].isoformat()
                has_event_games = has_player_played_event(target_user.id, event_start_str)
                if season_glicko2:
                    # Settled players take rank numbers; provisional ones don't
                    from services.avatar_mode import get_event_ladder

                    ladder = get_event_ladder(active_event)
                    event_rank = None
                    ranked = provisional.settled_first(
                        ladder, True, lambda e: e.games_played, lambda e: e.label
                    )
                    for rank, entry in ranked:
                        if entry.user_id == target_user.id:
                            event_rank, event_games = rank, entry.games_played
                            break
                else:
                    # Get event rank (only count players who have played event matches)
                    event_participants = get_event_participant_ids(event_start_str)
                    cur.execute("SELECT user_id, online_event_elo FROM overall_standings WHERE online_event_elo > ?", (event_elo,))
                    event_rank = sum(1 for r in cur.fetchall() if r[0] in event_participants) + 1

            if is_self:
                msg = f"{ctx.author.mention}\n"
            else:
                msg = f"**{target_name}**\n"

            if check_is_admin(ctx):
                if lifetime_glicko2 and g2.is_provisional(lifetime_games):
                    msg += f"**Lifetime ELO:** {g2.provisional_label(lifetime_games)}\n"
                else:
                    msg += f"**Lifetime ELO:** {lifetime_elo} (Rank #{lifetime_rank})\n"
                if legacy_elo is not None:
                    msg += f"**Legacy ELO (Seasons 1-8):** {legacy_elo}\n"

            if active_event:
                from utils.database import calculate_player_event_k, get_user_event_games

                season_games = get_user_event_games(target_user.id)
                if season_glicko2:
                    games_text = f"{season_games} ranked game{'s' if season_games != 1 else ''} this season"
                    if active_event.get("elo_mode") != "avatar" and g2.is_provisional(season_games):
                        k_line = (
                            f"\n**Rating:** Glicko-2, {g2.provisional_label(season_games)}: "
                            f"your rating shows after {provisional.PROVISIONAL_GAMES} ranked games "
                            "and counts for top cut from then"
                        )
                    else:
                        k_line = f"\n**Rating:** Glicko-2 ({games_text})"
                else:
                    k_line = (
                        f"\n**K-value:** {calculate_player_event_k(season_games)} "
                        f"({season_games} ranked game{'s' if season_games != 1 else ''} this season)"
                    )
            else:
                k_line = ""

            if active_event and active_event.get("elo_mode") == "avatar":
                msg += _avatar_rank_lines(active_event, target_user.id)
            elif active_event:
                if not has_event_games:
                    msg += f"**Event ELO ({active_event['event_name']}):** 1500 (No matches yet)"
                elif event_rank is None:
                    msg += f"**Event ELO ({active_event['event_name']}):** {g2.provisional_label(event_games)}"
                else:
                    msg += f"**Event ELO ({active_event['event_name']}):** {event_elo} (Rank #{event_rank})"
            else:
                msg += "*No active event*"

            await ctx.send(msg + k_line)
        else:
            if is_self:
                await ctx.send(
                    f"{ctx.author.mention}, you don't have an Elo rating yet. "
                    "Play some matches to get started!"
                )
            else:
                await ctx.send(
                    f"{target_name} doesn't have an Elo rating yet. "
                    "They need to play some matches to get started!"
                )
        conn.close()

    @commands.command()
    async def leaderboard(self, ctx):
        """Check the top 16 lifetime Elo rankings (admin only)."""
        from utils.checks import check_is_admin

        if not check_is_admin(ctx):
            await ctx.send("The lifetime leaderboard is only available to admins. Use `!event_leaderboard` instead.")
            return

        conn = sqlite3.connect("elo.db")
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id, user_display_name, online_elo FROM overall_standings ORDER BY online_elo DESC"
        )
        rows = _lifetime_ranked(cur.fetchall(), g2.lifetime_is_glicko2(conn))[:16]
        if rows:
            leaderboard = "🏆 **Lifetime Elo Leaderboard** 🏆\n"
            leaderboard += "".join(_lifetime_line(rank, name, elo, games) for rank, (name, elo, games) in rows)
            await ctx.send(leaderboard)
        else:
            await ctx.send("No Elo ratings found. Play some matches to get started!")
        conn.close()

    @commands.command()
    async def event_leaderboard(self, ctx):
        """Check the top 16 event Elo rankings for the current event."""
        from utils.database import get_active_event, get_event_participant_ids

        from services.avatar_mode import get_event_ladder

        active_event = get_active_event()
        if not active_event:
            await ctx.send("No active event. Check back when a new event starts!")
            return

        # One row per player (Player mode) or per player/avatar entry (Avatar mode).
        # Glicko-2: settled entries first; provisional ones take no rank number.
        rows = provisional.settled_first(
            get_event_ladder(active_event), g2.is_glicko2(active_event),
            lambda e: e.games_played, lambda e: e.label,
        )[:16]

        if rows:
            leaderboard = f"🏆 **{active_event['event_name']} Leaderboard** 🏆\n"
            for rank, entry in rows:
                if rank is None:
                    leaderboard += f"- {entry.label} - {g2.provisional_label(entry.games_played)}\n"
                else:
                    leaderboard += f"#{rank}: {entry.label} - {entry.event_elo} Elo\n"
            await ctx.send(leaderboard)
        else:
            await ctx.send(f"No rankings yet for {active_event['event_name']}. Play some matches to get started!")

    @commands.command()
    async def masters_bracket(self, ctx):
        """Check the top 16 Elo rankings for masters bracket members only (admin only)."""
        from utils.checks import check_is_admin

        if not check_is_admin(ctx):
            await ctx.send("The masters bracket leaderboard is only available to admins.")
            return

        # Role IDs to filter by
        masters_role_ids = config.MASTERS_ROLE_IDS

        conn = sqlite3.connect("elo.db")
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id, user_display_name, online_elo FROM overall_standings ORDER BY online_elo DESC"
        )
        all_players = cur.fetchall()
        lifetime_glicko2 = g2.lifetime_is_glicko2(conn)
        conn.close()

        # Filter players who have one of the masters roles
        guild = ctx.guild
        if not guild:
            await ctx.send("This command can only be used in a server.")
            return

        filtered_players = []
        for user_id, display_name, elo in all_players:
            member = guild.get_member(user_id)
            if member:
                # Check if member has any of the masters roles
                has_masters = any(role.id in masters_role_ids for role in member.roles)
                if has_masters:
                    filtered_players.append((user_id, display_name, elo))

        if filtered_players:
            leaderboard = "🏆 **Masters Bracket Leaderboard** 🏆\n"
            rows = _lifetime_ranked(filtered_players, lifetime_glicko2)[:24]
            leaderboard += "".join(_lifetime_line(rank, name, elo, games) for rank, (name, elo, games) in rows)
            await ctx.send(leaderboard)
        else:
            await ctx.send("No masters bracket members found with Elo ratings!")

    @commands.command()
    async def match_elo(self, ctx, match_id=None):
        """Show event Elo before and after a specific current-event match."""
        from utils.checks import check_is_admin
        if match_id is None:
            await ctx.send("Please provide a match ID. Usage: `!match_elo <match_id>`")
            return

        try:
            parsed_match_id = int(match_id)
        except (TypeError, ValueError):
            await ctx.send("Invalid match ID. Usage: `!match_elo <match_id>`")
            return

        try:
            snapshot = get_current_event_match_elo_snapshot(parsed_match_id)
        except ValueError as exc:
            await ctx.send(str(exc))
            return
        except sqlite3.Error as exc:
            logger.error(f"Database error in match_elo command: {exc}")
            await ctx.send(
                "There was an error retrieving that match's Elo details. Please try again later."
            )
            return
        except Exception as exc:
            logger.error(f"Unexpected error in match_elo command: {exc}", exc_info=True)
            await ctx.send("An unexpected error occurred. Please try again later.")
            return

        timestamp_str = snapshot["match_timestamp"].strftime("%Y-%m-%d %H:%M")
        is_admin = check_is_admin(ctx)
        lines = [
            f"**Match #{snapshot['match_id']} Elo Snapshot**",
            f"**Event:** {snapshot['event_name']}",
            f"**Played:** {timestamp_str}",
            f"**Winner:** {snapshot['winner_display_name']}",
        ]
        if is_admin:
            lines.append(_snapshot_lifetime_line(snapshot["winner"]))
        lines.append(_snapshot_event_line(snapshot["winner"]))
        lines.append(f"**Loser:** {snapshot['loser_display_name']}")
        if is_admin:
            lines.append(_snapshot_lifetime_line(snapshot["loser"]))
        lines.append(_snapshot_event_line(snapshot["loser"]))

        if snapshot["notes"]:
            lines.append("**Notes:**")
            lines.extend(f"- {note}" for note in snapshot["notes"])

        await ctx.send("\n".join(lines))



def _lifetime_ranked(rows, glicko2: bool):
    """(rank, (name, elo, games)) for (user_id, name, elo) rows sorted by lifetime ELO.

    A Glicko-2 lifetime lists settled players first; provisional ones get no rank.
    """
    games = provisional.lifetime_games() if glicko2 else {}
    entries = [(name, elo, games.get(uid, 0)) for uid, name, elo in rows]
    return provisional.settled_first(entries, glicko2, lambda e: e[2], lambda e: e[0])


def _lifetime_line(rank, name, elo, games) -> str:
    if rank is None:
        return f"- {name} - {g2.provisional_label(games)}\n"
    return f"#{rank}: {name} - {elo} Elo\n"


def _snapshot_lifetime_line(side: dict) -> str:
    if side["lifetime_before"] is None:
        return "Lifetime: unavailable"
    if g2.change_hidden(side.get("lifetime_games")):
        return f"Lifetime: {g2.provisional_label(side['lifetime_games'])} at this match"
    return f"Lifetime: {side['lifetime_before']} -> {side['lifetime_after']}"


def _snapshot_event_line(side: dict) -> str:
    """A side's event before/after, unless that side was still provisional then."""
    if g2.change_hidden(side.get("event_games")):
        return f"Event{_avatar_label(side)}: {g2.provisional_label(side['event_games'])} at this match"
    return f"Event{_avatar_label(side)}: {side['event_before']} -> {side['event_after']}"


def _avatar_label(side: dict) -> str:
    return f" ({side['avatar']})" if side.get("avatar") else ""


def _avatar_rank_lines(active_event, user_id) -> str:
    """!rank in Avatar mode: every avatar entry the player has, with its rank."""
    from repositories.avatar_elo_repo import get_avatar_standings

    glicko2 = g2.is_glicko2(active_event)
    ranked = provisional.settled_first(
        get_avatar_standings(active_event["event_id"]), glicko2,
        lambda e: e["games_played"], lambda e: e["user_display_name"],
    )
    entries = [(rank, entry) for rank, entry in ranked if entry["user_id"] == user_id]
    header = f"**Event ELO ({active_event['event_name']}) — rated per avatar:**"
    if not entries:
        return f"{header}\nNo matches yet."
    lines = []
    for rank, entry in entries:
        games = f"{entry['games_played']} game{'s' if entry['games_played'] != 1 else ''}"
        if rank is None:
            lines.append(f"- **{entry['avatar']}:** {g2.provisional_label(entry['games_played'])}")
        else:
            lines.append(f"- **{entry['avatar']}:** {entry['event_elo']} (Rank #{rank}, {games})")
    return header + "\n" + "\n".join(lines)


async def setup(bot):
    await bot.add_cog(EloCog(bot))
