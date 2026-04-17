"""Generate dummy policies/standards/procedures inventory for the Risk Taxonomy Transformer.

Creates one file in data/input/:

POLICIES INVENTORY (policystandardprocedure_test_dummy.xlsx):
  ~25 policy/standard/procedure rows.
  IDs follow the PSP-101 .. PSP-125 scheme referenced from the legacy dummy data.

Usage:
    python tests/generate_policies_test_data.py
"""

import pandas as pd
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = _PROJECT_ROOT / "data" / "input"


POLICIES = [
    ("PSP-101", "Consumer Credit Policy"),
    ("PSP-102", "Anti-Money Laundering Standard"),
    ("PSP-103", "Third Party Risk Procedure"),
    ("PSP-104", "Fraud Management Policy"),
    ("PSP-105", "Data Governance Standard"),
    ("PSP-106", "Liquidity Risk Policy"),
    ("PSP-107", "Treasury Operations Standard"),
    ("PSP-108", "Counterparty Credit Procedure"),
    ("PSP-109", "Merchant Acquiring Policy"),
    ("PSP-110", "Payment Card Industry Procedure"),
    ("PSP-111", "Sanctions Screening Standard"),
    ("PSP-112", "Consumer Complaint Handling Procedure"),
    ("PSP-113", "Digital Identity Policy"),
    ("PSP-114", "Mobile Banking Standard"),
    ("PSP-115", "API Security Procedure"),
    ("PSP-116", "Information Security Policy"),
    ("PSP-117", "Incident Response Standard"),
    ("PSP-118", "Customer Authentication Procedure"),
    ("PSP-119", "New Market Entry Policy"),
    ("PSP-120", "Country Risk Procedure"),
    ("PSP-121", "Enterprise Risk Management Framework"),
    ("PSP-122", "Risk Appetite Statement"),
    ("PSP-123", "Model Risk Management Policy"),
    ("PSP-124", "Capital Planning Standard"),
    ("PSP-125", "Three Lines of Defense Policy"),
]


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(POLICIES, columns=[
        "PSP ID",
        "Policy/Standard/Procedure Name",
    ])
    out_path = OUTPUT_DIR / "policystandardprocedure_test_dummy.xlsx"
    df.to_excel(out_path, index=False)
    print(f"Created: {out_path}")
    print(f"  Policies/Standards/Procedures: {len(df)}")


if __name__ == "__main__":
    main()
