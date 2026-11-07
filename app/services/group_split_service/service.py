"""Group Trip Expense Splitting Service."""
from typing import List, Optional
from .models import ExpenseItem, GroupBalanceSheet
from .calculator import calculate_member_balances
from .debt_simplifier import simplify_debts


def settle_group_expenses(
    expenses: List[ExpenseItem],
    members: Optional[List[str]] = None,
) -> GroupBalanceSheet:
    """Takes all trip expenses and outputs a simplified Splitwise-style settlement sheet."""
    balances, all_members, total_expense = calculate_member_balances(expenses, members)
    settlements = simplify_debts(balances)

    return GroupBalanceSheet(
        total_trip_expense=total_expense,
        total_members=len(all_members),
        members=all_members,
        per_person_net_balance=balances,
        settlements=settlements,
    )
