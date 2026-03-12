# Documentation

This folder contains technical documentation and implementation notes for the Summit Discord Bot project.

## Main Documentation Files (in root)

### Getting Started
- **[../README.md](../README.md)** - Main project README with quickstart
- **[../CONTRIBUTING.md](../CONTRIBUTING.md)** - How to contribute
- **[../TESTING.md](../TESTING.md)** - Testing guide and strategies
- **[../GITHUB_SETUP_GUIDE.md](../GITHUB_SETUP_GUIDE.md)** - Repository setup for maintainers

### Architecture & Development
- **[../CLAUDE.md](../CLAUDE.md)** - Comprehensive architecture documentation
  - Project overview and structure
  - Cog system architecture
  - Database patterns
  - External integrations
  - Development patterns

## Technical Implementation Notes

This folder contains historical implementation summaries and bug fix documentation:

- **IMPLEMENTATION_SUMMARY.md** - General implementation notes
- **DUAL_ELO_IMPLEMENTATION_SUMMARY.md** - Dual ELO system implementation
- **GOOGLE_OAUTH_OVERFLOW_FIX.md** - OAuth overflow bug fix
- **OPPONENT_SEARCH_500_ERROR_FIX.md** - Opponent search error fix

These files are kept for historical reference and to help understand past decisions.

## Component-Specific Documentation

### Discord Bot
- See `discord-bot/` folder for cog-specific documentation
- Test documentation in `discord-bot/tests/`

### Web Application
- **[../web-app/DEPLOYMENT.md](../web-app/DEPLOYMENT.md)** - Web app deployment guide

### SorceryAI
- **[../SorceryAI/DEPLOYMENT.md](../SorceryAI/DEPLOYMENT.md)** - AI system deployment
- Knowledge base documentation in `SorceryAI/knowledge_base/`

## Quick Links

### For Contributors
1. Read [CONTRIBUTING.md](../CONTRIBUTING.md)
2. Review [CLAUDE.md](../CLAUDE.md) for architecture
3. Follow [TESTING.md](../TESTING.md) for testing

### For Maintainers
1. Review [GITHUB_SETUP_GUIDE.md](../GITHUB_SETUP_GUIDE.md)
2. Check deployment docs for each component
3. Review implementation notes in this folder

## Documentation Standards

When adding new documentation:
- Place user-facing docs in root directory
- Place technical/historical docs in `docs/`
- Use clear, descriptive titles
- Include examples where helpful
- Link between related documents
- Keep README.md updated with new docs

## Need Help?

- Check [../README.md](../README.md) first
- Review relevant documentation files
- Open an issue on GitHub
- Join the Discord community
