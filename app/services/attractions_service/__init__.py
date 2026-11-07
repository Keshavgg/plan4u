"""Attractions and Monuments Service Package."""

from .search import search_attractions
from .details import get_attraction_details

__all__ = [
    "search_attractions",
    "get_attraction_details",
]
