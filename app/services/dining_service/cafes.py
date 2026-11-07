"""Cafe search from OpenStreetMap."""
from app.schemas.attraction import PlaceItem, PlaceCategory, GeoLocation, PlacesSearchResult
from app.services.hotel_service.distance import haversine_distance_km
from .osm_client import query_osm_food_spots


def search_cafes(
    lat: float,
    lng: float,
    radius_meters: int = 2000,
    limit: int = 10,
) -> PlacesSearchResult:
    """Finds cafes near coordinates, nearest first. OpenStreetMap has no ratings or prices."""
    places = []
    for o in query_osm_food_spots(lat, lng, radius_meters=radius_meters, amenity_tag="cafe", limit=limit * 3):
        dist_km = haversine_distance_km(lat, lng, o["lat"], o["lng"])
        places.append(
            PlaceItem(
                id=o["id"],
                name=o["name"],
                category=PlaceCategory.CAFE,
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
