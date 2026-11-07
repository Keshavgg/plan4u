"""Live place research with the AI engine (Claude, then Gemini), used when OpenStreetMap returns nothing.

One call per city returns real, named attractions, restaurants and cafes with coordinates, fees and costs. Results are
cached for 24 hours. Callers fall back to the offline catalog only if the AI engine is unavailable or answers badly.
"""
import json
import logging
import re
import threading
import time
from typing import Any, Dict, List, Optional

from app.services.hotel_service.distance import haversine_distance_km

logger = logging.getLogger(__name__)
TTL = 24 * 3600
_cache: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()

PROMPT = """You are a local travel researcher. For the city "{city}", list REAL, currently existing places that a visitor would genuinely go to.
Return ONLY a JSON object (no prose, no markdown) with exactly these keys:
{{"center": {{"lat": number, "lng": number}},
 "attractions": [ {{"name": str, "kind": "monument|heritage|beach|market|activity", "lat": number, "lng": number, "entry_fee_inr": number, "description": str, "best_time": str, "duration_hours": number}} ],
 "restaurants": [ {{"name": str, "cuisines": [str], "lat": number, "lng": number, "cost_per_person_inr": number, "area": str}} ],
 "cafes": [ {{"name": str, "cuisines": [str], "lat": number, "lng": number, "cost_per_person_inr": number, "area": str}} ]}}
Give 10 attractions, 6 restaurants and 4 cafes. Keep descriptions under 12 words. Use accurate coordinates (4+ decimals) and realistic INR prices; 0 for free entry. Only places you are confident exist."""


def _extract_json(text: str) -> Optional[dict]:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except ValueError:
        return None


def _valid(d: Optional[dict]) -> bool:
    return bool(d and isinstance(d.get("attractions"), list) and d["attractions"] and isinstance(d.get("center"), dict))


def research_city(city: str) -> Optional[Dict[str, Any]]:
    key = (city or "").strip().lower()
    if not key:
        return None
    with _lock:
        hit = _cache.get(key)
        if hit and hit["until"] > time.time():
            return hit["data"]
    data = None
    for attempt in range(2):
        try:
            from app.agent.subagents.copilot_agent import call_ai_engine
            text = call_ai_engine(PROMPT.format(city=city), system_prompt="You output strictly valid JSON and nothing else.")
        except Exception as e:  # noqa: BLE001
            logger.warning("llm_places: AI engine failed for %s: %s", city, e)
            return None
        data = _extract_json(text or "")
        if _valid(data):
            break
        logger.warning("llm_places: unusable answer for %s (attempt %d)", city, attempt + 1)
    if not _valid(data):
        return None
    with _lock:
        _cache[key] = {"until": time.time() + TTL, "data": data}
    return data


def nearest_city_data(lat: float, lng: float, max_km: float = 60.0) -> Optional[Dict[str, Any]]:
    with _lock:
        entries = [e["data"] for e in _cache.values() if e["until"] > time.time()]
    best, best_km = None, max_km
    for d in entries:
        c = d.get("center") or {}
        try:
            km = haversine_distance_km(lat, lng, float(c["lat"]), float(c["lng"]))
        except (KeyError, TypeError, ValueError):
            continue
        if km < best_km:
            best, best_km = d, km
    return best
