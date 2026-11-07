"""Shared cache for Swiggy restaurant searches (Food delivery and Dineout).

One Swiggy search returns up to 30 restaurants near a point. Instead of searching on every chat message, the result
is stored under (source, ~1 km grid cell, search term) and served to everyone asking for the same thing nearby.

  - fresh  -> served from the database, no Swiggy call
  - stale  -> served immediately and refreshed once in the background (stale-while-revalidate)
  - missing-> one blocking search; concurrent requests for the same key share it (single-flight)

Only search results are cached (names, ratings, cuisines, cost). Slots, restaurant details and bookings are always
live. Swiggy calls are capped per day and a failing Swiggy is backed off, so this never hammers the API.
"""
import datetime
import json
import logging
import re
import threading
import time
from typing import Any, Dict, List, Optional

from app.config import settings
from app.services.database_service import db_service
from app.services.swiggy_mcp_service import SwiggyAuthRequired, SwiggyError, swiggy_mcp_service

logger = logging.getLogger(__name__)

SOURCES = ("food", "dineout")
CELL_DECIMALS = 2          # ~1.1 km grid
FETCH_SIZE = 30            # the most Dineout returns in one search
EMPTY_RESULT_TTL_SECONDS = 600
FAILURE_BACKOFF_SECONDS = 300
MAX_TERM_CHARS = 60


def _term_key(term: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (term or "").lower()))[:MAX_TERM_CHARS] or "restaurant"


def _cell_key(lat: float, lng: float) -> str:
    return f"{lat:.{CELL_DECIMALS}f},{lng:.{CELL_DECIMALS}f}"


