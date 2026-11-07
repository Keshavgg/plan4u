"""FastAPI REST API routes for Plan4U backend."""
from fastapi import APIRouter, Depends, HTTPException, Query, Header, Path
from fastapi.responses import RedirectResponse, HTMLResponse
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from app.schemas.flight import (
    FlightSearchQuery,
    FlightSearchResult,
    FlightOption,
)
from app.schemas.hotel import (
    HotelSearchQuery,
    HotelSearchResult,
    HotelOption,
)
from app.schemas.attraction import (
    PlaceCategory,
    PriceBand,
    PlaceItem,
    RestaurantSearchQuery,
    AttractionSearchQuery,
    PlacesSearchResult,
    NearbyExploreResult,
    GeoLocation,
)
from app.schemas.itinerary import ItineraryRequest, CompleteItinerary
from app.schemas.agent import LiveCopilotQuery, LiveCopilotResponse
from app.schemas.booking import (
    CreateBookingHoldRequest,
    BookingRecord,
    BookingStatus,
    RazorpayCheckoutSession,
    PassengerDetail,
    GstDetails,
)
from app.agent.planner_orchestrator import PlannerOrchestrator
from app.agent.companion_orchestrator import CompanionOrchestrator
from app.services.flight_service import (
    search_flights,
    quote_flight_fare,
    get_fare_rules,
    get_flight_ssr,
    create_flight_hold,
)
from app.services.hotel_service import (
    search_hotels,
    search_hotels_near_location,
    get_hotel_details,
    prebook_hotel,
)
from app.services.dining_service import (
    search_restaurants,
    search_cafes,
    recommend_food_near_stop,
)
from app.services.attractions_service import (
    search_attractions,
    get_attraction_details,
)
from app.services.reel_service import convert_reel_to_places, UnsupportedUrlError
from app.services.group_split_service import settle_group_expenses, ExpenseItem, GroupBalanceSheet
from app.tools.events import search_live_events_tool
from app.tools.payments import create_checkout_session_tool
from app.services.smart_tools import (
    analyze_flight_tradeoffs,
    cluster_places_by_geography,
    get_emergency_reroute_options,
    create_event_anchored_plan,
    generate_group_settlement_links,
    estimate_transport_options,
    generate_packing_checklist,
    get_destination_weather_insights,
    convert_currency,
)
from app.auth import get_current_user, get_optional_user
from app.config import settings
from app.date_utils import resolve_stay_dates

router = APIRouter(prefix="/api/v1", tags=["Plan4U API"])

planner_orchestrator = PlannerOrchestrator()
companion_orchestrator = CompanionOrchestrator()


# =============================================================
# 1. System Health
# =============================================================
@router.get("/health")
def health_check():
    """System health check and live API provider integration status."""
    return {
        "status": "healthy",
        "service": "Plan4U AI Travel Engine",
        "env": settings.ENV,
        "providers_status": {
            "gemini_search_grounding": bool(settings.GEMINI_API_KEY),
            "anthropic_claude_clip2trip": bool(settings.ANTHROPIC_API_KEY),
            "tbo_air": bool(settings.TBO_USERNAME and settings.TBO_PASSWORD),
            "tbo_hotels": bool(settings.TBO_HOTEL_USERNAME and settings.TBO_HOTEL_PASSWORD),
            "galileo_gds": bool(settings.GALILEO_API_URL and settings.GALILEO_CREDENTIALS),
            "razorpay_payments": bool(settings.PAYMENT_KEY_ID and settings.PAYMENT_KEY_SECRET),
        },
    }


# =============================================================
# 2. AI Multi-Agent Panels
# =============================================================
class PlannerResponse(BaseModel):
    success: bool = True
    session_id: str
    status: str
    itinerary: CompleteItinerary
    checkout_session: Optional[RazorpayCheckoutSession] = None
    execution_logs: List[str] = Field(default_factory=list)


class PlannerChatQuery(BaseModel):
    user_message: str
    origin: Optional[str] = None
    destination: Optional[str] = None
    budget: Optional[float] = None
    traveler_count: Optional[int] = 2
    interests: Optional[List[str]] = None


class PlannerChatResponse(BaseModel):
    reply_text: str
    itinerary: Optional[CompleteItinerary] = None
    checkout_session: Optional[RazorpayCheckoutSession] = None
    suggested_quick_replies: List[str] = Field(default_factory=list)


