"""
Embedding generation for documents and queries
"""

import sys
from pathlib import Path

# Add discord-bot to path to use shared config
_bot_path = str(Path(__file__).parent.parent.parent / "discord-bot")
if _bot_path not in sys.path:
    sys.path.insert(0, _bot_path)

import tiktoken
from openai import OpenAI
from typing import List, Union
import config

# Lazy-loaded client to avoid initialization issues
_client = None


def _get_client():
    """Get or create OpenAI client lazily."""
    global _client
    if _client is None:
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


def get_embedding(text: str, model: str = config.EMBEDDING_MODEL) -> List[float]:
    """
    Generate embedding for a single text.

    Args:
        text: Input text to embed
        model: OpenAI embedding model to use

    Returns:
        List of floats representing the embedding vector
    """
    text = text.replace("\n", " ")
    response = _get_client().embeddings.create(input=[text], model=model)
    return response.data[0].embedding


def get_embeddings(
    texts: List[str], model: str = config.EMBEDDING_MODEL
) -> List[List[float]]:
    """
    Generate embeddings for multiple texts (batch operation).

    Args:
        texts: List of texts to embed
        model: OpenAI embedding model to use

    Returns:
        List of embedding vectors
    """
    texts = [text.replace("\n", " ") for text in texts]
    response = _get_client().embeddings.create(input=texts, model=model)
    return [item.embedding for item in response.data]


def count_tokens(text: str, model: str = "gpt-4") -> int:
    """
    Count the number of tokens in a text.

    Args:
        text: Input text
        model: Model to use for tokenization

    Returns:
        Number of tokens
    """
    encoding = tiktoken.encoding_for_model(model)
    return len(encoding.encode(text))


def chunk_text(
    text: str, chunk_size: int = config.CHUNK_SIZE, overlap: int = config.CHUNK_OVERLAP
) -> List[str]:
    """
    Split text into overlapping chunks based on token count.

    Args:
        text: Input text to chunk
        chunk_size: Maximum tokens per chunk
        overlap: Number of overlapping tokens between chunks

    Returns:
        List of text chunks
    """
    encoding = tiktoken.encoding_for_model("gpt-4")
    tokens = encoding.encode(text)
    chunks = []

    start = 0
    while start < len(tokens):
        end = start + chunk_size
        chunk_tokens = tokens[start:end]
        chunk_text = encoding.decode(chunk_tokens)
        chunks.append(chunk_text)
        start += chunk_size - overlap

    return chunks
