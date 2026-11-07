"""Flight Hold & Booking integration with TBO / Galileo."""
import json
import urllib.request
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.schemas.booking import PassengerDetail, GstDetails
from .auth import authenticate_tbo_air, get_server_public_ip

TBO_BOOK_URL = "https://api.tektravels.com/BookingEngineService_Air/AirService.svc/rest/Book"


def create_flight_hold(
    trace_id: str,
    result_index: str,
    passengers: List[PassengerDetail],
    gst: Optional[GstDetails] = None,
) -> Dict[str, Any]:
    """Places a fare hold / PNR reservation on TBO or Galileo."""
    token = authenticate_tbo_air()
    if not token:
        return {"status": "FAILED", "error": "Flight supplier is not configured or authentication failed"}

    # Format passengers for TBO Book API
    pax_payload = []
    for p in passengers:
        pax_payload.append({
            "Title": p.title.value,
            "FirstName": p.first_name,
            "LastName": p.last_name,
            "PaxType": 1,  # Adult
            "DateOfBirth": f"{p.date_of_birth}T00:00:00",
            "Gender": 1 if p.gender.value == "Male" else 2,
            "PAN": p.pan_number,
            "Email": p.email,
            "ContactNo": p.phone,
        })

    payload: Dict[str, Any] = {
        "EndUserIp": get_server_public_ip(),
        "TokenId": token,
        "TraceId": trace_id,
        "ResultIndex": result_index,
        "Passengers": pax_payload,
    }

    if gst:
        payload["GSTCompanyAddress"] = gst.company_address
        payload["GSTCompanyContactNumber"] = gst.company_email
        payload["GSTCompanyName"] = gst.company_name
        payload["GSTNumber"] = gst.gstin

    try:
        req = urllib.request.Request(
            TBO_BOOK_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            response_block = data.get("Response", {})
            return {
                "status": "HOLD_CONFIRMED" if response_block.get("PNR") else "FAILED",
                "pnr": response_block.get("PNR"),
                "booking_id": str(response_block.get("BookingId", "")),
                "is_ticketed": False,
                "raw_response": response_block,
            }
    except Exception as e:
        print(f"[FlightService:Hold] Flight booking hold failed: {e}")
        return {"status": "FAILED", "error": str(e)}
