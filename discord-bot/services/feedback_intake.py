"""Send feedback picked up in Discord to the website's Feedback board."""

from __future__ import annotations

import logging
import re

import aiohttp

import config

logger = logging.getLogger("discord_bot")

WEB_APP_URL = getattr(config, "WEB_APP_URL", "https://sorcererssummit.com").rstrip("/")
WEB_APP_API_KEY = getattr(config, "WEB_APP_API_KEY", "") or ""

_BUG_WORDS = re.compile(r"\b(bug|broken|error|crash|doesn'?t work|not working|wrong|fails?)\b", re.I)
_FEATURE_WORDS = re.compile(r"\b(feature|idea|suggest\w*|request|would be (nice|cool)|please add|add a)\b", re.I)


def guess_type(*texts: str) -> str:
    text = " ".join(t for t in texts if t)
    if _BUG_WORDS.search(text):
        return "bug_report"
    if _FEATURE_WORDS.search(text):
        return "feature_request"
    return "general"


def make_title(text: str, limit: int = 90) -> str:
    first = (text or "").strip().splitlines()[0] if (text or "").strip() else "Discord feedback"
    return first if len(first) <= limit else first[: limit - 1].rstrip() + "…"


async def submit(*, title: str, description: str, feedback_type: str,
                 source_ref: str, username: str, user_id: int | str) -> int | None:
    """POST to /api/feedback/feedback/intake. Returns the board item id, or None."""
    if not WEB_APP_API_KEY:
        logger.warning("feedback_intake: WEB_APP_API_KEY not set; feedback not saved")
        return None
    payload = {
        "title": title[:200],
        "description": description[:2000],
        "type": feedback_type,
        "source": "discord",
        "source_ref": str(source_ref),
        "username": username,
        "user_id": str(user_id),
    }
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.post(
                f"{WEB_APP_URL}/api/feedback/feedback/intake",
                json=payload,
                headers={"X-API-Key": WEB_APP_API_KEY},
            ) as resp:
                if resp.status in (200, 201):
                    return (await resp.json()).get("id")
                logger.warning(f"feedback_intake: site answered {resp.status}")
    except Exception as exc:
        logger.warning(f"feedback_intake: could not reach site: {exc}")
    return None
