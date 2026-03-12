# Contribution Workflow Diagram

## 🔄 Full Contribution Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     CONTRIBUTOR WORKFLOW                         │
└─────────────────────────────────────────────────────────────────┘

1. FORK REPOSITORY
   ↓
2. CLONE FORK
   git clone https://github.com/contributor/SummitDiscordBot
   ↓
3. SET UP TEST ENVIRONMENT
   • Create test Discord bot
   • Create test Discord server
   • Run: python scripts/create_test_databases.py
   • Copy config.example.py → config.py
   • Add test bot token to .env
   ↓
4. CREATE FEATURE BRANCH
   git checkout -b feature/my-feature
   ↓
5. MAKE CHANGES
   • Edit code
   • Add tests
   • Test locally
   ↓
6. RUN TESTS
   pytest tests/ -v
   ↓
7. COMMIT & PUSH
   git commit -m "Add feature: description"
   git push origin feature/my-feature
   ↓
8. OPEN PULL REQUEST
   GitHub: New Pull Request → Your Fork → Main Repo
   ↓
   ┌─────────────────────────────────────────────────────────────┐
   │                    GITHUB ACTIONS                           │
   │  • Automatically runs pytest                                │
   │  • Comments on PR with results                              │
   │  • ✅ Pass → Ready for review                               │
   │  • ❌ Fail → Needs fixes                                    │
   └─────────────────────────────────────────────────────────────┘
   ↓
9. CODE REVIEW
   Maintainer reviews code
   ↓
10. APPROVAL & MERGE
    Maintainer clicks "Merge"
    ↓
    ┌─────────────────────────────────────────────────────────────┐
    │              AUTO-DEPLOY TO PRODUCTION                      │
    │  • deploy-bot.yml triggered                                 │
    │  • deploy-web.yml triggered                                 │
    │  • Changes go live!                                         │
    └─────────────────────────────────────────────────────────────┘
```

---

## 🛡️ Branch Protection Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    MAIN BRANCH PROTECTION                        │
└─────────────────────────────────────────────────────────────────┘

ATTEMPT: git push origin main
   ↓
   ❌ REJECTED!
   "Branch protection: direct push not allowed"
   ↓
CORRECT FLOW:
   ↓
1. Create feature branch
   git checkout -b feature/my-fix
   ↓
2. Push feature branch
   git push origin feature/my-fix
   ↓
3. Open Pull Request on GitHub
   ↓
4. Tests must pass ✅
   ↓
5. Get approval from maintainer ✅
   ↓
6. Maintainer clicks "Merge"
   ↓
   ✅ SUCCESS: Changes merged to main!
```

---

## 🧪 Testing Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                      TEST ENVIRONMENTS                           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────┐  ┌────────────────────────────────┐
│  CONTRIBUTOR LOCAL TESTING  │  │   PRODUCTION ENVIRONMENT       │
├─────────────────────────────┤  ├────────────────────────────────┤
│ • Test Discord bot          │  │ • Production Discord bot       │
│ • Test Discord server       │  │ • Production Discord server    │
│ • Test databases            │  │ • Production databases         │
│   - test_match_records.db   │  │   - match_records.db          │
│   - test_elo.db             │  │   - elo.db                    │
│   - test_fart_scores.db     │  │   - fart_scores.db            │
│ • Sample data               │  │ • Real user data              │
│ • Safe to break!            │  │ • Protected!                  │
└─────────────────────────────┘  └────────────────────────────────┘
         ↓                                   ↑
         ↓                                   ↑
    [TEST LOCALLY]                           ↑
         ↓                                   ↑
    [RUN pytest]                             ↑
         ↓                                   ↑
    [OPEN PR]                                ↑
         ↓                                   ↑
 [GITHUB ACTIONS TESTS]                      ↑
         ↓                                   ↑
    [CODE REVIEW]                            ↑
         ↓                                   ↑
    [MERGE TO MAIN] ─────────────────────────┘

    [AUTO-DEPLOY]
