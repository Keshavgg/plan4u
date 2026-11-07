"""Flight schemas aligned with TBO (Tek Travels) and Galileo (Travelport) specs."""
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class FlightProvider(str, Enum):
    TBO = "tbo"
    TRAVELPORT = "travelport"
    AMADEUS = "amadeus"
    INDIGO_DIRECT = "indigo_direct"
    MOCK = "mock"


class FlightSegment(BaseModel):
    airline_code: str = Field(..., description="e.g. '6E' (IndiGo), 'AI' (Air India)")
    airline_name: str
    airline_logo: Optional[str] = None
    flight_number: str = Field(..., description="e.g. '6E-205'")
    aircraft: Optional[str] = Field(None, description="e.g. 'A320neo'")
    
    origin: str = Field(..., description="Airport code e.g. 'DEL'")
    origin_terminal: Optional[str] = None
    destination: str = Field(..., description="Airport code e.g. 'BOM'")
    destination_terminal: Optional[str] = None
    
    departure_time: str = Field(..., description="Local airport departure time")
    arrival_time: str = Field(..., description="Local airport arrival time")
    duration: str = Field(..., description="e.g. '2h 15m'")
    layover_after: Optional[str] = Field(None, description="e.g. '1h 30m at BOM'")
    seats_left: Optional[int] = None


class FlightSearchQuery(BaseModel):
    origin: str = Field(..., description="Origin airport code (e.g. DEL, BOM)")
    destination: str = Field(..., description="Destination airport code (e.g. GOI, BLR)")
    departure_date: str = Field(..., description="YYYY-MM-DD")
    return_date: Optional[str] = Field(None, description="YYYY-MM-DD for round trips")
    adults: int = Field(default=1, ge=1, le=9)
    children: int = Field(default=0, ge=0, le=8)
    infants: int = Field(default=0, ge=0, le=4)
    cabin_class: str = Field(default="economy", description="economy, premium_economy, business")
    preferred_carrier: Optional[str] = None
    provider: FlightProvider = FlightProvider.TBO
    
    # Manual UI Filters
    min_price: Optional[float] = Field(None, description="Minimum price filter in INR")
    max_price: Optional[float] = Field(None, description="Maximum price filter in INR")
    airlines: Optional[List[str]] = Field(None, description="List of airline codes e.g. ['6E', 'AI', 'QP']")
    max_stops: Optional[int] = Field(None, description="0 = Non-stop only, 1 = 1 stop max")
    is_refundable: Optional[bool] = Field(None, description="True = only refundable fares")
    departure_time_window: Optional[str] = Field(
        None, description="'early_morning' (00-06), 'morning' (06-12), 'afternoon' (12-18), 'evening' (18-24)"
    )
    sort_by: Optional[str] = Field(
        "price_asc", description="Sort by: 'price_asc', 'price_desc', 'duration_asc', 'departure_asc'"
    )


class FlightOption(BaseModel):
    id: str = Field(..., description="App-level unique offer ID (e.g. tbo_del_bom_1)")
    provider: FlightProvider = FlightProvider.TBO
    trace_id: Optional[str] = Field(None, description="TBO TraceId valid for ~15 mins")
    result_index: Optional[str] = Field(None, description="TBO ResultIndex for quote/book")
    
    airline_name: str
    airline_code: str
    airline_logo: Optional[str] = None
    
    is_lcc: bool = Field(default=True, description="True for IndiGo, SpiceJet, Akasa")
    is_refundable: bool = Field(default=False)
    
    origin: str
    destination: str
    departure_time: str
    arrival_time: str
    total_duration: str
    stops: int = 0
    
    segments: List[FlightSegment] = Field(default_factory=list)
    
    # Baggage Info
    cabin_baggage: str = Field(default="7 Kg")
    checkin_baggage: str = Field(default="15 Kg")
    
    # Fares (in INR)
    base_fare: float = 0.0
    taxes_and_surcharges: float = 0.0
    published_fare: float = Field(..., description="Final price shown to user (INR)")
    currency: str = "INR"
    
    fare_rule_summary: Optional[str] = None
    seats_remaining: Optional[int] = None


class FlightSearchResult(BaseModel):
    origin: str
    destination: str
    departure_date: str
    trace_id: Optional[str] = None
    provider: FlightProvider
    options: List[FlightOption] = Field(default_factory=list)
    total_found: int = 0
