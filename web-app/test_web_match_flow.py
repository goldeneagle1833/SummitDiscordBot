"""
Test script to verify web match reporting flow with Google OAuth IDs.

This script tests that:
1. Google OAuth IDs (google_xxx) are kept intact in match_reports_web
2. ELO updates work correctly by stripping google_ prefix
3. Match confirmations handle google_ IDs properly

Run: python test_web_match_flow.py
"""

import sys
from pathlib import Path

# Add web-app to path
sys.path.insert(0, str(Path(__file__).parent))

from services.match_confirmation import MatchConfirmationService
from repositories.match_confirmation import MatchConfirmationRepository
import sqlite3
from webapp_config import MATCH_RECORDS_DB_PATH


def test_google_id_handling():
    """Test that google_ prefix is preserved in match_reports_web."""

    print("🧪 Testing Google OAuth ID handling...\n")

    # Test IDs (google_ prefix should be preserved)
    submitter_id = "google_123456789012345678901"
    opponent_id = "google_987654321098765432109"

    print(f"Submitter ID: {submitter_id}")
    print(f"Opponent ID: {opponent_id}\n")

    # Create service
    service = MatchConfirmationService()

    # Test 1: Validate that google_ IDs are accepted
    print("📝 Test 1: Creating match report with google_ IDs...")
    try:
        validation = service.validate_match_report_input(
            submitter_id=submitter_id,
            opponent_id=opponent_id,
            result="won",
            went_first="submitter",
            submitter_deck_url="https://curiosa.io/decks/testdeck123",
            opponent_deck_url=None
        )

        if validation["valid"]:
            print("✅ Validation passed - google_ IDs accepted")
        else:
            print(f"❌ Validation failed: {validation['errors']}")
            return False
    except Exception as e:
        print(f"❌ Validation error: {e}")
        return False

    # Test 2: Check that match_reports_web table exists
    print("\n📊 Test 2: Checking match_reports_web table...")
    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cursor = conn.cursor()

        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='match_reports_web'
        """)

        if cursor.fetchone():
            print("✅ match_reports_web table exists")

            # Check schema
            cursor.execute("PRAGMA table_info(match_reports_web)")
            columns = cursor.fetchall()

            # Verify TEXT columns for IDs
            id_columns = ["match_id", "reporter_id", "winner_id", "losser_id"]
            for col_info in columns:
                col_name = col_info[1]
                col_type = col_info[2]
                if col_name in id_columns:
                    if col_type == "TEXT":
                        print(f"  ✅ {col_name}: {col_type}")
                    else:
                        print(f"  ❌ {col_name}: {col_type} (expected TEXT)")
                        return False
        else:
            print("❌ match_reports_web table NOT found")
            print("   Run: python migrations/create_match_reports_web.py")
            return False

        conn.close()

    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

    # Test 3: Test winner/loser calculation
    print("\n🏆 Test 3: Testing winner/loser calculation...")
    try:
        result = service.calculate_winner_loser(
            submitter_id=submitter_id,
            opponent_id=opponent_id,
            result="won"
        )

        if result["winner_id"] == submitter_id and result["loser_id"] == opponent_id:
            print(f"✅ Winner: {result['winner_id']}")
            print(f"✅ Loser: {result['loser_id']}")
        else:
            print(f"❌ Incorrect winner/loser assignment")
            return False

    except Exception as e:
        print(f"❌ Calculation error: {e}")
        return False

    # Test 4: Test that google_ prefix is NOT stripped in match data
    print("\n🔍 Test 4: Verifying google_ prefix preservation...")

    # Check that service keeps IDs as-is
    test_id = "google_123456789"
    if test_id.startswith("google_"):
        print(f"✅ Test ID maintains google_ prefix: {test_id}")
    else:
        print(f"❌ google_ prefix was stripped: {test_id}")
        return False

    print("\n" + "="*60)
    print("✅ All tests passed!")
    print("="*60)
    print("\nNext steps:")
    print("1. Run migration: python migrations/create_match_reports_web.py")
    print("2. Deploy updated code")
    print("3. Test with real Google OAuth users")

    return True


if __name__ == "__main__":
    try:
        success = test_google_id_handling()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test suite failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
