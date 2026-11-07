"""Booking a Dineout table from chat.

The LLM only understands the request and the booking is *prepared* (validated, summary shown). Nothing is booked
until the user presses the confirm button, which calls the authenticated confirm endpoint directly. The model
never confirms anything.
"""
import datetime
import logging
import re
from typing import Any, Dict, List, Optional

from app.agent.state import CompanionState
from app.schemas.agent import LiveCopilotQuery, LiveCopilotResponse
from app.services import dineout_booking_service as booking_service
from app.services.booking_store import booking_store
from app.services.swiggy_mcp_service import (
    SwiggyAuthRequired,
    SwiggyError,
    swiggy_mcp_service,
)

logger = logging.getLogger(__name__)

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
MAX_CHOICES_SHOWN = 4
NEAREST_TIMES_SHOWN = 4
MAX_DAYS_AHEAD = 7  # the slots tool covers 7 days from the requested date


def _reply(text: str, card: Optional[Dict[str, Any]] = None) -> LiveCopilotResponse:
    return LiveCopilotResponse(reply_text=text, action_card=card)


def _display_time(hhmm: str) -> Optional[str]:
    try:
        return datetime.datetime.strptime(hhmm, "%H:%M").strftime("%I:%M %p")
    except (TypeError, ValueError):
        return None


def _minutes(display_time: str) -> int:
    t = datetime.datetime.strptime(display_time, "%I:%M %p")
    return t.hour * 60 + t.minute


