"""Data structures for group trip expenses and settlements."""
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from enum import Enum


class ExpenseCategory(str, Enum):
    HOTEL = "hotel"
    FOOD_DINING = "food_dining"
    TRANSPORT_CAB = "transport_cab"
    ACTIVITY_TICKETS = "activity_tickets"
    SHOPPING = "shopping"
    MISC = "misc"


class ExpenseItem(BaseModel):
    title: str = Field(..., description="e.g. 'Dinner at LMB', 'Goa Beach Resort'")
    amount: float = Field(..., gt=0.0, description="Total amount paid in INR")
    paid_by: str = Field(..., description="Name of the person who paid the bill")
    split_among: Optional[List[str]] = Field(
        default=None,
        description="List of members sharing this cost. If None, split equally among all trip members.",
    )
    category: ExpenseCategory = ExpenseCategory.MISC


class SettlementTransfer(BaseModel):
    from_member: str = Field(..., description="Who needs to pay")
    to_member: str = Field(..., description="Who receives the payment")
    amount: float = Field(..., description="Amount in INR")
    summary: str = Field(..., description="Human-readable transfer summary")


class GroupBalanceSheet(BaseModel):
    total_trip_expense: float
    total_members: int
    members: List[str]
    per_person_net_balance: Dict[str, float] = Field(
        ...,
        description="Positive = receives money, Negative = owes money",
    )
    settlements: List[SettlementTransfer] = Field(
        ...,
        description="Minimal transactions needed to settle all debts",
    )
