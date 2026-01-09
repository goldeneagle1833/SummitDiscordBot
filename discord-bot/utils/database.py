import sqlite3
import datetime
import logging

from utils.deck_checker import scrape_Curosa

logger = logging.getLogger("discord_bot")


def create_db():
    """Create all required database tables if they don't exist."""
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    # Create match_records table with auto-increment match_id
    cur.execute("""CREATE TABLE IF NOT EXISTS match_records
                   (match_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reporter_id INTEGER,
                    winner_id INTEGER, 
                    winner_display_name TEXT,
                    losser_id INTEGER,
                    losser_display_name TEXT,
                    did_win BOOLEAN,
                    timestamp TEXT,
                    first_player TEXT,
                    match_time INTEGER,
                    curiosa_url TEXT,
                    match_comment TEXT,
                    json_deck_data TEXT,
                    winner_elo_change INTEGER,
                    loser_elo_change INTEGER
                   )""")

    # Add match_id column if it doesn't exist (migration for existing databases)
    try:
        cur.execute(
            "ALTER TABLE match_records ADD COLUMN match_id INTEGER PRIMARY KEY AUTOINCREMENT"
        )
    except sqlite3.OperationalError:
        pass  # Column already exists or table was created with it

    # Add elo_change columns if they don't exist (migration for existing databases)
    try:
        cur.execute("ALTER TABLE match_records ADD COLUMN winner_elo_change INTEGER")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        cur.execute("ALTER TABLE match_records ADD COLUMN loser_elo_change INTEGER")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Create solo_match_reports table with auto-increment report_id
    cur.execute("""CREATE TABLE IF NOT EXISTS solo_match_reports
                   (report_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reporter_id INTEGER,
                    reporter_name TEXT,
                    opponent_name TEXT,
                    is_winner BOOLEAN,
                    first_player TEXT,
                    match_time INTEGER,
                    curiosa_link TEXT,
                    match_comment TEXT,
                    report_date DATETIME,
                    json_deck_data TEXT
                   )""")

    conn.commit()
    conn.close()


