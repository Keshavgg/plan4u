"""Two-step Dineout table booking: prepare (validate + summary) then confirm (book).

Reservations are made on the signed-in user's own Swiggy account, so the name on the booking
at the restaurant is theirs. When booking "for" a saved contact, the contact is only recorded
here and used to build a share message; Swiggy's book_table has no guest-name field.
"""
import json
import logging
import re
import time
import urllib.parse
from typing import Any, Dict, Optional

from app.config import settings
from app.services.booking_store import booking_store
from app.services.swiggy_mcp_service import (
    SwiggyAuthRequired,
    SwiggyError,
    swiggy_mcp_service,
)

logger = logging.getLogger(__name__)

ATTRIBUTION = {"service": "dineout", "text": "Powered by Dineout"}
ONE_DAY_SECONDS = 24 * 3600


CANCEL_UNAVAILABLE_MESSAGE = (
    "Cancelling from Plan4U is not available for this Swiggy account yet. "
    "Cancel the booking in the Swiggy Dineout app, or call Swiggy customer care at 080-67466729."
)


def _can_cancel(user_id: str) -> bool:
    """True only if Swiggy exposes cancel_booking for this account."""
    try:
        return swiggy_mcp_service.supports_tool(user_id, "dineout", "cancel_booking")
    except SwiggyError:
        return False


