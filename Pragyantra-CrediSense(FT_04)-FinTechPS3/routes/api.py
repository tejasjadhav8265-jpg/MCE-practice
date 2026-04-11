from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Dict, List
import shutil
import os
import tempfile

from parser.pdf_parser import extract_bank_statement
from parser.transform import transform_transactions_for_ml
from ml.features import compute_features
from scoring.engine import get_credit_score
from ollama_advisor.advisor import generate_financial_advice

router = APIRouter()


@router.get("/health")
def health_check():
    return {
        "status": "ok",
        "message": "AI Credit Scoring API is running",
        "model": "RandomForest (loaded)"
    }


@router.post("/test-score")
async def test_score(payload: Dict):
    """
    Test endpoint: send transactions directly.
    """
    try:
        transactions: List[Dict] = payload.get("transactions", [])
        occupation = payload.get("occupation", "Other")

        if not transactions:
            raise HTTPException(status_code=400, detail="No transactions provided")

        features = compute_features(transactions)
        score_result = get_credit_score(features)
        advice = generate_financial_advice(features, score_result, occupation)

        return {
            "status": "success",
            "features": features,
            "score": score_result,
            "advice": advice,
            "occupation": occupation,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")


@router.post("/analyze")
async def analyze(
    file: UploadFile = File(...),
    password: str = Form(""),
    occupation: str = Form("Other"),
):
    """
    Real endpoint: upload PDF -> parse -> transform -> features -> score -> advice
    """
    suffix = os.path.splitext(file.filename or "")[1] or ".pdf"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)

    try:
        with open(tmp.name, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        parsed = extract_bank_statement(tmp.name, password or None)
        transactions = parsed.get("transactions", [])

        if not transactions:
            raise HTTPException(status_code=400, detail="No transactions found in PDF. Please ensure it's a valid bank statement PDF.")

        ml_ready = transform_transactions_for_ml(transactions)
        features = compute_features(ml_ready)
        score_result = get_credit_score(features)
        advice = generate_financial_advice(features, score_result, occupation)

        return {
            "status": "success",
            "features": features,
            "score": score_result,
            "advice": advice,
            "occupation": occupation,
            "transactions_extracted": len(transactions),
        }

    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Error processing PDF: {str(e)}"
        print(f"[ERROR] {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)
    finally:
        try:
            os.remove(tmp.name)
        except OSError:
            pass