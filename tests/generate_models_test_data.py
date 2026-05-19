"""Generate dummy model inventory for the Risk Taxonomy Transformer.

Creates one file in data/input/:

MODEL INVENTORY (model_inventory_test_dummy.xlsx):
  ~12 model rows keyed by Model ID with five fields used by the HTML
  drill-down inventory section and the Source - Models Excel tab.

Columns:
  - Model ID
  - Model Name
  - Markets             (single-value; e.g. Consumer Cards, Commercial Cards,
                         Enterprise, Wealth & Investment)
  - Model Impact Category   (Critical / High / Medium / Low — colored pill in HTML)
  - Model Class         (Marketing / Credit & Fraud / Finance/Treasury)

Coverage:
  - All four Impact tiers (Critical, High, Medium, Low) are represented.
  - Three distinct Model Class values (Marketing, Credit & Fraud,
    Finance/Treasury).
  - IDs are all-numeric, 1001 .. 1011 plus a 2-digit ID (12) to exercise
    the relaxed two-or-more-digit regex, matching the IDs that
    `tests/generate_test_data.py` writes into the legacy
    `Models` column.

Unmatched-ID coverage:
  AE-9 (Cross-Border Operations) deliberately references 9001 and 9002
  in the legacy data — these IDs are NOT present in this inventory,
  exercising the "in legacy but not in inventory" gap surfaced by the
  HTML drill-down renderer.

Usage:
    python tests/generate_models_test_data.py
"""

import pandas as pd
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = _PROJECT_ROOT / "data" / "input"


# (Model ID, Model Name, Model Class, Markets, Model Impact Category)
MODELS = [
    ("1001", "Consumer Credit Decision Model",      "Credit & Fraud",   "Consumer Cards",         "Critical"),
    ("1002", "Account Fraud Scoring",               "Credit & Fraud",   "Consumer Cards",         "High"),
    ("1003", "Customer Lifetime Value",             "Marketing",        "Consumer Cards",         "Medium"),
    ("1004", "Loss Forecasting Model",              "Finance/Treasury", "Consumer Cards",         "High"),
    ("1005", "Liquidity Stress Model",              "Finance/Treasury", "Enterprise",             "Critical"),
    ("1006", "FTP Allocation Model",                "Finance/Treasury", "Enterprise",             "Medium"),
    ("1007", "Merchant Risk Scoring",               "Credit & Fraud",   "Commercial Cards",       "High"),
    ("1008", "Chargeback Prediction",               "Credit & Fraud",   "Commercial Cards",       "Medium"),
    ("1009", "Digital Onboarding Model",            "Marketing",        "Consumer Cards",         "Low"),
    ("1010", "Behavioral Biometrics",               "Credit & Fraud",   "Consumer Cards",         "High"),
    ("1011", "Capital Allocation Model",            "Finance/Treasury", "Enterprise",             "Critical"),
    ("12",   "Wealth Allocation Model",             "Marketing",        "Wealth & Investment",    "Medium"),
]


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(MODELS, columns=[
        "Model ID",
        "Model Name",
        "Model Class",
        "Markets",
        "Model Impact Category",
    ])
    out_path = OUTPUT_DIR / "model_inventory_test_dummy.xlsx"
    df.to_excel(out_path, index=False)
    print(f"Created: {out_path}")
    print(f"  Models: {len(df)}")
    impact_counts = df["Model Impact Category"].value_counts().to_dict()
    print(f"  Impact distribution: {impact_counts}")
    class_counts = df["Model Class"].value_counts().to_dict()
    print(f"  Class distribution: {class_counts}")


if __name__ == "__main__":
    main()
