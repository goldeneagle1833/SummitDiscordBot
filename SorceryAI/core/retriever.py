"""
Retriever for finding relevant documents based on query
"""

import sys
from pathlib import Path

# Add discord-bot to path to use shared config
_bot_path = str(Path(__file__).parent.parent.parent / "discord-bot")
if _bot_path not in sys.path:
    sys.path.insert(0, _bot_path)

from typing import List, Dict
from dataclasses import dataclass
from core.embeddings import get_embedding
from core.vector_store import VectorStore
import config


@dataclass
class RetrievedChunk:
    """Container for a retrieved document chunk."""

    text: str
    source: str
    distance: float
    metadata: Dict


class RulesRetriever:
    """Retrieves relevant rules documentation based on queries."""

    def __init__(self):
        """Initialize the retriever with vector store."""
        self.vector_store = VectorStore()

    def search(
        self,
        query: str,
        top_k: int = config.TOP_K_RESULTS,
        filter_metadata: Dict = None,
    ) -> List[RetrievedChunk]:
        """
        Search for relevant documents.

        Args:
            query: User's question
            top_k: Number of results to return
            filter_metadata: Optional metadata filters

        Returns:
            List of RetrievedChunk objects
        """
        # Generate query embedding
        query_embedding = get_embedding(query)

        # Query vector store
        results = self.vector_store.query(
            query_embedding=query_embedding, top_k=top_k, where=filter_metadata
        )

        # Package results
        chunks = []
        for i in range(len(results["documents"][0])):
            chunk = RetrievedChunk(
                text=results["documents"][0][i],
                source=results["metadatas"][0][i].get("source", "Unknown"),
                distance=results["distances"][0][i],
                metadata=results["metadatas"][0][i],
            )
            chunks.append(chunk)

        return chunks

    def filter_by_confidence(
        self,
        chunks: List[RetrievedChunk],
        threshold: float = config.SIMILARITY_THRESHOLD,
    ) -> List[RetrievedChunk]:
        """
        Filter chunks by confidence threshold.

        Args:
            chunks: List of retrieved chunks
            threshold: Minimum confidence score (lower distance = higher confidence)

        Returns:
            Filtered list of chunks
        """
        # For cosine distance, lower is better. Threshold should be max distance.
        return [chunk for chunk in chunks if chunk.distance <= (1 - threshold)]
