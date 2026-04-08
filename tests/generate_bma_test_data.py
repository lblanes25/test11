"""Generate dummy test data for the BMA (Business Monitoring Activities) pipeline.

Creates one file in data/input/:

BM Activities (bm_activities_test_dummy.xlsx):
  ~25 rows simulating the business monitoring activity instance report.

  Row grain: one business monitoring activity instance.

  Test scenarios covered:

  1. Basic case: AE with a few BMA instances, some occurred (Yes), some not (No)
  2. Blank AE: 2-3 rows where "Related Audit Entity" is blank (untagged)
  3. Date range: mix of dates from July 2025 through March 2026, plus 2 rows
     with dates before July 2025 that should be filtered out during ingestion
  4. All rows have "Yes" for impact question and "Audit Entity Risk Assessment
     (AERA) Update" for action needed (real file is pre-filtered)
  5. Multiple AEs: spread across AE-1 through AE-6
  6. Some AEs with multiple BMA instances, some with just one

  AEs reused from generate_test_data.py:
    AE-1  North America Cards        (Team Alpha)
    AE-2  Treasury Operations        (Team Bravo)
    AE-3  Global Merchant Services   (Team Charlie)
    AE-4  Digital Banking Platform   (Team Delta)
    AE-5  New Markets Expansion      (Team Alpha)
    AE-6  Enterprise Risk Services   (Team Bravo)

Usage:
    python tests/generate_bma_test_data.py
"""

import pandas as pd
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = _PROJECT_ROOT / "data" / "input"

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

IMPACT_ANSWER = "Yes"
ACTION_NEEDED = "Audit Entity Risk Assessment (AERA) Update"


