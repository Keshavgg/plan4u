"""AI-facing attractions and monuments tools."""
from typing import Optional, Dict, Any, List
from app.services.attractions_service import (
    search_attractions,
    get_attraction_details,
)
from app.schemas.attraction import PlaceCategory


def search_attractions_tool(
    city: str,
    category: Optional[str] = None,
    must_see_only: bool = False,
) -> Dict[str, Any]:
    """Search heritage monuments, forts, UNESCO sites, and sightseeing spots in a city.
    
    Args:
        city: City name, e.g. 'Delhi', 'Jaipur', 'Goa'
        category: Optional category filter e.g. 'monument', 'museum', 'activity'
        must_see_only: If True, prioritize UNESCO and top iconic monuments
    """
    cat_enum = None
    if category:
        try:
            cat_enum = PlaceCategory(category.lower())
        except ValueError:
            pass
            
    res = search_attractions(city=city, category=cat_enum)
    return {
        "success": True,
        "city": city,
        "count": len(res.places),
        "places": [p.model_dump() for p in res.places],
    }


def get_attraction_details_tool(place_id: str) -> Dict[str, Any]:
    """Retrieve detailed history, photography golden-hour tips, ticket price, and timings.
    
    Args:
        place_id: Unique ID of the attraction
    """
    return get_attraction_details(place_id=place_id)
