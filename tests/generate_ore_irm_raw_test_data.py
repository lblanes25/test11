"""Generate a STACKED raw IRM ORE export fixture for the consolidation pre-step.

Creates IRM_ORE_raw_test_dummy.csv in data/input/ — a denormalized export
with multiple rows per ORE ID (one row per Cause / Risk / Impact child, the
other two sections blank). Exercises consolidate_ore_irm.py + the consolidated
impact-closure wiring in ingestion._derive_irm_ore_status.

Uses the exact 22-column A..V header set from the real export. Deterministic
(no random). Crafted OREs:

  ORE-1135446: 1 cause, 1 risk, 53 Completed impacts (=> Closed). Material.
  ORE-2000001: causes + risks + some In-Progress impacts (=> Open). Material.
  ORE-2000002: impacts all Not Needed / Cancelled (=> Closed). Material.
  ORE-2000003: impacts include one blank status (=> Open). Material.
  ORE-2000004: base-ORE-only, no child rows (=> Closed=No). Material.
  ORE-2000005: Below Threshold category (non-Material; In-Progress phases => Open).
  ORE-2000006: duplicate-looking impact rows, identical status (counting test). Material.
  ORE-2000007: Capture cancelled, no child rows (=> Closed via cancelled short-circuit). Material.
"""

import csv
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = _PROJECT_ROOT / "data" / "input"

HEADERS = [
    "ORE ID", "ORE Title", "ORE Rating", "ORE Description",
    "Identified By", "Identified By Sub-Group", "Capture Status", "ORE Root Cause",
    "Remediation ID", "Legacy Event ID", "Risk Pillar", "RCA Status",
    "Stop ongoing impact Status", "ORE Category", "Cause ID", "Root Cause Description",
    "Root Cause Level 1", "Root Cause Level 2", "Risk Level 2", "Risk Level 4",
    "Impact ID", "Impact Assessment Status",
]

