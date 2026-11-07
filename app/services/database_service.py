"""Production Database Service for Plan4U (Hostinger MySQL & SQLite Supported).
Provides persistent relational storage and smart caching for live events, movies,
tickets and analytics, eliminating flat JSON file dependencies.
"""
import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.config import settings

# In-memory and Disk paths
DATA_STORE_DIR = Path(__file__).resolve().parent.parent.parent / "data_store"
DEFAULT_SQLITE_PATH = DATA_STORE_DIR / "plan4u.db"
OLD_JSON_CACHE_PATH = DATA_STORE_DIR / "exa_cache.json"


class DatabaseService:
    """Production Database Manager supporting SQLite (local & VPS) and MySQL (Hostinger cPanel/Cloud)."""

    def __init__(self):
        self.db_type = (settings.DB_TYPE or "sqlite").lower()
        if settings.DATABASE_URL.startswith("mysql://") or settings.DATABASE_URL.startswith("mysql+pymysql://"):
            self.db_type = "mysql"

        self.sqlite_path = Path(settings.DB_PATH) if settings.DB_PATH else DEFAULT_SQLITE_PATH
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)

        # L1 Memory Cache for sub-millisecond retrieval (0.0001s)
        self.l1_cache: Dict[str, Dict[str, Any]] = {}
        self.cost_per_query_usd: float = 0.005
        self.usd_to_inr: float = 84.0

        # Initialize Schema & Auto-migrate any existing JSON file
        self._init_schema()
        self._auto_migrate_from_json()

    def get_connection(self):
        """Thread-safe connection provider for SQLite or MySQL."""
        if self.db_type == "mysql":
            import pymysql
            from urllib.parse import urlparse

            if settings.DATABASE_URL:
                parsed = urlparse(settings.DATABASE_URL)
                return pymysql.connect(
                    host=parsed.hostname or "localhost",
                    port=parsed.port or 3306,
                    user=parsed.username or "root",
                    password=parsed.password or "",
                    database=parsed.path.lstrip("/"),
                    charset="utf8mb4",
                    autocommit=True
                )
            return pymysql.connect(
                host=settings.DB_HOST,
                port=settings.DB_PORT,
                user=settings.DB_USER,
                password=settings.DB_PASSWORD,
                database=settings.DB_NAME,
                charset="utf8mb4",
                autocommit=True
            )
        else:
            # SQLite with Write-Ahead Logging (WAL) for high concurrency
            conn = sqlite3.connect(str(self.sqlite_path), check_same_thread=False, timeout=10.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute("PRAGMA busy_timeout=5000;")
            cursor.close()
            return conn

    def _init_schema(self):
        """Creates required relational tables and indexes if they do not exist."""
        conn = self.get_connection()
        cur = conn.cursor()
        try:
            if self.db_type == "mysql":
                cur.execute("""
                CREATE TABLE IF NOT EXISTS cache_entries (
                    cache_key VARCHAR(255) PRIMARY KEY,
                    category VARCHAR(64),
                    city VARCHAR(128),
                    data MEDIUMTEXT NOT NULL,
                    timestamp DOUBLE NOT NULL,
                    expires_at DOUBLE NOT NULL,
                    hit_count INT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_cache_expires (expires_at),
                    INDEX idx_cache_cat_city (category, city)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)

                cur.execute("""
                CREATE TABLE IF NOT EXISTS live_events (
                    id VARCHAR(255) PRIMARY KEY,
                    cache_key VARCHAR(255),
                    category VARCHAR(64),
                    title VARCHAR(255) NOT NULL,
                    venue VARCHAR(255),
                    date_time VARCHAR(128),
                    min_price_inr DECIMAL(10,2),
                    price_range_inr VARCHAR(64),
                    is_free TINYINT(1) DEFAULT 0,
                    booking_provider VARCHAR(64),
                    booking_url TEXT,
                    description TEXT,
                    city VARCHAR(128),
                    expires_at DOUBLE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_events_cat_city (category, city),
                    INDEX idx_events_expires (expires_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)

                cur.execute("""
                CREATE TABLE IF NOT EXISTS cache_metrics (
                    id INT PRIMARY KEY,
                    hits INT DEFAULT 0,
                    misses INT DEFAULT 0,
                    saved_usd DOUBLE DEFAULT 0.0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)
                cur.execute("INSERT IGNORE INTO cache_metrics (id, hits, misses, saved_usd) VALUES (1, 0, 0, 0.0);")

                cur.execute("""
                CREATE TABLE IF NOT EXISTS swiggy_auth (
                    id INT PRIMARY KEY,
                    access_token TEXT NOT NULL,
                    refresh_token TEXT,
                    expires_at DOUBLE NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)

                cur.execute("""
                CREATE TABLE IF NOT EXISTS shared_trips (
                    share_code VARCHAR(32) PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    destination VARCHAR(128) NOT NULL,
                    origin VARCHAR(128),
                    days INT,
                    budget_inr DECIMAL(12,2),
                    itinerary_data MEDIUMTEXT NOT NULL,
                    creator_name VARCHAR(128) DEFAULT 'Traveler',
                    fork_count INT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)

                cur.execute("""
                CREATE TABLE IF NOT EXISTS user_memory (
                    id VARCHAR(64) PRIMARY KEY,
                    user_id VARCHAR(128) NOT NULL,
                    layer VARCHAR(32) NOT NULL,
                    topic VARCHAR(64) NOT NULL,
                    content TEXT NOT NULL,
                    confidence DOUBLE DEFAULT 1.0,
                    source VARCHAR(32) DEFAULT 'chat',
                    pointer_id VARCHAR(64),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_user_mem (user_id, layer, topic)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)
            else:
                # SQLite
                cur.execute("""
                CREATE TABLE IF NOT EXISTS cache_entries (
                    cache_key TEXT PRIMARY KEY,
                    category TEXT,
                    city TEXT,
                    data TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    hit_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache_entries(expires_at);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_cache_cat_city ON cache_entries(category, city);")

                cur.execute("""
                CREATE TABLE IF NOT EXISTS live_events (
                    id TEXT PRIMARY KEY,
                    cache_key TEXT,
                    category TEXT,
                    title TEXT NOT NULL,
                    venue TEXT,
                    date_time TEXT,
                    min_price_inr REAL,
                    price_range_inr TEXT,
                    is_free INTEGER DEFAULT 0,
                    booking_provider TEXT,
                    booking_url TEXT,
                    description TEXT,
                    city TEXT,
                    expires_at REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_events_cat_city ON live_events(category, city);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_events_expires ON live_events(expires_at);")

                cur.execute("""
                CREATE TABLE IF NOT EXISTS cache_metrics (
                    id INTEGER PRIMARY KEY,
                    hits INTEGER DEFAULT 0,
                    misses INTEGER DEFAULT 0,
                    saved_usd REAL DEFAULT 0.0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)
                cur.execute("INSERT OR IGNORE INTO cache_metrics (id, hits, misses, saved_usd) VALUES (1, 0, 0, 0.0);")

                cur.execute("""
                CREATE TABLE IF NOT EXISTS swiggy_auth (
                    id INTEGER PRIMARY KEY,
                    access_token TEXT NOT NULL,
                    refresh_token TEXT,
                    expires_at REAL NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)

                cur.execute("""
                CREATE TABLE IF NOT EXISTS shared_trips (
                    share_code TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    origin TEXT,
                    days INTEGER,
                    budget_inr REAL,
                    itinerary_data TEXT NOT NULL,
                    creator_name TEXT DEFAULT 'Traveler',
                    fork_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_shared_trips_dest ON shared_trips(destination);")

                cur.execute("""
                CREATE TABLE IF NOT EXISTS user_memory (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    layer TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    content TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    source TEXT DEFAULT 'chat',
                    pointer_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_user_mem ON user_memory(user_id, layer, topic);")
                conn.commit()
        except Exception as e:
            print(f"[DatabaseService] Error initializing schema: {e}")
        finally:
            cur.close()
            conn.close()

    def _auto_migrate_from_json(self):
        """Automatically imports existing exa_cache.json into the database and migrates away from JSON."""
        if not OLD_JSON_CACHE_PATH.exists():
            return

        try:
            with open(OLD_JSON_CACHE_PATH, "r", encoding="utf-8") as f:
                old_data = json.load(f)

            if isinstance(old_data, dict) and old_data:
                print(f"[DatabaseService] Migrating {len(old_data)} entries from JSON to Database...")
                for cache_key, entry in old_data.items():
                    ts = entry.get("timestamp", time.time())
                    items = entry.get("data", [])
                    # Infer category & city from key
                    parts = cache_key.split(":")
                    category = parts[0] if len(parts) > 0 else "general"
                    city = parts[1] if len(parts) > 1 else "delhi"
                    ttl = 21600 if category == "movies" else 14400
                    self.set_cache(cache_key, items, category=category, city=city, ttl_seconds=ttl, recorded_time=ts)

                # Rename json to indicate migration complete
                migrated_path = DATA_STORE_DIR / "exa_cache.json.migrated"
                OLD_JSON_CACHE_PATH.rename(migrated_path)
                print(f"[DatabaseService] ✅ Migration complete! Flat JSON archived to {migrated_path.name}")
        except Exception as e:
            print(f"[DatabaseService] Warning during JSON migration: {e}")

    def get_cache(self, cache_key: str, ttl_seconds: int = 21600) -> Optional[List[Dict[str, Any]]]:
        """Fetch cached data from L1 Memory or Database if not expired."""
        now = time.time()

        # 1. Fast L1 Memory check
        l1_entry = self.l1_cache.get(cache_key)
        if l1_entry and now <= l1_entry.get("expires_at", 0):
            self._record_metric(is_hit=True, cache_key=cache_key)
            return l1_entry.get("data")

        # 2. Database check
        conn = self.get_connection()
        cur = conn.cursor()
        try:
            param = "%s" if self.db_type == "mysql" else "?"
            cur.execute(f"SELECT data, expires_at FROM cache_entries WHERE cache_key = {param}", (cache_key,))
            row = cur.fetchone()
            if row:
                expires_at = row["expires_at"] if isinstance(row, sqlite3.Row) else row[1]
                raw_data = row["data"] if isinstance(row, sqlite3.Row) else row[0]
                if now <= expires_at:
                    data = json.loads(raw_data)
                    # Warm L1 cache
                    self.l1_cache[cache_key] = {"data": data, "expires_at": expires_at}
                    self._record_metric(is_hit=True, cache_key=cache_key)
                    return data
            
            # Miss or Expired
            self._record_metric(is_hit=False, cache_key=cache_key)
            return None
        except Exception as e:
            print(f"[DatabaseService] Error reading cache key '{cache_key}': {e}")
            self._record_metric(is_hit=False, cache_key=cache_key)
            return None
        finally:
            cur.close()
            conn.close()

    def set_cache(
        self,
        cache_key: str,
        data: List[Dict[str, Any]],
        category: str = "general",
        city: str = "delhi",
        ttl_seconds: int = 21600,
        recorded_time: Optional[float] = None
    ):
        """Stores entries in both L1 Memory and persistent Database (cache_entries + live_events)."""
        if not data:
            return

        ts = recorded_time or time.time()
        expires_at = ts + ttl_seconds
        json_str = json.dumps(data)

        # 1. Warm L1 cache
        self.l1_cache[cache_key] = {"data": data, "expires_at": expires_at}

        # 2. Write to Database
        conn = self.get_connection()
        cur = conn.cursor()
        try:
            param = "%s" if self.db_type == "mysql" else "?"
            
            if self.db_type == "mysql":
                cur.execute(f"""
                INSERT INTO cache_entries (cache_key, category, city, data, timestamp, expires_at, hit_count)
                VALUES ({param}, {param}, {param}, {param}, {param}, {param}, 0)
                ON DUPLICATE KEY UPDATE
                    data = VALUES(data),
                    timestamp = VALUES(timestamp),
                    expires_at = VALUES(expires_at);
                """, (cache_key, category, city, json_str, ts, expires_at))
            else:
                cur.execute(f"""
                INSERT OR REPLACE INTO cache_entries (cache_key, category, city, data, timestamp, expires_at, hit_count)
                VALUES ({param}, {param}, {param}, {param}, {param}, {param}, 0);
                """, (cache_key, category, city, json_str, ts, expires_at))

            # Store individual normalized events into live_events table
            for ev in data:
                ev_id = ev.get("id") or f"ev_{int(time.time()*1000)}"
                title = ev.get("title") or "Event"
                venue = ev.get("venue") or ""
                dt_str = ev.get("date_time") or ""
                min_p = float(ev.get("min_price_inr") or 0.0)
                p_range = str(ev.get("price_range_inr") or "")
                is_free = 1 if ev.get("is_free") else 0
                provider = ev.get("booking_provider") or "BookMyShow"
                b_url = ev.get("booking_url") or ""
                desc = ev.get("description") or ""

                if self.db_type == "mysql":
                    cur.execute(f"""
                    INSERT INTO live_events (id, cache_key, category, title, venue, date_time, min_price_inr, price_range_inr, is_free, booking_provider, booking_url, description, city, expires_at)
                    VALUES ({param}, {param}, {param}, {param}, {param}, {param}, {param}, {param}, {param}, {param}, {param}, {param}, {param}, {param})
                    ON DUPLICATE KEY UPDATE
                        venue = VALUES(venue), date_time = VALUES(date_time), booking_url = VALUES(booking_url), expires_at = VALUES(expires_at);
                    """, (ev_id, cache_key, category, title, venue, dt_str, min_p, p_range, is_free, provider, b_url, desc, city, expires_at))
                else:
                    cur.execute(f"""
                    INSERT OR REPLACE INTO live_events (id, cache_key, category, title, venue, date_time, min_price_inr, price_range_inr, is_free, booking_provider, booking_url, description, city, expires_at)
                    VALUES ({param}, {param}, {param}, {param}, {param}, {param}, {param}, {param}, {param}, {param}, {param}, {param}, {param}, {param});
                    """, (ev_id, cache_key, category, title, venue, dt_str, min_p, p_range, is_free, provider, b_url, desc, city, expires_at))

            if self.db_type != "mysql":
                conn.commit()
            print(f"[DatabaseService:STORE 💾] Saved {len(data)} items to SQL Database for key '{cache_key}'")
        except Exception as e:
            print(f"[DatabaseService] Error setting cache for '{cache_key}': {e}")
        finally:
            cur.close()
            conn.close()

    def get_stale_fallback(self, cache_key: str) -> Optional[List[Dict[str, Any]]]:
        """Provides stale fallback from Database if live API is temporarily unavailable."""
        conn = self.get_connection()
        cur = conn.cursor()
        try:
            param = "%s" if self.db_type == "mysql" else "?"
            cur.execute(f"SELECT data FROM cache_entries WHERE cache_key = {param}", (cache_key,))
            row = cur.fetchone()
            if row:
                raw_data = row["data"] if isinstance(row, sqlite3.Row) else row[0]
                print(f"[DatabaseService:STALE-FALLBACK 🛡️] Serving stale DB cache for '{cache_key}'")
                return json.loads(raw_data)
            return None
        except Exception as e:
            print(f"[DatabaseService] Error fetching stale fallback: {e}")
            return None
        finally:
            cur.close()
            conn.close()

    def _record_metric(self, is_hit: bool, cache_key: str):
        """Updates hit/miss counters in cache_metrics and increments key hit count."""
        conn = self.get_connection()
        cur = conn.cursor()
        try:
            param = "%s" if self.db_type == "mysql" else "?"
            if is_hit:
                cur.execute(f"UPDATE cache_metrics SET hits = hits + 1, saved_usd = saved_usd + {self.cost_per_query_usd} WHERE id = 1;")
                cur.execute(f"UPDATE cache_entries SET hit_count = hit_count + 1 WHERE cache_key = {param};", (cache_key,))
            else:
                cur.execute("UPDATE cache_metrics SET misses = misses + 1 WHERE id = 1;")

            if self.db_type != "mysql":
                conn.commit()
        except Exception as e:
            pass
        finally:
            cur.close()
            conn.close()

    def get_stats(self) -> Dict[str, Any]:
        """Returns live statistics from the database."""
        conn = self.get_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT hits, misses, saved_usd FROM cache_metrics WHERE id = 1;")
            m_row = cur.fetchone()
            hits = (m_row["hits"] if isinstance(m_row, sqlite3.Row) else m_row[0]) if m_row else 0
            misses = (m_row["misses"] if isinstance(m_row, sqlite3.Row) else m_row[1]) if m_row else 0
            saved_usd = (m_row["saved_usd"] if isinstance(m_row, sqlite3.Row) else m_row[2]) if m_row else 0.0

            cur.execute("SELECT COUNT(*) FROM cache_entries;")
            c_row = cur.fetchone()
            total_entries = (c_row[0] if not isinstance(c_row, sqlite3.Row) else c_row["COUNT(*)"]) if c_row else 0

            cur.execute("SELECT COUNT(*) FROM live_events;")
            e_row = cur.fetchone()
            total_events = (e_row[0] if not isinstance(e_row, sqlite3.Row) else e_row["COUNT(*)"]) if e_row else 0

            total_requests = hits + misses
            hit_rate_pct = (hits / total_requests * 100) if total_requests > 0 else 0.0
            saved_inr = saved_usd * self.usd_to_inr

            db_display = "Hostinger MySQL / MariaDB" if self.db_type == "mysql" else f"SQL Database (SQLite WAL: {self.sqlite_path.name})"

            return {
                "database_engine": db_display,
                "db_type": self.db_type,
                "total_cache_keys": total_entries,
                "total_stored_events": total_events,
                "hits": hits,
                "misses": misses,
                "hit_rate": f"{hit_rate_pct:.1f}%",
                "total_saved_usd": f"${saved_usd:.3f}",
                "total_saved_inr": f"₹{saved_inr:.1f}",
                "strategy": "Database-backed Dual Layer (L1 RAM + SQL ACID Storage) with 6h Movies / 4h Events TTL"
            }
        except Exception as e:
            return {
                "database_engine": self.db_type,
                "error": str(e)
            }
        finally:
            cur.close()
            conn.close()

    def save_swiggy_tokens(self, access_token: str, refresh_token: Optional[str] = None, expires_in: float = 432000.0):
        """Persist Swiggy OAuth tokens into Database."""
        expires_at = time.time() + float(expires_in)
        conn = self.get_connection()
        cur = conn.cursor()
        try:
            param = "%s" if self.db_type == "mysql" else "?"
            if self.db_type == "mysql":
                cur.execute(f"""
                INSERT INTO swiggy_auth (id, access_token, refresh_token, expires_at)
                VALUES (1, {param}, {param}, {param})
                ON DUPLICATE KEY UPDATE
                    access_token = VALUES(access_token),
                    refresh_token = VALUES(refresh_token),
                    expires_at = VALUES(expires_at);
                """, (access_token, refresh_token or "", expires_at))
            else:
                cur.execute(f"""
                INSERT OR REPLACE INTO swiggy_auth (id, access_token, refresh_token, expires_at)
                VALUES (1, {param}, {param}, {param});
                """, (access_token, refresh_token or "", expires_at))
                conn.commit()
            print("[DatabaseService] Swiggy OAuth tokens saved successfully.")
        except Exception as e:
            print(f"[DatabaseService] Error saving Swiggy tokens: {e}")
        finally:
            cur.close()
            conn.close()

    def get_swiggy_tokens(self) -> Optional[Dict[str, Any]]:
        """Fetch active Swiggy OAuth tokens from Database."""
        conn = self.get_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT access_token, refresh_token, expires_at FROM swiggy_auth WHERE id = 1;")
            row = cur.fetchone()
            if row:
                access_token = row["access_token"] if isinstance(row, sqlite3.Row) else row[0]
                refresh_token = row["refresh_token"] if isinstance(row, sqlite3.Row) else row[1]
                expires_at = row["expires_at"] if isinstance(row, sqlite3.Row) else row[2]
                return {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "expires_at": expires_at,
                    "is_expired": time.time() >= expires_at
                }
            return None
        except Exception as e:
            print(f"[DatabaseService] Error getting Swiggy tokens: {e}")
            return None
        finally:
            cur.close()
            conn.close()

    def delete_swiggy_tokens(self):
        """Remove Swiggy OAuth tokens on disconnect."""
        conn = self.get_connection()
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM swiggy_auth WHERE id = 1;")
            if self.db_type != "mysql":
                conn.commit()
            print("[DatabaseService] Swiggy OAuth tokens cleared.")
        except Exception as e:
            pass
        finally:
            cur.close()
            conn.close()

    # =========================================================================
    # VDC-INHERITED FEATURE 1: Trip Share & Fork System
    # =========================================================================
    def save_shared_trip(
        self,
        title: str,
        destination: str,
        origin: str,
        days: int,
        budget_inr: float,
        itinerary_data: Dict[str, Any],
        creator_name: str = "Traveler"
    ) -> str:
        """Saves a trip and returns a short, viral share code like TRIP-7K2P."""
        import uuid
        share_code = f"TRIP-{uuid.uuid4().hex[:6].upper()}"
        data_json = json.dumps(itinerary_data, ensure_ascii=False)
        conn = self.get_connection()
        cur = conn.cursor()
        param = "%s" if self.db_type == "mysql" else "?"
        try:
            cur.execute(f"""
            INSERT INTO shared_trips (share_code, title, destination, origin, days, budget_inr, itinerary_data, creator_name, fork_count)
            VALUES ({param}, {param}, {param}, {param}, {param}, {param}, {param}, {param}, 0);
            """, (share_code, title, destination, origin or "", days or 1, budget_inr or 0.0, data_json, creator_name))
            if self.db_type != "mysql":
                conn.commit()
            return share_code
        finally:
            cur.close()
            conn.close()

    def get_shared_trip(self, share_code: str) -> Optional[Dict[str, Any]]:
        """Retrieves a shared trip by share code."""
        conn = self.get_connection()
        cur = conn.cursor()
        param = "%s" if self.db_type == "mysql" else "?"
        try:
            cur.execute(f"SELECT * FROM shared_trips WHERE share_code = {param};", (share_code.strip().upper(),))
            row = cur.fetchone()
            if not row:
                return None
            return {
                "share_code": row["share_code"] if isinstance(row, sqlite3.Row) else row[0],
                "title": row["title"] if isinstance(row, sqlite3.Row) else row[1],
                "destination": row["destination"] if isinstance(row, sqlite3.Row) else row[2],
                "origin": row["origin"] if isinstance(row, sqlite3.Row) else row[3],
                "days": row["days"] if isinstance(row, sqlite3.Row) else row[4],
                "budget_inr": row["budget_inr"] if isinstance(row, sqlite3.Row) else row[5],
                "itinerary": json.loads(row["itinerary_data"] if isinstance(row, sqlite3.Row) else row[6]),
                "creator_name": row["creator_name"] if isinstance(row, sqlite3.Row) else row[7],
                "fork_count": row["fork_count"] if isinstance(row, sqlite3.Row) else row[8],
                "created_at": str(row["created_at"] if isinstance(row, sqlite3.Row) else row[9]),
            }
        finally:
            cur.close()
            conn.close()

    def fork_shared_trip(self, share_code: str) -> Optional[Dict[str, Any]]:
        """Increments fork counter and returns the itinerary ready for user customization."""
        conn = self.get_connection()
        cur = conn.cursor()
        param = "%s" if self.db_type == "mysql" else "?"
        try:
            code = share_code.strip().upper()
            cur.execute(f"UPDATE shared_trips SET fork_count = fork_count + 1 WHERE share_code = {param};", (code,))
            if self.db_type != "mysql":
                conn.commit()
            return self.get_shared_trip(code)
        finally:
            cur.close()
            conn.close()

    # =========================================================================
    # VDC-INHERITED FEATURE 2: Dual-Layer User Memory (Facts vs Recollections)
    # =========================================================================
    def upsert_user_memory(
        self,
        user_id: str,
        layer: str,       # 'fact' | 'recollection'
        topic: str,       # 'budget_tier' | 'diet' | 'dining_vibe' | 'home_city' | 'companion_style'
        content: str,
        confidence: float = 1.0,
        source: str = "chat",
        pointer_id: Optional[str] = None
    ):
        """Stores user preference partitioned cleanly by layer (authoritative fact vs fuzzy recollection)."""
        import uuid
        mem_id = f"mem_{uuid.uuid4().hex[:8]}"
        conn = self.get_connection()
        cur = conn.cursor()
        param = "%s" if self.db_type == "mysql" else "?"
        try:
            # Check if this topic already exists for the user in this layer
            cur.execute(f"""
            SELECT id FROM user_memory WHERE user_id = {param} AND layer = {param} AND topic = {param};
            """, (user_id, layer, topic))
            existing = cur.fetchone()
            if existing:
                e_id = existing["id"] if isinstance(existing, sqlite3.Row) else existing[0]
                cur.execute(f"""
                UPDATE user_memory SET content = {param}, confidence = {param}, source = {param}, updated_at = CURRENT_TIMESTAMP
                WHERE id = {param};
                """, (content, confidence, source, e_id))
            else:
                cur.execute(f"""
                INSERT INTO user_memory (id, user_id, layer, topic, content, confidence, source, pointer_id)
                VALUES ({param}, {param}, {param}, {param}, {param}, {param}, {param}, {param});
                """, (mem_id, user_id, layer, topic, content, confidence, source, pointer_id or ""))
            if self.db_type != "mysql":
                conn.commit()
        finally:
            cur.close()
            conn.close()

    def get_user_memory(self, user_id: str) -> Dict[str, Any]:
        """Returns structured facts and ranked fuzzy recollections for the user."""
        conn = self.get_connection()
        cur = conn.cursor()
        param = "%s" if self.db_type == "mysql" else "?"
        try:
            cur.execute(f"SELECT layer, topic, content, confidence, source FROM user_memory WHERE user_id = {param};", (user_id,))
            rows = cur.fetchall()
            facts = {}
            recollections = []
            for r in rows:
                layer = r["layer"] if isinstance(r, sqlite3.Row) else r[0]
                topic = r["topic"] if isinstance(r, sqlite3.Row) else r[1]
                content = r["content"] if isinstance(r, sqlite3.Row) else r[2]
                conf = r["confidence"] if isinstance(r, sqlite3.Row) else r[3]
                src = r["source"] if isinstance(r, sqlite3.Row) else r[4]
                if layer == "fact":
                    facts[topic] = content
                else:
                    recollections.append({"topic": topic, "content": content, "confidence": conf, "source": src})
            return {"facts": facts, "recollections": recollections}
        finally:
            cur.close()
            conn.close()


# Singleton Database Service
db_service = DatabaseService()