def _build_rows() -> list[dict]:
    """Return the list of row dicts for the BM Activities report."""

    rows: list[dict] = []

    def _add(ae_id, instance_id, activity_id, activity_title,
             planned_date, occurred, cases):
        rows.append({
            "Related Audit Entity": ae_id,
            "Activity Instance ID": instance_id,
            "Related BM Activity ID": activity_id,
            "Related BM Activity Title": activity_title,
            "Planned Instance Completion Date": planned_date,
            "Did this activity occur?": occurred,
            "Business Monitoring Cases": cases,
            "Did this activity result in an impact to one or more of the following items?": IMPACT_ANSWER,
            "If yes, select one or more of the following actions needed": ACTION_NEEDED,
        })

    # -------------------------------------------------------------------
    # Scenario 1 — Basic case: AE-1 with multiple instances
    # -------------------------------------------------------------------
    _add("AE-1", "BMA-INST-001", "BMA-ACT-001",
         "Monthly Transaction Volume Review",
         "2025-08-15", "Yes", "CASE-BMA-001")

    _add("AE-1", "BMA-INST-002", "BMA-ACT-001",
         "Monthly Transaction Volume Review",
         "2025-09-15", "No", "")

    _add("AE-1", "BMA-INST-003", "BMA-ACT-002",
         "Quarterly Fraud Indicator Assessment",
         "2025-10-01", "Yes", "CASE-BMA-002; CASE-BMA-003")

    # -------------------------------------------------------------------
    # Scenario 2 — AE-2 with single instance
    # -------------------------------------------------------------------
    _add("AE-2", "BMA-INST-004", "BMA-ACT-003",
         "Interest Rate Exposure Monitoring",
         "2025-11-30", "Yes", "CASE-BMA-004")

    # -------------------------------------------------------------------
    # Scenario 3 — AE-3 with multiple instances
    # -------------------------------------------------------------------
    _add("AE-3", "BMA-INST-005", "BMA-ACT-004",
         "Merchant Risk Tier Reassessment",
         "2025-07-31", "Yes", "CASE-BMA-005")

    _add("AE-3", "BMA-INST-006", "BMA-ACT-004",
         "Merchant Risk Tier Reassessment",
         "2025-12-31", "No", "")

    _add("AE-3", "BMA-INST-007", "BMA-ACT-005",
         "Chargeback Rate Trend Analysis",
         "2026-01-15", "Yes", "CASE-BMA-006")

    # -------------------------------------------------------------------
    # Scenario 4 — AE-4 with instances
    # -------------------------------------------------------------------
    _add("AE-4", "BMA-INST-008", "BMA-ACT-006",
         "Digital Channel Incident Monitoring",
         "2025-08-31", "Yes", "CASE-BMA-007")

    _add("AE-4", "BMA-INST-009", "BMA-ACT-007",
         "Mobile App Fraud Pattern Review",
         "2026-02-28", "Yes", "CASE-BMA-008; CASE-BMA-009")

    # -------------------------------------------------------------------
    # Scenario 5 — AE-5 with instances
    # -------------------------------------------------------------------
    _add("AE-5", "BMA-INST-010", "BMA-ACT-008",
         "New Market Regulatory Change Tracking",
         "2025-09-30", "Yes", "CASE-BMA-010")

    _add("AE-5", "BMA-INST-011", "BMA-ACT-008",
         "New Market Regulatory Change Tracking",
         "2026-01-31", "No", "")

    _add("AE-5", "BMA-INST-012", "BMA-ACT-009",
         "Cross-Border Partner Health Check",
         "2025-12-15", "Yes", "CASE-BMA-011")

    _add("AE-5", "BMA-INST-013", "BMA-ACT-010",
         "Local Licensing Compliance Review",
         "2026-03-15", "Yes", "CASE-BMA-012")

    # -------------------------------------------------------------------
    # Scenario 6 — AE-6 with single instance
    # -------------------------------------------------------------------
    _add("AE-6", "BMA-INST-014", "BMA-ACT-011",
         "Enterprise Risk Appetite Drift Monitoring",
         "2025-10-31", "Yes", "CASE-BMA-013")

    # -------------------------------------------------------------------
    # Scenario 7 — Blank AE rows (untagged activities)
    # -------------------------------------------------------------------
    _add("", "BMA-INST-015", "BMA-ACT-012",
         "Untagged Compliance Monitoring Activity",
         "2025-11-15", "Yes", "CASE-BMA-014")

    _add("", "BMA-INST-016", "BMA-ACT-013",
         "Untagged Operational Resilience Check",
         "2026-02-15", "No", "")

    _add("", "BMA-INST-017", "BMA-ACT-014",
         "Untagged Data Quality Review",
         "2026-01-20", "Yes", "CASE-BMA-015")

    # -------------------------------------------------------------------
    # Scenario 8 — Rows with dates BEFORE July 2025 (should be filtered)
    # -------------------------------------------------------------------
    _add("AE-1", "BMA-INST-018", "BMA-ACT-001",
         "Monthly Transaction Volume Review",
         "2025-05-15", "Yes", "CASE-BMA-016")

    _add("AE-3", "BMA-INST-019", "BMA-ACT-004",
         "Merchant Risk Tier Reassessment",
         "2025-06-30", "Yes", "CASE-BMA-017")

    # -------------------------------------------------------------------
    # Additional rows — more variety in dates and AEs
    # -------------------------------------------------------------------
    _add("AE-2", "BMA-INST-020", "BMA-ACT-003",
         "Interest Rate Exposure Monitoring",
         "2026-02-28", "Yes", "CASE-BMA-018")

    _add("AE-4", "BMA-INST-021", "BMA-ACT-015",
         "API Gateway Security Assessment",
         "2025-07-15", "Yes", "CASE-BMA-019")

    _add("AE-6", "BMA-INST-022", "BMA-ACT-016",
         "Risk Report Data Integrity Validation",
         "2026-03-31", "No", "")

    _add("AE-1", "BMA-INST-023", "BMA-ACT-002",
         "Quarterly Fraud Indicator Assessment",
         "2026-01-01", "Yes", "CASE-BMA-020")

    _add("AE-3", "BMA-INST-024", "BMA-ACT-005",
         "Chargeback Rate Trend Analysis",
         "2026-03-15", "Yes", "CASE-BMA-021; CASE-BMA-022")

    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def generate_bma_data() -> pd.DataFrame:
    """Build the BM Activities report DataFrame."""
    return pd.DataFrame(_build_rows())


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = generate_bma_data()
    out_path = OUTPUT_DIR / "bm_activities_test_dummy.xlsx"
    df.to_excel(out_path, index=False)
    print(f"Created: {out_path}")
    print(f"  Total rows: {len(df)}")

    # Summary statistics
    unique_instances = df["Activity Instance ID"].nunique()
    unique_activities = df["Related BM Activity ID"].nunique()
    blank_ae = df["Related Audit Entity"].apply(lambda x: str(x).strip() == "").sum()
    ae_count = df[df["Related Audit Entity"].apply(lambda x: str(x).strip() != "")]["Related Audit Entity"].nunique()

    print(f"  Unique instances:      {unique_instances}")
    print(f"  Unique activities:     {unique_activities}")
    print(f"  Unique AEs:            {ae_count}")
    print(f"  Blank AE rows:         {blank_ae}")

    # Count rows before July 2025
    dates = pd.to_datetime(df["Planned Instance Completion Date"], errors="coerce")
    pre_july = (dates < "2025-07-01").sum()
    print(f"  Rows before July 2025: {pre_july} (should be filtered during ingestion)")

    print("\nScenario coverage:")
    print("  1. Basic case:          AE-1 with multiple BMA instances")
    print("  2. Blank AE:            3 rows with no entity tagged")
    print("  3. Date range:          July 2025 through March 2026, plus 2 pre-filter rows")
    print("  4. Impact pre-filter:   All rows have Yes / AERA Update")
    print("  5. Multiple AEs:        AE-1 through AE-6")
    print("  6. Mixed occurrence:    Yes and No for 'Did this activity occur?'")


if __name__ == "__main__":
    main()