@router.post("/planner/chat", response_model=PlannerChatResponse)
def master_planner_chat(query: PlannerChatQuery):
    """Panel 1 Conversational Planner: Natural language chat interface that synthesizes full itineraries."""
    from datetime import datetime, timedelta
    from app.agent.subagents.copilot_agent import call_ai_engine
    import json

    msg = query.user_message.strip()
    msg_low = msg.lower()

    # Determine if general question or trip request
    is_general_q = any(q in msg_low for q in ["best time", "kaisa mausam", "packing", "what to wear", "safe for solo", "visa", "currency"]) and not any(w in msg_low for w in ["plan", "bna", "banao", "trip", "itinerary", "jaana hai", "ghoomna"])

    if is_general_q:
        ai_prompt = f"User asks travel planning advice: '{msg}'. Provide a friendly, expert, concise 3-4 line Hinglish answer with actionable advice."
        reply = call_ai_engine(ai_prompt) or "Bhai, travel time ke liye seasonal climate aur local crowd dekh ke plan karna sabse best rehta hai!"
        return PlannerChatResponse(
            reply_text=reply,
            itinerary=None,
            checkout_session=None,
            suggested_quick_replies=["Plan a 3-Day trip there ✈️", "What about budget? 💰", "Show top hotels 🏨"]
        )

    # Extract travel parameters using AI / regex
    origin = query.origin or "DEL"
    destination = query.destination or "Jaipur"
    budget = query.budget or 35000.0
    duration_days = 3
    traveler_count = query.traveler_count or 2
    interests = query.interests or ["heritage", "street food", "cafes"]

    # AI parameter extraction
    extract_prompt = f"""
Extract travel parameters from user request: "{msg}"
Return ONLY a valid JSON object with keys:
- "origin": 3-letter IATA (DEL, BOM, BLR, CCU, MAA, HYD, etc.) or default "DEL"
- "destination": City name (Jaipur, Goa, Udaipur, Mumbai, Delhi, Bengaluru, Kochi, etc.)
- "duration_days": integer (2, 3, or 4)
- "budget": integer INR budget (or 35000)
- "traveler_count": integer
- "interests": list of strings (e.g. ["heritage", "street food", "beach"])
"""
    try:
        raw_ai = call_ai_engine(extract_prompt) or "{}"
        if "```" in raw_ai:
            raw_ai = raw_ai.split("```")[1]
            if raw_ai.startswith("json"):
                raw_ai = raw_ai[4:].strip()
        parsed = json.loads(raw_ai.strip())
        origin = parsed.get("origin") or origin
        destination = parsed.get("destination") or destination
        duration_days = int(parsed.get("duration_days") or duration_days)
        budget = float(parsed.get("budget") or budget)
        traveler_count = int(parsed.get("traveler_count") or traveler_count)
        if parsed.get("interests"):
            interests = parsed.get("interests")
    except Exception:
        # Fallback keyword checks
        for c in ["Goa", "Jaipur", "Udaipur", "Mumbai", "Delhi", "Bengaluru", "Kochi", "Kolkata", "Chennai", "Hyderabad"]:
            if c.lower() in msg_low:
                destination = c
                break
        if "mumbai" in msg_low and "delhi" in msg_low:
            if "mumbai se" in msg_low:
                origin, destination = "BOM", "Delhi"
            elif "delhi se" in msg_low:
                origin, destination = "DEL", "Mumbai"

    # Normalize destination
    destination = destination.strip().title()

    # Generate dates: 14 days out
    start_dt = datetime.now() + timedelta(days=14)
    end_dt = start_dt + timedelta(days=duration_days)
    start_date_str = start_dt.strftime("%Y-%m-%d")
    end_date_str = end_dt.strftime("%Y-%m-%d")

    req = ItineraryRequest(
        origin=origin.upper(),
        destination=destination,
        start_date=start_date_str,
        end_date=end_date_str,
        total_budget=budget,
        traveler_count=traveler_count,
        interests=interests,
    )

    state = planner_orchestrator.generate_plan(req)
    itin = state.final_itinerary
    checkout = state.budget_result.checkout_session if state.budget_result else None

    # AI conversational summary introducing the itinerary
    flight_name = itin.selected_flight.airline_name if itin.selected_flight else "Direct Airline"
    hotel_name = itin.selected_hotel.name if itin.selected_hotel else "Top Rated Boutique Hotel"
    total_cost = itin.grand_total_inr

    summary_prompt = f"""
You are Plan4U Master Planner AI.
User requested: "{msg}"
Generated Itinerary Highlights:
- Destination: {destination} ({duration_days} Days)
- Flight: {flight_name} from {origin}
- Stay: {hotel_name}
- Total Price: ₹{total_cost:,.0f} for {traveler_count} travelers (Under user budget of ₹{budget:,.0f})
- Daily stops: Zero-backtrack sightseeing, handpicked cafes, street food, and monument fast-track passes included.
- Synchronized Hold: 15-minute Razorpay lock active.

Write a friendly, energetic, expert 3-paragraph Hinglish pitch presenting this itinerary to the user.
Highlight why this plan is optimal and how everything is synced together.
"""
    reply_intro = call_ai_engine(summary_prompt)
    if not reply_intro:
        reply_intro = f"Bhai, tumhara {destination} ka {duration_days}-Day trip ready hai! Flight ({flight_name}), verified stay ({hotel_name}), aur day-by-day zero-backtrack itinerary sab ek saath sync kar diya hai. Total package cost ₹{total_cost:,.0f} aaya hai (budget ₹{budget:,.0f} ke andar)! 15-minute lock active hai."

    return PlannerChatResponse(
        reply_text=reply_intro,
        itinerary=itin,
        checkout_session=checkout,
        suggested_quick_replies=[
            f"Lock this {destination} trip with ₹1 hold 🔒",
            "Show alternative flight timings ✈️",
            "Can we add a luxury pool resort? 🏊‍♂️",
        ]
    )


