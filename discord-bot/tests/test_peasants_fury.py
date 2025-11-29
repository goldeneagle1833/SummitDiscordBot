"""
Test script for Peasant's Fury achievement
"""
import json

# Sample deck data from the user's example
deck_data = {
  "id": "cmeixm96y00lhjs04zkbf7co1",
  "name": "Big Fury",
  "username": "Goldeneagle1833",
  "avatar": [
    {
      "identifier": "sorcerer",
      "name": "Sorcerer",
      "rarity": "Ordinary"
    }
  ],
  "spellbook": [
    {"name": "Root Spider", "rarity": "Exceptional"},
    {"name": "Slumbering Giantess", "rarity": "Exceptional"},
    {"name": "Bury", "rarity": "Ordinary"},
    {"name": "Common Sense", "rarity": "Ordinary"},
    {"name": "Dispel", "rarity": "Ordinary"},
    {"name": "Earthquake", "rarity": "Elite"},  # This disqualifies the deck
    {"name": "Courtesan Thais", "rarity": "Unique"},
  ],
  "atlas": [
    {"name": "Holy Ground", "rarity": "Exceptional"},
    {"name": "Arid Desert", "rarity": "Ordinary"},
  ],
  "sideboard": [
    {"name": "Sand Worm", "rarity": "Ordinary"},
  ]
}

def check_peasants_fury_logic(deck_data):
    """Test the Peasant's Fury achievement logic"""
    
    # Check all cards except avatar
    cards_to_check = []
    
    # Add spellbook cards
    if "spellbook" in deck_data:
        cards_to_check.extend(deck_data["spellbook"])
    
    # Add atlas (site) cards
    if "atlas" in deck_data:
        cards_to_check.extend(deck_data["atlas"])
    
    # Add sideboard cards
    if "sideboard" in deck_data:
        cards_to_check.extend(deck_data["sideboard"])
    
    print(f"Total cards to check (excluding avatar): {len(cards_to_check)}")
    print("\nCard rarities:")
    for card in cards_to_check:
        rarity = card.get("rarity", "Unknown")
        print(f"  - {card.get('name', 'Unknown')}: {rarity}")
    
    # Check if ALL cards are Ordinary or Exceptional
    if cards_to_check:
        non_qualifying_cards = [
            card for card in cards_to_check
            if card.get("rarity", "").lower() not in ["ordinary", "exceptional"]
        ]
        
        if non_qualifying_cards:
            print(f"\n❌ DISQUALIFIED - Contains {len(non_qualifying_cards)} non-Ordinary/Exceptional cards:")
            for card in non_qualifying_cards:
                print(f"  - {card.get('name')}: {card.get('rarity')}")
            return False
        else:
            print("\n✅ QUALIFIES - All cards are Ordinary or Exceptional!")
            return True
    
    return False


# Test with the provided deck
print("="*60)
print("Testing Peasant's Fury Achievement")
print("="*60)
print(f"Deck: {deck_data['name']} by {deck_data['username']}")
print("="*60)

result = check_peasants_fury_logic(deck_data)

print("\n" + "="*60)
print(f"Result: {'ACHIEVEMENT EARNED' if result else 'NOT QUALIFIED'}")
print("="*60)

# Test with a qualifying deck
print("\n\n")
print("="*60)
print("Testing with a QUALIFYING deck")
print("="*60)

qualifying_deck = {
  "name": "Budget Deck",
  "avatar": [{"name": "Sorcerer", "rarity": "Ordinary"}],
  "spellbook": [
    {"name": "Root Spider", "rarity": "Exceptional"},
    {"name": "Bury", "rarity": "Ordinary"},
    {"name": "Common Sense", "rarity": "Ordinary"},
    {"name": "Slumbering Giantess", "rarity": "Exceptional"},
  ],
  "atlas": [
    {"name": "Holy Ground", "rarity": "Exceptional"},
    {"name": "Arid Desert", "rarity": "Ordinary"},
  ],
  "sideboard": []
}

result2 = check_peasants_fury_logic(qualifying_deck)
print("\n" + "="*60)
print(f"Result: {'ACHIEVEMENT EARNED' if result2 else 'NOT QUALIFIED'}")
print("="*60)
