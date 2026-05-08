"""Generate dummy test data for the IRM ORE evidence path.

Creates ORE_IRM_test_dummy.xlsx in data/input/ with ~10 IRM ORE rows
designed to exercise every code path in ingestion.ingest_ore_irm_source +
build_ore_irm_mapping_index + the new Source - ORE IRM Excel tab.

Coverage cells:
  ORE-IRM-001: Risk Level 2 = "Information and Cyber Security" (valid -> source path)
  ORE-IRM-002: Risk Level 2 = blank (mapper fallback path)
  ORE-IRM-003: Risk Level 2 = "Made Up Risk Category" (invalid -> WARNING + mapper fallback)
  ORE-IRM-004: Capture Status = "in progress", description fits Privacy
  ORE-IRM-005: Capture Status = "complete" (display-only, must NOT be filtered)
  ORE-IRM-006: Capture Status = "cancelled" (display-only, must NOT be filtered)
  ORE-IRM-007: Legacy Event ID = "ORE-001" (populated, links to legacy fixture)
  ORE-IRM-008: Legacy Event ID = "" (blank — most common case)
  ORE-IRM-009: Risk Level 2 = "Operational - Data" (valid via L1-prefix strip -> "Data")
  ORE-IRM-010: Long description (truncation test)

The legacy test data generator's `IRM ORE ID` column tags these to AEs.
"""

import pandas as pd
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = _PROJECT_ROOT / "data" / "input"