# ORE-level values repeated identically across every row of an ORE (A..N).
_ORE_LEVEL = {
    "ORE-1135446": {
        "ORE Title": "Settlement reconciliation control failure",
        "ORE Rating": "High",
        "ORE Description": "Repeated settlement breaks across 53 impacted accounts.",
        "Identified By": "Operations", "Identified By Sub-Group": "Settlement",
        "Capture Status": "Completed", "ORE Root Cause": "Manual reconciliation gap",
        "Remediation ID": "REM-1135446", "Legacy Event ID": "",
        "Risk Pillar": "Operational", "RCA Status": "Completed",
        "Stop ongoing impact Status": "Completed", "ORE Category": "Material ORE",
    },
    "ORE-2000001": {
        "ORE Title": "Cyber intrusion with active remediation",
        "ORE Rating": "High",
        "ORE Description": "Credential compromise with remediation in flight.",
        "Identified By": "Cyber SOC", "Identified By Sub-Group": "IR",
        "Capture Status": "Completed", "ORE Root Cause": "MFA gap",
        "Remediation ID": "REM-2000001", "Legacy Event ID": "",
        "Risk Pillar": "Technology", "RCA Status": "Completed",
        "Stop ongoing impact Status": "Completed", "ORE Category": "Material ORE",
    },
    "ORE-2000002": {
        "ORE Title": "Investigated event, impacts not pursued",
        "ORE Rating": "Medium",
        "ORE Description": "Impacts triaged to Not Needed / Cancelled.",
        "Identified By": "Op Risk", "Identified By Sub-Group": "Investigations",
        "Capture Status": "Completed", "ORE Root Cause": "False alarm",
        "Remediation ID": "", "Legacy Event ID": "",
        "Risk Pillar": "Operational", "RCA Status": "Completed",
        "Stop ongoing impact Status": "Completed", "ORE Category": "Material ORE",
    },
    "ORE-2000003": {
        "ORE Title": "Event with an unassessed impact",
        "ORE Rating": "Medium",
        "ORE Description": "One impact row still has a blank assessment status.",
        "Identified By": "Op Risk", "Identified By Sub-Group": "Investigations",
        "Capture Status": "Completed", "ORE Root Cause": "Pending assessment",
        "Remediation ID": "", "Legacy Event ID": "",
        "Risk Pillar": "Operational", "RCA Status": "Completed",
        "Stop ongoing impact Status": "Completed", "ORE Category": "Material ORE",
    },
    "ORE-2000004": {
        "ORE Title": "Base ORE with no child sections",
        "ORE Rating": "Low",
        "ORE Description": "Captured ORE with no cause/risk/impact rows yet.",
        "Identified By": "Op Risk", "Identified By Sub-Group": "Intake",
        "Capture Status": "Completed", "ORE Root Cause": "",
        "Remediation ID": "", "Legacy Event ID": "",
        "Risk Pillar": "Operational", "RCA Status": "Completed",
        "Stop ongoing impact Status": "Completed", "ORE Category": "Material ORE",
    },
    "ORE-2000005": {
        "ORE Title": "Non-material event",
        "ORE Rating": "Low",
        "ORE Description": "Below materiality threshold; Non-Material flag, In-Progress phases => Open.",
        "Identified By": "Op Risk", "Identified By Sub-Group": "Intake",
        "Capture Status": "In-Progress", "ORE Root Cause": "Minor",
        "Remediation ID": "", "Legacy Event ID": "",
        "Risk Pillar": "Operational", "RCA Status": "In-Progress",
        "Stop ongoing impact Status": "In-Progress", "ORE Category": "Below Threshold",
    },
    "ORE-2000006": {
        "ORE Title": "Event with duplicate-looking impact rows",
        "ORE Rating": "Medium",
        "ORE Description": "Multiple impact rows share an identical Completed status.",
        "Identified By": "Op Risk", "Identified By Sub-Group": "Investigations",
        "Capture Status": "Completed", "ORE Root Cause": "Repeat pattern",
        "Remediation ID": "", "Legacy Event ID": "",
        "Risk Pillar": "Operational", "RCA Status": "Completed",
        "Stop ongoing impact Status": "Completed", "ORE Category": "Material ORE",
    },
    "ORE-2000007": {
        "ORE Title": "Cancelled event",
        "ORE Rating": "Medium",
        "ORE Description": "Capture cancelled; impacts irrelevant.",
        "Identified By": "Op Risk", "Identified By Sub-Group": "Intake",
        "Capture Status": "Cancelled", "ORE Root Cause": "Withdrawn",
        "Remediation ID": "", "Legacy Event ID": "",
        "Risk Pillar": "Operational", "RCA Status": "Cancelled",
        "Stop ongoing impact Status": "Cancelled", "ORE Category": "Material ORE",
    },
}

# Cause / Risk / Impact section keys (the only columns a child row populates).
_CAUSE_COLS = ["Cause ID", "Root Cause Description", "Root Cause Level 1", "Root Cause Level 2"]
_RISK_COLS = ["Risk Level 2", "Risk Level 4"]
_IMPACT_COLS = ["Impact ID", "Impact Assessment Status"]


def _blank_row(ore_id: str) -> dict:
    row = {h: "" for h in HEADERS}
    row["ORE ID"] = ore_id
    for k, v in _ORE_LEVEL[ore_id].items():
        row[k] = v
    return row


def _cause_row(ore_id, cid, desc, l1, l2):
    r = _blank_row(ore_id)
    r["Cause ID"], r["Root Cause Description"] = cid, desc
    r["Root Cause Level 1"], r["Root Cause Level 2"] = l1, l2
    return r


def _risk_row(ore_id, rl2, rl4):
    r = _blank_row(ore_id)
    r["Risk Level 2"], r["Risk Level 4"] = rl2, rl4
    return r


def _impact_row(ore_id, iid, status):
    r = _blank_row(ore_id)
    r["Impact ID"], r["Impact Assessment Status"] = iid, status
    return r


