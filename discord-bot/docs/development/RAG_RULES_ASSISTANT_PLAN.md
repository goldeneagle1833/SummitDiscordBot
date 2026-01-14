# AI RAG Rules Assistant Implementation Plan

## Overview

This document outlines the plan to implement a Retrieval-Augmented Generation (RAG) system for the Discord bot. The system will answer rules questions for Sorcery: Contested Realm by querying a knowledge base of official rules, FAQs, and card rulings.

## What is RAG?

RAG combines:

1. **Retrieval**: Finding relevant documents/chunks from a knowledge base
2. **Augmented**: Injecting retrieved context into the AI prompt
3. **Generation**: Using an LLM to generate accurate answers based on the context

This prevents hallucinations by grounding responses in actual documentation.

---

## Architecture

```
User Question
     │
     ▼
┌─────────────────┐
│  Discord Bot    │
│  (!rules cmd)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Query Embedding │  ◄── OpenAI/Local Embeddings
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Vector Search  │  ◄── ChromaDB / Pinecone / FAISS
│  (Find similar  │
│   documents)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Context Build  │  ◄── Top 3-5 relevant chunks
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   LLM (GPT-4)   │  ◄── System prompt + context + question
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Discord Response│
└─────────────────┘
```

---

## Knowledge Base Structure

### Documents to Include

```
knowledge_base/
├── rules/
│   ├── comprehensive_rules.md      # Full rulebook
│   ├── quick_start_rules.md        # Beginner rules
│   └── tournament_rules.md         # Competitive play rules
├── faqs/
│   ├── general_faq.md              # Common questions
│   ├── keyword_faq.md              # Keyword ability questions
│   └── timing_faq.md               # Stack/timing questions
├── card_rulings/
│   ├── errata.md                   # Official card errata
│   └── specific_rulings.md         # Specific card interactions
├── glossary/
│   └── terms.md                    # Game terminology definitions
└── metadata/
    └── sources.json                # Document metadata & versions
```

### Document Format

Each document should be in Markdown with clear headers for chunking:

```markdown
# Section Title

## Subsection

### Rule 1.2.3 - Combat Phase

The combat phase consists of...

---

### Rule 1.2.4 - Declaring Attackers

When declaring attackers...
```

---

## Required Components

### 1. Vector Database (Choose One)

| Option       | Pros                                   | Cons                                  | Cost      |
| ------------ | -------------------------------------- | ------------------------------------- | --------- |
| **ChromaDB** | Free, local, easy setup, Python native | Limited scale                         | Free      |
| **Pinecone** | Managed, scalable, fast                | Paid after free tier                  | $0-70/mo  |
| **FAISS**    | Free, Facebook-backed, very fast       | More setup, no persistence by default | Free      |
| **Weaviate** | Open source, hybrid search             | More complex                          | Free/Paid |

**Recommendation**: Start with **ChromaDB** for simplicity, migrate to Pinecone if scaling needed.

### 2. Embedding Model (Choose One)

| Option                            | Dimensions | Cost            | Quality |
| --------------------------------- | ---------- | --------------- | ------- |
| **OpenAI text-embedding-3-small** | 1536       | $0.02/1M tokens | Good    |
| **OpenAI text-embedding-3-large** | 3072       | $0.13/1M tokens | Best    |
| **sentence-transformers (local)** | 384-768    | Free            | Good    |

**Recommendation**: **OpenAI text-embedding-3-small** - good balance of cost/quality, already using OpenAI.

### 3. LLM for Generation

Already using OpenAI - continue with **GPT-4.1-nano** for cost efficiency or **GPT-4o** for best quality.

### 4. Document Processing

- **LangChain** or **LlamaIndex** for document loading and chunking
- Markdown parser for structured documents
- Chunk size: 500-1000 tokens with overlap

---

## Python Dependencies

