"""Places, Dining, Monuments, and Attraction schemas matching Tripplannr-Places Postman specs."""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum


class PlaceCategory(str, Enum):
    MONUMENT = "monument"
    HERITAGE = "heritage"
    CAFE = "cafe"
    RESTAURANT = "restaurant"
    BAR_NIGHTLIFE = "bar_nightlife"
    BEACH = "beach"
    MARKET = "market"
    ACTIVITY = "activity"


class PriceBand(str, Enum):
    BUDGET = "₹"           # Budget / Street Food / Free entry
    MODERATE = "₹₹"        # Casual Dining / Standard Entry
    EXPENSIVE = "₹₹₹"      # Fine Dining / Premium Activity
    LUXURY = "₹₹₹₹"        # Ultra luxury


class GeoLocation(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0)
    lng: float = Field(..., ge=-180.0, le=180.0)


class PlaceItem(BaseModel):
    id: str = Field(..., description="Unique Place ID (e.g. osm_123, geo_456, or google_place_id)")
    name: str = Field(..., description="Name of restaurant, cafe, or monument")
    category: PlaceCategory
    description: Optional[str] = None
    
    address: str
    location: GeoLocation
    distance_meters: Optional[int] = Field(None, description="Distance from current stop / search center")
    
    # Dining Specifics
    cuisines: List[str] = Field(default_factory=list, description="e.g. ['North Indian', 'Rajasthani Thali', 'Continental']")
    price_band: Optional[PriceBand] = None
    estimated_cost_per_person: Optional[float] = Field(default=None, description="INR cost per person, None if unknown")

    # Monument Specifics
    entry_fee: Optional[float] = Field(default=None, description="Ticket/entry cost per person in INR, 0 if free, None if unknown")
    recommended_duration_hours: Optional[float] = Field(default=None, description="Time spent at this spot, None if unknown")

    # Metadata
    rating: Optional[float] = Field(default=None, ge=0.0, le=5.0, description="None if no rating source is available")
    review_count: int = 0
    opening_hours: Optional[str] = None
    best_time_slot: Optional[str] = None
    is_bookable: bool = Field(default=False, description="Whether this venue accepts advance table reservation")
    
    photo_urls: List[str] = Field(default_factory=list)
    google_maps_url: Optional[str] = None
    directions_url: Optional[str] = None
    source_provider: str = Field(default="osm", description="osm | geoapify | google | mock")


class NearbyPlacesQuery(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0)
    lng: float = Field(..., ge=-180.0, le=180.0)
    radius: int = Field(default=2000, ge=100, le=50000, description="Search radius in meters")
    category: Optional[PlaceCategory] = None
    limit: int = Field(default=10, ge=1, le=20)


class TextSearchPlacesQuery(BaseModel):
    query: str = Field(..., min_length=2, description="Search query e.g. 'vegetarian thali', 'amber fort'")
    category: Optional[PlaceCategory] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    city: Optional[str] = None


class RecommendNearStopQuery(BaseModel):
    stop_name: str = Field(..., description="Current itinerary stop name (e.g. 'Hawa Mahal')")
    lat: float
    lng: float
    target_category: PlaceCategory = PlaceCategory.RESTAURANT
    preference: Optional[str] = Field("authentic local food", description="e.g. 'rooftop cafe', 'pure veg thali'")
    radius: int = Field(default=1500, description="Radius in meters")


class RestaurantSearchQuery(BaseModel):
    city: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    radius_meters: int = Field(default=4000, ge=100, le=50000)
    cuisines: Optional[List[str]] = Field(None, description="e.g. ['North Indian', 'Rajasthani Thali', 'Continental']")
    price_band: Optional[PriceBand] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    category: Optional[PlaceCategory] = Field(None, description="restaurant, cafe, or bar_nightlife")
    min_rating: Optional[float] = Field(None, ge=0.0, le=5.0)
    is_pure_veg: Optional[bool] = None
    is_rooftop: Optional[bool] = None
    sort_by: Optional[str] = Field("rating_desc", description="'rating_desc', 'distance_asc', 'price_asc'")


class AttractionSearchQuery(BaseModel):
    city: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    radius_km: Optional[float] = Field(default=10.0, ge=0.5, le=100.0)
    category: Optional[PlaceCategory] = None
    max_entry_fee: Optional[float] = None
    sort_by: Optional[str] = Field("rating_desc", description="'rating_desc', 'distance_asc', 'price_asc'")


class PlacesSearchResult(BaseModel):
    places: List[PlaceItem] = Field(default_factory=list)
    total_found: int = 0
    provider_used: str = "osm"


class NearbyExploreResult(BaseModel):
    center: GeoLocation
    city: str
    radius_km: float
    total_nearby_items: int
    hotels: List[Any] = Field(default_factory=list)
    restaurants: List[PlaceItem] = Field(default_factory=list)
    attractions: List[PlaceItem] = Field(default_factory=list)
    live_events: List[Dict[str, Any]] = Field(default_factory=list)
