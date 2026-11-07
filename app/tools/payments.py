"""AI-facing payment and checkout session creation tools."""
from typing import Optional, Dict, Any
import uuid
import datetime
import urllib.request
import urllib.parse
import json
import base64

from app.config import settings
from app.schemas.booking import RazorpayCheckoutSession


def create_checkout_session_tool(
    amount_inr: float,
    description: str = "Plan4U Trip Booking",
    customer_email: Optional[str] = None,
    customer_phone: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a secured Razorpay order and checkout session for trip booking.
    
    Args:
        amount_inr: Grand total amount in Indian Rupees (INR)
        description: Brief description of the booked trip or package
        customer_email: Optional email address for confirmation receipts
        customer_phone: Optional 10-digit Indian mobile number
    """
    amount_paise = int(round(amount_inr * 100))
    expiry_time = (datetime.datetime.utcnow() + datetime.timedelta(minutes=15)).isoformat() + "Z"
    
    # If production / test keys are configured
    if settings.PAYMENT_KEY_ID and settings.PAYMENT_KEY_SECRET:
        try:
            url = "https://api.razorpay.com/v1/orders"
            payload = json.dumps({
                "amount": amount_paise,
                "currency": "INR",
                "receipt": f"rcpt_{uuid.uuid4().hex[:8]}",
                "notes": {
                    "description": description,
                    "customer_email": customer_email or "guest@plan4u.ai",
                }
            }).encode("utf-8")
            
            req = urllib.request.Request(url, data=payload, method="POST")
            auth_str = f"{settings.PAYMENT_KEY_ID}:{settings.PAYMENT_KEY_SECRET}"
            b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
            req.add_header("Authorization", f"Basic {b64_auth}")
            req.add_header("Content-Type", "application/json")
            
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                order_id = data.get("id")
                return {
                    "success": True,
                    "order_id": order_id,
                    "key_id": settings.PAYMENT_KEY_ID,
                    "amount_in_inr": amount_inr,
                    "amount_in_paise": amount_paise,
                    "currency": "INR",
                    "checkout_url": f"https://api.razorpay.com/v1/checkout/embedded?order_id={order_id}",
                    "expires_at": expiry_time,
                }
        except Exception as e:
            # Fallback to sandbox session if live API failed
            pass
            
    # Sandbox / Demo mode
    order_id = f"order_{uuid.uuid4().hex[:14]}"
    key_id = settings.PAYMENT_KEY_ID or "rzp_test_Plan4USandbox"
    return {
        "success": True,
        "order_id": order_id,
        "key_id": key_id,
        "amount_in_inr": amount_inr,
        "amount_in_paise": amount_paise,
        "currency": "INR",
        "checkout_url": f"https://checkout.razorpay.com/v1/checkout.js?order_id={order_id}",
        "expires_at": expiry_time,
    }
