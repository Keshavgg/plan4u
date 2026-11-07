"""Event-Anchored Trip Generator: builds a weekend plan around a concert, show, or match.

Only data returned by live sources is used. If the event has no venue coordinates, or a
supplier returns nothing, the related section is None rather than a guessed value.
"""
import datetime
from typing import Dict, Any, Optional
from app.date_utils import resolve_stay_dates
from app.services.flight_service.search import search_flights
from app.services.hotel_service.search import search_hotels
from app.services.dining_service.restaurants import search_restaurants


def create_event_anchored_plan(
    event_name_or_id: str,
    city: str,
    origin_city: str,
    destination_airport: Optional[str] = None,
    departure_date: Optional[str] = None,
    return_date: Optional[str] = None,
    travelers: int = 2,
    max_budget: Optional[float] = None,
) -> Dict[str, Any]:
    """Designs a getaway anchored around an event.

    origin_city is the origin airport code; destination_airport is required to search flights.
    """
    from app.tools.events import search_live_events_tool

    departure_date, return_date = resolve_stay_dates(departure_date, return_date)

    # 1. Fetch matching event
    events = search_live_events_tool(city=city).get("events", [])
    needle = event_name_or_id.lower()
    matched_event = next(
        (e for e in events if needle in (e.get("title") or "").lower() or needle in (e.get("id") or "").lower()),
        None,
    )
    if not matched_event:
        return {"success": False, "error": f"No live event matching '{event_name_or_id}' found in {city}."}

    v_lat = matched_event.get("venue_lat")
    v_lng = matched_event.get("venue_lng")
    has_venue_coords = v_lat is not None and v_lng is not None

    # 2. Flights
    recommended_flight = None
    if destination_airport:
        flights_res = search_flights(
            origin=origin_city,
            destination=destination_airport,
            departure_date=departure_date,
            return_date=return_date,
            adults=travelers,
        )
        recommended_flight = flights_res.options[0] if flights_res.options else None

    # 3. Hotel near the venue (distance filter only when coordinates are known)
    hotels_res = search_hotels(
        city=city,
        check_in_date=departure_date,
        check_out_date=return_date,
        adults=travelers,
        lat=v_lat,
        lng=v_lng,
        radius_km=3.0 if has_venue_coords else None,
        sort_by="distance_asc" if has_venue_coords else "price_asc",
    )
    recommended_hotel = hotels_res.options[0] if hotels_res.options else None

    # 4. Dining near the venue
    post_show_spot = None
    if has_venue_coords:
        dining_res = search_restaurants(
            lat=v_lat,
            lng=v_lng,
            radius_meters=1500,
            sort_by="rating_desc",
            limit=2,
        )
        post_show_spot = dining_res.places[0] if dining_res.places else None

    # 5. Total from known costs only
    nights = (datetime.date.fromisoformat(return_date) - datetime.date.fromisoformat(departure_date)).days
    flight_cost = recommended_flight.published_fare * travelers if recommended_flight else None
    hotel_cost = recommended_hotel.min_price_per_night * nights if recommended_hotel else None
    ticket_price = matched_event.get("min_price_inr")
    event_cost = ticket_price * travelers if ticket_price is not None else None
    known_costs = [c for c in (flight_cost, hotel_cost, event_cost) if c is not None]
    known_total = sum(known_costs) if known_costs else None

    return {
        "success": True,
        "anchor_event": matched_event,
        "itinerary_title": f"Trip to {city} for {matched_event['title']}",
        "post_show_dining": post_show_spot.model_dump() if hasattr(post_show_spot, "model_dump") else post_show_spot,
        "recommended_hotel": recommended_hotel.model_dump() if recommended_hotel else None,
        "recommended_flight": recommended_flight.model_dump() if recommended_flight else None,
        "cost_breakdown_inr": {"flight": flight_cost, "hotel": hotel_cost, "event_tickets": event_cost},
        "estimated_known_total_inr": known_total,
        "within_budget": (known_total <= max_budget) if known_total is not None and max_budget is not None else None,
    }
