"""
Test embeddings module
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from core.embeddings import get_embedding, count_tokens, chunk_text


def test_get_embedding():
    """Test embedding generation."""
    text = "This is a test sentence."
    embedding = get_embedding(text)
    assert len(embedding) == 1536  # text-embedding-3-small dimensions
    assert all(isinstance(x, float) for x in embedding)


def test_count_tokens():
    """Test token counting."""
    text = "This is a test."
    tokens = count_tokens(text)
    assert tokens > 0


def test_chunk_text():
    """Test text chunking."""
    text = " ".join(["word"] * 1000)  # Create long text
    chunks = chunk_text(text, chunk_size=100, overlap=10)
    assert len(chunks) > 1


if __name__ == "__main__":
    test_get_embedding()
    print("✓ Embedding test passed")

    test_count_tokens()
    print("✓ Token counting test passed")

    test_chunk_text()
    print("✓ Chunking test passed")

    print("\nAll tests passed!")
