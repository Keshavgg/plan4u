"""Swiggy MCP client (Food, Dineout, Instamart, Scenes).

Talks to Swiggy's official MCP servers (https://mcp.swiggy.com/<server>) over Streamable HTTP
with OAuth 2.1 + PKCE. Docs: https://mcp.swiggy.com/builders/docs/

- The OAuth client registers itself once via Dynamic Client Registration (RFC 7591); no
  client id has to be applied for. The registration is persisted in the database.
- Every call runs as one app user: each user connects their own Swiggy account once (phone +
  OTP on Swiggy's page) and their tokens are stored encrypted, one row per user.
- Read-only discovery (search, details, slots) may fall back to the account of
  SWIGGY_SERVICE_USER_ID when the caller has not connected. Bookings and Instamart never do.
- Tool results come back as structured JSON, JSON text or a plain-text report; this module
  returns the data and raises SwiggyError on failure.
"""
import base64
import hashlib
import json
import logging
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.services.database_service import db_service
from app.services.swiggy_token_store import swiggy_token_store

logger = logging.getLogger(__name__)

SCOPE = "mcp:tools"
PKCE_TTL_SECONDS = 600
MCP_TIMEOUT_SECONDS = 20
AUTH_TIMEOUT_SECONDS = 10
CLIENT_REGISTRATION_TTL_SECONDS = 365 * 24 * 3600
MCP_PROTOCOL_VERSION = "2025-03-26"
# Refresh proactively when <= 60s remain (per the Swiggy docs).
REFRESH_MARGIN_SECONDS = 60
# Retry guidance from the docs: upstream 502/503/504 are retried with exponential backoff.
MAX_UPSTREAM_RETRIES = 3
BACKOFF_BASE_SECONDS = 0.5
# Which tools a server exposes depends on the account (some are rolled out gradually).
TOOL_LIST_TTL_SECONDS = 600

# In-flight PKCE verifiers keyed by OAuth state; each remembers which app user started the flow.
PKCE_VERIFIERS: Dict[str, Dict[str, Any]] = {}


class SwiggyError(Exception):
    """A Swiggy MCP call failed (domain failure, transport failure or bad response)."""


class SwiggyAuthRequired(SwiggyError):
    """No valid Swiggy session; the user must complete the OAuth flow."""


