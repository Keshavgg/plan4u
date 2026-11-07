"""Plan4U Tool Registry: Formal, precision-bound tool specifications and subagent assignments."""
from typing import Dict, Any, List, Callable, Optional
from pydantic import BaseModel, Field
from app.schemas.agent import AgentRole

# Import all underlying services and tools
from app.services.flight_service import (
    search_flights,
    quote_flight_fare,
    get_fare_rules,
    get_flight_ssr,
    create_flight_hold,
)
from app.services.hotel_service import (
    search_hotels,
    search_hotels_near_location,
    get_hotel_details,
    prebook_hotel,
)
from app.services.dining_service import (
    search_restaurants,
    search_cafes,
    recommend_food_near_stop,
)
from app.services.attractions_service import (
    search_attractions,
    get_attraction_details,
)
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
from app.tools.events import search_live_events_tool
from app.tools.payments import create_checkout_session_tool


class ToolDefinition(BaseModel):
    name: str = Field(..., description="Unique tool identifier")
    description: str = Field(..., description="Clear explanation of tool's exact capability")
    assigned_agents: List[AgentRole] = Field(..., description="Subagents permitted to invoke this tool")
    parameters_schema: Dict[str, Any] = Field(default_factory=dict, description="JSON schema for LLM function calling")


# Registry storing all tool specifications
TOOL_DEFINITIONS: Dict[str, ToolDefinition] = {
    # -------------------------------------------------------------
    # 1. Flight Specialist Tools
    # -------------------------------------------------------------
    "search_flights": ToolDefinition(
        name="search_flights",
        description="Search live airline schedules and fares between airport IATA codes (e.g. DEL to BOM) with baggage allowances and LCC tags.",
        assigned_agents=[AgentRole.FLIGHT_SPECIALIST, AgentRole.ORCHESTRATOR],
        parameters_schema={
            "type": "object",
            "properties": {
                "origin": {"type": "string", "description": "3-letter airport code (e.g. DEL)"},
                "destination": {"type": "string", "description": "3-letter airport code (e.g. BOM, GOI)"},
                "departure_date": {"type": "string", "description": "YYYY-MM-DD"},
                "return_date": {"type": "string", "description": "Optional YYYY-MM-DD"},
                "adults": {"type": "integer", "default": 1},
                "cabin_class": {"type": "string", "default": "economy"},
            },
            "required": ["origin", "destination", "departure_date"],
        },
    ),
    "quote_flight_fare": ToolDefinition(
        name="quote_flight_fare",
        description="Re-validates live price and seat availability before checkout to ensure no airline price surge.",
        assigned_agents=[AgentRole.FLIGHT_SPECIALIST, AgentRole.BUDGET_CHECKOUT_MASTER],
        parameters_schema={
            "type": "object",
            "properties": {
                "trace_id": {"type": "string"},
                "result_index": {"type": "string"},
            },
            "required": ["trace_id", "result_index"],
        },
    ),
    "get_flight_fare_rules": ToolDefinition(
        name="get_flight_fare_rules",
        description="Retrieves exact cancellation penalty bands and date-change charges for a flight.",
        assigned_agents=[AgentRole.FLIGHT_SPECIALIST],
        parameters_schema={
            "type": "object",
            "properties": {
                "trace_id": {"type": "string"},
                "result_index": {"type": "string"},
            },
            "required": ["trace_id", "result_index"],
        },
    ),
    "get_flight_ssr": ToolDefinition(
        name="get_flight_ssr",
        description="Checks available seat map, hot meals (Veg/Non-Veg), and extra check-in baggage add-on prices.",
        assigned_agents=[AgentRole.FLIGHT_SPECIALIST],
        parameters_schema={
            "type": "object",
            "properties": {
                "trace_id": {"type": "string"},
                "result_index": {"type": "string"},
            },
            "required": ["trace_id", "result_index"],
        },
    ),
    "analyze_flight_tradeoffs": ToolDefinition(
        name="analyze_flight_tradeoffs",
        description="Evaluates flight options to detect 2 AM red-eye cab surcharges, best overall value, and time-shift savings.",
        assigned_agents=[AgentRole.FLIGHT_SPECIALIST, AgentRole.ORCHESTRATOR],
        parameters_schema={
            "type": "object",
            "properties": {
                "flights": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["flights"],
        },
    ),

    # -------------------------------------------------------------
    # 2. Stay Curator Tools
    # -------------------------------------------------------------
    "search_hotels": ToolDefinition(
        name="search_hotels",
        description="Searches hotels in a destination city with star ratings, TripAdvisor reviews, and room rates.",
        assigned_agents=[AgentRole.STAY_CURATOR, AgentRole.ORCHESTRATOR],
        parameters_schema={
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "check_in_date": {"type": "string"},
                "check_out_date": {"type": "string"},
                "rooms": {"type": "integer", "default": 1},
                "adults": {"type": "integer", "default": 2},
                "min_rating": {"type": "number", "default": 3.5},
            },
            "required": ["city", "check_in_date", "check_out_date"],
        },
    ),
    "search_hotels_near_landmark": ToolDefinition(
        name="search_hotels_near_landmark",
        description="Ranks hotels strictly by walking / driving proximity to a specific monument or beach.",
        assigned_agents=[AgentRole.STAY_CURATOR],
        parameters_schema={
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "landmark_name": {"type": "string"},
                "landmark_lat": {"type": "number"},
                "landmark_lng": {"type": "number"},
                "check_in_date": {"type": "string"},
                "check_out_date": {"type": "string"},
                "max_radius_km": {"type": "number", "default": 3.0},
            },
            "required": ["city", "landmark_name", "landmark_lat", "landmark_lng", "check_in_date", "check_out_date"],
        },
    ),
    "get_hotel_details": ToolDefinition(
        name="get_hotel_details",
        description="Retrieves full photo gallery, amenities (pool, free breakfast, wifi), and house policies.",
        assigned_agents=[AgentRole.STAY_CURATOR],
        parameters_schema={
            "type": "object",
            "properties": {
                "hotel_code": {"type": "string"},
            },
            "required": ["hotel_code"],
        },
    ),
    "prebook_hotel": ToolDefinition(
        name="prebook_hotel",
        description="Locks room inventory and freezes rate for 15 minutes before checkout.",
        assigned_agents=[AgentRole.STAY_CURATOR, AgentRole.BUDGET_CHECKOUT_MASTER],
        parameters_schema={
            "type": "object",
            "properties": {
                "hotel_code": {"type": "string"},
                "booking_code": {"type": "string"},
            },
            "required": ["hotel_code", "booking_code"],
        },
    ),

    # -------------------------------------------------------------
    # 3. Culture & Food Guide Tools
    # -------------------------------------------------------------
    "search_attractions": ToolDefinition(
        name="search_attractions",
        description="Finds heritage monuments, UNESCO forts, and viewpoints with entry fees and opening hours.",
        assigned_agents=[AgentRole.CULTURE_FOOD_GUIDE, AgentRole.LIVE_CITY_COPILOT],
        parameters_schema={
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "category": {"type": "string", "description": "monument | heritage | viewpoint | activity"},
                "max_entry_fee": {"type": "number"},
            },
            "required": ["city"],
        },
    ),
    "get_attraction_details": ToolDefinition(
        name="get_attraction_details",
        description="Provides deep historical context, architecture stories, and photography golden-hour tips.",
        assigned_agents=[AgentRole.CULTURE_FOOD_GUIDE, AgentRole.LIVE_CITY_COPILOT],
        parameters_schema={
            "type": "object",
            "properties": {
                "place_id": {"type": "string"},
            },
            "required": ["place_id"],
        },
    ),
    "search_restaurants": ToolDefinition(
        name="search_restaurants",
        description="Finds authentic regional dining, royal thalis, and local eateries near given GPS coordinates.",
        assigned_agents=[AgentRole.CULTURE_FOOD_GUIDE, AgentRole.LIVE_CITY_COPILOT],
        parameters_schema={
            "type": "object",
            "properties": {
                "lat": {"type": "number"},
                "lng": {"type": "number"},
                "cuisines": {"type": "array", "items": {"type": "string"}},
                "max_price": {"type": "number"},
                "radius_meters": {"type": "integer", "default": 3000},
            },
            "required": ["lat", "lng"],
        },
    ),
    "search_cafes": ToolDefinition(
        name="search_cafes",
        description="Finds artisanal coffee roasteries, rooftop lounges, and bakeries with scenic views.",
        assigned_agents=[AgentRole.CULTURE_FOOD_GUIDE, AgentRole.LIVE_CITY_COPILOT],
        parameters_schema={
            "type": "object",
            "properties": {
                "lat": {"type": "number"},
                "lng": {"type": "number"},
                "radius_meters": {"type": "integer", "default": 3000},
            },
            "required": ["lat", "lng"],
        },
    ),
    "recommend_food_near_stop": ToolDefinition(
        name="recommend_food_near_stop",
        description="Finds restaurants within walking distance of an active itinerary sightseeing stop.",
        assigned_agents=[AgentRole.CULTURE_FOOD_GUIDE, AgentRole.LIVE_CITY_COPILOT],
        parameters_schema={
            "type": "object",
            "properties": {
                "stop_name": {"type": "string"},
                "stop_lat": {"type": "number"},
                "stop_lng": {"type": "number"},
                "cuisine_preference": {"type": "string"},
            },
            "required": ["stop_name", "stop_lat", "stop_lng"],
        },
    ),
    "cluster_places_by_geography": ToolDefinition(
        name="cluster_places_by_geography",
        description="Smart spatial clustering grouping sights into geographical days to eliminate zigzagging across town.",
        assigned_agents=[AgentRole.CULTURE_FOOD_GUIDE, AgentRole.ORCHESTRATOR],
        parameters_schema={
            "type": "object",
            "properties": {
                "places": {"type": "array", "items": {"type": "object"}},
                "days_count": {"type": "integer", "default": 2},
            },
            "required": ["places"],
        },
    ),
    "get_destination_weather_insights": ToolDefinition(
        name="get_destination_weather_insights",
        description="Provides a live 7-day forecast, sunrise/sunset times, and golden hour photography windows.",
        assigned_agents=[AgentRole.CULTURE_FOOD_GUIDE, AgentRole.LIVE_CITY_COPILOT],
        parameters_schema={
            "type": "object",
            "properties": {
                "city": {"type": "string"},
            },
            "required": ["city"],
        },
    ),
    "estimate_transport_options": ToolDefinition(
        name="estimate_transport_options",
        description="Computes road distance, travel duration, Cab (Uber/Ola), Auto-rickshaw, and Metro fares between coordinates.",
        assigned_agents=[AgentRole.CULTURE_FOOD_GUIDE, AgentRole.LIVE_CITY_COPILOT],
        parameters_schema={
            "type": "object",
            "properties": {
                "origin_lat": {"type": "number"},
                "origin_lng": {"type": "number"},
                "dest_lat": {"type": "number"},
                "dest_lng": {"type": "number"},
                "city": {"type": "string", "default": "Delhi"},
            },
            "required": ["origin_lat", "origin_lng", "dest_lat", "dest_lng"],
        },
    ),

    # -------------------------------------------------------------
    # 4. Budget & Checkout Master Tools
    # -------------------------------------------------------------
    "create_checkout_session": ToolDefinition(
        name="create_checkout_session",
        description="Generates a 15-minute secured Razorpay checkout session and order ID for trip booking.",
        assigned_agents=[AgentRole.BUDGET_CHECKOUT_MASTER, AgentRole.LIVE_CITY_COPILOT],
        parameters_schema={
            "type": "object",
            "properties": {
                "amount_inr": {"type": "number"},
                "description": {"type": "string"},
                "customer_email": {"type": "string"},
                "customer_phone": {"type": "string"},
            },
            "required": ["amount_inr"],
        },
    ),
    "generate_group_settlement_links": ToolDefinition(
        name="generate_group_settlement_links",
        description="Calculates min-cash-flow settlements among group members and creates clickable UPI deep links and WhatsApp templates.",
        assigned_agents=[AgentRole.BUDGET_CHECKOUT_MASTER],
        parameters_schema={
            "type": "object",
            "properties": {
                "expenses": {"type": "array", "items": {"type": "object"}},
                "upi_vpa": {"type": "string", "default": "trip.split@upi"},
            },
            "required": ["expenses"],
        },
    ),
    "convert_currency": ToolDefinition(
        name="convert_currency",
        description="Converts an amount between two currencies at the latest published exchange rate.",
        assigned_agents=[AgentRole.BUDGET_CHECKOUT_MASTER],
        parameters_schema={
            "type": "object",
            "properties": {
                "amount": {"type": "number"},
                "from_currency": {"type": "string"},
                "to_currency": {"type": "string"},
            },
            "required": ["amount", "from_currency", "to_currency"],
        },
    ),

    # -------------------------------------------------------------
    # 5. Live City Copilot (Panel 2) Tools
    # -------------------------------------------------------------
    "get_emergency_reroute_options": ToolDefinition(
        name="get_emergency_reroute_options",
        description="Real-time weather (rain/heat) & closure rerouting with instant indoor & covered comfort pivots.",
        assigned_agents=[AgentRole.LIVE_CITY_COPILOT],
        parameters_schema={
            "type": "object",
            "properties": {
                "current_lat": {"type": "number"},
                "current_lng": {"type": "number"},
                "reason": {"type": "string", "default": "heavy_rain"},
                "time_of_day": {"type": "string", "default": "03:30 PM"},
            },
            "required": ["current_lat", "current_lng"],
        },
    ),
    "search_live_events": ToolDefinition(
        name="search_live_events",
        description="Finds verified live concerts, standup comedy shows, and sundowners with direct BookMyShow / Paytm Insider booking links.",
        assigned_agents=[AgentRole.LIVE_CITY_COPILOT, AgentRole.ORCHESTRATOR],
        parameters_schema={
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "category": {"type": "string"},
                "timeframe": {"type": "string", "default": "today or this weekend"},
                "lat": {"type": "number"},
                "lng": {"type": "number"},
            },
            "required": ["city"],
        },
    ),
    "create_event_anchored_plan": ToolDefinition(
        name="create_event_anchored_plan",
        description="Generates an entire weekend getaway anchored around an event, concert, or comedy show with nearby hotel and flight.",
        assigned_agents=[AgentRole.LIVE_CITY_COPILOT, AgentRole.ORCHESTRATOR],
        parameters_schema={
            "type": "object",
            "properties": {
                "event_name_or_id": {"type": "string"},
                "city": {"type": "string"},
                "origin_city": {"type": "string", "description": "Origin airport code"},
                "destination_airport": {"type": "string", "description": "Destination airport code"},
                "departure_date": {"type": "string"},
                "return_date": {"type": "string"},
            },
            "required": ["event_name_or_id", "city", "origin_city"],
        },
    ),
    "generate_packing_checklist": ToolDefinition(
        name="generate_packing_checklist",
        description="Generates a destination-, climate-, and activity-aware smart packing checklist.",
        assigned_agents=[AgentRole.ORCHESTRATOR, AgentRole.CULTURE_FOOD_GUIDE],
        parameters_schema={
            "type": "object",
            "properties": {
                "destination": {"type": "string"},
                "duration_days": {"type": "integer", "default": 3},
                "travel_month": {"type": "string", "default": "November"},
            },
            "required": ["destination"],
        },
    ),
}