class BookingError(ValueError):
    """A booking request was invalid or cannot proceed (maps to HTTP 4xx)."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _stored_confirmation(booking: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    raw = booking.get("confirmation_json")
    return json.loads(raw) if raw else None


def _build_confirmation(user_id: str, booking: Dict[str, Any], result: Dict[str, Any], order_id: Optional[str]) -> Dict[str, Any]:
    """Everything the user needs after booking: Swiggy's message, order id, address and timings.

    Swiggy sends no SMS for these bookings, so the app is the user's confirmation.
    """
    detail = result.get("booking") or {}
    confirmation: Dict[str, Any] = {
        "order_id": order_id,
        "swiggy_message": result.get("message"),
        "deal": detail.get("dealTitle"),
        "area": result.get("restaurantLocation"),
        "address": None,
        "timings": None,
        "map_url": None,
    }
    try:  # best effort: the booking already exists, so a failure here must not fail the confirmation
        info = swiggy_mcp_service.get_dineout_details(user_id, booking["restaurant_id"], booking["lat"], booking["lng"])
        restaurant = info.get("restaurant") or {}
        address = restaurant.get("address")
        confirmation["address"] = re.sub(r"^\s*[\d.]+\s*km\s*[•·]\s*", "", address) if address else None
        confirmation["timings"] = restaurant.get("timings")
        confirmation["map_url"] = info.get("map_url")
    except Exception as e:
        logger.warning("Could not fetch restaurant details for the confirmation: %s", e)
    return confirmation


def _share(booking: Dict[str, Any], phone: Optional[str]) -> Dict[str, Any]:
    """Builds a prefilled WhatsApp link. The user taps send; nothing is sent automatically."""
    confirmation = _stored_confirmation(booking) or {}
    where = confirmation.get("address") or confirmation.get("area")
    text = (
        f"Table booked at {booking['restaurant_name']}"
        + (f", {where}" if where else "")
        + f" on {booking['reservation_date']} at {booking['display_time']} for {booking['guest_count']}."
        + (f" Order ID: {booking['swiggy_order_id']}." if booking.get("swiggy_order_id") else "")
        + " (Booked via Plan4U, Powered by Dineout)"
    )
    digits = re.sub(r"\D", "", phone) if phone else ""
    base = f"https://wa.me/{digits}" if digits else "https://wa.me/"
    return {"message": text, "whatsapp_url": f"{base}?text={urllib.parse.quote(text)}"}


def _view(booking: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "booking_id": booking["id"],
        "status": booking["status"],
        "restaurant": {"id": booking["restaurant_id"], "name": booking["restaurant_name"]},
        "date": booking["reservation_date"],
        "time": booking["display_time"],
        "guest_count": booking["guest_count"],
        "for_contact": (
            {"alias": booking["contact_alias"], "name": booking["contact_name"]}
            if booking.get("contact_alias") else None
        ),
        "swiggy_order_id": booking.get("swiggy_order_id"),
        "confirmation": _stored_confirmation(booking),
        "error": booking.get("error_message"),
        "expires_at": booking["expires_at"],
        "attribution": ATTRIBUTION,
    }


def prepare(user_id: str, *, restaurant_id: str, date: str, slot_id: int, item_id: str,
            reservation_time: int, guest_count: int, lat: float, lng: float,
            contact_alias: Optional[str]) -> Dict[str, Any]:
    """Validates the slot against live availability and stores a pending booking to confirm."""
    contact = None
    if contact_alias:
        contact = booking_store.get_contact(user_id, contact_alias)
        if not contact:
            raise BookingError(f"No contact called '{contact_alias}'.", 404)

    if booking_store.count_confirmed_since(user_id, time.time() - ONE_DAY_SECONDS) >= settings.BOOKING_MAX_PER_DAY:
        raise BookingError("Daily booking limit reached. Try again tomorrow.", 429)

    # Availability is checked on the user's own connection (raises SwiggyAuthRequired if not connected).
    slots = swiggy_mcp_service.get_dineout_slots(user_id, restaurant_id, date, lat, lng)
    deal = next((d for d in slots["deals"]
                 if d["date"] == date and d["slot_id"] == slot_id and d["item_id"] == item_id), None)
    if not deal:
        raise BookingError("That deal is not available for this date. Fetch the slots again.")
    if not deal["is_free"]:
        raise BookingError("This deal needs payment, which is not supported yet. Pick a free slot.")
    slot = next((s for s in slots["slots"] if s["reservation_time"] == reservation_time), None)
    if not slot:
        raise BookingError("That time is not available for this date. Fetch the slots again.")

    details = swiggy_mcp_service.get_dineout_details(user_id, restaurant_id, lat, lng)
    restaurant_name = (details.get("restaurant") or {}).get("name")
    if not restaurant_name:
        raise SwiggyError("Swiggy returned no restaurant name for this id.")

    booking = booking_store.create_booking(
        user_id, settings.BOOKING_CONFIRM_TTL_SECONDS,
        contact_alias=contact["alias"] if contact else None,
        contact_name=contact["name"] if contact else None,
        restaurant_id=restaurant_id, restaurant_name=restaurant_name,
        slot_id=slot_id, item_id=item_id, reservation_time=reservation_time,
        reservation_date=date, display_time=slot["display_time"], guest_count=guest_count,
        lat=lat, lng=lng,
    )
    summary = _view(booking)
    summary["confirm_required"] = True
    summary["notice"] = (
        "This books a real table on your Swiggy account. The reservation will be under your own "
        "name and number at the restaurant" + (f", not {contact['name']}'s." if contact else ".")
    )
    return summary


def _order_id(result: Dict[str, Any]) -> Optional[str]:
    if result.get("orderId"):
        return str(result["orderId"])
    match = re.search(r"order\s*id\W+([A-Za-z0-9_-]+)", result.get("text", ""), re.IGNORECASE)
    return match.group(1) if match else None


def confirm(user_id: str, booking_id: str) -> Dict[str, Any]:
    """Books the prepared table. Safe to call twice: a booking is made at most once."""
    booking = booking_store.get_booking(user_id, booking_id)
    if not booking:
        raise BookingError("Booking not found.", 404)

    contact = booking_store.get_contact(user_id, booking["contact_alias"]) if booking.get("contact_alias") else None

    if booking["status"] == "CONFIRMED":
        return {**_view(booking), "can_cancel": _can_cancel(user_id),
                "share": _share(booking, contact["phone"] if contact else None)}
    if booking["status"] != "PENDING":
        raise BookingError(f"This booking is {booking['status']} and cannot be confirmed.", 409)
    if time.time() > booking["expires_at"]:
        booking_store.finish(user_id, booking_id, "EXPIRED", error="Confirmation window passed.")
        raise BookingError("This booking expired. Prepare it again.", 410)

    if not booking_store.transition(user_id, booking_id, "PENDING", "CONFIRMING"):
        raise BookingError("This booking is already being confirmed.", 409)

    try:
        result = swiggy_mcp_service.book_dineout_free_table(
            user_id, booking["restaurant_id"], booking["slot_id"], booking["item_id"],
            booking["reservation_time"], booking["guest_count"], booking["lat"], booking["lng"],
        )
    except SwiggyAuthRequired:
        booking_store.transition(user_id, booking_id, "CONFIRMING", "PENDING")  # nothing was booked; retry after reconnect
        raise
    except SwiggyError as e:
        message = str(e)
        # Transport-level failures are ambiguous: Swiggy may or may not have created the table.
        uncertain = message.startswith("Swiggy MCP")
        booking_store.finish(user_id, booking_id, "UNCERTAIN" if uncertain else "FAILED", error=message[:500])
        if uncertain:
            raise BookingError(
                "We could not confirm whether the table was booked. Check the Swiggy app before retrying.", 502)
        raise

    order_id = _order_id(result)
    confirmation = _build_confirmation(user_id, booking, result, order_id)
    booking_store.finish(user_id, booking_id, "CONFIRMED", order_id=order_id,
                         confirmation_json=json.dumps(confirmation, ensure_ascii=False))
    booking = booking_store.get_booking(user_id, booking_id)
    return {**_view(booking), "can_cancel": _can_cancel(user_id),
            "share": _share(booking, contact["phone"] if contact else None)}


def dismiss(user_id: str, booking_id: str) -> Dict[str, Any]:
    """The user pressed 'No' on a prepared booking. Nothing was booked, so this only closes it."""
    booking = booking_store.get_booking(user_id, booking_id)
    if not booking:
        raise BookingError("Booking not found.", 404)
    if booking["status"] == "PENDING":
        booking_store.transition(user_id, booking_id, "PENDING", "DISMISSED")
        booking = booking_store.get_booking(user_id, booking_id)
    elif booking["status"] != "DISMISSED":
        raise BookingError(f"A booking that is {booking['status']} cannot be dismissed.", 409)
    return _view(booking)


def cancel(user_id: str, booking_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
    """Cancels a confirmed booking on the user's Swiggy account (the caller has confirmed with the user)."""
    booking = booking_store.get_booking(user_id, booking_id)
    if not booking:
        raise BookingError("Booking not found.", 404)
    if booking["status"] == "CANCELLED":
        return _view(booking)
    if booking["status"] != "CONFIRMED" or not booking.get("swiggy_order_id"):
        raise BookingError(f"A booking that is {booking['status']} cannot be cancelled.", 409)
    if not _can_cancel(user_id):
        raise BookingError(CANCEL_UNAVAILABLE_MESSAGE, 409)
    if not booking_store.transition(user_id, booking_id, "CONFIRMED", "CANCELLING"):
        raise BookingError("This booking is already being cancelled.", 409)

    try:
        swiggy_mcp_service.cancel_dineout_booking(user_id, booking["swiggy_order_id"], reason)
    except SwiggyError as e:
        # Nothing is known to have changed, so it stays CONFIRMED; the user can retry or use the Swiggy app.
        booking_store.transition(user_id, booking_id, "CANCELLING", "CONFIRMED")
        if isinstance(e, SwiggyAuthRequired):
            raise
        raise BookingError(
            f"Swiggy could not cancel this booking ({e}). Cancel it in the Swiggy Dineout app "
            "or call customer care at 080-67466729.", 502)

    booking_store.finish(user_id, booking_id, "CANCELLED", order_id=booking["swiggy_order_id"])
    return _view(booking_store.get_booking(user_id, booking_id))


