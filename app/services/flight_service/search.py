"""Flight search integration calling TBO Air REST API."""
import json
import urllib.request
from typing import Optional, List

from app.schemas.flight import (
    FlightSearchQuery,
    FlightSearchResult,
    FlightOption,
    FlightProvider,
    FlightSegment,
)
from .auth import authenticate_tbo_air, get_server_public_ip, is_flight_api_configured
from .parser import parse_tbo_search_response

TBO_SEARCH_URL = "https://api.tektravels.com/BookingEngineService_Air/AirService.svc/rest/Search"


def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: Optional[str] = None,
    adults: int = 1,
    children: int = 0,
    infants: int = 0,
    cabin_class: str = "1",
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    airlines: Optional[List[str]] = None,
    max_stops: Optional[int] = None,
    is_refundable: Optional[bool] = None,
    departure_time_window: Optional[str] = None,
    sort_by: Optional[str] = "price_asc",
) -> FlightSearchResult:
    """Searches flights between two airport codes for given dates with optional MMT-style filters."""
    origin_code = origin.upper().strip()
    dest_code = destination.upper().strip()

    token = authenticate_tbo_air()
    result = None
    if token:
        live_result = _execute_live_search(
            token=token,
            origin=origin_code,
            destination=dest_code,
            dep_date=departure_date,
            adults=adults,
            children=children,
            infants=infants,
            cabin_class=cabin_class,
        )
        if live_result and live_result.options:
            result = live_result

    if not result:
        # No live supplier data: return an empty result, never invented flights.
        result = FlightSearchResult(
            origin=origin_code,
            destination=dest_code,
            departure_date=departure_date,
            provider=FlightProvider.TBO,
            options=[],
            total_found=0,
        )

    # Apply manual filters and sorting
    return _apply_flight_filters_and_sorting(
        result=result,
        min_price=min_price,
        max_price=max_price,
        airlines=airlines,
        max_stops=max_stops,
        is_refundable=is_refundable,
        departure_time_window=departure_time_window,
        sort_by=sort_by,
    )


def _apply_flight_filters_and_sorting(
    result: FlightSearchResult,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    airlines: Optional[List[str]] = None,
    max_stops: Optional[int] = None,
    is_refundable: Optional[bool] = None,
    departure_time_window: Optional[str] = None,
    sort_by: Optional[str] = "price_asc",
) -> FlightSearchResult:
    filtered = list(result.options)

    if min_price is not None:
        filtered = [f for f in filtered if f.published_fare >= min_price]
    if max_price is not None:
        filtered = [f for f in filtered if f.published_fare <= max_price]
    if airlines:
        airline_set = {a.upper().strip() for a in airlines}
        filtered = [
            f for f in filtered
            if f.airline_code.upper() in airline_set or any(a in f.airline_name.upper() for a in airline_set)
        ]
    if max_stops is not None:
        filtered = [f for f in filtered if f.stops <= max_stops]
    if is_refundable is not None:
        filtered = [f for f in filtered if f.is_refundable == is_refundable]
    if departure_time_window:
        def match_window(dep_str: str, window: str) -> bool:
            try:
                hour = int(dep_str.split("T")[1][:2])
                if window == "early_morning":
                    return 0 <= hour < 6
                if window == "morning":
                    return 6 <= hour < 12
                if window == "afternoon":
                    return 12 <= hour < 18
                if window == "evening":
                    return 18 <= hour <= 23
            except Exception:
                return True
            return True

        filtered = [f for f in filtered if match_window(f.departure_time, departure_time_window.lower())]

    # Sorting
    def parse_dur(d_str: str) -> int:
        tot = 0
        for p in d_str.split():
            if p.endswith("h"):
                tot += int(p[:-1]) * 60
            elif p.endswith("m"):
                tot += int(p[:-1])
        return tot or 9999

    if sort_by == "price_desc":
        filtered.sort(key=lambda x: x.published_fare, reverse=True)
    elif sort_by == "duration_asc":
        filtered.sort(key=lambda x: parse_dur(x.total_duration))
    elif sort_by == "departure_asc":
        filtered.sort(key=lambda x: x.departure_time)
    else:  # price_asc default
        filtered.sort(key=lambda x: x.published_fare)

    result.options = filtered
    result.total_found = len(filtered)
    return result


def _execute_live_search(
    token: str,
    origin: str,
    destination: str,
    dep_date: str,
    adults: int,
    children: int,
    infants: int,
    cabin_class: str,
) -> Optional[FlightSearchResult]:
    """Sends JSON POST request to TBO Air Search endpoint."""
    payload = {
        "EndUserIp": get_server_public_ip(),
        "TokenId": token,
        "AdultCount": str(adults),
        "ChildCount": str(children),
        "InfantCount": str(infants),
        "DirectFlight": "false",
        "OneStopFlight": "false",
        "JourneyType": "1",
        "PreferredAirlines": None,
        "Segments": [
            {
                "Origin": origin,
                "Destination": destination,
                "FlightCabinClass": cabin_class,
                "PreferredDepartureTime": f"{dep_date}T00:00:00",
            }
        ],
        "Sources": None,
    }

    try:
        req = urllib.request.Request(
            TBO_SEARCH_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw_data = json.loads(resp.read().decode("utf-8"))
            return parse_tbo_search_response(raw_data, origin, destination, dep_date)
    except Exception as e:
        print(f"[FlightService:Search] Live search failed: {e}")
        return None
