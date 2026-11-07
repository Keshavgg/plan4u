"""FareQuote integration: verifies live price before booking/checkout."""
import json
import urllib.request
from typing import Dict, Any, Optional

from .auth import authenticate_tbo_air, get_server_public_ip

TBO_FARE_QUOTE_URL = "https://api.tektravels.com/BookingEngineService_Air/AirService.svc/rest/FareQuote"


def quote_flight_fare(trace_id: str, result_index: str) -> Dict[str, Any]:
    """Calls TBO FareQuote to re-validate fare, tax breakdown, and seat availability."""
    token = authenticate_tbo_air()
    if not token:
        return {"status": "error", "message": "Flight supplier is not configured or authentication failed", "is_price_changed": False}

    payload = {
        "EndUserIp": get_server_public_ip(),
        "TokenId": token,
        "TraceId": trace_id,
        "ResultIndex": result_index,
    }

    try:
        req = urllib.request.Request(
            TBO_FARE_QUOTE_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            response_block = data.get("Response", {})
            results = response_block.get("Results", {})
            fare = results.get("Fare", {})

            return {
                "status": "success" if response_block.get("Error", {}).get("ErrorCode") == 0 else "failed",
                "is_price_changed": results.get("IsPriceChanged", False),
                "published_fare": float(fare.get("PublishedPrice", 0.0)),
                "base_fare": float(fare.get("BaseFare", 0.0)),
                "tax": float(fare.get("Tax", 0.0)),
                "currency": fare.get("Currency", "INR"),
                "trace_id": trace_id,
                "result_index": result_index,
            }
    except Exception as e:
        print(f"[FlightService:FareQuote] FareQuote failed: {e}")
        return {"status": "error", "message": str(e), "is_price_changed": False}
