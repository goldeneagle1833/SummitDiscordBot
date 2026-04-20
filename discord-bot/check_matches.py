import sqlite3
import sys

# Check match_records.db
conn = sqlite3.connect('match_records.db')
cur = conn.cursor()

# Count total matches
cur.execute('SELECT COUNT(*) FROM match_records')
total = cur.fetchone()[0]
print(f'Total matches in database: {total}')

# Get recent matches
print('\nRecent 10 matches:')
cur.execute('''
    SELECT match_id, winner_id, loser_id, match_date, match_type,
           winner_elo_change, loser_elo_change
    FROM match_records
    ORDER BY match_id DESC
    LIMIT 10
''')

for row in cur.fetchall():
    match_id, winner_id, loser_id, match_date, match_type, winner_elo, loser_elo = row
    print(f'  Match #{match_id}: Winner={winner_id}, Loser={loser_id}, '
          f'Date={match_date}, Type={match_type}, '
          f'Winner ELO: {winner_elo}, Loser ELO: {loser_elo}')

conn.close()

# Check elo.db
print('\n--- Checking ELO database ---')
conn2 = sqlite3.connect('elo.db')
cur2 = conn2.cursor()

# Check if players from recent matches have ELO records
cur2.execute('''
    SELECT user_id, user_display_name, elo, event_elo, online_elo, online_event_elo
    FROM overall_standings
    ORDER BY user_id DESC
    LIMIT 5
''')

print('\nRecent players in ELO database:')
for row in cur2.fetchall():
    user_id, name, elo, event_elo, online_elo, online_event_elo = row
    print(f'  User {user_id} ({name}): ELO={elo}, Event={event_elo}, '
          f'Online={online_elo}, Online Event={online_event_elo}')

conn2.close()
