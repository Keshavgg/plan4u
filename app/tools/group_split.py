"""AI-facing tool for group bill splitting and debt settlement."""
from typing import List, Dict, Any
from app.services.group_split_service import settle_group_expenses, ExpenseItem, ExpenseCategory


def calculate_group_split_tool(expenses: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate net balances and minimum cash-flow settlements among trip members.
    
    Args:
        expenses: List of expenses, each containing 'description'/'title', 'amount', 'paid_by', and 'split_among' (list of names).
    """
    items = []
    for exp in expenses:
        items.append(ExpenseItem(
            title=exp.get("title") or exp.get("description", "Trip Expense"),
            amount=float(exp.get("amount") or exp.get("amount_inr", 0)),
            paid_by=exp.get("paid_by", ""),
            split_among=exp.get("split_among", []),
            category=ExpenseCategory.MISC,
        ))
    sheet = settle_group_expenses(items)
    return {
        "success": True,
        "total_trip_expense": sheet.total_trip_expense,
        "total_members": sheet.total_members,
        "per_person_net_balance": sheet.per_person_net_balance,
        "settlements": [s.model_dump() for s in sheet.settlements],
        "summary_narrative": [
            s.summary for s in sheet.settlements
        ],
    }
