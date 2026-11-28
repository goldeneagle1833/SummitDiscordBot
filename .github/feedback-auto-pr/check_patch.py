"""Decide what to do with one item after Claude ran: open a draft PR or just report.

Runs in the publish job, which holds the write token, so it never executes
anything from the patch. It only reads triage.json, change.patch and tests.txt
and writes decision.json:

  {"status": "drafted|duplicate|needs_human|not_actionable|failed",
   "note": "...", "title": "...", "branch": "...", "open_pr": true|false}

plus pr_body.md when a PR should be opened.

usage: python -I check_patch.py <item_id> <out_dir>
"""

import json
import re
import sys
from pathlib import Path

MAX_FILES = 25
MAX_CHANGED_LINES = 800

BLOCKED_PREFIXES = (".github/", "web-app/nginx/", ".feedback-task/")
BLOCKED_NAMES = {
    "config.py", "requirements.txt", "requirements-dev.txt", "package.json",
    "package-lock.json", "gunicorn_config.py", "gunicorn_priority_config.py",
}
BLOCKED_SUFFIXES = (".db", ".sqlite", ".sqlite3", ".pem", ".key", ".p12", ".service", ".sh")
SECRET = re.compile(
    r"(sk-ant-|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_|xox[bp]-|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|AKIA[0-9A-Z]{16})"
)
DECISIONS = {"draft", "duplicate", "not_actionable", "needs_human"}


def blocked(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return (
        path.startswith(BLOCKED_PREFIXES)
        or name in BLOCKED_NAMES
        or name.startswith(".env")
        or name.endswith(BLOCKED_SUFFIXES)
        or "deploy" in name.lower()
        or ".." in path.split("/")
    )


def patch_problems(patch: str) -> list[str]:
    problems = []
    files = set()
    changed = 0
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            parts = line.split(" ")
            for part in parts[2:4]:
                files.add(part[2:] if part[:2] in ("a/", "b/") else part)
        elif line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
            changed += 1
            if line.startswith("+") and SECRET.search(line):
                problems.append("the change contains something that looks like a secret")
        elif line.startswith("GIT binary patch"):
            problems.append("the change contains a binary file")
    for path in sorted(files):
        if blocked(path):
            problems.append(f"the change touches a protected file ({path})")
    if len(files) > MAX_FILES:
        problems.append(f"the change touches {len(files)} files (limit {MAX_FILES})")
    if changed > MAX_CHANGED_LINES:
        problems.append(f"the change is {changed} lines (limit {MAX_CHANGED_LINES})")
    return sorted(set(problems))


def one_line(text, limit):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text[:limit]


def decide(item_id: int, out: Path) -> dict:
    triage_path = out / "triage.json"
    if not triage_path.exists():
        return {"status": "failed", "note": "The auto PR run didn't finish this item."}
    try:
        triage = json.loads(triage_path.read_text())
    except json.JSONDecodeError:
        return {"status": "failed", "note": "The auto PR run gave an unreadable answer."}
    decision = triage.get("decision")
    if decision not in DECISIONS:
        return {"status": "failed", "note": "The auto PR run gave an unknown decision."}
    summary = one_line(triage.get("summary"), 400)

    if decision == "duplicate":
        dup = one_line(triage.get("duplicate_of"), 120)
        return {"status": "duplicate", "note": f"{summary} {f'(same as {dup})' if dup else ''}".strip()}
    if decision in ("not_actionable", "needs_human"):
        return {"status": decision, "note": summary}

    patch_path = out / "change.patch"
    patch = patch_path.read_text(errors="replace") if patch_path.exists() else ""
    if not patch.strip():
        return {"status": "needs_human", "note": f"Claude meant to draft a fix but made no change. {summary}"}
    problems = patch_problems(patch)
    if problems:
        return {"status": "failed", "note": "Change thrown away: " + "; ".join(problems) + "."}

    title = one_line(triage.get("pr_title"), 90) or f"Player feedback #{item_id}"
    tests = (out / "tests.txt").read_text(errors="replace") if (out / "tests.txt").exists() else "Tests were not run."
    body = (
        f"**Auto-drafted from player feedback #{item_id}.** Nothing here is merged or "
        "deployed. Review it like any outside contribution, and take desktop and phone "
        "screenshots before merging any page change.\n\n"
        f"{str(triage.get('pr_body') or summary)[:6000]}\n\n"
        f"### Tests run by the workflow\n\n```\n{tests[-3000:]}\n```\n\n"
        "_Checks from the other PR workflows don't start on PRs the bot opens; push any "
        "commit (or close and reopen) to run them._\n"
    )
    (out / "pr_body.md").write_text(body)
    return {
        "status": "drafted",
        "note": summary,
        "title": f"Feedback #{item_id}: {title}",
        "open_pr": True,
    }


def main(item_id: str, out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    result = decide(int(item_id), out)
    result.setdefault("open_pr", False)
    result["branch"] = f"auto-feedback/{int(item_id)}"
    (out / "decision.json").write_text(json.dumps(result))
    print(json.dumps({k: result[k] for k in ("status", "note", "open_pr")}))


if __name__ == "__main__":
    main(*sys.argv[1:3])
