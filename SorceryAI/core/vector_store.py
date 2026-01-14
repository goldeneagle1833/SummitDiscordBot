"""
Vector store interface using ChromaDB
"""

import chromadb
from chromadb.config import Settings
from typing import List, Dict, Optional
import config


class VectorStore:
    """Interface to ChromaDB for storing and retrieving document embeddings."""

    def __init__(self, collection_name: str = config.COLLECTION_NAME):
        """
        Initialize the vector store.

        Args:
            collection_name: Name of the ChromaDB collection
        """
        self.client = chromadb.PersistentClient(
            path=str(config.CHROMA_DB_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name=collection_name, metadata={"hnsw:space": config.DISTANCE_METRIC}
        )

    def add_documents(
        self,
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict],
        ids: List[str],
    ):
        """
        Add documents to the vector store.

        Args:
            documents: List of document texts
            embeddings: List of embedding vectors
            metadatas: List of metadata dicts for each document
            ids: List of unique IDs for each document
        """
        self.collection.add(
            documents=documents, embeddings=embeddings, metadatas=metadatas, ids=ids
        )

    def query(
        self,
        query_embedding: List[float],
        top_k: int = config.TOP_K_RESULTS,
        where: Optional[Dict] = None,
    ) -> Dict:
        """
        Query the vector store for similar documents.

        Args:
            query_embedding: Embedding vector of the query
            top_k: Number of results to return
            where: Optional metadata filter

        Returns:
            Dictionary with 'documents', 'distances', 'metadatas', 'ids'
        """
        results = self.collection.query(
            query_embeddings=[query_embedding], n_results=top_k, where=where
        )
        return results

    def delete_all(self):
        """Delete all documents from the collection."""
        self.client.delete_collection(self.collection.name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection.name, metadata={"hnsw:space": config.DISTANCE_METRIC}
        )

    def count(self) -> int:
        """Get the number of documents in the collection."""
        return self.collection.count()
