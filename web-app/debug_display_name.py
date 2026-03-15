"""Debug script to test custom_display_name functionality."""

import sys
sys.path.insert(0, '.')

from repositories.user_profiles import UserProfileRepository

def test_display_name_flow():
    """Test the full flow of setting a custom display name."""

    repo = UserProfileRepository()

    # Test user data
    test_user_id = "google_test123456"
    test_provider = "google"
    test_display_name = "Test User"
    test_custom_name = "MyCustomName"

    print("=== Testing Custom Display Name Flow ===\n")

    # Step 1: Create a test user profile
    print("1. Creating test user profile...")
    repo.upsert_profile(
        user_id=test_user_id,
        display_name=test_display_name,
        provider=test_provider
    )
    print(f"   [OK] Created user: {test_user_id}\n")

    # Step 2: Check current custom_display_name
    print("2. Checking current custom_display_name...")
    current_custom_name = repo.get_custom_display_name(test_user_id, test_provider)
    print(f"   Current value: {current_custom_name!r}")
    print(f"   Should be: None\n")

    # Step 3: Set custom display name (first time - should succeed)
    print("3. Setting custom_display_name (first attempt)...")
    success1 = repo.set_custom_display_name(test_user_id, test_provider, test_custom_name)
    print(f"   Result: {success1}")
    print(f"   Expected: True\n")

    # Step 4: Verify it was set
    print("4. Verifying custom_display_name was set...")
    updated_custom_name = repo.get_custom_display_name(test_user_id, test_provider)
    print(f"   Current value: {updated_custom_name!r}")
    print(f"   Expected: '{test_custom_name}'\n")

    # Step 5: Try to set it again (should fail)
    print("5. Attempting to set custom_display_name again...")
    success2 = repo.set_custom_display_name(test_user_id, test_provider, "AnotherName")
    print(f"   Result: {success2}")
    print(f"   Expected: False (already set)\n")

    # Step 6: Test with non-existent user
    print("6. Testing with non-existent user...")
    success3 = repo.set_custom_display_name("nonexistent_user", test_provider, "TestName")
    print(f"   Result: {success3}")
    print(f"   Expected: False (user not found)\n")

    # Summary
    print("=== Test Summary ===")
    if success1 and not success2 and not success3 and updated_custom_name == test_custom_name:
        print("[PASS] All tests PASSED")
        print("\nThe custom_display_name logic is working correctly.")
        print("\nIf users are still seeing the error, it's likely due to:")
        print("1. Double-submission (already fixed with button disabling)")
        print("2. Browser/network retries")
        print("3. Check web app logs for duplicate API calls")
    else:
        print("[FAIL] Some tests FAILED")
        print(f"   First set succeeded: {success1} (expected: True)")
        print(f"   Second set failed: {not success2} (expected: True)")
        print(f"   Non-existent user failed: {not success3} (expected: True)")
        print(f"   Custom name was set: {updated_custom_name == test_custom_name} (expected: True)")

    # Cleanup
    print("\n=== Cleanup ===")
    conn = repo._get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM user_profiles WHERE user_id = ?", (test_user_id,))
    conn.commit()
    conn.close()
    print("[OK] Test user deleted")

if __name__ == "__main__":
    test_display_name_flow()
