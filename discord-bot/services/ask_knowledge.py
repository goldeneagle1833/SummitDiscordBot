"""Read-only view of the Summit code base for the @mention question answerer.

Only files git tracks are visible. The repository is public on GitHub, so the
bot can never show anything here that isn't already public: config.py, .env,
the databases, logs and backups on the server are untracked and invisible.
"""

from __future__ import annotations

import logging
import re
import subprocess
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger("discord_bot")

REPO_ROOT = Path(__file__).resolve().parents[2]

ALLOWED_SUFFIXES = {".py", ".md", ".jsx", ".js", ".txt"}

# Tracked, but nothing a player question needs (or noise / big data dumps).
BLOCKED_PARTS = {
    ".github", "node_modules", "dist", "pull_from_server", "backup",
    "top-8-decks-by-event", "data", "migrations", "nginx",
}
BLOCKED_NAMES = {"config.py", "config.example.py", "gunicorn_config.py"}

# Belt and braces: never return a line that looks like a credential.
_SECRET_LINE = re.compile(
    r"(sk-ant-|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|xox[bp]-|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|(api[_-]?key|secret|token|password)"
    r"\s*[:=]\s*['\"][^'\"\s]{12,}['\"])",
    re.IGNORECASE,
)

# Curated files sent with every question (the rest is reached with tools).
PACK_FILES = [
    "README.md",
    "discord-bot/README.md",
    "avatar-mode-season-guide.md",
    "web-app/frontend/src/pages/Help.jsx",
    "web-app/frontend/src/pages/About.jsx",
    "web-app/frontend/src/pages/SummitFormat.jsx",
    "discord-bot/services/provisional.py",
    "discord-bot/services/ranked_eligibility.py",
    "discord-bot/services/avatar_mode.py",
    "discord-bot/services/ticket_reset.py",
    "discord-bot/cogs/rating_decay.py",
    "discord-bot/cogs/lfg/queue_definitions.py",
    "discord-bot/cogs/lfg/skill_match.py",
]

MAX_READ_LINES = 250
MAX_MATCHES = 40


def _is_allowed(rel: str) -> bool:
    path = Path(rel)
    if path.suffix not in ALLOWED_SUFFIXES or path.name in BLOCKED_NAMES:
        return False
    if path.name.startswith(".env"):
        return False
    return not any(part in BLOCKED_PARTS for part in path.parts)


@lru_cache(maxsize=1)
def visible_files() -> tuple[str, ...]:
    """Repo-relative paths the bot may read (git-tracked and allowed)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-files"],
            capture_output=True, text=True, timeout=20, check=True,
        ).stdout
        files = [line.strip() for line in out.splitlines() if line.strip()]
    except Exception as exc:  # git missing: answer from the curated pack only
        logger.warning(f"ask_knowledge: git ls-files failed ({exc}); pack only")
        files = list(PACK_FILES)
    return tuple(sorted(f for f in files if _is_allowed(f) and (REPO_ROOT / f).is_file()))


def _clean(text: str) -> str:
    return "\n".join(
        "[line hidden]" if _SECRET_LINE.search(line) else line
        for line in text.splitlines()
    )


def _resolve(rel: str) -> Path | None:
    rel = (rel or "").strip().lstrip("/").replace("\\", "/")
    if rel not in set(visible_files()):
        return None
    path = (REPO_ROOT / rel).resolve()
    if REPO_ROOT not in path.parents:
        return None
    return path


@lru_cache(maxsize=1)
def knowledge_pack() -> str:
    """The curated files as one stable block of text (prompt-cache friendly)."""
    chunks = []
    for rel in PACK_FILES:
        path = _resolve(rel)
        if not path:
            continue
        try:
            chunks.append(f"===== {rel} =====\n{_clean(path.read_text(errors='replace'))}")
        except OSError:
            continue
    return "\n\n".join(chunks)


def search_code(query: str, path_contains: str = "") -> str:
    """Case-insensitive text search across visible files."""
    query = (query or "").strip()
    if len(query) < 2:
        return "Query too short."
    needle = query.lower()
    hits = []
    for rel in visible_files():
        if path_contains and path_contains.lower() not in rel.lower():
            continue
        try:
            lines = (REPO_ROOT / rel).read_text(errors="replace").splitlines()
        except OSError:
            continue
        for number, line in enumerate(lines, 1):
            if needle in line.lower():
                hits.append(f"{rel}:{number}: {_clean(line.strip())[:200]}")
                if len(hits) >= MAX_MATCHES:
                    return "\n".join(hits) + "\n(more matches cut off; narrow the search)"
    return "\n".join(hits) or "No matches."


def list_files(path_contains: str = "") -> str:
    files = [f for f in visible_files() if path_contains.lower() in f.lower()]
    if len(files) > 200:
        return "\n".join(files[:200]) + f"\n(+{len(files) - 200} more; narrow it)"
    return "\n".join(files) or "No files."


def read_file(path: str, start_line: int = 1, end_line: int | None = None) -> str:
    resolved = _resolve(path)
    if not resolved:
        return "That file isn't available. Use list_files or search_code to find one."
    lines = resolved.read_text(errors="replace").splitlines()
    start = max(1, int(start_line or 1))
    end = int(end_line) if end_line else start + MAX_READ_LINES - 1
    end = min(end, start + MAX_READ_LINES - 1, len(lines))
    body = "\n".join(f"{n}: {lines[n - 1]}" for n in range(start, end + 1))
    footer = f"\n(lines {start}-{end} of {len(lines)})"
    return _clean(body) + footer
