import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen:4b"

def generate_financial_advice(features, score, occupation):
    prompt = f"""
You are a financial advisor.

User Details:
- Credit Score: {score['credit_score']}
- Risk Level: {score['risk_level']}
- Occupation: {occupation}

Financial Features:
{features}

Your task:
1. Explain the user's financial health in simple terms
2. Identify strengths
3. Identify weaknesses
4. Give 3 actionable improvement tips

Keep it concise and practical.
"""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False
        }
    )

    return response.json()["response"]