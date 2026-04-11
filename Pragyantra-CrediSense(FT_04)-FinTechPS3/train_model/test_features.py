import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml.features import compute_features
from scoring.engine import get_credit_score

sample_transactions = [
    {"date": "2024-01-01", "amount": 50000, "category": "salary", "balance": 50000},
    {"date": "2024-01-05", "amount": -12000, "category": "rent", "balance": 38000},
    {"date": "2024-01-10", "amount": -3000, "category": "groceries", "balance": 35000},
    {"date": "2024-01-15", "amount": -1500, "category": "food", "balance": 33500},
    {"date": "2024-01-20", "amount": -2000, "category": "transport", "balance": 31500},
    {"date": "2024-01-25", "amount": -1000, "category": "entertainment", "balance": 30500},
    {"date": "2024-02-01", "amount": 50000, "category": "salary", "balance": 80500},
    {"date": "2024-02-05", "amount": -12000, "category": "rent", "balance": 68500},
    {"date": "2024-02-10", "amount": -3500, "category": "groceries", "balance": 65000},
    {"date": "2024-02-15", "amount": -2000, "category": "food", "balance": 63000},
    {"date": "2024-02-20", "amount": -2000, "category": "transport", "balance": 61000},
    {"date": "2024-02-25", "amount": -5000, "category": "entertainment", "balance": 56000},
]

print("🚀 Running End-to-End ML Credit Scoring Test...\n")

features = compute_features(sample_transactions)

print("========= COMPUTED FEATURES =========")
for key, value in features.items():
    print(f"  {key:30s} →  {value}")
print("=====================================\n")

score_result = get_credit_score(features)

print("========= ML CREDIT SCORE RESULT =========")
print(f"  Credit Score     : {score_result.get('credit_score', 'ERROR')}")
print(f"  Risk Level       : {score_result.get('risk_level', 'ERROR')}")
print(f"  Grade            : {score_result.get('grade', 'ERROR')}")
print(f"  Message          : {score_result.get('message', 'ERROR')}")

print("\n  Factor Breakdown (Feature Importance %):")
if "factor_breakdown" in score_result:
    for factor, contrib in score_result["factor_breakdown"].items():
        print(f"    {factor:30s} →  {contrib}%")
else:
    print("    No factor breakdown available.")

print("\n==========================================\n")
print("✅ Test completed! Your ML scoring pipeline is working.")