```txt
# Add to requirements.txt

# Vector Database
chromadb>=0.4.0

# Document Processing & RAG Framework
langchain>=0.1.0
langchain-openai>=0.0.5
langchain-community>=0.0.10

# Text Processing
tiktoken>=0.5.0          # Token counting
unstructured>=0.10.0     # Document parsing

# Optional: Alternative embeddings
# sentence-transformers>=2.2.0
```

---

## Implementation Steps

### Phase 1: Knowledge Base Setup (Week 1)

- [ ] Create `SorceryAI/` directory at root level (same as discord-bot/)
- [ ] Create directory structure inside SorceryAI
- [ ] Gather and format official rules documents
- [ ] Convert PDFs/docs to clean Markdown
- [ ] Add clear section headers for chunking
- [ ] Create metadata file tracking document versions

### Phase 2: Vector Database Setup (Week 1-2)

- [ ] Install ChromaDB in SorceryAI
- [ ] Create `SorceryAI/core/` module structure
- [ ] Create embedding pipeline (`embeddings.py`)
- [ ] Implement document chunking (500 tokens, 50 token overlap)
- [ ] Build initial vector index (`scripts/index_knowledge_base.py`)
- [ ] Create index update script for new documents

### Phase 3: RAG Pipeline (Week 2)

- [ ] Implement query embedding in `core/embeddings.py`
- [ ] Implement similarity search in `core/retriever.py`
- [ ] Build context assembly (combine relevant chunks)
- [ ] Create system prompt for rules assistant in `core/prompts.py`
- [ ] Implement response generation in `core/generator.py` with citations

### Phase 4: Discord Integration (Week 2-3)

- [ ] Create new cog: `discord-bot/cogs/rules_assistant.py`
- [ ] Import SorceryAI modules in the cog
- [ ] Implement `!rules <question>` command
- [ ] Implement `/rules` slash command
- [ ] Add response formatting (embeds, citations)
- [ ] Add rate limiting per user

### Phase 5: Testing & Refinement (Week 3)

- [ ] Test with common rules questions using `scripts/test_queries.py`
- [ ] Tune chunk size and overlap
- [ ] Tune number of retrieved chunks
- [ ] Adjust system prompt for accuracy
- [ ] Add fallback for low-confidence answers

### Phase 6: Maintenance Tools (Ongoing)

- [ ] Script to re-index knowledge base (`scripts/update_documents.py`)
- [ ] Admin command to add quick rulings
- [ ] Logging for question analytics
- [ ] Feedback mechanism for wrong answers

---

## Code Structure

```
SummitDiscordBot/
├── discord-bot/
│   ├── cogs/
│   │   └── rules_assistant.py      # Discord commands for rules
│   └── utils/
│       └── ...
├── web-app/
│   └── ...
└── SorceryAI/                       # NEW: RAG System
    ├── config.py                    # Configuration (API keys, DB paths)
    ├── requirements.txt             # Python dependencies
    ├── README.md                    # Setup instructions
    ├── api/
    │   ├── __init__.py
    │   └── rules_api.py             # FastAPI/Flask endpoint (optional)
    ├── core/
    │   ├── __init__.py
    │   ├── embeddings.py            # Embedding generation
    │   ├── vector_store.py          # ChromaDB interface
    │   ├── retriever.py             # Similarity search
    │   ├── generator.py             # LLM response generation
    │   └── prompts.py               # System prompts
    ├── knowledge_base/
    │   ├── rules/
    │   │   ├── comprehensive_rules.md
    │   │   ├── quick_start_rules.md
    │   │   └── tournament_rules.md
    │   ├── faqs/
    │   │   ├── general_faq.md
    │   │   ├── keyword_faq.md
    │   │   └── timing_faq.md
    │   ├── card_rulings/
    │   │   ├── errata.md
    │   │   └── specific_rulings.md
    │   ├── glossary/
    │   │   └── terms.md
    │   └── metadata/
    │       └── sources.json
    ├── scripts/
    │   ├── index_knowledge_base.py  # Build vector index
    │   ├── update_documents.py      # Add/update documents
    │   └── test_queries.py          # Test question/answer
    ├── data/
    │   └── chroma_db/               # ChromaDB storage (gitignored)
    └── tests/
        ├── test_embeddings.py
        ├── test_retriever.py
        └── test_generator.py
```

