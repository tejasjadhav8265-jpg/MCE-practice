def categorize_transaction(narration: str) -> str:
    text = (narration or "").lower()

    if any(k in text for k in ["rent", "emi"]):
        return "rent"
    if any(k in text for k in ["grocery", "supermarket", "mart"]):
        return "groceries"
    if any(k in text for k in ["fuel", "petrol", "uber", "taxi", "bus"]):
        return "transport"
    if any(k in text for k in ["salary", "income", "payroll"]):
        return "income"
    if any(k in text for k in ["food", "zomato", "swiggy", "restaurant", "cafe"]):
        return "food"
    if any(k in text for k in ["utility", "electricity", "water", "gas", "recharge"]):
        return "utilities"
    if any(k in text for k in ["insurance"]):
        return "insurance"

    return "others"


def transform_transactions_for_ml(transactions):
    """
    Convert parsed transactions -> ML-ready format expected by compute_features()
    """
    transformed = []

    for t in transactions:
        amount = 0.0

        if t.get("transaction_type") == "CREDIT":
            amount = float(t.get("deposit_amt", 0.0))
        elif t.get("transaction_type") == "DEBIT":
            amount = -float(t.get("withdrawal_amt", 0.0))
        else:
            # fallback
            deposit = float(t.get("deposit_amt", 0.0))
            withdrawal = float(t.get("withdrawal_amt", 0.0))
            amount = deposit if deposit > 0 else -withdrawal

        transformed.append({
            "date": t.get("date"),
            "amount": amount,
            "balance": float(t.get("closing_balance", 0.0)),
            "category": categorize_transaction(t.get("narration", "")),
        })

    return transformed