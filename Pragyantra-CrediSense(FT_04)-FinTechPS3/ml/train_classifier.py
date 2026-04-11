import pandas as pd
import pickle
import json
import os
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error

from ml.training_data import save_training_data


def train_model():
    data_path = save_training_data()

    df = pd.read_csv(data_path)

    X = df.drop("credit_score", axis=1)
    y = df["credit_score"]
    feature_names = list(X.columns)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    model = RandomForestRegressor(
        n_estimators=100,
        random_state=42,
        n_jobs=-1
    )
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    mae = mean_absolute_error(y_test, preds)

    print(f"✅ Model trained | MAE: {mae:.2f}")

    base_dir = os.path.dirname(__file__)
    model_path = os.path.join(base_dir, "classifier.pkl")
    features_path = os.path.join(base_dir, "feature_names.json")

    with open(model_path, "wb") as f:
        pickle.dump(model, f)

    with open(features_path, "w") as f:
        json.dump(feature_names, f)

    print("✅ Model + features saved")


if __name__ == "__main__":
    train_model()