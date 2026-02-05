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

    # Add new deck columns for winner and loser (Phase 1 migration)
    try:
        cur.execute("ALTER TABLE match_records ADD COLUMN curiosa_url_winner TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        cur.execute("ALTER TABLE match_records ADD COLUMN curiosa_url_loser TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        cur.execute("ALTER TABLE match_records ADD COLUMN json_deck_data_winner TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        cur.execute("ALTER TABLE match_records ADD COLUMN json_deck_data_loser TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add winner/loser went first columns (replaces ambiguous first_player)
    try:
        cur.execute("ALTER TABLE match_records ADD COLUMN winner_went_first TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        cur.execute("ALTER TABLE match_records ADD COLUMN loser_went_first TEXT")
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


def create_events_table():
    """Create the events table for tracking event-based ELO seasons."""
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_name TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT,
                    is_active BOOLEAN DEFAULT 1
                   )""")

    # Create event standings archive table
    cur.execute("""CREATE TABLE IF NOT EXISTS event_standings_archive (
                    archive_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    user_display_name TEXT,
                    final_event_elo INTEGER,
                    final_rank INTEGER,
                    archived_at TEXT
                   )""")

    conn.commit()
    conn.close()


def create_match_records_archive():
    """Create the match_records_archive table for archived event matches."""
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS match_records_archive (
                    archive_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER NOT NULL,
                    original_match_id INTEGER,
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
                    curiosa_url_winner TEXT,
                    curiosa_url_loser TEXT,
                    match_comment TEXT,
                    json_deck_data TEXT,
                    json_deck_data_winner TEXT,
                    json_deck_data_loser TEXT,
                    winner_elo_change INTEGER,
                    loser_elo_change INTEGER,
                    winner_lifetime_elo_change INTEGER,
                    loser_lifetime_elo_change INTEGER,
                    archived_at TEXT
                   )""")

    conn.commit()
    conn.close()


def ensure_event_elo_column():
    """Add event_elo column to overall_standings if it doesn't exist."""
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()

    try:
        cur.execute(
            "ALTER TABLE overall_standings ADD COLUMN event_elo INTEGER DEFAULT 1500"
        )
    except sqlite3.OperationalError:
        pass  # Column already exists

    conn.commit()
    conn.close()


def get_active_event():
    """
    Get the currently active event, if any.

    Returns:
        dict with event info or None if no active event
    """
    create_events_table()
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()

    cur.execute("""SELECT event_id, event_name, start_date
                   FROM events
                   WHERE is_active = 1
                   LIMIT 1""")
    row = cur.fetchone()
    conn.close()

    if row:
        return {
            "event_id": row[0],
            "event_name": row[1],
            "start_date": datetime.datetime.fromisoformat(row[2]),
        }
    return None


def calculate_event_k_value(start_date):
    """
    Calculate K-value based on days since event started.

    Day 0: K=16
    Day 1: K=18
    Day 2: K=20
    ...
    Day 8+: K=32 (capped)

    Args:
        start_date: datetime when the event started

    Returns:
        int: K-value between 16 and 32
    """
    now = datetime.datetime.now()
    days_elapsed = (now - start_date).days
    k_value = 16 + (days_elapsed * 2)
    return min(k_value, 32)


def start_new_event(event_name):
    """
    Start a new event, archiving any active event first.

    Args:
        event_name: Name for the new event

    Returns:
        dict with new event info and optional previous event summary
    """
    create_events_table()
    create_match_records_archive()
    ensure_event_elo_column()

    previous_event_summary = None

    # Check for and archive any active event
    active_event = get_active_event()
    if active_event:
        previous_event_summary = end_current_event()

    # Create new event
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()

    start_date = datetime.datetime.now().isoformat()
    cur.execute(
        "INSERT INTO events (event_name, start_date, is_active) VALUES (?, ?, 1)",
        (event_name, start_date),
    )
    event_id = cur.lastrowid

    # Reset all players' event_elo to 1500
    cur.execute("UPDATE overall_standings SET event_elo = 1500")

    conn.commit()
    conn.close()

    return {
        "event_id": event_id,
        "event_name": event_name,
        "start_date": datetime.datetime.fromisoformat(start_date),
        "previous_event": previous_event_summary,
    }


def end_current_event():
    """
    End the current active event and archive its data.

    Returns:
        dict with event summary (top players, total matches) or None
    """
    active_event = get_active_event()
    if not active_event:
        return None

    event_id = active_event["event_id"]
    event_name = active_event["event_name"]

    # Archive standings
    conn_elo = sqlite3.connect("elo.db")
    cur_elo = conn_elo.cursor()

    # Get final standings ordered by event_elo
    cur_elo.execute("""SELECT user_id, user_display_name, event_elo
                       FROM overall_standings
                       WHERE event_elo != 1500
                       ORDER BY event_elo DESC""")
    standings = cur_elo.fetchall()

    # Archive to event_standings_archive
    archived_at = datetime.datetime.now().isoformat()
    for rank, (user_id, display_name, event_elo) in enumerate(standings, start=1):
        cur_elo.execute(
            """INSERT INTO event_standings_archive
               (event_id, user_id, user_display_name, final_event_elo, final_rank, archived_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (event_id, user_id, display_name, event_elo, rank, archived_at),
        )

    # Mark event as ended
    cur_elo.execute(
        "UPDATE events SET is_active = 0, end_date = ? WHERE event_id = ?",
        (archived_at, event_id),
    )

    conn_elo.commit()
    conn_elo.close()

    # Archive match records
    conn_match = sqlite3.connect("match_records.db")
    cur_match = conn_match.cursor()

    # Copy all matches to archive
    cur_match.execute("SELECT * FROM match_records")
    matches = cur_match.fetchall()
    match_count = len(matches)

    # Get column names from match_records
    cur_match.execute("PRAGMA table_info(match_records)")
    columns = [col[1] for col in cur_match.fetchall()]

    for match in matches:
        match_dict = dict(zip(columns, match))
        cur_match.execute(
            """INSERT INTO match_records_archive
               (event_id, original_match_id, reporter_id, winner_id, winner_display_name,
                losser_id, losser_display_name, did_win, timestamp, first_player, match_time,
                curiosa_url, curiosa_url_winner, curiosa_url_loser, match_comment,
                json_deck_data, json_deck_data_winner, json_deck_data_loser,
                winner_elo_change, loser_elo_change, archived_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id,
                match_dict.get("match_id"),
                match_dict.get("reporter_id"),
                match_dict.get("winner_id"),
                match_dict.get("winner_display_name"),
                match_dict.get("losser_id"),
                match_dict.get("losser_display_name"),
                match_dict.get("did_win"),
                match_dict.get("timestamp"),
                match_dict.get("first_player"),
                match_dict.get("match_time"),
                match_dict.get("curiosa_url"),
                match_dict.get("curiosa_url_winner"),
                match_dict.get("curiosa_url_loser"),
                match_dict.get("match_comment"),
                match_dict.get("json_deck_data"),
                match_dict.get("json_deck_data_winner"),
                match_dict.get("json_deck_data_loser"),
                match_dict.get("winner_elo_change"),
                match_dict.get("loser_elo_change"),
                archived_at,
            ),
        )

    # Clear match_records table
    cur_match.execute("DELETE FROM match_records")

    conn_match.commit()
    conn_match.close()

    # Return summary
    top_3 = standings[:3] if len(standings) >= 3 else standings
    return {
        "event_id": event_id,
        "event_name": event_name,
        "total_matches": match_count,
        "total_players": len(standings),
        "top_players": [(name, elo) for _, name, elo in top_3],
    }


def get_user_event_elo(user_id: int) -> int:
    """
    Get a user's current event ELO from the database.

    Args:
        user_id: The Discord user ID

    Returns:
        The user's current event ELO, or 1500 if not found
    """
    ensure_event_elo_column()
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()
    cur.execute("SELECT event_elo FROM overall_standings WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row and row[0] else 1500


def get_past_events():
    """
    Get a list of all past (ended) events.

    Returns:
        List of dicts with event info
    """
    create_events_table()
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()

    cur.execute("""SELECT event_id, event_name, start_date, end_date
                   FROM events
                   WHERE is_active = 0
                   ORDER BY end_date DESC""")
    rows = cur.fetchall()
    conn.close()

    return [
        {
            "event_id": row[0],
            "event_name": row[1],
            "start_date": row[2],
            "end_date": row[3],
        }
        for row in rows
    ]


def get_event_archive_standings(event_id: int):
    """
    Get archived standings for a specific event.

    Args:
        event_id: The event ID to get standings for

    Returns:
        List of tuples (rank, display_name, final_elo)
    """
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()

    cur.execute(
        """SELECT final_rank, user_display_name, final_event_elo
                   FROM event_standings_archive
                   WHERE event_id = ?
                   ORDER BY final_rank ASC
                   LIMIT 16""",
        (event_id,),
    )
    rows = cur.fetchall()
    conn.close()

    return rows


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
    """
    Update the ELO database with match results.

    Updates both lifetime ELO (K=32) and event ELO (dynamic K) if an event is active.
    If no event is active, ELO is not updated (returns 0 changes).

    Returns:
        Tuple of (new_lifetime_elo, lifetime_change, new_event_elo, event_change, event_active)
    """
    ensure_event_elo_column()
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()
    print(user_id, opponent_id)

    cur.execute("""CREATE TABLE IF NOT EXISTS overall_standings
                   (user_id INTEGER PRIMARY KEY,
                    user_display_name TEXT,
                    elo INTEGER DEFAULT 1500,
                    event_elo INTEGER DEFAULT 1500
                   )""")

    # Check for active event
    active_event = get_active_event()

    # Get player's current ELOs (or insert if new)
    cur.execute(
        "SELECT elo, event_elo FROM overall_standings WHERE user_id=?", (user_id,)
    )
    player_row = cur.fetchone()

    if player_row:
        player_lifetime_elo = player_row[0]
        player_event_elo = player_row[1] if player_row[1] else 1500
        print(
            "Existing player found with lifetime ELO:",
            player_lifetime_elo,
            "event ELO:",
            player_event_elo,
        )
    else:
        player_lifetime_elo = 1500
        player_event_elo = 1500
        cur.execute(
            """INSERT OR IGNORE INTO overall_standings
               (user_id, user_display_name, elo, event_elo) VALUES (?, ?, ?, ?)""",
            (user_id, user_display_name, player_lifetime_elo, player_event_elo),
        )
        print("New player inserted with default ELOs:", player_lifetime_elo)

    # Get opponent's ELOs (or use default if not found)
    cur.execute(
        "SELECT elo, event_elo FROM overall_standings WHERE user_id=?", (opponent_id,)
    )
    opponent_row = cur.fetchone()

    if opponent_row:
        opponent_lifetime_elo = opponent_row[0]
        opponent_event_elo = opponent_row[1] if opponent_row[1] else 1500
        print(
            "Opponent found with lifetime ELO:",
            opponent_lifetime_elo,
            "event ELO:",
            opponent_event_elo,
        )
    else:
        opponent_lifetime_elo = 1500
        opponent_event_elo = 1500
        print("Opponent not found, using default ELOs:", opponent_lifetime_elo)

    # If no active event, don't update ELO
    if not active_event:
        print("No active event - ELO not updated")
        conn.close()
        return (player_lifetime_elo, 0, player_event_elo, 0, False)

    # Calculate new lifetime ELO (always K=32)
    new_lifetime_elo = update_elo(
        player_lifetime_elo, opponent_lifetime_elo, did_win, k=32
    )
    lifetime_change = new_lifetime_elo - player_lifetime_elo
    print(
        f"Lifetime ELO: {player_lifetime_elo} -> {new_lifetime_elo} (change: {lifetime_change:+d})"
    )

    # Calculate new event ELO (dynamic K based on days elapsed)
    event_k = calculate_event_k_value(active_event["start_date"])
    new_event_elo = update_elo(player_event_elo, opponent_event_elo, did_win, k=event_k)
    event_change = new_event_elo - player_event_elo
    print(
        f"Event ELO (K={event_k}): {player_event_elo} -> {new_event_elo} (change: {event_change:+d})"
    )

    # Update player's ELOs
    cur.execute(
        "UPDATE overall_standings SET elo = ?, event_elo = ? WHERE user_id = ?",
        (new_lifetime_elo, new_event_elo, user_id),
    )

    conn.commit()
    conn.close()

    print(
        f"Player {user_id} ELO updated - lifetime: {new_lifetime_elo}, event: {new_event_elo}"
    )
    return (new_lifetime_elo, lifetime_change, new_event_elo, event_change, True)


def get_user_elo(user_id: int) -> int:
    """
    Get a user's current ELO from the database.

    Args:
        user_id: The Discord user ID

    Returns:
        The user's current ELO, or 1500 if not found
    """
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()
    cur.execute("SELECT elo FROM overall_standings WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 1500


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
    winner_deck_url=None,
    loser_deck_url=None,
    winner_went_first=None,
    loser_went_first=None,
):
    """
    Log a win in the database.

    Returns:
        Tuple of (match_id, winner_id, loser_id, event_active)
        event_active is True if ELO was updated, False if no active event
    """
    logger.info(f"Logging win for user {interaction_global}")
    create_db()
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    # Fetch deck data for both players
    json_deck_data_winner = "{}"
    json_deck_data_loser = "{}"

    # Use new deck URLs if provided, otherwise fall back to old curiosa_link
    if winner_deck_url:
        json_deck_data_winner = scrape_Curosa(winner_deck_url, "deck_data_test.json")
    elif curiosa_link and curiosa_link != "No URL provided":
        # Backward compatibility: if only one URL provided, assume it's winner's
        json_deck_data_winner = scrape_Curosa(curiosa_link, "deck_data_test.json")

    if loser_deck_url:
        json_deck_data_loser = scrape_Curosa(loser_deck_url, "deck_data_test.json")

    # Update ELO and get the change values (returns 5 values now)
    new_lifetime_elo, lifetime_change, new_event_elo, event_change, event_active = (
        update_elo_db(interaction_user_id, interaction_global, did_win, opponent_id)
    )
    # For winner_report, did_win is True so this is the winner's elo change
    # Use event_change for display (or lifetime_change if you prefer)
    winner_elo_change = event_change if event_active else 0
    loser_elo_change = (
        -event_change if event_active else 0
    )  # Approximate: loser loses roughly what winner gains

    cur.execute(
        "INSERT INTO match_records (reporter_id, winner_id, winner_display_name, "
        "losser_id, losser_display_name, did_win, timestamp, first_player, match_time, "
        "curiosa_url, curiosa_url_winner, curiosa_url_loser, match_comment, "
        "json_deck_data, json_deck_data_winner, json_deck_data_loser, winner_elo_change, loser_elo_change, "
        "winner_went_first, loser_went_first) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
            curiosa_link,  # Keep for backward compatibility
            winner_deck_url or curiosa_link,
            loser_deck_url,
            match_comment,
            json_deck_data_winner,  # Keep for backward compatibility
            json_deck_data_winner,
            json_deck_data_loser,
            winner_elo_change,
            loser_elo_change,
            winner_went_first,
            loser_went_first,
        ),
    )

    match_id = cur.lastrowid
    conn.commit()
    conn.close()

    return (match_id, user_id, opponent_id, event_active)


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
    winner_deck_url=None,
    loser_deck_url=None,
    winner_went_first=None,
    loser_went_first=None,
):
    """
    Log a loss in the database.

    Returns:
        Tuple of (match_id, winner_id, loser_id, event_active)
        event_active is True if ELO was updated, False if no active event
    """
    logger.info(f"Logging loss for user {interaction_global}")
    create_db()
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    # Fetch deck data for both players
    json_deck_data_winner = "{}"
    json_deck_data_loser = "{}"

    # Use new deck URLs if provided, otherwise fall back to old curiosa_link
    if winner_deck_url:
        json_deck_data_winner = scrape_Curosa(winner_deck_url, "deck_data_test.json")

    if loser_deck_url:
        json_deck_data_loser = scrape_Curosa(loser_deck_url, "deck_data_test.json")
    elif curiosa_link and curiosa_link != "No URL provided":
        # Backward compatibility: if only one URL provided, assume it's loser's
        json_deck_data_loser = scrape_Curosa(curiosa_link, "deck_data_test.json")

    # Update ELO and get the change values (returns 5 values now)
    new_lifetime_elo, lifetime_change, new_event_elo, event_change, event_active = (
        update_elo_db(interaction_user_id, interaction_global, did_win, opponent_id)
    )
    # For losser_report, did_win is False so this is the loser's elo change
    loser_elo_change = event_change if event_active else 0
    winner_elo_change = (
        -event_change if event_active else 0
    )  # Approximate: winner gains roughly what loser loses

    cur.execute(
        "INSERT INTO match_records (reporter_id, winner_id, winner_display_name, "
        "losser_id, losser_display_name, did_win, timestamp, first_player, match_time, "
        "curiosa_url, curiosa_url_winner, curiosa_url_loser, match_comment, "
        "json_deck_data, json_deck_data_winner, json_deck_data_loser, winner_elo_change, loser_elo_change, "
        "winner_went_first, loser_went_first) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
            curiosa_link,  # Keep for backward compatibility
            winner_deck_url,
            loser_deck_url or curiosa_link,
            match_comment,
            json_deck_data_loser,  # Keep for backward compatibility
            json_deck_data_winner,
            json_deck_data_loser,
            winner_elo_change,
            loser_elo_change,
            winner_went_first,
            loser_went_first,
        ),
    )

    match_id = cur.lastrowid
    conn.commit()
    conn.close()

    return (match_id, user_id, opponent_id, event_active)


def get_total_match_count():
    """Get the total number of matches recorded in the database."""
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM match_records")
    count = cur.fetchone()[0]
    conn.close()
    return count


def check_milestone(match_id):
    """
    Check if the current match is a milestone (every 100 matches).

    Args:
        match_id: The ID of the just-recorded match

    Returns:
        int or None: The milestone number if this is a milestone match, None otherwise
    """
    total_matches = get_total_match_count()
    if total_matches > 0 and total_matches % 100 == 0:
        return total_matches
    return None


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
