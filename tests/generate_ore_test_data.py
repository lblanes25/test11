"""Generate dummy test data for the ORE-to-L2 Risk Mapper (ore_mapper.py).

Creates two files in data/input/:

ORE FILE (ORE_test_dummy.xlsx):
  20 synthetic Operational Risk Events designed to exercise every code path:

  ORE-001: Clear cybersecurity incident — should map confidently to InfoSec
  ORE-002: Clear fraud event — should map confidently to Fraud
  ORE-003: Ambiguous between Data and Privacy — tight margin expected
  ORE-004: Clear third-party vendor failure — should map to Third Party
  ORE-005: Clear regulatory fine — should map to Prudential Compliance or Conduct
  ORE-006: Ambiguous between Technology and InfoSec — tight margin expected
  ORE-007: Clear model risk event — should map to Model
  ORE-008: Processing error — should map to Proc/Exec
  ORE-009: Clear human capital event — should map to Human Capital
  ORE-010: Vague/generic text — may produce No Valid Match or very low scores
  ORE-011: Financial crimes / AML — should map to Financial Crimes
  ORE-012: Clear privacy event — should map to Privacy
  ORE-013: Country risk — should map to Country
  ORE-014: Reputational event — should map to Reputational
  ORE-015: Consumer product event — should map to Customer Protection or Consumer/SMB
  ORE-016: Empty description, title only — tests sparse input handling
  ORE-017: Very long description — tests truncation in output
  ORE-018: Ambiguous between Conduct and Legal — tight margin expected
  ORE-019: Clear FX event — should map to FX/Price
  ORE-020: Liquidity event — should map to Funding/Liquidity

  Edge cases:
  ORE-900: Blank title AND description — should be dropped in load_ore_data
  ORE-901: Blank Event ID — should be dropped
  (blank): No entity ID — should be dropped if ORE_ENTITY_COL filtering is active

L2 TAXONOMY FILE:
  Already exists at data/input/L2_Risk_Taxonomy.xlsx — not recreated here.
  The ORE texts are written to produce realistic similarity scores against
  the real L2 definitions.

Usage:
    python tests/generate_ore_test_data.py
"""

import pandas as pd
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = _PROJECT_ROOT / "data" / "input"