@router.post("/planner/generate", response_model=PlannerResponse)
def generate_master_itinerary(request: ItineraryRequest):
    """Panel 1: Master Pre-Trip Planner. Synthesizes flights, hotels, monuments, dining, and budget limit."""
    try:
        state = planner_orchestrator.generate_plan(request)
        if not state.final_itinerary:
            raise HTTPException(status_code=500, detail="Failed to synthesize itinerary.")
        return PlannerResponse(
            success=True,
            session_id=state.session_id,
            status=state.status,
            itinerary=state.final_itinerary,
            checkout_session=state.budget_result.checkout_session if state.budget_result else None,
            execution_logs=state.execution_logs,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Planning error: {str(e)}")


@router.post("/companion/chat", response_model=LiveCopilotResponse)
def live_companion_chat(
    query: LiveCopilotQuery,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    user_id: Optional[str] = Depends(get_optional_user),
):
    """Panel 2: Live In-Trip Companion. GPS location-aware, food cravings, live events, instant passes.

    Send the login token to let Swiggy searches run on the user's own connected account.
    """
    session_id = x_session_id or query.active_trip_id or "default_live_session"
    try:
        response = companion_orchestrator.handle_message(session_id=session_id, query=query, user_id=user_id)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Companion error: {str(e)}")


@router.post("/companion/reset")
def reset_companion_session(x_session_id: Optional[str] = Header(None, alias="X-Session-ID")):
    """Completely flushes companion memory and state for a fresh chat session."""
    session_id = x_session_id or "default_live_session"
    companion_orchestrator.reset_session(session_id)
    return {"status": "success", "message": f"Session {session_id} memory cleared"}


@router.get("/companion/cache-stats")
def get_companion_cache_stats():
    """Returns real-time Smart Caching metrics, hit-rate, and API cost savings."""
    from app.services.exa_service import exa_service
    from app.services.event_catalog import event_catalog
    from app.services.swiggy_search_cache import swiggy_search_cache
    return {
        "status": "active",
        "service": "Exa AI Smart Cache Manager",
        "exa_calls_today": event_catalog.calls_today(),
        "exa_daily_cap": settings.EXA_MAX_CALLS_PER_DAY,
        "exa_custom_searches_today": event_catalog.custom_calls_today(),
        "exa_custom_searches_cap": settings.EXA_MAX_CUSTOM_SEARCHES_PER_DAY,
        "swiggy_searches_today": swiggy_search_cache.calls_today(),
        "swiggy_searches_cap": settings.SWIGGY_MAX_SEARCHES_PER_DAY,
        **exa_service.cache_mgr.get_stats()
    }


@router.get("/companion/reverse-geocode")
def reverse_geocode_endpoint(lat: float, lng: float):
    """Reverse geocodes real-time GPS coordinates into authentic Indian locality, city and landmark."""
    from app.services.location_service import reverse_geocode_coords
    return reverse_geocode_coords(lat, lng)


# =============================================================
# 2.1 Swiggy Builders Club MCP Platform Integration
# =============================================================
def _swiggy_point(lat: Optional[float], lng: Optional[float], city: Optional[str]):
    """Resolves the search point from explicit coordinates or a geocoded city name."""
    if lat is not None and lng is not None:
        return lat, lng
    if city:
        from app.services.location_service import geocode_city
        center = geocode_city(city)
        if center:
            return center["lat"], center["lng"]
    raise HTTPException(status_code=400, detail="Provide lat/lng or a city that can be located.")


def _run_swiggy(fn, *args, **kwargs):
    """Runs a Swiggy MCP call and maps its failures onto HTTP errors."""
    from app.services.swiggy_mcp_service import SwiggyAuthRequired, SwiggyError
    try:
        return fn(*args, **kwargs)
    except SwiggyAuthRequired:
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Connect your Swiggy account to continue.",
                "connect": {"method": "POST", "url": "/api/v1/swiggy/connect"},
            },
        )
    except SwiggyError as e:
        raise HTTPException(status_code=502, detail=str(e))


def _run_swiggy_discovery(user_id: str, fn, *args):
    """Read-only call: runs as the user's own account, else as the configured service account."""
    from app.services.swiggy_mcp_service import swiggy_mcp_service
    return _run_swiggy(lambda: fn(swiggy_mcp_service.discovery_actor(user_id), *args))


@router.get("/swiggy/status")
def get_swiggy_mcp_status(user_id: str = Depends(get_current_user)):
    """Whether the signed-in user has connected their own Swiggy account."""
    from app.services.swiggy_mcp_service import swiggy_mcp_service
    base = settings.SWIGGY_MCP_BASE_URL.rstrip("/")
    connected = swiggy_mcp_service.is_authenticated(user_id)
    return {
        "status": "connected" if connected else "not_connected",
        "connected": connected,
        "mcp_servers": {s: f"{base}/{s}" for s in ("food", "dineout", "im", "scenes")},
    }


@router.post("/swiggy/connect")
def swiggy_connect(user_id: str = Depends(get_current_user)):
    """Returns the Swiggy sign-in URL for this user. Open it in a popup; the user enters their
    phone number and OTP on Swiggy's page once, and the popup closes itself when done."""
    from app.services.swiggy_mcp_service import swiggy_mcp_service, SwiggyError
    try:
        return {"auth_url": swiggy_mcp_service.create_authorization_url(user_id)}
    except SwiggyError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/swiggy/oauth/callback")
def swiggy_oauth_callback(code: str, state: str):
    """Handles the OAuth callback from Swiggy and stores the tokens for the user who started the flow."""
    import json as _json
    from app.services.swiggy_mcp_service import swiggy_mcp_service
    frontend = settings.SWIGGY_FRONTEND_URL.rstrip("/")
    res = swiggy_mcp_service.exchange_code_for_token(code=code, state=state)
    if res.get("success"):
        html = f"""
        <!DOCTYPE html>
        <html>
        <head><title>Swiggy Connected</title></head>
        <body style="font-family: sans-serif; background: #0f172a; color: #fff; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0;">
          <div style="text-align: center; padding: 24px; background: #1e293b; border-radius: 16px; border: 1px solid #f97316;">
            <h2 style="color: #f97316; margin: 0 0 10px;">Swiggy connected</h2>
            <p style="color: #94a3b8; font-size: 14px;">You can close this window.</p>
          </div>
          <script>
            if (window.opener) {{
              window.opener.postMessage({{ type: 'SWIGGY_OAUTH_SUCCESS' }}, {_json.dumps(frontend)});
              setTimeout(() => window.close(), 700);
            }}
          </script>
        </body>
        </html>
        """
        return HTMLResponse(content=html)
    return RedirectResponse(url=f"{frontend}/?swiggy=error")


@router.post("/swiggy/disconnect")
def swiggy_disconnect(user_id: str = Depends(get_current_user)):
    """Revokes the user's Swiggy session and deletes their stored tokens."""
    from app.services.swiggy_mcp_service import swiggy_mcp_service
    swiggy_mcp_service.disconnect(user_id)
    return {"status": "success", "message": "Swiggy account disconnected"}


