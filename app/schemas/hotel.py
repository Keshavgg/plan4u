"""Hotel schemas aligned with TBO Holidays (TBOHolidays_HotelAPI) specs."""
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class HotelProvider(str, Enum):
    TBO = "tbo"
    MOCK = "mock"


class MealType(str, Enum):
    ROOM_ONLY = "room_only"
    BREAKFAST_INCLUDED = "breakfast_included"
    HALF_BOARD = "half_board"
    ALL_INCLUSIVE = "all_inclusive"


class CancellationPolicyBand(BaseModel):
    from_date: str = Field(..., description="Timestamp from which penalty applies")
    charge_type: str = Field(default="Fixed", description="Fixed or Percentage")
    charge_amount: float = Field(default=0.0, description="Penalty fee in INR")
    currency: str = "INR"


class HotelRoom(BaseModel):
    room_index: int = 1
    room_type_name: str = Field(..., description="e.g. 'Deluxe King Room Garden View'")
    room_type_code: Optional[str] = Field("STD", description="TBO RoomTypeCode for pre-booking")
    meal_type: MealType = MealType.BREAKFAST_INCLUDED
    meal_description: Optional[str] = "Complimentary Buffet Breakfast"
    
    is_refundable: bool = True
    cancellation_policies: List[CancellationPolicyBand] = Field(default_factory=list)
    
    price_per_night: float
    total_fare: float
    tax_amount: float = 0.0
    currency: str = "INR"
    amenities: List[str] = Field(default_factory=list)


class HotelSearchQuery(BaseModel):
    city: str = Field(..., description="Destination city name (e.g. Goa, Jaipur)")
    city_code: Optional[str] = Field(None, description="TBO CityCode if known")
    check_in_date: str = Field(..., description="YYYY-MM-DD")
    check_out_date: str = Field(..., description="YYYY-MM-DD")
    rooms: int = Field(default=1, ge=1)
    adults: int = Field(default=2, ge=1)
    children: int = Field(default=0, ge=0)
    
    # Manual Location & Price Filters
    min_rating: Optional[float] = Field(default=3.5, ge=0.0, le=5.0)
    min_star_rating: Optional[int] = Field(None, ge=1, le=5, description="Min star rating: 3, 4, or 5")
    min_price: Optional[float] = Field(None, description="Min price per night in INR")
    max_budget_per_night: Optional[float] = Field(None, description="Max price per night in INR")
    preferred_amenities: List[str] = Field(
        default_factory=list,
        description="e.g. ['swimming_pool', 'free_wifi', 'beachfront', 'spa', 'rooftop']"
    )
    near_landmark: Optional[str] = Field(None, description="e.g. 'Hawa Mahal', 'Candolim Beach'")
    lat: Optional[float] = Field(None, description="Current GPS Latitude")
    lng: Optional[float] = Field(None, description="Current GPS Longitude")
    radius_km: Optional[float] = Field(default=5.0, description="Radius around coordinates or landmark")
    sort_by: Optional[str] = Field(
        "price_asc", description="'price_asc', 'price_desc', 'rating_desc', 'distance_asc'"
    )
    provider: HotelProvider = HotelProvider.TBO


class HotelOption(BaseModel):
    id: str = Field(..., description="App-level unique hotel identifier")
    provider: HotelProvider = HotelProvider.TBO
    hotel_code: str = Field(..., description="TBO HotelCode for fetching details/pre-booking")
    
    name: str = Field(..., description="Hotel / Resort Name")
    star_rating: int = Field(default=3, ge=1, le=5)
    trip_advisor_rating: Optional[float] = Field(default=4.0)
    review_count: int = 0
    
    address: str
    city: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    
    # Pricing
    min_price_per_night: float
    total_estimated_price: float
    currency: str = "INR"
    
    # Available room options
    rooms: List[HotelRoom] = Field(default_factory=list)
    
    # Media & Amenities
    featured_image: Optional[str] = None
    photo_urls: List[str] = Field(default_factory=list)
    amenities: List[str] = Field(default_factory=list)
    hotel_description: Optional[str] = None


class HotelSearchResult(BaseModel):
    city: str
    check_in_date: str
    check_out_date: str
    provider: HotelProvider
    options: List[HotelOption] = Field(default_factory=list)
    total_found: int = 0
