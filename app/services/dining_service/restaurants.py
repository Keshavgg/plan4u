"""Restaurant search from OpenStreetMap."""
from typing import List, Optional
from app.schemas.attraction import PlaceItem, PlaceCategory, PriceBand, GeoLocation, PlacesSearchResult
from app.services.hotel_service.distance import haversine_distance_km
from .osm_client import query_osm_food_spots


def search_restaurants(
    lat: float,
    lng: float,
    radius_meters: int = 4000,
    cuisines: Optional[List[str]] = None,
    price_band: Optional[PriceBand] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_rating: Optional[float] = None,
    sort_by: Optional[str] = "distance_asc",
    limit: int = 15,
) -> PlacesSearchResult:
    """Finds restaurants near coordinates.

    OpenStreetMap has no ratings or prices, so min_rating / price filters exclude every
    result when set (we cannot verify them) and results are never ranked by rating.
    """
    places: List[PlaceItem] = []

    for o in query_osm_food_spots(lat, lng, radius_meters=radius_meters, amenity_tag="restaurant", limit=limit * 3):
        if min_rating is not None or min_price is not None or max_price is not None or price_band:
            continue
        if cuisines:
            wanted = {c.lower() for c in cuisines}
            if not any(any(w in c.lower() for w in wanted) for c in o["cuisines"]):
                continue

        dist_km = haversine_distance_km(lat, lng, o["lat"], o["lng"])
        places.append(
            PlaceItem(
                id=o["id"],
                name=o["name"],
                category=PlaceCategory.RESTAURANT,
                address=o["street"],
                location=GeoLocation(lat=o["lat"], lng=o["lng"]),
                distance_meters=int(dist_km * 1000),
                cuisines=o["cuisines"],
                opening_hours=o["opening_hours"],
                source_provider="osm",
            )
        )

    places.sort(key=lambda p: p.distance_meters)
    return PlacesSearchResult(places=places[:limit], total_found=len(places), provider_used="osm")
