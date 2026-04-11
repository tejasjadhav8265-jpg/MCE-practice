import pickle
import json
import os

model = None
feature_names = []


def load_model():
    global model, feature_names

    if model is not None:
        return

    BASE_DIR = os.path.dirname(__file__)

    try:
        with open(os.path.join(BASE_DIR, "classifier.pkl"), "rb") as f:
            model = pickle.load(f)

        with open(os.path.join(BASE_DIR, "feature_names.json"), "r") as f:
            feature_names = json.load(f)

        print("✅ Model loaded")

    except Exception as e:
        print("❌ Model load failed:", e)


def predict_credit_score(features: dict) -> int:
    if model is None:
        load_model()

    if model is None:
        raise Exception("Model not loaded")

    input_vector = [features.get(name, 0) for name in feature_names]

    prediction = model.predict([input_vector])[0]

    return int(prediction)