def categorize_transaction(narration: str) -> str:
    text = narration.lower()

    if any(k in text for k in ["rent", "emi"]):
        return "rent"
    if any(k in text for k in ["grocery", "supermarket"]):
        return "groceries"
    if any(k in text for k in ["fuel", "petrol", "uber"]):
        return "transport"
    if any(k in text for k in ["salary", "credit", "income"]):
        return "income"
    if any(k in text for k in ["food", "zomato", "swiggy"]):
        return "food"

    return "others"


def transform_transactions_for_ml(transactions):
    """
    Convert parsed transactions → ML-ready format
    """
    transformed = []

    for t in transactions:
        amount = 0

        if t["transaction_type"] == "CREDIT":
            amount = t["deposit_amt"]
        elif t["transaction_type"] == "DEBIT":
            amount = -t["withdrawal_amt"]

        transformed.append({
            "date": t["date"],
            "amount": amount,
            "balance": t["closing_balance"],
            "category": categorize_transaction(t["narration"])
        })

    return transformed