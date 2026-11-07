"""Strict URL validation for Instagram Reels, YouTube Shorts, and TikTok."""
import re
from urllib.parse import urlparse
from typing import Dict, Any, Optional

MAX_URL_LENGTH = 500

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
INSTAGRAM_HOSTS = {"instagram.com", "www.instagram.com"}
TIKTOK_HOSTS = {"tiktok.com", "www.tiktok.com", "m.tiktok.com"}

YT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")
IG_CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{5,64}$")


class UnsupportedUrlError(ValueError):
    pass


def parse_reel_url(raw_url: str) -> Dict[str, str]:
    """Validates and parses a social media link into platform, ID, and canonical URL.
    
    Prevents open proxy / SSRF by constructing strict canonical URLs.
    """
    if not isinstance(raw_url, str):
        raise ValueError("URL must be a string.")

    cleaned = raw_url.strip()
    if not cleaned or len(cleaned) > MAX_URL_LENGTH:
        raise ValueError(f"URL length must be between 1 and {MAX_URL_LENGTH} characters.")

    try:
        parsed = urlparse(cleaned)
    except Exception:
        raise ValueError("Invalid URL format.")

    if parsed.scheme != "https":
        raise UnsupportedUrlError("Only https:// links are supported.")

    host = (parsed.hostname or "").lower()
    path_parts = [p for p in parsed.path.split("/") if p]

    # YouTube / YouTube Shorts
    if host in YOUTUBE_HOSTS:
        yt_id = None
        if host == "youtu.be" and len(path_parts) == 1:
            yt_id = path_parts[0]
        elif len(path_parts) >= 2 and path_parts[0] in ["shorts", "watch", "live"]:
            yt_id = path_parts[1]
        elif "v=" in (parsed.query or ""):
            match = re.search(r"v=([A-Za-z0-9_-]{11})", parsed.query)
            if match:
                yt_id = match.group(1)

        if not yt_id or not YT_ID_PATTERN.match(yt_id):
            raise UnsupportedUrlError("Use a valid YouTube video or Shorts link (youtube.com/shorts/...).")

        return {
            "platform": "youtube",
            "external_id": yt_id,
            "canonical_url": f"https://www.youtube.com/watch?v={yt_id}",
        }

    # Instagram Posts / Reels
    if host in INSTAGRAM_HOSTS:
        ig_code = None
        # Pattern: /reel/{code}/, /p/{code}/, /reels/{code}/
        for idx, part in enumerate(path_parts):
            if part in ["reel", "reels", "p", "tv"] and idx + 1 < len(path_parts):
                ig_code = path_parts[idx + 1]
                break

        if not ig_code or not IG_CODE_PATTERN.match(ig_code):
            raise UnsupportedUrlError("Use a valid Instagram Reel or Post link (instagram.com/reel/...).")

        return {
            "platform": "instagram",
            "external_id": ig_code,
            "canonical_url": f"https://www.instagram.com/reel/{ig_code}/",
        }

    raise UnsupportedUrlError("Only Instagram and YouTube links are currently supported.")