@router.get("/swiggy/food/search")
def search_swiggy_food_endpoint(
    query: str = Query(..., description="Food item, cuisine or restaurant"),
    lat: Optional[float] = Query(None, description="Delivery latitude"),
    lng: Optional[float] = Query(None, description="Delivery longitude"),
    city: Optional[str] = Query(None, description="City name, used when lat/lng are not given"),
    limit: int = Query(10, ge=1, le=30),
    user_id: str = Depends(get_current_user),
):
    """Food delivery restaurants from Swiggy MCP (search_restaurants)."""
    from app.services.swiggy_search_cache import swiggy_search_cache
    point_lat, point_lng = _swiggy_point(lat, lng, city)
    places = _run_swiggy(swiggy_search_cache.search, user_id, "food", query, point_lat, point_lng, limit)
    return {"query": query, "lat": point_lat, "lng": point_lng, "count": len(places), "results": places}


@router.get("/swiggy/dineout/search")
def search_swiggy_dineout_endpoint(
    query: str = Query(..., description="Restaurant, cuisine, area or vibe"),
    lat: Optional[float] = Query(None, description="Search latitude"),
    lng: Optional[float] = Query(None, description="Search longitude"),
    city: Optional[str] = Query(None, description="City name, used when lat/lng are not given"),
    limit: int = Query(10, ge=1, le=30),
    user_id: str = Depends(get_current_user),
):
    """Dineout restaurants and offers from Swiggy MCP (search_restaurants_dineout)."""
    from app.services.swiggy_search_cache import swiggy_search_cache
    point_lat, point_lng = _swiggy_point(lat, lng, city)
    places = _run_swiggy(swiggy_search_cache.search, user_id, "dineout", query, point_lat, point_lng, limit)
    return {"query": query, "lat": point_lat, "lng": point_lng, "count": len(places), "results": places}


@router.get("/swiggy/dineout/restaurants/{restaurant_id}")
def get_swiggy_dineout_details_endpoint(
    restaurant_id: str,
    lat: Optional[float] = Query(None, description="Latitude used in the search"),
    lng: Optional[float] = Query(None, description="Longitude used in the search"),
    city: Optional[str] = Query(None, description="City name, used when lat/lng are not given"),
    user_id: str = Depends(get_current_user),
):
    """Dineout restaurant profile, offers, timings and amenities (get_restaurant_details)."""
    from app.services.swiggy_mcp_service import swiggy_mcp_service
    point_lat, point_lng = _swiggy_point(lat, lng, city)
    return _run_swiggy_discovery(user_id, swiggy_mcp_service.get_dineout_details, restaurant_id, point_lat, point_lng)


@router.get("/swiggy/dineout/restaurants/{restaurant_id}/slots")
def get_swiggy_dineout_slots_endpoint(
    restaurant_id: str,
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Start date YYYY-MM-DD (covers 7 days)"),
    lat: Optional[float] = Query(None, description="Latitude used in the search"),
    lng: Optional[float] = Query(None, description="Longitude used in the search"),
    city: Optional[str] = Query(None, description="City name, used when lat/lng are not given"),
    user_id: str = Depends(get_current_user),
):
    """Bookable Dineout slots and booking ids (get_available_slots)."""
    from app.services.swiggy_mcp_service import swiggy_mcp_service
    point_lat, point_lng = _swiggy_point(lat, lng, city)
    return _run_swiggy_discovery(user_id, swiggy_mcp_service.get_dineout_slots, restaurant_id, date, point_lat, point_lng)


@router.get("/swiggy/instamart/search")
def search_swiggy_instamart_endpoint(
    query: str = Query(..., description="Product, category or brand"),
    limit: int = Query(10, ge=1, le=30),
    user_id: str = Depends(get_current_user),
):
    """Instamart products for the signed-in user's saved address (search_products)."""
    from app.services.swiggy_mcp_service import swiggy_mcp_service
    products = _run_swiggy(swiggy_mcp_service.search_swiggy_instamart, user_id, query, limit)
    return {"query": query, "count": len(products), "results": products}


@router.get("/swiggy/dineout/resolve")
def resolve_swiggy_dineout_url_endpoint(
    name: str = Query(..., description="Restaurant name"),
    city: str = Query("", description="City name")
):
    """Resolves direct official Swiggy Dineout table booking URL with zero broken links."""
    from app.services.swiggy_mcp_service import swiggy_mcp_service
    url = swiggy_mcp_service.resolve_restaurant_dineout_url(name=name, city=city)
    return {"name": name, "city": city, "dineout_url": url}




# =============================================================
# 3. Direct Flight Booking APIs (MakeMyTrip Style)
# =============================================================
@router.post("/flights/search", response_model=FlightSearchResult)
def search_flights_endpoint(query: FlightSearchQuery):
    """Search live flights with MMT filters: airlines, price range, stops, refundability, departure time window, and sorting."""
    return search_flights(
        origin=query.origin,
        destination=query.destination,
        departure_date=query.departure_date,
        return_date=query.return_date,
        adults=query.adults,
        children=query.children,
        infants=query.infants,
        cabin_class="1" if query.cabin_class == "economy" else "2",
        min_price=query.min_price,
        max_price=query.max_price,
        airlines=query.airlines,
        max_stops=query.max_stops,
        is_refundable=query.is_refundable,
        departure_time_window=query.departure_time_window,
        sort_by=query.sort_by or "price_asc",
    )


class FlightQuoteRequest(BaseModel):
    trace_id: str
    result_index: str


@router.post("/flights/quote")
def quote_flight_fare_endpoint(payload: FlightQuoteRequest):
    """Validate fare price freeze lock before checkout (Checks for price surge or tax changes)."""
    return quote_flight_fare(trace_id=payload.trace_id, result_index=payload.result_index)


class FlightRulesRequest(BaseModel):
    trace_id: str
    result_index: str


@router.post("/flights/rules")
def get_flight_fare_rules_endpoint(payload: FlightRulesRequest):
    """Fetch cancellation penalty bands, date change fees, and refundability rules (MMT Table)."""
    return get_fare_rules(trace_id=payload.trace_id, result_index=payload.result_index)


class FlightSSRRequest(BaseModel):
    trace_id: str
    result_index: str


