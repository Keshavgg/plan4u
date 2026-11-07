"""City-wide hotel search calling TBO Hotel API."""
import json
import urllib.request
from typing import Optional, List, Dict, Any
from datetime import datetime

from app.schemas.hotel import (
    HotelSearchResult,
    HotelOption,
    HotelProvider,
    HotelRoom,
    MealType,
    CancellationPolicyBand,
)
from .auth import authenticate_tbo_hotel, get_hotel_outbound_ip
from .parser import parse_tbo_hotel_response

TBO_HOTEL_SEARCH_URL = "https://HotelBE.tektravels.com/hotelservice.svc/rest/GetHotelResult/"

# Pre-mapped TBO City Codes for top destinations
TBO_CITY_CODES: Dict[str, str] = {
    "goa": "111812",
    "delhi": "130443",
    "jaipur": "116035",
    "mumbai": "144306",
    "bengaluru": "111124",
    "bangalore": "111124",
    "agra": "100147",
    "udaipur": "142106",
    "manali": "129845",
    "shimla": "139115",
    "varanasi": "143004",
    "kerala": "120800",
    "kochi": "120800",
}


def search_hotels(
    city: str,
    check_in_date: str,
    check_out_date: str,
    rooms: int = 1,
    adults: int = 2,
    min_rating: float = 3.5,
    min_star_rating: Optional[int] = None,
    min_price: Optional[float] = None,
    max_budget_per_night: Optional[float] = None,
    preferred_amenities: Optional[List[str]] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius_km: Optional[float] = None,
    sort_by: Optional[str] = "price_asc",
) -> HotelSearchResult:
    """Searches hotels in a destination city with comprehensive location, price, and amenity filters."""
    normalized_city = city.lower().strip()
    city_code = TBO_CITY_CODES.get(normalized_city, "111812")

    token = authenticate_tbo_hotel()
    result = None
    if token:
        live_result = _execute_live_hotel_search(
            token=token,
            city_code=city_code,
            city_name=city,
            check_in=check_in_date,
            check_out=check_out_date,
            rooms=rooms,
            adults=adults,
        )
        if live_result and live_result.options:
            result = live_result

    if not result:
        # No live supplier data: return an empty result, never invented hotels.
        result = HotelSearchResult(
            city=city.title(),
            check_in_date=check_in_date,
            check_out_date=check_out_date,
            provider=HotelProvider.TBO,
            options=[],
            total_found=0,
        )

    # Apply manual filters and sorting
    return _apply_hotel_filters_and_sorting(
        result=result,
        min_star_rating=min_star_rating,
        min_price=min_price,
        max_price=max_budget_per_night,
        preferred_amenities=preferred_amenities,
        lat=lat,
        lng=lng,
        radius_km=radius_km,
        sort_by=sort_by,
    )


def _apply_hotel_filters_and_sorting(
    result: HotelSearchResult,
    min_star_rating: Optional[int] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    preferred_amenities: Optional[List[str]] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius_km: Optional[float] = None,
    sort_by: Optional[str] = "price_asc",
) -> HotelSearchResult:
    from .distance import haversine_distance_km

    filtered = list(result.options)

    if min_star_rating is not None:
        filtered = [h for h in filtered if h.star_rating >= min_star_rating]
    if min_price is not None:
        filtered = [h for h in filtered if h.min_price_per_night >= min_price]
    if max_price is not None:
        filtered = [h for h in filtered if h.min_price_per_night <= max_price]
    if preferred_amenities:
        amenity_set = {a.lower().strip() for a in preferred_amenities}
        filtered = [
            h for h in filtered
            if any(any(req in (am.lower()) for req in amenity_set) for am in h.amenities)
        ]

    # Location / Coordinate Proximity Filtering
    if lat is not None and lng is not None:
        for h in filtered:
            if h.latitude and h.longitude:
                dist = haversine_distance_km(lat, lng, h.latitude, h.longitude)
                setattr(h, "_distance_km", dist)
            else:
                setattr(h, "_distance_km", 999.0)

        if radius_km is not None:
            filtered = [h for h in filtered if getattr(h, "_distance_km", 999.0) <= radius_km]

    # Sorting
    if sort_by == "price_desc":
        filtered.sort(key=lambda x: x.min_price_per_night, reverse=True)
    elif sort_by == "rating_desc":
        filtered.sort(key=lambda x: (x.trip_advisor_rating or x.star_rating), reverse=True)
    elif sort_by == "distance_asc" and lat is not None and lng is not None:
        filtered.sort(key=lambda x: getattr(x, "_distance_km", 999.0))
    else:  # price_asc default
        filtered.sort(key=lambda x: x.min_price_per_night)

    result.options = filtered
    result.total_found = len(filtered)
    return result


def _execute_live_hotel_search(
    token: str,
    city_code: str,
    city_name: str,
    check_in: str,
    check_out: str,
    rooms: int,
    adults: int,
) -> Optional[HotelSearchResult]:
    """Posts JSON request to TBO GetHotelResult endpoint."""
    try:
        d_in = datetime.strptime(check_in, "%Y-%m-%d").strftime("%d/%m/%Y")
        d_out = datetime.strptime(check_out, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        d_in, d_out = "15/11/2026", "18/11/2026"

    payload = {
        "TokenId": token,
        "EndUserIp": get_hotel_outbound_ip(),
        "CheckInDate": d_in,
        "CheckOutDate": d_out,
        "CountryName": "India",
        "CityId": city_code,
        "CityName": city_name,
        "GuestNationality": "IN",
        "PreferredCurrency": "INR",
        "NoOfRooms": rooms,
        "RoomGuests": [{"NoOfAdults": adults, "NoOfChild": 0, "ChildAge": []}],
        "MaxResult": 25,
        "OrderBy": "PriceAsc",
        "StarRating": "All",
    }

    try:
        req = urllib.request.Request(
            TBO_HOTEL_SEARCH_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return parse_tbo_hotel_response(data, city_name, check_in, check_out)
    except Exception as e:
        print(f"[HotelService:Search] Live search failed: {e}")
        return None
