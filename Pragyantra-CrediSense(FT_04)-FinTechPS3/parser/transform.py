def categorize_transaction(narration: str) -> str:
    text = narration.lower()

    if "rent" in text or "emi" in text:
        return "rent"
    if "grocery" in text:
        return "groceries"
    if "fuel" in text or "petrol" in text:
        return "transport"
    if "salary" in text:
        return "income"

    return "others"


def transform_transactions_for_ml(transactions):
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