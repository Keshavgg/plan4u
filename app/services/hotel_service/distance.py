"""GPS distance calculation using Haversine formula and walking time estimation."""
import math


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates straight-line spherical distance between two GPS coordinates in kilometers."""
    R = 6371.0  # Earth's radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)


def estimate_walking_time_mins(distance_km: float) -> int:
    """Estimates walking time assuming average human walking speed of 4.6 km/h (~13 mins/km)."""
    return max(1, int(distance_km * 13))


def format_distance_label(distance_km: float) -> str:
    """Returns user-friendly string e.g. '450m door (6 mins walk)' or '2.3 km door'."""
    walk_mins = estimate_walking_time_mins(distance_km)
    if distance_km < 1.0:
        meters = int(distance_km * 1000)
        return f"{meters}m door ({walk_mins} mins walk)"
    return f"{distance_km} km door"
