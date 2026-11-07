"""Bridge to the Tripora FastAPI service (backend-py): its flight and hotel catalogues feed the planner when no
supplier (TBO / Galileo) is configured, so the AI plan always includes a flight and a stay.

TRIPORA_API_URL (default http://localhost:8787). Everything fails soft: on any error the agents see "no results", as before.
"""
import json
import logging
import os
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
BASE = os.getenv("TRIPORA_API_URL", "http://localhost:8787").rstrip("/")
TOKEN = os.getenv("TRIPORA_APP_TOKEN", "")
TIMEOUT = 15

# name -> (IATA, lat, lng)
CITIES: Dict[str, tuple] = {
    "mumbai": ("BOM", 19.0760, 72.8777), "delhi": ("DEL", 28.6139, 77.2090), "new delhi": ("DEL", 28.6139, 77.2090),
    "bengaluru": ("BLR", 12.9716, 77.5946), "bangalore": ("BLR", 12.9716, 77.5946), "goa": ("GOI", 15.4909, 73.8278),
    "jaipur": ("JAI", 26.9124, 75.7873), "udaipur": ("UDR", 24.5854, 73.7125), "kochi": ("COK", 9.9312, 76.2673),
    "kerala": ("COK", 9.9312, 76.2673), "hyderabad": ("HYD", 17.3850, 78.4867), "chennai": ("MAA", 13.0827, 80.2707),
    "kolkata": ("CCU", 22.5726, 88.3639), "pune": ("PNQ", 18.5204, 73.8567), "ahmedabad": ("AMD", 23.0225, 72.5714),
    "leh": ("IXL", 34.1526, 77.5770), "ladakh": ("IXL", 34.1526, 77.5770), "manali": ("KUU", 32.2396, 77.1887),
    "varanasi": ("VNS", 25.3176, 82.9739), "amritsar": ("ATQ", 31.6340, 74.8723), "srinagar": ("SXR", 34.0837, 74.7973),
    "dubai": ("DXB", 25.2048, 55.2708), "bali": ("DPS", -8.4095, 115.1889), "singapore": ("SIN", 1.3521, 103.8198),
    "bangkok": ("BKK", 13.7563, 100.5018), "kyoto": ("KIX", 35.0116, 135.7681), "tokyo": ("HND", 35.6762, 139.6503),
    "lisbon": ("LIS", 38.7223, -9.1393), "santorini": ("JTR", 36.3932, 25.4615), "london": ("LHR", 51.5072, -0.1276),
    "paris": ("CDG", 48.8566, 2.3522), "rishikesh": ("DED", 30.0869, 78.2676), "shimla": ("IXC", 31.1048, 77.1734),
}


def city_info(name: str) -> Optional[tuple]:
    key = re.sub(r"[^a-z ]", "", (name or "").lower()).strip()
    if key in CITIES:
        return CITIES[key]
    if len(key) == 3:  # already an IATA code
        for v in CITIES.values():
            if v[0].lower() == key:
                return v
    return None


def _get(path: str, params: Dict[str, Any]) -> Optional[dict]:
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    headers = {"User-Agent": "Plan4U-Bridge/1.0"}
    if TOKEN:
        headers["x-tripora-app-token"] = TOKEN
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        logger.warning("mock_bridge %s failed: %s", path, e)
        return None


def _hm(iso: Optional[str]) -> str:
    return iso[11:16] if iso and len(iso) >= 16 else ""


def _dur(m: Optional[int]) -> str:
    return f"{m // 60}h {m % 60:02d}m" if m else ""


LCC = {"6E", "SG", "QP", "IX", "I5", "G8"}


def flights(origin: str, destination: str, depart: str, ret: Optional[str], adults: int) -> List[Dict[str, Any]]:
    o, d = city_info(origin), city_info(destination)
    if not o or not d or o[0] == d[0]:
        return []
    params = {"from": o[0], "to": d[0], "date": depart, "adults": max(1, adults), "limit": 12}
    if ret:
        params["returnDate"] = ret
    body = _get("/v1/flights/search", params)
    out: List[Dict[str, Any]] = []
    for off in (body or {}).get("offers", []):
        sl = (off.get("slices") or [{}])[0]
        segs = sl.get("segments") or []
        if not segs:
            continue
        code = (off.get("airline") or {}).get("code") or segs[0].get("carrier") or ""
        name = (off.get("airline") or {}).get("name") or segs[0].get("carrierName") or code
        total = (off.get("totalFare") or {}).get("amount", 0)
        out.append({
            "id": f"bridge_{off['id']}", "provider": "mock", "airline_name": name, "airline_code": code, "is_lcc": code in LCC,
            "is_refundable": bool(off.get("refundable")), "origin": o[0], "destination": d[0],
            "departure_time": (segs[0].get("departAt") or ""), "arrival_time": (segs[-1].get("arriveAt") or ""),
            "total_duration": _dur(sl.get("durationMinutes")), "stops": max(0, len(segs) - 1),
            "segments": [{
                "airline_code": s.get("carrier") or code, "airline_name": s.get("carrierName") or name,
                "flight_number": f"{s.get('carrier') or code}-{s.get('flightNumber', '')}".strip("-"),
                "origin": s.get("from"), "destination": s.get("to"), "departure_time": (s.get("departAt") or ""),
                "arrival_time": (s.get("arriveAt") or ""), "duration": _dur(s.get("durationMinutes"))} for s in segs],
            "base_fare": float((off.get("baseFare") or {}).get("amount", 0)),
            "taxes_and_surcharges": float((off.get("taxes") or {}).get("amount", 0)),
            "published_fare": float(total), "checkin_baggage": off.get("checkedBaggage") or "15 Kg",
        })
    return out


def hotels(city: str, check_in: str, check_out: str, rooms: int, adults: int) -> List[Dict[str, Any]]:
    c = city_info(city)
    if not c:
        return []
    body = _get("/v1/hotels/search", {"lat": c[1], "lng": c[2], "checkIn": check_in, "checkOut": check_out, "rooms": max(1, rooms), "limit": 12})
    out: List[Dict[str, Any]] = []
    for off in (body or {}).get("offers", []):
        h = off.get("hotel") or {}
        ppn = float((off.get("pricePerNight") or {}).get("amount", 0))
        total = float((off.get("totalPrice") or {}).get("amount", 0))
        imgs = h.get("images") or []
        out.append({
            "id": f"bridge_{off['id']}", "provider": "mock", "hotel_code": str(h.get("id", off["id"])), "name": h.get("name", "Hotel"),
            "star_rating": int(h.get("starRating") or 3), "trip_advisor_rating": h.get("guestRating"), "review_count": int(h.get("reviewCount") or 0),
            "address": h.get("address") or city.title(), "city": city.title(),
            "latitude": (h.get("location") or {}).get("lat"), "longitude": (h.get("location") or {}).get("lng"),
            "min_price_per_night": ppn, "total_estimated_price": total or ppn * max(1, off.get("nights") or 1),
            "rooms": [{"room_type_name": off.get("roomName") or "Standard Room", "is_refundable": bool(off.get("refundable")),
                       "price_per_night": ppn, "total_fare": total, "amenities": h.get("amenities", [])[:6]}],
            "featured_image": imgs[0] if imgs else None, "photo_urls": imgs, "amenities": h.get("amenities", []),
            "hotel_description": h.get("propertyType"),
        })
    return out
