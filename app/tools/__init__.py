"""Plan4U Tool Registry: clean interfaces for Gemini and subagents."""
from .flights import (
    search_flights_tool,
    quote_flight_fare_tool,
    get_flight_fare_rules_tool,
)
from .hotels import (
    search_hotels_tool,
    search_hotels_near_landmark_tool,
    get_hotel_details_tool,
)
from .attractions import (
    search_attractions_tool,
    get_attraction_details_tool,
)
from .dining import (
    search_cafes_tool,
    search_restaurants_tool,
    recommend_food_near_stop_tool,
)
from .reels import extract_spots_from_reel_tool
from .group_split import calculate_group_split_tool
from .payments import create_checkout_session_tool
from .events import search_live_events_tool
from app.services.smart_tools import (
    analyze_flight_tradeoffs,
    cluster_places_by_geography,
    get_emergency_reroute_options,
    create_event_anchored_plan,
    generate_group_settlement_links,
    estimate_transport_options,
    generate_packing_checklist,
    get_destination_weather_insights,
    convert_currency,
)

__all__ = [
    "search_flights_tool",
    "quote_flight_fare_tool",
    "get_flight_fare_rules_tool",
    "search_hotels_tool",
    "search_hotels_near_landmark_tool",
    "get_hotel_details_tool",
    "search_attractions_tool",
    "get_attraction_details_tool",
    "search_cafes_tool",
    "search_restaurants_tool",
    "recommend_food_near_stop_tool",
    "extract_spots_from_reel_tool",
    "calculate_group_split_tool",
    "create_checkout_session_tool",
    "search_live_events_tool",
    # Smart Superpower Tools
    "analyze_flight_tradeoffs",
    "cluster_places_by_geography",
    "get_emergency_reroute_options",
    "create_event_anchored_plan",
    "generate_group_settlement_links",
    "estimate_transport_options",
    "generate_packing_checklist",
    "get_destination_weather_insights",
    "convert_currency",
]
