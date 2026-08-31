"""Recover limited season ELO after an accidental reset.

Run this on the server to replay limited match records and recalculate
season ELO from scratch. Lifetime ELO is NOT affected (it was preserved
during the reset).

Usage:
    cd /root/Summit/SummitDiscordBot/discord-bot
    python scripts/recover_limited_elo.py --dry-run   # Preview changes
    python scripts/recover_limited_elo.py              # Apply changes

This script:
1. Reads all matches from limited_match_records in timestamp order
2. Resets all season ELO to 1500
3. Replays each match using the standard ELO formula (K=32)
4. Updates the limited_elo table with recalculated values
"""

import sqlite3
import argparse


def update_elo(player_elo, opponent_elo, did_win, k=32):
    """Standard ELO calculation (matches elo_service.update_elo)."""
    expected_score = 1 / (1 + 10 ** ((opponent_elo - player_elo) / 400))
    actual_score = 1 if did_win else 0
    new_elo = player_elo + k * (actual_score - expected_score)
    return round(new_elo)


def main():
    parser = argparse.ArgumentParser(description="Recover limited season ELO")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    # Read all current limited match records in order
    conn = sqlite3.connect("match_records.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT match_id, winner_id, winner_display_name, loser_id, loser_display_name, timestamp
        FROM limited_match_records
        ORDER BY match_id ASC
    """)
    matches = [dict(row) for row in cur.fetchall()]
    conn.close()

    print(f"Found {len(matches)} matches to replay")

    # Start everyone at 1500
    elos = {}
    names = {}

    for match in matches:
        w_id = match["winner_id"]
        l_id = match["loser_id"]
        names[w_id] = match["winner_display_name"]
        names[l_id] = match["loser_display_name"]

        w_elo = elos.get(w_id, 1500)
        l_elo = elos.get(l_id, 1500)

        new_w = update_elo(w_elo, l_elo, did_win=True)
        new_l = update_elo(l_elo, w_elo, did_win=False)

        w_change = new_w - w_elo
        l_change = new_l - l_elo

        print(f"  Match {match['match_id']}: {names[w_id]} ({w_elo}->{new_w}, {w_change:+d}) "
              f"beat {names[l_id]} ({l_elo}->{new_l}, {l_change:+d})")

        elos[w_id] = new_w
        elos[l_id] = new_l

    print(f"\nFinal recalculated ELO for {len(elos)} players:")
    for uid, elo in sorted(elos.items(), key=lambda x: -x[1]):
        print(f"  {names[uid]}: {elo}")

    if args.dry_run:
        print("\n[DRY RUN] No changes written.")
        return

    # Apply: reset all to 1500, then set recalculated values
    elo_conn = sqlite3.connect("elo.db")
    elo_cur = elo_conn.cursor()

    # Reset all season ELO to 1500 first
    elo_cur.execute("UPDATE limited_elo SET elo = 1500")

    # Set recalculated ELO for players who had matches
    for uid, elo in elos.items():
        elo_cur.execute(
            "UPDATE limited_elo SET elo = ? WHERE user_id = ?",
            (elo, uid),
        )
        if elo_cur.rowcount == 0:
            # Player not in limited_elo yet, insert them
            elo_cur.execute(
                "INSERT INTO limited_elo (user_id, user_display_name, elo, lifetime_elo) VALUES (?, ?, ?, 1500)",
                (uid, names[uid], elo),
            )

    elo_conn.commit()
    elo_conn.close()
    print(f"\nRecovery complete. Updated {len(elos)} player ELOs.")


if __name__ == "__main__":
    main()
