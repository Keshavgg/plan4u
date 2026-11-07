"""Real-time Geolocation & Reverse Geocoding Service for Plan4U Live Copilot.
Resolves GPS coordinates into authentic Indian localities, landmarks, and cities.
Includes memory caching and offline fallback.
"""
import json
import math
import time
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional

# In-memory cache for fast lookups (<100m grid)
GEO_CACHE: Dict[str, Dict[str, Any]] = {}


def reverse_geocode_coords(lat: float, lng: float) -> Dict[str, Any]:
    """Reverse geocodes latitude and longitude into locality and city using dynamic OSM Nominatim API (Zero static data)."""
    # Round to ~100m grid for caching
    cache_key = f"{round(lat, 3)}:{round(lng, 3)}"
    if cache_key in GEO_CACHE:
        entry = GEO_CACHE[cache_key]
        if time.time() - entry.get("timestamp", 0) < 86400:  # 24h cache
            return entry.get("data", {})

    url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lng}&format=json"
    req = urllib.request.Request(url, headers={"User-Agent": "Plan4U-App/1.0 (travel@plan4u.ai)"})

    try:
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            addr = data.get("address", {})

            # 1. Extract clean locality
            neighbourhood = addr.get("neighbourhood") or ""
            suburb = addr.get("suburb") or addr.get("quarter") or addr.get("residential") or ""
            town = addr.get("town") or addr.get("village") or addr.get("subdistrict") or ""
            road = addr.get("road") or ""

            locality = suburb or neighbourhood or town or road or "Local Area"
            if neighbourhood and suburb and neighbourhood != suburb:
                locality = f"{neighbourhood}, {suburb}"

            # 2. Extract and standardize city
            raw_city = addr.get("city") or addr.get("state_district") or addr.get("state") or ""
            raw_state = str(addr.get("state", "")).lower()

            if "delhi" in raw_state or "new delhi" in raw_city.lower():
                city = "Delhi"
            elif "goa" in raw_state or "goa" in raw_city.lower():
                city = "Goa"
            elif "mumbai" in raw_city.lower() or "bombay" in raw_city.lower():
                city = "Mumbai"
            elif "jaipur" in raw_city.lower():
                city = "Jaipur"
            elif "bengaluru" in raw_city.lower() or "bangalore" in raw_city.lower():
                city = "Bengaluru"
            elif "hyderabad" in raw_city.lower():
                city = "Hyderabad"
            elif "kolkata" in raw_city.lower() or "calcutta" in raw_city.lower():
                city = "Kolkata"
            elif "chennai" in raw_city.lower() or "madras" in raw_city.lower():
                city = "Chennai"
            elif "agra" in raw_city.lower():
                city = "Agra"
            elif "udaipur" in raw_city.lower():
                city = "Udaipur"
            elif "kochi" in raw_city.lower() or "cochin" in raw_city.lower():
                city = "Kochi"
            else:
                city = raw_city

            display_name = f"{locality}, {city}"

            res = {
                "city": city,
                "locality": locality,
                "display_name": display_name,
                "postcode": addr.get("postcode", ""),
                "state": addr.get("state", ""),
                "lat": lat,
                "lng": lng,
                "source": "osm_nominatim_live"
            }

            GEO_CACHE[cache_key] = {"timestamp": time.time(), "data": res}
            return res

    except Exception as e:
        print(f"[LocationService] Dynamic geocode fallback: {e}")
        res = {
            "city": "Current City",
            "locality": f"Coordinates ({lat:.4f}, {lng:.4f})",
            "display_name": f"GPS Position ({lat:.4f}, {lng:.4f})",
            "lat": lat,
            "lng": lng,
            "source": "live_gps"
        }
        return res


GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"


def geocode_city(city: str) -> Optional[Dict[str, float]]:
    """Resolve a city name to coordinates via Open-Meteo geocoding. Returns None if not found."""
    key = f"city:{city.lower().strip()}"
    cached = GEO_CACHE.get(key)
    if cached and time.time() - cached.get("timestamp", 0) < 86400 * 30:
        return cached["data"]
    try:
        url = f"{GEOCODE_URL}?{urllib.parse.urlencode({'name': city, 'count': 1, 'language': 'en', 'format': 'json'})}"
        req = urllib.request.Request(url, headers={"User-Agent": "Plan4U-App/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            results = json.loads(resp.read().decode("utf-8")).get("results") or []
        if not results:
            return None
        coords = {"lat": results[0]["latitude"], "lng": results[0]["longitude"]}
        GEO_CACHE[key] = {"timestamp": time.time(), "data": coords}
        return coords
    except Exception as e:
        print(f"[LocationService] City geocode failed for {city!r}: {e}")
        return None