@router.post("/flights/seat-map")
def get_flight_seat_map_and_addons_endpoint(payload: FlightSSRRequest):
    """Fetch seat map availability, hot meals (Veg/Non-Veg), and extra check-in baggage add-on prices."""
    return get_flight_ssr(trace_id=payload.trace_id, result_index=payload.result_index)


class FlightHoldRequest(BaseModel):
    trace_id: str
    result_index: str
    published_fare: float
    passengers: List[PassengerDetail]
    gst: Optional[GstDetails] = None


@router.post("/flights/hold")
def create_flight_pnr_hold_endpoint(payload: FlightHoldRequest):
    """Place a reservation hold on the airline GDS (TBO / Galileo), generate PNR, and issue Razorpay checkout link."""
    hold_res = create_flight_hold(
        trace_id=payload.trace_id,
        result_index=payload.result_index,
        passengers=payload.passengers,
        gst=payload.gst,
    )

    if hold_res.get("status") != "HOLD_CONFIRMED":
        return {"success": False, "flight_hold": hold_res, "checkout_session": None}

    first_pax = payload.passengers[0] if payload.passengers else None
    checkout = create_checkout_session_tool(
        amount_inr=payload.published_fare,
        description=f"Flight Booking Hold - PNR: {hold_res.get('pnr', 'PENDING')}",
        customer_email=first_pax.email if first_pax else None,
        customer_phone=first_pax.phone if first_pax else None,
    )

    return {
        "success": hold_res.get("status") == "HOLD_CONFIRMED",
        "flight_hold": hold_res,
        "checkout_session": checkout,
        "expires_in_minutes": 15,
    }


# =============================================================
# 4. Direct Hotel Booking APIs (MakeMyTrip Style)
# =============================================================
@router.post("/hotels/search", response_model=HotelSearchResult)
def search_hotels_endpoint(query: HotelSearchQuery):
    """Search hotels with location, min/max price, star ratings, amenities, and sorting."""
    return search_hotels(
        city=query.city,
        check_in_date=query.check_in_date,
        check_out_date=query.check_out_date,
        rooms=query.rooms,
        adults=query.adults,
        min_rating=query.min_rating or 3.5,
        min_star_rating=query.min_star_rating,
        min_price=query.min_price,
        max_budget_per_night=query.max_budget_per_night,
        preferred_amenities=query.preferred_amenities,
        lat=query.lat,
        lng=query.lng,
        radius_km=query.radius_km,
        sort_by=query.sort_by or "price_asc",
    )


@router.get("/hotels/nearby", response_model=HotelSearchResult)
def get_hotels_nearby_gps(
    lat: float = Query(..., description="Current GPS Latitude"),
    lng: float = Query(..., description="Current GPS Longitude"),
    city: str = Query("Delhi", description="Nearest city"),
    check_in_date: Optional[str] = Query(None, description="YYYY-MM-DD (defaults to tomorrow)"),
    check_out_date: Optional[str] = Query(None, description="YYYY-MM-DD (defaults to check-in + 2 nights)"),
    radius_km: float = Query(10.0, description="Max search radius in km"),
    min_star_rating: Optional[int] = Query(None, description="Min star rating: 3, 4, 5"),
    max_price: Optional[float] = Query(None, description="Max price per night"),
):
    """Auto-fetch nearby hotels based on user's live GPS coordinates sorted by closest distance."""
    check_in_date, check_out_date = resolve_stay_dates(check_in_date, check_out_date)
    return search_hotels(
        city=city,
        check_in_date=check_in_date,
        check_out_date=check_out_date,
        min_star_rating=min_star_rating,
        max_budget_per_night=max_price,
        lat=lat,
        lng=lng,
        radius_km=radius_km,
        sort_by="distance_asc",
    )


@router.get("/hotels/{hotel_code}")
def get_hotel_details_endpoint(hotel_code: str = Path(..., description="TBO Hotel Code")):
    """Retrieve full hotel profile: high-res photo gallery, amenities, and policies."""
    return get_hotel_details(hotel_code=hotel_code)


class HotelPrebookRequest(BaseModel):
    hotel_code: str
    booking_code: str
    room_index: int = 1


@router.post("/hotels/prebook")
def prebook_hotel_room_endpoint(payload: HotelPrebookRequest):
    """Pre-book lock to freeze room rate for 15 minutes before payment."""
    return prebook_hotel(
        hotel_code=payload.hotel_code,
        booking_code=payload.booking_code,
        room_index=payload.room_index,
    )


# =============================================================
# 5. Restaurants & Dining Manual Exploration APIs
# =============================================================
@router.post("/places/restaurants/search", response_model=PlacesSearchResult)
def search_restaurants_endpoint(query: RestaurantSearchQuery):
    """Manual restaurant & cafe exploration with cuisines, price band, veg/rooftop, and sorting."""
    from app.services.location_service import geocode_city
    lat = query.lat
    lng = query.lng
    radius = query.radius_meters
    if (lat is None or lng is None) and query.city:
        coords = geocode_city(query.city)
        if coords:
            lat, lng = coords["lat"], coords["lng"]
            radius = max(radius, 15000)

    if lat is None or lng is None:
        raise HTTPException(status_code=400, detail="Provide lat/lng or a city that can be located.")
    return search_restaurants(
        lat=lat,
        lng=lng,
        radius_meters=radius,
        cuisines=query.cuisines,
        price_band=query.price_band,
        min_price=query.min_price,
        max_price=query.max_price,
        min_rating=query.min_rating,
        sort_by=query.sort_by or "distance_asc",
    )


