"""Intra-city and airport transport fare & time estimator (Cab, Auto, Metro)."""
from typing import Dict, Any, Optional
from app.services.hotel_service.distance import haversine_distance_km, estimate_walking_time_mins


def estimate_transport_options(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    city: str = "Delhi",
) -> Dict[str, Any]:
    """Computes realistic travel times and fares across Cab (Uber/Ola), Auto-rickshaw, Metro, and Walking."""
    straight_dist = haversine_distance_km(origin_lat, origin_lng, dest_lat, dest_lng)
    # Road distance is typically 1.35x straight line
    road_km = max(0.5, round(straight_dist * 1.35, 1))

    # Traffic speed assumption
    city_lower = city.lower()
    avg_speed_kmh = 22.0 if "delhi" in city_lower or "mumbai" in city_lower else 28.0
    drive_time_mins = max(5, int((road_km / avg_speed_kmh) * 60))

    # Auto fare calculation (Govt baseline in India: ₹30 base + ₹12/km)
    auto_fare = max(40, round(30 + (road_km - 1.5) * 12)) if road_km > 1.5 else 40

    # Cab fare calculation (UberGo / Ola Mini: ₹60 base + ₹16/km + time buffer)
    cab_fare = max(110, round(60 + road_km * 16 + drive_time_mins * 1.5))
    cab_premium = round(cab_fare * 1.4)

    # Metro recommendation
    metro_info = None
    if "delhi" in city_lower and road_km > 4.0:
        metro_info = {
            "available": True,
            "estimated_fare_inr": 40.0,
            "travel_time_mins": int(road_km * 2.2),
            "tip": "Delhi Metro runs every 3-5 minutes with AC comfort. Use DMRC smart card or QR ticket on WhatsApp.",
        }
    elif "jaipur" in city_lower and road_km > 3.0:
        metro_info = {
            "available": True,
            "estimated_fare_inr": 20.0,
            "travel_time_mins": 15,
            "tip": "Jaipur Pink Line connects Mansarovar to Badi Choupad (Hawa Mahal).",
        }

    # Walking option
    walk_mins = estimate_walking_time_mins(straight_dist)
    is_walkable = road_km <= 1.8

    return {
        "success": True,
        "city": city.title(),
        "road_distance_km": road_km,
        "estimated_drive_time_mins": drive_time_mins,
        "is_walkable": is_walkable,
        "walking_time_mins": walk_mins if is_walkable else None,
        "modes": [
            {
                "mode": "Cab (Uber / Ola Mini)",
                "estimated_fare_inr": cab_fare,
                "travel_time_mins": drive_time_mins,
                "notes": "Door-to-door AC comfort. Book directly on Uber/Ola.",
                "booking_url": "https://m.uber.com",
            },
            {
                "mode": "Auto-Rickshaw",
                "estimated_fare_inr": auto_fare,
                "travel_time_mins": drive_time_mins - 2,
                "notes": "Best for maneuvering tight city streets and lively local feel.",
            },
            {
                "mode": "City Metro",
                "available": bool(metro_info),
                "estimated_fare_inr": metro_info["estimated_fare_inr"] if metro_info else None,
                "notes": metro_info["tip"] if metro_info else "Metro not available on this direct sector.",
            },
        ],
    }