def create_challenge_db():
    """Create the challenge_matches table if it doesn't exist."""
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS challenge_matches
                   (match_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    challenger_id INTEGER NOT NULL,
                    challenged_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    match_time DATETIME NOT NULL,
                    winner_id INTEGER,
                    curiosa_url TEXT,
                    match_comment TEXT,
                    json_deck_data TEXT
                   )""")

    conn.commit()
    conn.close()


def update_elo(player_elo, opponent_elo, did_win, k=32):
    """
    Update Elo rating.

    :param player_elo: Current player's Elo rating
    :param opponent_elo: Opponent's Elo rating
    :param did_win: True if player won, False if lost
    :param k: K-factor (default = 32)
    :return: Updated Elo rating
    """
    expected_score = 1 / (1 + 10 ** ((opponent_elo - player_elo) / 400))
    actual_score = 1 if did_win else 0
    new_elo = player_elo + k * (actual_score - expected_score)
    return round(new_elo)


def update_elo_db(user_id, user_display_name, did_win, opponent_id):
    """Update the ELO database with match results."""
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()
    print(user_id, opponent_id)

    cur.execute("""CREATE TABLE IF NOT EXISTS overall_standings
                   (user_id INTEGER PRIMARY KEY, 
                    user_display_name TEXT,
                    elo INTEGER DEFAULT 1500
                   )""")

    # Get player's current ELO (or insert if new)
    cur.execute("SELECT elo FROM overall_standings WHERE user_id=?", (user_id,))
    player_row = cur.fetchone()

    if player_row:
        player_elo = player_row[0]
        print("Existing player found with ELO:", player_elo)
    else:
        player_elo = 1500
        cur.execute(
            """INSERT OR IGNORE INTO overall_standings 
               (user_id, user_display_name, elo) VALUES (?, ?, ?)""",
            (user_id, user_display_name, player_elo),
        )
        print("New player inserted with default ELO:", player_elo)

    # Get opponent's ELO (or use default if not found)
    cur.execute("SELECT elo FROM overall_standings WHERE user_id=?", (opponent_id,))
    opponent_row = cur.fetchone()

    if opponent_row:
        opponent_elo = opponent_row[0]
        print("Opponent found with ELO:", opponent_elo)
    else:
        opponent_elo = 1500
        print("Opponent not found, using default ELO:", opponent_elo)

    # Calculate new ELO
    new_player_elo = update_elo(player_elo, opponent_elo, did_win)
    elo_change = new_player_elo - player_elo
    print(
        f"New ELO calculated: {player_elo} -> {new_player_elo} (change: {elo_change:+d})"
    )

    # Update player's ELO
    cur.execute(
        "UPDATE overall_standings SET elo = ? WHERE user_id = ?",
        (new_player_elo, user_id),
    )

    conn.commit()
    conn.close()

    print(f"Player {user_id} ELO updated to {new_player_elo}")
    return new_player_elo, elo_change


async def winner_report(
    reporter_id,
    user_id,
    user_display_name,
    did_win,
    opponent_id,
    opponent_display_name,
    first_player,
    match_time,
    curiosa_link,
    match_comment,
    interaction_user_id,
    interaction_global,
):
    """
    Log a win in the database.

    Returns:
        Tuple of (match_id, winner_id, loser_id)
    """
    logger.info(f"Logging win for user {interaction_global}")
    create_db()
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    json_deck_data = "{}"
    json_deck_data = scrape_Curosa(curiosa_link, "deck_data_test.json")

    # Update ELO and get the change values
    new_elo, elo_change = update_elo_db(
        interaction_user_id, interaction_global, did_win, opponent_id
    )
    # For winner_report, did_win is True so this is the winner's elo change
    winner_elo_change = elo_change
    loser_elo_change = -elo_change  # Approximate: loser loses roughly what winner gains

    cur.execute(
        "INSERT INTO match_records (reporter_id, winner_id, winner_display_name, "
        "losser_id, losser_display_name, did_win, timestamp, first_player, match_time, "
        "curiosa_url, match_comment, json_deck_data, winner_elo_change, loser_elo_change) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            reporter_id,
            user_id,
            user_display_name,
            opponent_id,
            opponent_display_name,
            did_win,
            datetime.datetime.now().isoformat(),
            first_player,
            match_time,
            curiosa_link,
            match_comment,
            json_deck_data,
            winner_elo_change,
            loser_elo_change,
        ),
    )

    match_id = cur.lastrowid
    conn.commit()
    conn.close()

    return (match_id, user_id, opponent_id)


async def losser_report(
    reporter_id,
    user_id,
    user_display_name,
    did_win,
    opponent_id,
    opponent_display_name,
    first_player,
    match_time,
    curiosa_link,
    match_comment,
    interaction_user_id,
    interaction_global,
):
    """
    Log a loss in the database.

    Returns:
        Tuple of (match_id, winner_id, loser_id)
    """
    logger.info(f"Logging loss for user {interaction_global}")
    create_db()
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    json_deck_data = "{}"
    json_deck_data = scrape_Curosa(curiosa_link, "deck_data_test.json")

    # Update ELO and get the change values
    new_elo, elo_change = update_elo_db(
        interaction_user_id, interaction_global, did_win, opponent_id
    )
    # For losser_report, did_win is False so this is the loser's elo change
    loser_elo_change = elo_change
    winner_elo_change = (
        -elo_change
    )  # Approximate: winner gains roughly what loser loses

    cur.execute(
        "INSERT INTO match_records (reporter_id, winner_id, winner_display_name, "
        "losser_id, losser_display_name, did_win, timestamp, first_player, match_time, "
        "curiosa_url, match_comment, json_deck_data, winner_elo_change, loser_elo_change) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            reporter_id,
            user_id,
            user_display_name,
            opponent_id,
            opponent_display_name,
            did_win,
            datetime.datetime.now().isoformat(),
            first_player,
            match_time,
            curiosa_link,
            match_comment,
            json_deck_data,
            winner_elo_change,
            loser_elo_change,
        ),
    )

    match_id = cur.lastrowid
    conn.commit()
    conn.close()

    return (match_id, user_id, opponent_id)


async def save_challenge_match(
    challenger_id: int, challenged_id: int, status: str, winner_id: int = None
):
    """
    Save a challenge match to the database.

    Args:
        challenger_id: ID of the player who initiated the challenge
        challenged_id: ID of the player who was challenged
        status: Match status ('pending', 'completed', 'declined', 'cancelled')
        winner_id: ID of the winning player (if match is completed)
    """
    # Ensure the challenge_matches table exists, then open a connection directly.
    create_challenge_db()
    conn = sqlite3.connect("match_records.db")
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO challenge_matches 
            (challenger_id, challenged_id, status, match_time, winner_id) 
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)
        """,
            (challenger_id, challenged_id, status, winner_id),
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Error saving challenge match: {e}")
    finally:
        conn.close()


class DatabaseConnection:
    def __init__(self, db_name):
        self.db_name = db_name

    async def __aenter__(self):
        self.conn = sqlite3.connect(self.db_name)
        return self.conn.cursor()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.conn.commit()
            self.conn.close()


async def solo_match_report(
    reporter_id: int,
    reporter_global: str,
    opponent_name: str,
    is_winner: bool,
    first_player: str,
    match_time: int,
    curiosa_link: str,
    match_comment: str,
) -> int:
    """
    Save a solo match report to the database.

    Args:
        reporter_id: Discord ID of the reporting player
        reporter_global: Global name of the reporting player
        opponent_name: Name of the opponent (manually entered)
        is_winner: True if reporter won, False if lost
        first_player: 'y' if reporter went first, 'n' if not
        match_time: Duration of match in minutes
        curiosa_link: URL to Curiosa deck
        match_comment: Additional match notes

    Returns:
        The report_id of the newly created report
    """
    logger.info(f"Logging solo match report for user {reporter_global}")
    create_db()  # Ensure tables exist
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    json_deck_data = "{}"
    if curiosa_link and curiosa_link != "No URL provided":
        json_deck_data = scrape_Curosa(curiosa_link, "deck_data_test.json")

    cur.execute(
        """INSERT INTO solo_match_reports 
           (reporter_id, reporter_name, opponent_name, is_winner, 
            first_player, match_time, curiosa_link, match_comment, 
            report_date, json_deck_data)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)""",
        (
            reporter_id,
            reporter_global,
            opponent_name,
            is_winner,
            first_player,
            match_time,
            curiosa_link,
            match_comment,
            json_deck_data,
        ),
    )

    report_id = cur.lastrowid
    conn.commit()
    conn.close()

    return report_id
