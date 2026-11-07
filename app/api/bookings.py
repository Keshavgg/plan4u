"""Contacts and Dineout table-booking endpoints (all require a signed-in app user)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.services import dineout_booking_service as booking_service
from app.services.booking_store import DuplicateAliasError, booking_store
from app.services.swiggy_mcp_service import SwiggyAuthRequired, SwiggyError

router = APIRouter(prefix="/api/v1", tags=["Contacts & Bookings"])

PHONE_PATTERN = r"^\+[1-9]\d{7,14}$"


class ContactIn(BaseModel):
    alias: str = Field(..., min_length=1, max_length=40, description="Short name you say in chat, e.g. 'rahul'")
    name: str = Field(..., min_length=1, max_length=80)
    phone: Optional[str] = Field(None, pattern=PHONE_PATTERN, description="E.164 with country code, e.g. +919876543210")


@router.post("/contacts", status_code=201)
def add_contact(payload: ContactIn, user_id: str = Depends(get_current_user)):
    """Saves a person you book for. The phone number is stored encrypted and is optional."""
    try:
        return booking_store.add_contact(user_id, payload.alias, payload.name, payload.phone)
    except DuplicateAliasError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/contacts")
def list_contacts(user_id: str = Depends(get_current_user)):
    return {"contacts": booking_store.list_contacts(user_id)}


@router.delete("/contacts/{alias}")
def delete_contact(alias: str, user_id: str = Depends(get_current_user)):
    """Deletes the contact and its stored phone number."""
    if not booking_store.delete_contact(user_id, alias):
        raise HTTPException(status_code=404, detail="Contact not found.")
    return {"status": "deleted"}


class PrepareBooking(BaseModel):
    restaurant_id: str
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Date of the slot, YYYY-MM-DD")
    slot_id: int
    item_id: str = Field(..., description="From the slots response, format '<restaurantId>-<ticketId>'")
    reservation_time: int = Field(..., description="Unix timestamp of the chosen slot, from the slots response")
    guest_count: int = Field(..., ge=1, le=20)
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    for_contact: Optional[str] = Field(None, description="Alias of a saved contact you are booking for")


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except booking_service.BookingError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except SwiggyAuthRequired:
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Connect your Swiggy account to continue.",
                "connect": {"method": "POST", "url": "/api/v1/swiggy/connect"},
            },
        )
    except SwiggyError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/bookings/dineout/prepare")
def prepare_booking(payload: PrepareBooking, user_id: str = Depends(get_current_user)):
    """Step 1: validates a free slot and returns a summary to show the user. Nothing is booked yet."""
    return _run(
        booking_service.prepare, user_id,
        restaurant_id=payload.restaurant_id, date=payload.date, slot_id=payload.slot_id,
        item_id=payload.item_id, reservation_time=payload.reservation_time,
        guest_count=payload.guest_count, lat=payload.lat, lng=payload.lng,
        contact_alias=payload.for_contact,
    )


@router.post("/bookings/dineout/{booking_id}/confirm")
def confirm_booking(booking_id: str, user_id: str = Depends(get_current_user)):
    """Step 2: the user said yes. Books the table on their Swiggy account (at most once)."""
    return _run(booking_service.confirm, user_id, booking_id)


@router.post("/bookings/dineout/{booking_id}/dismiss")
def dismiss_booking(booking_id: str, user_id: str = Depends(get_current_user)):
    """The user declined a prepared booking. Nothing was booked."""
    return _run(booking_service.dismiss, user_id, booking_id)


class CancelBooking(BaseModel):
    confirmed: bool = Field(..., description="Must be true: the user agreed to cancel this reservation")
    reason: Optional[str] = Field(None, max_length=200)


@router.post("/bookings/dineout/{booking_id}/cancel")
def cancel_booking(booking_id: str, payload: CancelBooking, user_id: str = Depends(get_current_user)):
    """Cancels a confirmed booking on the user's Swiggy account."""
    if not payload.confirmed:
        raise HTTPException(status_code=400, detail="Set confirmed=true to cancel this reservation.")
    return _run(booking_service.cancel, user_id, booking_id, payload.reason)


@router.get("/bookings/dineout")
def list_bookings(user_id: str = Depends(get_current_user)):
    return {"bookings": booking_service.list_all(user_id)}


@router.get("/bookings/dineout/{booking_id}")
def get_booking(booking_id: str, refresh: bool = False, user_id: str = Depends(get_current_user)):
    """The booking with its confirmation details. refresh=true also asks Swiggy for the live order status."""
    return _run(booking_service.get, user_id, booking_id, refresh)
