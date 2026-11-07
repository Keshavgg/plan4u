"""AI-facing flight search and quote tools."""
from typing import Optional, Dict, Any, List
from app.services.flight_service import (
    search_flights,
    quote_flight_fare,
    get_fare_rules,
)
from app.schemas.flight import FlightSearchQuery, FlightSearchResult, FlightOption


def search_flights_tool(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: Optional[str] = None,
    adult_count: int = 1,
    direct_flight_only: bool = False,
) -> Dict[str, Any]:
    """Search live flights between two airport IATA codes (e.g. DEL to GOI).
    
    Args:
        origin: 3-letter IATA code, e.g. 'DEL', 'BOM', 'BLR'
        destination: 3-letter IATA code, e.g. 'GOI', 'JAI', 'DXB'
        departure_date: Date in YYYY-MM-DD format
        return_date: Optional return date in YYYY-MM-DD
        adult_count: Number of adult passengers (>=1)
        direct_flight_only: If True, filters only non-stop flights
    """
    query = FlightSearchQuery(
        origin=origin.strip().upper(),
        destination=destination.strip().upper(),
        departure_date=departure_date,
        return_date=return_date,
        adult_count=adult_count,
        direct_flight_only=direct_flight_only,
    )
    res: FlightSearchResult = search_flights(
        origin=origin.strip().upper(),
        destination=destination.strip().upper(),
        departure_date=departure_date,
        return_date=return_date,
        adults=adult_count,
    )
    return {
        "success": True,
        "trace_id": res.trace_id,
        "flight_count": len(res.options),
        "flights": [f.model_dump() for f in res.options],
        "cheapest_price_inr": min([f.published_fare for f in res.options]) if res.options else 0,
    }


def quote_flight_fare_tool(trace_id: str, result_index: str) -> Dict[str, Any]:
    """Validate fare price freeze lock before booking.
    
    Args:
        trace_id: Active session TraceId from search_flights_tool
        result_index: ResultIndex of the chosen flight option
    """
    return quote_flight_fare(trace_id=trace_id, result_index=result_index)


def get_flight_fare_rules_tool(trace_id: str, result_index: str) -> Dict[str, Any]:
    """Fetch cancellation penalty bands and date-change rules for a flight.
    
    Args:
        trace_id: Active session TraceId from search_flights_tool
        result_index: ResultIndex of the chosen flight option
    """
    return get_fare_rules(trace_id=trace_id, result_index=result_index)
