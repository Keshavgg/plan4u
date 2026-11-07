"""AI-facing dining, cafes, and stop-adjacent food tools."""
from typing import Optional, Dict, Any, List
from app.services.dining_service import (
    search_cafes,
    search_restaurants,
    recommend_food_near_stop,
)
from app.schemas.attraction import GeoLocation, RecommendNearStopQuery
from app.services.location_service import geocode_city


def search_cafes_tool(
    city_or_area: str,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius_meters: int = 8000,
) -> Dict[str, Any]:
    """Search specialty coffee roasteries, rooftop cafes, and bakeries."""
    if lat is None or lng is None:
        center = geocode_city(city_or_area)
        if not center:
            return {"success": False, "error": f"Could not locate '{city_or_area}'.", "count": 0, "cafes": []}
        lat, lng = center["lat"], center["lng"]

    res = search_cafes(lat=lat, lng=lng, radius_meters=radius_meters)
    return {
        "success": True,
        "count": len(res.places),
        "cafes": [p.model_dump() for p in res.places],
    }


def search_restaurants_tool(
    city_or_area: str,
    cuisine: Optional[str] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius_meters: int = 8000,
) -> Dict[str, Any]:
    """Search authentic local cuisine, thalis, fine dining, or street food."""
    if lat is None or lng is None:
        center = geocode_city(city_or_area)
        if not center:
            return {"success": False, "error": f"Could not locate '{city_or_area}'.", "count": 0, "restaurants": []}
        lat, lng = center["lat"], center["lng"]

    res = search_restaurants(
        lat=lat, lng=lng, radius_meters=radius_meters,
        cuisines=[cuisine] if cuisine else None,
    )
    return {
        "success": True,
        "count": len(res.places),
        "restaurants": [p.model_dump() for p in res.places],
    }


def recommend_food_near_stop_tool(
    stop_name: str,
    stop_lat: float,
    stop_lng: float,
    cuisine_preference: Optional[str] = None,
    max_walking_time_mins: int = 15,
) -> Dict[str, Any]:
    """Find food and cafes specifically adjacent to an itinerary sightseeing stop."""
    query = RecommendNearStopQuery(
        stop_name=stop_name,
        lat=stop_lat,
        lng=stop_lng,
        preference=cuisine_preference or "authentic local food",
    )
    res = recommend_food_near_stop(query)
    return {
        "success": True,
        "stop_name": stop_name,
        "recommendations": [p.model_dump() for p in res.places],
    }


def reserve_restaurant_table_tool(
    restaurant_name: str,
    city: str,
    party_size: int,
    reservation_time: str,
    guest_name: str,
    guest_phone: str,
    special_requests: Optional[str] = None,
) -> Dict[str, Any]:
    """Table reservation. Not supported until a real reservation provider is integrated."""
    return {
        "success": False,
        "error": "Table reservations are not available: no reservation provider is integrated.",
    }
