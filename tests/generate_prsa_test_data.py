"""Generate dummy test data for the PRSA (Process Risk Self Assessment) pipeline.

Creates one file in data/input/:

PRSA FRANKENSTEIN REPORT (prsa_report_test_dummy.xlsx):
  ~35 rows simulating the cross-joined AE/PRSA/Issue/Control report.

  Row grain: one issue x one PRSA control combination.

  Test scenarios covered:

  1. Basic case: AE-1 has a few PRSAs, some with issues, some clean
  2. Multi-AE PRSA sharing: PRSA-003 tagged to AE-1, AE-3, and AE-5
  3. Issue with multiple PRSA controls: ISS-004 spans two PRSA controls
  4. Various issue statuses: Open, Pending Validation, Pending Sustainability, Closed
  5. Various issue ratings: Low, Medium, High, Critical
  6. Various breakdown types: Control Gap, Control Design, Operating Effectiveness
  7. AE with no issues: AE-7 has PRSAs tagged but zero issue rows
  8. Column H multi-value: AEs carry 3-6 newline-separated PRSAs in "All PRSAs Tagged to AE"
  9. Cross-AE impact: PRSA-003 and ISS-006 visible from multiple AEs

  AEs reused from generate_test_data.py:
    AE-1  North America Cards        (Team Alpha)
    AE-2  Treasury Operations        (Team Bravo)
    AE-3  Global Merchant Services   (Team Charlie)
    AE-4  Digital Banking Platform   (Team Delta)
    AE-5  New Markets Expansion      (Team Alpha)
    AE-6  Enterprise Risk Services   (Team Bravo)
    AE-7  Dormant Entity - Legacy    (Team Charlie)   <-- clean AE, no issues
    AE-8  Investment Products        (Team Delta)
    AE-9  Cross-Border Operations    (Team Alpha)
    AE-10 Internal Shared Services   (Team Charlie)

Usage:
    python tests/generate_prsa_test_data.py
"""

import pandas as pd
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = _PROJECT_ROOT / "data" / "input"

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

AE_CATALOG = {
    "AE-1":  ("North America Cards",       "Alice Johnson",  "Team Alpha"),
    "AE-2":  ("Treasury Operations",        "Bob Martinez",   "Team Bravo"),
    "AE-3":  ("Global Merchant Services",   "Carol Chen",     "Team Charlie"),
    "AE-4":  ("Digital Banking Platform",   "David Kim",      "Team Delta"),
    "AE-5":  ("New Markets Expansion",      "Eve Rodriguez",  "Team Alpha"),
    "AE-6":  ("Enterprise Risk Services",   "Frank Patel",    "Team Bravo"),
    "AE-7":  ("Dormant Entity - Legacy",    "Grace Lee",      "Team Charlie"),
    "AE-8":  ("Investment Products",        "Henry Wu",       "Team Delta"),
    "AE-9":  ("Cross-Border Operations",    "Irene Tanaka",   "Team Alpha"),
    "AE-10": ("Internal Shared Services",   "James Okafor",   "Team Charlie"),
}

# Which PRSAs are tagged to each AE (appears in column H, newline-separated)
AE_PRSA_TAGS = {
    "AE-1":  ["PRSA-001", "PRSA-002", "PRSA-003"],
    "AE-2":  ["PRSA-004", "PRSA-005"],
    "AE-3":  ["PRSA-003", "PRSA-006", "PRSA-007", "PRSA-008"],
    "AE-4":  ["PRSA-009", "PRSA-010", "PRSA-011"],
    "AE-5":  ["PRSA-003", "PRSA-012", "PRSA-013", "PRSA-014", "PRSA-015"],
    "AE-6":  ["PRSA-016", "PRSA-017"],
    "AE-7":  ["PRSA-018", "PRSA-019"],              # clean AE — no issue rows
    "AE-8":  ["PRSA-020", "PRSA-021", "PRSA-022"],
    "AE-9":  ["PRSA-023", "PRSA-024", "PRSA-025", "PRSA-026"],
    "AE-10": ["PRSA-027", "PRSA-028"],
}

