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
        # The new parser returns signed amount: positive for credit, negative for debit
        amount = float(t.get("amount", 0.0))
        balance = float(t.get("balance", 0.0))
        category = t.get("category", "other")
        description = t.get("description", "")

        transformed.append({
            "date": t.get("date"),
            "amount": amount,
            "balance": balance,
            "category": category,
            "narration": description,  # for categorization
        })

    return transformed