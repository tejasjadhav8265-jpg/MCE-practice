import pandas as pd
from typing import List, Dict


DEFAULT_FEATURES = {
    "avg_monthly_income": 0.0,
    "income_stability": 0.0,
    "savings_ratio": 0.0,
    "expense_to_income_ratio": 1.0,
    "essential_expense_ratio": 0.0,
    "cash_flow_volatility": 0.0,
    "overdraft_frequency": 1.0,
    "transaction_regularity": 0.0,
}


def compute_features(transactions: List[Dict]) -> Dict:
    """
    Compute ML-ready financial behavior features from parsed transactions.
    Expects each transaction to have:
    - date
    - amount (positive credit, negative debit)
    - balance
    - category
    """
    if not transactions:
        return DEFAULT_FEATURES.copy()

    df = pd.DataFrame(transactions)

    # Normalize expected columns
    if "amount" not in df.columns:
        df["amount"] = 0.0
    if "balance" not in df.columns:
        df["balance"] = 0.0
    if "category" not in df.columns:
        df["category"] = "others"

    df["date"] = pd.to_datetime(df.get("date"), errors="coerce")
    df = df.dropna(subset=["date"])

    if df.empty:
        return DEFAULT_FEATURES.copy()

    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    df["balance"] = pd.to_numeric(df["balance"], errors="coerce").fillna(method="ffill").fillna(0.0)
    df["category"] = df["category"].fillna("others").astype(str).str.lower()
    df["month"] = df["date"].dt.to_period("M")

    credits = df[df["amount"] > 0].copy()
    debits = df[df["amount"] < 0].copy()

    monthly_income = credits.groupby("month")["amount"].sum()
    monthly_expense = debits.groupby("month")["amount"].apply(lambda x: x.abs().sum())
    monthly_cashflow = monthly_income.subtract(monthly_expense, fill_value=0)

    total_income = float(monthly_income.sum()) if not monthly_income.empty else 0.0
    total_expense = float(monthly_expense.sum()) if not monthly_expense.empty else 0.0

    avg_monthly_income = float(monthly_income.mean()) if not monthly_income.empty else 0.0

    if not monthly_income.empty and monthly_income.mean() != 0:
        income_cv = monthly_income.std() / (monthly_income.mean() + 1e-9)
        if pd.isna(income_cv):
            income_cv = 0.0
    else:
        income_cv = 0.0

    income_stability = round(max(0.0, 1.0 - income_cv), 4)

    savings_ratio = round(max(0.0, (total_income - total_expense) / (total_income + 1e-9)), 4) if total_income else 0.0
    expense_to_income_ratio = round(min(1.0, total_expense / (total_income + 1e-9)), 4) if total_income else 1.0

    essential_categories = ["rent", "utilities", "groceries", "transport", "insurance", "emi", "food"]
    essential_spend = debits[debits["category"].isin(essential_categories)]["amount"].abs().sum()
    essential_expense_ratio = round(essential_spend / (total_expense + 1e-9), 4) if total_expense else 0.0

    if monthly_cashflow.empty or monthly_cashflow.mean() == 0:
        cash_flow_volatility = 0.0
    else:
        cash_flow_volatility = monthly_cashflow.std() / (abs(monthly_cashflow.mean()) + 1e-9)
        if pd.isna(cash_flow_volatility):
            cash_flow_volatility = 0.0
    cash_flow_volatility = round(float(cash_flow_volatility), 4)

    overdraft_frequency = round((df["balance"] < 500).sum() / (len(df) + 1e-9), 4)

    transaction_regularity = 0.0
    if not debits.empty:
        rounded_amounts = debits["amount"].abs().round(0)
        recurring_count = (rounded_amounts.value_counts() >= 3).sum()
        transaction_regularity = round(min(1.0, recurring_count / 5), 4)

    return {
        "avg_monthly_income": round(avg_monthly_income, 2),
        "income_stability": float(income_stability),
        "savings_ratio": float(savings_ratio),
        "expense_to_income_ratio": float(expense_to_income_ratio),
        "essential_expense_ratio": float(essential_expense_ratio),
        "cash_flow_volatility": float(cash_flow_volatility),
        "overdraft_frequency": float(overdraft_frequency),
        "transaction_regularity": float(transaction_regularity),
    }