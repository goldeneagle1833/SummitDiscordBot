"""
LLM response generator with context
"""

import sys
from pathlib import Path

# Add discord-bot to path to use shared config
_bot_path = str(Path(__file__).parent.parent.parent / "discord-bot")
if _bot_path not in sys.path:
    sys.path.insert(0, _bot_path)

from typing import List
from dataclasses import dataclass
from openai import OpenAI
from core.retriever import RetrievedChunk
from core.prompts import RULES_ASSISTANT_PROMPT
import config

client = OpenAI(api_key=config.OPENAI_API_KEY)


@dataclass
class GeneratedResponse:
    """Container for generated response with metadata."""

    answer: str
    sources: List[str]
    context_used: str


class RulesGenerator:
    """Generates answers to rules questions using LLM with retrieved context."""

    def __init__(self, model: str = config.LLM_MODEL):
        """
        Initialize the generator.

        Args:
            model: OpenAI model to use for generation
        """
        self.model = model
        self._initialized = False

    def ensure_initialized(self):
        """Ensure the system is initialized before use."""
        if not self._initialized:
            from init import initialize

            if not initialize():
                raise RuntimeError("Failed to initialize SorceryAI system")
            self._initialized = True

    def generate(
        self, question: str, context: List[RetrievedChunk]
    ) -> GeneratedResponse:
        """
        Generate an answer to a question using retrieved context.

        Args:
            question: User's question
            context: List of retrieved document chunks

        Returns:
            GeneratedResponse with answer and sources
        """
        # Ensure system is initialized
        self.ensure_initialized()

        # Build context string
        context_str = self._build_context(context)

        # Build prompt
        prompt = RULES_ASSISTANT_PROMPT.format(context=context_str, question=question)

        # Generate response
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful rules assistant for Sorcery: Contested Realm.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=config.TEMPERATURE,
            max_tokens=config.MAX_RESPONSE_LENGTH,
        )

        answer = response.choices[0].message.content

        # Extract unique sources
        sources = list(set([chunk.source for chunk in context]))

        return GeneratedResponse(
            answer=answer, sources=sources, context_used=context_str
        )

    def _build_context(self, chunks: List[RetrievedChunk]) -> str:
        """
        Build context string from retrieved chunks.

        Args:
            chunks: List of retrieved chunks

        Returns:
            Formatted context string
        """
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            context_parts.append(f"[Source {i}: {chunk.source}]\n{chunk.text}\n")

        return "\n---\n".join(context_parts)