def generate_ore_irm_data() -> pd.DataFrame:
    """Generate ~10 synthetic IRM OREs covering source/mapper provenance, mixed
    Capture Status values, and Legacy Event ID linkage."""

    ores = [
        # --- Valid Risk Level 2 (source provenance) ---
        {
            "ORE ID": "ORE-IRM-001",
            "ORE Title": "Phishing campaign exposes employee credentials",
            "ORE Description": (
                "An external phishing campaign targeted finance employees and "
                "successfully harvested credentials for 7 mailbox accounts before "
                "being detected by the SOC. Cybersecurity controls failed to "
                "block the initial email vector."
            ),
            "Identified By": "Cyber SOC",
            "Identified By Sub-Group": "Threat Detection",
            "Capture Status": "In Progress",
            "ORE Root Cause": "Email gateway filter not catching new domain spoof",
            "Remediation ID": "REM-IRM-001",
            "Legacy Event ID": "",
            "Root Cause Description": "Domain spoof bypassed SPF/DKIM check",
            "Root Cause Level 1": "Technology",
            "Root Cause Level 2": "Email Security",
            "Risk Level 2": "Information and Cyber Security",
            "Risk Level 4": "Phishing",
        },

        # --- Blank Risk Level 2 (mapper fallback) ---
        {
            "ORE ID": "ORE-IRM-002",
            "ORE Title": "Wire transfer reconciliation delay",
            "ORE Description": (
                "Daily wire transfer reconciliation was delayed by 36 hours due "
                "to a settlement file format change from a counterparty bank. "
                "Process execution control failed to detect the format mismatch "
                "earlier in the workflow."
            ),
            "Identified By": "Operations Team",
            "Identified By Sub-Group": "Wire Operations",
            "Capture Status": "In Progress",
            "ORE Root Cause": "Untested change to incoming file format",
            "Remediation ID": "",
            "Legacy Event ID": "",
            "Root Cause Description": "File format from counterparty changed",
            "Root Cause Level 1": "Process",
            "Root Cause Level 2": "Reconciliation",
            "Risk Level 2": "",
            "Risk Level 4": "",
        },

        # --- Invalid Risk Level 2 (WARNING + mapper fallback) ---
        {
            "ORE ID": "ORE-IRM-003",
            "ORE Title": "Vendor SLA breach in onboarding workflow",
            "ORE Description": (
                "A critical KYC vendor missed contractual SLAs for three "
                "consecutive weeks, causing onboarding queue buildup. Third "
                "party risk team had not escalated through governance channels."
            ),
            "Identified By": "Vendor Mgmt",
            "Identified By Sub-Group": "TPRM",
            "Capture Status": "In Progress",
            "ORE Root Cause": "Vendor capacity constraints",
            "Remediation ID": "",
            "Legacy Event ID": "",
            "Root Cause Description": "Vendor capacity",
            "Root Cause Level 1": "Vendor",
            "Root Cause Level 2": "Performance",
            # Intentionally invalid — does not normalize to a taxonomy L2.
            "Risk Level 2": "Made Up Risk Category",
            "Risk Level 4": "",
        },

        # --- Privacy event, in progress ---
        {
            "ORE ID": "ORE-IRM-004",
            "ORE Title": "Customer PII inadvertently emailed to wrong recipient",
            "ORE Description": (
                "A customer service representative replied-all to an email "
                "containing 12 customer PII records, exposing them to other "
                "customers on the thread. Privacy and data protection controls "
                "did not flag the outbound message."
            ),
            "Identified By": "Customer Service",
            "Identified By Sub-Group": "Tier 1 Support",
            "Capture Status": "In Progress",
            "ORE Root Cause": "Reply-all on customer thread",
            "Remediation ID": "REM-IRM-004",
            "Legacy Event ID": "",
            "Root Cause Description": "Email habits",
            "Root Cause Level 1": "Human",
            "Root Cause Level 2": "Process Adherence",
            "Risk Level 2": "Privacy",
            "Risk Level 4": "Personal Data Disclosure",
        },

        # --- Capture Status = complete (must NOT be filtered out) ---
        {
            "ORE ID": "ORE-IRM-005",
            "ORE Title": "Trade settlement processing error",
            "ORE Description": (
                "A trade settlement system change introduced a bug that delayed "
                "settlement on 18 trades. Processing execution issue resolved "
                "after rollback."
            ),
            "Identified By": "Operations",
            "Identified By Sub-Group": "Settlement",
            "Capture Status": "Complete",
            "ORE Root Cause": "Untested code change",
            "Remediation ID": "REM-IRM-005",
            "Legacy Event ID": "",
            "Root Cause Description": "Change management gap",
            "Root Cause Level 1": "Process",
            "Root Cause Level 2": "Change Management",
            "Risk Level 2": "Processing, Execution and Change",
            "Risk Level 4": "Settlement Failure",
        },

        # --- Capture Status = cancelled (must NOT be filtered out) ---
        {
            "ORE ID": "ORE-IRM-006",
            "ORE Title": "Suspected fraud transaction (ultimately legitimate)",
            "ORE Description": (
                "A flagged transaction suspected to be account takeover fraud "
                "was investigated and confirmed legitimate. External fraud "
                "monitoring alert resolved without further action."
            ),
            "Identified By": "Fraud Ops",
            "Identified By Sub-Group": "Cardmember Fraud",
            "Capture Status": "Cancelled",
            "ORE Root Cause": "False positive",
            "Remediation ID": "",
            "Legacy Event ID": "",
            "Root Cause Description": "Genuine cardmember activity",
            "Root Cause Level 1": "External",
            "Root Cause Level 2": "Cardmember Behavior",
            "Risk Level 2": "External Fraud - First Party",
            "Risk Level 4": "",
        },

        # --- Legacy Event ID populated (links to ORE-001 in legacy fixture) ---
        {
            "ORE ID": "ORE-IRM-007",
            "ORE Title": "Cyber incident — re-tagged from legacy ORE",
            "ORE Description": (
                "This IRM ORE represents the same underlying event captured in "
                "legacy ORE-001. The Legacy Event ID column carries the prior "
                "EV ID so reviewers can trace continuity."
            ),
            "Identified By": "Cyber SOC",
            "Identified By Sub-Group": "Incident Response",
            "Capture Status": "In Progress",
            "ORE Root Cause": "VPN MFA gap (as in ORE-001)",
            "Remediation ID": "REM-IRM-007",
            "Legacy Event ID": "ORE-001",
            "Root Cause Description": "Lack of MFA on VPN",
            "Root Cause Level 1": "Technology",
            "Root Cause Level 2": "Identity & Access",
            "Risk Level 2": "Information and Cyber Security",
            "Risk Level 4": "Account Compromise",
        },

        # --- Blank Legacy Event ID (most common) ---
        {
            "ORE ID": "ORE-IRM-008",
            "ORE Title": "Model performance drift in credit scoring",
            "ORE Description": (
                "Model risk monitoring detected performance drift in a credit "
                "scoring model that exceeded the validation tolerance band. "
                "Model governance review initiated."
            ),
            "Identified By": "Model Risk Mgmt",
            "Identified By Sub-Group": "Validation",
            "Capture Status": "In Progress",
            "ORE Root Cause": "Population drift post-pandemic",
            "Remediation ID": "",
            "Legacy Event ID": "",
            "Root Cause Description": "Drift",
            "Root Cause Level 1": "Model",
            "Root Cause Level 2": "Performance Monitoring",
            "Risk Level 2": "Model",
            "Risk Level 4": "",
        },

        # --- Risk Level 2 with L1 prefix (valid via prefix strip) ---
        {
            "ORE ID": "ORE-IRM-009",
            "ORE Title": "Customer data quality issue in CRM migration",
            "ORE Description": (
                "Migration to a new CRM resulted in 4,200 customer records with "
                "incorrect address fields. Data governance procedures missed "
                "the field-mapping discrepancy in pre-cutover testing."
            ),
            "Identified By": "Data Governance",
            "Identified By Sub-Group": "Data Quality",
            "Capture Status": "In Progress",
            "ORE Root Cause": "Field mapping not validated",
            "Remediation ID": "REM-IRM-009",
            "Legacy Event ID": "",
            "Root Cause Description": "Field mapping",
            "Root Cause Level 1": "Data",
            "Root Cause Level 2": "Migration",
            # Should normalize to "Data" via L1-prefix strip in normalize_l2_name.
            "Risk Level 2": "Operational - Data",
            "Risk Level 4": "",
        },

        # --- Long description (truncation test) ---
        {
            "ORE ID": "ORE-IRM-010",
            "ORE Title": "Multi-factor operational event with extended detail",
            "ORE Description": (
                "This IRM ORE involves a complex chain of contributing factors. " * 30 +
                "Root cause analysis identified processing breakdowns, technology "
                "infrastructure issues, and human error as joint contributors."
            ),
            "Identified By": "Operational Risk",
            "Identified By Sub-Group": "Investigations",
            "Capture Status": "In Progress",
            "ORE Root Cause": "Multiple",
            "Remediation ID": "",
            "Legacy Event ID": "",
            "Root Cause Description": "See investigation report",
            "Root Cause Level 1": "Process",
            "Root Cause Level 2": "Multiple",
            "Risk Level 2": "Processing, Execution and Change",
            "Risk Level 4": "",
        },
    ]

    return pd.DataFrame(ores)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = generate_ore_irm_data()
    out_path = OUTPUT_DIR / "ORE_IRM_test_dummy.xlsx"
    df.to_excel(out_path, index=False)
    print(f"Created: {out_path}")
    print(f"  Total IRM ORE rows: {len(df)}")
    print()
    print("Expected provenance breakdown (after ingest_ore_irm_source):")
    print("  source: 5 (ORE-IRM-001, 004, 005, 006, 007, 008, 009)")
    print("    - of which one (ORE-IRM-009) normalizes via L1-prefix strip")
    print("  mapper: 2 blank (ORE-IRM-002, 010 - if RL2 set kept it as RL2)")
    print("  invalid: 1 (ORE-IRM-003 - WARNING expected)")
    print()
    print("Capture Status mix: In Progress / Complete / Cancelled (no filter applied).")


if __name__ == "__main__":
    main()
