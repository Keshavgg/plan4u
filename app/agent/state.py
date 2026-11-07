"""Agent state definitions and conversation memory schema for Plan4U."""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import uuid

from app.schemas.itinerary import ItineraryRequest, CompleteItinerary
from app.schemas.attraction import GeoLocation, PlaceItem
from app.schemas.agent import (
    FlightSpecialistResult,
    StayCuratorResult,
    CultureFoodResult,
    BudgetCheckoutResult,
)


class PlannerState(BaseModel):
    """Execution state for Panel 1 (Master Pre-Trip Planner)."""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: str = Field(default="initializing", description="Workflow state tracker")
    request: ItineraryRequest
    flight_result: Optional[FlightSpecialistResult] = None
    stay_result: Optional[StayCuratorResult] = None
    culture_result: Optional[CultureFoodResult] = None
    budget_result: Optional[BudgetCheckoutResult] = None
    final_itinerary: Optional[CompleteItinerary] = None
    execution_logs: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None


class ChatMessage(BaseModel):
    role: str = Field(..., description="'user', 'assistant', or 'system'")
    content: str
    timestamp: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CompanionState(BaseModel):
    """Session memory for Panel 2 (Live In-Trip Copilot)."""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: Optional[str] = None
    active_city: str = "Delhi"
    current_location: Optional[GeoLocation] = None
    active_trip_id: Optional[str] = None
    chat_history: List[ChatMessage] = Field(default_factory=list)
    last_recommended_places: List[PlaceItem] = Field(default_factory=list)
    last_ticket_cards: List[Dict[str, Any]] = Field(default_factory=list)
    active_cravings: List[str] = Field(default_factory=list)
