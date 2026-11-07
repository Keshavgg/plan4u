"""Comprehensive Itinerary schemas combining travel, stay, monuments, dining, and budget."""
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum

from .flight import FlightOption
from .hotel import HotelOption
from .attraction import PlaceItem, PlaceCategory


class TravelPace(str, Enum):
    RELAXED = "relaxed"
    MODERATE = "moderate"
    FAST = "fast"


class TravelerType(str, Enum):
    SOLO = "solo"
    COUPLE = "couple"
    FAMILY = "family"
    FRIENDS = "friends"


class TimeSlot(str, Enum):
    MORNING = "morning"        # Sights / Monuments / Breakfast
    AFTERNOON = "afternoon"    # Lunch / Indoor museum / Palaces
    EVENING = "evening"        # Sunset spots / Shopping / Cafes
    NIGHT = "night"            # Dinner / Nightlife / Cultural shows


class ScheduledActivity(BaseModel):
    time_slot: TimeSlot
    start_time: str = Field(..., description="e.g. '09:30 AM'")
    end_time: str = Field(..., description="e.g. '12:00 PM'")
    title: str = Field(..., description="Activity or Dining Title")
    category: PlaceCategory = PlaceCategory.MONUMENT
    description: str
    
    # Linked place / monument / restaurant details
    place: Optional[PlaceItem] = None
    estimated_cost_inr: float = Field(default=0.0, description="Cost for tickets or dining in INR")
    travel_time_from_prev: Optional[str] = Field(None, description="e.g. '15 mins by cab'")
    insider_tips: List[str] = Field(default_factory=list, description="Local tips, best camera angles, dish recommendations")


class DayPlan(BaseModel):
    day_number: int = Field(..., ge=1)
    date: str = Field(..., description="YYYY-MM-DD")
    theme: str = Field(..., description="e.g. 'Old Jaipur Heritage Walk & Traditional Rajasthani Dining'")
    activities: List[ScheduledActivity] = Field(default_factory=list)
    daily_budget_estimate: float = 0.0


class ItineraryRequest(BaseModel):
    origin: str = Field(..., description="Origin city / airport (e.g. 'DEL' or 'Delhi')")
    destination: str = Field(..., description="Destination city (e.g. 'Jaipur', 'Goa')")
    start_date: str = Field(..., description="YYYY-MM-DD")
    end_date: str = Field(..., description="YYYY-MM-DD")
    
    total_budget: Optional[float] = Field(None, description="Budget in INR")
    traveler_count: int = Field(default=2, ge=1)
    traveler_type: TravelerType = TravelerType.COUPLE
    pace: TravelPace = TravelPace.MODERATE
    
    interests: List[str] = Field(
        default_factory=lambda: ["heritage", "local_cuisine"],
        description="e.g. ['monuments', 'street food', 'cafes', 'nature', 'photography']"
    )
    dietary_preferences: Optional[str] = Field(None, description="e.g. 'pure vegetarian', 'halal', 'vegan'")


class CompleteItinerary(BaseModel):
    id: str = Field(..., description="Unique itinerary ID")
    title: str = Field(..., description="e.g. 'Royal 3-Day Jaipur Heritage & Culinary Tour'")
    destination: str
    origin: str
    start_date: str
    end_date: str
    duration_days: int
    
    # Transport (TBO / Galileo)
    recommended_flights: List[FlightOption] = Field(default_factory=list)
    selected_flight: Optional[FlightOption] = None
    
    # Accommodation (TBO Hotel API)
    recommended_hotels: List[HotelOption] = Field(default_factory=list)
    selected_hotel: Optional[HotelOption] = None
    
    # Day-wise plans with Monuments + Cafes / Restaurants
    days: List[DayPlan] = Field(default_factory=list)
    
    # Cost Breakdown in INR
    flight_total_cost: float = 0.0
    hotel_total_cost: float = 0.0
    dining_and_tickets_cost: float = 0.0
    grand_total_inr: float = 0.0
    
    # Travel insights
    best_time_to_visit_note: Optional[str] = None
    weather_note: Optional[str] = None
    pro_travel_tips: List[str] = Field(default_factory=list)
    
    ready_for_checkout: bool = False
