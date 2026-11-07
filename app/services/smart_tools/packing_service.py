"""Smart Packing Checklist Generator customized by destination, climate, and activity."""
from typing import List, Dict, Any, Optional


def generate_packing_checklist(
    destination: str,
    duration_days: int = 3,
    travel_month: str = "November",
    interests: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Generates an intelligent, activity-aware packing checklist."""
    dest_lower = destination.lower()
    interests_set = {i.lower() for i in (interests or [])}

    docs = [
        "Aadhaar Card or Government Photo ID (Required for domestic hotel & airport entry)",
        "Flight E-tickets & Hotel booking vouchers (saved offline on phone)",
        "Credit / Debit cards with contact-less payment enabled",
        "Small cash in ₹100/₹500 notes for street vendors and temple shoe attendants",
    ]

    clothing = [
        f"{duration_days + 1} sets of comfortable daily breathable outfits",
        "Comfortable walking sneakers with good grip (crucial for stone fort ramparts)",
        "1 smart-casual outfit for fine dining or rooftop clubs",
    ]

    electronics = [
        "High-capacity Power Bank (10,000mAh+) for full-day photography & Google Maps",
        "Phone charger & charging cables",
        "Noise-cancelling earphones or AirPods for flight and cab journeys",
    ]

    toiletries = [
        "Broad-spectrum Sunscreen (SPF 50+)",
        "Lip balm and hydrating moisturizer",
        "Personal medications, band-aids, Paracetamol & ORS rehydration sachets",
        "Hand sanitizer & pocket wet wipes",
    ]

    regional_specials = []

    # Goa / Beach specials
    if "goa" in dest_lower or "beach" in interests_set:
        clothing.extend(["Swimwear / quick-dry shorts", "Flip-flops or beach sliders", "Linen shirts"])
        regional_specials.extend([
            "Mosquito repellent spray (Odomos) for outdoor beach shacks",
            "Waterproof phone pouch for water sports",
            "UV-protection polarized sunglasses",
        ])

    # Jaipur / Rajasthan / Heritage specials
    elif "jaipur" in dest_lower or "rajasthan" in dest_lower or "agra" in dest_lower:
        clothing.extend([
            "Modest lightweight cotton scarf / dupatta for covering shoulders & head at temples/dargahs",
            "Light sweater / denim jacket for evening breeze and fort sunset rooftops",
        ])
        regional_specials.extend([
            "Polarized sunglasses to cut desert glare",
            "Refillable insulated water bottle to avoid single-use plastic",
        ])

    # Hill station specials
    elif any(h in dest_lower for h in ["manali", "shimla", "ladakh", "kashmir", "ooty"]):
        clothing.extend([
            "Thermal inner wear (top & bottom)",
            "Fleece jacket & windproof winter coat",
            "Woolen beanie and gloves",
        ])
        regional_specials.extend([
            "Thermos flask for hot water/tea",
            "Altitude sickness pills (Diamox if Ladakh)",
            "Heavy moisturizer and cold cream",
        ])

    return {
        "success": True,
        "destination": destination.title(),
        "duration_days": duration_days,
        "total_items_suggested": len(docs) + len(clothing) + len(electronics) + len(toiletries) + len(regional_specials),
        "checklist": {
            "documents_and_finance": docs,
            "clothing_and_footwear": clothing,
            "electronics_and_gadgets": electronics,
            "toiletries_and_health": toiletries,
            "destination_essentials": regional_specials,
        },
    }