---

## Example System Prompt

```python
RULES_ASSISTANT_PROMPT = """You are a helpful rules assistant for the card game Sorcery: Contested Realm.

Your role is to answer rules questions accurately based ONLY on the official rules documentation provided below.

IMPORTANT GUIDELINES:
1. Only answer based on the provided context
2. If the answer is not in the context, say "I couldn't find a specific ruling for that. Please check the official rules or ask a judge."
3. Quote specific rule numbers when applicable (e.g., "According to Rule 3.2.1...")
4. Be concise but complete
5. If a question is ambiguous, ask for clarification

CONTEXT FROM RULES DOCUMENTATION:
{context}

---

USER QUESTION: {question}

ANSWER:"""
```

---

## Example Discord Command

```python
# In discord-bot/cogs/rules_assistant.py

import sys
sys.path.append('../SorceryAI')  # Add SorceryAI to path

from core.retriever import RulesRetriever
from core.generator import RulesGenerator

class RulesAssistantCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.retriever = RulesRetriever()
        self.generator = RulesGenerator()

    @app_commands.command(name="rules", description="Ask a rules question")
    @app_commands.describe(question="Your rules question")
    async def rules_command(self, interaction: discord.Interaction, question: str):
        await interaction.response.defer(thinking=True)

        # Retrieve relevant context from SorceryAI
        context_chunks = await self.retriever.search(question, top_k=5)

        # Generate response using SorceryAI
        response = await self.generator.generate(
            question=question,
            context=context_chunks
        )

        # Format embed with answer and sources
        embed = discord.Embed(
            title="📜 Rules Answer",
            description=response.answer,
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Sources",
            value="\n".join(response.sources),
            inline=False
        )

        await interaction.followup.send(embed=embed)
```

---

## Cost Estimates

### One-Time Indexing

- ~50 pages of rules ≈ 25,000 tokens
- Embedding cost: ~$0.01

### Per Query

- Query embedding: ~$0.0001
- GPT-4.1-nano generation: ~$0.001-0.005
- **Estimated: $0.005/query**

### Monthly (Estimated 1000 queries)

- ~$5-10/month for moderate usage

---

## Future Enhancements

1. **Card-Specific Rulings**: Link to card database for card-specific Q&A
2. **Conversation Memory**: Multi-turn conversations for follow-up questions
3. **Admin Portal**: Web interface to manage knowledge base
4. **Auto-Update**: Webhook to update when official docs change
5. **Confidence Scoring**: Show confidence level in answers
6. **Multi-Language**: Support for non-English rules

---

## Resources Needed

### Documents to Acquire

- [ ] Official Comprehensive Rules PDF
- [ ] Quick Start Guide
- [ ] Tournament Rules
- [ ] Official FAQ (if available)
- [ ] Card errata list

### Accounts/Services

- [x] OpenAI API key (already have)
- [ ] Optional: Pinecone account (if scaling needed)

### Development Time

- Estimated: 2-3 weeks for full implementation
- MVP (basic Q&A): 1 week

---

## Questions to Decide

1. **Hosting**: Vector DB stored locally in `SorceryAI/data/chroma_db/` (gitignored)
2. **Scope**: Start with just rules, or include card database from the start?
3. **Moderation**: Should answers be reviewed before sending?
4. **Channel Restriction**: Limit to specific channels or allow anywhere?
5. **Deployment**: Should SorceryAI be a separate microservice or integrated library?

---

## Next Steps

1. ✅ Create this plan document
2. ⬜ Create `SorceryAI/` directory structure at root level
3. ⬜ Gather and format rules documentation
4. ⬜ Set up ChromaDB in SorceryAI folder
5. ⬜ Create basic embedding pipeline
6. ⬜ Build initial knowledge base index
7. ⬜ Test with sample questions
8. ⬜ Integrate with Discord bot via import
