"""Budget & Checkout Master Subagent equipped with precision financial tools."""
from typing import Optional, List
from app.schemas.agent import BudgetCheckoutTask, BudgetCheckoutResult, AgentRole
from app.schemas.booking import RazorpayCheckoutSession
from app.tools.payments import create_checkout_session_tool
from app.services.smart_tools.forex_service import convert_currency
from app.tools.registry import get_tools_for_agent


class BudgetCheckoutAgent:
    """Specialist subagent for budget reconciliation, currency conversion, and Razorpay payment session creation."""

    def __init__(self):
        self.role = AgentRole.BUDGET_CHECKOUT_MASTER
        self.authorized_tools = get_tools_for_agent(self.role)

    def run(self, task: BudgetCheckoutTask) -> BudgetCheckoutResult:
        flight_total = task.selected_flight.published_fare if task.selected_flight else 0.0
        hotel_total = (task.selected_hotel.min_price_per_night * task.days_count) if task.selected_hotel else 0.0
        activities_total = task.activities_cost

        grand_total = flight_total + hotel_total + activities_total

        is_within = True
        variance = 0.0
        notes = []

        if task.total_budget_limit:
            variance = task.total_budget_limit - grand_total
            if variance < 0:
                is_within = False
                notes.append(
                    f"Warning: Selected package exceeds stated budget by ₹{abs(variance):,.0f}. "
                    "Consider choosing non-refundable LCC flight or a boutique 3-star stay to stay within limits."
                )
            else:
                notes.append(f"Great news! Your plan is ₹{variance:,.0f} under your maximum budget limit.")

        notes.append(f"Flights: ₹{flight_total:,.0f} | Hotel ({task.days_count} nights): ₹{hotel_total:,.0f} | Activities & Dining: ₹{activities_total:,.0f}")

        # Tool: create_checkout_session
        checkout_dict = create_checkout_session_tool(
            amount_inr=grand_total,
            description="Plan4U Curated Complete Itinerary",
            customer_email=task.user_email,
            customer_phone=task.user_phone,
        )

        checkout_session = RazorpayCheckoutSession(
            order_id=checkout_dict["order_id"],
            key_id=checkout_dict["key_id"],
            amount_in_inr=checkout_dict["amount_in_inr"],
            amount_in_paise=checkout_dict["amount_in_paise"],
            currency=checkout_dict["currency"],
            checkout_url=checkout_dict.get("checkout_url"),
            expires_at=checkout_dict["expires_at"],
        )

        return BudgetCheckoutResult(
            success=True,
            flight_total=flight_total,
            hotel_total=hotel_total,
            activities_total=activities_total,
            grand_total=grand_total,
            is_within_budget=is_within,
            budget_variance_inr=variance,
            checkout_session=checkout_session,
            financial_notes=notes,
        )
