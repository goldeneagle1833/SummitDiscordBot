"""
Update documents and re-index the knowledge base
Useful for adding new documents or updating existing ones
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from scripts.index_knowledge_base import index_documents
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def update_and_reindex():
    """Update the vector store with any new or modified documents."""
    logger.info("Starting knowledge base update...")

    try:
        # Re-index everything
        index_documents()
        logger.info("Knowledge base updated successfully!")
        return True
    except Exception as e:
        logger.error(f"Failed to update knowledge base: {e}")
        return False


if __name__ == "__main__":
    success = update_and_reindex()
    sys.exit(0 if success else 1)