def generate_rows() -> list[dict]:
    rows: list[dict] = []

    # ORE-1135446: 1 cause, 1 risk, 53 Completed impacts => Closed.
    rows.append(_cause_row("ORE-1135446", "C-1", "Manual recon gap", "Process", "Reconciliation"))
    rows.append(_risk_row("ORE-1135446", "Processing, Execution and Change", "Settlement Failure"))
    for i in range(1, 54):
        rows.append(_impact_row("ORE-1135446", f"IMP-{i:04d}", "Completed"))

    # ORE-2000001: 2 causes, 2 risks, mixed impacts incl In-Progress => Open.
    rows.append(_cause_row("ORE-2000001", "C-10", "MFA gap on VPN", "Technology", "Identity & Access"))
    rows.append(_cause_row("ORE-2000001", "C-11", "Delayed detection", "Process", "Monitoring"))
    rows.append(_risk_row("ORE-2000001", "Information and Cyber Security", "Account Compromise"))
    rows.append(_risk_row("ORE-2000001", "Information and Cyber Security", "Data Exfiltration"))
    rows.append(_impact_row("ORE-2000001", "IMP-A1", "Completed"))
    rows.append(_impact_row("ORE-2000001", "IMP-A2", "In-Progress"))
    rows.append(_impact_row("ORE-2000001", "IMP-A3", "Completed"))

    # ORE-2000002: impacts all Not Needed / Cancelled => Closed.
    rows.append(_cause_row("ORE-2000002", "C-20", "False alarm", "External", "Noise"))
    rows.append(_risk_row("ORE-2000002", "External Fraud - First Party", ""))
    rows.append(_impact_row("ORE-2000002", "IMP-B1", "Not Needed"))
    rows.append(_impact_row("ORE-2000002", "IMP-B2", "Cancelled"))
    rows.append(_impact_row("ORE-2000002", "IMP-B3", "Not Needed"))

    # ORE-2000003: one blank impact status among Completed => Open.
    rows.append(_cause_row("ORE-2000003", "C-30", "Pending review", "Process", "Assessment"))
    rows.append(_risk_row("ORE-2000003", "Processing, Execution and Change", ""))
    rows.append(_impact_row("ORE-2000003", "IMP-C1", "Completed"))
    rows.append(_impact_row("ORE-2000003", "IMP-C2", ""))

    # ORE-2000004: base ORE only, no child rows => Closed=No.
    rows.append(_blank_row("ORE-2000004"))

    # ORE-2000005: Below Threshold (Non-Material), In-Progress phases + one impact => Open.
    rows.append(_cause_row("ORE-2000005", "C-50", "Minor", "Process", "Minor"))
    rows.append(_impact_row("ORE-2000005", "IMP-D1", "Completed"))

    # ORE-2000006: duplicate-looking impact rows, identical Completed status.
    rows.append(_risk_row("ORE-2000006", "Processing, Execution and Change", ""))
    rows.append(_impact_row("ORE-2000006", "IMP-E1", "Completed"))
    rows.append(_impact_row("ORE-2000006", "IMP-E1", "Completed"))
    rows.append(_impact_row("ORE-2000006", "IMP-E2", "Completed"))

    # ORE-2000007: capture cancelled, no child rows => Closed (cancelled short-circuit).
    rows.append(_blank_row("ORE-2000007"))

    return rows


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = generate_rows()
    out_path = OUTPUT_DIR / "IRM_ORE_raw_test_dummy.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)
    n_ores = len({r["ORE ID"] for r in rows})
    print(f"Created: {out_path}")
    print(f"  Raw rows: {len(rows)}  Unique OREs: {n_ores}")
    print("  Expected Impact Assessment Closed:")
    print("    ORE-1135446 => Yes (53 Completed)")
    print("    ORE-2000001 => No  (In-Progress present)")
    print("    ORE-2000002 => Yes (Not Needed / Cancelled)")
    print("    ORE-2000003 => No  (blank impact status)")
    print("    ORE-2000004 => No  (no impact rows)")
    print("    ORE-2000006 => Yes (all Completed)")
    print("  Expected ORE Status:")
    print("    ORE-2000007 => Closed (cancelled, no impacts)")


if __name__ == "__main__":
    main()
