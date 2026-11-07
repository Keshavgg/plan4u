"""Exa AI Search Service for real-time live events, ticketing and local discovery.
Provides neural search across ticketing sites (domains configured via EXA_EVENT_DOMAINS).
Callers should go through app.services.event_catalog, which caches results per city and category.

Only values present in the Exa response are returned. Fields Exa does not provide
(venue, date, price) are None rather than being guessed.
"""
import datetime
import json
import logging
import re
import urllib.request
from typing import List, Dict, Any, Optional
from app.config import settings
from app.services.database_service import db_service

logger = logging.getLogger(__name__)

EXA_ENDPOINT = "https://api.exa.ai/search"

# Generic section headings on BookMyShow listing pages that are not movie titles.
NON_MOVIE_HEADINGS = (
    "enjoy online", "latest movies", "upcoming", "with bookmyshow",
    "family and friends", "ticket booking", "movies that you", "explore movies",
)

# Ticketing site name -> provider label, matched against the result URL.
PROVIDER_BY_DOMAIN = {
    "district.in": "District",
    "insider.in": "Paytm Insider",
    "bookmyshow.com": "BookMyShow",
    "skillbox": "Skillbox",
    "zomato.com": "Zomato Live",
}

# Site-name suffixes/prefixes Exa appends to page titles.
TITLE_NOISE = re.compile(
    r"\s*[|\-]\s*(District|BookMyShow|Insider\.in|Skillbox)\s*$"
    r"|\s*\b[a-z]+-shows\b"
    r"|\b(Event Tickets|Buy Tickets|Tickets Online)\b.*$"
    r"|\s+[A-Za-z]+-NCR\b"
    r"|^Book\s+Tickets?\s+(to|for)\s+",
    re.IGNORECASE,
)

def _is_listing_page(url: str) -> bool:
    """True for category/index pages ('Best Live Events in Delhi-NCR') as opposed to a single event page."""
    if "bookmyshow.com" in url:
        return not re.search(r"/events/[^/]+/ET\d+", url)
    if "district.in" in url:
        return "buy-tickets" not in url
    if "insider.in" in url:
        return "/event/" not in url
    if "zomato.com" in url:  # Zomato pages here are articles and restaurant lists, not single events
        return True
    return False


_MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_DATE_PART = re.compile(r"(?:(mon|tue|wed|thu|fri|sat|sun)[a-z]*[,\s]+)?(\d{1,2})\s+([A-Za-z]{3,9})(?:\s+(\d{4}))?", re.IGNORECASE)


def event_end_date(date_text: Optional[str], today: Optional[datetime.date] = None) -> Optional[datetime.date]:
    """The last date mentioned in text like 'Wed, 26 Aug - Sun, 30 Aug, 7:00 PM', or None if none can be read.

    A missing year is resolved with the weekday when one is given, otherwise to the occurrence nearest to today.
    """
    today = today or datetime.date.today()
    found = []
    for weekday, day, month, year in _DATE_PART.findall(date_text or ""):
        month_no = _MONTHS.get(month[:3].lower())
        if not month_no:
            continue
        candidates = []
        for y in ([int(year)] if year else [today.year - 1, today.year, today.year + 1]):
            try:
                candidates.append(datetime.date(y, month_no, int(day)))
            except ValueError:
                pass
        if weekday:
            wanted = _WEEKDAYS.index(weekday[:3].lower())
            candidates = [c for c in candidates if c.weekday() == wanted]
        if candidates:
            found.append(min(candidates, key=lambda c: abs((c - today).days)))
    return max(found) if found else None


def event_has_ended(date_text: Optional[str], today: Optional[datetime.date] = None) -> bool:
    end = event_end_date(date_text, today)
    return end is not None and end < (today or datetime.date.today())


_LISTING_TITLE = re.compile(
    r"\b(best|top|upcoming)\b.*\b(events?|shows?|gigs?|concerts?)\b"
    r"|\bnear you\b"
    r"|\bnow!?$"
    r"|^(?:[\w\s-]+\s)?(?:shows?|events?|gigs?|concerts?)\s+(?:live\s+)?in\s+[\w\s]+$",
    re.IGNORECASE,
)


def _is_listing_title(title: str) -> bool:
    """True for category-page titles such as 'Top Upcoming Events in Goa' or 'Music in Goa Now!'."""
    return bool(_LISTING_TITLE.search(title.strip()))


