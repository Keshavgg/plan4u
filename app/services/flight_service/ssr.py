"""SSR (Special Service Request): Seat maps, baggage, and meal add-ons."""
import json
import urllib.request
from typing import Dict, Any, List

from .auth import authenticate_tbo_air, get_server_public_ip

TBO_SSR_URL = "https://api.tektravels.com/BookingEngineService_Air/AirService.svc/rest/SSR"


def get_flight_ssr(trace_id: str, result_index: str) -> Dict[str, Any]:
    """Fetches seat map, baggage options, and meal selections for the selected flight."""
    token = authenticate_tbo_air()
    if not token:
        return {
            "meals": [],
            "extra_baggage": [],
            "seat_map_available": False,
            "error": "Flight supplier is not configured or authentication failed",
        }

    payload = {
        "EndUserIp": get_server_public_ip(),
        "TokenId": token,
        "TraceId": trace_id,
        "ResultIndex": result_index,
    }

    try:
        req = urllib.request.Request(
            TBO_SSR_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            response_block = data.get("Response", {})
            
            # Extract meal and baggage arrays
            meals = response_block.get("MealDynamic", [[]])[0] if response_block.get("MealDynamic") else []
            baggage = response_block.get("Baggage", [[]])[0] if response_block.get("Baggage") else []
            
            return {
                "meals": [{"code": m.get("Code"), "description": m.get("AirlineDescription"), "price": m.get("Price")} for m in meals],
                "extra_baggage": [{"weight_kg": b.get("Weight"), "price": b.get("Price")} for b in baggage],
                "seat_map_available": bool(response_block.get("SeatDynamic")),
            }
    except Exception as e:
        print(f"[FlightService:SSR] SSR fetch failed: {e}")
        return {"meals": [], "extra_baggage": [], "seat_map_available": False}