class SwiggyMcpService:
    """Client for the Swiggy MCP platform."""

    def __init__(self):
        self.base_url = settings.SWIGGY_MCP_BASE_URL.rstrip("/")
        self.redirect_uri = settings.SWIGGY_REDIRECT_URI
        self.db = db_service
        self.tokens = swiggy_token_store
        self._sessions: Dict[Tuple[str, str], str] = {}  # (user_id, server) -> Mcp-Session-Id
        self._tool_cache: Dict[Tuple[str, str], Tuple[float, set]] = {}  # (user_id, server) -> (fetched_at, names)
        self._lock = threading.Lock()

    # -------------------------------------------------------------
    # Which account serves a request
    # -------------------------------------------------------------
    def service_user_id(self) -> Optional[str]:
        """The app user whose Swiggy account serves read-only discovery, if configured."""
        return settings.SWIGGY_SERVICE_USER_ID or None

    def discovery_actor(self, user_id: Optional[str]) -> str:
        """The account that serves read-only discovery (search, details, slots).

        A user who has connected Swiggy always searches with their own token. Everyone else
        (not connected, or not signed in) falls back to the service account. Bookings never use
        the fallback: they run as the signed-in user.
        """
        if user_id and self.is_authenticated(user_id):
            return user_id
        service = self.service_user_id()
        if service and self.is_authenticated(service):
            return service
        raise SwiggyAuthRequired("Swiggy account is not connected.")

    # -------------------------------------------------------------
    # OAuth 2.1 + PKCE with Dynamic Client Registration
    # -------------------------------------------------------------
    def _post_json(self, url: str, payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "Plan4U-App/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body.strip() else {}

    def get_client_id(self) -> str:
        """Returns the OAuth client id, registering this app with Swiggy on first use."""
        if settings.SWIGGY_CLIENT_ID:
            return settings.SWIGGY_CLIENT_ID

        cache_key = f"swiggy_client:{self.redirect_uri}"
        cached = self.db.get_cache(cache_key, ttl_seconds=CLIENT_REGISTRATION_TTL_SECONDS)
        if cached and cached[0].get("client_id"):
            return cached[0]["client_id"]

        try:
            reg = self._post_json(f"{self.base_url}/auth/register", {
                "client_name": "Plan4U",
                "redirect_uris": [self.redirect_uri],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
                "scope": SCOPE,
            }, AUTH_TIMEOUT_SECONDS)
        except Exception as e:
            raise SwiggyError(f"Swiggy client registration failed: {e}") from e

        client_id = reg.get("client_id")
        if not client_id:
            raise SwiggyError("Swiggy client registration returned no client_id")
        self.db.set_cache(
            cache_key, [{"client_id": client_id}], category="swiggy", city="",
            ttl_seconds=CLIENT_REGISTRATION_TTL_SECONDS,
        )
        return client_id

    def create_authorization_url(self, user_id: str) -> str:
        """Builds the Swiggy authorize URL for this app user with a fresh PKCE challenge and state."""
        now = time.time()
        for st in [s for s, e in PKCE_VERIFIERS.items() if now - e["created_at"] > PKCE_TTL_SECONDS]:
            PKCE_VERIFIERS.pop(st, None)

        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("utf-8")).digest()).decode("utf-8").rstrip("=")
        state = secrets.token_urlsafe(16)
        PKCE_VERIFIERS[state] = {"verifier": verifier, "user_id": user_id, "created_at": now}

        params = {
            "response_type": "code",
            "client_id": self.get_client_id(),
            "redirect_uri": self.redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "scope": SCOPE,
        }
        return f"{self.base_url}/auth/authorize?{urllib.parse.urlencode(params)}"

    def exchange_code_for_token(self, code: str, state: str) -> Dict[str, Any]:
        """Exchanges the authorization code (valid 120s, single use) and stores the user's tokens."""
        entry = PKCE_VERIFIERS.pop(state, None)
        if not entry or time.time() - entry["created_at"] > PKCE_TTL_SECONDS:
            return {"success": False, "error": "Unknown or expired OAuth state. Start the connection again."}

        try:
            data = self._post_json(f"{self.base_url}/auth/token", {
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": entry["verifier"],
                "redirect_uri": self.redirect_uri,
                "client_id": self.get_client_id(),
            }, AUTH_TIMEOUT_SECONDS)
        except Exception as e:
            logger.warning("Swiggy token exchange failed: %s", e)
            return {"success": False, "error": "Token exchange with Swiggy failed."}

        if not data.get("access_token"):
            return {"success": False, "error": "Swiggy returned no access token."}
        user_id = entry["user_id"]
        self.tokens.save(user_id, data["access_token"], data.get("refresh_token"), data.get("expires_in", 432000))
        self._drop_sessions(user_id)
        return {"success": True, "user_id": user_id}

    def refresh_access_token(self, user_id: str, refresh_token: str) -> Optional[str]:
        """Refreshes the user's access token. Refresh tokens rotate, so the new one is stored."""
        try:
            data = self._post_json(f"{self.base_url}/auth/token", {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.get_client_id(),
            }, AUTH_TIMEOUT_SECONDS)
        except urllib.error.HTTPError as e:
            if e.code == 400:  # invalid_grant: the session is gone, re-authorization needed
                self.tokens.delete(user_id)
            logger.warning("Swiggy token refresh failed: HTTP %s", e.code)
            return None
        except Exception as e:
            logger.warning("Swiggy token refresh failed: %s", e)
            return None

        if not data.get("access_token"):
            return None
        self.tokens.save(
            user_id, data["access_token"], data.get("refresh_token") or refresh_token,
            data.get("expires_in", 2592000),
        )
        return data["access_token"]

    def get_valid_token(self, user_id: str) -> Optional[str]:
        """Returns a usable access token for the user, refreshing it if it is about to expire."""
        stored = self.tokens.get(user_id)
        if not stored:
            return None
        if time.time() + REFRESH_MARGIN_SECONDS < stored["expires_at"]:
            return stored["access_token"]
        if stored.get("refresh_token"):
            return self.refresh_access_token(user_id, stored["refresh_token"])
        return None

    def is_authenticated(self, user_id: str) -> bool:
        return self.get_valid_token(user_id) is not None

    def disconnect(self, user_id: str):
        """Revokes the session at Swiggy (best effort) and deletes the stored tokens."""
        token = self.get_valid_token(user_id)
        if token:
            try:
                req = urllib.request.Request(
                    f"{self.base_url}/auth/logout", data=b"", method="POST",
                    headers={"Authorization": f"Bearer {token}", "User-Agent": "Plan4U-App/1.0"},
                )
                urllib.request.urlopen(req, timeout=AUTH_TIMEOUT_SECONDS).close()
            except Exception as e:
                logger.warning("Swiggy logout call failed: %s", e)
        self.tokens.delete(user_id)
        self._drop_sessions(user_id)

    def _drop_sessions(self, user_id: str):
        with self._lock:
            for key in [k for k in self._sessions if k[0] == user_id]:
                self._sessions.pop(key, None)

    # -------------------------------------------------------------
    # MCP Streamable HTTP transport
    # -------------------------------------------------------------
    @staticmethod
    def _parse_rpc_body(body: str, content_type: str) -> Dict[str, Any]:
        """The server may answer with plain JSON or a text/event-stream carrying the JSON-RPC reply."""
        if "text/event-stream" in content_type:
            last = None
            for line in body.splitlines():
                if line.startswith("data:"):
                    payload = line[5:].strip()
                    if payload:
                        last = payload
            if last is None:
                raise SwiggyError("Empty event-stream response from Swiggy MCP")
            return json.loads(last)
        return json.loads(body)

    def _rpc(self, server: str, token: str, message: Dict[str, Any], session_id: Optional[str]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {token}",
            "User-Agent": "Plan4U-App/1.0",
        }
        if session_id:
            headers["Mcp-Session-Id"] = session_id
        req = urllib.request.Request(
            f"{self.base_url}/{server}", data=json.dumps(message).encode("utf-8"), headers=headers,
        )
        with urllib.request.urlopen(req, timeout=MCP_TIMEOUT_SECONDS) as resp:
            body = resp.read().decode("utf-8")
            new_session = resp.headers.get("Mcp-Session-Id") or session_id
            if not body.strip():
                return None, new_session  # e.g. 202 Accepted for notifications
            return self._parse_rpc_body(body, resp.headers.get("Content-Type", "")), new_session

    def _ensure_session(self, user_id: str, server: str, token: str) -> Optional[str]:
        """Runs the MCP initialize handshake once per (user, server) and remembers the session id."""
        key = (user_id, server)
        with self._lock:
            if key in self._sessions:
                return self._sessions[key]
        init = {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "plan4u", "version": "1.0"},
            },
        }
        _, session_id = self._rpc(server, token, init, None)
        self._rpc(server, token, {"jsonrpc": "2.0", "method": "notifications/initialized"}, session_id)
        with self._lock:
            self._sessions[key] = session_id or ""
        return session_id

    def call_tool(self, user_id: str, server: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Calls an MCP tool as the given user and returns its data payload.

        Raises SwiggyAuthRequired when the user is not connected or the session expired, and
        SwiggyError for domain failures or transport errors.
        """
        token = self.get_valid_token(user_id)
        if not token:
            raise SwiggyAuthRequired("Swiggy account is not connected.")

        for attempt in range(MAX_UPSTREAM_RETRIES + 1):
            try:
                session_id = self._ensure_session(user_id, server, token)
                reply, _ = self._rpc(server, token, {
                    "jsonrpc": "2.0", "id": int(time.time() * 1000), "method": "tools/call",
                    "params": {"name": tool_name, "arguments": arguments},
                }, session_id or None)
                return self._unwrap_tool_result(reply)
            except urllib.error.HTTPError as e:
                if e.code in (401, 419):
                    self._drop_sessions(user_id)
                    if e.code == 419:
                        self.tokens.delete(user_id)
                    raise SwiggyAuthRequired("Swiggy session expired or revoked; reconnect the account.") from e
                if e.code in (502, 503, 504) and attempt < MAX_UPSTREAM_RETRIES:
                    time.sleep(BACKOFF_BASE_SECONDS * (2 ** attempt))
                    continue
                self._drop_sessions(user_id)
                raise SwiggyError(f"Swiggy MCP HTTP {e.code} from /{server}") from e
            except SwiggyError:
                raise
            except Exception as e:
                raise SwiggyError(f"Swiggy MCP call failed: {e}") from e
        raise SwiggyError("Swiggy MCP unavailable after retries")

    def list_tool_names(self, user_id: str, server: str) -> set:
        """Names of the tools this user's account can call on a server (cached for a few minutes)."""
        key = (user_id, server)
        cached = self._tool_cache.get(key)
        if cached and time.time() - cached[0] < TOOL_LIST_TTL_SECONDS:
            return cached[1]

        token = self.get_valid_token(user_id)
        if not token:
            raise SwiggyAuthRequired("Swiggy account is not connected.")
        try:
            session_id = self._ensure_session(user_id, server, token)
            reply, _ = self._rpc(server, token, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                                 session_id or None)
        except urllib.error.HTTPError as e:
            if e.code in (401, 419):
                raise SwiggyAuthRequired("Swiggy session expired; reconnect the account.") from e
            raise SwiggyError(f"Swiggy tools/list failed with HTTP {e.code}") from e
        except Exception as e:
            raise SwiggyError(f"Swiggy tools/list failed: {e}") from e

        names = {t.get("name") for t in ((reply or {}).get("result") or {}).get("tools", []) if t.get("name")}
        self._tool_cache[key] = (time.time(), names)
        return names

    def supports_tool(self, user_id: str, server: str, tool_name: str) -> bool:
        return tool_name in self.list_tool_names(user_id, server)

    @staticmethod
    def _unwrap_tool_result(reply: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not reply:
            raise SwiggyError("Empty response from Swiggy MCP")
        if "error" in reply:
            err = reply["error"]
            if err.get("code") == -32001:
                raise SwiggyAuthRequired("Swiggy session expired; reconnect the account.")
            raise SwiggyError(err.get("message", "Swiggy MCP error"))

        result = reply.get("result", {})
        text = next((c.get("text") for c in result.get("content", []) if c.get("type") == "text"), None)
        if result.get("isError"):
            raise SwiggyError(text or "Swiggy tool reported an error")

        # Tools answer in one of three shapes: structuredContent, JSON text, or plain text.
        envelope = result.get("structuredContent") or None
        if isinstance(envelope, dict) and text and "success" not in envelope:
            try:
                json.loads(text)
            except ValueError:
                # Keep the human-readable report: some tools put the details only there.
                return {**envelope, "text": text}
        if envelope is None:
            if text is None:
                raise SwiggyError("Swiggy MCP result had no content")
            try:
                envelope = json.loads(text)
            except ValueError:
                return {"text": text}

        if isinstance(envelope, dict) and "success" in envelope:
            if not envelope["success"]:
                raise SwiggyError((envelope.get("error") or {}).get("message", "Swiggy tool reported a failure"))
            return envelope.get("data", {})
        return envelope

    # -------------------------------------------------------------
    # Domain helpers (field names follow the tool reference docs)
    # -------------------------------------------------------------
    @staticmethod
    def _number_from_text(text: Optional[str]) -> Optional[float]:
        """'₹400 for two' -> 400.0; None if there is no number."""
        if not text:
            return None
        digits = re.search(r"\d[\d,]*", text)
        return float(digits.group(0).replace(",", "")) if digits else None

    @staticmethod
    def search_url(name: str) -> str:
        """Deep link to Swiggy search. The MCP responses carry no restaurant URL."""
        return f"https://www.swiggy.com/search?query={urllib.parse.quote(name)}"

    def resolve_restaurant_dineout_url(self, name: str, city: str = "") -> str:
        """Deep link for a restaurant name, or the city's Dineout landing page."""
        if (name or "").strip():
            return self.search_url(name.strip())
        slug = re.sub(r"[^a-z0-9]+", "-", (city or "").lower()).strip("-")
        return f"https://www.swiggy.com/dineout/{slug}" if slug else "https://www.swiggy.com/dineout"

    def search_swiggy_food(self, user_id: str, query: str, lat: float, lng: float, limit: int = 4) -> List[Dict[str, Any]]:
        """Food delivery restaurants near a point (tool: search_restaurants on /food)."""
        data = self.call_tool(user_id, "food", "search_restaurants", {
            "query": query.strip(), "latitude": lat, "longitude": lng,
        })
        results = []
        for r in data.get("restaurants", [])[:limit]:
            cost_for_two = self._number_from_text(r.get("costForTwo"))
            results.append({
                "id": f"swiggy_{r.get('id')}",
                "name": r["name"],
                "cuisines": r.get("cuisines", []),
                "rating": r.get("avgRating"),
                "sla_string": r.get("deliveryTimeRange") or (
                    f"{r['deliveryTimeMinutes']} mins" if r.get("deliveryTimeMinutes") else None
                ),
                "cost_for_two": r.get("costForTwo"),
                "cost_per_person": cost_for_two / 2 if cost_for_two else None,
                "locality": r.get("areaName"),
                "offer": r.get("offer"),
                "availability": r.get("availabilityStatus"),
                "image_url": r.get("imageUrl"),
                "distance_km": r.get("distanceKm"),
                "order_url": self.search_url(r["name"]),
                "source": "swiggy_mcp_food",
            })
        return results

    def search_swiggy_dineout(self, user_id: str, query: str, lat: float, lng: float, limit: int = 4) -> List[Dict[str, Any]]:
        """Dineout restaurants near a point (tool: search_restaurants_dineout on /dineout)."""
        data = self.call_tool(user_id, "dineout", "search_restaurants_dineout", {
            "query": query.strip(), "latitude": lat, "longitude": lng, "limit": min(limit, 30),
        })
        # The live server answers with a numbered text list rather than the documented JSON.
        restaurants = data.get("restaurants")
        if restaurants is None:
            restaurants = self._parse_dineout_text(data.get("text", ""))

        results = []
        for r in restaurants[:limit]:
            cost_for_two = self._number_from_text(r.get("costForTwo"))
            offers = r.get("offers") or []
            results.append({
                "id": f"swiggy_dineout_{r.get('id')}",
                "dineout_id": r.get("id"),
                "name": r["name"],
                "cuisines": r.get("cuisine", []),
                "rating": r.get("rating"),
                "cost_for_two": r.get("costForTwo"),
                "cost_per_person": cost_for_two / 2 if cost_for_two else None,
                "locality": r.get("locality"),
                "distance": r.get("distance"),
                "discount_text": offers[0].get("offerTitle") if offers else None,
                "available_deals": r.get("availableDeals", []),
                "booking_url": self.search_url(r["name"]),
                "source": "swiggy_mcp_dineout",
            })
        return results

    @staticmethod
    def _parse_dineout_text(text: str) -> List[Dict[str, Any]]:
        """Parses lines like: '1. Pour Over — Coffee | 4.3★ | ₹1200 for two | Khan Market (ID: 962101)'."""
        restaurants = []
        for line in text.splitlines():
            m = re.match(r"^\s*\d+\.\s+(.*?)\s*\(ID:\s*([^)]+)\)\s*$", line)
            if not m:
                continue
            parts = [p.strip() for p in m.group(1).split(" | ")]
            name, _, cuisine = parts[0].rpartition(" — ")
            if not name:
                name, cuisine = parts[0], ""
            name = re.sub(r"\s*—\s*$", "", name).strip()  # no cuisine listed: the line ends with a bare dash
            rating = cost = area = distance = None
            for part in parts[1:]:
                if "★" in part:
                    num = re.search(r"\d+(?:\.\d+)?", part)
                    rating = float(num.group(0)) if num else None
                elif "for two" in part:
                    cost = part
                elif re.search(r"\d\s*km\b", part):
                    distance = part
                elif part:
                    area = part
            restaurants.append({
                "id": m.group(2).strip(),
                "name": name,
                "cuisine": [c.strip() for c in cuisine.split(",") if c.strip()],
                "rating": rating,
                "costForTwo": cost,
                "locality": area,
                "distance": distance,
            })
        return restaurants

    def search_swiggy_instamart(self, user_id: str, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Instamart products for the user's saved address (tool: search_products on /im)."""
        # A signed-in session must search against one of its saved addresses (guest mode is not allowed).
        addresses = self.call_tool(user_id, "food", "get_addresses", {}).get("addresses", [])
        if not addresses:
            raise SwiggyError("The connected Swiggy account has no saved address. Add one in the Swiggy app first.")
        data = self.call_tool(user_id, "im", "search_products", {
            "query": query.strip(), "addressId": addresses[0]["id"],
        })
        results = []
        for p in data.get("products", [])[:limit]:
            variation = next((v for v in p.get("variations", []) if v.get("isInStockAndAvailable")), None) or (
                p.get("variations") or [None])[0]
            price = (variation or {}).get("price") or {}
            results.append({
                "id": p.get("productId"),
                "title": p.get("displayName"),
                "brand": p.get("brand"),
                "in_stock": p.get("inStock"),
                "quantity": (variation or {}).get("quantityDescription"),
                "mrp": price.get("mrp"),
                "price": price.get("offerPrice"),
                "sla": (variation or {}).get("sla"),
                "delivery_url": f"https://www.swiggy.com/instamart/search?query={urllib.parse.quote(query.strip())}",
                "source": "swiggy_mcp_instamart",
            })
        return results

    # -------------------------------------------------------------
    # Dineout: details, availability and (free-deal) booking
    # -------------------------------------------------------------
    def get_dineout_details(self, user_id: str, restaurant_id: str, lat: float, lng: float) -> Dict[str, Any]:
        """Restaurant profile, offers, timings and amenities (tool: get_restaurant_details)."""
        data = self.call_tool(user_id, "dineout", "get_restaurant_details", {
            "restaurantId": restaurant_id, "latitude": lat, "longitude": lng,
        })
        if "text" in data and "restaurant" not in data:
            raise SwiggyError("Unexpected restaurant details response from Swiggy")
        return {
            "restaurant": data.get("restaurant"),
            "offers": data.get("offers"),
            "amenities": data.get("amenities", []),
            "menu_images": data.get("menuImages", []),
            "map_url": data.get("locationMapUrl"),
            "source": "swiggy_mcp_dineout",
        }

    def get_dineout_slots(self, user_id: str, restaurant_id: str, date: str, lat: float, lng: float) -> Dict[str, Any]:
        """Bookable slots for a date plus per-date booking ids (tool: get_available_slots).

        The server returns a text report; slotId/itemId are listed per date and individual
        slot times are listed for the requested date only.
        """
        data = self.call_tool(user_id, "dineout", "get_available_slots", {
            "restaurantId": restaurant_id, "date": date, "latitude": lat, "longitude": lng,
        })
        text = data.get("text")
        if text is None:
            raise SwiggyError(data.get("message") or "No slot details returned by Swiggy")

        deals = [
            {"date": d, "is_free": kind == "FREE", "slot_id": int(slot_id), "item_id": item_id}
            for d, kind, slot_id, item_id in re.findall(
                r'(\d{4}-\d{2}-\d{2}) \[(FREE|PAID)\]: slotId=(\d+), itemId="([^"]+)"', text)
        ]

        slots: List[Dict[str, Any]] = []
        block = re.search(rf"Slots for {re.escape(date)}:\n((?:[ \t]+.+\n?)+)", text)
        if block:
            for line in block.group(1).splitlines():
                group, _, times = line.strip().partition(":")
                for display, epoch in re.findall(r"(\d{2}:\d{2} [AP]M)→(\d+)", times):
                    slots.append({"group": group, "display_time": display, "reservation_time": int(epoch)})

        return {"restaurant_id": restaurant_id, "date": date, "deals": deals, "slots": slots,
                "source": "swiggy_mcp_dineout"}

    def book_dineout_free_table(
        self,
        user_id: str,
        restaurant_id: str,
        slot_id: int,
        item_id: str,
        reservation_time: int,
        guest_count: int,
        lat: float,
        lng: float,
    ) -> Dict[str, Any]:
        """Books a table on a FREE deal as this user (tool: book_table). Creates a real reservation.

        Paid deals need create_cart, UPI payment and confirm_order and are not supported here.
        """
        return self.call_tool(user_id, "dineout", "book_table", {
            "restaurantId": restaurant_id,
            "slotId": slot_id,
            "itemId": item_id,
            "reservationTime": reservation_time,
            "guestCount": guest_count,
            "latitude": lat,
            "longitude": lng,
        })

    def get_dineout_booking_status(self, user_id: str, order_id: str) -> Dict[str, Any]:
        """Swiggy's own view of a booking (tool: get_booking_status)."""
        return self.call_tool(user_id, "dineout", "get_booking_status", {"orderId": order_id})

    def cancel_dineout_booking(self, user_id: str, order_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
        """Cancels a Dineout booking (tool: cancel_booking). Not rolled out to every account."""
        args: Dict[str, Any] = {"orderId": order_id}
        if reason:
            args["cancellationReason"] = reason
        return self.call_tool(user_id, "dineout", "cancel_booking", args)


# Singleton Swiggy MCP Service
swiggy_mcp_service = SwiggyMcpService()
