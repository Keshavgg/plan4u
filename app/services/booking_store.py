"""Storage for a user's contacts (people they book for) and their Dineout booking records."""
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.services.database_service import db_service
from app.services.swiggy_token_store import swiggy_token_store


class DuplicateAliasError(ValueError):
    """The user already has a contact with this alias."""


class BookingStore:
    def __init__(self):
        self.db = db_service
        self._crypto = swiggy_token_store
        self._init_schema()

    @property
    def _mysql(self) -> bool:
        return self.db.db_type == "mysql"

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self._mysql else sql

    def _run(self, sql: str, params: Tuple = (), fetch: Optional[str] = None):
        """Runs one statement. fetch: 'one' | 'all' | None. Returns (rows, rowcount)."""
        conn = self.db.get_connection()
        cur = conn.cursor()
        try:
            cur.execute(self._sql(sql), params)
            rows = None
            if fetch:
                cols = [d[0] for d in cur.description]
                raw = cur.fetchone() if fetch == "one" else cur.fetchall()
                if fetch == "one":
                    rows = dict(zip(cols, raw)) if raw else None
                else:
                    rows = [dict(zip(cols, r)) for r in raw]
            rowcount = cur.rowcount
            if not self._mysql:
                conn.commit()
            return rows, rowcount
        finally:
            cur.close()
            conn.close()

    def _init_schema(self):
        text_key = "VARCHAR(128)" if self._mysql else "TEXT"
        real = "DOUBLE" if self._mysql else "REAL"
        tail = " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4" if self._mysql else ""
        self._run(f"""
        CREATE TABLE IF NOT EXISTS user_contacts (
            id {text_key} PRIMARY KEY,
            user_id {text_key} NOT NULL,
            alias {text_key} NOT NULL,
            name TEXT NOT NULL,
            phone_enc TEXT,
            created_at {real} NOT NULL,
            UNIQUE (user_id, alias)
        ){tail};
        """)
        self._run(f"""
        CREATE TABLE IF NOT EXISTS dineout_bookings (
            id {text_key} PRIMARY KEY,
            user_id {text_key} NOT NULL,
            contact_alias TEXT,
            contact_name TEXT,
            restaurant_id TEXT NOT NULL,
            restaurant_name TEXT NOT NULL,
            slot_id INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            reservation_time INTEGER NOT NULL,
            reservation_date TEXT NOT NULL,
            display_time TEXT NOT NULL,
            guest_count INTEGER NOT NULL,
            lat {real} NOT NULL,
            lng {real} NOT NULL,
            status TEXT NOT NULL,
            swiggy_order_id TEXT,
            error_message TEXT,
            created_at {real} NOT NULL,
            expires_at {real} NOT NULL,
            confirmed_at {real}
        ){tail};
        """)
        try:
            self._run("ALTER TABLE dineout_bookings ADD COLUMN confirmation_json TEXT")
        except Exception:
            pass  # the column already exists

    # ---------------- contacts ----------------
    def _contact_view(self, row: Dict[str, Any], include_phone: bool = True) -> Dict[str, Any]:
        out = {"id": row["id"], "alias": row["alias"], "name": row["name"], "created_at": row["created_at"]}
        if include_phone:
            out["phone"] = self._crypto.decrypt_text(row.get("phone_enc"))
        return out

    def add_contact(self, user_id: str, alias: str, name: str, phone: Optional[str]) -> Dict[str, Any]:
        alias_key = alias.strip().lower()
        existing, _ = self._run("SELECT id FROM user_contacts WHERE user_id = ? AND alias = ?", (user_id, alias_key), "one")
        if existing:
            raise DuplicateAliasError(f"You already have a contact called '{alias_key}'.")
        contact_id = uuid.uuid4().hex
        now = time.time()
        self._run(
            "INSERT INTO user_contacts (id, user_id, alias, name, phone_enc, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (contact_id, user_id, alias_key, name.strip(), self._crypto.encrypt_text(phone) if phone else "", now),
        )
        return {"id": contact_id, "alias": alias_key, "name": name.strip(), "phone": phone, "created_at": now}

    def list_contacts(self, user_id: str) -> List[Dict[str, Any]]:
        rows, _ = self._run("SELECT * FROM user_contacts WHERE user_id = ? ORDER BY alias", (user_id,), "all")
        return [self._contact_view(r) for r in rows]

    def get_contact(self, user_id: str, alias: str) -> Optional[Dict[str, Any]]:
        row, _ = self._run(
            "SELECT * FROM user_contacts WHERE user_id = ? AND alias = ?", (user_id, alias.strip().lower()), "one")
        return self._contact_view(row) if row else None

    def delete_contact(self, user_id: str, alias: str) -> bool:
        _, count = self._run(
            "DELETE FROM user_contacts WHERE user_id = ? AND alias = ?", (user_id, alias.strip().lower()))
        return count > 0

    # ---------------- bookings ----------------
    def create_booking(self, user_id: str, ttl_seconds: int, **fields: Any) -> Dict[str, Any]:
        booking_id = uuid.uuid4().hex
        now = time.time()
        self._run(
            """INSERT INTO dineout_bookings
               (id, user_id, contact_alias, contact_name, restaurant_id, restaurant_name, slot_id, item_id,
                reservation_time, reservation_date, display_time, guest_count, lat, lng,
                status, created_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)""",
            (booking_id, user_id, fields.get("contact_alias"), fields.get("contact_name"),
             fields["restaurant_id"], fields["restaurant_name"], fields["slot_id"], fields["item_id"],
             fields["reservation_time"], fields["reservation_date"], fields["display_time"],
             fields["guest_count"], fields["lat"], fields["lng"], now, now + ttl_seconds),
        )
        return self.get_booking(user_id, booking_id)

    def get_booking(self, user_id: str, booking_id: str) -> Optional[Dict[str, Any]]:
        row, _ = self._run(
            "SELECT * FROM dineout_bookings WHERE id = ? AND user_id = ?", (booking_id, user_id), "one")
        return row

    def list_bookings(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        rows, _ = self._run(
            "SELECT * FROM dineout_bookings WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit), "all")
        return rows

    def transition(self, user_id: str, booking_id: str, from_status: str, to_status: str) -> bool:
        """Atomic status change; False if the booking was not in from_status (e.g. a double confirm)."""
        _, count = self._run(
            "UPDATE dineout_bookings SET status = ? WHERE id = ? AND user_id = ? AND status = ?",
            (to_status, booking_id, user_id, from_status))
        return count == 1

    def finish(self, user_id: str, booking_id: str, status: str,
               order_id: Optional[str] = None, error: Optional[str] = None,
               confirmation_json: Optional[str] = None):
        self._run(
            "UPDATE dineout_bookings SET status = ?, swiggy_order_id = ?, error_message = ?, confirmed_at = ?, "
            "confirmation_json = COALESCE(?, confirmation_json) WHERE id = ? AND user_id = ?",
            (status, order_id, error, time.time() if status == "CONFIRMED" else None,
             confirmation_json, booking_id, user_id))

    def count_confirmed_since(self, user_id: str, since: float) -> int:
        row, _ = self._run(
            "SELECT COUNT(*) AS n FROM dineout_bookings WHERE user_id = ? AND status IN ('CONFIRMED', 'CONFIRMING', 'UNCERTAIN') "
            "AND created_at >= ?", (user_id, since), "one")
        return int(row["n"]) if row else 0


booking_store = BookingStore()
