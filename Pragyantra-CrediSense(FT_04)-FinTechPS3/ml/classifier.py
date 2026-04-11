import pickle
import json
import os

# Global variables (loaded once)
model = None
feature_names = []


def load_model():
    global model, feature_names

    if model is not None:
        return  # already loaded

    try:
        model_path = os.path.join("ml", "classifier.pkl")
        features_path = os.path.join("ml", "feature_names.json")

        with open(model_path, "rb") as f:
            model = pickle.load(f)

        with open(features_path, "r") as f:
            feature_names = json.load(f)

        print("✅ ML model loaded successfully")

    except Exception as e:
        print("❌ Error loading model:", e)


def predict_credit_score(features: dict) -> int:
    """
    Takes feature dict → returns predicted credit score
    """
    if model is None:
        load_model()

    if model is None:
        raise Exception("Model not loaded")

    # Ensure correct feature order
    input_vector = [features.get(name, 0) for name in feature_names]

    prediction = model.predict([input_vector])[0]

    return int(prediction)