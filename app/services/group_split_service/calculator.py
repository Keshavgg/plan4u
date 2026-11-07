"""Net balance calculation across group members."""
from typing import List, Dict, Set, Tuple
from .models import ExpenseItem


def calculate_member_balances(
    expenses: List[ExpenseItem],
    explicit_members: List[str] = None,
) -> Tuple[Dict[str, float], List[str], float]:
    """Calculates each member's net balance (+ receives, - owes) and total trip cost."""
    # Discover all members
    member_set: Set[str] = set(explicit_members or [])
    for exp in expenses:
        member_set.add(exp.paid_by)
        if exp.split_among:
            member_set.update(exp.split_among)

    all_members = sorted(list(member_set))
    balances: Dict[str, float] = {m: 0.0 for m in all_members}
    total_expense = 0.0

    for exp in expenses:
        total_expense += exp.amount
        payer = exp.paid_by
        beneficiaries = exp.split_among if (exp.split_among and len(exp.split_among) > 0) else all_members
        
        split_share = round(exp.amount / len(beneficiaries), 2)

        # Payer gets credit for the full amount
        balances[payer] += exp.amount

        # Each beneficiary owes their share
        for b in beneficiaries:
            balances[b] -= split_share

    # Round balances to 2 decimal places to avoid floating point precision issues
    clean_balances = {m: round(bal, 2) for m, bal in balances.items()}
    return clean_balances, all_members, round(total_expense, 2)
