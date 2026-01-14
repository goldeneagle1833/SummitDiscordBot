"""
Test queries against the RAG system
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from core.retriever import RulesRetriever
from core.generator import RulesGenerator


def test_query(question: str):
    """Test a single query."""
    print(f"\n{'=' * 80}")
    print(f"QUESTION: {question}")
    print("=" * 80)

    retriever = RulesRetriever()
    generator = RulesGenerator()

    # Retrieve context
    print("\nRetrieving context...")
    context = retriever.search(question, top_k=5)

    print(f"Found {len(context)} relevant chunks:")
    for i, chunk in enumerate(context, 1):
        print(f"  {i}. {chunk.source} (distance: {chunk.distance:.3f})")

    # Generate answer
    print("\nGenerating answer...")
    response = generator.generate(question, context)

    print("\nANSWER:")
    print(response.answer)

    print("\nSOURCES:")
    for source in response.sources:
        print(f"  - {source}")

    return response


def main():
    """Run test queries."""
    test_questions = [
        "How do i win?",
        "What is a mana?",
        "Can I play cards during my opponent's turn?",
        "How do I attack?",
        "What happens when a creature dies?",
        "what is deaths door?",
    ]

    print("SorceryAI - Test Queries")
    print("=" * 80)

    for question in test_questions:
        try:
            test_query(question)
        except Exception as e:
            print(f"\nERROR: {e}")

    print("\n" + "=" * 80)
    print("Testing complete!")


if __name__ == "__main__":
    main()
