"""
Retriever for finding relevant documents based on query
"""

import sys
from pathlib import Path

# Add discord-bot to path to use shared config
_bot_path = str(Path(__file__).parent.parent.parent / "discord-bot")
if _bot_path not in sys.path:
    sys.path.insert(0, _bot_path)

from typing import List, Dict, Set
from dataclasses import dataclass
from core.embeddings import get_embedding, _get_client
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

    def expand_query(self, query: str, num_variations: int = 3) -> List[str]:
        """
        Generate multiple query variations to improve retrieval coverage.

        Args:
            query: Original user question
            num_variations: Number of variations to generate

        Returns:
            List of query variations including the original
        """
        client = _get_client()

        prompt = f"""Given this question about Sorcery: Contested Realm rules:
"{query}"

Generate {num_variations - 1} alternative phrasings that ask the same thing using different terminology.
Focus on game mechanic synonyms and different ways players might ask.

Format: Return only the alternative questions, one per line."""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,  # Lower for more consistent query variations
        )

        variations = [query]  # Include original
        alt_queries = response.choices[0].message.content.strip().split("\n")
        variations.extend([q.strip("- ").strip() for q in alt_queries if q.strip()])

        return variations[:num_variations]

    def search_with_expansion(
        self,
        query: str,
        top_k: int = config.TOP_K_RESULTS,
        num_variations: int = 3,
    ) -> List[RetrievedChunk]:
        """
        Search with query expansion for better coverage.

        Args:
            query: Original question
            top_k: Number of results per variation
            num_variations: Number of query variations to generate

        Returns:
            Deduplicated list of relevant chunks
        """
        # Generate query variations
        queries = self.expand_query(query, num_variations)

        # Search with each variation
        all_chunks = []
        seen_texts: Set[str] = set()

        for q in queries:
            chunks = self.search(q, top_k=top_k)
            for chunk in chunks:
                # Deduplicate by text content
                if chunk.text not in seen_texts:
                    seen_texts.add(chunk.text)
                    all_chunks.append(chunk)

        # Sort by relevance (distance)
        all_chunks.sort(key=lambda c: c.distance)

        # Return top results across all variations
        return all_chunks[: top_k * 2]  # Return more since we're combining results