class SwiggySearchCache:
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
        CREATE TABLE IF NOT EXISTS swiggy_search_cache (
            source {key} NOT NULL,
            cell {key} NOT NULL,
            term {key} NOT NULL,
            payload {"MEDIUMTEXT" if self._mysql else "TEXT"} NOT NULL,
            fetched_at {real} NOT NULL,
            expires_at {real} NOT NULL,
            PRIMARY KEY (source, cell, term)
        ){tail};
        """)
        self._run(f"""
        CREATE TABLE IF NOT EXISTS exa_usage (
            day {key} PRIMARY KEY,
            calls INTEGER NOT NULL
        ){tail};
        """)

    def _load(self, source: str, cell: str, term: str) -> Optional[Dict[str, Any]]:
        row = self._run("SELECT payload, fetched_at, expires_at FROM swiggy_search_cache "
                        "WHERE source = ? AND cell = ? AND term = ?", (source, cell, term), fetch=True)
        if not row:
            return None
        return {"results": json.loads(row["payload"]), "fetched_at": row["fetched_at"], "expires_at": row["expires_at"]}

    def _save(self, source: str, cell: str, term: str, results: List[Dict[str, Any]]):
        now = time.time()
        ttl = settings.SWIGGY_SEARCH_TTL_SECONDS if results else EMPTY_RESULT_TTL_SECONDS
        payload = json.dumps(results, ensure_ascii=False)
        if self._mysql:
            self._run("INSERT INTO swiggy_search_cache (source, cell, term, payload, fetched_at, expires_at) "
                      "VALUES (?, ?, ?, ?, ?, ?) ON DUPLICATE KEY UPDATE payload = VALUES(payload), "
                      "fetched_at = VALUES(fetched_at), expires_at = VALUES(expires_at)",
                      (source, cell, term, payload, now, now + ttl))
        else:
            self._run("INSERT OR REPLACE INTO swiggy_search_cache (source, cell, term, payload, fetched_at, expires_at) "
                      "VALUES (?, ?, ?, ?, ?, ?)", (source, cell, term, payload, now, now + ttl))

    # ---------------- budget ----------------
    @staticmethod
    def _usage_key() -> str:
        return "swiggy:" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    def _consume_call(self) -> bool:
        key = self._usage_key()
        row = self._run("SELECT calls FROM exa_usage WHERE day = ?", (key,), fetch=True)
        if row and row["calls"] >= settings.SWIGGY_MAX_SEARCHES_PER_DAY:
            logger.warning("Swiggy daily search cap (%s) reached; serving cached data only.",
                           settings.SWIGGY_MAX_SEARCHES_PER_DAY)
            return False
        if row:
            self._run("UPDATE exa_usage SET calls = calls + 1 WHERE day = ?", (key,))
        else:
            self._run("INSERT INTO exa_usage (day, calls) VALUES (?, 1)", (key,))
        return True

    def calls_today(self) -> int:
        row = self._run("SELECT calls FROM exa_usage WHERE day = ?", (self._usage_key(),), fetch=True)
        return row["calls"] if row else 0

    # ---------------- fetching ----------------
    def _flight_lock(self, key: str) -> threading.Lock:
        with self._flights_guard:
            return self._flights.setdefault(key, threading.Lock())

    def _fetch_and_store(self, user_id: Optional[str], source: str, term: str, lat: float, lng: float,
                         cell: str, term_key: str) -> Optional[List[Dict[str, Any]]]:
        """One Swiggy search. Returns the results, or None if nothing was fetched.

        Raises SwiggyAuthRequired when no connected account can serve the search (nothing is cached then).
        """
        actor = swiggy_mcp_service.discovery_actor(user_id)  # raises SwiggyAuthRequired
        if not self._consume_call():
            return None
        try:
            if source == "dineout":
                results = swiggy_mcp_service.search_swiggy_dineout(actor, term, lat, lng, limit=FETCH_SIZE)
            else:
                results = swiggy_mcp_service.search_swiggy_food(actor, term, lat, lng, limit=FETCH_SIZE)
        except SwiggyAuthRequired:
            raise
        except SwiggyError as e:
            logger.warning("Swiggy %s search failed for %r near %s: %s", source, term, cell, e)
            # Back off so a failing Swiggy is not retried (and counted) on every message.
            if self._load(source, cell, term_key):
                self._run("UPDATE swiggy_search_cache SET expires_at = ? WHERE source = ? AND cell = ? AND term = ?",
                          (time.time() + FAILURE_BACKOFF_SECONDS, source, cell, term_key))
            else:
                self._save(source, cell, term_key, [])
            return None
        self._save(source, cell, term_key, results)
        logger.info("Swiggy search cached: %s/%s/%s (%d restaurants)", source, cell, term_key, len(results))
        return results

    def search(self, user_id: Optional[str], source: str, term: str, lat: float, lng: float,
               limit: int = 12) -> List[Dict[str, Any]]:
        """Restaurants near a point for a search term. Swiggy is called only when the entry is missing or stale."""
        if source not in SOURCES:
            raise ValueError(f"source must be one of {SOURCES}")
        cell, term_key = _cell_key(lat, lng), _term_key(term)

        entry = self._load(source, cell, term_key)
        if entry and time.time() < entry["expires_at"]:
            return entry["results"][:limit]

        lock = self._flight_lock(f"{source}:{cell}:{term_key}")

        if entry:  # stale: answer now, refresh once in the background
            if lock.acquire(blocking=False):
                def work():
                    try:
                        self._fetch_and_store(user_id, source, term_key, lat, lng, cell, term_key)
                    except Exception as e:
                        logger.warning("Background Swiggy refresh failed: %s", e)
                    finally:
                        lock.release()
                threading.Thread(target=work, daemon=True, name=f"swiggy-refresh-{source}-{cell}").start()
            return entry["results"][:limit]

        # nothing stored: the first request searches, concurrent requests wait for it
        with lock:
            entry = self._load(source, cell, term_key)
            if entry:
                return entry["results"][:limit]
            return (self._fetch_and_store(user_id, source, term_key, lat, lng, cell, term_key) or [])[:limit]


swiggy_search_cache = SwiggySearchCache()