@router.get("/places/restaurants/nearby", response_model=PlacesSearchResult)
def get_restaurants_nearby_gps(
    lat: float = Query(..., description="User GPS Latitude"),
    lng: float = Query(..., description="User GPS Longitude"),
    radius_meters: int = Query(3000, description="Radius in meters"),
    cuisine: Optional[str] = Query(None, description="Preferred cuisine"),
    max_price: Optional[float] = Query(None, description="Max cost per person"),
):
    """Auto-fetch nearby restaurants and cafes based on live GPS coordinates."""
    cuisines_list = [cuisine] if cuisine else None
    return search_restaurants(
        lat=lat,
        lng=lng,
        radius_meters=radius_meters,
        cuisines=cuisines_list,
        max_price=max_price,
        sort_by="distance_asc",
    )


class RestaurantReservationRequest(BaseModel):
    restaurant_id: str
    party_size: int = Field(default=2, ge=1, le=20)
    reservation_time: str = Field("08:00 PM", description="Reservation time e.g. '08:00 PM'")
    guest_name: str
    guest_phone: str
    restaurant_name: Optional[str] = None
    restaurant_address: Optional[str] = None
    city: Optional[str] = None
    seating_preference: Optional[str] = None
    special_requests: Optional[str] = None


@router.post("/places/restaurants/reserve")
def reserve_restaurant_table_endpoint(payload: RestaurantReservationRequest):
    """Not implemented: no reservation provider is integrated."""
    raise HTTPException(status_code=501, detail="Table reservations are not available yet.")


@router.get("/places/restaurants/{place_id}", response_model=Dict[str, Any])
def get_restaurant_details_endpoint(place_id: str):
    """Restaurant details are not available: OpenStreetMap results carry no menu or booking data."""
    raise HTTPException(status_code=501, detail="Restaurant detail profiles are not available yet.")


# =============================================================
# 6. Monuments & Sightseeing Manual Exploration APIs
# =============================================================
@router.post("/places/attractions/search", response_model=PlacesSearchResult)
def search_attractions_endpoint(query: AttractionSearchQuery):
    """Manual attractions search by city, category, max entry ticket price, and rating."""
    if not query.city and (query.lat is None or query.lng is None):
        raise HTTPException(status_code=400, detail="Provide a city or lat/lng.")
    return search_attractions(
        city=query.city or "",
        category=query.category,
        max_entry_fee=query.max_entry_fee,
        lat=query.lat,
        lng=query.lng,
        radius_km=query.radius_km,
        sort_by=query.sort_by or "distance_asc",
    )


@router.get("/places/attractions/nearby", response_model=PlacesSearchResult)
def get_attractions_nearby_gps(
    lat: float = Query(..., description="User GPS Latitude"),
    lng: float = Query(..., description="User GPS Longitude"),
    city: str = Query("Delhi", description="Current city"),
    radius_km: float = Query(10.0, description="Radius in km"),
    max_entry_fee: Optional[float] = Query(None, description="Max entry fee in INR"),
):
    """Auto-fetch nearby monuments and viewpoints from user's live GPS coordinates."""
    return search_attractions(
        city=city,
        lat=lat,
        lng=lng,
        radius_km=radius_km,
        max_entry_fee=max_entry_fee,
        sort_by="distance_asc",
    )


@router.get("/places/attractions/{place_id}")
def get_attraction_details_endpoint(place_id: str):
    """Get rich history, photography tips, ticket prices, and opening hours for a monument."""
    return get_attraction_details(place_id=place_id)


# =============================================================
# 7. Live Events & Nightlife Manual Discovery APIs
# =============================================================
@router.get("/events/search")
def search_events_endpoint(
    city: str = Query("Delhi", description="City name"),
    category: Optional[str] = Query(None, description="music | comedy | festival | nightlife | art"),
    timeframe: str = Query("this week", description="today | tomorrow | this weekend | this week"),
    min_price: Optional[float] = Query(None, description="Minimum price"),
    max_price: Optional[float] = Query(None, description="Maximum price"),
    is_free: Optional[bool] = Query(None, description="Free entry only"),
    sort_by: Optional[str] = Query("popularity", description="popularity | price_asc | price_desc"),
):
    """Search live concerts, standup comedy, and nightlife with direct BookMyShow / Paytm Insider links."""
    return search_live_events_tool(
        city=city,
        category=category,
        timeframe=timeframe,
        min_price=min_price,
        max_price=max_price,
        is_free=is_free,
        sort_by=sort_by,
    )


@router.get("/events/nearby")
def get_events_nearby_gps(
    lat: float = Query(..., description="User GPS Latitude"),
    lng: float = Query(..., description="User GPS Longitude"),
    city: str = Query("Delhi", description="City name"),
    category: Optional[str] = Query(None, description="Filter category"),
):
    """Auto-fetch live events and gigs happening near user's GPS coordinates sorted by distance."""
    return search_live_events_tool(
        city=city,
        category=category,
        timeframe="today or this weekend",
        lat=lat,
        lng=lng,
        sort_by="distance_asc",
    )


# =============================================================
# 8. Unified Master "Explore Nearby" (All-in-One GPS Fetch)
# =============================================================
@router.get("/explore/nearby", response_model=NearbyExploreResult)
def explore_all_nearby_gps(
    lat: float = Query(..., description="User GPS Latitude"),
    lng: float = Query(..., description="User GPS Longitude"),
    city: str = Query("Delhi", description="City name"),
    radius_km: float = Query(5.0, description="Exploration radius in km"),
    check_in_date: Optional[str] = Query(None, description="YYYY-MM-DD for hotel pricing (defaults to tomorrow)"),
    check_out_date: Optional[str] = Query(None, description="YYYY-MM-DD (defaults to check-in + 2 nights)"),
):
    """Master All-in-One endpoint: fetches nearby Hotels, Restaurants, Monuments, and Live Events in 1 call!"""
    # 1. Nearby Hotels
    check_in_date, check_out_date = resolve_stay_dates(check_in_date, check_out_date)
    hotel_res = search_hotels(
        city=city,
        check_in_date=check_in_date,
        check_out_date=check_out_date,
        lat=lat,
        lng=lng,
        radius_km=radius_km,
        sort_by="distance_asc",
    )

    # 2. Nearby Restaurants & Cafes
    rest_res = search_restaurants(
        lat=lat,
        lng=lng,
        radius_meters=int(radius_km * 1000),
        sort_by="distance_asc",
        limit=6,
    )

    # 3. Nearby Monuments & Attractions
    attr_res = search_attractions(
        city=city,
        lat=lat,
        lng=lng,
        radius_km=radius_km,
        sort_by="distance_asc",
    )

    # 4. Nearby Live Events
    events_res = search_live_events_tool(
        city=city,
        timeframe="this week",
        lat=lat,
        lng=lng,
        sort_by="distance_asc",
    )

    total_count = (
        len(hotel_res.options)
        + len(rest_res.places)
        + len(attr_res.places)
        + len(events_res.get("events", []))
    )

    return NearbyExploreResult(
        center=GeoLocation(lat=lat, lng=lng),
        city=city.title(),
        radius_km=radius_km,
        total_nearby_items=total_count,
        hotels=[h.model_dump() for h in hotel_res.options[:5]],
        restaurants=rest_res.places[:6],
        attractions=attr_res.places[:5],
        live_events=events_res.get("events", [])[:4],
    )


