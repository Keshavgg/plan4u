"""Live events and entertainment discovery tools using Gemini Google Search Grounding & Event aggregators."""
from typing import Optional, Dict, Any, List
import urllib.parse
from app.services.hotel_service.distance import haversine_distance_km

# How many catalog events a request reads before the caller's price/category filters apply.
CATALOG_READ_LIMIT = 20


def search_live_events_tool(
    city: str,
    category: Optional[str] = None,
    timeframe: str = "this week",
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    locality: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    is_free: Optional[bool] = None,
    sort_by: Optional[str] = "popularity",
) -> Dict[str, Any]:
    """Search live, up-to-date concerts, comedy shows, nightlife, festivals and gigs in an Indian city.
    
    Supports GPS distance calculation, price range filters, free entry filters, and category sorting.
    """
    city_clean = city.strip().title()
    events: List[Dict[str, Any]] = []

    # Event catalog: Exa fills it in the background and a request normally reads stored data. A specific
    # search ("Zakir Khan", "pottery workshop") is matched against it first, then searched live once and
    # stored. Locality, price and distance are filtered below in our own code. Nothing is invented: if the
    # catalog has nothing, the caller gets an empty list and search links.
    try:
        from app.services.event_catalog import event_catalog
        events = event_catalog.search(city_clean, category, limit=CATALOG_READ_LIMIT)
        if events:
            print(f"[EventsTool:Catalog] {len(events)} events for {city_clean}")
    except Exception as e:
        print(f"[EventsTool:Catalog] Event catalog error: {e}")

    # 3. Apply Filters: Category, Price, Free, Proximity
    filtered = []
    for e in events:
        if is_free is True and not e.get("is_free", False):
            continue

        p_min = e.get("min_price_inr")
        if (min_price is not None or max_price is not None) and p_min is None:
            continue
        if min_price is not None and p_min < min_price:
            continue
        if max_price is not None and p_min > max_price:
            continue

        # Proximity distance if coordinates exist
        if lat is not None and lng is not None and "venue_lat" in e and "venue_lng" in e:
            dist_km = haversine_distance_km(lat, lng, e["venue_lat"], e["venue_lng"])
            e["distance_km"] = round(dist_km, 2)
            e["distance_meters"] = int(dist_km * 1000)

        filtered.append(e)

    # 4. Sorting
    if sort_by == "price_asc":
        filtered.sort(key=lambda x: x.get("min_price_inr") or 0.0)
    elif sort_by == "price_desc":
        filtered.sort(key=lambda x: x.get("min_price_inr") or 0.0, reverse=True)
    elif sort_by == "distance_asc" and lat is not None and lng is not None:
        filtered.sort(key=lambda x: x.get("distance_km", float("inf")))

    result: Dict[str, Any] = {
        "success": True,
        "city": city_clean,
        "events_count": len(filtered),
        "events": filtered,
    }
    if not filtered:
        search_text = urllib.parse.quote(f"{category or 'events'} in {city_clean}")
        result["message"] = "No live events found for this right now."
        result["search_links"] = {
            "google": f"https://www.google.com/search?q={search_text}+tickets",
            "bookmyshow": f"https://in.bookmyshow.com/explore/events-{urllib.parse.quote(city_clean.lower())}",
        }
    return result
