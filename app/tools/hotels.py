"""AI-facing hotel and stay curation tools."""
from typing import Optional, Dict, Any, List
from app.services.hotel_service import (
    search_hotels,
    search_hotels_near_location,
    get_hotel_details,
    prebook_hotel,
)
from app.schemas.hotel import HotelSearchQuery, HotelSearchResult, HotelOption


def search_hotels_tool(
    city: str,
    check_in_date: str,
    check_out_date: str,
    guest_nationality: str = "IN",
    rooms: int = 1,
    adults: int = 2,
    max_rating: Optional[float] = None,
) -> Dict[str, Any]:
    """Search hotels in a destination city.
    
    Args:
        city: City name, e.g. 'Delhi', 'Goa', 'Jaipur', 'Mumbai'
        check_in_date: Check-in date in YYYY-MM-DD
        check_out_date: Check-out date in YYYY-MM-DD
        guest_nationality: 2-letter country code (default 'IN')
        rooms: Number of rooms needed
        adults: Number of adult guests
        max_rating: Optional rating threshold
    """
    res: HotelSearchResult = search_hotels(
        city=city,
        check_in_date=check_in_date,
        check_out_date=check_out_date,
        rooms=rooms,
        adults=adults,
    )
    hotels = res.options
    if max_rating:
        hotels = [h for h in hotels if h.star_rating <= max_rating]
    return {
        "success": True,
        "city": city,
        "hotel_count": len(hotels),
        "hotels": [h.model_dump() for h in hotels],
        "lowest_price_per_night": min([h.min_price_per_night for h in hotels]) if hotels else 0,
    }


def search_hotels_near_landmark_tool(
    city: str,
    landmark_name: str,
    landmark_lat: float,
    landmark_lng: float,
    check_in_date: str,
    check_out_date: str,
    max_radius_km: float = 3.0,
) -> Dict[str, Any]:
    """Search and rank hotels specifically by walking / driving proximity to a monument or beach.
    
    Args:
        city: City name e.g. 'Jaipur', 'Goa'
        landmark_name: Name of sight, e.g. 'Hawa Mahal', 'Candolim Beach', 'India Gate'
        landmark_lat: Latitude of landmark
        landmark_lng: Longitude of landmark
        check_in_date: Check-in date in YYYY-MM-DD
        check_out_date: Check-out date in YYYY-MM-DD
        max_radius_km: Max distance threshold in km (default 3.0)
    """
    hotel_entries = search_hotels_near_location(
        city=city,
        target_lat=landmark_lat,
        target_lng=landmark_lng,
        check_in_date=check_in_date,
        check_out_date=check_out_date,
        max_radius_km=max_radius_km,
    )
    hotels = [entry["hotel"].model_dump() for entry in hotel_entries]
    return {
        "success": True,
        "landmark": landmark_name,
        "hotel_count": len(hotels),
        "hotels": hotels,
        "proximity_details": [
            {
                "hotel_name": entry["hotel"].name,
                "distance_km": entry["distance_km"],
                "distance_label": entry["distance_label"],
                "walking_time_mins": entry["walking_time_mins"],
            }
            for entry in hotel_entries
        ],
    }


def get_hotel_details_tool(hotel_code: str) -> Dict[str, Any]:
    """Retrieve full photos, amenities, descriptions, and address of a hotel.
    
    Args:
        hotel_code: Unique TBO hotel code
    """
    return get_hotel_details(hotel_code=hotel_code)
