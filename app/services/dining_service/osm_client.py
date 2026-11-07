"""OpenStreetMap (Overpass API) connector for cafes, restaurants and attractions."""
import hashlib
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.parse
import urllib.request
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

OSM_OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
OVERPASS_TIMEOUT_SECONDS = 15
# Fast-fail tuning: public mirrors are flaky. Mirrors are raced in parallel under one short deadline, successful answers are
# cached, and once every mirror has failed the circuit stays open for a while so a plan never waits on OSM again and again.
OVERPASS_DEADLINE_SECONDS = 8
OVERPASS_CACHE_TTL_SECONDS = 6 * 3600
OVERPASS_BREAKER_SECONDS = 180

_cache: Dict[str, Any] = {}
_breaker_until = 0.0
_cache_lock = threading.Lock()


def _fetch_mirror(url: str, data: bytes, timeout: float) -> List[Dict[str, Any]]:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "Plan4U-Travel-App/1.0"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8")).get("elements", [])


def run_overpass(overpass_query: str) -> List[Dict[str, Any]]:
    """Run an Overpass QL query across the public mirrors in parallel. Returns [] quickly if they all fail."""
    global _breaker_until
    key = hashlib.sha1(overpass_query.encode("utf-8")).hexdigest()
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
        if now < _breaker_until:
            return []
    data = urllib.parse.urlencode({"data": overpass_query}).encode("utf-8")
    pool = ThreadPoolExecutor(max_workers=len(OSM_OVERPASS_URLS))
    futures = {pool.submit(_fetch_mirror, u, data, OVERPASS_DEADLINE_SECONDS): u for u in OSM_OVERPASS_URLS}
    result: List[Dict[str, Any]] = []
    ok = False
    try:
        for fut in as_completed(futures, timeout=OVERPASS_DEADLINE_SECONDS + 1):
            try:
                result = fut.result()
                ok = True
                break
            except Exception as e:
                logger.warning("Overpass mirror %s failed: %s", futures[fut], e)
    except Exception:
        logger.warning("Overpass: no mirror answered within %ss", OVERPASS_DEADLINE_SECONDS)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    with _cache_lock:
        if ok:
            _cache[key] = (time.time() + OVERPASS_CACHE_TTL_SECONDS, result)
        else:
            _breaker_until = time.time() + OVERPASS_BREAKER_SECONDS
    return result


def element_coords(el: Dict[str, Any]):
    """Return (lat, lng) for an Overpass node or way/relation with a computed center."""
    lat = el.get("lat") or el.get("center", {}).get("lat")
    lng = el.get("lon") or el.get("center", {}).get("lon")
    return lat, lng


def query_osm_food_spots(
    lat: float,
    lng: float,
    radius_meters: int = 2000,
    amenity_tag: str = "restaurant",
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Free OpenStreetMap POI query without API keys."""
    overpass_query = f"""
    [out:json][timeout:{OVERPASS_TIMEOUT_SECONDS}];
    (
      node["amenity"="{amenity_tag}"](around:{radius_meters},{lat},{lng});
      way["amenity"="{amenity_tag}"](around:{radius_meters},{lat},{lng});
    );
    out center {limit};
    """

    places = []
    for el in run_overpass(overpass_query):
        tags = el.get("tags", {})
        name = tags.get("name")
        place_lat, place_lng = element_coords(el)
        if not name or place_lat is None or place_lng is None:
            continue
        cuisine = tags.get("cuisine", "").split(";") if tags.get("cuisine") else []
        street = " ".join(p for p in (tags.get("addr:housenumber"), tags.get("addr:street"), tags.get("addr:suburb")) if p)
        places.append({
            "id": f"osm_{el.get('id')}",
            "name": name,
            "lat": place_lat,
            "lng": place_lng,
            "cuisines": [c.strip().replace("_", " ").title() for c in cuisine if c.strip()],
            "opening_hours": tags.get("opening_hours"),
            "street": street,
            "phone": tags.get("phone") or tags.get("contact:phone"),
            "website": tags.get("website") or tags.get("contact:website"),
        })
    if not places:
        from app.services.fallback_catalog import food_spots
        return food_spots(lat, lng, amenity_tag, limit)
    return places[:limit]
