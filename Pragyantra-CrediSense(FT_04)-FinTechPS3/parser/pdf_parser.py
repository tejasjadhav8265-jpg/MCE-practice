import pdfplumber
import re
from datetime import datetime


def extract_transactions(pdf_path: str, password: str = None):
    transactions = []

    with pdfplumber.open(pdf_path, password=password) as pdf:
        lines = []

        for page in pdf.pages:
            text = page.extract_text()
            if text:
                lines.extend(text.split("\n"))

    date_pattern = re.compile(r"(\d{2}/\d{2}/\d{2})")
    amount_pattern = re.compile(r"(\d+\.\d{2})")

    current = None

    for line in lines:
        line = line.strip()

        if not line:
            continue

        # 🟢 New transaction starts - look for date in the line
        date_match = date_pattern.search(line)
        if date_match:
            if current:
                transactions.append(current)

            date = date_match.group(1)

            current = {
                "date": datetime.strptime(date, "%d/%m/%y").strftime("%Y-%m-%d"),
                "description": "",
                "amount": 0.0,
                "balance": 0.0,
                "category": "other"
            }

        if current:
            current["description"] += " " + line

            amounts = amount_pattern.findall(line)

            if len(amounts) >= 2:
                balance = float(amounts[-1])
                txn_amount = float(amounts[-2])  # Second last is transaction amount

                current["balance"] = balance

                # Heuristic: deposit vs withdrawal
                if txn_amount < balance:
                    current["amount"] = -txn_amount
                else:
                    current["amount"] = txn_amount

    if current:
        transactions.append(current)

    # 🏷 Categorization
    for txn in transactions:
        desc = txn["description"].lower()

        if "salary" in desc:
            txn["category"] = "income"
        elif "grocery" in desc or "shopping" in desc:
            txn["category"] = "groceries"
        elif "utility" in desc or "bill" in desc:
            txn["category"] = "utilities"
        elif "upi" in desc:
            txn["category"] = "upi"
        elif "amazon" in desc:
            txn["category"] = "shopping"
        elif "zomato" in desc:
            txn["category"] = "food"
        elif "petrol" in desc:
            txn["category"] = "transport"
        else:
            txn["category"] = "other"

    return transactions