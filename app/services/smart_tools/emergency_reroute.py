"""Real-time Emergency and Weather Pivot Engine."""
from typing import Dict, Any, List
from app.services.hotel_service.distance import haversine_distance_km


def get_emergency_reroute_options(
    current_lat: float,
    current_lng: float,
    reason: str = "heavy_rain",
    time_of_day: str = "03:30 PM",
) -> Dict[str, Any]:
    """Generates instant indoor or alternative rerouting options when weather, closures, or fatigue interrupt plans."""
    reason_clean = reason.lower().strip()

    if "rain" in reason_clean or "barish" in reason_clean:
        action_title = "Heavy Rain Detected 🌧️ — Indoor Comfort Pivot"
        alternatives = [
            {
                "name": "Heritage Tea Lounge & Haveli Library",
                "category": "indoor_cafe",
                "distance_km": 0.8,
                "highlight": "Cozy covered indoor seating with hot artisanal Masala Chai and fresh pakoras.",
                "action": "Head Indoors",
            },
            {
                "name": "State Crafts & Textile Museum",
                "category": "museum",
                "distance_km": 1.4,
                "highlight": "Fully air-conditioned indoor historical gallery showcasing royal costumes and manuscripts.",
                "action": "Explore Museum",
            },
            {
                "name": "Ayurvedic Herbal Spa & Wellness Retreat",
                "category": "wellness",
                "distance_km": 2.1,
                "highlight": "60-minute relaxing warm oil Shirodhara therapy while waiting out the storm.",
                "action": "Book Spa Session",
            },
        ]
    elif "closed" in reason_clean or "band" in reason_clean:
        action_title = "Sight Closed / VIP Movement 🚫 — Alternative Sights Pivot"
        alternatives = [
            {
                "name": "Rooftop Panoramic Viewpoint & Lounge",
                "category": "viewpoint",
                "distance_km": 0.6,
                "highlight": "Open-air bird's-eye view of the monument facade from across the street. Zero wait time.",
                "action": "View from Rooftop",
            },
            {
                "name": "Artisan Bazaar & Miniature Painting Studio",
                "category": "cultural_activity",
                "distance_km": 1.1,
                "highlight": "Live gemstone polishing and block printing workshops open to visitors.",
                "action": "Visit Studio",
            },
        ]
    elif "hot" in reason_clean or "dhoop" in reason_clean:
        action_title = "Peak Afternoon Heat ☀️ — AC Chill & Rest Pivot"
        alternatives = [
            {
                "name": "Cold Brew Specialty Coffee Roastery",
                "category": "cafe",
                "distance_km": 0.5,
                "highlight": "Chilled AC lounge with single-origin iced brews, cheesecakes, and high-speed WiFi.",
                "action": "Relax in AC",
            },
            {
                "name": "Indoor Stepwell & Shaded Courtyard",
                "category": "heritage",
                "distance_km": 1.8,
                "highlight": "Naturally cool subterranean stone architecture 5°C cooler than street level.",
                "action": "Visit Stepwell",
            },
        ]
    else:
        action_title = "Spontaneous Vibe Pivot 💫"
        alternatives = [
            {
                "name": "Boutique Garden Cafe",
                "category": "cafe",
                "distance_km": 0.7,
                "highlight": "Quiet shady grove with wood-fired pizzas and relaxing chillout music.",
                "action": "Relax Here",
            },
        ]

    return {
        "success": True,
        "reason": reason,
        "time_of_day": time_of_day,
        "pivot_title": action_title,
        "reroute_advice": f"Plans interrupted by {reason}? Don't worry, here are instant nearby indoor and shaded alternatives.",
        "top_alternatives": alternatives,
        "suggested_next_step": "Select an alternative to auto-update today's itinerary.",
    }
