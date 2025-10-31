import discord
from discord.ext import commands
import datetime
import logging
import json
import os
from typing import Dict, List

logger = logging.getLogger("discord_bot")

# Tournament storage with file persistence
active_tournaments: Dict[int, dict] = {}  # tournament_id: tournament_data
TOURNAMENTS_FILE = "data/tournaments.json"


def find_tournament_by_name(name: str) -> tuple[int, dict] | tuple[None, None]:
    """Find a tournament by name (case-insensitive)"""
    name = name.lower()
    for tournament_id, tournament in active_tournaments.items():
        if tournament["name"].lower() == name:
            return tournament_id, tournament
    return None, None


def save_tournaments():
    """Save tournaments data to file"""
    try:
        # Ensure the data directory exists
        os.makedirs(os.path.dirname(TOURNAMENTS_FILE), exist_ok=True)

        with open(TOURNAMENTS_FILE, "w") as f:
            json.dump(active_tournaments, f, indent=4)
        logger.info("Tournaments data saved successfully")
    except Exception as e:
        logger.error(f"Error saving tournaments data: {str(e)}")


def load_tournaments():
    """Load tournaments data from file"""
    global active_tournaments
    try:
        if os.path.exists(TOURNAMENTS_FILE):
            with open(TOURNAMENTS_FILE, "r") as f:
                active_tournaments = json.load(f)
            logger.info("Tournaments data loaded successfully")
    except Exception as e:
        logger.error(f"Error loading tournaments data: {str(e)}")
        active_tournaments = {}


