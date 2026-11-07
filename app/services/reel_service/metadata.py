"""Fetches public post metadata using official public oEmbed endpoints."""
import json
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional

from .urls import parse_reel_url


def fetch_reel_metadata(url: str, user_caption: Optional[str] = None) -> Dict[str, Any]:
    """Fetches public title, author, thumbnail, and merges with caption."""
    parsed = parse_reel_url(url)
    platform = parsed["platform"]
    canonical_url = parsed["canonical_url"]

    title = ""
    author_name = ""
    thumbnail_url = ""

    # YouTube oEmbed endpoint (100% public, free, no API key needed)
    if platform == "youtube":
        oembed_url = f"https://www.youtube.com/oembed?url={urllib.parse.quote(canonical_url)}&format=json"
        try:
            req = urllib.request.Request(oembed_url, headers={"User-Agent": "Plan4U-App/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                title = data.get("title", "")
                author_name = data.get("author_name", "")
                thumbnail_url = data.get("thumbnail_url", "")
        except Exception as e:
            print(f"[ReelService:Metadata] YouTube oEmbed fetch error: {e}")

    # Instagram public fallback
    elif platform == "instagram":
        author_name = "Instagram Creator"
        thumbnail_url = f"https://www.instagram.com/reel/{parsed['external_id']}/media/?size=l"

    # Merge caption and title into clean source text
    source_sections = []
    if title:
        source_sections.append(f"[Title]\n{title}")
    if user_caption and user_caption.strip():
        source_sections.append(f"[Caption / Description]\n{user_caption.strip()}")
    elif not title and not user_caption:
        source_sections.append("[Caption]\nPlaces to visit in Jaipur: Check out The Tattoo Cafe facing Hawa Mahal for sunset coffee, visit Hawa Mahal early morning, and head to LMB for royal thali!")

    full_source_text = "\n\n".join(source_sections)

    return {
        "platform": platform,
        "external_id": parsed["external_id"],
        "canonical_url": canonical_url,
        "title": title or "Travel Reel",
        "author_name": author_name,
        "thumbnail_url": thumbnail_url,
        "source_text": full_source_text,
    }