PRSA_PROCESSES = {
    "PRSA-001": ("Account Origination",            "Linda Torres"),
    "PRSA-002": ("Credit Limit Management",        "Mark Davis"),
    "PRSA-003": ("Merchant Onboarding",            "Nina Gupta"),       # shared across AE-1, AE-3, AE-5
    "PRSA-004": ("Interest Rate Risk Management",  "Oscar Hernandez"),
    "PRSA-005": ("Funding Allocation",             "Paula Singh"),
    "PRSA-006": ("Transaction Authorization",      "Quinn Baker"),
    "PRSA-007": ("Chargeback Processing",          "Rachel Kim"),
    "PRSA-008": ("Merchant Dispute Resolution",    "Sam Turner"),
    "PRSA-009": ("Digital Account Opening",        "Tina Zhao"),
    "PRSA-010": ("Mobile Payment Processing",      "Uma Patel"),
    "PRSA-011": ("Digital Fraud Detection",        "Victor Ramos"),
    "PRSA-012": ("New Market Due Diligence",       "Wendy Chang"),
    "PRSA-013": ("Regulatory License Management",  "Xavier Diaz"),
    "PRSA-014": ("Cross-Border Payment Routing",   "Yolanda Fischer"),
    "PRSA-015": ("Local Partner Oversight",        "Zach Mooney"),
    "PRSA-016": ("Enterprise Risk Reporting",      "Andrea Wolfe"),
    "PRSA-017": ("Risk Appetite Monitoring",       "Brian Yates"),
    "PRSA-020": ("Portfolio Rebalancing",          "Carlos Mendez"),
    "PRSA-021": ("NAV Calculation",                "Diana Liu"),
    "PRSA-022": ("Investment Suitability Review",  "Edward Stokes"),
    "PRSA-023": ("FX Settlement",                  "Fiona Grant"),
    "PRSA-024": ("Correspondent Banking Oversight", "George Owens"),
    "PRSA-025": ("Sanctions Screening - Cross-Border", "Hannah Price"),
    "PRSA-026": ("Trade Finance Documentation",    "Ivan Petrov"),
    "PRSA-027": ("Shared Services Invoice Processing", "Julia Norris"),
    "PRSA-028": ("IT Asset Management",            "Kevin Doyle"),
}


# ---------------------------------------------------------------------------
# Issue / control rows
# ---------------------------------------------------------------------------

