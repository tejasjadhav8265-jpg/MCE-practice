# app/ml/train.py
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
import pickle
import json
import os

FEATURE_COLUMNS = [
    "avg_monthly_income",
    "income_stability",
    "savings_ratio",
    "expense_to_income_ratio",
    "essential_expense_ratio",
    "cash_flow_volatility",
    "overdraft_frequency",
    "transaction_regularity"
]

def train_model():
    data_path = "app/ml/synthetic_training_data.csv"

    if not os.path.exists(data_path):
        print(f"❌ Error: {data_path} not found. Run data_gen.py first.")
        return

    print("📂 Loading synthetic training data...")
    df = pd.read_csv(data_path)

    # Verify all columns exist
    missing = [col for col in FEATURE_COLUMNS if col not in df.columns]
    if missing:
        print(f"❌ Missing columns in CSV: {missing}")
        return

    X = df[FEATURE_COLUMNS]
    y = df['credit_score']

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    print(f"🤖 Training RandomForest on {len(FEATURE_COLUMNS)} features...")
    model = RandomForestRegressor(
        n_estimators=150,
        max_depth=12,
        min_samples_split=4,
        random_state=42,
        n_jobs=-1
    )

    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    print(f"✅ Model trained! Test MAE: {mae:.2f} points")

    # Save model and feature names
    with open("app/ml/credit_model.pkl", "wb") as f:
        pickle.dump(model, f)

    with open("app/ml/feature_names.json", "w") as f:
        json.dump(FEATURE_COLUMNS, f)

    print("✅ Saved: credit_model.pkl + feature_names.json")

if __name__ == "__main__":
    train_model()