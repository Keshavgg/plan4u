"""Agent and Subagent I/O contract schemas for Multi-Agent Orchestration."""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum

from .flight import FlightOption, FlightSearchResult
from .hotel import HotelOption, HotelSearchResult
from .attraction import PlaceItem, PlacesSearchResult
from .booking import RazorpayCheckoutSession, BookingStatus
from .itinerary import DayPlan, CompleteItinerary, TravelPace, TravelerType


class AgentRole(str, Enum):
    ORCHESTRATOR = "orchestrator"
    FLIGHT_SPECIALIST = "flight_specialist"
    STAY_CURATOR = "stay_curator"
    CULTURE_FOOD_GUIDE = "culture_food_guide"
    BUDGET_CHECKOUT_MASTER = "budget_checkout_master"
    LIVE_CITY_COPILOT = "live_city_copilot"


# -------------------------------------------------------------
# 1. Flight Specialist Subagent Contracts
# -------------------------------------------------------------
class FlightSpecialistTask(BaseModel):
    origin: str
    destination: str
    departure_date: str
    return_date: Optional[str] = None
    passengers: int = 1
    max_flight_budget: Optional[float] = None
    preferred_carrier: Optional[str] = None


class FlightSpecialistResult(BaseModel):
    success: bool = True
    recommended_flights: List[FlightOption] = Field(default_factory=list)
    cheapest_fare: float = 0.0
    fastest_flight_id: Optional[str] = None
    notes: List[str] = Field(default_factory=list, description="Baggage rules, terminal tips, layover notes")


# -------------------------------------------------------------
# 2. Stay Curator Subagent Contracts
# -------------------------------------------------------------
class StayCuratorTask(BaseModel):
    city: str
    check_in_date: str
    check_out_date: str
    rooms: int = 1
    guests: int = 2
    max_budget_per_night: Optional[float] = None
    anchor_landmark: Optional[str] = Field(None, description="e.g. 'Near Hawa Mahal' or 'Candolim Beach'")
    anchor_lat: Optional[float] = None
    anchor_lng: Optional[float] = None


class StayCuratorResult(BaseModel):
    success: bool = True
    recommended_hotels: List[HotelOption] = Field(default_factory=list)
    best_value_hotel_id: Optional[str] = None
    proximity_highlights: List[str] = Field(
        default_factory=list,
        description="e.g. 'Hotel Haveli is 80m walking distance from Hawa Mahal'"
    )


# -------------------------------------------------------------
# 3. Culture & Food Guide Subagent Contracts
# -------------------------------------------------------------
class CultureFoodTask(BaseModel):
    destination: str
    duration_days: int
    interests: List[str] = Field(default_factory=list)
    dietary_preferences: Optional[str] = None
    pace: TravelPace = TravelPace.MODERATE


class CultureFoodResult(BaseModel):
    success: bool = True
    top_monuments: List[PlaceItem] = Field(default_factory=list)
    recommended_dining: List[PlaceItem] = Field(default_factory=list)
    day_plans: List[DayPlan] = Field(default_factory=list)
    local_secrets_and_tips: List[str] = Field(default_factory=list)


# -------------------------------------------------------------
# 4. Budget & Checkout Master Subagent Contracts
# -------------------------------------------------------------
class BudgetCheckoutTask(BaseModel):
    total_budget_limit: Optional[float] = None
    selected_flight: Optional[FlightOption] = None
    selected_hotel: Optional[HotelOption] = None
    activities_cost: float = 0.0
    days_count: int = 1
    user_email: Optional[str] = None
    user_phone: Optional[str] = None


class BudgetCheckoutResult(BaseModel):
    success: bool = True
    flight_total: float = 0.0
    hotel_total: float = 0.0
    activities_total: float = 0.0
    grand_total: float = 0.0
    is_within_budget: bool = True
    budget_variance_inr: float = 0.0
    checkout_session: Optional[RazorpayCheckoutSession] = None
    financial_notes: List[str] = Field(default_factory=list)


# -------------------------------------------------------------
# 5. Live City Copilot (Panel 2 - In-Trip Companion) Contracts
# -------------------------------------------------------------
class LiveCopilotActionType(str, Enum):
    FOOD_RECOMMENDATION = "food_recommendation"
    LIVE_EVENTS = "live_events"
    MONUMENT_DISCOVERY = "monument_discovery"
    INSTANT_PASS = "instant_pass"
    GENERAL_CHAT = "general_chat"


class ChatMessage(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Message text content")


class LiveCopilotQuery(BaseModel):
    user_message: str
    current_lat: float
    current_lng: float
    current_time_str: str = Field(..., description="e.g. '04:30 PM'")
    active_trip_id: Optional[str] = None
    user_preferences: List[str] = Field(default_factory=list)
    conversation_history: List[ChatMessage] = Field(default_factory=list)


class LiveCopilotResponse(BaseModel):
    reply_text: str = Field(..., description="Conversational witty response in friendly Hinglish/English")
    action_type: LiveCopilotActionType = LiveCopilotActionType.GENERAL_CHAT
    nearby_recommendations: List[PlaceItem] = Field(default_factory=list)
    ticket_booking_card: Optional[Dict[str, Any]] = None
    ticket_booking_cards: List[Dict[str, Any]] = Field(default_factory=list)
    suggested_quick_replies: List[str] = Field(default_factory=list)
    # An interactive card the UI renders with buttons, e.g. a table booking to confirm or a Swiggy connect prompt.
    action_card: Optional[Dict[str, Any]] = None
