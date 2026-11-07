"""Group Trip Settlement UPI & Payment Links Generator."""
from typing import List, Dict, Any
import urllib.parse
from app.services.group_split_service.models import ExpenseItem, ExpenseCategory
from app.services.group_split_service.service import settle_group_expenses


def generate_group_settlement_links(
    expenses_raw: List[Dict[str, Any]],
    upi_vpa_recipient: str = "trip.split@upi",
) -> Dict[str, Any]:
    """Generates direct UPI deep-links, Razorpay checkout sessions, and WhatsApp shareable templates for group debt settlement."""
    from app.tools.payments import create_checkout_session_tool
    items = []
    for exp in expenses_raw:
        items.append(ExpenseItem(
            title=exp.get("title") or exp.get("description", "Trip Spend"),
            amount=float(exp.get("amount") or exp.get("amount_inr", 0)),
            paid_by=exp.get("paid_by", ""),
            split_among=exp.get("split_among", []),
            category=ExpenseCategory.MISC,
        ))

    sheet = settle_group_expenses(items)

    actionable_settlements = []
    for s in sheet.settlements:
        amt = s.amount
        note = f"Trip settlement: {s.from_member} to {s.to_member}"
        encoded_note = urllib.parse.quote(note)

        # Standard NPCI UPI URI Scheme (Opens GPay, PhonePe, Paytm on mobile)
        upi_link = f"upi://pay?pa={upi_vpa_recipient}&pn={urllib.parse.quote(s.to_member)}&am={amt:.2f}&cu=INR&tn={encoded_note}"

        # Razorpay Card / NetBanking Payment Link
        checkout = create_checkout_session_tool(
            amount_inr=amt,
            description=note,
        )

        # WhatsApp shareable copy text
        wa_message = f"Hey {s.from_member}! Your share for our trip is ₹{amt:,.0f} to {s.to_member}. Settle it quickly using this link: {checkout.get('checkout_url')}"
        wa_url = f"https://wa.me/?text={urllib.parse.quote(wa_message)}"

        actionable_settlements.append({
            "from_member": s.from_member,
            "to_member": s.to_member,
            "amount_inr": amt,
            "upi_deep_link": upi_link,
            "razorpay_order_id": checkout["order_id"],
            "checkout_url": checkout.get("checkout_url"),
            "whatsapp_share_url": wa_url,
            "summary_text": s.summary,
        })

    return {
        "success": True,
        "total_trip_spend_inr": sheet.total_trip_expense,
        "total_members": sheet.total_members,
        "net_balances": sheet.per_person_net_balance,
        "actionable_settlements": actionable_settlements,
    }
