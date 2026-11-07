"""Authentication and session management for TBO Air Service."""
import json
import urllib.request
from datetime import datetime, timedelta
from typing import Optional

from app.config import settings

# Memory cache for TBO session token
_cached_token: Optional[str] = None
_token_expiry: Optional[datetime] = None
_cached_ip: Optional[str] = None

TBO_AUTH_URL = "https://Sharedapi.tektravels.com/SharedData.svc/rest/Authenticate"


def get_server_public_ip() -> str:
    """Detects server's outbound public IPv4 address for TBO IP whitelisting."""
    global _cached_ip
    if _cached_ip:
        return _cached_ip

    try:
        req = urllib.request.Request("https://api.ipify.org", headers={"User-Agent": "Plan4U-Backend"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            _cached_ip = resp.read().decode("utf-8").strip()
            return _cached_ip
    except Exception:
        return "122.161.45.12"  # Fallback IP


def is_flight_api_configured() -> bool:
    """Returns True if TBO air credentials are provided in settings."""
    return bool(settings.TBO_USERNAME and settings.TBO_PASSWORD)


def authenticate_tbo_air() -> Optional[str]:
    """Authenticates with TBO Air Service and caches the TokenId."""
    global _cached_token, _token_expiry

    if not is_flight_api_configured():
        return None

    # Return valid cached token if available
    if _cached_token and _token_expiry and datetime.utcnow() < _token_expiry:
        return _cached_token

    end_user_ip = get_server_public_ip()
    payload = {
        "ClientId": settings.TBO_CLIENT_ID or "ApiIntegrationNew",
        "UserName": settings.TBO_USERNAME,
        "Password": settings.TBO_PASSWORD,
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
        print(f"[FlightService:Auth] TBO Authentication failed: {e}")

    return None
