"""Test script to verify on-the-play vs on-the-draw logic."""

def test_play_draw_logic():
    """Simulate the logic from avatars.py endpoint."""

    # Sample test data: (timestamp, first_player, avatar_in_winner, avatar_in_loser)
    # first_player: "y" = winner went first (on play), else winner went on draw
    test_matches = [
        ("2026-02-08", "y", True, False),   # Avatar won on the play
        ("2026-02-08", "n", True, False),   # Avatar won on the draw
        ("2026-02-09", "y", False, True),   # Avatar lost on the draw (winner on play)
        ("2026-02-09", "n", False, True),   # Avatar lost on the play (winner on draw)
        ("2026-02-10", "y", True, False),   # Avatar won on the play
        ("2026-02-10", "y", True, False),   # Avatar won on the play
        ("2026-02-11", "n", False, True),   # Avatar lost on the play
        ("2026-02-11", "y", True, False),   # Avatar won on the play
        ("2026-02-06", "y", True, False),   # Before cutoff - should be ignored
    ]

    cutoff_date = "2026-02-07"
    play_wins = 0
    play_losses = 0
    draw_wins = 0
    draw_losses = 0

    print("Processing matches:")
    print("-" * 70)

    for timestamp, first_player, avatar_in_winner, avatar_in_loser in test_matches:
        # Skip matches before cutoff
        if timestamp < cutoff_date:
            print(f"{timestamp}: SKIPPED (before {cutoff_date})")
            continue

        result = ""
        if avatar_in_winner:
            # Avatar won
            if first_player and "y" in first_player.lower():
                play_wins += 1
                result = "Avatar WON on the PLAY"
            else:
                draw_wins += 1
                result = "Avatar WON on the DRAW"

        if avatar_in_loser:
            # Avatar lost
            if first_player and "y" in first_player.lower():
                draw_losses += 1
                result = "Avatar LOST on the DRAW (opponent played first)"
            else:
                play_losses += 1
                result = "Avatar LOST on the PLAY (opponent drew)"

        print(f"{timestamp} | first_player={first_player:>3} | {result}")

    print("-" * 70)
    print("\nResults:")
    print(f"  On the Play:  {play_wins}W - {play_losses}L  ({play_wins + play_losses} matches)")
    print(f"  On the Draw:  {draw_wins}W - {draw_losses}L  ({draw_wins + draw_losses} matches)")

    play_total = play_wins + play_losses
    draw_total = draw_wins + draw_losses
    play_win_rate = (play_wins / play_total * 100) if play_total > 0 else 0
    draw_win_rate = (draw_wins / draw_total * 100) if draw_total > 0 else 0

    print(f"\n  Play Win Rate: {play_win_rate:.1f}%")
    print(f"  Draw Win Rate: {draw_win_rate:.1f}%")

    # Expected results:
    # Play: 4W-2L (66.7% win rate)
    # Draw: 1W-1L (50% win rate)
    assert play_wins == 4, f"Expected 4 play wins, got {play_wins}"
    assert play_losses == 2, f"Expected 2 play losses, got {play_losses}"
    assert draw_wins == 1, f"Expected 1 draw win, got {draw_wins}"
    assert draw_losses == 1, f"Expected 1 draw loss, got {draw_losses}"

    print("\n[PASS] All assertions passed! Logic is correct.")

if __name__ == "__main__":
    test_play_draw_logic()
