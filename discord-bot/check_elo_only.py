import sqlite3

print('--- Checking ELO database ---')
try:
    conn = sqlite3.connect('elo.db')
    cur = conn.cursor()

    # Check if table exists
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cur.fetchall()
    print(f'Tables in elo.db: {tables}')

    # Count players
    cur.execute('SELECT COUNT(*) FROM overall_standings')
    count = cur.fetchone()[0]
    print(f'\nTotal players: {count}')

    # Recent ELO updates (based on the log showing recent player IDs)
    recent_player_ids = [266525184574357504, 1061797343881613373, 480924592530128897,
                         236069354771447808, 876478437651537950, 694973686142337074]

    print('\nRecent players from logs:')
    for player_id in recent_player_ids:
        cur.execute('''
            SELECT user_id, user_display_name, elo, event_elo, online_elo, online_event_elo
            FROM overall_standings
            WHERE user_id = ?
        ''', (player_id,))
        row = cur.fetchone()
        if row:
            user_id, name, elo, event_elo, online_elo, online_event_elo = row
            print(f'  {name} ({user_id}):')
            print(f'    Lifetime ELO: {elo}, Event ELO: {event_elo}')
            print(f'    Online ELO: {online_elo}, Online Event ELO: {online_event_elo}')
        else:
            print(f'  Player {player_id} not found')

    conn.close()
    print('\n✓ elo.db appears to be working correctly')

except Exception as e:
    print(f'✗ Error with elo.db: {e}')

print('\n--- Checking match_records database ---')
try:
    conn2 = sqlite3.connect('match_records.db')
    cur2 = conn2.cursor()

    # Try to check integrity
    cur2.execute('PRAGMA integrity_check')
    result = cur2.fetchone()
    print(f'Integrity check: {result}')

    conn2.close()

except Exception as e:
    print(f'✗ match_records.db error: {e}')
    print('\nThe match_records.db database is CORRUPTED!')
