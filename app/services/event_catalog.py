"""Event catalog: Exa fills it, requests read it.

Three tiers for a request about a city:
  1. Category browsing ("comedy", "movies"): the stored list for (city, category).
  2. Something specific ("Zakir Khan", "pottery workshop"): matched against the stored lists first.
  3. Still no match: one live Exa search for that exact request, stored under (city, query) so the
     next person asking the same thing is served from the database.

Every stored entry behaves the same way:
  - fresh  -> served from the database, no Exa call
  - stale  -> served immediately and refreshed once in the background (stale-while-revalidate)
  - missing-> one blocking fetch; concurrent requests for the same key share it (single-flight)
Exa searches are capped per day (general cap plus a smaller cap for free-text searches), failed or empty
fetches are remembered briefly, and nothing here ever invents events.
"""
import datetime
import hashlib
from itertools import zip_longest
import json
import logging
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from app.config import settings
from app.services.database_service import db_service
from app.services.exa_service import event_has_ended, exa_service

logger = logging.getLogger(__name__)

EMPTY_RESULT_TTL_SECONDS = 1800
FAILURE_BACKOFF_SECONDS = 600
MAX_EVENTS_PER_ENTRY = 20
# 'What's on?' with no category shows a mix of these; each is cached on its own, so it costs nothing extra
# once someone has asked for that category.
BROWSE_CATEGORIES = ("comedy", "music", "nightlife", "festival")
MAX_QUERY_CHARS = 100

# Canonical categories and the broad Exa query used to fill each one for a city.
CATEGORY_QUERIES = {
    "movie": None,  # BookMyShow listing page, not a text query
    "comedy": "stand-up comedy shows",
    "music": "live music concerts and gigs",
    "nightlife": "nightlife club nights DJ parties",
    "theatre": "theatre plays and drama shows",
    "festival": "festivals and fairs",
    "workshop": "workshops and classes",
    "sports": "sports matches and tournaments",
    "art": "art exhibitions and gallery shows",
    "events": "live shows and events",
}

# Order matters: the first category with a matching keyword wins.
_CATEGORY_KEYWORDS = (
    ("movie", ("movie", "film", "cinema", "pvr", "inox", "cinepolis", "showtime", "multiplex")),
    ("comedy", ("comedy", "standup", "stand-up", "stand up", "open mic", "comic")),
    ("theatre", ("theatre", "theater", "drama", "play", "plays")),
    ("nightlife", ("nightlife", "club", "dj", "party", "techno", "pub")),
    ("music", ("music", "concert", "gig", "band", "jazz", "qawwali")),
    ("festival", ("festival", "fest", "fair", "mela")),
    ("workshop", ("workshop", "class", "classes", "course")),
    ("sports", ("sports", "match", "cricket", "football", "tournament")),
    ("art", ("art", "exhibition", "gallery")),
)

# Words that describe the request but do not identify a specific event.
_GENERIC_WORDS = {
    "the", "and", "for", "near", "nearby", "me", "in", "at", "on", "of", "to", "any", "some", "best", "good",
    "top", "live", "show", "shows", "event", "events", "tonight", "today", "tomorrow", "weekend", "week",
    "this", "next", "now", "happening", "around", "city", "going", "there", "what", "whats", "find",
    "search", "book", "ticket", "tickets", "please", "plz", "want", "wanna", "with", "from", "are", "is",
}
_CATEGORY_WORDS = {w for _, words in _CATEGORY_KEYWORDS for kw in words for w in re.findall(r"[a-z0-9]+", kw)}