def _name_tokens(name: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", (name or "").lower()) if len(w) >= 3}


def _pick_restaurant(results: List[Dict[str, Any]], wanted: str) -> List[Dict[str, Any]]:
    """Restaurants from a search that match the requested name (one means a clear match)."""
    wanted_low = " ".join(re.findall(r"[a-z0-9]+", wanted.lower()))
    exact = [r for r in results if " ".join(re.findall(r"[a-z0-9]+", r["name"].lower())) == wanted_low]
    if exact:
        return exact[:1]
    wanted_tokens = _name_tokens(wanted)
    close = [r for r in results if wanted_tokens and (wanted_tokens <= _name_tokens(r["name"])
                                                       or _name_tokens(r["name"]) <= wanted_tokens)]
    return close


def _connect_card() -> Dict[str, Any]:
    return {
        "type": "connect_swiggy",
        "title": "Connect Swiggy to book",
        "text": "Booking aapke apne Swiggy account se hoti hai. Ek baar number aur OTP Swiggy ke page par dalna hoga.",
        "button": {"label": "Connect Swiggy", "method": "POST", "url": "/api/v1/swiggy/connect"},
        "attribution": booking_service.ATTRIBUTION,
    }


def try_handle(query: LiveCopilotQuery, state: CompanionState, user_id: Optional[str],
               details: Dict[str, Any]) -> Optional[LiveCopilotResponse]:
    """Returns a chat response if the message is a table-booking request, else None (normal copilot flow).

    `details` is the "booking" part of the combined message analysis.
    """
    if not details or not details.get("book_table"):
        return None

    if not user_id:
        return _reply("Table book karne ke liye pehle login chahiye.")
    if not swiggy_mcp_service.is_authenticated(user_id):
        return _reply("Booking ke liye pehle apna Swiggy account connect karo, phir main wahi booking tayyar kar dunga.",
                      _connect_card())

    name = (details.get("restaurant_name") or "").strip()
    date = details.get("date")
    time_24 = details.get("time")
    guests = details.get("guests")

    missing = [label for label, value in (("kaun sa restaurant", name), ("kis din", date),
                                          ("kitne baje", time_24), ("kitne log", guests)) if not value]
    if missing:
        return _reply("Booking ke liye bas ye bata do: " + ", ".join(missing) + ".")

    try:
        guests = int(guests)
        day = datetime.date.fromisoformat(date)
    except (TypeError, ValueError):
        return _reply("Date ya log ki sankhya samajh nahi aayi. Dobara bata do, jaise 'kal 8 baje 2 log'.")
    today = datetime.datetime.now(IST).date()
    if not 1 <= guests <= 20:
        return _reply("Ek booking mein 1 se 20 log hi ho sakte hain.")
    if day < today:
        return _reply("Ye date nikal chuki hai. Aaj ya aage ki date bata do.")
    if (day - today).days > MAX_DAYS_AHEAD:
        return _reply(f"Dineout mein abhi se {MAX_DAYS_AHEAD} din aage tak hi slots dikhte hain. Isse pehle ki date bata do.")
    wanted_display = _display_time(time_24)
    if not wanted_display:
        return _reply("Time samajh nahi aaya. Jaise '8 baje raat' ya '1 PM' bata do.")

    lat, lng = query.current_lat, query.current_lng
    try:
        found = swiggy_mcp_service.search_swiggy_dineout(user_id, name, lat, lng, limit=8)
        matches = _pick_restaurant(found, name)
        if not matches:
            if found:
                options = ", ".join(r["name"] for r in found[:MAX_CHOICES_SHOWN])
                return _reply(f"'{name}' Dineout par nahi mila. Ye mile: {options}. Inme se koi chahiye?")
            return _reply(f"'{name}' Dineout par nahi mila. Naam dobara check kar lo.")
        if len(matches) > 1:
            options = ", ".join(r["name"] for r in matches[:MAX_CHOICES_SHOWN])
            return _reply(f"Kai restaurants match hue: {options}. Kaun sa wala?")
        restaurant = matches[0]

        slots = swiggy_mcp_service.get_dineout_slots(user_id, restaurant["dineout_id"], date, lat, lng)
        deal = next((d for d in slots["deals"] if d["date"] == date), None)
        if not deal:
            return _reply(f"{restaurant['name']} mein {date} ko koi slot nahi hai. Koi aur din bata do.")
        if not deal["is_free"]:
            return _reply(f"{restaurant['name']} ki is din ki booking paid hai, jo abhi yahan se nahi hoti. "
                          "Swiggy app se kar lo, ya koi free slot wala din bata do.")

        slot = next((s for s in slots["slots"] if s["display_time"] == wanted_display), None)
        if not slot:
            ranked = sorted(slots["slots"], key=lambda s: abs(_minutes(s["display_time"]) - _minutes(wanted_display)))
            nearest = ", ".join(s["display_time"] for s in ranked[:NEAREST_TIMES_SHOWN])
            return _reply(f"{wanted_display} par slot nahi hai. Paas ke time: {nearest}. Kaun sa chalega?")

        contact_alias = details.get("for_contact") or None
        if contact_alias and not booking_store.get_contact(user_id, contact_alias):
            contact_alias = None

        summary = booking_service.prepare(
            user_id, restaurant_id=restaurant["dineout_id"], date=date, slot_id=deal["slot_id"],
            item_id=deal["item_id"], reservation_time=slot["reservation_time"], guest_count=guests,
            lat=lat, lng=lng, contact_alias=contact_alias,
        )
    except booking_service.BookingError as e:
        return _reply(str(e))
    except SwiggyAuthRequired:
        return _reply("Swiggy session khatam ho gaya. Dobara connect karo.", _connect_card())
    except SwiggyError as e:
        return _reply(f"Swiggy se baat nahi ho paayi ({e}). Thodi der baad dobara try karo.")

    card = {
        "type": "booking_confirmation",
        "title": "Book this table?",
        "booking_id": summary["booking_id"],
        "restaurant": restaurant["name"],
        "area": restaurant.get("locality"),
        "date": summary["date"],
        "time": summary["time"],
        "guest_count": summary["guest_count"],
        "for_contact": summary["for_contact"],
        "notice": summary["notice"],
        "expires_at": summary["expires_at"],
        "confirm": {"label": "Yes, book it", "method": "POST",
                    "url": f"/api/v1/bookings/dineout/{summary['booking_id']}/confirm"},
        "dismiss": {"label": "No", "method": "POST",
                    "url": f"/api/v1/bookings/dineout/{summary['booking_id']}/dismiss"},
        "attribution": summary["attribution"],
    }
    return _reply("Booking tayyar hai. Neeche dekh lo, aur theek ho to confirm karo. Tab tak kuch book nahi hua.", card)
