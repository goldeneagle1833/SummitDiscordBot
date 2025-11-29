"""
Test Avatar Set Detection
==========================

This script tests the avatar set detection logic for Alpha and Beta achievements.
It demonstrates how the system identifies which set an avatar belongs to.
"""

import json

# Sample deck data structures based on All_Cards_Array.json format

# Example 1: Avatar with sets array (actual structure from All_Cards_Array.json)
alpha_avatar_deck = {
    "avatar": [
        {
            "name": "Avatar of Air",
            "rarity": "Elite",
            "type": "Avatar",
            "sets": [
                {
                    "name": "Alpha",
                    "releasedAt": "2023-04-19T00:00:00.000Z"
                }
            ]
        }
    ],
    "spellbook": [],
    "atlas": [],
    "sideboard": []
}

beta_avatar_deck = {
    "avatar": [
        {
            "name": "Avatar of Fire",
            "rarity": "Elite", 
            "type": "Avatar",
            "sets": [
                {
                    "name": "Beta",
                    "releasedAt": "2023-06-15T00:00:00.000Z"
                }
            ]
        }
    ],
    "spellbook": [],
    "atlas": [],
    "sideboard": []
}

arthurian_avatar_deck = {
    "avatar": [
        {
            "name": "Druid",
            "rarity": "Elite",
            "type": "Avatar",
            "sets": [
                {
                    "name": "Arthurian Legends",
                    "releasedAt": "2024-10-04T00:00:00.000Z"
                }
            ]
        }
    ],
    "spellbook": [],
    "atlas": [],
    "sideboard": []
}

# Example 2: Avatar with set_name field (alternative format)
alpha_avatar_simple = {
    "avatar": [
        {
            "name": "Avatar of Water",
            "rarity": "Elite",
            "type": "Avatar",
            "set_name": "Alpha"
        }
    ],
    "spellbook": [],
    "atlas": [],
    "sideboard": []
}


def check_avatar_set(deck_data: dict, target_set: str) -> bool:
    """
    Check if the deck's avatar is from a specific set.
    
    Args:
        deck_data: Deck JSON data
        target_set: Name of the set to check for (e.g., "Alpha", "Beta", "Arthurian Legends")
    
    Returns:
        True if avatar is from the target set, False otherwise
    """
    try:
        avatar = deck_data.get("avatar", [])
        
        if avatar and len(avatar) > 0:
            avatar_card = avatar[0]
            
            # Check set_name field (simpler format)
            if "set_name" in avatar_card:
                if avatar_card.get("set_name", "").lower() == target_set.lower():
                    return True
            
            # Check sets array (All_Cards_Array.json format)
            if "sets" in avatar_card:
                for card_set in avatar_card.get("sets", []):
                    if isinstance(card_set, dict) and card_set.get("name", "").lower() == target_set.lower():
                        return True
                        
    except (KeyError, TypeError, IndexError):
        return False
    
    return False


def test_avatar_detection():
    """Test avatar set detection with different deck configurations."""
    
    print("=" * 60)
    print("AVATAR SET DETECTION TESTS")
    print("=" * 60)
    
    # Test Alpha avatars
    print("\n🅰️ Testing Alpha Avatar Detection:")
    print(f"  Alpha deck (sets array): {check_avatar_set(alpha_avatar_deck, 'Alpha')}")
    print(f"  Alpha deck (set_name): {check_avatar_set(alpha_avatar_simple, 'Alpha')}")
    print(f"  Beta deck: {check_avatar_set(beta_avatar_deck, 'Alpha')}")
    print(f"  Arthurian deck: {check_avatar_set(arthurian_avatar_deck, 'Alpha')}")
    
    # Test Beta avatars
    print("\n🅱️ Testing Beta Avatar Detection:")
    print(f"  Beta deck: {check_avatar_set(beta_avatar_deck, 'Beta')}")
    print(f"  Alpha deck: {check_avatar_set(alpha_avatar_deck, 'Beta')}")
    print(f"  Arthurian deck: {check_avatar_set(arthurian_avatar_deck, 'Beta')}")
    
    # Test Arthurian Legends avatars
    print("\n⚔️ Testing Arthurian Legends Avatar Detection:")
    print(f"  Arthurian deck: {check_avatar_set(arthurian_avatar_deck, 'Arthurian Legends')}")
    print(f"  Alpha deck: {check_avatar_set(alpha_avatar_deck, 'Arthurian Legends')}")
    print(f"  Beta deck: {check_avatar_set(beta_avatar_deck, 'Arthurian Legends')}")
    
    print("\n" + "=" * 60)
    print("DECK STRUCTURE EXAMPLES")
    print("=" * 60)
    
    print("\n📋 Alpha Avatar Deck Structure:")
    print(json.dumps(alpha_avatar_deck, indent=2))
    
    print("\n📋 Beta Avatar Deck Structure:")
    print(json.dumps(beta_avatar_deck, indent=2))
    
    print("\n📋 Arthurian Legends Avatar Deck Structure:")
    print(json.dumps(arthurian_avatar_deck, indent=2))
    
    print("\n✅ All tests completed!")


if __name__ == "__main__":
    test_avatar_detection()
