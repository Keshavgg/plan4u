"""Proximity food recommendation near an itinerary stop (matches Postman /v1/places/recommend)."""
from typing import Optional, Dict, Any

from app.schemas.attraction import PlaceCategory, PriceBand
from .cafes import search_cafes
from .restaurants import search_restaurants


def recommend_food_near_stop(
    stop_name: str,
    lat: float,
    lng: float,
    meal_type: str = "lunch",  # breakfast, lunch, sunset_cafe, dinner
    preference: Optional[str] = None,
    radius_meters: int = 1500,
) -> Dict[str, Any]:
    """Finds the best restaurant or cafe directly adjacent to a tourist attraction or stop."""
    is_cafe_request = meal_type.lower() in ["breakfast", "sunset_cafe", "coffee", "evening"]
    
    if is_cafe_request:
        result = search_cafes(lat, lng, radius_meters=radius_meters, limit=3)
    else:
        result = search_restaurants(lat, lng, radius_meters=radius_meters, limit=3)

    if not result.places:
        # Fallback if no spots within narrow radius, expand search
        result = search_restaurants(lat, lng, radius_meters=4000, limit=2)

    best_match = result.places[0] if result.places else None

    return {
        "stop_name": stop_name,
        "meal_type": meal_type,
        "recommended_spot": best_match,
        "walking_distance_meters": best_match.distance_meters if best_match else None,
        "recommendation_reason": (
            f"Located just {best_match.distance_meters}m from {stop_name}, perfect for {meal_type} after sightseeing."
            if best_match
            else f"Top dining recommended in the vicinity of {stop_name}."
        ),
    }
