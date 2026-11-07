"""Attraction details from OpenStreetMap."""
from typing import Optional, Dict, Any

from app.services.dining_service.osm_client import run_overpass, OVERPASS_TIMEOUT_SECONDS
from .search import osm_element_to_place


def get_attraction_details(attraction_id: str) -> Optional[Dict[str, Any]]:
    """Fetches an attraction by its id (format: osm_<node|way|relation>_<id>)."""
    parts = attraction_id.split("_")
    if len(parts) != 3 or parts[0] != "osm" or parts[1] not in ("node", "way", "relation") or not parts[2].isdigit():
        return None

    elements = run_overpass(
        f"[out:json][timeout:{OVERPASS_TIMEOUT_SECONDS}];{parts[1]}({parts[2]});out center tags;"
    )
    if not elements:
        return None

    el = elements[0]
    place = osm_element_to_place(el)
    if place is None:
        return None

    tags = el.get("tags", {})
    return {
        "id": place.id,
        "name": place.name,
        "category": place.category.value,
        "description": place.description,
        "address": place.address,
        "coordinates": {"lat": place.location.lat, "lng": place.location.lng},
        "entry_fee_inr": place.entry_fee,
        "opening_hours": place.opening_hours,
        "website": tags.get("website") or tags.get("contact:website"),
        "wikipedia": tags.get("wikipedia"),
        "phone": tags.get("phone") or tags.get("contact:phone"),
    }
