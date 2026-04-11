import pandas as pd
import numpy as np
import os


def generate_synthetic_data(n_samples: int = 1200) -> pd.DataFrame:
    np.random.seed(42)

    data = {
        "avg_monthly_income":      np.random.uniform(15000, 200000, n_samples),
        "income_stability":        np.random.uniform(0.0, 1.0, n_samples),
        "savings_ratio":           np.random.uniform(0.0, 0.7, n_samples),
        "expense_to_income_ratio": np.random.uniform(0.3, 1.0, n_samples),
        "essential_expense_ratio": np.random.uniform(0.2, 1.0, n_samples),
        "cash_flow_volatility":    np.random.uniform(0.0, 2.0, n_samples),
        "overdraft_frequency":     np.random.uniform(0.0, 0.5, n_samples),
        "transaction_regularity":  np.random.uniform(0.0, 1.0, n_samples),
    }

    df = pd.DataFrame(data)

    df['credit_score'] = (
        300
        + (df['income_stability'] * 120)
        + (df['savings_ratio'] * 150)
        + ((1 - df['expense_to_income_ratio']) * 100)
        + (df['essential_expense_ratio'] * 60)
        + ((1 - df['cash_flow_volatility'].clip(0, 1)) * 80)
        + ((1 - df['overdraft_frequency']) * 80)
        + (df['transaction_regularity'] * 60)
        + (df['avg_monthly_income'].clip(0, 200000) / 200000 * 100)
    ).clip(300, 850).round().astype(int)

    return df


def save_training_data():
    BASE_DIR = os.path.dirname(__file__)
    file_path = os.path.join(BASE_DIR, "synthetic_training_data.csv")

    df = generate_synthetic_data()
    df.to_csv(file_path, index=False)

    print(f"✅ Training data saved → {file_path}")

    return file_path