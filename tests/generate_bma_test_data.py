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
             planned_date, occurred, cases, summary="", impact_desc=""):
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
            "Summary of Results": summary,
            "If yes, please describe impact": impact_desc,
        })

    # -------------------------------------------------------------------
    # Scenario 1 — Basic case: AE-1 with multiple instances
    # -------------------------------------------------------------------
    _add("AE-1", "BMA-INST-001", "BMA-ACT-001",
         "Monthly Transaction Volume Review",
         "2025-08-15", "Yes", "CASE-BMA-001",
         "Reviewed card transaction volumes for July. Noted a 14% month-over-month "
         "increase in declined auth attempts on the co-brand portfolio, which exceeded "
         "the variance threshold. Fraud team opened CASE-BMA-001 to investigate whether "
         "the spike reflects a new BIN-attack pattern or legitimate seasonal behavior.",
         impact_desc=(
             "Recommend revisiting the fraud inherent-risk rating for the co-brand "
             "portfolio; sustained BIN-attack attempts suggest the current AERA "
             "understates authorization-layer exposure."))

    _add("AE-1", "BMA-INST-002", "BMA-ACT-001",
         "Monthly Transaction Volume Review",
         "2025-09-15", "No", "",
         "Activity did not occur this cycle due to analyst PTO coverage gap. "
         "Rescheduled for the following cycle; no volume review performed.")

    _add("AE-1", "BMA-INST-003", "BMA-ACT-002",
         "Quarterly Fraud Indicator Assessment",
         "2025-10-01", "Yes", "CASE-BMA-002; CASE-BMA-003",
         "Quarterly fraud indicator review flagged two concerns: (1) account-takeover "
         "attempts increased 22% QoQ, concentrated in the consumer digital channel, and "
         "(2) chargeback rate on merchant-present transactions exceeded tolerance in two "
         "MCCs. Both routed to fraud investigations and merchant risk respectively.",
         impact_desc=(
             "Recommend updating the AERA to reflect elevated account-takeover exposure "
             "in the consumer digital channel; current inherent rating understates this "
             "risk. Merchant-present chargeback trend should be reassessed in the next "
             "control-effectiveness review."))

    # -------------------------------------------------------------------
    # Scenario 2 — AE-2 with single instance
    # -------------------------------------------------------------------
    _add("AE-2", "BMA-INST-004", "BMA-ACT-003",
         "Interest Rate Exposure Monitoring",
         "2025-11-30", "Yes", "CASE-BMA-004",
         "IR risk dashboard showed the treasury portfolio's DV01 approaching the inner "
         "limit for the first time in 18 months. Primary driver is the extension of "
         "the fixed-rate investment book. Case opened to track whether ALCO action is "
         "needed; no breach to date.",
         impact_desc=(
             "Recommend the AERA reflect the portfolio's proximity to the DV01 inner "
             "limit as a directional driver of interest-rate risk; control assessment "
             "should note reliance on ALCO discretion for near-limit positions."))

    # -------------------------------------------------------------------
    # Scenario 3 — AE-3 with multiple instances
    # -------------------------------------------------------------------
    _add("AE-3", "BMA-INST-005", "BMA-ACT-004",
         "Merchant Risk Tier Reassessment",
         "2025-07-31", "Yes", "CASE-BMA-005",
         "Reassessed risk tiers for the merchant book. 23 merchants moved to higher "
         "tiers based on updated chargeback and fraud-rate inputs; 11 moved to lower "
         "tiers. One large-volume travel merchant flagged for enhanced monitoring due "
         "to sustained chargeback ratios above the 1% threshold.",
         impact_desc=(
             "Recommend the AERA for merchant credit reflect the net upward drift in "
             "tier distribution; the travel-merchant outlier warrants named exposure "
             "in the rationale and should be revisited at the next control review."))

    _add("AE-3", "BMA-INST-006", "BMA-ACT-004",
         "Merchant Risk Tier Reassessment",
         "2025-12-31", "No", "",
         "Activity did not occur — underlying merchant-tier data feed was delayed by "
         "the upstream partner. Rescheduled to Q1 once data arrives.")

    _add("AE-3", "BMA-INST-007", "BMA-ACT-005",
         "Chargeback Rate Trend Analysis",
         "2026-01-15", "Yes", "CASE-BMA-006",
         "Chargeback trend analysis showed consumer-disputed-transaction volume up 9% "
         "QoQ, with an outsized concentration in digital-goods MCCs. Suspected driver "
         "is friendly fraud post-delivery. Working with issuer partners to refine "
         "dispute-handling guidance.",
         impact_desc=(
             "Recommend the AERA reference the friendly-fraud pattern as a consumer-"
             "disputes driver; current dispute-handling controls should be reassessed "
             "for effectiveness against this specific vector."))

    # -------------------------------------------------------------------
    # Scenario 4 — AE-4 with instances
    # -------------------------------------------------------------------
    _add("AE-4", "BMA-INST-008", "BMA-ACT-006",
         "Digital Channel Incident Monitoring",
         "2025-08-31", "Yes", "CASE-BMA-007",
         "Reviewed digital-channel incident log for August. Identified a 3-hour login "
         "outage on the consumer banking app caused by a failed credential-service "
         "deployment. Customer impact estimated at ~180K affected sessions; no data "
         "loss. Incident post-mortem referenced CASE-BMA-007 for action tracking.",
         impact_desc=(
             "Recommend elevating the change-management residual-risk rating for the "
             "consumer banking app; the deployment-driven outage points to gaps in "
             "pre-release validation controls that the AERA should reflect."))

    _add("AE-4", "BMA-INST-009", "BMA-ACT-007",
         "Mobile App Fraud Pattern Review",
         "2026-02-28", "Yes", "CASE-BMA-008; CASE-BMA-009",
         "Mobile fraud review identified two emerging patterns: (1) device-spoofing "
         "attempts targeting the biometric auth flow, and (2) social-engineering "
         "vectors where customers were coaxed into approving push notifications. "
         "Product security engaged; detection-rule updates and customer-education "
         "messaging prioritized.",
         impact_desc=(
             "Recommend the AERA for this entity name mobile-channel fraud as a "
             "distinct exposure; authentication-bypass and social-engineering vectors "
             "are not adequately captured by the current inherent-risk rationale."))

    # -------------------------------------------------------------------
    # Scenario 5 — AE-5 with instances
    # -------------------------------------------------------------------
    _add("AE-5", "BMA-INST-010", "BMA-ACT-008",
         "New Market Regulatory Change Tracking",
         "2025-09-30", "Yes", "CASE-BMA-010",
         "Tracked regulatory developments in three target markets (Brazil, UAE, India). "
         "Key changes include revised consumer-protection disclosures in Brazil taking "
         "effect Q1, new data-residency requirements in UAE, and updated KYC thresholds "
         "in India. Product and Compliance aligning on implementation plans.",
         impact_desc=(
             "Recommend the AERA reflect pending regulatory changes in Brazil, UAE, "
             "and India as near-term compliance drivers; the data-residency rule in "
             "particular raises the inherent profile for data and privacy risk."))

    _add("AE-5", "BMA-INST-011", "BMA-ACT-008",
         "New Market Regulatory Change Tracking",
         "2026-01-31", "No", "",
         "Activity did not occur — lead analyst transitioned teams and backup "
         "coverage not yet trained on the new-markets regulatory scope. Rescheduled.")

    _add("AE-5", "BMA-INST-012", "BMA-ACT-009",
         "Cross-Border Partner Health Check",
         "2025-12-15", "Yes", "CASE-BMA-011",
         "Reviewed financial health of three cross-border issuing partners. Two "
         "partners meet all covenants; one partner in LATAM showing deteriorating "
         "capital ratios flagged for enhanced diligence. Contingency planning discussion "
         "initiated for the affected portfolio.",
         impact_desc=(
             "Recommend the AERA elevate third-party credit risk for the LATAM issuing "
             "relationship; partner deterioration is a named exposure that the current "
             "inherent-risk rationale does not capture."))

    _add("AE-5", "BMA-INST-013", "BMA-ACT-010",
         "Local Licensing Compliance Review",
         "2026-03-15", "Yes", "CASE-BMA-012",
         "Confirmed active licensing status across all in-scope markets. Identified a "
         "renewal gap in one EMEA jurisdiction where the local money-services license "
         "is due for renewal within 60 days; compliance has engaged outside counsel to "
         "ensure no lapse.",
         impact_desc=(
             "Recommend the AERA note license-renewal dependency in the EMEA "
             "jurisdiction as a specific regulatory-compliance exposure; control "
             "assessment should reference the outside-counsel contingency."))

    # -------------------------------------------------------------------
    # Scenario 6 — AE-6 with single instance
    # -------------------------------------------------------------------
    _add("AE-6", "BMA-INST-014", "BMA-ACT-011",
         "Enterprise Risk Appetite Drift Monitoring",
         "2025-10-31", "Yes", "CASE-BMA-013",
         "Quarterly risk-appetite drift review noted two early-warning indicators: "
         "operational-loss trend above appetite threshold (driven by a single large "
         "ORE) and credit concentration moving toward the upper band in small-business "
         "lending. Both items escalated to the ERC for visibility.",
         impact_desc=(
             "Recommend the AERA reflect the small-business lending concentration "
             "drift as a directional credit-risk driver; the operational-loss trend "
             "should be addressed in the control-effectiveness narrative."))

    # -------------------------------------------------------------------
    # Scenario 7 — Blank AE rows (untagged activities)
    # -------------------------------------------------------------------
    _add("", "BMA-INST-015", "BMA-ACT-012",
         "Untagged Compliance Monitoring Activity",
         "2025-11-15", "Yes", "CASE-BMA-014",
         "General compliance monitoring scan across enterprise policies. Identified "
         "two minor policy-attestation gaps in non-core business units, tracked "
         "separately. No issues requiring AE-level attention.",
         impact_desc=(
             "No AERA change recommended — policy-attestation gaps are administrative "
             "and tracked through the standard remediation process; no inherent or "
             "control-rating adjustment needed."))

    _add("", "BMA-INST-016", "BMA-ACT-013",
         "Untagged Operational Resilience Check",
         "2026-02-15", "No", "",
         "Activity did not occur — owning team still in restructuring following recent "
         "reorg. To be reassigned and rescheduled.")

    _add("", "BMA-INST-017", "BMA-ACT-014",
         "Untagged Data Quality Review",
         "2026-01-20", "Yes", "CASE-BMA-015",
         "Enterprise-wide data-quality review flagged a recurring issue with customer "
         "address standardization in the consolidated warehouse. Root-cause traced to "
         "an upstream ETL change. Data engineering remediating.",
         impact_desc=(
             "Recommend the consuming AEs' AERAs reflect data-quality dependency on "
             "the consolidated warehouse; the ETL-driven standardization gap is a "
             "directional driver of data-risk inherent rating until remediated."))

    # -------------------------------------------------------------------
    # Scenario 8 — Rows with dates BEFORE July 2025 (should be filtered)
    # -------------------------------------------------------------------
    _add("AE-1", "BMA-INST-018", "BMA-ACT-001",
         "Monthly Transaction Volume Review",
         "2025-05-15", "Yes", "CASE-BMA-016",
         "Pre-period activity. Routine monthly volume review completed with no anomalies "
         "outside threshold.",
         impact_desc=(
             "No AERA change recommended — pre-period activity with no findings; "
             "included for completeness but should be filtered during ingestion."))

    _add("AE-3", "BMA-INST-019", "BMA-ACT-004",
         "Merchant Risk Tier Reassessment",
         "2025-06-30", "Yes", "CASE-BMA-017",
         "Pre-period activity. Tier reassessment completed; no tier changes required.",
         impact_desc=(
             "No AERA change recommended — pre-period activity with no tier "
             "movement; filtered during ingestion and out of scope for this cycle."))

    # -------------------------------------------------------------------
    # Additional rows — more variety in dates and AEs
    # -------------------------------------------------------------------
    _add("AE-2", "BMA-INST-020", "BMA-ACT-003",
         "Interest Rate Exposure Monitoring",
         "2026-02-28", "Yes", "CASE-BMA-018",
         "Follow-up to the Q4 DV01 tightening. Portfolio rebalanced toward shorter "
         "duration; exposure back within the middle tolerance band. No further action "
         "needed this cycle.",
         impact_desc=(
             "No AERA change recommended — the earlier DV01 concern has resolved and "
             "the control response (rebalance) worked as intended; existing ratings "
             "remain directionally correct."))

    _add("AE-4", "BMA-INST-021", "BMA-ACT-015",
         "API Gateway Security Assessment",
         "2025-07-15", "Yes", "CASE-BMA-019",
         "Quarterly assessment of the external API gateway identified one deprecated "
         "authentication method still enabled on two partner integrations. Cyber raised "
         "CASE-BMA-019 to coordinate migration to OAuth 2.0 with PKCE by year-end.",
         impact_desc=(
             "Recommend the AERA reference the deprecated-auth exposure on partner "
             "integrations as a named cyber driver until the OAuth 2.0 migration "
             "completes; control-effectiveness narrative should track the migration."))

    _add("AE-6", "BMA-INST-022", "BMA-ACT-016",
         "Risk Report Data Integrity Validation",
         "2026-03-31", "No", "",
         "Activity did not occur — source systems were in scheduled maintenance during "
         "the planned review window. Rescheduled for next quarter.")

    _add("AE-1", "BMA-INST-023", "BMA-ACT-002",
         "Quarterly Fraud Indicator Assessment",
         "2026-01-01", "Yes", "CASE-BMA-020",
         "Q1 fraud indicator review found continued elevation in account-takeover "
         "attempts, partially offset by the new step-up auth controls. One new pattern "
         "identified involving SIM-swap-enabled porting attacks; detection rules are "
         "being tuned.",
         impact_desc=(
             "Recommend the AERA retain elevated fraud inherent rating and add "
             "SIM-swap porting as a named vector; control assessment can reference "
             "the partial offset from step-up auth as a mitigating factor."))

    # -------------------------------------------------------------------
    # AE-1 Third Party showcase — critical vendor monitoring activity
    # -------------------------------------------------------------------
    _add("AE-1", "BMA-INST-050", "BMA-ACT-TP01",
         "Critical Third-Party Vendor Monitoring - North America Cards",
         "2026-02-15", "Yes", "CASE-BMA-TP01",
         "Quarterly monitoring review identified that two tier-1 payment processing "
         "vendors are operating outside documented SLA thresholds. Third-party risk "
         "team flagged both for enhanced oversight. Remediation plans require "
         "executive sponsor review. Fourth-party dependencies for one vendor remain "
         "uncatalogued, increasing concentration risk exposure.",
         impact_desc=(
             "Recommend the AERA elevate third-party inherent risk for the cards "
             "portfolio; vendor SLA breaches and uncatalogued fourth-party exposure "
             "are not captured by the current rationale. Control assessment should "
             "reference the pending remediation plan and the enhanced oversight "
             "cadence initiated by the third-party risk team."))

    _add("AE-3", "BMA-INST-024", "BMA-ACT-005",
         "Chargeback Rate Trend Analysis",
         "2026-03-15", "Yes", "CASE-BMA-021; CASE-BMA-022",
         "Chargeback analysis showed the digital-goods friendly-fraud pattern from Q4 "
         "has plateaued. A new concern emerged around a specific high-volume travel "
         "merchant whose dispute rate spiked 40% MoM following a service-delivery "
         "disruption. Merchant outreach initiated; CASE-BMA-022 tracks the "
         "relationship-management decision.",
         impact_desc=(
             "Recommend the AERA name the travel-merchant exposure as a concentration "
             "driver for merchant credit risk; control narrative should reference the "
             "pending relationship-management decision as a contingent mitigant."))

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
