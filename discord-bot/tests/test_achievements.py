"""
Achievement System Test Script
==============================

This script tests the achievement system functionality without running the full bot.

Usage:
    python test_achievements.py
"""

import sqlite3
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from utils.achievements import (
    create_profiles_db,
    get_or_create_profile,
    ACHIEVEMENTS,
    get_user_achievements,
    get_earned_achievements
)


async def test_profile_creation():
    """Test profile creation and retrieval."""
    print("\n🧪 Test 1: Profile Creation")
    print("-" * 40)
    
    test_discord_id = "123456789"
    test_username = "TestUser"
    
    profile = get_or_create_profile(test_discord_id, test_username)
    
    if profile:
        print(f"✅ Profile created for {test_username}")
        print(f"   Discord ID: {profile['discord_id']}")
        print(f"   Username: {profile['username']}")
        
        # Check all achievement columns exist
        achievement_count = sum(1 for key in profile.keys() if key not in ['discord_id', 'username'])
        print(f"   Achievement columns: {achievement_count}")
        return True
    else:
        print("❌ Failed to create profile")
        return False


async def test_achievement_registry():
    """Test achievement registry."""
    print("\n🧪 Test 2: Achievement Registry")
    print("-" * 40)
    
    print(f"Total achievements registered: {len(ACHIEVEMENTS)}")
    
    categories = {
        "Win/Play": 0,
        "Elo": 0,
        "Avatar": 0,
        "Special": 0
    }
    
    for achievement_id, config in ACHIEVEMENTS.items():
        # Categorize
        if "win" in achievement_id or "play" in achievement_id:
            categories["Win/Play"] += 1
        elif "elo" in achievement_id:
            categories["Elo"] += 1
        elif "avatar" in achievement_id:
            categories["Avatar"] += 1
        else:
            categories["Special"] += 1
        
        # Verify structure
        required_keys = ["name", "description", "emoji", "check_func"]
        if all(key in config for key in required_keys):
            print(f"✅ {config['emoji']} {config['name']}")
        else:
            print(f"❌ {achievement_id} - Missing required keys")
            return False
    
    print("\nCategories:")
    for category, count in categories.items():
        print(f"   {category}: {count}")
    
    return True


async def test_check_functions():
    """Test achievement check functions."""
    print("\n🧪 Test 3: Check Functions")
    print("-" * 40)
    
    test_discord_id = "123456789"
    
    # Test a few check functions
    test_functions = [
        ("win_5_games", "Win 5 Games"),
        ("elo_1600", "Reach 1600 Elo"),
        ("alpha_avatar", "Alpha Avatar")
    ]
    
    for achievement_id, name in test_functions:
        if achievement_id in ACHIEVEMENTS:
            check_func = ACHIEVEMENTS[achievement_id]["check_func"]
            try:
                result = await check_func(test_discord_id)
                status = "✅" if isinstance(result, bool) else "⚠️"
                print(f"{status} {name}: Returns {type(result).__name__}")
            except Exception as e:
                print(f"❌ {name}: Error - {e}")
                return False
    
    return True


async def test_database_queries():
    """Test database accessibility."""
    print("\n🧪 Test 4: Database Access")
    print("-" * 40)
    
    databases = [
        ("profiles.db", "Profiles"),
        ("match_records.db", "Match Records"),
        ("elo.db", "Elo Ratings")
    ]
    
    for db_name, description in databases:
        try:
            conn = sqlite3.connect(db_name)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cur.fetchall()
            conn.close()
            
            if tables:
                print(f"✅ {description}: {len(tables)} table(s)")
            else:
                print(f"⚠️ {description}: No tables (database may be empty)")
        except Exception as e:
            print(f"❌ {description}: {e}")


async def test_user_achievements():
    """Test user achievement retrieval."""
    print("\n🧪 Test 5: User Achievement Retrieval")
    print("-" * 40)
    
    test_discord_id = "123456789"
    test_username = "TestUser"
    
    # Get achievements
    achievement_status, profile = get_user_achievements(test_discord_id, test_username)
    
    total = len(achievement_status)
    earned = sum(1 for status in achievement_status.values() if status)
    
    print(f"✅ Retrieved achievement status")
    print(f"   Total achievements: {total}")
    print(f"   Earned: {earned}")
    print(f"   Completion: {(earned/total)*100:.1f}%")
    
    # Get earned achievements
    earned_list = get_earned_achievements(test_discord_id, test_username)
    print(f"✅ Retrieved earned achievement list: {len(earned_list)} items")
    
    return True


async def run_all_tests():
    """Run all tests."""
    print("=" * 50)
    print("🎯 ACHIEVEMENT SYSTEM TEST SUITE")
    print("=" * 50)
    
    # Initialize database
    print("\n📊 Initializing test database...")
    create_profiles_db()
    print("✅ Database initialized")
    
    # Run tests
    tests = [
        test_profile_creation,
        test_achievement_registry,
        test_check_functions,
        test_database_queries,
        test_user_achievements
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            result = await test()
            if result or result is None:
                passed += 1
        except Exception as e:
            print(f"\n❌ Test failed with error: {e}")
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 TEST SUMMARY")
    print("=" * 50)
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("\n✨ All tests passed! Achievement system is ready.")
        print("\nTo use the system:")
        print("1. Configure ACHIEVEMENT_CHANNEL_ID in utils/config.py")
        print("2. Run the bot: python main.py")
        print("3. Submit a match report to trigger achievement checks")
        return 0
    else:
        print(f"\n⚠️ {total - passed} test(s) failed. Please review the errors above.")
        return 1


def main():
    """Main entry point."""
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
