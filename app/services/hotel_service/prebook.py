"""Pre-booking integration to lock hotel room and verify live pricing before checkout."""
import json
import urllib.request
from typing import Dict, Any

from .auth import authenticate_tbo_hotel, get_hotel_outbound_ip

TBO_PREBOOK_URL = "https://HotelBE.tektravels.com/hotelservice.svc/rest/PreBook/"


def prebook_hotel(
    hotel_code: str,
    booking_code: str,
    room_index: int = 1,
) -> Dict[str, Any]:
    """Locks hotel room and verifies price hasn't surged before checkout."""
    token = authenticate_tbo_hotel()
    if not token:
        return {"status": "FAILED", "error": "Hotel supplier is not configured or authentication failed"}

    payload = {
        "TokenId": token,
        "EndUserIp": get_hotel_outbound_ip(),
        "BookingCode": booking_code,
    }

    try:
        req = urllib.request.Request(
            TBO_PREBOOK_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "status": "PREBOOK_CONFIRMED" if data.get("Status") == 1 else "FAILED",
                "is_price_changed": data.get("IsPriceChanged", False),
                "hotel_code": hotel_code,
                "raw_response": data,
            }
    except Exception as e:
        print(f"[HotelService:PreBook] PreBook error: {e}")
        return {"status": "FAILED", "error": str(e)}
