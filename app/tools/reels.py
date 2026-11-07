"""AI-facing tool for Clip2Trip social reel extraction."""
from typing import Dict, Any
from app.services.reel_service import convert_reel_to_places


def extract_spots_from_reel_tool(url: str) -> Dict[str, Any]:
    """Extract location name, visited spots, food recommendations, and timestamps from Instagram Reel or YouTube Shorts URL.
    
    Args:
        url: Valid Instagram Reel (https://instagram.com/reel/...) or YouTube Short (https://youtube.com/shorts/...) URL.
    """
    res = convert_reel_to_places(url=url)
    return {
        "success": True,
        "destination": res.destination,
        "summary": res.summary,
        "spots": [s.model_dump() for s in res.spots],
        "tips": res.extracted_tips,
        "thumbnail_url": res.thumbnail_url,
    }
