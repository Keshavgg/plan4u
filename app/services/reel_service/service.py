"""Main orchestrator for Clip2Trip (Reels/Shorts -> Itinerary places)."""
from typing import Dict, Any, Optional

from .urls import parse_reel_url
from .metadata import fetch_reel_metadata
from .claude_extractor import extract_spots_with_claude
from .verifier import verify_extracted_spots


def convert_reel_to_places(
    reel_url: str,
    user_caption: Optional[str] = None,
) -> Dict[str, Any]:
    """End-to-end Clip2Trip pipeline:
    1. Validates Reel / Shorts URL.
    2. Fetches public title, author, and merges with caption.
    3. Uses Anthropic Claude 3.5 Sonnet to extract places, quotes, and timestamps.
    4. Runs anti-hallucination verification.
    """
    # 1. Parse & validate URL
    url_info = parse_reel_url(reel_url)

    # 2. Fetch metadata & source text
    meta = fetch_reel_metadata(reel_url, user_caption=user_caption)

    # 3. Claude 3.5 Sonnet extraction
    raw_extraction = extract_spots_with_claude(meta["source_text"])

    # 4. Anti-hallucination verification
    verified_result = verify_extracted_spots(raw_extraction, meta["source_text"])

    return {
        "status": "success",
        "reel_info": {
            "platform": url_info["platform"],
            "canonical_url": url_info["canonical_url"],
            "title": meta["title"],
            "author": meta["author_name"],
            "thumbnail": meta["thumbnail_url"],
        },
        "extracted_destination": verified_result["destination"],
        "total_spots_found": verified_result["total_spots_found"],
        "spots": verified_result["spots"],
    }
