#!/usr/bin/env python3
"""
Initialize the knowledge base on the server.
Run this once after deploying to ensure the ChromaDB collection exists.
"""

import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from core.knowledge_base import ensure_initialized

if __name__ == "__main__":
    print("Initializing SorceryAI knowledge base...")
    print("This will index all rules documents into ChromaDB.")
    print("This may take a few minutes on first run...\n")

    try:
        ensure_initialized()
        print("\n✅ Knowledge base initialized successfully!")
        print("The bot can now answer rules questions.")
    except Exception as e:
        print(f"\n❌ Error initializing knowledge base: {e}")
        sys.exit(1)