def get(user_id: str, booking_id: str, refresh: bool = False) -> Dict[str, Any]:
    """Returns the booking. With refresh=True, also asks Swiggy for its current view of the order."""
    booking = booking_store.get_booking(user_id, booking_id)
    if not booking:
        raise BookingError("Booking not found.", 404)
    contact = booking_store.get_contact(user_id, booking["contact_alias"]) if booking.get("contact_alias") else None
    out = _view(booking)
    if booking["status"] == "CONFIRMED":
        out["share"] = _share(booking, contact["phone"] if contact else None)
        out["can_cancel"] = _can_cancel(user_id)
        if not out["can_cancel"]:
            out["cancel_help"] = CANCEL_UNAVAILABLE_MESSAGE
    if refresh and booking.get("swiggy_order_id"):
        status = swiggy_mcp_service.get_dineout_booking_status(user_id, booking["swiggy_order_id"])
        order = status.get("order") or {}
        out["swiggy_status"] = {
            "status": order.get("status"),
            "deal": order.get("dealTitle"),
            "date": order.get("reservationDate"),
            "time": order.get("reservationTime"),
            "guest_count": order.get("guestCount"),
        }
    return out


def list_all(user_id: str) -> list:
    can_cancel = _can_cancel(user_id)  # one cached lookup for the whole list
    return [
        {**_view(b), "can_cancel": can_cancel} if b["status"] == "CONFIRMED" else _view(b)
        for b in booking_store.list_bookings(user_id)
    ]
