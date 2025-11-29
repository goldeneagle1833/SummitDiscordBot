"""
Database Migration Script for Achievement System (OPTIONAL)
============================================================

This script manually initializes the profiles database for the achievement system.

NOTE: This script is OPTIONAL. The database is automatically created when the bot
starts or when a user first accesses their profile. You only need to run this if
you want to verify the database setup before starting the bot.

Usage:
    python init_achievements_db.py
"""

import sqlite3
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from utils.achievements import create_profiles_db


def main():
    """Initialize the achievement system database."""
    print("🎯 Achievement System Database Initialization (Optional)")
    print("=" * 50)
    print("\nℹ️  NOTE: The database is created automatically when the bot starts.")
    print("   This script is only needed if you want to verify setup manually.\n")
    
    try:
        # Create the profiles database
        print("📊 Creating profiles.db table...")
        create_profiles_db()
        print("✅ Profiles database created successfully!")
        
        # Verify the database
        conn = sqlite3.connect("profiles.db")
        cur = conn.cursor()
        
        # Get table info
        cur.execute("PRAGMA table_info(profiles)")
        columns = cur.fetchall()
        
        print(f"\n📋 Database schema verified:")
        print(f"   - Table: profiles")
        print(f"   - Columns: {len(columns)}")
        
        achievement_columns = [col[1] for col in columns if col[1] not in ['discord_id', 'username']]
        print(f"   - Achievement fields: {len(achievement_columns)}")
        
        conn.close()
        
        print("\n" + "=" * 50)
        print("✨ Achievement system database is ready!")
        print("\nNext steps:")
        print("1. Configure ACHIEVEMENT_CHANNEL_ID in utils/config.py (optional)")
        print("2. Start the bot with: python main.py")
        print("3. The database will be automatically maintained from now on")
        print("\nFor more info, see ACHIEVEMENT_QUICKSTART.md")
        
    except Exception as e:
        print(f"\n❌ Error initializing database: {e}")
        print("\nPlease check:")
        print("- File permissions in the current directory")
        print("- No other process is using profiles.db")
        print("- utils/achievements.py exists and is valid")
        sys.exit(1)


if __name__ == "__main__":
    main()
