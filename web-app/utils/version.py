"""Application version utilities."""

import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def get_app_version() -> str:
    """Get application version from git commit hash combined with static file mtimes.

    The git hash ensures cache busting on deploy; the mtime suffix ensures
    cache busting whenever any JS or CSS file is modified without a commit
    (useful during local development).
    """
    git_hash = None
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
                            git_hash = f.read().strip()[:8]
                else:
                    git_hash = ref[:8]
    except Exception as e:
        logger.warning(f"Could not get git version: {e}")

    # Find the most recent modification time across all JS and CSS static files
    latest_mtime = 0
    try:
        static_dir = Path(__file__).parent.parent / "static"
        for pattern in ("**/*.js", "**/*.css"):
            for f in static_dir.glob(pattern):
                mtime = f.stat().st_mtime
                if mtime > latest_mtime:
                    latest_mtime = mtime
    except Exception:
        pass

    mtime_suffix = str(int(latest_mtime))[-6:] if latest_mtime else "0"

    if git_hash:
        return f"{git_hash}-{mtime_suffix}"

    try:
        mtime = os.path.getmtime(Path(__file__).parent.parent / "app.py")
        return f"{int(mtime)}-{mtime_suffix}"
    except Exception:
        return f"1.0.0-{mtime_suffix}"


APP_VERSION = get_app_version()