```

---

## 📊 Repository Structure

```
SummitDiscordBot/
│
├── 📝 DOCUMENTATION (Root Level)
│   ├── README.md                    ← Main project overview
│   ├── CONTRIBUTING.md              ← How to contribute
│   ├── TESTING.md                   ← Testing guide
│   ├── GITHUB_SETUP_GUIDE.md        ← GitHub configuration
│   ├── PRE_RELEASE_CHECKLIST.md     ← Pre-release tasks
│   ├── RELEASE_SUMMARY.md           ← What was done
│   ├── CLAUDE.md                    ← Architecture docs
│   └── LICENSE                      ← MIT License
│
├── 📁 docs/                         ← Technical documentation
│   ├── README.md                    ← Docs index
│   ├── WORKFLOW_DIAGRAM.md          ← This file
│   └── [Technical summaries]
│
├── 🤖 discord-bot/                  ← Discord bot application
│   ├── cogs/                        ← Command modules
│   ├── repositories/                ← Data access
│   ├── services/                    ← Business logic
│   ├── utils/                       ← Utilities
│   ├── tests/                       ← Test suite (87+ tests)
│   ├── scripts/
│   │   └── create_test_databases.py ← Test DB setup
│   ├── config.example.py            ← Config template
│   ├── .env.example                 ← Environment template
│   └── main.py                      ← Entry point
│
├── 🌐 web-app/                      ← Flask web app
│   └── [Web app files]
│
├── 🧠 SorceryAI/                    ← RAG system
│   └── [AI system files]
│
└── ⚙️ .github/
    └── workflows/
        ├── pr-test-bot.yml          ← PR testing
        ├── deploy-bot.yml           ← Bot deployment
        ├── deploy-web.yml           ← Web deployment
        └── deploy-ai.yml            ← AI deployment
```

---

## 🔐 Security Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    SECRET MANAGEMENT                             │
└─────────────────────────────────────────────────────────────────┘

PRODUCTION SECRETS (Never Committed)
   ├── config.py           ← Contains Discord IDs, config
   ├── .env                ← Contains TOKEN, API_KEY
   └── *.db                ← Contains user data
          ↓
     [.gitignore]          ← Prevents commit
          ↓
   ❌ BLOCKED from Git

COMMITTED TO REPO (Safe)
   ├── config.example.py   ← Template with placeholders
   ├── .env.example        ← Template for env vars
   └── test_data/*.db      ← Sample data only
          ↓
   ✅ Safe to share publicly

CONTRIBUTOR SETUP
   1. Copy templates
      cp config.example.py → config.py
      cp .env.example → .env
   2. Fill in TEST values (not production!)
   3. Never commit these files
```

---

## 🚦 PR Status Checks

```
┌─────────────────────────────────────────────────────────────────┐
│                  PULL REQUEST CHECKS                             │
└─────────────────────────────────────────────────────────────────┘

PR OPENED
   ↓
[1] GitHub Actions: Test Runner
    • pytest tests/ -v
    • Check syntax
    • Comment results on PR
    ↓
    ✅ PASS                 ❌ FAIL
    ↓                      ↓
    Green checkmark        Red X
    ↓                      ↓
    Ready for review       Needs fixes
    ↓                      ↓
[2] Code Review            FIX → Re-run tests
    • Maintainer reviews   ↓
    • Leaves comments      Go back to step 1
    • Requests changes
    ↓
[3] Approval Required
    • 1 approval needed
    • All comments resolved
    ↓
[4] Merge Button Enabled
    • Only maintainer can click
    • Merges to main
    ↓
[5] Auto-Deploy
    • Production deployment
    • Changes go live
```

---

## 📈 Contribution Metrics

```
BEFORE                          AFTER SETUP
─────────────────────────────────────────────────────────
❌ No documentation             ✅ 7 documentation files
❌ No contributor guide         ✅ CONTRIBUTING.md
❌ No branch protection         ✅ Branch protection ready
❌ No test infrastructure       ✅ Test DBs + config templates
❌ No CI/CD for PRs             ✅ GitHub Actions workflow
❌ Secrets at risk              ✅ .gitignore configured
❌ No clear workflow            ✅ Complete workflow docs
```

---

## 🎯 Quick Reference

### For Contributors
1. Read [CONTRIBUTING.md](../CONTRIBUTING.md)
2. Set up test environment
3. Make changes
4. Run tests: `pytest tests/ -v`
5. Open PR

### For Maintainer
1. Review [GITHUB_SETUP_GUIDE.md](../GITHUB_SETUP_GUIDE.md)
2. Set up branch protection
3. Review PRs when they come in
4. Approve and merge

### For Everyone
- All code changes go through PRs
- Tests must pass before merge
- No direct pushes to main
- Use test environments, never production
