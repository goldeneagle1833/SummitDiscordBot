# SorceryAI - RAG Rules Assistant

AI-powered rules assistant for Sorcery: Contested Realm using Retrieval-Augmented Generation (RAG).

## Overview

SorceryAI is a standalone RAG system that answers rules questions by retrieving relevant context from a knowledge base of official rules, FAQs, and card rulings, then using an LLM to generate accurate responses.

## Quick Start

### Local Development

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Set environment variables:

```bash
export OPENAI_API_KEY="your-api-key-here"
```

3. The system will **automatically initialize** on first use!

### Server Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed deployment instructions.

**TL;DR:**

```bash
# On server
cd ~/Summit/SummitDiscordBot/SorceryAI
pip install -r requirements.txt
# System auto-initializes when Discord bot starts
```

## Automatic Initialization

✨ **No manual indexing required!**

The system automatically:

- Checks if knowledge base is indexed
- Indexes it on first use if needed
- Handles initialization gracefully

You can still manually index if desired:

```bash
python scripts/index_knowledge_base.py
```

## Project Structure

```
SorceryAI/
├── core/                   # Core RAG components
│   ├── embeddings.py      # Embedding generation
│   ├── vector_store.py    # ChromaDB interface
│   ├── retriever.py       # Similarity search
│   ├── generator.py       # LLM response generation
│   └── prompts.py         # System prompts
├── knowledge_base/        # Rules documentation
│   ├── rules/
│   ├── faqs/
│   ├── card_rulings/
│   └── glossary/
├── scripts/               # Utility scripts
├── data/                  # Vector database storage (gitignored)
└── tests/                 # Unit tests
```

## Usage

### From Python

```python
from core.retriever import RulesRetriever
from core.generator import RulesGenerator

retriever = RulesRetriever()
generator = RulesGenerator()

# Retrieve relevant context
context = retriever.search("How does the combat phase work?", top_k=5)

# Generate answer
response = generator.generate(question="How does the combat phase work?", context=context)
print(response.answer)
```

### From Discord Bot

See `discord-bot/cogs/rules_assistant.py` for integration example.

## Development

Run tests:

```bash
pytest tests/
```

Re-index knowledge base:

```bash
python scripts/index_knowledge_base.py
```

## License

Same as parent project.
