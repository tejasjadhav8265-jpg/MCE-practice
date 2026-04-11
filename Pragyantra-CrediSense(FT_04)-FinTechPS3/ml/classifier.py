import pickle
import json
import os

model = None
feature_names = []

BASE_DIR = os.path.dirname(__file__)
MODEL_PATH = os.path.join(BASE_DIR, "classifier.pkl")
FEATURES_PATH = os.path.join(BASE_DIR, "feature_names.json")


def load_model():
    global model, feature_names

    if model is not None and feature_names:
        return model, feature_names

    try:
        with open(MODEL_PATH, "rb") as f:
            model = pickle.load(f)

        with open(FEATURES_PATH, "r") as f:
            feature_names = json.load(f)

        print("✅ Model loaded")
    except Exception as e:
        print("❌ Model load failed:", e)
        model = None
        feature_names = []

    return model, feature_names


def get_model():
    return load_model()


def predict_credit_score(features: dict) -> int:
    mdl, names = get_model()

    if mdl is None:
        raise RuntimeError("Model not loaded")

    input_vector = [float(features.get(name, 0.0)) for name in names]
    prediction = mdl.predict([input_vector])[0]

    return int(round(float(prediction)))