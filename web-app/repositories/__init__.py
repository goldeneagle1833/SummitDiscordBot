"""Repository layer for data access."""

from repositories.elo import EloRepository
from repositories.matches import MatchRepository
from repositories.fart import FartRepository
from repositories.events import EventRepository
from repositories.curios import CurioRepository

__all__ = [
    "EloRepository",
    "MatchRepository",
    "FartRepository",
    "EventRepository",
    "CurioRepository",
]