# =============================================================
# 9. Clip2Trip: Social Reel to Itinerary
# =============================================================
class ReelExtractRequest(BaseModel):
    url: str = Field(..., description="Instagram Reel or YouTube Short URL")


@router.post("/reels/clip2trip")
def extract_reel_to_itinerary(payload: ReelExtractRequest):
    """Convert an Instagram Reel or YouTube Shorts URL into structured places, tips, and timestamps."""
    try:
        result = convert_reel_to_places(payload.url)
        return {
            "success": True,
            "data": result,
        }
    except UnsupportedUrlError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reel extraction failed: {str(e)}")


# =============================================================
# 10. Group Expense Split & Debt Simplification
# =============================================================
class GroupSplitRequest(BaseModel):
    expenses: List[ExpenseItem]


@router.post("/group-split/calculate", response_model=GroupBalanceSheet)
def calculate_group_split(payload: GroupSplitRequest):
    """Calculate net balances and minimum cash-flow debt settlements for a group trip."""
    try:
        return settle_group_expenses(payload.expenses)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Split calculation failed: {str(e)}")


# =============================================================
# 11. Complete Itinerary Package Booking & Checkout Hold
# =============================================================
@router.post("/booking/checkout", response_model=Dict[str, Any])
def create_booking_hold_and_checkout(req: CreateBookingHoldRequest):
    """Not implemented: package checkout needs real supplier holds and a server-side priced total.

    Use /flights/hold and /hotels/prebook, which call the suppliers.
    """
    raise HTTPException(
        status_code=501,
        detail="Package checkout is not implemented. Use /flights/hold and /hotels/prebook.",
    )


# =============================================================
# 12. Smart AI Tools & Superpowers Endpoints
# =============================================================
class FlightTradeoffRequest(BaseModel):
    flights: List[FlightOption]


@router.post("/tools/flights/tradeoffs")
def analyze_flight_tradeoffs_endpoint(payload: FlightTradeoffRequest):
    """Tool: Evaluates cheapest vs fastest, detects 2 AM red-eye cab surcharges, and spots time-shift savings."""
    return analyze_flight_tradeoffs(payload.flights)


class ClusterPlacesRequest(BaseModel):
    places: List[Dict[str, Any]]
    days_count: int = 2


@router.post("/tools/itinerary/cluster")
def cluster_places_endpoint(payload: ClusterPlacesRequest):
    """Tool: Zero-backtrack spatial clustering grouping spots into tight geographical days, saving ~90 mins of traffic."""
    return cluster_places_by_geography(payload.places, days_count=payload.days_count)


class EmergencyRerouteRequest(BaseModel):
    current_lat: float
    current_lng: float
    reason: str = Field("heavy_rain", description="'heavy_rain', 'monument_closed', 'too_hot', 'exhausted'")
    time_of_day: str = Field("03:30 PM", description="Current time")


@router.post("/tools/companion/reroute")
def emergency_reroute_endpoint(payload: EmergencyRerouteRequest):
    """Tool: Real-time on-the-ground weather / emergency rerouting with instant indoor & covered comfort pivots."""
    return get_emergency_reroute_options(
        current_lat=payload.current_lat,
        current_lng=payload.current_lng,
        reason=payload.reason,
        time_of_day=payload.time_of_day,
    )


class EventAnchoredRequest(BaseModel):
    event_query: str = Field(..., description="e.g. 'Zakir Khan Live' or 'Diljit Dosanjh'")
    city: str = Field(..., description="Destination city")
    origin_city: str = Field(..., description="Origin airport code")
    destination_airport: Optional[str] = Field(None, description="Destination airport code (needed to search flights)")
    departure_date: Optional[str] = Field(None, description="YYYY-MM-DD (defaults to tomorrow)")
    return_date: Optional[str] = Field(None, description="YYYY-MM-DD (defaults to departure + 2 days)")
    travelers: int = Field(2, ge=1)
    max_budget: Optional[float] = None


@router.post("/tools/planner/event-anchored")
def event_anchored_plan_endpoint(payload: EventAnchoredRequest):
    """Tool: Generates a complete weekend getaway anchored around an event, concert, or comedy show."""
    return create_event_anchored_plan(
        event_name_or_id=payload.event_query,
        city=payload.city,
        origin_city=payload.origin_city,
        destination_airport=payload.destination_airport,
        departure_date=payload.departure_date,
        return_date=payload.return_date,
        travelers=payload.travelers,
        max_budget=payload.max_budget,
    )


class GroupPaymentLinksRequest(BaseModel):
    expenses: List[Dict[str, Any]]
    upi_vpa: str = Field(..., description="UPI ID for settlements")


