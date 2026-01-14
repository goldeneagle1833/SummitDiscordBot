# SorceryAI Deployment Guide

## Server Deployment Steps

### 1. Initial Setup on Server

```bash
# SSH into server
ssh root@50.116.43.215

# Navigate to project
cd ~/Summit/SummitDiscordBot

# Pull latest changes
git pull

# Navigate to SorceryAI
cd SorceryAI

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Configuration

Ensure `OPENAI_API_KEY` is set in the environment (should already be set for discord-bot).

```bash
# Check if set
echo $OPENAI_API_KEY

# If not set, add to your environment or .env file
export OPENAI_API_KEY="your-key-here"
```

### 3. Initialize Knowledge Base

**Option A: Automatic (Recommended)**

The system will auto-initialize on first use. The Discord bot will automatically:

1. Check if the knowledge base is indexed
2. Index it if needed
3. Start serving requests

**Option B: Manual**

```bash
# Index the knowledge base manually
cd ~/Summit/SummitDiscordBot/SorceryAI
python scripts/index_knowledge_base.py

# Test it works
python scripts/test_queries.py
```

### 4. Restart Discord Bot

```bash
# Restart bot to load SorceryAI
systemctl restart discord-bot
# OR
pm2 restart discord-bot
# OR manually restart however you run it
```

---

## Automatic Initialization

The system includes automatic initialization that runs when the Discord bot starts:

1. **On Bot Startup**: The rules assistant cog will initialize SorceryAI
2. **Checks**: System verifies API key, knowledge base, and index
3. **Auto-Index**: If no index exists, it automatically indexes the knowledge base
4. **Graceful Degradation**: If initialization fails, the bot logs errors but continues running

---

## File Structure on Server

```
~/Summit/SummitDiscordBot/
├── discord-bot/
│   └── cogs/
│       └── rules_assistant.py    # Imports from ../SorceryAI
├── web-app/
└── SorceryAI/
    ├── core/
    ├── knowledge_base/            # Rules docs (tracked in git)
    ├── scripts/
    └── data/
        └── chroma_db/             # Generated on server (gitignored)
```

---

## Important Notes

### Persistent Data

The `SorceryAI/data/chroma_db/` directory contains the vector database. It:

- ✅ Is automatically created on server
- ✅ Persists between deployments
- ❌ Is NOT tracked in git (.gitignored)
- ⚠️ Will be recreated if deleted (takes ~30 seconds)

### Knowledge Base Updates

When you update rules documents:

```bash
# After git pull with new rules
cd ~/Summit/SummitDiscordBot/SorceryAI
python scripts/index_knowledge_base.py  # Re-index
```

Or use the update script:

```bash
python scripts/update_documents.py
```

### Monitoring

Check if SorceryAI is working:

```bash
# Check bot logs
tail -f ~/Summit/SummitDiscordBot/discord-bot/discord_bot.log

# Look for:
# "Initializing SorceryAI..."
# "Knowledge base indexed successfully"
# "SorceryAI initialized successfully"
```

---

## Troubleshooting

### Index Not Building

```bash
# Check if knowledge base has content
ls -la ~/Summit/SummitDiscordBot/SorceryAI/knowledge_base/rules/

# Manually rebuild
cd ~/Summit/SummitDiscordBot/SorceryAI
rm -rf data/chroma_db/
python scripts/index_knowledge_base.py
```

### API Key Issues

```bash
# Verify API key is set
cd ~/Summit/SummitDiscordBot/SorceryAI
python -c "import config; print('OK' if config.OPENAI_API_KEY else 'MISSING')"
```

### Import Errors in Discord Bot

```bash
# Verify Python can import SorceryAI
cd ~/Summit/SummitDiscordBot/discord-bot
python -c "import sys; sys.path.append('../SorceryAI'); from core.retriever import RulesRetriever; print('OK')"
```

---

## CI/CD Integration (Optional)

For automated deployment, add to your deployment script:

```bash
#!/bin/bash
# deploy.sh

cd ~/Summit/SummitDiscordBot
git pull

# Install SorceryAI dependencies
cd SorceryAI
pip install -r requirements.txt

# Re-index if knowledge base changed
if git diff --name-only HEAD@{1} HEAD | grep "SorceryAI/knowledge_base"; then
    echo "Knowledge base changed, re-indexing..."
    python scripts/index_knowledge_base.py
fi

# Restart bot
systemctl restart discord-bot
```

---

## Performance

- **Initial Index**: ~30 seconds for typical rulebook
- **Query Time**: ~1-2 seconds (embedding + retrieval + generation)
- **Storage**: ~10MB for typical knowledge base
- **Memory**: ~100MB additional for bot

---

## Next Steps After Deployment

1. ✅ Deploy to server
2. ✅ Verify automatic initialization works
3. ✅ Test `/rules` command in Discord
4. ⬜ Add actual rules documents to `knowledge_base/`
5. ⬜ Re-index with real content
6. ⬜ Monitor usage and refine prompts
