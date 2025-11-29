"""
Test New Achievements
=====================

Test logic for the 6 new achievements:
- Underdog Victory
- Giant Slayer
- Avatar Collector
- Mono Element Master
- First Blood
- Rivalry
"""

import json


def test_avatar_collector():
    """Test Avatar Collector logic - 5 different avatars."""
    print("=" * 60)
    print("AVATAR COLLECTOR TEST")
    print("=" * 60)
    
    games = [
        {"avatar": [{"name": "Avatar of Air"}]},
        {"avatar": [{"name": "Avatar of Fire"}]},
        {"avatar": [{"name": "Avatar of Water"}]},
        {"avatar": [{"name": "Avatar of Earth"}]},
        {"avatar": [{"name": "Druid"}]},
    ]
    
    unique_avatars = set()
    for game in games:
        avatar = game.get("avatar", [])
        if avatar and len(avatar) > 0:
            avatar_name = avatar[0].get("name", "")
            if avatar_name:
                unique_avatars.add(avatar_name)
    
    result = len(unique_avatars) >= 5
    print(f"\nGames played with different avatars: {len(unique_avatars)}")
    print(f"Avatars used: {unique_avatars}")
    print(f"Achievement unlocked: {result} {'✅' if result else '❌'}")
    assert result == True


def test_mono_element():
    """Test Mono Element Master logic - single element deck."""
    print("\n" + "=" * 60)
    print("MONO ELEMENT MASTER TEST")
    print("=" * 60)
    
    # Test 1: Pure Fire deck
    fire_deck = {
        "spellbook": [
            {"name": "Fireball", "elements": "Fire"},
            {"name": "Inferno", "elements": "Fire"},
            {"name": "Blaze", "elements": "Fire"},
        ],
        "atlas": [
            {"name": "Volcano", "elements": "Fire"},
        ]
    }
    
    elements_set = set()
    all_cards = fire_deck.get("spellbook", []) + fire_deck.get("atlas", [])
    for card in all_cards:
        card_elements = card.get("elements", "")
        if card_elements and card_elements != "None":
            for element in card_elements.split("/"):
                element = element.strip()
                if element and element != "None":
                    elements_set.add(element)
    
    result1 = len(elements_set) == 1
    print(f"\nTest 1 - Pure Fire Deck:")
    print(f"  Elements found: {elements_set}")
    print(f"  Is mono-element: {result1} {'✅' if result1 else '❌'}")
    assert result1 == True
    
    # Test 2: Mixed deck (should fail)
    mixed_deck = {
        "spellbook": [
            {"name": "Fireball", "elements": "Fire"},
            {"name": "Tidal Wave", "elements": "Water"},
        ]
    }
    
    elements_set2 = set()
    all_cards2 = mixed_deck.get("spellbook", [])
    for card in all_cards2:
        card_elements = card.get("elements", "")
        if card_elements and card_elements != "None":
            for element in card_elements.split("/"):
                element = element.strip()
                if element and element != "None":
                    elements_set2.add(element)
    
    result2 = len(elements_set2) == 1
    print(f"\nTest 2 - Mixed Deck:")
    print(f"  Elements found: {elements_set2}")
    print(f"  Is mono-element: {result2} {'✅ PASS (correctly False)' if not result2 else '❌ FAIL'}")
    assert result2 == False


def test_first_blood():
    """Test First Blood logic - win first game."""
    print("\n" + "=" * 60)
    print("FIRST BLOOD TEST")
    print("=" * 60)
    
    # Test 1: Won first game
    games1 = [
        {"did_win": True, "timestamp": "2024-01-01 10:00:00"},
        {"did_win": False, "timestamp": "2024-01-01 11:00:00"},
        {"did_win": True, "timestamp": "2024-01-01 12:00:00"},
    ]
    
    games1_sorted = sorted(games1, key=lambda x: x["timestamp"])
    result1 = games1_sorted[0]["did_win"] if games1_sorted else False
    
    print(f"\nTest 1 - Won first game:")
    print(f"  First game result: {'Win' if games1_sorted[0]['did_win'] else 'Loss'}")
    print(f"  Achievement unlocked: {result1} {'✅' if result1 else '❌'}")
    assert result1 == True
    
    # Test 2: Lost first game
    games2 = [
        {"did_win": False, "timestamp": "2024-01-01 10:00:00"},
        {"did_win": True, "timestamp": "2024-01-01 11:00:00"},
    ]
    
    games2_sorted = sorted(games2, key=lambda x: x["timestamp"])
    result2 = games2_sorted[0]["did_win"] if games2_sorted else False
    
    print(f"\nTest 2 - Lost first game:")
    print(f"  First game result: {'Win' if games2_sorted[0]['did_win'] else 'Loss'}")
    print(f"  Achievement unlocked: {result2} {'✅ PASS (correctly False)' if not result2 else '❌ FAIL'}")
    assert result2 == False