@router.post("/tools/group-split/payment-links")
def group_payment_links_endpoint(payload: GroupPaymentLinksRequest):
    """Tool: Generates direct clickable UPI deep-links, Razorpay links, and WhatsApp shareable messages for group debts."""
    return generate_group_settlement_links(
        expenses_raw=payload.expenses,
        upi_vpa_recipient=payload.upi_vpa,
    )


class TransportEstimateRequest(BaseModel):
    origin_lat: float
    origin_lng: float
    dest_lat: float
    dest_lng: float
    city: str = "Delhi"


@router.post("/tools/transport/estimate")
def estimate_transport_endpoint(payload: TransportEstimateRequest):
    """Tool: Estimates road distance, duration, Cab (Uber/Ola), Auto-rickshaw, and Metro fares."""
    return estimate_transport_options(
        origin_lat=payload.origin_lat,
        origin_lng=payload.origin_lng,
        dest_lat=payload.dest_lat,
        dest_lng=payload.dest_lng,
        city=payload.city,
    )


class PackingChecklistRequest(BaseModel):
    destination: str
    duration_days: int = 3
    travel_month: str = "November"
    interests: Optional[List[str]] = None


@router.post("/tools/packing/checklist")
def packing_checklist_endpoint(payload: PackingChecklistRequest):
    """Tool: Generates a smart, destination-aware and climate-aware packing checklist."""
    return generate_packing_checklist(
        destination=payload.destination,
        duration_days=payload.duration_days,
        travel_month=payload.travel_month,
        interests=payload.interests,
    )


@router.get("/tools/weather/forecast")
def weather_forecast_endpoint(
    city: str = Query(..., description="Destination city"),
):
    """Tool: Live 7-day forecast, sunrise/sunset, and photography golden hours."""
    return get_destination_weather_insights(city=city)


@router.get("/tools/currency/convert")
def currency_converter_endpoint(
    amount: float = Query(..., description="Amount to convert"),
    from_currency: str = Query(..., description="Base currency code e.g. USD, EUR, GBP, AED"),
    to_currency: str = Query(..., description="Target currency code"),
):
    """Tool: Currency converter using the latest published exchange rate."""
    return convert_currency(amount=amount, from_currency=from_currency, to_currency=to_currency)


# =============================================================================
# VDC-INHERITED FEATURE 1: Trip Share & Fork System
# =============================================================================

class ShareTripRequest(BaseModel):
    title: str = Field(..., description="Trip title e.g. 'Jaipur 3-Day Heritage & Food Tour'")
    destination: str
    origin: Optional[str] = "DEL"
    days: Optional[int] = 2
    budget_inr: Optional[float] = None
    itinerary: Optional[Dict[str, Any]] = None
    itinerary_data: Optional[Dict[str, Any]] = None
    creator_name: Optional[str] = "Traveler"


@router.post("/trips/share")
def share_trip_endpoint(payload: ShareTripRequest):
    """Generates an instant shareable trip code and URL from an itinerary."""
    from app.services.database_service import db_service
    itin = payload.itinerary or payload.itinerary_data or {}
    share_code = db_service.save_shared_trip(
        title=payload.title,
        destination=payload.destination,
        origin=payload.origin or "DEL",
        days=payload.days or 1,
        budget_inr=payload.budget_inr or 0.0,
        itinerary_data=itin,
        creator_name=payload.creator_name or "Traveler"
    )
    return {
        "status": "success",
        "share_code": share_code,
        "share_url": f"http://localhost:3000/?trip={share_code}",
        "message": "Trip successfully shared! Friends can view or fork this itinerary."
    }


@router.get("/trips/share/{share_code}")
def get_shared_trip_endpoint(share_code: str):
    """Retrieves a shared itinerary by share code."""
    from app.services.database_service import db_service
    trip = db_service.get_shared_trip(share_code)
    if not trip:
        raise HTTPException(status_code=404, detail="Shared trip not found or link has expired.")
    # Ensure both itinerary and itinerary_data keys exist
    if "itinerary" in trip and "itinerary_data" not in trip:
        trip["itinerary_data"] = trip["itinerary"]
    return trip


@router.post("/trips/share/{share_code}/fork")
def fork_shared_trip_endpoint(share_code: str):
    """Forks/clones a shared itinerary into the user's active planning session."""
    from app.services.database_service import db_service
    forked = db_service.fork_shared_trip(share_code)
    if not forked:
        raise HTTPException(status_code=404, detail="Shared trip not found.")
    return {
        "status": "forked",
        "message": f"Successfully forked '{forked['title']}'! You can now customize and adjust it.",
        "fork_count": forked.get("fork_count", 1),
        "itinerary": forked.get("itinerary", {}),
        "trip": forked
    }


# =============================================================================
# VDC-INHERITED FEATURE 2: Dual-Layer User Memory (Facts vs Recollections)
# =============================================================================

class UpsertMemoryFactRequest(BaseModel):
    topic: str = Field(..., description="Fact topic: 'diet' | 'budget_tier' | 'dining_vibe' | 'home_city'")
    content: str = Field(..., description="Authoritative fact content e.g. 'Pure Vegetarian'")
    layer: Optional[str] = "fact"


@router.get("/user/memory")
def get_user_memory_endpoint(
    user_id: Optional[str] = Query(None),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """Returns persistent facts and ranked recollections for the user session."""
    from app.services.database_service import db_service
    uid = user_id or x_session_id or "default_live_session"
    return db_service.get_user_memory(uid)


@router.post("/user/memory/fact")
def save_user_memory_fact_endpoint(
    payload: UpsertMemoryFactRequest,
    user_id: Optional[str] = Query(None),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """Explicitly stores a user fact into the authoritative truth layer."""
    from app.services.database_service import db_service
    uid = user_id or x_session_id or "default_live_session"
    db_service.upsert_user_memory(
        user_id=uid,
        layer=payload.layer or "fact",
        topic=payload.topic,
        content=payload.content,
        confidence=1.0,
        source="explicit"
    )
    return {"status": "saved", "user_id": uid, "topic": payload.topic, "content": payload.content}
