"""Authentication and session caching for TBO Hotel API."""
import json
import urllib.request
from datetime import datetime, timedelta
from typing import Optional

from app.config import settings

_cached_token: Optional[str] = None
_token_expiry: Optional[datetime] = None
_cached_ip: Optional[str] = None

TBO_AUTH_URL = "https://Sharedapi.tektravels.com/SharedData.svc/rest/Authenticate"


def get_hotel_outbound_ip() -> str:
    """Detects server's outbound public IPv4 address for TBO whitelisting."""
    global _cached_ip
    if _cached_ip:
        return _cached_ip

    try:
        req = urllib.request.Request("https://api.ipify.org", headers={"User-Agent": "Plan4U-Backend"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            _cached_ip = resp.read().decode("utf-8").strip()
            return _cached_ip
    except Exception:
        return "122.161.45.12"


def is_hotel_api_configured() -> bool:
    """Checks if TBO credentials exist in settings."""
    username = settings.TBO_HOTEL_USERNAME or settings.TBO_USERNAME
    password = settings.TBO_HOTEL_PASSWORD or settings.TBO_PASSWORD
    return bool(username and password)


def authenticate_tbo_hotel() -> Optional[str]:
    """Authenticates with TBO and returns cached TokenId."""
    global _cached_token, _token_expiry

    if not is_hotel_api_configured():
        return None

    if _cached_token and _token_expiry and datetime.utcnow() < _token_expiry:
        return _cached_token

    username = settings.TBO_HOTEL_USERNAME or settings.TBO_USERNAME
    password = settings.TBO_HOTEL_PASSWORD or settings.TBO_PASSWORD
    end_user_ip = get_hotel_outbound_ip()

    payload = {
        "ClientId": settings.TBO_CLIENT_ID or "ApiIntegrationNew",
        "UserName": username,
        "Password": password,
        "EndUserIp": end_user_ip,
    }

    try:
        req = urllib.request.Request(
            TBO_AUTH_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("Status") == 1 and data.get("TokenId"):
                _cached_token = data["TokenId"]
                _token_expiry = datetime.utcnow() + timedelta(hours=20)
                return _cached_token
    except Exception as e:
        print(f"[HotelService:Auth] TBO Hotel Authentication failed: {e}")

    return None
