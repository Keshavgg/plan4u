"""Hotel Service Package: Modular, readable hotel operations."""

from .auth import authenticate_tbo_hotel, is_hotel_api_configured
from .search import search_hotels
from .proximity import search_hotels_near_location
from .details import get_hotel_details
from .prebook import prebook_hotel
from .distance import haversine_distance_km, estimate_walking_time_mins, format_distance_label
from .parser import parse_tbo_hotel_response

__all__ = [
    "authenticate_tbo_hotel",
    "is_hotel_api_configured",
    "search_hotels",
    "search_hotels_near_location",
    "get_hotel_details",
    "prebook_hotel",
    "haversine_distance_km",
    "estimate_walking_time_mins",
    "format_distance_label",
    "parse_tbo_hotel_response",
]
