"""Per-user storage for Swiggy OAuth tokens, encrypted at rest with Fernet."""
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings
from app.services.database_service import db_service, DATA_STORE_DIR

logger = logging.getLogger(__name__)

DEV_KEY_FILE = DATA_STORE_DIR / ".swiggy_token_key"


def _load_fernet() -> Fernet:
    if settings.SWIGGY_TOKEN_ENCRYPTION_KEY:
        return Fernet(settings.SWIGGY_TOKEN_ENCRYPTION_KEY.encode("utf-8"))
    if settings.ENV == "production":
        raise RuntimeError("SWIGGY_TOKEN_ENCRYPTION_KEY must be set when ENV=production.")
    if not DEV_KEY_FILE.exists():
        DEV_KEY_FILE.write_bytes(Fernet.generate_key())
        try:
            os.chmod(DEV_KEY_FILE, 0o600)
        except OSError:
            pass
    return Fernet(DEV_KEY_FILE.read_bytes())


class SwiggyTokenStore:
    """One row per app user: encrypted access token, encrypted refresh token, expiry."""

    def __init__(self):
        self.db = db_service
        self._fernet = _load_fernet()
        self._init_schema()

    @property
    def _mysql(self) -> bool:
        return self.db.db_type == "mysql"

    @property
    def _param(self) -> str:
        return "%s" if self._mysql else "?"

    def _init_schema(self):
        conn = self.db.get_connection()
        cur = conn.cursor()
        try:
            if self._mysql:
                cur.execute("""
                CREATE TABLE IF NOT EXISTS swiggy_user_auth (
                    user_id VARCHAR(128) PRIMARY KEY,
                    access_token TEXT NOT NULL,
                    refresh_token TEXT,
                    expires_at DOUBLE NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)
            else:
                cur.execute("""
                CREATE TABLE IF NOT EXISTS swiggy_user_auth (
                    user_id TEXT PRIMARY KEY,
                    access_token TEXT NOT NULL,
                    refresh_token TEXT,
                    expires_at REAL NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)
                conn.commit()
        finally:
            cur.close()
            conn.close()

    def _encrypt(self, value: Optional[str]) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8") if value else ""

    def _decrypt(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        try:
            return self._fernet.decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            logger.error("Stored Swiggy token could not be decrypted (key changed?).")
            return None

    def encrypt_text(self, value: Optional[str]) -> str:
        """Encrypts arbitrary text with the same key (used for stored third-party phone numbers)."""
        return self._encrypt(value)

    def decrypt_text(self, value: Optional[str]) -> Optional[str]:
        return self._decrypt(value)

    def save(self, user_id: str, access_token: str, refresh_token: Optional[str], expires_in: float):
        expires_at = time.time() + float(expires_in)
        conn = self.db.get_connection()
        cur = conn.cursor()
        p = self._param
        try:
            if self._mysql:
                cur.execute(f"""
                INSERT INTO swiggy_user_auth (user_id, access_token, refresh_token, expires_at)
                VALUES ({p}, {p}, {p}, {p})
                ON DUPLICATE KEY UPDATE access_token = VALUES(access_token),
                    refresh_token = VALUES(refresh_token), expires_at = VALUES(expires_at);
                """, (user_id, self._encrypt(access_token), self._encrypt(refresh_token), expires_at))
            else:
                cur.execute(f"""
                INSERT OR REPLACE INTO swiggy_user_auth (user_id, access_token, refresh_token, expires_at)
                VALUES ({p}, {p}, {p}, {p});
                """, (user_id, self._encrypt(access_token), self._encrypt(refresh_token), expires_at))
                conn.commit()
        finally:
            cur.close()
            conn.close()

    def get(self, user_id: str) -> Optional[Dict[str, Any]]:
        conn = self.db.get_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                f"SELECT access_token, refresh_token, expires_at FROM swiggy_user_auth WHERE user_id = {self._param};",
                (user_id,),
            )
            row = cur.fetchone()
        finally:
            cur.close()
            conn.close()
        if not row:
            return self._migrate_legacy(user_id)
        access, refresh, expires_at = (
            (row["access_token"], row["refresh_token"], row["expires_at"])
            if isinstance(row, sqlite3.Row) else (row[0], row[1], row[2])
        )
        access = self._decrypt(access)
        if not access:
            return None
        return {"access_token": access, "refresh_token": self._decrypt(refresh), "expires_at": expires_at}

    def delete(self, user_id: str):
        conn = self.db.get_connection()
        cur = conn.cursor()
        try:
            cur.execute(f"DELETE FROM swiggy_user_auth WHERE user_id = {self._param};", (user_id,))
            if not self._mysql:
                conn.commit()
        finally:
            cur.close()
            conn.close()

    def _migrate_legacy(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Moves the old single global token into the service user's row, once."""
        if not settings.SWIGGY_SERVICE_USER_ID or user_id != settings.SWIGGY_SERVICE_USER_ID:
            return None
        legacy = self.db.get_swiggy_tokens()
        if not legacy or not legacy.get("access_token"):
            return None
        remaining = max(legacy["expires_at"] - time.time(), 0)
        self.save(user_id, legacy["access_token"], legacy.get("refresh_token") or None, remaining)
        self.db.delete_swiggy_tokens()
        logger.info("Migrated legacy global Swiggy token to the service user.")
        return self.get(user_id)


swiggy_token_store = SwiggyTokenStore()
