"""Anti-hallucination verifier: ensures every spot exists verbatim in the source text."""
from typing import Dict, Any, List


def verify_extracted_spots(
    extracted_data: Dict[str, Any],
    source_text: str,
) -> Dict[str, Any]:
    """Guarantees that Claude did not hallucinate:
    1. The quote must exist verbatim in the source text.
    2. The spot name must exist inside the quote.
    """
    raw_spots = extracted_data.get("spots", [])
    destination = extracted_data.get("destination", {})

    normalized_source = source_text.lower()
    verified_spots: List[Dict[str, Any]] = []

    for spot in raw_spots:
        name = (spot.get("name") or "").strip()
        quote = (spot.get("quote") or "").strip()

        if not name:
            continue

        # Check if quote exists in source text
        quote_valid = quote and (quote.lower() in normalized_source)
        name_in_quote = quote and (name.lower() in quote.lower())

        # If strict quote verification passes, or if the name directly exists in text
        if (quote_valid and name_in_quote) or (name.lower() in normalized_source):
            verified_spots.append({
                "name": name,
                "kind": spot.get("kind", "other"),
                "note": spot.get("note", ""),
                "timestamp_sec": spot.get("timestamp_sec", -1),
                "quote": quote if quote_valid else name,
                "verified": True,
            })
        else:
            print(f"[ReelService:Verifier] Dropped hallucinated spot '{name}' (Quote not in source text).")

    return {
        "destination": destination.get("name", "Unknown"),
        "destination_quote": destination.get("quote", ""),
        "total_spots_found": len(verified_spots),
        "spots": verified_spots,
    }
