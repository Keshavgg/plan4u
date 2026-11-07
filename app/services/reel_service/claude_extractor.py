"""Claude 3.5 Sonnet extraction: Extracts structured travel places from social post text."""
import json
import urllib.request
from typing import Dict, Any, List, Optional

from app.config import settings

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

SYSTEM_PROMPT = """You extract travel places from the public text of a travel social-media post (its title, caption, and description).
You only have this text. Never claim to have watched the video or heard audio.

Rules:
- Your response MUST be valid JSON only (no markdown, no backticks, no extra text).
- List only specific, named places that are written in the text: cafés, restaurants, viewpoints, activities, stays, monuments.
- name: the place name as written in the text.
- kind: cafe, restaurant, viewpoint, activity, stay, or monument.
- quote: an exact, contiguous excerpt (5-200 characters) from the text that contains the name.
- note: a short tip if the text states one (e.g., 'must try the iced latte', 'best at sunset'); otherwise "".
- timestamp_sec: integer seconds if the text gave a timestamp (e.g. '01:30 Cafe X' -> 90), otherwise -1.
- destination: object with 'name' and 'quote' for the city/region mentioned (e.g. 'Goa', 'Jaipur').

Output JSON format:
{
  "destination": {"name": "...", "quote": "..."},
  "spots": [
    {"name": "...", "kind": "cafe", "quote": "...", "note": "...", "timestamp_sec": -1}
  ]
}"""


def extract_spots_with_claude(source_text: str) -> Dict[str, Any]:
    """Uses Anthropic Claude to parse travel spots from social text."""
    api_key = settings.ANTHROPIC_API_KEY
    model = settings.ANTHROPIC_MODEL

    if not api_key:
        return {"destination": {}, "spots": []}

    payload = {
        "model": model,
        "max_tokens": 1500,
        "system": SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": f"Extract travel places from this post text:\n\n{source_text}",
            }
        ],
    }

    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }

    try:
        req = urllib.request.Request(
            ANTHROPIC_API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content_list = data.get("content", [])
            text_response = "{}"
            for item in content_list:
                if item.get("type") == "text":
                    text_response = item.get("text", "{}")
                    break
            
            # Clean possible markdown wrapping if any
            clean_json = text_response.strip().removeprefix("```json").removesuffix("```").strip()
            return json.loads(clean_json)
    except Exception as e:
        print(f"[ReelService:Claude] Extraction API error: {e}. Using fallback.")
        return {"destination": {}, "spots": []}