def _words(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def match_category(text: Optional[str]) -> Optional[str]:
    """The catalog category named in free text, or None if no category keyword is present."""
    tokens = set(_words(text or ""))
    low = (text or "").lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        for kw in keywords:
            if (" " in kw or "-" in kw) and kw in low:
                return category
            if kw in tokens:
                return category
    return None


def canonical_category(text: Optional[str]) -> str:
    return match_category(text) or "events"


def specific_tokens(text: Optional[str], city: str = "") -> List[str]:
    """Words that identify something specific ('zakir', 'khan'), without category or filler words."""
    city_words = set(_words(city))
    return sorted({
        w for w in _words(text or "")
        if len(w) >= 3 and w not in _GENERIC_WORDS and w not in _CATEGORY_WORDS and w not in city_words
    })


_CATEGORY_KEYWORD_MAP = {category: keywords for category, keywords in _CATEGORY_KEYWORDS}


def _fits_category(event: Dict[str, Any], category: str) -> bool:
    """Does the event actually belong to the category it was fetched for? (Exa returns related pages too.)"""
    keywords = _CATEGORY_KEYWORD_MAP.get(category)
    if not keywords:
        return True
    text = f"{event.get('title') or ''} {event.get('description') or ''}".lower()
    words = set(_words(text))
    return any((" " in kw or "-" in kw) and kw in text or kw in words for kw in keywords)


def _current(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drops events whose date has passed since they were stored."""
    return [e for e in events if not event_has_ended(e.get("date_time"))]


def _city_key(city: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", city.lower().strip()).strip("-")


def _haystack(event: Dict[str, Any]) -> str:
    return " ".join(str(event.get(k) or "") for k in ("title", "description", "venue")).lower()


def _matches_all(events: List[Dict[str, Any]], tokens: List[str]) -> List[Dict[str, Any]]:
    return [e for e in events if all(t in _haystack(e) for t in tokens)]


class EventCatalog:
    def __init__(self):
        self.db = db_service
        self._flights: Dict[str, threading.Lock] = {}
        self._flights_guard = threading.Lock()
        self._init_schema()

    # ---------------- storage ----------------
    @property
    def _mysql(self) -> bool:
        return self.db.db_type == "mysql"

    def _run(self, sql: str, params: tuple = (), fetch: bool = False):
        conn = self.db.get_connection()
        cur = conn.cursor()
        try:
            cur.execute(sql.replace("?", "%s") if self._mysql else sql, params)
            row = None
            if fetch:
                raw = cur.fetchone()
                row = dict(zip([d[0] for d in cur.description], raw)) if raw else None
            if not self._mysql:
                conn.commit()
            return row
        finally:
            cur.close()
            conn.close()

    def _init_schema(self):
        key = "VARCHAR(100)" if self._mysql else "TEXT"
        real = "DOUBLE" if self._mysql else "REAL"
        tail = " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4" if self._mysql else ""
        self._run(f"""
        CREATE TABLE IF NOT EXISTS event_catalog (
            city {key} NOT NULL,
            category {key} NOT NULL,
            payload {"MEDIUMTEXT" if self._mysql else "TEXT"} NOT NULL,
            fetched_at {real} NOT NULL,
            expires_at {real} NOT NULL,
            PRIMARY KEY (city, category)
        ){tail};
        """)
        self._run(f"""
        CREATE TABLE IF NOT EXISTS exa_usage (
            day {key} PRIMARY KEY,
            calls INTEGER NOT NULL
        ){tail};
        """)

    def _load(self, city: str, key: str) -> Optional[Dict[str, Any]]:
        row = self._run("SELECT payload, fetched_at, expires_at FROM event_catalog WHERE city = ? AND category = ?",
                        (city, key), fetch=True)
        if not row:
            return None
        return {"events": json.loads(row["payload"]), "fetched_at": row["fetched_at"], "expires_at": row["expires_at"]}

    def _save(self, city: str, key: str, events: List[Dict[str, Any]]):
        now = time.time()
        if events:
            ttl = settings.MOVIES_CACHE_TTL_SECONDS if key == "movie" else settings.EVENTS_CACHE_TTL_SECONDS
        else:
            ttl = EMPTY_RESULT_TTL_SECONDS
        payload = json.dumps(events, ensure_ascii=False)
        if self._mysql:
            self._run(
                "INSERT INTO event_catalog (city, category, payload, fetched_at, expires_at) VALUES (?, ?, ?, ?, ?) "
                "ON DUPLICATE KEY UPDATE payload = VALUES(payload), fetched_at = VALUES(fetched_at), "
                "expires_at = VALUES(expires_at)", (city, key, payload, now, now + ttl))
        else:
            self._run(
                "INSERT OR REPLACE INTO event_catalog (city, category, payload, fetched_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?)", (city, key, payload, now, now + ttl))

    # ---------------- budget ----------------
    @staticmethod
    def _today() -> str:
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    def _consume_call(self, kind: str) -> bool:
        """Counts one Exa search for today; False if that kind's daily cap is already reached.

        kind 'catalog' = category lists; 'custom' = free-text searches (smaller cap, since anyone can
        type a new query). Both also count towards the overall total.
        """
        day = self._today()
        total_row = self._run("SELECT calls FROM exa_usage WHERE day = ?", (day,), fetch=True)
        total = total_row["calls"] if total_row else 0
        if total >= settings.EXA_MAX_CALLS_PER_DAY:
            logger.warning("Exa daily cap (%s) reached; not searching.", settings.EXA_MAX_CALLS_PER_DAY)
            return False
        if kind == "custom":
            custom_day = f"custom:{day}"
            custom_row = self._run("SELECT calls FROM exa_usage WHERE day = ?", (custom_day,), fetch=True)
            if custom_row and custom_row["calls"] >= settings.EXA_MAX_CUSTOM_SEARCHES_PER_DAY:
                logger.warning("Exa free-text search cap (%s) reached.", settings.EXA_MAX_CUSTOM_SEARCHES_PER_DAY)
                return False
            self._bump(custom_day, bool(custom_row))
        self._bump(day, bool(total_row))
        return True

    def _bump(self, day_key: str, exists: bool):
        if exists:
            self._run("UPDATE exa_usage SET calls = calls + 1 WHERE day = ?", (day_key,))
        else:
            self._run("INSERT INTO exa_usage (day, calls) VALUES (?, 1)", (day_key,))

    def calls_today(self) -> int:
        row = self._run("SELECT calls FROM exa_usage WHERE day = ?", (self._today(),), fetch=True)
        return row["calls"] if row else 0

    def custom_calls_today(self) -> int:
        row = self._run("SELECT calls FROM exa_usage WHERE day = ?", (f"custom:{self._today()}",), fetch=True)
        return row["calls"] if row else 0

    # ---------------- fill / read an entry ----------------
    def _flight_lock(self, key: str) -> threading.Lock:
        with self._flights_guard:
            return self._flights.setdefault(key, threading.Lock())

    def _fetch_and_store(self, city: str, key: str, fetcher: Callable[[], List[Dict[str, Any]]],
                         kind: str) -> Optional[List[Dict[str, Any]]]:
        """One Exa search for an entry. Returns the events, or None if nothing was fetched."""
        if not exa_service.is_available() or not self._consume_call(kind):
            return None
        try:
            events = fetcher()
        except Exception as e:
            logger.warning("Exa fetch failed for %s/%s: %s", city, key, e)
            # Back off so a failing Exa is not retried (and counted) on every request.
            if self._load(city, key):
                self._run("UPDATE event_catalog SET expires_at = ? WHERE city = ? AND category = ?",
                          (time.time() + FAILURE_BACKOFF_SECONDS, city, key))
            else:
                self._save(city, key, [])
            return None
        self._save(city, key, events)
        logger.info("Event catalog filled: %s/%s (%d events)", city, key, len(events))
        return events

    def _read(self, city: str, key: str, fetcher: Callable[[], List[Dict[str, Any]]], kind: str,
              allow_fetch: bool = True) -> List[Dict[str, Any]]:
        entry = self._load(city, key)
        if entry and time.time() < entry["expires_at"]:
            return entry["events"]

        lock = self._flight_lock(f"{city}:{key}")

        if entry:  # stale: answer now, refresh once in the background
            if allow_fetch and lock.acquire(blocking=False):
                def work():
                    try:
                        self._fetch_and_store(city, key, fetcher, kind)
                    finally:
                        lock.release()
                threading.Thread(target=work, daemon=True, name=f"catalog-refresh-{city}-{key}").start()
            return entry["events"]

        if not allow_fetch:
            return []
        # nothing stored: the first request fetches, concurrent requests wait for it
        with lock:
            entry = self._load(city, key)
            if entry:
                return entry["events"]
            return self._fetch_and_store(city, key, fetcher, kind) or []

    # ---------------- public API ----------------
    def get_events(self, city: str, category: str, limit: int = 12, allow_fetch: bool = True) -> List[Dict[str, Any]]:
        """The stored list for a city and canonical category. Exa is called only if it is missing or stale."""
        category = category if category in CATEGORY_QUERIES else "events"
        city_key = _city_key(city)
        if not city_key:
            return []

        if category == "events":  # open-ended: interleave the main categories so one does not crowd out the rest
            lists = [self.get_events(city, c, MAX_EVENTS_PER_ENTRY, allow_fetch) for c in BROWSE_CATEGORIES]
            mixed = [e for group in zip_longest(*lists) for e in group if e is not None]
            return mixed[:limit]

        def fetcher() -> List[Dict[str, Any]]:
            if category == "movie":
                return exa_service.fetch_movies(city, limit=MAX_EVENTS_PER_ENTRY)
            events = exa_service.fetch_events(CATEGORY_QUERIES[category], city, limit=MAX_EVENTS_PER_ENTRY)
            if category != "events":
                events = [e for e in events if _fits_category(e, category)]
                for e in events:
                    e["category"] = category
            return events

        return _current(self._read(city_key, category, fetcher, "catalog", allow_fetch))[:limit]

    def search(self, city: str, text: Optional[str], limit: int = 20) -> List[Dict[str, Any]]:
        """Events for a free-text request, cheapest source first (see the module docstring)."""
        category = canonical_category(text)
        tokens = specific_tokens(text, city)

        # Tier 1: browsing a category (or everything) - just the stored list.
        if not tokens:
            return self.get_events(city, category, limit)

        # Tier 2: something specific - look inside the lists we already hold, without fetching more.
        pool = self.get_events(city, category, MAX_EVENTS_PER_ENTRY)
        if category != "events":
            pool += self.get_events(city, "events", MAX_EVENTS_PER_ENTRY, allow_fetch=False)
        matched = _matches_all(pool, tokens)
        if matched:
            seen, unique = set(), []
            for e in matched:
                if e["id"] not in seen:
                    seen.add(e["id"])
                    unique.append(e)
            return unique[:limit]

        # Tier 3: one live search for exactly this, stored so the next person gets it from the database.
        city_key = _city_key(city)
        if not city_key:
            return []
        query = " ".join(_words(text))[:MAX_QUERY_CHARS]
        key = "q:" + hashlib.sha1(f"{category}|{' '.join(tokens)}".encode("utf-8")).hexdigest()[:16]

        def fetcher() -> List[Dict[str, Any]]:
            found = exa_service.fetch_events(query, city, limit=MAX_EVENTS_PER_ENTRY)
            return _matches_all(found, tokens)  # keep only what is actually about the request

        return _current(self._read(city_key, key, fetcher, "custom"))[:limit]


event_catalog = EventCatalog()
