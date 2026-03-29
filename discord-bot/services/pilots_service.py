"""Business logic for pilots (feature flags) with in-memory cache."""

import logging

from repositories.pilots_repo import get_all_pilots, get_pilot, set_pilot

logger = logging.getLogger("discord_bot")

# In-memory cache: {name: bool}
_cache: dict[str, bool] = {}
_cache_loaded = False


def _load_cache():
    """Load all pilots from DB into memory cache."""
    global _cache, _cache_loaded
    pilots = get_all_pilots()
    _cache = {p["name"]: p["enabled"] for p in pilots}
    _cache_loaded = True


def is_pilot_active(name: str) -> bool:
    """Check if a pilot is active. Returns False if pilot doesn't exist."""
    global _cache_loaded
    if not _cache_loaded:
        _load_cache()
    return _cache.get(name, False)


def enable_pilot(name: str):
    """Enable a pilot and update cache."""
    set_pilot(name, True)
    _cache[name] = True
    logger.info("Pilot '%s' enabled", name)


def disable_pilot(name: str):
    """Disable a pilot and update cache."""
    set_pilot(name, False)
    _cache[name] = False
    logger.info("Pilot '%s' disabled", name)


def list_pilots() -> list[dict]:
    """Return all pilots from DB (refreshes cache)."""
    _load_cache()
    return get_all_pilots()
