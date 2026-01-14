"""
Script to index the knowledge base into the vector store
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from core.embeddings import get_embeddings, chunk_text
from core.vector_store import VectorStore
import config
import json
from datetime import datetime


def load_documents():
    """Load all documents from knowledge_base directory."""
    documents = []
    kb_dir = config.KNOWLEDGE_BASE_DIR

    # Process all markdown files
    for category in ["rules", "faqs", "card_rulings", "glossary"]:
        category_dir = kb_dir / category
        if not category_dir.exists():
            print(f"Warning: {category_dir} does not exist")
            continue

        for md_file in category_dir.glob("*.md"):
            with open(md_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Chunk the document
            chunks = chunk_text(content)

            for i, chunk in enumerate(chunks):
                documents.append(
                    {
                        "text": chunk,
                        "source": f"{category}/{md_file.name}",
                        "chunk_id": i,
                        "category": category,
                    }
                )

    return documents


def index_documents():
    """Index all documents into the vector store."""
    print("Loading documents...")
    documents = load_documents()

    if not documents:
        print("No documents found to index!")
        return

    print(f"Loaded {len(documents)} document chunks")

    print("Generating embeddings...")
    texts = [doc["text"] for doc in documents]
    embeddings = get_embeddings(texts)

    print("Storing in vector database...")
    vector_store = VectorStore()

    # Clear existing data
    vector_store.delete_all()

    # Add documents
    ids = [f"{doc['source']}_chunk_{doc['chunk_id']}" for doc in documents]
    metadatas = [
        {
            "source": doc["source"],
            "chunk_id": doc["chunk_id"],
            "category": doc["category"],
        }
        for doc in documents
    ]

    vector_store.add_documents(
        documents=texts, embeddings=embeddings, metadatas=metadatas, ids=ids
    )

    print(f"Successfully indexed {len(documents)} chunks")

    # Save metadata
    metadata_file = config.KNOWLEDGE_BASE_DIR / "metadata" / "index_metadata.json"
    metadata = {
        "indexed_at": datetime.now().isoformat(),
        "num_documents": len(documents),
        "embedding_model": config.EMBEDDING_MODEL,
        "chunk_size": config.CHUNK_SIZE,
        "chunk_overlap": config.CHUNK_OVERLAP,
    }

    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"Metadata saved to {metadata_file}")


if __name__ == "__main__":
    index_documents()
