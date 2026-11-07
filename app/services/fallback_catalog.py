"""Offline fallback places (real OSM/Wikivoyage-derived listings, harvested once into app/data/*.json).

Used only when the live OpenStreetMap (Overpass) lookup returns nothing, so a plan never comes back empty because a
public mirror is down. Coverage: goa, kerala, jaipur, udaipur, ladakh, mumbai, delhi, bengaluru.
"""
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.schemas.attraction import GeoLocation, PlaceCategory, PlaceItem
from app.services.hotel_service.distance import haversine_distance_km

DATA = Path(__file__).resolve().parent.parent / "data"
ALIASES = {"kochi": "kerala", "cochin": "kerala", "munnar": "kerala", "alleppey": "kerala", "alappuzha": "kerala", "leh": "ladakh",
           "bangalore": "bengaluru", "new delhi": "delhi", "bombay": "mumbai", "panaji": "goa", "panjim": "goa", "calangute": "goa"}
HERITAGE = {"HISTORICAL", "RELIGIOUS", "MUSEUM"}


@lru_cache(maxsize=1)
def _load(name: str) -> Dict[str, List[Dict[str, Any]]]:
    try:
        return json.loads((DATA / f"{name}.json").read_text(encoding="utf8"))
    except (OSError, ValueError):
        return {}


def dest_id(city: str) -> Optional[str]:
    c = re.sub(r"[^a-z ]", "", (city or "").lower()).strip()
    c = ALIASES.get(c, c)
    return c if c in _load("attractions") else None


def _fee(price: Optional[str]) -> Optional[float]:
    if not price:
        return None
    if "free" in price.lower():
        return 0.0
    m = re.search(r"\d[\d,]*", price)
    return float(m.group(0).replace(",", "")) if m else None


def _ai_attractions(city: str, center: Optional[Dict[str, float]]) -> List[PlaceItem]:
    from app.services.llm_places import research_city
    data = research_city(city)
    out: List[PlaceItem] = []
    for i, a in enumerate((data or {}).get("attractions", [])):
        try:
            lat, lng = float(a["lat"]), float(a["lng"])
            kind = str(a.get("kind", "")).lower()
            cat = {"heritage": PlaceCategory.HERITAGE, "monument": PlaceCategory.MONUMENT, "beach": PlaceCategory.BEACH, "market": PlaceCategory.MARKET}.get(kind, PlaceCategory.ACTIVITY)
            c = center or (data.get("center") and {"lat": float(data["center"]["lat"]), "lng": float(data["center"]["lng"])})
            dist = int(haversine_distance_km(c["lat"], c["lng"], lat, lng) * 1000) if c else None
            out.append(PlaceItem(id=f"ai_{i}", name=str(a["name"]), category=cat, description=a.get("description"), address=city.title(),
                                 location=GeoLocation(lat=lat, lng=lng), distance_meters=dist, entry_fee=float(a["entry_fee_inr"]) if a.get("entry_fee_inr") is not None else None,
                                 recommended_duration_hours=float(a["duration_hours"]) if a.get("duration_hours") else None,
                                 best_time_slot=a.get("best_time"), source_provider="ai"))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def attractions(city: str, center: Optional[Dict[str, float]] = None, limit: int = 40) -> List[PlaceItem]:
    live = _ai_attractions(city, center)
    if live:
        return live
    d = dest_id(city)
    out: List[PlaceItem] = []
    for i, a in enumerate(_load("attractions").get(d or "", [])[:limit]):
        cat = PlaceCategory.HERITAGE if a.get("category") in HERITAGE else PlaceCategory.ACTIVITY
        dist = int(haversine_distance_km(center["lat"], center["lng"], a["lat"], a["lng"]) * 1000) if center else None
        out.append(PlaceItem(id=f"cat_{d}_{i}", name=a["name"], category=cat, description=a.get("description"), address=a.get("address") or "",
                             location=GeoLocation(lat=a["lat"], lng=a["lng"]), distance_meters=dist, entry_fee=_fee(a.get("price")),
                             opening_hours=a.get("hours"), photo_urls=[a["image"]] if a.get("image") else [], source_provider="catalog"))
    return out


def _nearest_dest(lat: float, lng: float) -> Optional[str]:
    best, best_d = None, 80.0
    for d, rows in _load("restaurants").items():
        pts = [(r["lat"], r["lng"]) for r in rows if r.get("lat") is not None]
        if not pts:
            continue
        clat, clng = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
        km = haversine_distance_km(lat, lng, clat, clng)
        if km < best_d:
            best, best_d = d, km
    return best


def food_spots(lat: float, lng: float, amenity_tag: str, limit: int) -> List[Dict[str, Any]]:
    """Same dict shape as osm_client.query_osm_food_spots."""
    from app.services.llm_places import nearest_city_data
    data = nearest_city_data(lat, lng)
    if data:
        rows = data.get("cafes" if amenity_tag == "cafe" else "restaurants", [])
        out = []
        for i, r in enumerate(rows):
            try:
                out.append({"id": f"ai_{amenity_tag}_{i}", "name": str(r["name"]), "lat": float(r["lat"]), "lng": float(r["lng"]),
                            "cuisines": [str(c) for c in r.get("cuisines", [])], "opening_hours": None, "street": str(r.get("area") or ""),
                            "phone": None, "website": None, "cost_per_person": r.get("cost_per_person_inr")})
            except (KeyError, TypeError, ValueError):
                continue
        out.sort(key=lambda r: haversine_distance_km(lat, lng, r["lat"], r["lng"]))
        if out:
            return out[: max(limit, 1)]
    d = _nearest_dest(lat, lng)
    kind = "cafe" if amenity_tag == "cafe" else "food"
    rows = [r for r in _load("restaurants").get(d or "", []) if r.get("kind") == kind and r.get("lat") is not None]
    rows.sort(key=lambda r: haversine_distance_km(lat, lng, r["lat"], r["lng"]))
    return [{"id": f"cat_{d}_{i}", "name": r["name"], "lat": r["lat"], "lng": r["lng"],
             "cuisines": [c.strip().replace("_", " ").title() for c in (r.get("cuisine") or "").split(";") if c.strip()],
             "opening_hours": r.get("hours"), "street": r.get("address") or "", "phone": None, "website": None} for i, r in enumerate(rows[: max(limit, 1)])]