def test_rivalry():
    """Test Rivalry logic - 10+ games against same opponent."""
    print("\n" + "=" * 60)
    print("RIVALRY TEST")
    print("=" * 60)
    
    games = [
        {"opponent_id": "user123"},
        {"opponent_id": "user123"},
        {"opponent_id": "user123"},
        {"opponent_id": "user123"},
        {"opponent_id": "user123"},
        {"opponent_id": "user123"},
        {"opponent_id": "user123"},
        {"opponent_id": "user123"},
        {"opponent_id": "user123"},
        {"opponent_id": "user123"},  # 10 games
        {"opponent_id": "user456"},
        {"opponent_id": "user456"},
    ]
    
    opponent_counts = {}
    for game in games:
        opp = game.get("opponent_id")
        if opp:
            opponent_counts[opp] = opponent_counts.get(opp, 0) + 1
    
    result = any(count >= 10 for count in opponent_counts.values())
    
    print(f"\nGames per opponent:")
    for opp, count in opponent_counts.items():
        print(f"  {opp}: {count} games")
    print(f"\nAchievement unlocked: {result} {'✅' if result else '❌'}")
    assert result == True


def test_elo_achievements():
    """Test Underdog Victory and Giant Slayer logic."""
    print("\n" + "=" * 60)
    print("ELO-BASED ACHIEVEMENTS TEST")
    print("=" * 60)
    
    user_elo = 1500
    
    # Test Underdog Victory (200+ Elo difference)
    winning_games = [
        {"opponent_elo": 1600},  # +100
        {"opponent_elo": 1750},  # +250 ✓
        {"opponent_elo": 1400},  # -100
    ]
    
    underdog = False
    for game in winning_games:
        if game["opponent_elo"] >= user_elo + 200:
            underdog = True
            break
    
    print(f"\nUnderdog Victory Test:")
    print(f"  User Elo: {user_elo}")
    print(f"  Opponent Elos: {[g['opponent_elo'] for g in winning_games]}")
    print(f"  Found win with 200+ Elo difference: {underdog} {'✅' if underdog else '❌'}")
    assert underdog == True
    
    # Test Giant Slayer (5 wins against higher Elo)
    winning_games2 = [
        {"opponent_elo": 1550},  # Higher ✓
        {"opponent_elo": 1600},  # Higher ✓
        {"opponent_elo": 1450},  # Lower
        {"opponent_elo": 1520},  # Higher ✓
        {"opponent_elo": 1580},  # Higher ✓
        {"opponent_elo": 1510},  # Higher ✓
    ]
    
    wins_against_higher = sum(1 for g in winning_games2 if g["opponent_elo"] > user_elo)
    giant_slayer = wins_against_higher >= 5
    
    print(f"\nGiant Slayer Test:")
    print(f"  User Elo: {user_elo}")
    print(f"  Wins against higher Elo: {wins_against_higher}/5")
    print(f"  Achievement unlocked: {giant_slayer} {'✅' if giant_slayer else '❌'}")
    assert giant_slayer == True


if __name__ == "__main__":
    test_avatar_collector()
    test_mono_element()
    test_first_blood()
    test_rivalry()
    test_elo_achievements()
    
    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED!")
    print("=" * 60)
    print("\n📊 SUMMARY:")
    print("  ✅ Avatar Collector - Detects 5 different avatars")
    print("  ✅ Mono Element Master - Detects single-element decks")
    print("  ✅ First Blood - Detects first game win")
    print("  ✅ Rivalry - Detects 10+ games vs same opponent")
    print("  ✅ Underdog Victory - Detects 200+ Elo difference win")
    print("  ✅ Giant Slayer - Detects 5 wins vs higher Elo")