class TournamentSetupModal(discord.ui.Modal, title="Tournament Setup"):
    tournament_name = discord.ui.TextInput(
        label="Tournament Name", placeholder="Enter tournament name", required=True
    )

    max_players = discord.ui.TextInput(
        label="Maximum Players",
        placeholder="Enter number of players (must be power of 2)",
        required=True,
        max_length=3,
    )

    tournament_format = discord.ui.TextInput(
        label="Tournament Format",
        placeholder="Single Elimination/Double Elimination",
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            max_players = int(self.max_players.value)
            if not (max_players & (max_players - 1) == 0):
                await interaction.response.send_message(
                    "Maximum players must be a power of 2 (4, 8, 16, 32, etc).",
                    ephemeral=True,
                )
                return

            tournament_data = {
                "name": self.tournament_name.value,
                "format": self.tournament_format.value,
                "max_players": max_players,
                "players": [],
                "matches": [],
                "status": "registration",
                "winner": None,
            }

            tournament_id = len(active_tournaments) + 1
            active_tournaments[tournament_id] = tournament_data
            save_tournaments()  # Save after creating new tournament

            await interaction.response.send_message(
                f"Tournament '{self.tournament_name.value}' created! Players can join by using `!join {self.tournament_name.value}`"
            )

        except ValueError:
            await interaction.response.send_message(
                "Invalid maximum players value. Please enter a number.", ephemeral=True
            )


class TournamentMatchModal(discord.ui.Modal, title="Tournament Match Report"):
    curiosa_url = discord.ui.TextInput(
        label="Curiosa Deck URL",
        placeholder="Enter Your Curiosa Deck URL",
        required=False,
    )

    first_player = discord.ui.TextInput(
        label="Did you go first? (y/n)",
        placeholder="Enter YES or NO",
        required=False,
        max_length=3,
    )

    match_time = discord.ui.TextInput(
        label="Match time",
        placeholder="Estimate match time in minutes (eg. 30)",
        required=False,
        max_length=3,
        min_length=1,
    )

    match_comment = discord.ui.TextInput(
        label="Notes",
        placeholder="Anything else about the match?",
        style=discord.TextStyle.paragraph,
        required=False,
    )

    def __init__(
        self, tournament_id: int, match_id: int, is_winner: bool, tournament_name: str
    ):
        super().__init__()
        self.tournament_id = tournament_id
        self.match_id = match_id
        self.is_winner = is_winner
        self.tournament_name = tournament_name

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        # Get the tournament and match data
        tournament = active_tournaments.get(self.tournament_id)
        match = next(
            (m for m in tournament["matches"] if m["id"] == self.match_id), None
        )

        # Record match details
        curiosa_link = (
            self.curiosa_url.value if self.curiosa_url.value else "No URL provided"
        )
        match_comment = self.match_comment.value if self.match_comment.value else ""
        first_player = self.first_player.value if self.first_player.value else "n"
        match_time = (
            int(self.match_time.value) if self.match_time.value.isdigit() else 0
        )

        # Update match with winner
        if self.is_winner:
            match["winner"] = interaction.user.id
        else:
            opponent_id = (
                match["player2"]
                if interaction.user.id == match["player1"]
                else match["player1"]
            )
            match["winner"] = opponent_id

        match["status"] = "completed"
        match["details"] = {
            "curiosa_url": curiosa_link,
            "first_player": first_player,
            "match_time": match_time,
            "match_comment": match_comment,
            "reported_by": interaction.user.id,
        }
        save_tournaments()

        # Get opponent name for the database record
        opponent_id = (
            match["player2"]
            if interaction.user.id == match["player1"]
            else match["player1"]
        )
        try:
            opponent = await interaction.client.fetch_user(opponent_id)
            opponent_name = opponent.global_name or opponent.name
        except Exception as e:
            logger.warning(
                f"Could not fetch opponent name for ID {opponent_id}: {str(e)}"
            )
            opponent_name = str(opponent_id)

        # Save to solo_match_reports table
        from utils.database import solo_match_report

        solo_match_report(
            reporter_id=interaction.user.id,
            reporter_global=interaction.user.global_name or interaction.user.name,
            opponent_name=opponent_name,
            is_winner=self.is_winner,
            first_player=first_player,
            match_time=match_time,
            curiosa_link=curiosa_link,
            match_comment=f"[Tournament: {self.tournament_name}] {match_comment}",
        )

        await interaction.followup.send(
            f"✅ Tournament match report submitted for {self.tournament_name} Round {match['round']}!\n"
            f"**Deck URL:** {curiosa_link}\n"
            f"**Match Time:** {match_time} minutes",
            ephemeral=True,
        )


class MatchReportButton(discord.ui.View):
    def __init__(self, tournament_id: int, match_id: int, user_id: int):
        super().__init__(timeout=300)  # 5 minute timeout
        self.tournament_id = tournament_id
        self.match_id = match_id
        self.user_id = user_id
        self.disabled = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This is not your match result to report!", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        # Disable all buttons when the view times out
        for item in self.children:
            item.disabled = True
        # Try to edit the message if it still exists
        try:
            if hasattr(self, "message"):
                await self.message.edit(view=self)
        except discord.NotFound:
            pass

    @discord.ui.button(label="I Won! 🏆", style=discord.ButtonStyle.green)
    async def report_win(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.disabled:
            await interaction.response.send_message(
                "This match has already been reported!", ephemeral=True
            )
            return

        tournament = active_tournaments.get(self.tournament_id)
        if not tournament:
            await interaction.response.send_message(
                "Tournament not found!", ephemeral=True
            )
            return

        match = next(
            (m for m in tournament["matches"] if m["id"] == self.match_id), None
        )
        if not match or match["status"] == "completed":
            await interaction.response.send_message(
                "Match not found or already completed!", ephemeral=True
            )
            return

        # Send modal for detailed match report
        await interaction.response.send_modal(
            TournamentMatchModal(
                tournament_id=self.tournament_id,
                match_id=self.match_id,
                is_winner=True,
                tournament_name=tournament["name"],
            )
        )

        logger.info(
            f"Win button clicked by {interaction.user.name} (ID: {interaction.user.id})"
        )
        logger.info(f"Tournament ID: {self.tournament_id}, Match ID: {self.match_id}")

        tournament = active_tournaments.get(self.tournament_id)
        if not tournament:
            logger.error(
                f"Tournament {self.tournament_id} not found in active tournaments"
            )
            await interaction.response.send_message(
                "Tournament not found!", ephemeral=True
            )
            return

        match = next(
            (m for m in tournament["matches"] if m["id"] == self.match_id), None
        )
        if not match:
            logger.error(
                f"Match {self.match_id} not found in tournament {self.tournament_id}"
            )
            await interaction.response.send_message("Match not found!", ephemeral=True)
            return

        if match["status"] == "completed":
            await interaction.response.send_message(
                "This match has already been reported!", ephemeral=True
            )
            return

        logger.info(
            f"Match found - Round: {match['round']}, Players: {match['player1']} vs {match['player2']}"
        )
        if interaction.user.id not in [match["player1"], match["player2"]]:
            logger.warning(
                f"Unauthorized win report attempt by {interaction.user.id} for match {self.match_id}"
            )
            await interaction.response.send_message(
                "You are not part of this match!", ephemeral=True
            )
            return

        # Update match with winner
        match["winner"] = interaction.user.id
        match["status"] = "completed"
        save_tournaments()

        # Get opponent for the announcement
        opponent_id = (
            match["player2"]
            if interaction.user.id == match["player1"]
            else match["player1"]
        )
        try:
            opponent = await interaction.client.fetch_user(opponent_id)
            victory_message = f"Victory recorded for {interaction.user.mention} against {opponent.mention} in round {match['round']}!"
        except discord.NotFound:
            victory_message = f"Victory recorded for {interaction.user.name}!"

        # Update the bracket display
        try:
            cog = interaction.client.get_cog("TournamentCog")
            if cog:
                logger.info("Generating updated bracket display")
                bracket_display = await cog.generate_bracket_display(tournament)
                if interaction.message:
                    await interaction.message.edit(content=bracket_display)
                    logger.info("Successfully updated bracket display")
                else:
                    logger.warning(
                        "Could not update bracket - interaction message not found"
                    )
            else:
                logger.error("TournamentCog not found - cannot update bracket display")
        except Exception as e:
            logger.error(f"Error updating bracket display: {str(e)}")

        # Check if the round is complete and create next round matches if needed
        current_round = match["round"]
        round_matches = [
            m for m in tournament["matches"] if m["round"] == current_round
        ]
        all_completed = all(m["status"] == "completed" for m in round_matches)

        if all_completed:
            winners_count = len([m for m in round_matches if m["winner"] is not None])
            if winners_count >= 2:  # Need at least 2 winners to create a new match
                cog = interaction.client.get_cog("TournamentCog")
                if cog:
                    new_matches = await cog.create_next_round_match(
                        tournament, round_matches
                    )
                    if new_matches:
                        victory_message += (
                            "\n\nNext round matches have been created! Use `!bracket"
                            + f" {tournament['name']}`"
                            + " to view the updated bracket."
                        )

        # Disable both buttons after a result is reported
        self.disabled = True
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

        await interaction.response.send_message(victory_message)

    @discord.ui.button(label="I Lost 😢", style=discord.ButtonStyle.red)
    async def report_loss(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.disabled:
            await interaction.response.send_message(
                "This match has already been reported!", ephemeral=True
            )
            return

        tournament = active_tournaments.get(self.tournament_id)
        if not tournament:
            await interaction.response.send_message(
                "Tournament not found!", ephemeral=True
            )
            return

        match = next(
            (m for m in tournament["matches"] if m["id"] == self.match_id), None
        )
        if not match or match["status"] == "completed":
            await interaction.response.send_message(
                "Match not found or already completed!", ephemeral=True
            )
            return

        # Send modal for detailed match report
        await interaction.response.send_modal(
            TournamentMatchModal(
                tournament_id=self.tournament_id,
                match_id=self.match_id,
                is_winner=False,
                tournament_name=tournament["name"],
            )
        )

        logger.info(
            f"Loss button clicked by {interaction.user.name} (ID: {interaction.user.id})"
        )
        logger.info(f"Tournament ID: {self.tournament_id}, Match ID: {self.match_id}")

        tournament = active_tournaments.get(self.tournament_id)
        if not tournament:
            logger.error(
                f"Tournament {self.tournament_id} not found in active tournaments"
            )
            await interaction.response.send_message(
                "Tournament not found!", ephemeral=True
            )
            return

        match = next(
            (m for m in tournament["matches"] if m["id"] == self.match_id), None
        )
        if not match:
            logger.error(
                f"Match {self.match_id} not found in tournament {self.tournament_id}"
            )
            await interaction.response.send_message("Match not found!", ephemeral=True)
            return

        if match["status"] == "completed":
            await interaction.response.send_message(
                "This match has already been reported!", ephemeral=True
            )
            return

        # Get opponent as the winner
        opponent_id = (
            match["player2"]
            if interaction.user.id == match["player1"]
            else match["player1"]
        )
        match["winner"] = opponent_id
        match["status"] = "completed"
        save_tournaments()

        try:
            opponent = await interaction.client.fetch_user(opponent_id)
            loss_message = f"Match result recorded: {opponent.mention} won against {interaction.user.mention} in round {match['round']}!"
        except discord.NotFound:
            loss_message = f"Match result recorded: You lost in round {match['round']}!"

        # Update the bracket display
        try:
            cog = interaction.client.get_cog("TournamentCog")
            if cog:
                logger.info("Generating updated bracket display")
                bracket_display = await cog.generate_bracket_display(tournament)
                if interaction.message:
                    await interaction.message.edit(content=bracket_display)
                    logger.info("Successfully updated bracket display")
                else:
                    logger.warning(
                        "Could not update bracket - interaction message not found"
                    )
            else:
                logger.error("TournamentCog not found - cannot update bracket display")
        except Exception as e:
            logger.error(f"Error updating bracket display: {str(e)}")

        # Check if the round is complete and create next round matches if needed
        current_round = match["round"]
        round_matches = [
            m for m in tournament["matches"] if m["round"] == current_round
        ]
        all_completed = all(m["status"] == "completed" for m in round_matches)

        if all_completed:
            winners_count = len([m for m in round_matches if m["winner"] is not None])
            if winners_count >= 2:  # Need at least 2 winners to create a new match
                cog = interaction.client.get_cog("TournamentCog")
                if cog:
                    new_matches = await cog.create_next_round_match(
                        tournament, round_matches
                    )
                    if new_matches:
                        loss_message += (
                            "\n\nNext round matches have been created! Use `!bracket"
                            + f" {tournament['name']}`"
                            + " to view the updated bracket."
                        )

        # Disable both buttons after a result is reported
        self.disabled = True
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

        await interaction.response.send_message(loss_message)


class CreateTournamentButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)  # 5 minute timeout

    @discord.ui.button(label="Create Tournament", style=discord.ButtonStyle.primary)
    async def create_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        modal = TournamentSetupModal()
        await interaction.response.send_modal(modal)
        await interaction.message.edit(view=None)  # Remove the button after clicking


class TournamentCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Load existing tournaments when the cog is initialized
        load_tournaments()

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def create_tournament(self, ctx):
        """Create a new tournament (Admin only)"""
        # Clear existing tournaments
        global active_tournaments
        active_tournaments.clear()
        save_tournaments()

        view = CreateTournamentButton()
        await ctx.send(
            "Previous tournament cleared. Click the button below to create a new tournament:",
            view=view,
        )

    @commands.command()
    async def join(self, ctx, *, tournament_name: str):
        """Join a tournament by name"""
        tournament_id, tournament = find_tournament_by_name(tournament_name)
        if not tournament:
            await ctx.send(
                "Tournament not found! Please check the exact tournament name."
            )
            return

        if tournament["status"] != "registration":
            await ctx.send("Tournament is not accepting registrations!")
            return

        if len(tournament["players"]) >= tournament["max_players"]:
            await ctx.send("Tournament is full!")
            return

        if ctx.author.id in tournament["players"]:
            await ctx.send("You are already registered!")
            return

        tournament["players"].append(ctx.author.id)
        save_tournaments()  # Save after adding player
        await ctx.send(
            f"You have joined {tournament['name']}! ({len(tournament['players'])}/{tournament['max_players']} players)"
        )

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def start_tournament(self, ctx, *, tournament_name: str):
        """Start a tournament by name (Admin only)"""
        try:
            logger.info(
                f"Attempting to start tournament '{tournament_name}' by {ctx.author}"
            )

            tournament_id, tournament = find_tournament_by_name(tournament_name)
            if not tournament:
                logger.warning(
                    f"Tournament '{tournament_name}' not found when attempted to start by {ctx.author}"
                )
                await ctx.send(
                    "Tournament not found! Please check the exact tournament name."
                )
                return

            tournament = active_tournaments[tournament_id]
            if tournament["status"] != "registration":
                logger.warning(
                    f"Tournament {tournament_id} already started when attempted by {ctx.author}"
                )
                await ctx.send("Tournament has already started!")
                return

            if len(tournament["players"]) < 2:
                logger.warning(
                    f"Tournament {tournament_id} has insufficient players ({len(tournament['players'])}) when start attempted by {ctx.author}"
                )
                await ctx.send("Not enough players to start tournament!")
                return

            # Generate first round matches
            import random

            players = tournament["players"].copy()
            random.shuffle(players)
            logger.info(
                f"Generated matchups for tournament {tournament_id} with {len(players)} players"
            )

            matches = []
            for i in range(0, len(players), 2):
                if i + 1 < len(players):
                    matches.append(
                        {
                            "id": len(matches) + 1,
                            "round": 1,
                            "player1": players[i],
                            "player2": players[i + 1],
                            "winner": None,
                            "status": "pending",
                        }
                    )

            tournament["matches"] = matches
            tournament["status"] = "in_progress"
            save_tournaments()  # Save after starting tournament
            logger.info(
                f"Created {len(matches)} matches for tournament {tournament_id}"
            )

            # Send match notifications
            for match in matches:
                try:
                    player1 = await self.bot.fetch_user(match["player1"])
                    player2 = await self.bot.fetch_user(match["player2"])

                    match_msg = f"Round 1 Match: {player1.mention} vs {player2.mention}\nUse `!my_round` to view your match and report your win!"
                    await ctx.send(match_msg)
                    logger.info(
                        f"Sent match notification for match {match['id']} in tournament {tournament_id}"
                    )
                except discord.NotFound:
                    logger.error(
                        f"Failed to fetch user for match {match['id']} in tournament {tournament_id}"
                    )
                    await ctx.send(
                        f"Error: Could not fetch user information for match {match['id']}"
                    )
                except Exception as e:
                    logger.error(
                        f"Error sending match notification for match {match['id']} in tournament {tournament_id}: {str(e)}"
                    )
                    await ctx.send(
                        f"Error sending match notification for match {match['id']}"
                    )

            logger.info(f"Successfully started tournament {tournament_id}")

        except Exception as e:
            logger.error(
                f"Error starting tournament {tournament_id}: {str(e)}", exc_info=True
            )
            await ctx.send(
                "An error occurred while starting the tournament. Please check the logs or contact an administrator."
            )

    @commands.command()
    async def create_next_round_match(self, tournament, prev_round_matches):
        """Create matches for the next round based on winners"""
        next_round = prev_round_matches[0]["round"] + 1
        winners = []

        # Get winners from the previous round in order
        for match in sorted(prev_round_matches, key=lambda m: m["id"]):
            if match["winner"] is not None:
                winners.append(match["winner"])

        # Create new matches pairing winners
        new_matches = []
        for i in range(0, len(winners), 2):
            if i + 1 < len(winners):
                match_id = len(tournament["matches"]) + 1
                new_matches.append(
                    {
                        "id": match_id,
                        "round": next_round,
                        "player1": winners[i],
                        "player2": winners[i + 1],
                        "winner": None,
                        "status": "pending",
                    }
                )

        if new_matches:
            tournament["matches"].extend(new_matches)
            save_tournaments()
            return new_matches
        return []

    @commands.command()
    async def check_round_completion(self, ctx, *, tournament_name: str):
        """Check if a round is complete and create next round if needed"""
        # Find the tournament
        tournament_id, tournament = find_tournament_by_name(tournament_name)
        if not tournament:
            await ctx.send(
                "Tournament not found! Please check the exact tournament name."
            )
            return

        # Get current round (highest round number with pending matches)
        current_round = max(
            (m["round"] for m in tournament["matches"] if m["status"] == "pending"),
            default=1,
        )

        # Get matches for the current round
        round_matches = [
            m for m in tournament["matches"] if m["round"] == current_round
        ]

        if not round_matches:
            await ctx.send(
                f"No matches found for round {current_round} in tournament {tournament_name}."
            )
            return

        # Count completed and pending matches
        completed_matches = [m for m in round_matches if m["status"] == "completed"]
        pending_matches = [m for m in round_matches if m["status"] == "pending"]

        # Create status message
        status_msg = f"**Round {current_round} Status for {tournament_name}**\n"
        status_msg += f"Total Matches: {len(round_matches)}\n"
        status_msg += f"Completed: {len(completed_matches)}/{len(round_matches)}\n"
        status_msg += f"Pending: {len(pending_matches)}/{len(round_matches)}\n\n"

        # Add details about pending matches
        if pending_matches:
            status_msg += "**Pending Matches:**\n"
            for match in pending_matches:
                try:
                    player1 = await ctx.bot.fetch_user(match["player1"])
                    player2 = await ctx.bot.fetch_user(match["player2"])
                    status_msg += f"• {player1.name} vs {player2.name}\n"
                except discord.NotFound:
                    status_msg += "• Unknown Players\n"

        all_completed = len(pending_matches) == 0
        if all_completed and len(round_matches) >= 2:
            # Create next round matches
            new_matches = await self.create_next_round_match(tournament, round_matches)
            if new_matches:
                status_msg += f"\n✅ Round {current_round} is complete! Next round matches have been created."
            else:
                status_msg += f"\n✅ Round {current_round} is complete!"
        elif all_completed:
            status_msg += f"\n🏆 Tournament complete! Use `!complete_tournament {tournament_name}` to finalize."
        else:
            status_msg += "\n⏳ Waiting for remaining matches to complete."

        await ctx.send(status_msg)

    @commands.command()
    async def my_round(self, ctx):
        """View your current match and report your win"""
        # Find the player's current active match across all tournaments
        player_match = None
        print("Checking active tournaments for player match...")

        for tournament in active_tournaments.values():
            if tournament["status"] != "in_progress":
                continue

            for match in tournament["matches"]:
                if match["status"] == "pending" and ctx.author.id in [
                    match["player1"],
                    match["player2"],
                ]:
                    player_match = match
                    pass  # Tournament found, continue with the code below
                    break
            if player_match:
                break

        if not player_match:
            await ctx.send("You don't have any active matches at the moment!")
            return

        # Find the tournament this match belongs to
        tournament_id = None
        for t_id, tournament in active_tournaments.items():
            if any(m["id"] == player_match["id"] for m in tournament["matches"]):
                tournament_id = t_id
                break

        if player_match["status"] == "completed":
            await ctx.send("This match has already been completed!")
            return

        # Get the opponent's user object for the match display
        opponent_id = (
            player_match["player2"]
            if ctx.author.id == player_match["player1"]
            else player_match["player1"]
        )
        opponent = await self.bot.fetch_user(opponent_id)

        # Create an embed to display the match
        embed = discord.Embed(
            title=f"Round {player_match['round']} Match",
            description=f"{ctx.author.mention} vs {opponent.mention}\n\n⏰ You have 5 minutes to report the match result.",
            color=discord.Color.blue(),
        )

        # Send the match information with a report button
        view = MatchReportButton(tournament_id, player_match["id"], ctx.author.id)
        message = await ctx.send(embed=embed, view=view)

        # Store message reference for timeout handling
        view.message = message

        # Return to let the button handle the win reporting
        return

    @commands.command()
    async def find_tournament_winner(self, tournament):
        """Helper method to find the winner of a tournament"""
        if not tournament["matches"]:
            return None

        # Get matches from the last round
        max_round = max(match["round"] for match in tournament["matches"])
        final_matches = [m for m in tournament["matches"] if m["round"] == max_round]

        if not final_matches or len(final_matches) > 1:
            return None  # No finals match or multiple matches in final round

        final_match = final_matches[0]
        if final_match["winner"] is None:
            return None  # Final match not completed

        return final_match["winner"]

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def complete_tournament(self, ctx, *, tournament_name: str):
        """Complete a tournament and announce the winner (Admin only)"""
        tournament_id, tournament = find_tournament_by_name(tournament_name)
        if not tournament:
            await ctx.send(
                "Tournament not found! Please check the exact tournament name."
            )
            return

        if tournament["status"] != "in_progress":
            await ctx.send("Tournament is not in progress!")
            return

        # Check if all matches are completed and identify rounds with pending matches
        incomplete_matches = [
            m for m in tournament["matches"] if m["status"] != "completed"
        ]
        if incomplete_matches:
            # Group incomplete matches by round
            rounds_pending = {}
            for match in incomplete_matches:
                round_num = match["round"]
                if round_num not in rounds_pending:
                    rounds_pending[round_num] = []
                rounds_pending[round_num].append(match)

            # Create detailed message about pending matches
            pending_details = []
            for round_num, matches in sorted(rounds_pending.items()):
                match_details = []
                for match in matches:
                    try:
                        player1 = await self.bot.fetch_user(match["player1"])
                        player2 = await self.bot.fetch_user(match["player2"])
                        match_details.append(f"{player1.name} vs {player2.name}")
                    except discord.NotFound:
                        match_details.append("Unknown Players")

                pending_details.append(
                    f"Round {round_num}: {len(matches)} match(es) pending\n"
                    f"• " + "\n• ".join(match_details)
                )

            message = "Cannot complete tournament - the following matches still need to be played:\n\n"
            message += "\n\n".join(pending_details)
            await ctx.send(message)
            return

        # Find the winner
        winner_id = await self.find_tournament_winner(tournament)
        if not winner_id:
            await ctx.send("Error: Could not determine tournament winner!")
            return

        try:
            winner = await self.bot.fetch_user(winner_id)

            # Update tournament status
            tournament["status"] = "completed"
            tournament["winner"] = winner_id
            save_tournaments()

            # Create winner announcement embed
            embed = discord.Embed(
                title=f"🏆 Tournament Complete: {tournament['name']}",
                description=f"Congratulations to our champion: {winner.mention}!",
                color=discord.Color.gold(),
            )

            embed.add_field(
                name="Tournament Stats",
                value=f"Total Players: {len(tournament['matches'])}\nTotal Matches: {len(tournament['matches'])}",
                inline=False,
            )

            await ctx.send(embed=embed)

        except discord.NotFound:
            await ctx.send("Error: Could not fetch winner information!")
        except Exception as e:
            logger.error(f"Error completing tournament: {str(e)}")
            await ctx.send("An error occurred while completing the tournament.")

    @commands.command()
    async def bracket(self, ctx, *, tournament_name: str):
        """View the current tournament bracket in a visual format"""
        tournament_id, tournament = find_tournament_by_name(tournament_name)
        if not tournament:
            await ctx.send(
                "Tournament not found! Please check the exact tournament name."
            )
            return

        # Prepare description with winner if tournament is completed
        description = f"Status: {tournament['status']}\n"
        description += (
            f"Players: {len(tournament['players'])}/{tournament['max_players']}"
        )

        if tournament["status"] == "completed" and tournament.get("winner"):
            try:
                winner = await self.bot.fetch_user(tournament["winner"])
                description += f"\n🏆 Champion: {winner.name}"
            except discord.NotFound:
                description += "\n🏆 Champion: Unknown"

        embed = discord.Embed(
            title=f"🏆 Tournament: {tournament['name']}",
            description=description,
            color=discord.Color.gold()
            if tournament["status"] == "completed"
            else discord.Color.blue(),
        )

        # Add list of registered players
        registered_players = []
        for player_id in tournament['players']:
            try:
                player = await self.bot.fetch_user(player_id)
                registered_players.append(player.name)
            except discord.NotFound:
                registered_players.append(f"Unknown Player ({player_id})")

        # Sort players alphabetically
        registered_players.sort()
        
        # Split into columns if many players
        if len(registered_players) > 10:
            # Create two columns
            half = (len(registered_players) + 1) // 2
            col1 = registered_players[:half]
            col2 = registered_players[half:]
            
            # Format columns with padding
            max_len = max(len(name) for name in registered_players)
            player_list = ""
            for i in range(max(len(col1), len(col2))):
                row = ""
                if i < len(col1):
                    row += f"{col1[i]:<{max_len}}"
                if i < len(col2):
                    row += "  " + col2[i]
                player_list += row + "\n"
        else:
            # Single column for fewer players
            player_list = "\n".join(registered_players)

        embed.add_field(
            name="Registered Players",
            value=f"```\n{player_list}```",
            inline=False
        )

        if not tournament["matches"]:
            embed.add_field(
                name="Bracket",
                value="No matches have been scheduled yet.",
                inline=False,
            )
            await ctx.send(embed=embed)
            return

        # Group matches by round
        matches_by_round = {}
        max_round = 1
        for match in tournament["matches"]:
            round_num = match["round"]
            if round_num not in matches_by_round:
                matches_by_round[round_num] = []
            matches_by_round[round_num].append(match)
            max_round = max(max_round, round_num)

        # Create visual bracket for each round
        for round_num in range(1, max_round + 1):
            round_matches = matches_by_round.get(round_num, [])
            bracket_lines = []

            for match in round_matches:
                try:
                    player1 = await self.bot.fetch_user(match["player1"])
                    player2 = await self.bot.fetch_user(match["player2"])

                    # Format player names with status indicators
                    p1_name = player1.name[:20]  # Truncate long names
                    p2_name = player2.name[:20]

                    if match["winner"] is not None:
                        if match["winner"] == player1.id:
                            p1_name = f"✅ {p1_name}"
                            p2_name = f"❌ {p2_name}"
                        else:
                            p1_name = f"❌ {p1_name}"
                            p2_name = f"✅ {p2_name}"

                    # Create match display
                    bracket_lines.append("┌─" + "─" * 24 + "┐")
                    bracket_lines.append(f"│ {p1_name:<22} │")
                    bracket_lines.append(f"├─{'vs':^24}┤")
                    bracket_lines.append(f"│ {p2_name:<22} │")
                    bracket_lines.append("└─" + "─" * 24 + "┘")
                    bracket_lines.append("")  # Add space between matches

                except discord.NotFound:
                    continue
                except Exception as e:
                    logger.error(f"Error displaying match in bracket: {str(e)}")
                    continue

            if bracket_lines:
                round_display = "```\n" + "\n".join(bracket_lines) + "```"
                embed.add_field(
                    name=f"Round {round_num}", value=round_display, inline=False
                )

        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def remove(self, ctx, tournament_name: str, member: discord.Member):
        """Remove a player from a tournament (Admin only)"""
        tournament_id, tournament = find_tournament_by_name(tournament_name)
        if not tournament:
            await ctx.send(
                "Tournament not found! Please check the exact tournament name."
            )
            return

        if tournament["status"] != "registration":
            await ctx.send("Players can only be removed during registration phase!")
            return

        if member.id not in tournament["players"]:
            await ctx.send(f"{member.name} is not registered in this tournament!")
            return

        # Remove the player
        tournament["players"].remove(member.id)
        save_tournaments()

        await ctx.send(
            f"Successfully removed {member.name} from {tournament['name']}! ({len(tournament['players'])}/{tournament['max_players']} players)"
        )

    @commands.command()
    async def tournament_help(self, ctx):
        """Show help information for all tournament commands"""
        embed = discord.Embed(
            title="Tournament Commands Help",
            description="Here are all the available tournament commands:",
            color=discord.Color.blue(),
        )

        # Admin Commands
        admin_commands = (
            "`!create_tournament` - Create a new tournament (Admin only)\n"
            "`!start_tournament <name>` - Start a tournament with registered players (Admin only)\n"
            "`!complete_tournament <name>` - Complete and finalize a tournament (Admin only)\n"
            "`!remove <name> @user` - Remove a player from a tournament (Admin only)\n"
        )
        embed.add_field(name="🛡️ Admin Commands", value=admin_commands, inline=False)

        # Player Commands
        player_commands = (
            "`!join <tournament_name>` - Join a tournament during registration\n"
            "`!my_round` - View your current match and report results\n"
            "`!bracket <tournament_name>` - View the current tournament bracket\n"
        )
        embed.add_field(name="👥 Player Commands", value=player_commands, inline=False)

        # Usage Examples
        examples = (
            "**Example Usage:**\n"
            "1. Admin creates tournament: `!create_tournament`\n"
            "2. Players join: `!join tournament_name`\n"
            "3. Admin starts: `!start_tournament tournament_name`\n"
            "4. Players check matches: `!my_round`\n"
            "5. View progress: `!bracket tournament_name`\n"
        )
        embed.add_field(name="📝 Examples", value=examples, inline=False)

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(TournamentCog(bot))
