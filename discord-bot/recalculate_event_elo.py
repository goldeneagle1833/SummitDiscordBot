"""
Script to recalculate all event ELO from match records since the event started.
This fixes any event_elo discrepancies by replaying all matches.

Run this from the discord-bot directory:
    python recalculate_event_elo.py
"""

import sqlite3
import datetime
from utils.database import get_active_event, update_elo, calculate_event_k_value


def recalculate_all_event_elo():
    """Recalculate event_elo for all players based on matches since event start."""

    # Get active event
    active_event = get_active_event()
    if not active_event:
        print("No active event found. Nothing to recalculate.")
        return

    event_start = active_event["start_date"]
    event_start_str = event_start.isoformat()

    print(f"Active event: {active_event['event_name']}")
    print(f"Event started: {event_start}")
    print()

    # Connect to databases
    elo_conn = sqlite3.connect("elo.db")
    elo_cur = elo_conn.cursor()

    match_conn = sqlite3.connect("match_records.db")
    match_cur = match_conn.cursor()

    # Step 1: Reset all event_elo to 1500
    print("Step 1: Resetting all event_elo to 1500...")
    elo_cur.execute("UPDATE overall_standings SET event_elo = 1500")
    elo_conn.commit()
    print(f"Reset {elo_cur.rowcount} players to 1500 event_elo")
    print()

    # Step 2: Get all matches since event started, ordered by timestamp
    print("Step 2: Fetching matches since event start...")
    match_cur.execute(
        """
        SELECT rowid, winner_id, winner_display_name, losser_id, losser_display_name, timestamp
        FROM match_records
        WHERE timestamp >= ?
        ORDER BY timestamp ASC
    """,
        (event_start_str,),
    )

    matches = match_cur.fetchall()
    print(f"Found {len(matches)} matches to process")
    print()

    # Step 3: Replay each match and update event_elo
    print("Step 3: Replaying matches and updating event_elo...")

    # Keep track of each player's current event_elo
    player_elos = {}  # user_id -> event_elo

    # Get initial lifetime ELOs for K-value calculation (we'll use event_elo though)
    elo_cur.execute("SELECT user_id, elo FROM overall_standings")
    for row in elo_cur.fetchall():
        player_elos[row[0]] = 1500  # Start at 1500

    matches_processed = 0
    players_updated = set()

    for match in matches:
        rowid, winner_id, winner_name, loser_id, loser_name, timestamp = match

        match_time = datetime.datetime.fromisoformat(timestamp)
        k_value = calculate_event_k_value(event_start)

        # Get current event_elo for both players (default 1500)
        winner_elo = player_elos.get(winner_id, 1500)
        loser_elo = player_elos.get(loser_id, 1500)

        # Calculate new ELOs
        new_winner_elo = update_elo(winner_elo, loser_elo, True, k=k_value)
        new_loser_elo = update_elo(loser_elo, winner_elo, False, k=k_value)

        # Update tracking
        player_elos[winner_id] = new_winner_elo
        player_elos[loser_id] = new_loser_elo
        players_updated.add(winner_id)
        players_updated.add(loser_id)

        matches_processed += 1
        if matches_processed % 10 == 0:
            print(f"  Processed {matches_processed}/{len(matches)} matches...")

    print(f"Processed all {matches_processed} matches")
    print()

    # Step 4: Write all updated event_elos back to database
    print("Step 4: Writing updated event_elo values to database...")

    updates_written = 0
    for user_id, event_elo in player_elos.items():
        if event_elo != 1500:  # Only update if changed
            elo_cur.execute(
                "UPDATE overall_standings SET event_elo = ? WHERE user_id = ?",
                (event_elo, user_id),
            )
            updates_written += 1

    elo_conn.commit()
    print(f"Updated event_elo for {updates_written} players")
    print()

    # Step 5: Show top players
    print("Step 5: Top 10 players by event_elo:")
    elo_cur.execute("""
        SELECT user_display_name, event_elo 
        FROM overall_standings 
        WHERE event_elo != 1500 
        ORDER BY event_elo DESC 
        LIMIT 10
    """)
    for i, row in enumerate(elo_cur.fetchall(), 1):
        print(f"  {i}. {row[0]}: {row[1]}")

    # Cleanup
    elo_conn.close()
    match_conn.close()

    print()
    print("Done! Event ELO has been recalculated for all players.")
    print(
        f"Affected {len(players_updated)} unique players across {matches_processed} matches."
    )


if __name__ == "__main__":
    recalculate_all_event_elo()
