"""Generate dummy laws & regulations mandates inventory for the Risk Taxonomy Transformer.

Creates one file in data/input/:

MANDATES INVENTORY (lawsandapplicability_test_dummy.xlsx):
  ~20 laws/regulations/mandates rows.
  IDs follow the MAN-1001 .. MAN-1020 scheme referenced from the legacy dummy data.

Applicability scale (ASSUMPTION — matches CIA rating style): Low / Medium / High / Critical.
If real source uses different values (text descriptions, etc.), update the scale
or swap out this column's content without changing the column name.

Usage:
    python tests/generate_laws_test_data.py
"""

import pandas as pd
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = _PROJECT_ROOT / "data" / "input"


MANDATES = [
    ("MAN-1001", "Regulation Z (Truth in Lending)",            "High"),
    ("MAN-1002", "Bank Secrecy Act (BSA)",                     "Critical"),
    ("MAN-1003", "General Data Protection Regulation (GDPR)",  "High"),
    ("MAN-1004", "Fair Credit Reporting Act (FCRA)",           "High"),
    ("MAN-1005", "CFPB Supervision",                           "High"),
    ("MAN-1006", "OCC Consent Order 2023-01",                  "Critical"),
    ("MAN-1007", "Regulation YY",                              "Medium"),
    ("MAN-1008", "Liquidity Coverage Ratio (LCR) Rule",        "High"),
    ("MAN-1009", "Payment Card Industry (PCI DSS)",            "Critical"),
    ("MAN-1010", "Regulation E (EFT Act)",                     "High"),
    ("MAN-1011", "OFAC Sanctions",                             "Critical"),
    ("MAN-1012", "FTC Consent Order 2022-14",                  "Medium"),
    ("MAN-1013", "EU PSD2 (Payment Services Directive)",       "High"),
    ("MAN-1014", "Gramm-Leach-Bliley Act (GLBA)",              "High"),
    ("MAN-1015", "California Consumer Privacy Act (CCPA)",     "High"),
    ("MAN-1016", "NYDFS Part 500 (Cybersecurity)",             "High"),
    ("MAN-1017", "FFIEC Authentication Guidance",              "Medium"),
    ("MAN-1018", "Dodd-Frank Act",                             "High"),
    ("MAN-1019", "Basel III",                                  "High"),
    ("MAN-1020", "Foreign Corrupt Practices Act (FCPA)",       "High"),
]


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(MANDATES, columns=[
        "Applicable Mandates ID",
        "Mandate Title",
        "Applicability to Audit Entity",
    ])
    out_path = OUTPUT_DIR / "lawsandapplicability_test_dummy.xlsx"
    df.to_excel(out_path, index=False)
    print(f"Created: {out_path}")
    print(f"  Mandates: {len(df)}")


if __name__ == "__main__":
    main()
