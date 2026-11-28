"""Write one claimed feedback item into .feedback-task/ for Claude to read.

usage: python -I prepare.py <claim_dir> <item_id> <out_dir>
"""

import json
import sys
from pathlib import Path


def main(claim_dir: str, item_id: str, out_dir: str) -> None:
    claim = json.loads((Path(claim_dir) / "claim.json").read_text())
    open_prs = json.loads((Path(claim_dir) / "open_prs.json").read_text() or "[]")
    wanted = int(item_id)
    item = next(i for i in claim["items"] if int(i["id"]) == wanted)
    others = [i for i in claim["items"] if int(i["id"]) != wanted]

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "item.json").write_text(json.dumps({
        "id": item["id"],
        "type": item.get("type"),
        "source": item.get("source"),
        "title": item.get("title", ""),
        "description": item.get("description", ""),
    }, indent=2))
    (out / "context.json").write_text(json.dumps({
        "open_auto_prs": open_prs,
        "other_items_this_run": [{"id": i["id"], "title": i["title"]} for i in others],
        "recent_feedback": claim.get("recent", []),
    }, indent=2))


if __name__ == "__main__":
    main(*sys.argv[1:4])
