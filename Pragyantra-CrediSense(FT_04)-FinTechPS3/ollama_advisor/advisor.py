import os
import requests

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL = os.getenv("OLLAMA_MODEL", "qwen:4b")


def generate_financial_advice(features, score, occupation):
    prompt = f"""
You are a financial advisor.

User Details:
- Credit Score: {score.get('credit_score', 'N/A')}
- Risk Level: {score.get('risk_level', 'N/A')}
- Occupation: {occupation}

Financial Features:
{features}

Your task:
1. Explain the user's financial health in simple terms
2. Identify strengths
3. Identify weaknesses
4. Give 3 actionable improvement tips

Keep it concise, practical, and easy to understand.
"""

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("response", "No advisor response received.")
    except Exception as e:
        return (
            "Advisor unavailable right now. "
            "Keep income stable, reduce unnecessary expenses, and avoid overdrafts.\n"
            f"(Ollama error: {e})"
        )