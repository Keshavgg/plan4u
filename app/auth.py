"""Request authentication: identifies the calling app user from a Firebase ID token.

Send `Authorization: Bearer <Firebase ID token>`. The token is verified against Google's
public keys and must be issued for FIREBASE_PROJECT_ID.

Local development without Firebase: when ENV is not "production" and FIREBASE_PROJECT_ID is
unset, an `X-Dev-User: <name>` header is accepted instead. That path is disabled in production.
"""
import logging
from typing import Optional

from fastapi import Header, HTTPException

from app.config import settings

logger = logging.getLogger(__name__)

_DEV_USER_PREFIX = "dev:"


def _verify_firebase_token(token: str) -> str:
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    try:
        claims = id_token.verify_firebase_token(
            token, google_requests.Request(), audience=settings.FIREBASE_PROJECT_ID
        )
    except Exception as e:
        logger.info("Firebase token rejected: %s", e)
        claims = None
    if not claims or not claims.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid or expired login token.")
    return claims["sub"]


def get_optional_user(
    authorization: Optional[str] = Header(None),
    x_dev_user: Optional[str] = Header(None, alias="X-Dev-User"),
) -> Optional[str]:
    """Like get_current_user, but anonymous callers get None instead of a 401."""
    if not authorization and not x_dev_user:
        return None
    return get_current_user(authorization, x_dev_user)


def get_current_user(
    authorization: Optional[str] = Header(None),
    x_dev_user: Optional[str] = Header(None, alias="X-Dev-User"),
) -> str:
    """FastAPI dependency returning the authenticated app user id."""
    if settings.FIREBASE_PROJECT_ID:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Login required.")
        return _verify_firebase_token(authorization[7:].strip())

    if settings.ENV != "production" and x_dev_user and x_dev_user.strip():
        logger.warning("Using X-Dev-User authentication (development only).")
        return _DEV_USER_PREFIX + x_dev_user.strip()

    raise HTTPException(status_code=401, detail="Login required.")
