"""Min-cash-flow algorithm (Splitwise-style debt simplification)."""
from typing import Dict, List, Any
from .models import SettlementTransfer


def simplify_debts(balances: Dict[str, float]) -> List[SettlementTransfer]:
    """Reduces mutual debts into the minimum number of money transfers."""
    # Separate into debtors (-ve balance) and creditors (+ve balance)
    # debtors owe money; creditors should receive money
    debtors: List[List[Any]] = []  # [member, amount_owed]
    creditors: List[List[Any]] = []  # [member, amount_to_receive]

    for member, net in balances.items():
        if net < -0.01:
            debtors.append([member, abs(net)])
        elif net > 0.01:
            creditors.append([member, net])

    settlements: List[SettlementTransfer] = []

    # Two pointers / greedy matching
    debtor_idx = 0
    creditor_idx = 0

    while debtor_idx < len(debtors) and creditor_idx < len(creditors):
        debtor_name, owed = debtors[debtor_idx]
        creditor_name, credit = creditors[creditor_idx]

        settled_amount = round(min(owed, credit), 2)

        if settled_amount > 0.01:
            settlements.append(
                SettlementTransfer(
                    from_member=debtor_name,
                    to_member=creditor_name,
                    amount=settled_amount,
                    summary=f"{debtor_name} pays ₹{settled_amount} to {creditor_name}",
                )
            )

        # Update remaining balances
        debtors[debtor_idx][1] -= settled_amount
        creditors[creditor_idx][1] -= settled_amount

        if debtors[debtor_idx][1] <= 0.01:
            debtor_idx += 1
        if creditors[creditor_idx][1] <= 0.01:
            creditor_idx += 1

    return settlements
