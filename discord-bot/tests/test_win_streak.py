"""
Test Win Streak Achievement
============================

This script tests the logic for detecting a 5-game win streak.
"""

def check_win_streak_logic(game_results: list) -> bool:
    """
    Simulate the win streak check logic.
    
    Args:
        game_results: List of booleans (True = win, False = loss) in chronological order
        
    Returns:
        True if there's a streak of 5 consecutive wins
    """
    if len(game_results) < 5:
        return False
    
    current_streak = 0
    for result in game_results:
        if result:  # If won
            current_streak += 1
            if current_streak >= 5:
                return True
        else:  # If lost
            current_streak = 0
    
    return False


def test_win_streak():
    """Test various win streak scenarios."""
    
    print("=" * 60)
    print("WIN STREAK ACHIEVEMENT TESTS")
    print("=" * 60)
    
    # Test 1: Exact 5 wins in a row
    test1 = [True, True, True, True, True]
    result1 = check_win_streak_logic(test1)
    print(f"\nTest 1 - Exactly 5 wins: {test1}")
    print(f"  Result: {result1} {'✅' if result1 else '❌'}")
    assert result1 == True, "Should detect 5 wins in a row"
    
    # Test 2: More than 5 wins in a row
    test2 = [True, True, True, True, True, True, True]
    result2 = check_win_streak_logic(test2)
    print(f"\nTest 2 - 7 wins in a row: {test2}")
    print(f"  Result: {result2} {'✅' if result2 else '❌'}")
    assert result2 == True, "Should detect 7 wins in a row"
    
    # Test 3: 5 wins with losses before
    test3 = [False, False, True, True, True, True, True]
    result3 = check_win_streak_logic(test3)
    print(f"\nTest 3 - 5 wins after losses: {test3}")
    print(f"  Result: {result3} {'✅' if result3 else '❌'}")
    assert result3 == True, "Should detect 5 wins after losses"
    
    # Test 4: 5 wins with losses after
    test4 = [True, True, True, True, True, False, False]
    result4 = check_win_streak_logic(test4)
    print(f"\nTest 4 - 5 wins then losses: {test4}")
    print(f"  Result: {result4} {'✅' if result4 else '❌'}")
    assert result4 == True, "Should detect 5 wins before losses"
    
    # Test 5: 5 wins in the middle
    test5 = [False, True, True, True, True, True, False]
    result5 = check_win_streak_logic(test5)
    print(f"\nTest 5 - 5 wins in middle: {test5}")
    print(f"  Result: {result5} {'✅' if result5 else '❌'}")
    assert result5 == True, "Should detect 5 wins in middle"
    
    # Test 6: Only 4 wins in a row
    test6 = [True, True, True, True, False]
    result6 = check_win_streak_logic(test6)
    print(f"\nTest 6 - Only 4 wins: {test6}")
    print(f"  Result: {result6} {'✅ PASS (correctly False)' if not result6 else '❌ FAIL'}")
    assert result6 == False, "Should NOT detect 4 wins"
    
    # Test 7: 4 wins, loss, then 4 more wins
    test7 = [True, True, True, True, False, True, True, True, True]
    result7 = check_win_streak_logic(test7)
    print(f"\nTest 7 - Two separate 4-win streaks: {test7}")
    print(f"  Result: {result7} {'✅ PASS (correctly False)' if not result7 else '❌ FAIL'}")
    assert result7 == False, "Should NOT detect two 4-win streaks"
    
    # Test 8: Alternating wins and losses
    test8 = [True, False, True, False, True, False, True, False]
    result8 = check_win_streak_logic(test8)
    print(f"\nTest 8 - Alternating: {test8}")
    print(f"  Result: {result8} {'✅ PASS (correctly False)' if not result8 else '❌ FAIL'}")
    assert result8 == False, "Should NOT detect alternating wins"
    
    # Test 9: Less than 5 games total
    test9 = [True, True, True]
    result9 = check_win_streak_logic(test9)
    print(f"\nTest 9 - Only 3 games: {test9}")
    print(f"  Result: {result9} {'✅ PASS (correctly False)' if not result9 else '❌ FAIL'}")
    assert result9 == False, "Should NOT detect with less than 5 games"
    
    # Test 10: Multiple 5-win streaks
    test10 = [True, True, True, True, True, False, True, True, True, True, True]
    result10 = check_win_streak_logic(test10)
    print(f"\nTest 10 - Two 5-win streaks: {test10}")
    print(f"  Result: {result10} {'✅' if result10 else '❌'}")
    assert result10 == True, "Should detect first 5-win streak"
    
    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED!")
    print("=" * 60)
    
    print("\n📊 SUMMARY:")
    print("  - Detects exactly 5 consecutive wins")
    print("  - Detects more than 5 consecutive wins")
    print("  - Detects win streaks at any position")
    print("  - Correctly rejects streaks less than 5")
    print("  - Requires minimum 5 games played")


if __name__ == "__main__":
    test_win_streak()
