"""Monuments, heritage sites and sightseeing attractions from OpenStreetMap (Overpass)."""
import re
from typing import Any, Dict, List, Optional

from app.schemas.attraction import PlaceItem, PlaceCategory, GeoLocation, PlacesSearchResult
from app.services.dining_service.osm_client import run_overpass, element_coords, OVERPASS_TIMEOUT_SECONDS
from app.services.hotel_service.distance import haversine_distance_km
from app.services.location_service import geocode_city

# Search radius around a city centre when the caller gave only a city name.
CITY_SEARCH_RADIUS_KM = 12.0
RESULT_LIMIT = 60

HISTORIC_HERITAGE = "fort|castle|palace|archaeological_site|ruins|temple|tomb|city_gate|manor"
HISTORIC_MONUMENT = "monument|memorial|building"
TOURISM_ACTIVITY = "attraction|viewpoint|zoo|theme_park|gallery|aquarium"


def osm_element_to_place(el: Dict[str, Any], center: Optional[Dict[str, float]] = None) -> Optional[PlaceItem]:
    """Convert an Overpass element to a PlaceItem using only tags OSM provides."""
    tags = el.get("tags", {})
    name = tags.get("name:en") or tags.get("name")
    lat, lng = element_coords(el)
    if not name or lat is None or lng is None:
        return None

    historic = tags.get("historic", "")
    tourism = tags.get("tourism", "")
    if historic and re.fullmatch(HISTORIC_HERITAGE, historic):
        category = PlaceCategory.HERITAGE
    elif historic or tourism == "museum":
        category = PlaceCategory.MONUMENT
    else:
        category = PlaceCategory.ACTIVITY

    entry_fee = None
    if tags.get("fee") == "no":
        entry_fee = 0.0
    elif tags.get("charge"):
        amount = re.search(r"\d+(?:\.\d+)?", tags["charge"].replace(",", ""))
        entry_fee = float(amount.group(0)) if amount else None

    distance_m = None
    if center:
        distance_m = int(haversine_distance_km(center["lat"], center["lng"], lat, lng) * 1000)

    address = ", ".join(p for p in (tags.get("addr:street"), tags.get("addr:suburb"), tags.get("addr:city")) if p)

    return PlaceItem(
        id=f"osm_{el['type']}_{el['id']}",
        name=name,
        category=category,
        description=tags.get("description:en") or tags.get("description"),
        address=address,
        location=GeoLocation(lat=lat, lng=lng),
        distance_meters=distance_m,
        entry_fee=entry_fee,
        opening_hours=tags.get("opening_hours"),
        photo_urls=[],
        source_provider="osm",
    )


def search_attractions(
    city: str,
    category: Optional[PlaceCategory] = None,
    tags: Optional[List[str]] = None,
    max_entry_fee: Optional[float] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius_km: Optional[float] = None,
    sort_by: Optional[str] = "distance_asc",
) -> PlacesSearchResult:
    """Searches monuments, heritage sites and attractions near a point or city centre.

    Ratings are not available from OpenStreetMap, so results are never ranked by rating.
    """
    if lat is None or lng is None:
        center = geocode_city(city)
        if not center:
            from app.services.fallback_catalog import attractions as _fallback
            fb = _fallback(city)
            return PlacesSearchResult(places=fb, total_found=len(fb), provider_used="catalog" if fb else "osm")
        radius_km = radius_km or CITY_SEARCH_RADIUS_KM
    else:
        center = {"lat": lat, "lng": lng}
        radius_km = radius_km or CITY_SEARCH_RADIUS_KM

    radius_m = int(radius_km * 1000)
    around = f"(around:{radius_m},{center['lat']},{center['lng']})"
    overpass_query = f"""
    [out:json][timeout:{OVERPASS_TIMEOUT_SECONDS}];
    (
      nwr["tourism"~"^({TOURISM_ACTIVITY}|museum)$"]["name"]{around};
      nwr["historic"~"^({HISTORIC_HERITAGE}|{HISTORIC_MONUMENT})$"]["name"]{around};
    );
    out center {RESULT_LIMIT};
    """

    places: List[PlaceItem] = []
    for el in run_overpass(overpass_query):
        place = osm_element_to_place(el, center)
        if place is None:
            continue
        if category and place.category != category:
            continue
        if max_entry_fee is not None and place.entry_fee is not None and place.entry_fee > max_entry_fee:
            continue
        places.append(place)

    provider = "osm"
    if not places:
        from app.services.fallback_catalog import attractions as _fallback
        places = [p for p in _fallback(city, center) if (not category or p.category == category)
                  and (max_entry_fee is None or p.entry_fee is None or p.entry_fee <= max_entry_fee)]
        provider = "catalog" if places else "osm"

    if sort_by == "price_asc":
        places.sort(key=lambda p: (p.entry_fee is None, p.entry_fee or 0.0))
    else:
        places.sort(key=lambda p: p.distance_meters if p.distance_meters is not None else float("inf"))

    return PlacesSearchResult(places=places, total_found=len(places), provider_used=provider)