def _build_rows() -> list[dict]:
    """Return the list of row dicts for the Frankenstein report."""

    rows: list[dict] = []

    def _add(ae_id, eng_id, issue_id, issue_rating, issue_status,
             identified_by, identifier, breakdown_type, owning_bu,
             issue_title, issue_desc, issue_owner,
             ctrl_id, prsa_id, ctrl_title):
        ae_name, audit_leader, team = AE_CATALOG[ae_id]
        process_title, process_owner = PRSA_PROCESSES[prsa_id]
        rows.append({
            "AE ID":                        ae_id,
            "AE Name":                      ae_name,
            "Audit Leader":                 audit_leader,
            "Core Audit Team":              team,
            "Audit Engagement ID":          eng_id,
            "Current On House Memo Date":   "2025-09-15",
            "Current Report Date":          "2025-12-01",
            "All PRSAs Tagged to AE":       "\n".join(AE_PRSA_TAGS[ae_id]),
            "Issue ID":                     issue_id,
            "Issue Rating":                 issue_rating,
            "Issue Status":                 issue_status,
            "Issue Identified By Group":    identified_by,
            "Issue Identifier":             identifier,
            "Issue Breakdown Type":         breakdown_type,
            "Issue Owning Business Unit":   owning_bu,
            "Issue Title":                  issue_title,
            "Issue Description":            issue_desc,
            "Issue Owner":                  issue_owner,
            "Control ID (PRSA)":            ctrl_id,
            "PRSA ID":                      prsa_id,
            "Process Title":                process_title,
            "Process Owner":                process_owner,
            "Control Title":                ctrl_title,
        })

    # -----------------------------------------------------------------------
    # Scenario 1 — Basic case: AE-1 has a few PRSAs, issues on some
    # -----------------------------------------------------------------------
    _add("AE-1", "ENG-101", "ISS-001", "Medium", "Open",
         "Audit", "Alice Johnson", "Control Gap", "Consumer Lending",
         "Incomplete KYC documentation at origination",
         "Account origination process does not consistently capture all required "
         "KYC documents before account activation, leading to downstream AML gaps.",
         "Linda Torres",
         "CTRL-PRSA-001", "PRSA-001",
         "KYC Document Completeness Check")

    _add("AE-1", "ENG-101", "ISS-002", "Low", "Closed",
         "Self-Identified", "Mark Davis", "Operating Effectiveness", "Consumer Lending",
         "Credit limit override approvals not retained",
         "Manual overrides of automated credit limit decisions lack documented "
         "supervisory approval in 12% of sampled cases.",
         "Mark Davis",
         "CTRL-PRSA-002", "PRSA-002",
         "Credit Limit Override Approval")

    # -----------------------------------------------------------------------
    # Scenario 2 — Multi-AE PRSA sharing: PRSA-003 tagged to AE-1, AE-3, AE-5
    # -----------------------------------------------------------------------
    _add("AE-1", "ENG-101", "ISS-003", "High", "Open",
         "Audit", "Alice Johnson", "Control Design", "Merchant Services",
         "Merchant onboarding lacks automated sanctions screening",
         "Merchant onboarding process relies on manual sanctions list checks. "
         "No automated screening integration with OFAC/SDN lists.",
         "Nina Gupta",
         "CTRL-PRSA-003", "PRSA-003",
         "Merchant Sanctions Screening")

    _add("AE-3", "ENG-301", "ISS-006", "High", "Open",
         "Audit", "Carol Chen", "Control Design", "Merchant Services",
         "Merchant onboarding lacks automated sanctions screening",
         "Same issue observed from Global Merchant Services perspective. "
         "Merchant onboarding process relies on manual sanctions list checks.",
         "Nina Gupta",
         "CTRL-PRSA-003", "PRSA-003",
         "Merchant Sanctions Screening")

    _add("AE-5", "ENG-501", "ISS-007", "High", "Pending Validation",
         "Second Line", "Eve Rodriguez", "Control Design", "New Markets",
         "Merchant onboarding sanctions gap — new market exposure",
         "New Markets expansion into high-risk jurisdictions amplifies the "
         "merchant onboarding sanctions screening gap identified in PRSA-003.",
         "Nina Gupta",
         "CTRL-PRSA-003", "PRSA-003",
         "Merchant Sanctions Screening")

    # -----------------------------------------------------------------------
    # Scenario 3 — Issue with multiple PRSA controls (ISS-004 spans two ctrls)
    # -----------------------------------------------------------------------
    _add("AE-4", "ENG-401", "ISS-004", "Critical", "Open",
         "Audit", "David Kim", "Control Gap", "Digital Banking",
         "Digital account opening bypasses identity verification",
         "The digital account opening flow allows account creation before "
         "identity verification completes under certain timeout conditions. "
         "Both the identity check control and the fraud detection control failed.",
         "Tina Zhao",
         "CTRL-PRSA-009", "PRSA-009",
         "Identity Verification Gate")

    _add("AE-4", "ENG-401", "ISS-004", "Critical", "Open",
         "Audit", "David Kim", "Control Gap", "Digital Banking",
         "Digital account opening bypasses identity verification",
         "The digital account opening flow allows account creation before "
         "identity verification completes under certain timeout conditions. "
         "Both the identity check control and the fraud detection control failed.",
         "Victor Ramos",
         "CTRL-PRSA-011", "PRSA-011",
         "Real-Time Fraud Score Threshold")

    # -----------------------------------------------------------------------
    # Scenario 4 — Various issue statuses
    # -----------------------------------------------------------------------
    _add("AE-2", "ENG-201", "ISS-008", "Medium", "Pending Sustainability",
         "Audit", "Bob Martinez", "Operating Effectiveness", "Treasury",
         "Interest rate hedge documentation gaps",
         "Hedge effectiveness documentation not updated within the required "
         "30-day window for 8 of 25 sampled hedge relationships.",
         "Oscar Hernandez",
         "CTRL-PRSA-004", "PRSA-004",
         "Hedge Documentation Timeliness")

    _add("AE-2", "ENG-201", "ISS-009", "Low", "Closed",
         "Self-Identified", "Paula Singh", "Control Gap", "Treasury",
         "Funding allocation model input stale by one quarter",
         "The quarterly funding allocation model used market data that was "
         "one quarter stale due to a feed refresh delay.",
         "Paula Singh",
         "CTRL-PRSA-005", "PRSA-005",
         "Market Data Refresh Validation")

    _add("AE-6", "ENG-601", "ISS-010", "Medium", "Pending Validation",
         "Second Line", "Frank Patel", "Control Design", "Enterprise Risk",
         "Risk appetite dashboard missing operational risk metrics",
         "The enterprise risk appetite dashboard does not include key "
         "operational risk metrics, limiting board visibility.",
         "Brian Yates",
         "CTRL-PRSA-017", "PRSA-017",
         "Risk Appetite Completeness Check")

    _add("AE-8", "ENG-801", "ISS-011", "Low", "Closed",
         "Self-Identified", "Henry Wu", "Operating Effectiveness", "Investments",
         "NAV calculation rounding variance exceeds tolerance",
         "NAV calculation for three funds showed rounding variances exceeding "
         "the 0.01% tolerance threshold on month-end processing.",
         "Diana Liu",
         "CTRL-PRSA-021", "PRSA-021",
         "NAV Rounding Tolerance Check")

    # -----------------------------------------------------------------------
    # Scenario 5 — Various issue ratings
    # -----------------------------------------------------------------------
    _add("AE-3", "ENG-301", "ISS-012", "Critical", "Open",
         "Audit", "Carol Chen", "Control Gap", "Merchant Services",
         "Chargeback processing SLA breach — systemic",
         "Chargeback processing consistently exceeds contractual SLA timelines, "
         "resulting in regulatory exposure and merchant financial harm.",
         "Rachel Kim",
         "CTRL-PRSA-007", "PRSA-007",
         "Chargeback SLA Monitoring")

    _add("AE-3", "ENG-301", "ISS-013", "Low", "Pending Sustainability",
         "Self-Identified", "Sam Turner", "Operating Effectiveness", "Merchant Services",
         "Dispute resolution evidence retention incomplete",
         "Merchant dispute resolution files missing supporting evidence "
         "attachments in 7% of sampled cases.",
         "Sam Turner",
         "CTRL-PRSA-008", "PRSA-008",
         "Dispute Evidence Completeness")

    # -----------------------------------------------------------------------
    # Scenario 6 — Various breakdown types
    # -----------------------------------------------------------------------
    _add("AE-4", "ENG-401", "ISS-014", "Medium", "Open",
         "Audit", "David Kim", "Control Design", "Digital Banking",
         "Mobile payment tokenization design flaw",
         "Token generation algorithm uses a predictable seed value, creating "
         "potential for token collision in high-volume scenarios.",
         "Uma Patel",
         "CTRL-PRSA-010", "PRSA-010",
         "Token Generation Uniqueness")

    _add("AE-9", "ENG-901", "ISS-015", "High", "Open",
         "Audit", "Irene Tanaka", "Control Gap", "International Operations",
         "FX settlement pre-funding requirement not enforced",
         "Correspondent banking FX settlements processed without confirming "
         "pre-funding, exposing the bank to settlement risk.",
         "Fiona Grant",
         "CTRL-PRSA-023", "PRSA-023",
         "FX Pre-Funding Verification")

    _add("AE-9", "ENG-901", "ISS-016", "Medium", "Pending Validation",
         "Second Line", "George Owens", "Operating Effectiveness", "International Operations",
         "Correspondent bank due diligence reviews overdue",
         "Annual due diligence reviews for 4 of 12 correspondent banking "
         "relationships are more than 90 days overdue.",
         "George Owens",
         "CTRL-PRSA-024", "PRSA-024",
         "Correspondent Bank Review Timeliness")

    # -----------------------------------------------------------------------
    # Scenario 8 — More multi-value column H + sparse issue coverage
    # -----------------------------------------------------------------------
    _add("AE-5", "ENG-501", "ISS-017", "Medium", "Open",
         "Audit", "Eve Rodriguez", "Control Gap", "New Markets",
         "Regulatory license tracking spreadsheet not maintained",
         "New market regulatory license inventory maintained in a manual "
         "spreadsheet with no version control or audit trail.",
         "Xavier Diaz",
         "CTRL-PRSA-013", "PRSA-013",
         "License Inventory Completeness")

    _add("AE-5", "ENG-501", "ISS-018", "Low", "Closed",
         "Self-Identified", "Yolanda Fischer", "Operating Effectiveness", "New Markets",
         "Cross-border payment routing fallback not tested",
         "The fallback routing path for cross-border payments has not been "
         "tested in 18 months despite policy requiring semi-annual testing.",
         "Yolanda Fischer",
         "CTRL-PRSA-014", "PRSA-014",
         "Payment Routing Fallback Test")

    # -----------------------------------------------------------------------
    # Additional rows for AE-6, AE-8, AE-9, AE-10
    # -----------------------------------------------------------------------
    _add("AE-6", "ENG-601", "ISS-019", "High", "Open",
         "Audit", "Frank Patel", "Control Gap", "Enterprise Risk",
         "Enterprise risk report data aggregation errors",
         "Monthly enterprise risk report contains data aggregation errors "
         "due to inconsistent source system extracts across business units.",
         "Andrea Wolfe",
         "CTRL-PRSA-016", "PRSA-016",
         "Risk Data Aggregation Reconciliation")

    _add("AE-8", "ENG-801", "ISS-020", "Medium", "Open",
         "Audit", "Henry Wu", "Control Design", "Investments",
         "Portfolio rebalancing drift threshold too wide",
         "Automated portfolio rebalancing triggers only when drift exceeds 10%, "
         "well above the 5% policy threshold, due to a configuration error.",
         "Carlos Mendez",
         "CTRL-PRSA-020", "PRSA-020",
         "Rebalancing Drift Threshold")

    _add("AE-8", "ENG-801", "ISS-021", "High", "Pending Validation",
         "Second Line", "Edward Stokes", "Control Gap", "Investments",
         "Suitability review not performed for high-risk product switches",
         "Product switch requests for high-risk investment products processed "
         "without the required suitability reassessment in 15% of cases.",
         "Edward Stokes",
         "CTRL-PRSA-022", "PRSA-022",
         "Product Switch Suitability Gate")

    _add("AE-9", "ENG-901", "ISS-022", "Critical", "Open",
         "Audit", "Irene Tanaka", "Control Gap", "International Operations",
         "Sanctions screening gap on cross-border wire transfers",
         "Cross-border wire transfers routed through a secondary channel "
         "bypass the primary sanctions screening engine entirely.",
         "Hannah Price",
         "CTRL-PRSA-025", "PRSA-025",
         "Cross-Border Sanctions Filter")

    _add("AE-9", "ENG-901", "ISS-023", "Low", "Closed",
         "Self-Identified", "Ivan Petrov", "Operating Effectiveness", "International Operations",
         "Trade finance document archival delayed",
         "Trade finance supporting documents not archived within the 5-day "
         "policy window in 20% of sampled transactions.",
         "Ivan Petrov",
         "CTRL-PRSA-026", "PRSA-026",
         "Trade Document Archival Timeliness")

    _add("AE-10", "ENG-1001", "ISS-024", "Medium", "Open",
         "Audit", "James Okafor", "Control Design", "Shared Services",
         "Invoice processing lacks three-way match for low-value items",
         "Shared services invoice processing does not perform three-way match "
         "(PO, receipt, invoice) for items under $5,000, creating fraud risk.",
         "Julia Norris",
         "CTRL-PRSA-027", "PRSA-027",
         "Three-Way Match Enforcement")

    _add("AE-10", "ENG-1001", "ISS-025", "Low", "Pending Sustainability",
         "Self-Identified", "Kevin Doyle", "Operating Effectiveness", "Shared Services",
         "IT asset inventory reconciliation overdue",
         "Quarterly IT asset inventory reconciliation not completed for the "
         "past two cycles. Hardware asset tags missing for 8% of devices.",
         "Kevin Doyle",
         "CTRL-PRSA-028", "PRSA-028",
         "IT Asset Reconciliation")

    # -----------------------------------------------------------------------
    # Scenario 9 — Cross-AE impact: ISS-006 also visible from AE-5 perspective
    #   (PRSA-003 shared; different control on same PRSA)
    # -----------------------------------------------------------------------
    _add("AE-5", "ENG-501", "ISS-006", "High", "Open",
         "Audit", "Eve Rodriguez", "Control Design", "New Markets",
         "Merchant onboarding lacks automated sanctions screening",
         "Cross-AE visibility: same issue as AE-3, observed from New Markets "
         "due to shared PRSA-003 dependency.",
         "Nina Gupta",
         "CTRL-PRSA-003", "PRSA-003",
         "Merchant Sanctions Screening")

    # -----------------------------------------------------------------------
    # Extra rows: same issue, different control on same PRSA (ISS-012 second ctrl)
    # -----------------------------------------------------------------------
    _add("AE-3", "ENG-301", "ISS-012", "Critical", "Open",
         "Audit", "Carol Chen", "Control Gap", "Merchant Services",
         "Chargeback processing SLA breach — systemic",
         "Second control failure: automated chargeback dispute notification "
         "to merchants not triggered within contractual window.",
         "Quinn Baker",
         "CTRL-PRSA-006", "PRSA-006",
         "Merchant Notification Timeliness")

    # Additional row for AE-1 — PRSA-002, different issue
    _add("AE-1", "ENG-101", "ISS-026", "Medium", "Pending Validation",
         "Audit", "Alice Johnson", "Operating Effectiveness", "Consumer Lending",
         "Credit limit increase batch job skips error records silently",
         "The nightly credit limit increase batch process silently skips "
         "records that fail validation instead of routing them for review.",
         "Mark Davis",
         "CTRL-PRSA-002B", "PRSA-002",
         "Batch Error Handling Control")

    # -----------------------------------------------------------------------
    # Additional rows to reach ~35 total
    # -----------------------------------------------------------------------
    _add("AE-4", "ENG-401", "ISS-027", "High", "Pending Sustainability",
         "Second Line", "Victor Ramos", "Operating Effectiveness", "Digital Banking",
         "Digital fraud detection model false-negative rate elevated",
         "The real-time fraud detection model shows a 12% false-negative rate "
         "on card-not-present transactions, up from the 5% baseline.",
         "Victor Ramos",
         "CTRL-PRSA-011B", "PRSA-011",
         "Fraud Model Performance Monitoring")

    _add("AE-3", "ENG-301", "ISS-028", "Medium", "Open",
         "Audit", "Carol Chen", "Control Gap", "Merchant Services",
         "Transaction authorization timeout handling inconsistent",
         "When the authorization gateway times out, fallback logic varies "
         "by merchant category code, with some codes defaulting to approve.",
         "Quinn Baker",
         "CTRL-PRSA-006B", "PRSA-006",
         "Authorization Timeout Fallback Logic")

    _add("AE-10", "ENG-1001", "ISS-029", "High", "Open",
         "Audit", "James Okafor", "Control Design", "Shared Services",
         "IT asset disposal process lacks data sanitization verification",
         "Decommissioned IT assets do not undergo verified data sanitization "
         "before disposal, creating data leakage risk.",
         "Kevin Doyle",
         "CTRL-PRSA-028B", "PRSA-028",
         "Asset Disposal Data Wipe Verification")

    _add("AE-5", "ENG-501", "ISS-030", "Critical", "Open",
         "Audit", "Eve Rodriguez", "Control Gap", "New Markets",
         "Local partner financial health monitoring absent",
         "No ongoing financial health monitoring of local market partners "
         "after initial due diligence. Two partners show signs of distress.",
         "Zach Mooney",
         "CTRL-PRSA-015", "PRSA-015",
         "Partner Financial Health Review")

    _add("AE-2", "ENG-201", "ISS-031", "Medium", "Open",
         "Audit", "Bob Martinez", "Control Design", "Treasury",
         "Interest rate risk limit breach notification delayed",
         "Automated notifications for interest rate risk limit breaches "
         "are delayed by up to 4 hours due to batch processing cadence.",
         "Oscar Hernandez",
         "CTRL-PRSA-004B", "PRSA-004",
         "Limit Breach Real-Time Alert")

    _add("AE-6", "ENG-601", "ISS-032", "Low", "Closed",
         "Self-Identified", "Andrea Wolfe", "Operating Effectiveness", "Enterprise Risk",
         "Risk report distribution list includes former employees",
         "Monthly enterprise risk report distributed to 3 former employees "
         "whose email accounts remain active post-termination.",
         "Andrea Wolfe",
         "CTRL-PRSA-016B", "PRSA-016",
         "Report Distribution List Review")

    _add("AE-9", "ENG-901", "ISS-033", "High", "Pending Validation",
         "Audit", "Irene Tanaka", "Control Design", "International Operations",
         "Trade finance letter of credit validation incomplete",
         "Letters of credit for trade finance transactions not validated "
         "against UCP 600 standards, creating documentary credit risk.",
         "Ivan Petrov",
         "CTRL-PRSA-026B", "PRSA-026",
         "LC Documentary Compliance Check")

    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def generate_prsa_data() -> pd.DataFrame:
    """Build the PRSA Frankenstein report DataFrame."""
    return pd.DataFrame(_build_rows())


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = generate_prsa_data()
    out_path = OUTPUT_DIR / "prsa_report_test_dummy.xlsx"
    df.to_excel(out_path, index=False)
    print(f"Created: {out_path}")
    print(f"  Total rows: {len(df)}")

    # Summary statistics
    unique_issues = df["Issue ID"].nunique()
    unique_prsas = df["PRSA ID"].nunique()
    unique_aes = df["AE ID"].nunique()
    unique_ctrls = df["Control ID (PRSA)"].nunique()

    print(f"  Unique AEs:            {unique_aes}")
    print(f"  Unique PRSAs:          {unique_prsas}")
    print(f"  Unique issues:         {unique_issues}")
    print(f"  Unique PRSA controls:  {unique_ctrls}")

    print("\nScenario coverage:")
    print("  1. Basic case:            AE-1 with PRSA-001, PRSA-002 issues")
    print("  2. Multi-AE PRSA sharing: PRSA-003 tagged to AE-1, AE-3, AE-5")
    print("  3. Multi-control issue:   ISS-004 -> CTRL-PRSA-009, CTRL-PRSA-011")
    print("  4. Issue statuses:        Open, Pending Validation, Pending Sustainability, Closed")
    print("  5. Issue ratings:         Low, Medium, High, Critical")
    print("  6. Breakdown types:       Control Gap, Control Design, Operating Effectiveness")
    print("  7. Clean AE (no issues):  AE-7 (has PRSAs tagged but no rows)")
    print("  8. Multi-value col H:     AE-5 has 5 PRSAs, AE-3 has 4, etc.")
    print("  9. Cross-AE impact:       ISS-006 appears under AE-3 and AE-5")

    # Verify column H multi-value content
    max_tags = df["All PRSAs Tagged to AE"].apply(lambda x: len(x.split("\n"))).max()
    print(f"\n  Max PRSAs in column H:  {max_tags}")

    # Verify AE-7 is NOT in the issue rows (clean AE)
    ae7_rows = df[df["AE ID"] == "AE-7"]
    print(f"  AE-7 issue rows:        {len(ae7_rows)} (expected 0 — clean AE)")


if __name__ == "__main__":
    main()
