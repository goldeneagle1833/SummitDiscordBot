"""
Automatic initialization for SorceryAI on startup
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from core.vector_store import VectorStore
import config
import logging

logger = logging.getLogger("sorcery_ai")


def is_indexed() -> bool:
    """Check if the knowledge base has been indexed."""
    try:
        vector_store = VectorStore()
        count = vector_store.count()
        return count > 0
    except Exception as e:
        logger.error(f"Error checking index: {e}")
        return False


def auto_index():
    """Automatically index knowledge base if not already done."""
    if is_indexed():
        logger.info("Knowledge base already indexed")
        return True

    logger.info("Knowledge base not indexed. Indexing now...")
    try:
        from scripts.index_knowledge_base import index_documents

        index_documents()
        logger.info("Knowledge base indexed successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to auto-index knowledge base: {e}")
        return False


def initialize():
    """
    Initialize SorceryAI system.
    Call this before using the RAG system.

    Returns:
        bool: True if initialized successfully, False otherwise
    """
    logger.info("Initializing SorceryAI...")

    # Check if API key is set
    if not config.OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY not set in environment")
        return False

    # Check if knowledge base exists
    if not config.KNOWLEDGE_BASE_DIR.exists():
        logger.error(f"Knowledge base directory not found: {config.KNOWLEDGE_BASE_DIR}")
        return False

    # Auto-index if needed
    if not auto_index():
        logger.warning("Failed to initialize knowledge base index")
        return False

    logger.info("SorceryAI initialized successfully")
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = initialize()
    sys.exit(0 if success else 1)
