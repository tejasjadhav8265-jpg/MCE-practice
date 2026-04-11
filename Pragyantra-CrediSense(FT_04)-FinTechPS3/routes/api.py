from fastapi import APIRouter, UploadFile, File
import shutil
import os

from parser.pdf_parser import extract_bank_statement
from parser.transform import transform_transactions_for_ml
from ml.features import compute_features
from ml.classifier import predict_credit_score

router = APIRouter()


@router.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    file_path = f"temp_{file.filename}"

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        data = extract_bank_statement(file_path)
        transactions = data["transactions"]

        ml_ready = transform_transactions_for_ml(transactions)

        features = compute_features(ml_ready)

        score = predict_credit_score(features)

        return {
            "credit_score": score,
            "features": features,
            "transactions": len(transactions)
        }

    finally:
        os.remove(file_path)