def generate_ore_data() -> pd.DataFrame:
    """Generate 20+ synthetic OREs covering confident, ambiguous, and edge cases."""

    ores = [
        # --- Confident matches ---
        {
            "Event ID": "ORE-001",
            "Audit Entity (Operational Risk Events)": "AE-1",
            "Event Title": "Unauthorized access to customer database via compromised credentials",
            "Event Description / Summary": (
                "A threat actor gained access to internal systems through a phishing attack "
                "that compromised an employee's VPN credentials. The attacker exfiltrated "
                "approximately 50,000 customer records including names, account numbers, and "
                "email addresses before the intrusion was detected by the SIEM. Incident response "
                "was initiated within 4 hours. Root cause: lack of multi-factor authentication "
                "on the VPN gateway. Cybersecurity controls were insufficient to prevent lateral "
                "movement once inside the network perimeter."
            ),
            "Final Event Classification": "Class A",
            "Event Status": "Confirmed",
        },
        {
            "Event ID": "ORE-002",
            "Audit Entity (Operational Risk Events)": "AE-1",
            "Event Title": "Internal fraud scheme in wire transfer operations",
            "Event Description / Summary": (
                "An operations manager in the wire transfer department created fictitious vendor "
                "accounts and initiated 37 fraudulent wire transfers totaling $2.1M over 18 months. "
                "The scheme was detected during a routine reconciliation audit. Dual authorization "
                "controls were bypassed because the manager had both initiator and approver access "
                "due to a segregation of duties failure. Internal fraud investigation confirmed "
                "deliberate misappropriation of funds. Employee terminated and referred to law "
                "enforcement."
            ),
            "Final Event Classification": "Class A",
            "Event Status": "Pending Ownership",
        },
        {
            "Event ID": "ORE-004",
            "Audit Entity (Operational Risk Events)": "AE-1",
            "Event Title": "Critical vendor outage disrupts payment processing",
            "Event Description / Summary": (
                "A key third-party payment processor experienced a 14-hour outage that prevented "
                "the bank from processing approximately 200,000 customer transactions. The vendor's "
                "disaster recovery plan failed to activate properly. The bank's third party risk "
                "management program had not conducted an on-site assessment of this vendor in over "
                "24 months despite it being classified as critical. SLA breach penalties were "
                "insufficient to cover customer remediation costs. Concentration risk identified — "
                "no alternate vendor arrangement was in place."
            ),
            "Final Event Classification": "Class B",
            "Event Status": "Ready For Confirmation",
        },
        {
            "Event ID": "ORE-005",
            "Audit Entity (Operational Risk Events)": "AE-4",
            "Event Title": "Regulatory enforcement action for BSA/AML deficiencies",
            "Event Description / Summary": (
                "The OCC issued a consent order citing significant deficiencies in the bank's "
                "Bank Secrecy Act and anti-money laundering compliance program. Specific findings "
                "included inadequate suspicious activity monitoring, failure to file timely SARs, "
                "insufficient staffing in the compliance function, and lack of independent testing. "
                "Civil money penalty of $15M assessed. Remediation plan required within 90 days. "
                "Prudential regulatory compliance failures across multiple examination cycles."
            ),
            "Final Event Classification": "Class A",
            "Event Status": "Financial Checkpoint Complete",
        },
        {
            "Event ID": "ORE-007",
            "Audit Entity (Operational Risk Events)": "AE-2",
            "Event Title": "Model validation failure in credit risk scoring",
            "Event Description / Summary": (
                "Annual model validation revealed that the primary credit risk scoring model had "
                "experienced significant performance degradation. The model's Gini coefficient "
                "dropped from 0.72 to 0.51 over the past year due to population drift in the "
                "post-pandemic lending environment. Model risk management failed to detect the "
                "degradation because the ongoing monitoring thresholds were set too wide. An "
                "estimated $45M in additional credit losses are attributed to misclassified "
                "borrowers during the period of degradation."
            ),
            "Final Event Classification": "Class A",
            "Event Status": "Pending Ownership",
        },
        {
            "Event ID": "ORE-008",
            "Audit Entity (Operational Risk Events)": "AE-5",
            "Event Title": "Trade settlement failure due to system migration error",
            "Event Description / Summary": (
                "During migration to a new trade processing platform, a configuration error caused "
                "approximately 3,200 equity trades to fail settlement over a 3-day period. The "
                "processing execution failure resulted in $8M in buy-in costs and regulatory "
                "reporting of settlement failures to the SEC. Change management procedures were "
                "not followed — the migration was executed without completing the required parallel "
                "run period. Operational processing controls in the new system were not properly "
                "configured."
            ),
            "Final Event Classification": "Class B",
            "Event Status": "Ready for Closure",
        },
        {
            "Event ID": "ORE-009",
            "Audit Entity (Operational Risk Events)": "AE-6",
            "Event Title": "Mass employee misconduct in sales incentive program",
            "Event Description / Summary": (
                "Internal investigation uncovered widespread manipulation of sales metrics by "
                "retail banking staff to meet aggressive incentive targets. Approximately 150 "
                "employees across 30 branches opened unauthorized accounts or inflated transaction "
                "volumes. Root cause analysis identified unrealistic sales targets, inadequate "
                "supervision, and a compensation structure that rewarded volume over quality. "
                "Human capital risk manifested through toxic workplace culture, high turnover in "
                "compliance roles, and insufficient training on ethical sales practices."
            ),
            "Final Event Classification": "Class B",
            "Event Status": "Canceled",
        },
        {
            "Event ID": "ORE-011",
            "Audit Entity (Operational Risk Events)": "AE-4",
            "Event Title": "Sanctions screening failure allows prohibited transactions",
            "Event Description / Summary": (
                "The bank's sanctions screening system failed to flag 23 wire transfers totaling "
                "$4.7M to entities on the OFAC SDN list. The failure was caused by a data feed "
                "issue that prevented the latest sanctions list update from being loaded into the "
                "screening engine. Financial crimes compliance monitoring did not detect the gap "
                "for 11 days. OFAC self-disclosure filed. Anti-money laundering controls were "
                "also found to be deficient in the same business unit."
            ),
            "Final Event Classification": "Class A",
            "Event Status": "Pending Confirmation",
        },
        {
            "Event ID": "ORE-012",
            "Audit Entity (Operational Risk Events)": "AE-1",
            "Event Title": "Customer PII exposed through misconfigured cloud storage",
            "Event Description / Summary": (
                "A misconfigured S3 bucket containing customer personally identifiable information "
                "was publicly accessible for approximately 60 days. The exposed data included "
                "Social Security numbers, dates of birth, and financial account details for 120,000 "
                "customers. The privacy breach was discovered by a security researcher who notified "
                "the bank. Data protection controls failed because the cloud configuration was not "
                "subject to the same privacy impact assessment process as on-premises systems. "
                "Regulatory notification required under state privacy laws."
            ),
            "Final Event Classification": "Class A",
            "Event Status": "Confirmed",
        },
        {
            "Event ID": "ORE-013",
            "Audit Entity (Operational Risk Events)": "AE-2",
            "Event Title": "Emerging market exposure loss from sovereign default",
            "Event Description / Summary": (
                "The bank sustained $180M in losses on sovereign bond holdings following a "
                "country debt restructuring. Country risk limits were exceeded due to a gap "
                "in aggregation of direct exposure and indirect exposure through correspondent "
                "banking relationships. The country risk assessment framework did not adequately "
                "capture political instability indicators that preceded the default. Cross-border "
                "transfer restrictions imposed during the crisis further complicated recovery."
            ),
            "Final Event Classification": "Class A",
            "Event Status": "Re-Open Requested",
        },
        {
            "Event ID": "ORE-014",
            "Audit Entity (Operational Risk Events)": "AE-3",
            "Event Title": "Negative media coverage from discriminatory lending practices",
            "Event Description / Summary": (
                "A major newspaper published an investigation alleging systematic bias in the "
                "bank's mortgage lending decisions, with statistical analysis showing significant "
                "disparities in approval rates across demographic groups. The reputational damage "
                "resulted in a 15% drop in mortgage applications over the following quarter. "
                "Multiple class-action lawsuits filed. The bank's reputation risk management "
                "framework had not identified fair lending as a material reputational risk driver."
            ),
            "Final Event Classification": "Class B",
            "Event Status": "Draft Expired",
        },
        {
            "Event ID": "ORE-015",
            "Audit Entity (Operational Risk Events)": "AE-6",
            "Event Title": "Unfair overdraft fee practices affecting consumer accounts",
            "Event Description / Summary": (
                "CFPB examination identified that the bank's overdraft program charged fees on "
                "transactions that appeared to be authorized at the time of swipe but settled "
                "into a negative balance days later. The practice disproportionately affected "
                "low-income consumers and small business checking account holders. Consumer harm "
                "estimated at $32M across 400,000 accounts. Customer protection and product "
                "compliance failures cited. Restitution required."
            ),
            "Final Event Classification": "Class B",
            "Event Status": "Confirmed",
        },
        {
            "Event ID": "ORE-019",
            "Audit Entity (Operational Risk Events)": "AE-2",
            "Event Title": "FX trading desk unauthorized position results in large loss",
            "Event Description / Summary": (
                "A senior FX trader built an unauthorized $500M position in emerging market "
                "currencies by mismarking trades and exploiting a gap in the position limit "
                "monitoring system. When the position was discovered during a routine P&L "
                "reconciliation, the rapid unwinding resulted in a $67M trading loss. FX price "
                "risk controls including position limits, independent price verification, and "
                "end-of-day reconciliation all failed to detect the unauthorized activity."
            ),
            "Final Event Classification": "Class A",
            "Event Status": "Pending Cancelation by Event Admin",
        },
        {
            "Event ID": "ORE-020",
            "Audit Entity (Operational Risk Events)": "AE-2",
            "Event Title": "Funding stress during market dislocation event",
            "Event Description / Summary": (
                "During a period of market stress, the bank experienced significant difficulty "
                "rolling over $3B in short-term wholesale funding. The liquidity coverage ratio "
                "dropped below regulatory minimums for 5 consecutive days. The bank was forced "
                "to access the Federal Reserve discount window. Funding and liquidity risk "
                "management models had not been calibrated to capture the speed of deposit "
                "outflows observed during the stress event. Contingency funding plan was "
                "inadequate."
            ),
            "Final Event Classification": "Class A",
            "Event Status": "Draft",
        },

        # --- Ambiguous cases (designed to produce tight margins) ---
        {
            "Event ID": "ORE-003",
            "Audit Entity (Operational Risk Events)": "AE-1",
            "Event Title": "Customer data mishandled during analytics project",
            "Event Description / Summary": (
                "A data analytics team used production customer data in a development environment "
                "without proper anonymization. The data included transaction histories and account "
                "balances for 50,000 customers. While no external breach occurred, the incident "
                "violated both data governance policies and privacy regulations. The data was "
                "accessed by 12 contractors who had not completed privacy training. Unclear whether "
                "this is primarily a data management failure or a privacy compliance violation."
            ),
            "Final Event Classification": "Class C",
            "Event Status": "Confirmed",
        },
        {
            "Event ID": "ORE-006",
            "Audit Entity (Operational Risk Events)": "AE-5",
            "Event Title": "Core banking system outage from failed software deployment",
            "Event Description / Summary": (
                "A software deployment to the core banking platform caused a cascading failure "
                "that took down online banking, mobile banking, and ATM services for 8 hours. "
                "The technology infrastructure failure was triggered by an incompatible database "
                "schema change. Information security monitoring was also impacted, creating a "
                "blind spot in threat detection during the outage. The incident involves both "
                "technology resilience and cyber security monitoring failures."
            ),
            "Final Event Classification": "Class A",
            "Event Status": "Closed",
        },
        {
            "Event ID": "ORE-018",
            "Audit Entity (Operational Risk Events)": "AE-3",
            "Event Title": "Employee whistleblower retaliation and improper disclosure",
            "Event Description / Summary": (
                "A compliance officer who reported concerns about suspicious trading activity "
                "was reassigned to a non-client-facing role within two weeks of filing the report. "
                "The employee's identity as a whistleblower was improperly disclosed to the "
                "business unit head. This involves both potential legal liability under "
                "whistleblower protection statutes and conduct risk from the management actions "
                "taken. Legal counsel and the conduct committee are jointly reviewing."
            ),
            "Final Event Classification": "Class B",
            "Event Status": "Pending Ownership",
        },

        # --- Edge cases ---
        {
            "Event ID": "ORE-010",
            "Audit Entity (Operational Risk Events)": "AE-7",
            "Event Title": "General operational issue",
            "Event Description / Summary": (
                "An issue occurred in the operations area. Some things went wrong and need to be "
                "fixed. The team is looking into it. More details to follow."
            ),
            "Final Event Classification": "Near Miss",
            "Event Status": "Confirmed",
        },
        {
            "Event ID": "ORE-016",
            "Audit Entity (Operational Risk Events)": "AE-8",
            "Event Title": "Unexpected loss from credit portfolio concentration",
            "Event Description / Summary": "",  # Empty description — title only
            "Final Event Classification": "Class C",
            "Event Status": "Closed",
        },
        {
            "Event ID": "ORE-017",
            "Audit Entity (Operational Risk Events)": "AE-9",
            "Event Title": "Complex multi-factor operational risk event",
            "Event Description / Summary": (
                "This event involves multiple intersecting risk factors. " * 30 +
                "The root cause analysis identified technology failures, process breakdowns, "
                "and human error as contributing factors."
            ),  # Very long description — tests truncation
            "Final Event Classification": "Class C",
            "Event Status": "Ready For Confirmation",
        },

        # --- Rows that should be DROPPED by load_ore_data ---
        {
            "Event ID": "ORE-900",
            "Audit Entity (Operational Risk Events)": "AE-1",
            "Event Title": "",
            "Event Description / Summary": "",  # Blank title AND description
            "Final Event Classification": "",
            "Event Status": "",
        },
        {
            "Event ID": "",
            "Audit Entity (Operational Risk Events)": "AE-1",
            "Event Title": "Event with blank ID",
            "Event Description / Summary": "Should be dropped because Event ID is blank.",
            "Final Event Classification": "",
            "Event Status": "Confirmed",
        },
        {
            "Event ID": "ORE-902",
            "Audit Entity (Operational Risk Events)": "",  # No entity ID — should be dropped
            "Event Title": "Event with no entity",
            "Event Description / Summary": "Should be dropped because Audit Entity ID is blank.",
            "Final Event Classification": "",
            "Event Status": "Pending Confirmation",
        },
    ]

    return pd.DataFrame(ores)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    ore_df = generate_ore_data()
    ore_path = OUTPUT_DIR / "ORE_test_dummy.xlsx"
    ore_df.to_excel(ore_path, index=False)
    print(f"Created: {ore_path}")
    print(f"  Total rows: {len(ore_df)}")
    print(f"  Valid OREs (should survive filtering): {len(ore_df) - 3}")
    print(f"  Drop candidates: 3 (blank title+desc, blank ID, blank entity)")

    # Summary of expected behavior
    print("\nExpected mapping behavior:")
    print("  Confident matches: ~14 OREs (001,002,004,005,007,008,009,011,012,013,014,015,019,020)")
    print("  Ambiguous matches: ~3 OREs (003,006,018)")
    print("  Weak/no match:     ~1 ORE (010)")
    print("  Title-only:        ~1 ORE (016)")
    print("  Long description:  ~1 ORE (017)")


if __name__ == "__main__":
    main()
