"""Generate dummy applications inventory for the Risk Taxonomy Transformer.

Creates one file in data/input/:

APPLICATIONS INVENTORY (all_applications_test_dummy.xlsx):
  ~40 application rows with CIA triad risk ratings
  (Confidentiality Risk, Availability Risk, Integrity Risk).
  IDs follow the ARA-1001 .. ARA-1040 scheme used in the legacy dummy data.

Usage:
    python tests/generate_applications_test_data.py
"""

import pandas as pd
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = _PROJECT_ROOT / "data" / "input"


APPLICATIONS = [
    ("ARA-1001", "Consumer Cards Origination Platform",     "Critical", "High",     "Critical"),
    ("ARA-1002", "Cards Ledger System",                     "High",     "Critical", "Critical"),
    ("ARA-1003", "Cardmember Rewards Engine",               "Medium",   "High",     "High"),
    ("ARA-1004", "Fraud Scoring Gateway",                   "High",     "Critical", "Critical"),
    ("ARA-1005", "Credit Decision Engine",                  "Critical", "Critical", "Critical"),
    ("ARA-1006", "Statement Generation Service",            "Medium",   "Medium",   "High"),
    ("ARA-1007", "Collections Workstation",                 "High",     "High",     "High"),
    ("ARA-1008", "Customer Data Warehouse",                 "High",     "Medium",   "High"),
    ("ARA-1009", "Treasury Cash Management",                "High",     "Critical", "Critical"),
    ("ARA-1010", "FTP Allocation System",                   "Medium",   "High",     "High"),
    ("ARA-1011", "Merchant Acquiring Gateway",              "High",     "Critical", "Critical"),
    ("ARA-1012", "Chargeback Processing System",            "Medium",   "High",     "High"),
    ("ARA-1013", "Sanctions Screening Engine",              "High",     "Critical", "Critical"),
    ("ARA-1014", "Terminal Management Platform",            "Medium",   "High",     "High"),
    ("ARA-1015", "Digital Banking Portal",                  "High",     "Critical", "Critical"),
    ("ARA-1016", "Mobile Banking App",                      "High",     "Critical", "Critical"),
    ("ARA-1017", "Biometric Authentication Service",        "Critical", "High",     "Critical"),
    ("ARA-1018", "API Gateway (Public)",                    "High",     "Critical", "Critical"),
    ("ARA-1019", "Core Onboarding Service",                 "High",     "High",     "High"),
    ("ARA-1020", "New Markets Sandbox",                     "Low",      "Low",      "Medium"),
    ("ARA-1021", "Country Risk Monitoring Tool",            "Medium",   "Medium",   "Medium"),
    ("ARA-1022", "Enterprise Risk Aggregator",              "High",     "Medium",   "High"),
    ("ARA-1023", "Stress Test Compute Grid",                "Medium",   "Medium",   "High"),
    ("ARA-1024", "Capital Planning Workbench",              "Medium",   "Medium",   "High"),
    ("ARA-1025", "Wealth Portfolio Optimizer",              "Medium",   "High",     "High"),
    ("ARA-1026", "Robo-Advisor Recommender",                "Medium",   "Medium",   "High"),
    ("ARA-1027", "Investment Suitability Engine",           "Medium",   "Medium",   "High"),
    ("ARA-1028", "Cross-Border Payments Hub",               "Critical", "Critical", "Critical"),
    ("ARA-1029", "FX Pricing Engine",                       "High",     "Critical", "Critical"),
    ("ARA-1030", "Correspondent Bank Settlement System",    "High",     "Critical", "Critical"),
    ("ARA-1031", "Global AML Monitoring Platform",          "High",     "Critical", "Critical"),
    ("ARA-1032", "Shared Identity Provider",                "High",     "Critical", "Critical"),
    ("ARA-1033", "Employee Directory Service",              "Medium",   "High",     "Medium"),
    ("ARA-1034", "Shared File Storage",                     "Medium",   "Medium",   "Medium"),
    ("ARA-1035", "Legacy Mainframe Gateway",                "High",     "High",     "High"),
    ("ARA-1036", "Regulatory Reporting Hub",                "High",     "High",     "Critical"),
    ("ARA-1037", "Model Risk Inventory",                    "Medium",   "Medium",   "High"),
    ("ARA-1038", "Model Validation Workbench",              "Medium",   "Medium",   "High"),
    ("ARA-1039", "Privacy Consent Management",              "High",     "High",     "High"),
    ("ARA-1040", "Data Governance Catalog",                 "High",     "Medium",   "High"),
]


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(APPLICATIONS, columns=[
        "ARA ID",
        "Application Name",
        "Confidentiality Risk",
        "Availability Risk",
        "Integrity Risk",
    ])
    out_path = OUTPUT_DIR / "all_applications_test_dummy.xlsx"
    df.to_excel(out_path, index=False)
    print(f"Created: {out_path}")
    print(f"  Applications: {len(df)}")
    critical_cnt = df[(df["Confidentiality Risk"] == "Critical") | (df["Availability Risk"] == "Critical") | (df["Integrity Risk"] == "Critical")].shape[0]
    print(f"  Apps with at least one Critical CIA rating: {critical_cnt}")


if __name__ == "__main__":
    main()
