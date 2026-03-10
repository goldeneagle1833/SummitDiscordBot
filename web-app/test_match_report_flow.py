"""Test complete match report submission flow with auto table creation"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from services.match_confirmation import MatchConfirmationService

print("Testing complete match report submission flow...")
print("=" * 60)

# Test data
submitter_id = "google_123456789"
opponent_id = "987654321"
result = "won"
went_first = "submitter"
submitter_deck_url = "https://curiosa.io/decks/testdeck123"
final_life_submitter = 20
final_life_opponent = 0

print(f"\nSubmitter: {submitter_id}")
print(f"Opponent: {opponent_id}")
print(f"Result: {result}")
print(f"Went first: {went_first}")
print(f"Submitter deck: {submitter_deck_url}")
print(f"Final life: Submitter={final_life_submitter}, Opponent={final_life_opponent}")

# Create service (this will auto-create table if needed)
print("\nCreating MatchConfirmationService...")
service = MatchConfirmationService()

# Submit match report
print("Submitting match report...")
try:
    result_data = service.create_match_report(
        submitter_id=submitter_id,
        opponent_id=opponent_id,
        result=result,
        went_first=went_first,
        submitter_deck_url=submitter_deck_url,
        opponent_deck_url=None,
        final_life_submitter=final_life_submitter,
        final_life_opponent=final_life_opponent
    )

    print("\n[SUCCESS] Match report created!")
    print(f"  - Confirmation ID: {result_data['confirmation_id']}")
    print(f"  - Expires at: {result_data['expires_at']}")
    print(f"  - Opponent: {result_data['opponent']['display_name']} ({result_data['opponent']['user_id']})")
    print(f"  - Message: {result_data['message']}")

except Exception as e:
    print(f"\n[ERROR] Failed to create match report: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("Test complete!")
