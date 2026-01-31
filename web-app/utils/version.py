"""Application version utilities."""

import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def get_app_version() -> str:
    """Get application version from git commit hash or fallback to timestamp."""
    try:
        git_dir = Path(__file__).parent.parent.parent / ".git"
        if git_dir.exists():
            head_file = git_dir / "HEAD"
            if head_file.exists():
                with open(head_file, "r") as f:
                    ref = f.read().strip()
                if ref.startswith("ref: "):
                    ref_path = git_dir / ref[5:]
                    if ref_path.exists():
                        with open(ref_path, "r") as f:
                            return f.read().strip()[:8]
                else:
                    return ref[:8]
    except Exception as e:
        logger.warning(f"Could not get git version: {e}")

    try:
        mtime = os.path.getmtime(Path(__file__).parent.parent / "app.py")
        return str(int(mtime))
    except Exception:
        return "1.0.0"


APP_VERSION = get_app_version()
