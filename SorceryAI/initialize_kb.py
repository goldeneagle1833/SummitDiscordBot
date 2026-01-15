#!/usr/bin/env python3
"""
Initialize the knowledge base on the server.
Run this once after deploying to ensure the ChromaDB collection exists.
"""

import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Add discord-bot to path to use shared config
_bot_path = str(Path(__file__).parent.parent / "discord-bot")
if _bot_path not in sys.path:
    sys.path.insert(0, _bot_path)

from init import initialize

if __name__ == "__main__":
    print("Initializing SorceryAI knowledge base...")
    print("This will index all rules documents into ChromaDB.")
    print("This may take a few minutes on first run...\n")

    try:
        if initialize():
            print("\n✅ Knowledge base initialized successfully!")
            print("The bot can now answer rules questions.")
        else:
            print("\n❌ Failed to initialize knowledge base")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error initializing knowledge base: {e}")
        sys.exit(1)
