"""Generate dummy third parties inventory for the Risk Taxonomy Transformer.

Creates one file in data/input/:

THIRD PARTIES INVENTORY (all_thirdparties_test_dummy.xlsx):
  ~20 third-party engagement rows keyed by TLM ID.
  IDs follow the TLM-1001 .. TLM-1020 scheme referenced in the legacy
  dummy data's PRIMARY / SECONDARY TLM THIRD PARTY ENGAGEMENT columns.

Columns:
  - TLM ID
  - Third Party Name
  - Overall Risk  (Low / Medium / High / Critical)

Usage:
    python tests/generate_thirdparties_test_data.py
"""

import pandas as pd
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = _PROJECT_ROOT / "data" / "input"


THIRDPARTIES = [
    ("TLM-1001", "Payment Processing Partners",          "Critical"),
    ("TLM-1002", "Customer Care Services",               "High"),
    ("TLM-1003", "Analytics & Reporting Vendor",         "Medium"),
    ("TLM-1004", "Cloud Infrastructure Provider",        "Critical"),
    ("TLM-1005", "Data Enrichment Services",             "High"),
    ("TLM-1006", "Background Check Vendor",              "Medium"),
    ("TLM-1007", "KYC / AML Screening",                  "Critical"),
    ("TLM-1008", "Credit Bureau Feed",                   "High"),
    ("TLM-1009", "Fraud Detection Platform",             "Critical"),
    ("TLM-1010", "Network Operations Partner",           "High"),
    ("TLM-1011", "Collections Agency",                   "Medium"),
    ("TLM-1012", "Document Management SaaS",             "Medium"),
    ("TLM-1013", "Email / Messaging Provider",           "Low"),
    ("TLM-1014", "Card Personalization Services",        "High"),
    ("TLM-1015", "Statement Printing Vendor",            "Low"),
    ("TLM-1016", "Call Center Outsourcer",               "High"),
    ("TLM-1017", "Anti-Money Laundering Platform",       "Critical"),
    ("TLM-1018", "Regulatory Reporting Platform",        "High"),
    ("TLM-1019", "Sanctions List Provider",              "Critical"),
    ("TLM-1020", "Training Services Vendor",             "Low"),
]


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(THIRDPARTIES, columns=[
        "TLM ID",
        "Third Party Name",
        "Overall Risk",
    ])
    out_path = OUTPUT_DIR / "all_thirdparties_test_dummy.xlsx"
    df.to_excel(out_path, index=False)
    print(f"Created: {out_path}")
    print(f"  Third parties: {len(df)}")
    critical_cnt = (df["Overall Risk"] == "Critical").sum()
    print(f"  Critical-risk TPs: {critical_cnt}")


if __name__ == "__main__":
    main()
