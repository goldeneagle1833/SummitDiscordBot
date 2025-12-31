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
        if not tournament:
            await interaction.followup.send("Tournament not found!", ephemeral=True)
            return

        match = next(
            (m for m in tournament["matches"] if m["id"] == self.match_id), None
        )
        if not match:
            await interaction.followup.send("Match not found!", ephemeral=True)
            return

        # Validate that the user is actually part of this specific match
        if interaction.user.id not in [match["player1"], match["player2"]]:
            logger.warning(
                f"Unauthorized match report attempt by {interaction.user.id} for match {self.match_id}"
            )
            await interaction.followup.send(
                "You are not part of this match!", ephemeral=True
            )
            return

        # Check if match is already completed
        if match["status"] == "completed":
            await interaction.followup.send(
                "This match has already been reported!", ephemeral=True
            )
            return

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

        logger.info(
            f"Match {self.match_id} completed - Winner: {match['winner']}, Round: {match['round']}, Tournament: {self.tournament_name}"
        )

        # Immediately try to pair winner with another winner for next round
        winner_id = match["winner"]
        current_round = match["round"]

        # Try to create next round match immediately
        next_match_created = False
        try:
            cog = interaction.client.get_cog("TournamentCog")
            if cog:
                next_match_created = await cog.try_pair_winner_immediately(
                    tournament, winner_id, current_round
                )
        except Exception as e:
            logger.error(f"Error trying to pair winner immediately: {str(e)}")

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

        # Create result message
        result_message = f"✅ Tournament match report submitted for {self.tournament_name} Round {match['round']}!\n"
        result_message += f"**Winner:** {'You' if self.is_winner else opponent_name}\n"
        result_message += f"**Deck URL:** {curiosa_link}\n"
        result_message += f"**Match Time:** {match_time} minutes"

        # Add immediate pairing notification if applicable
        if next_match_created and self.is_winner:
            result_message += (
                "\n\n🎮 **You've been immediately paired for the next round!**"
            )
            result_message += (
                f"\nUse `/tournament match_report` to view your next opponent!"
            )
        elif self.is_winner:
            result_message += "\n\n⏳ **Waiting for another winner to advance...**"
            result_message += (
                "\nYou'll be automatically paired once another player wins!"
            )

        # Check if the round is complete and create next round matches if needed
        current_round = match["round"]
        round_matches = [
            m for m in tournament["matches"] if m["round"] == current_round
        ]
        all_completed = all(m["status"] == "completed" for m in round_matches)

        if all_completed:
            winners_count = len([m for m in round_matches if m["winner"] is not None])
            if winners_count >= 2:  # Need at least 2 winners to create a new match
                try:
                    cog = interaction.client.get_cog("TournamentCog")
                    if cog:
                        new_matches = await cog.create_next_round_match(
                            tournament, round_matches
                        )
                        if new_matches:
                            result_message += (
                                f"\n\n🎉 Round {current_round} is complete! "
                                f"Next round matches have been created. "
                                f"Use `!my_round` to view your next match!"
                            )
                        else:
                            result_message += "\n\n🏆 Tournament complete! Congratulations to the winner!"
                    else:
                        logger.error(
                            "TournamentCog not found - cannot create next round matches"
                        )
                except Exception as e:
                    logger.error(f"Error creating next round matches: {str(e)}")

        # Disable the buttons for this match to prevent duplicate submissions
        try:
            # We need to find and disable the view that created this modal
            # This is a bit tricky since we don't have a direct reference
            # The interaction should be from the modal, but we need to handle this differently
            pass  # Button disabling will be handled by the view timeout or other mechanisms
        except Exception as e:
            logger.error(f"Error disabling buttons after match submission: {str(e)}")

        await interaction.followup.send(result_message, ephemeral=True)