# Callable dispatch map connecting tool names to actual Python functions
TOOL_DISPATCH_MAP: Dict[str, Callable] = {
    # Flights
    "search_flights": search_flights,
    "quote_flight_fare": quote_flight_fare,
    "get_flight_fare_rules": get_fare_rules,
    "get_flight_ssr": get_flight_ssr,
    "analyze_flight_tradeoffs": analyze_flight_tradeoffs,
    # Hotels
    "search_hotels": search_hotels,
    "search_hotels_near_landmark": search_hotels_near_location,
    "get_hotel_details": get_hotel_details,
    "prebook_hotel": prebook_hotel,
    # Culture & Food
    "search_attractions": search_attractions,
    "get_attraction_details": get_attraction_details,
    "search_restaurants": search_restaurants,
    "search_cafes": search_cafes,
    "recommend_food_near_stop": recommend_food_near_stop,
    "cluster_places_by_geography": cluster_places_by_geography,
    "get_destination_weather_insights": get_destination_weather_insights,
    "estimate_transport_options": estimate_transport_options,
    # Budget & Payments
    "create_checkout_session": create_checkout_session_tool,
    "generate_group_settlement_links": generate_group_settlement_links,
    "convert_currency": convert_currency,
    # Live Copilot
    "get_emergency_reroute_options": get_emergency_reroute_options,
    "search_live_events": search_live_events_tool,
    "create_event_anchored_plan": create_event_anchored_plan,
    "generate_packing_checklist": generate_packing_checklist,
}


def get_tools_for_agent(agent_role: AgentRole) -> List[ToolDefinition]:
    """Returns the precise list of tools authorized and assigned to a given subagent."""
    return [
        tool for tool in TOOL_DEFINITIONS.values()
        if agent_role in tool.assigned_agents
    ]


def execute_tool(tool_name: str, **kwargs) -> Any:
    """Executes a registered tool dynamically with argument unpacking and validation."""
    if tool_name not in TOOL_DISPATCH_MAP:
        raise ValueError(f"Tool '{tool_name}' is not registered.")
    func = TOOL_DISPATCH_MAP[tool_name]
    return func(**kwargs)