def _extract_venue(text: str, city: str) -> Optional[str]:
    """Venue from the structured lines these ticket sites print. None when the page does not state one."""
    patterns = (
        r"(?m)^\s*(.{3,80}?)\s*·\s*[\d.,]+\s*km away",                    # District: "Venue, Area · 3 km away"
        rf"(?im)^\s*([^\n#:]{{3,60}}):\s*{re.escape(city)}\s*$",           # BookMyShow: "Venue name: City"
        r"(?i)\b(?:venue|location)\s*[:\-]\s*([^\n\r|·]{3,60})",         # an explicit label
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            venue = match.group(1).strip(" -|,")
            if venue and not re.search(r"event tickets|search for", venue, re.IGNORECASE):
                return venue
    return None


MOVIE_QUERY_WORDS = (
    "movie", "movies", "film", "films", "cinema", "cinemas", "theatre", "theaters",
    "pvr", "inox", "cinepolis", "showtime", "showtimes",
)


class SmartCacheManager:
    """Database-backed cache for Exa lookups (SQLite WAL locally, MySQL in production)."""

    def __init__(self):
        self.db = db_service

    def get(self, key: str, ttl_seconds: int) -> Optional[List[Dict[str, Any]]]:
        """Fetch cached data from the database if not expired."""
        return self.db.get_cache(cache_key=key, ttl_seconds=ttl_seconds)

    def get_stale_fallback(self, key: str) -> Optional[List[Dict[str, Any]]]:
        """Serve stale cached data if the live API call fails."""
        return self.db.get_stale_fallback(cache_key=key)

    def set(self, key: str, data: List[Dict[str, Any]], ttl_seconds: int):
        """Save data to the database. Key format is '<category>:<city>[:<query>]'."""
        parts = key.split(":")
        category = parts[0]
        city = parts[1] if len(parts) > 1 else ""
        self.db.set_cache(cache_key=key, data=data, category=category, city=city, ttl_seconds=ttl_seconds)

    def get_stats(self) -> Dict[str, Any]:
        """Return database cache statistics."""
        return self.db.get_stats()


class ExaSearchService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.EXA_API_KEY
        self.cache_mgr = SmartCacheManager()

    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        req = urllib.request.Request(
            EXA_ENDPOINT,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
                "User-Agent": "Plan4U-TravelCopilot/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=settings.EXA_TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def fetch_movies(self, city: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Movies currently listed on BookMyShow for a city. One Exa call, no caching, raises on failure.

        Only data present in the Exa response is returned (title, source URL). Venue,
        showtimes and prices are not on the listing page, so they are left as None.
        """
        city_slug = re.sub(r"[^a-z0-9]+", "-", city.lower().strip()).strip("-")
        data = self._post({
            "query": f"site:in.bookmyshow.com/explore/movies-{city_slug}",
            "numResults": 2,
            "contents": {"text": {"maxCharacters": 3500}},
        })

        movies: List[Dict[str, Any]] = []
        seen = set()
        for r in data.get("results", []):
            page_url = r.get("url", "")
            for heading in re.findall(r"###\s+([^\n\r]+)", r.get("text", "")):
                title = heading.strip()
                if len(title) <= 2 or title.lower() in seen:
                    continue
                if any(h in title.lower() for h in NON_MOVIE_HEADINGS):
                    continue
                seen.add(title.lower())
                slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:25]
                movies.append({
                    "id": f"bms_live_{slug}",
                    "title": title,
                    "category": "movie",
                    "venue": None,
                    "date_time": None,
                    "min_price_inr": None,
                    "price_range_inr": None,
                    "is_free": False,
                    "description": None,
                    "booking_provider": "BookMyShow",
                    "booking_url": page_url,
                })
        return movies[:limit]

    def fetch_events(self, query: str, city: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Live events matching a broad query. One Exa call, no caching, raises on failure."""
        data = self._post({
            "query": f"{query} in {city}",
            "numResults": 10,  # some results are listing pages and are dropped, so ask for the maximum
            "contents": {"text": {"maxCharacters": 2000}},
            "includeDomains": settings.EXA_EVENT_DOMAINS,
        })

        events: List[Dict[str, Any]] = []
        for r in data.get("results", []):
            raw_title = r.get("title", "")
            url = r.get("url", "")
            text = r.get("text", "")
            # "{" means the page title is scraped CSS, not an event name
            if not url or not raw_title or "{" in raw_title or _is_listing_page(url):
                continue

            provider = next((label for dom, label in PROVIDER_BY_DOMAIN.items() if dom in url), None)

            title = TITLE_NOISE.sub("", raw_title).strip(" -|,\n\t")
            if provider == "Skillbox":  # "Event name | Club Gigs - Music" -> "Event name"
                title = title.split(" || ")[0].split(" | ")[0].strip(" -|,")
            if len(title) < 5:
                sub = re.search(r"#{2,5}\s+([A-Za-z0-9\s\-\'\&]+)", text)
                if sub:
                    title = sub.group(1).strip()
            if not title:
                continue

            date_match = re.search(
                r"((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*[,\s]+\d{1,2}\s+[A-Za-z]+[^\n\r·]{0,40})",
                text, re.IGNORECASE,
            )
            venue = _extract_venue(text, city)
            date_text = date_match.group(1).strip() if date_match else None
            if not date_text:  # recurring shows are listed as "Daily, Multiple slots" / "Every Friday"
                recurring = re.search(r"(?im)^(daily[^\n]{0,30}|every\s+\w+[^\n]{0,30})$", text)
                date_text = recurring.group(1).strip() if recurring else None
            if _is_listing_title(title) or event_has_ended(date_text):
                continue  # a category page, or an event that is already over
            price_match = re.search(r"(₹\s*[\d,]+(?:\s*-\s*₹?\s*[\d,]+)?)", text)

            price_range = price_match.group(1) if price_match else None
            min_price = None
            if price_range:
                min_price = float(re.search(r"[\d,]+", price_range).group(0).replace(",", ""))
            is_free = bool(re.search(r"\bfree (entry|entrance)\b", text, re.IGNORECASE))
            if is_free and min_price is None:
                min_price = 0.0

            lines = [l.strip() for l in text.split("\n") if len(l.strip()) > 30 and not l.strip().startswith("#")]
            # Prefer the paragraph under the "About" heading; the first long line is usually just the page title.
            about = re.search(r"(?im)^#*\s*about[^\n]*\n+(.{30,})", text)
            description = (about.group(1).strip() if about else (lines[0] if lines else None))
            if description and "event tickets" in description.lower():  # just the page title repeated
                description = None

            slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:30]
            events.append({
                "id": f"exa_{slug}_{(provider or 'web').lower()[:3]}",
                "title": title,
                "category": "event",
                "venue": venue,
                "date_time": date_text,
                "min_price_inr": min_price,
                "price_range_inr": price_range or ("Free entry" if is_free else None),
                "is_free": is_free,
                "description": description[:180] if description else None,
                "booking_provider": provider,
                "booking_url": url,
            })
            if len(events) >= limit:
                break
        return events


# Global Singleton instance
exa_service = ExaSearchService()
