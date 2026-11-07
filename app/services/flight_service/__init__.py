"""Flight Service Package: Modular, readable flight operations."""

from .auth import authenticate_tbo_air, is_flight_api_configured
from .search import search_flights
from .fare_quote import quote_flight_fare
from .fare_rule import get_fare_rules
from .ssr import get_flight_ssr
from .hold_booking import create_flight_hold
from .parser import parse_tbo_search_response

__all__ = [
    "authenticate_tbo_air",
    "is_flight_api_configured",
    "search_flights",
    "quote_flight_fare",
    "get_fare_rules",
    "get_flight_ssr",
    "create_flight_hold",
    "parse_tbo_search_response",
]