class MatchReportButton(discord.ui.View):
    def __init__(self, tournament_id: int, match_id: int, user_id: int):
        super().__init__(timeout=300)  # 5 minute timeout
        self.tournament_id = tournament_id
        self.match_id = match_id
        self.user_id = user_id
        self.disabled = False

    def validate_match_state(self) -> tuple[bool, str]:
        """Validate that the match is still in a reportable state"""
        tournament = active_tournaments.get(self.tournament_id)
        if not tournament:
            return False, "Tournament not found!"

        match = next(
            (m for m in tournament["matches"] if m["id"] == self.match_id), None
        )
        if not match:
            return False, "Match not found!"

        if match["status"] == "completed":
            return False, "This match has already been reported!"

        return True, ""

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
        # Validate match state first
        is_valid, error_message = self.validate_match_state()
        if not is_valid:
            await interaction.response.send_message(error_message, ephemeral=True)
            return

        if self.disabled:
            await interaction.response.send_message(
                "This match has already been reported!", ephemeral=True
            )
            return

        # Get fresh tournament and match data
        tournament = active_tournaments.get(self.tournament_id)
        match = next(
            (m for m in tournament["matches"] if m["id"] == self.match_id), None
        )

        # Validate that the user is actually part of this specific match
        if interaction.user.id not in [match["player1"], match["player2"]]:
            logger.warning(
                f"Unauthorized win report attempt by {interaction.user.id} for match {self.match_id} in tournament {tournament['name']}"
            )
            await interaction.response.send_message(
                "You are not part of this match!", ephemeral=True
            )
            return

        logger.info(
            f"Win button clicked by {interaction.user.name} (ID: {interaction.user.id}) for Match ID: {self.match_id} in tournament {tournament['name']}"
        )

        # Disable buttons to prevent double-submission
        self.disabled = True
        for child in self.children:
            child.disabled = True

        # Send modal for detailed match report
        await interaction.response.send_modal(
            TournamentMatchModal(
                tournament_id=self.tournament_id,
                match_id=self.match_id,
                is_winner=True,
                tournament_name=tournament["name"],
            )
        )

        # Update the message to show disabled buttons
        try:
            await interaction.edit_original_response(view=self)
        except Exception as e:
            logger.warning(f"Could not update button state: {str(e)}")

    @discord.ui.button(label="I Lost 😢", style=discord.ButtonStyle.red)
    async def report_loss(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Validate match state first
        is_valid, error_message = self.validate_match_state()
        if not is_valid:
            await interaction.response.send_message(error_message, ephemeral=True)
            return

        if self.disabled:
            await interaction.response.send_message(
                "This match has already been reported!", ephemeral=True
            )
            return

        # Get fresh tournament and match data
        tournament = active_tournaments.get(self.tournament_id)
        match = next(
            (m for m in tournament["matches"] if m["id"] == self.match_id), None
        )

        # Validate that the user is actually part of this specific match
        if interaction.user.id not in [match["player1"], match["player2"]]:
            logger.warning(
                f"Unauthorized loss report attempt by {interaction.user.id} for match {self.match_id} in tournament {tournament['name']}"
            )
            await interaction.response.send_message(
                "You are not part of this match!", ephemeral=True
            )
            return

        logger.info(
            f"Loss button clicked by {interaction.user.name} (ID: {interaction.user.id}) for Match ID: {self.match_id} in tournament {tournament['name']}"
        )

        # Disable buttons to prevent double-submission
        self.disabled = True
        for child in self.children:
            child.disabled = True

        # Send modal for detailed match report
        await interaction.response.send_modal(
            TournamentMatchModal(
                tournament_id=self.tournament_id,
                match_id=self.match_id,
                is_winner=False,
                tournament_name=tournament["name"],
            )
        )

        # Update the message to show disabled buttons
        try:
            await interaction.edit_original_response(view=self)
        except Exception as e:
            logger.warning(f"Could not update button state: {str(e)}")


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
    async def try_pair_winner_immediately(self, tournament, winner_id, completed_round):
        """
        Try to immediately pair a winner with another available winner from the same round.
        This allows players to advance without waiting for all round matches to complete.
        """
        # Get all matches from the completed round
        round_matches = [
            m for m in tournament["matches"] if m["round"] == completed_round
        ]

        # Find other completed matches from this round that have winners
        other_winners = []
        for m in round_matches:
            if (
                m["status"] == "completed"
                and m["winner"] is not None
                and m["winner"] != winner_id
            ):
                # Check if this winner is not already paired in next round
                already_paired = any(
                    next_m["round"] == completed_round + 1
                    and m["winner"] in [next_m["player1"], next_m["player2"]]
                    for next_m in tournament["matches"]
                )
                if not already_paired:
                    other_winners.append(m["winner"])

        # Check if current winner is already paired
        winner_already_paired = any(
            m["round"] == completed_round + 1
            and winner_id in [m["player1"], m["player2"]]
            for m in tournament["matches"]
        )

        if winner_already_paired:
            logger.info(f"Winner {winner_id} already paired in next round")
            return False

        # If we have another unpaired winner, create the next round match immediately
        if other_winners:
            opponent_id = other_winners[0]  # Take first available winner
            next_round = completed_round + 1
            match_id = len(tournament["matches"]) + 1

            new_match = {
                "id": match_id,
                "round": next_round,
                "player1": winner_id,
                "player2": opponent_id,
                "winner": None,
                "status": "pending",
            }

            tournament["matches"].append(new_match)
            save_tournaments()

            logger.info(
                f"Immediately created next round match: {winner_id} vs {opponent_id} "
                f"(Round {next_round})"
            )
            return True

        return False

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

    @commands.command(aliases=["match", "tournament_match"])
    async def my_round(self, ctx):
        """View your current tournament match and report results"""
        logger.info(
            f"my_round/match command invoked by {ctx.author.name} (ID: {ctx.author.id})"
        )

        # Find the player's current active match across all tournaments
        player_matches = []
        active_tournament_info = None

        logger.debug(
            f"Checking {len(active_tournaments)} active tournaments for player matches..."
        )

        for tournament_id, tournament in active_tournaments.items():
            logger.debug(
                f"Checking tournament {tournament_id} ({tournament['name']}) - Status: {tournament['status']}"
            )
            if tournament["status"] != "in_progress":
                continue

            # Find all pending matches for this player in this tournament
            for match in tournament["matches"]:
                if match["status"] == "pending" and ctx.author.id in [
                    match["player1"],
                    match["player2"],
                ]:
                    player_matches.append((match, tournament_id, tournament))
                    logger.info(
                        f"Found active match for {ctx.author.name}: Match ID {match['id']} in tournament {tournament['name']} (Round {match['round']})"
                    )

        if not player_matches:
            logger.info(
                f"No active matches found for {ctx.author.name} (ID: {ctx.author.id})"
            )
            await ctx.send("You don't have any active matches at the moment!")
            return

        if len(player_matches) > 1:
            # Multiple active matches - this shouldn't normally happen, but let's handle it
            logger.warning(
                f"Multiple active matches found for {ctx.author.name}: {len(player_matches)} matches"
            )
            # Select the match from the current round (highest round number)
            current_round = max(match[0]["round"] for match in player_matches)
            current_round_matches = [
                (match, t_id, tournament)
                for match, t_id, tournament in player_matches
                if match["round"] == current_round
            ]

            if len(current_round_matches) > 1:
                # Still multiple matches in the same round - shouldn't happen, but take the first one
                logger.error(
                    f"Multiple matches in round {current_round} for {ctx.author.name} - this indicates a tournament structure issue"
                )

            player_match, tournament_id, active_tournament_info = current_round_matches[
                0
            ]
        else:
            player_match, tournament_id, active_tournament_info = player_matches[0]

        logger.info(
            f"Selected match for {ctx.author.name}: Match ID {player_match['id']} in tournament {active_tournament_info['name']} (Round {player_match['round']})"
        )

        # Double-check that the match is still pending (race condition prevention)
        if player_match["status"] == "completed":
            logger.warning(
                f"Match {player_match['id']} is already completed but was found as active for {ctx.author.name}"
            )
            await ctx.send("This match has already been completed!")
            return

        # Get the opponent's user object for the match display
        opponent_id = (
            player_match["player2"]
            if ctx.author.id == player_match["player1"]
            else player_match["player1"]
        )

        try:
            opponent = await self.bot.fetch_user(opponent_id)
            logger.debug(
                f"Retrieved opponent info: {opponent.name} (ID: {opponent_id}) for match {player_match['id']}"
            )
        except discord.NotFound:
            logger.error(
                f"Could not fetch opponent user with ID {opponent_id} for match {player_match['id']}"
            )
            await ctx.send("Error: Could not retrieve opponent information!")
            return
        except Exception as e:
            logger.error(f"Error fetching opponent user {opponent_id}: {str(e)}")
            await ctx.send("Error: Could not retrieve opponent information!")
            return

        # Create an embed to display the match with tournament context
        embed = discord.Embed(
            title=f"🏆 {active_tournament_info['name']} - Round {player_match['round']}",
            description=f"{ctx.author.mention} vs {opponent.mention}\n\n⏰ You have 5 minutes to report the match result using the buttons below.\n\n**Match ID:** {player_match['id']}\n**Tournament ID:** {tournament_id}",
            color=discord.Color.blue(),
        )

        # Send the match information with a report button
        view = MatchReportButton(tournament_id, player_match["id"], ctx.author.id)

        try:
            message = await ctx.send(embed=embed, view=view)
            logger.info(
                f"Sent match report interface for {ctx.author.name} vs {opponent.name} (Match ID: {player_match['id']}, Tournament: {active_tournament_info['name']})"
            )

            # Store message reference for timeout handling
            view.message = message
        except Exception as e:
            logger.error(
                f"Error sending match report interface for {ctx.author.name}: {str(e)}"
            )
            await ctx.send("Error: Could not display match information!")
            return

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
        """View your side of the tournament bracket in a visual format"""
        tournament_id, tournament = find_tournament_by_name(tournament_name)
        if not tournament:
            await ctx.send(
                "Tournament not found! Please check the exact tournament name."
            )
            return

        # Check if user is in the tournament
        user_id = ctx.author.id
        if user_id not in tournament["players"]:
            await ctx.send(
                f"❌ You are not registered for **{tournament['name']}**.\n"
                f"Use `/tournament join {tournament_name}` to join!"
            )
            return

        # Build header
        message = "```\n"
        message += "╔═══════════════════════════════════════╗\n"
        message += "║     T O U R N A M E N T               ║\n"
        message += f"║     {tournament['name'][:30].center(30)}    ║\n"
        message += "╚═══════════════════════════════════════╝\n"
        message += "```\n"

        if tournament["status"] == "completed" and tournament.get("winner"):
            try:
                winner = await self.bot.fetch_user(tournament["winner"])
                message += f"🏆 **Champion:** {winner.name}\n\n"
            except discord.NotFound:
                message += "🏆 **Champion:** Unknown\n\n"

        if not tournament["matches"]:
            message += "⏳ No matches have been scheduled yet."
            await ctx.send(message)
            return

        # Find all matches involving the user
        user_matches = [
            m for m in tournament["matches"] if user_id in [m["player1"], m["player2"]]
        ]

        if not user_matches:
            message += "⏳ You don't have any scheduled matches yet."
            await ctx.send(message)
            return

        # Group user's matches by round
        matches_by_round = {}
        for match in user_matches:
            round_num = match["round"]
            if round_num not in matches_by_round:
                matches_by_round[round_num] = []
            matches_by_round[round_num].append(match)

        # Display user's path through the bracket
        message += "**📍 Your Bracket Path:**\n\n"

        for round_num in sorted(matches_by_round.keys()):
            round_matches = matches_by_round[round_num]

            # Determine round name
            remaining_rounds = (
                max([m["round"] for m in tournament["matches"]]) - round_num + 1
            )
            if remaining_rounds == 1:
                round_name = "Finals"
            elif remaining_rounds == 2:
                round_name = "Semi-Finals"
            elif remaining_rounds == 3:
                round_name = "Quarter-Finals"
            else:
                round_name = f"Round {round_num}"

            for match in round_matches:
                try:
                    player1 = await self.bot.fetch_user(match["player1"])
                    player2 = await self.bot.fetch_user(match["player2"])

                    # Determine which player is the user
                    if match["player1"] == user_id:
                        user_name = player1.name[:18]
                        opp_name = player2.name[:18]
                    else:
                        user_name = player2.name[:18]
                        opp_name = player1.name[:18]

                    # Create slim bracket display
                    message += f"**{round_name}**\n"
                    message += "```\n"

                    if match["winner"] is None:
                        # Match not played yet
                        message += "┌────────────────────┐\n"
                        message += f"│ {user_name:^18} │ (You)\n"
                        message += "├────────────────────┤\n"
                        message += f"│ {opp_name:^18} │\n"
                        message += "└────────────────────┘\n"
                    else:
                        # Match completed
                        winner = await self.bot.fetch_user(match["winner"])
                        user_won = match["winner"] == user_id

                        user_status = "✓ WIN " if user_won else "✗ LOSS"
                        opp_status = "✗ LOSS" if user_won else "✓ WIN "

                        message += "┌────────────────────┐\n"
                        message += f"│ {user_status} {user_name[:12]:<12} │\n"
                        message += "├────────────────────┤\n"
                        message += f"│ {opp_status} {opp_name[:12]:<12} │\n"
                        message += "└────────────────────┘\n"

                    message += "```\n"

                except discord.NotFound:
                    continue
                except Exception as e:
                    logger.error(f"Error displaying match in bracket: {str(e)}")
                    continue

        # Add footer with status
        if all(m["winner"] is not None for m in user_matches):
            # Check if user is still in tournament
            last_match = max(user_matches, key=lambda m: m["round"])
            if last_match["winner"] == user_id:
                if tournament["status"] == "completed":
                    message += "\n🎉 **You won the tournament!**"
                else:
                    message += "\n✅ **Still in the running!**"
            else:
                message += "\n💔 **You've been eliminated.**"

        # Split message if too long
        if len(message) > 2000:
            chunks = []
            current_chunk = ""
            for line in message.split("\n"):
                if len(current_chunk) + len(line) + 1 > 1900:
                    chunks.append(current_chunk)
                    current_chunk = line + "\n"
                else:
                    current_chunk += line + "\n"
            if current_chunk:
                chunks.append(current_chunk)

            for chunk in chunks:
                await ctx.send(chunk)
        else:
            await ctx.send(message)

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
    @commands.has_permissions(administrator=True)
    async def debug_matches(self, ctx, *, tournament_name: str = None):
        """Debug command to show all matches for a tournament (Admin only)"""
        if tournament_name:
            tournament_id, tournament = find_tournament_by_name(tournament_name)
            if not tournament:
                await ctx.send(
                    "Tournament not found! Please check the exact tournament name."
                )
                return

            tournaments_to_check = [(tournament_id, tournament)]
        else:
            tournaments_to_check = list(active_tournaments.items())

        debug_info = "**🔍 Tournament Match Debug Information**\n\n"

        for t_id, tournament in tournaments_to_check:
            debug_info += f"**Tournament {t_id}: {tournament['name']}** (Status: {tournament['status']})\n"

            if not tournament.get("matches"):
                debug_info += "  No matches found.\n\n"
                continue

            # Group matches by round
            rounds = {}
            for match in tournament["matches"]:
                round_num = match["round"]
                if round_num not in rounds:
                    rounds[round_num] = []
                rounds[round_num].append(match)

            for round_num in sorted(rounds.keys()):
                debug_info += f"  **Round {round_num}:**\n"
                for match in rounds[round_num]:
                    try:
                        player1 = await self.bot.fetch_user(match["player1"])
                        player2 = await self.bot.fetch_user(match["player2"])
                        p1_name = player1.name
                        p2_name = player2.name
                    except Exception as e:
                        logger.debug(f"Could not fetch player names: {str(e)}")
                        p1_name = f"ID:{match['player1']}"
                        p2_name = f"ID:{match['player2']}"

                    winner_info = ""
                    if match["winner"]:
                        try:
                            winner = await self.bot.fetch_user(match["winner"])
                            winner_info = f" (Winner: {winner.name})"
                        except Exception as e:
                            logger.debug(f"Could not fetch winner name: {str(e)}")
                            winner_info = f" (Winner ID: {match['winner']})"

                    debug_info += f"    Match {match['id']}: {p1_name} vs {p2_name} - {match['status']}{winner_info}\n"

                debug_info += "\n"

        # Send in chunks if too long
        if len(debug_info) > 2000:
            chunks = [debug_info[i : i + 2000] for i in range(0, len(debug_info), 2000)]
            for chunk in chunks:
                await ctx.send(chunk)
        else:
            await ctx.send(debug_info)

    @commands.command()
    async def players(self, ctx):
        """Get display names for the tournament player IDs"""
        user_ids = [
            296846802924208130,
            676067801848479745,
            1101250654871232642,
            703005385677865031,
            106682190745645056,
            97065365695123456,
            668506285020545047,
            169970918569934849,
        ]

        embed = discord.Embed(
            title="🎮 Player Display Names",
            color=discord.Color.blue(),
        )

        player_list = []
        for user_id in user_ids:
            try:
                user = await self.bot.fetch_user(user_id)
                display_name = user.global_name if user.global_name else user.name
                player_list.append(f"• {display_name} (ID: {user_id})")
            except Exception as e:
                player_list.append(f"• Unknown User (ID: {user_id})")

        embed.description = "\n".join(player_list)
        embed.set_footer(text=f"Total: {len(user_ids)} players")

        await ctx.send(embed=embed)

    @commands.command()
    async def tournament_help(self, ctx):
        """Show help information for all tournament commands"""
        embed = discord.Embed(
            title="🏆 Tournament Commands Help",
            description="Here are all the available tournament commands:",
            color=discord.Color.blue(),
        )

        # Admin Commands
        admin_commands = (
            "`!create_tournament` - Create a new tournament (Admin only)\n"
            "`!start_tournament <name>` - Start a tournament with registered players (Admin only)\n"
            "`!complete_tournament <name>` - Complete and finalize a tournament (Admin only)\n"
            "`!remove <name> @user` - Remove a player from a tournament (Admin only)\n"
            "`!debug_matches [tournament_name]` - Debug match information (Admin only)\n"
        )
        embed.add_field(name="🛡️ Admin Commands", value=admin_commands, inline=False)

        # Player Commands
        player_commands = (
            "`!join <tournament_name>` - Join a tournament during registration\n"
            "`!match` or `!my_round` - View your current match and report results\n"
            "`!bracket <tournament_name>` - View the current tournament bracket\n"
        )
        embed.add_field(name="👥 Player Commands", value=player_commands, inline=False)

        # How Match Reporting Works
        reporting_info = (
            "**Match Reporting:**\n"
            "1. Use `!match` to view your current match\n"
            "2. Click **'I Won! 🏆'** or **'I Lost 😢'** button\n"
            "3. Fill in match details (deck URL, time, notes)\n"
            "4. Match result is automatically recorded\n"
        )
        embed.add_field(
            name="📝 How to Report Matches", value=reporting_info, inline=False
        )

        # Usage Examples
        examples = (
            "**Example Flow:**\n"
            "1. Admin creates tournament: `!create_tournament`\n"
            "2. Players join: `!join Summit Championship`\n"
            "3. Admin starts: `!start_tournament Summit Championship`\n"
            "4. Check your match: `!match`\n"
            "5. Report result using the buttons shown\n"
            "6. View bracket: `!bracket Summit Championship`\n"
        )
        embed.add_field(name="� Example Flow", value=examples, inline=False)

        embed.set_footer(text="Use !help_lfg for Looking For Game commands")

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(TournamentCog(bot))
