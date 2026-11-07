"""Fetches comprehensive hotel info, photo gallery, and room options from TBO."""
import json
import urllib.request
from typing import Dict, Any, Optional

from .auth import authenticate_tbo_hotel, get_hotel_outbound_ip

TBO_HOTEL_DETAILS_URL = "https://HotelBE.tektravels.com/hotelservice.svc/rest/GetHotelDetails/"


def get_hotel_details(hotel_code: str) -> Dict[str, Any]:
    """Retrieves full hotel photos, amenities, and room categories from TBO."""
    token = authenticate_tbo_hotel()
    if not token:
        return {"hotel_code": hotel_code, "photos": [], "amenities": []}

    payload = {
        "TokenId": token,
        "EndUserIp": get_hotel_outbound_ip(),
        "HotelCode": hotel_code,
    }

    try:
        req = urllib.request.Request(
            TBO_HOTEL_DETAILS_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            details = data.get("HotelDetails", {})
            return {
                "hotel_code": hotel_code,
                "description": details.get("Description", ""),
                "photos": details.get("Images", []),
                "amenities": details.get("HotelFacilities", []),
                "check_in_time": details.get("CheckInTime", "14:00"),
                "check_out_time": details.get("CheckOutTime", "11:00"),
            }
    except Exception as e:
        print(f"[HotelService:Details] Details fetch error: {e}")
        return {"hotel_code": hotel_code, "photos": [], "amenities": []}
