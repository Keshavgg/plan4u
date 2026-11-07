"""Proximity search finding hotels near monuments and landmarks."""
from typing import List, Dict, Any

from .search import search_hotels
from .distance import haversine_distance_km, format_distance_label, estimate_walking_time_mins


def search_hotels_near_location(
    city: str,
    target_lat: float,
    target_lng: float,
    check_in_date: str,
    check_out_date: str,
    max_radius_km: float = 5.0,
    min_rating: float = 3.5,
) -> List[Dict[str, Any]]:
    """Filters and sorts city hotels based on proximity to a monument or coordinates."""
    search_res = search_hotels(
        city=city,
        check_in_date=check_in_date,
        check_out_date=check_out_date,
        min_rating=min_rating,
    )

    hotels_with_distance = []
    for h in search_res.options:
        if h.latitude is not None and h.longitude is not None:
            dist = haversine_distance_km(target_lat, target_lng, h.latitude, h.longitude)
            if dist <= max_radius_km:
                hotels_with_distance.append({
                    "hotel": h,
                    "distance_km": dist,
                    "walking_time_mins": estimate_walking_time_mins(dist),
                    "distance_label": format_distance_label(dist),
                })

    # Sort nearest first
    hotels_with_distance.sort(key=lambda x: x["distance_km"])
    return hotels_with_distance
