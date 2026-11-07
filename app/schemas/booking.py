"""Booking and Razorpay payment schemas for TBO/Galileo reservations."""
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class BookingStatus(str, Enum):
    DRAFT = "draft"
    HOLD_CONFIRMED = "hold_confirmed"      # PNR held on GDS/TBO
    PAYMENT_INITIATED = "payment_initiated"
    TICKETED = "ticketed"                  # Confirmed & ticket issued
    FAILED = "failed"
    CANCELLED = "cancelled"


class Gender(str, Enum):
    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"


class PassengerTitle(str, Enum):
    MR = "Mr"
    MS = "Ms"
    MRS = "Mrs"
    MASTER = "Master"


class PassengerDetail(BaseModel):
    title: PassengerTitle = PassengerTitle.MR
    first_name: str
    last_name: str
    gender: Gender = Gender.MALE
    date_of_birth: str = Field(..., description="YYYY-MM-DD")
    email: str
    phone: str
    pan_number: Optional[str] = Field(None, description="PAN Card number required for Indian travel bookings")
    passport_number: Optional[str] = None
    passport_expiry: Optional[str] = None


class GstDetails(BaseModel):
    gstin: str = Field(..., description="15-character GST identification number")
    company_name: str
    company_email: str
    company_address: str


class CreateBookingHoldRequest(BaseModel):
    itinerary_id: str
    
    # Flight Reservation Hold (TBO or Galileo)
    flight_id: Optional[str] = None
    flight_trace_id: Optional[str] = None
    flight_result_index: Optional[str] = None
    
    # Hotel Reservation (TBO)
    hotel_code: Optional[str] = None
    room_index: Optional[int] = 1
    
    passengers: List[PassengerDetail]
    gst: Optional[GstDetails] = None
    special_requests: Optional[str] = None


class RazorpayCheckoutSession(BaseModel):
    order_id: str = Field(..., description="Razorpay order ID e.g. 'order_ABC123'")
    key_id: str = Field(..., description="Razorpay Key ID (rzp_test_...)")
    amount_in_inr: float
    amount_in_paise: int
    currency: str = "INR"
    checkout_url: Optional[str] = Field(None, description="Pre-filled Payment link if hosted checkout is used")
    expires_at: str = Field(..., description="Valid for ~15 mins (matching TBO trace expiry)")


class BookingRecord(BaseModel):
    booking_id: str = Field(..., description="Internal app booking reference")
    status: BookingStatus = BookingStatus.HOLD_CONFIRMED
    itinerary_id: str
    
    # Supplier references
    pnr: Optional[str] = Field(None, description="Airline PNR / Galileo uAPI confirmation code")
    tbo_booking_id: Optional[str] = None
    hotel_confirmation_code: Optional[str] = None
    
    # Payment info
    razorpay_order_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    total_amount: float
    currency: str = "INR"
    
    ticket_pdf_url: Optional[str] = None
    hotel_voucher_url: Optional[str] = None
    created_at: str
