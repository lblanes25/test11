"""Generate dummy SOURCE fixtures for the three-source PRSA Frankenstein build.

Replaces the older single-file generator. Writes three files into
``data/input/``:

  1. ``PRSA_IRM_Archer_test_dummy.xlsx``     -- one row per Issue (raw IRM/Archer
     extract). ``Control ID (PRSA)`` is newline-delimited; the build script will
     explode on it. Rows where ``Control ID (PRSA)`` is blank but
     ``Control ID (RCSA)`` is populated are dropped at build time (no AE
     mapping path for RCSA).

  2. ``PRSA_Controls_Map_test_dummy.xlsx``   -- one row per PRSA control.
     ``Process ID`` joins to legacy ``PRSA``; ``Control ID`` joins to the
     exploded Archer ``Control ID (PRSA)``.

  3. ``prsa_report_test_dummy.xlsx``         -- the EXPECTED Frankenstein output
     (golden file for validation-qa). Built deterministically from the two
     source files above so that ``build_prsa_frankenstein.py`` (next task) can
     be diffed against it.

The AE catalogue and per-AE PRSA tagging are reused by
``tests/generate_test_data.py`` to populate the new ``PRSA`` column on
``legacy_risk_data_*.xlsx``. ``AE_PRSA_MAP`` is exposed as a module-level
constant for that import.

Usage:
    python tests/generate_prsa_source_test_data.py
"""

from __future__ import annotations

import re

import pandas as pd
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = _PROJECT_ROOT / "data" / "input"


# ---------------------------------------------------------------------------
# AE catalogue (kept aligned with tests/generate_test_data.py:AE_CATALOG)
# ---------------------------------------------------------------------------

AE_CATALOG: dict[str, tuple[str, str, str, str]] = {
    # ae_id: (name, audit_leader, core_audit_team, audit_engagement_id)
    "AE-1":  ("North America Cards",       "Alice Johnson", "Team Alpha",   "ENG-101"),
    "AE-2":  ("Treasury Operations",        "Bob Martinez",  "Team Bravo",   "ENG-201"),
    "AE-3":  ("Global Merchant Services",   "Carol Chen",    "Team Charlie", "ENG-301"),
    "AE-4":  ("Digital Banking Platform",   "David Kim",     "Team Delta",   "ENG-401"),
    "AE-5":  ("New Markets Expansion",      "Eve Rodriguez", "Team Alpha",   "ENG-501"),
    "AE-6":  ("Enterprise Risk Services",   "Frank Patel",   "Team Bravo",   "ENG-601"),
    "AE-7":  ("Dormant Entity - Legacy",    "Grace Lee",     "Team Charlie", "ENG-701"),
    "AE-8":  ("Investment Products",        "Henry Wu",      "Team Delta",   "ENG-801"),
    "AE-9":  ("Cross-Border Operations",    "Irene Tanaka",  "Team Alpha",   "ENG-901"),
    "AE-10": ("Internal Shared Services",   "James Okafor",  "Team Charlie", "ENG-1001"),
}


# ---------------------------------------------------------------------------
# AE -> PRSA tagging (this is what goes into the new "PRSA" column on the
# legacy_risk_data file). Imported by tests/generate_test_data.py.
# ---------------------------------------------------------------------------

AE_PRSA_MAP: dict[str, list[str]] = {
    "AE-1":  ["PRSA-001", "PRSA-002", "PRSA-003", "PRSA-100"],
    "AE-2":  ["PRSA-004", "PRSA-005"],
    "AE-3":  ["PRSA-003", "PRSA-006", "PRSA-007"],
    "AE-4":  ["PRSA-009", "PRSA-010", "PRSA-011"],
    "AE-5":  ["PRSA-003", "PRSA-012", "PRSA-013"],
    "AE-6":  ["PRSA-016", "PRSA-100"],
    "AE-7":  ["PRSA-018", "PRSA-019"],   # tagged but zero failing issues
    "AE-8":  ["PRSA-020", "PRSA-021"],
    "AE-9":  ["PRSA-023", "PRSA-024"],
    "AE-10": ["PRSA-027", "PRSA-028"],
}


# ---------------------------------------------------------------------------
# Controls Map (File 3): one row per control, joins by Process ID = PRSA
# ---------------------------------------------------------------------------

# (control_id, control_title, process_id, process_title)
CONTROLS_MAP: list[tuple[str, str, str, str]] = [
    ("CTRL-001",  "KYC Document Completeness Check",      "PRSA-001", "Account Origination"),
    ("CTRL-002A", "Credit Limit Override Approval",        "PRSA-002", "Credit Limit Management"),
    ("CTRL-002B", "Batch Error Handling Control",          "PRSA-002", "Credit Limit Management"),
    ("CTRL-003",  "Merchant Sanctions Screening",          "PRSA-003", "Merchant Onboarding"),
    ("CTRL-005",  "Market Data Refresh Validation",        "PRSA-005", "Funding Allocation"),  # no failing issue
    ("CTRL-007",  "Chargeback SLA Monitoring",             "PRSA-007", "Chargeback Processing"),
    ("CTRL-009A", "Identity Verification Gate",            "PRSA-009", "Digital Account Opening"),
    ("CTRL-009B", "Real-Time Fraud Score Threshold",       "PRSA-009", "Digital Account Opening"),
    ("CTRL-009C", "Session Timeout Enforcement",           "PRSA-009", "Digital Account Opening"),
    ("CTRL-013",  "License Inventory Completeness",        "PRSA-013", "Regulatory License Management"),
    ("CTRL-016",  "Risk Data Aggregation Reconciliation",  "PRSA-016", "Enterprise Risk Reporting"),
    ("CTRL-018A", "Dormant Account Periodic Review",       "PRSA-018", "Dormant Account Oversight"),  # AE-7, no issue
    ("CTRL-020",  "Rebalancing Drift Threshold",           "PRSA-020", "Portfolio Rebalancing"),
    ("CTRL-024",  "Correspondent Bank Review Timeliness",  "PRSA-024", "Correspondent Banking Oversight"),
]


# ---------------------------------------------------------------------------
# Issues (File 2: PRSA_IRM_Archer). One row per Issue. Multi-control issues
# carry a newline-delimited Control ID (PRSA) that the build script explodes.
# ---------------------------------------------------------------------------

# Each tuple matches the column order written below.
ISSUES: list[dict] = [
    # ISS-001 -- AE-1, single control, INTERNAL, L2 populated, Open. PG-flagged
    # so the Track C2 diagnostic can exercise the `prsa-only` verdict when the
    # PG team file references this Issue ID with a blank Finding ID.
    {
        "Issue ID":             "ISS-001",
        "Issue Title":          "Incomplete KYC documentation at origination",
        "Issue Owner":          "Linda Torres",
        "Issue Status":         "Open",
        "Issue Status Rating":  "On Track",
        "Issue Impact Rating":  "Medium",
        "Issue Identifier":     "INTERNAL",
        "Control ID (PRSA)":    "CTRL-001",
        "Control ID (RCSA)":    "",
        "Issue Description": (
            "#PG Account origination process does not consistently capture all required "
            "KYC documents before account activation, leading to downstream AML gaps."
        ),
        "Root Cause Description": "Manual handoff between intake and verification teams.",
        "Root Cause Sub-Theme":   "Process Handoff",
        "Root Cause Theme":       "Process Design",
        "Risk Level 2":           "Financial Crimes",
    },

    # ISS-002 -- AE-1, MULTI-CONTROL (2 controls newline-delimited), Open
    {
        "Issue ID":             "ISS-002",
        "Issue Title":          "Credit limit override approvals not retained",
        "Issue Owner":          "Mark Davis",
        "Issue Status":         "Open",
        "Issue Status Rating":  "Behind Schedule",
        "Issue Impact Rating":  "High",
        "Issue Identifier":     "INTERNAL",
        "Control ID (PRSA)":    "CTRL-002A\nCTRL-002B",
        "Control ID (RCSA)":    "",
        "Issue Description": (
            "Manual overrides of automated credit limit decisions lack documented "
            "supervisory approval, and the nightly batch silently skips error records."
        ),
        "Root Cause Description": "Two distinct control failures within the same process.",
        "Root Cause Sub-Theme":   "Approval Documentation",
        "Root Cause Theme":       "Operating Effectiveness",
        "Risk Level 2":           "Processing, Execution and Change",
    },

    # ISS-003 -- shared PRSA-003, EXTERNAL, CLOSED (must still appear in Frankenstein)
    {
        "Issue ID":             "ISS-003",
        "Issue Title":          "Merchant onboarding lacks automated sanctions screening",
        "Issue Owner":          "Nina Gupta",
        "Issue Status":         "Closed",
        "Issue Status Rating":  "Complete",
        "Issue Impact Rating":  "Critical",
        "Issue Identifier":     "EXTERNAL",
        "Control ID (PRSA)":    "CTRL-003",
        "Control ID (RCSA)":    "",
        "Issue Description": (
            "Merchant onboarding process relied on manual sanctions list checks "
            "with no automated screening integration. Remediated and validated."
        ),
        "Root Cause Description": "No automated integration with OFAC/SDN feeds.",
        "Root Cause Sub-Theme":   "System Integration",
        "Root Cause Theme":       "Control Design",
        "Risk Level 2":           "Financial Crimes",
    },

    # ISS-004 -- AE-4, MULTI-CONTROL (3 controls), Critical, Open. PG-flagged
    # so the Track C2 diagnostic can exercise the `disagree` verdict when the
    # PG team file pairs this Issue ID with a non-AE-4 Finding ID.
    {
        "Issue ID":             "ISS-004",
        "Issue Title":          "Digital account opening bypasses identity verification",
        "Issue Owner":          "Tina Zhao",
        "Issue Status":         "Open",
        "Issue Status Rating":  "On Track",
        "Issue Impact Rating":  "Critical",
        "Issue Identifier":     "INTERNAL",
        "Control ID (PRSA)":    "CTRL-009A\nCTRL-009B\nCTRL-009C",
        "Control ID (RCSA)":    "",
        "Issue Description": (
            "#PG The digital account opening flow allows account creation before "
            "identity verification completes under timeout conditions. Identity "
            "check, fraud score, and session timeout controls all failed."
        ),
        "Root Cause Description": "Race condition between session timeout and verification callback.",
        "Root Cause Sub-Theme":   "Concurrency",
        "Root Cause Theme":       "Control Design",
        "Risk Level 2":           "Information and Cyber Security",
    },

    # ISS-005 -- RCSA-ONLY (PRSA col blank, RCSA col populated). MUST be dropped.
    {
        "Issue ID":             "ISS-005",
        "Issue Title":          "RCSA-only finding with no PRSA mapping",
        "Issue Owner":          "Paula Singh",
        "Issue Status":         "Open",
        "Issue Status Rating":  "On Track",
        "Issue Impact Rating":  "Low",
        "Issue Identifier":     "INTERNAL",
        "Control ID (PRSA)":    "",
        "Control ID (RCSA)":    "RCSA-CTRL-501",
        "Issue Description": (
            "Issue scoped only to an RCSA control. There is no AE mapping path "
            "for RCSA controls today, so this row should not reach the Frankenstein."
        ),
        "Root Cause Description": "RCSA-only scope; legacy AE mapping unavailable.",
        "Root Cause Sub-Theme":   "Scope",
        "Root Cause Theme":       "Mapping Gap",
        "Risk Level 2":           "Processing, Execution and Change",
    },

    # ISS-006 -- AE-3, BLANK Risk Level 2 (would later fall back to PRSA mapper)
    {
        "Issue ID":             "ISS-006",
        "Issue Title":          "Chargeback processing SLA breach -- systemic",
        "Issue Owner":          "Rachel Kim",
        "Issue Status":         "Open",
        "Issue Status Rating":  "Behind Schedule",
        "Issue Impact Rating":  "Medium",
        "Issue Identifier":     "INTERNAL",
        "Control ID (PRSA)":    "CTRL-007",
        "Control ID (RCSA)":    "",
        "Issue Description": (
            "Chargeback processing consistently exceeds contractual SLA timelines, "
            "resulting in regulatory exposure and merchant financial harm."
        ),
        "Root Cause Description": "Capacity constraint in dispute operations.",
        "Root Cause Sub-Theme":   "Capacity",
        "Root Cause Theme":       "Operating Effectiveness",
        "Risk Level 2":           "",   # blank -- L2 will be inferred downstream
    },

    # ISS-007 -- AE-5, EXTERNAL, Low. Root Cause fields BLANK (carry blanks through).
    {
        "Issue ID":             "ISS-007",
        "Issue Title":          "Regulatory license tracking spreadsheet not maintained",
        "Issue Owner":          "Xavier Diaz",
        "Issue Status":         "Open",
        "Issue Status Rating":  "On Track",
        "Issue Impact Rating":  "Low",
        "Issue Identifier":     "EXTERNAL",
        "Control ID (PRSA)":    "CTRL-013",
        "Control ID (RCSA)":    "",
        "Issue Description": (
            "New market regulatory license inventory maintained in a manual "
            "spreadsheet with no version control or audit trail."
        ),
        "Root Cause Description": "",
        "Root Cause Sub-Theme":   "",
        "Root Cause Theme":       "",
        "Risk Level 2":           "Prudential & bank administration compliance",
    },

    # ISS-008 -- AE-6, INTERNAL, High
    {
        "Issue ID":             "ISS-008",
        "Issue Title":          "Enterprise risk report data aggregation errors",
        "Issue Owner":          "Andrea Wolfe",
        "Issue Status":         "Pending Validation",
        "Issue Status Rating":  "On Track",
        "Issue Impact Rating":  "High",
        "Issue Identifier":     "INTERNAL",
        "Control ID (PRSA)":    "CTRL-016",
        "Control ID (RCSA)":    "",
        "Issue Description": (
            "Monthly enterprise risk report contains data aggregation errors due "
            "to inconsistent source-system extracts across business units."
        ),
        "Root Cause Description": "Source extract logic diverged across BUs over time.",
        "Root Cause Sub-Theme":   "Data Lineage",
        "Root Cause Theme":       "Data Governance",
        "Risk Level 2":           "Data",
    },

    # ISS-009 -- AE-8, INTERNAL, Medium
    {
        "Issue ID":             "ISS-009",
        "Issue Title":          "Portfolio rebalancing drift threshold too wide",
        "Issue Owner":          "Carlos Mendez",
        "Issue Status":         "Open",
        "Issue Status Rating":  "On Track",
        "Issue Impact Rating":  "Medium",
        "Issue Identifier":     "INTERNAL",
        "Control ID (PRSA)":    "CTRL-020",
        "Control ID (RCSA)":    "",
        "Issue Description": (
            "Automated portfolio rebalancing triggers only when drift exceeds 10%, "
            "well above the 5% policy threshold, due to a configuration error."
        ),
        "Root Cause Description": "Configuration drift after a prior policy change.",
        "Root Cause Sub-Theme":   "Configuration Management",
        "Root Cause Theme":       "Operating Effectiveness",
        "Risk Level 2":           "Processing, Execution and Change",
    },

    # ISS-010 -- AE-9, INTERNAL, High. PG-flagged so the Track C2 diagnostic
    # can exercise the `match` verdict: ISS-010 PRSA-route resolves to AE-9 /
    # Third Party, and Finding F-9002 also resolves to AE-9 / Third Party
    # (after L1-prefix normalization of "Operational - Third Party").
    {
        "Issue ID":             "ISS-010",
        "Issue Title":          "Correspondent bank due diligence reviews overdue",
        "Issue Owner":          "George Owens",
        "Issue Status":         "Pending Validation",
        "Issue Status Rating":  "Behind Schedule",
        "Issue Impact Rating":  "High",
        "Issue Identifier":     "INTERNAL",
        "Control ID (PRSA)":    "CTRL-024",
        "Control ID (RCSA)":    "",
        "Issue Description": (
            "#PG Annual due diligence reviews for 4 of 12 correspondent banking "
            "relationships are more than 90 days overdue."
        ),
        "Root Cause Description": "Resource reallocation to remediation projects.",
        "Root Cause Sub-Theme":   "Resourcing",
        "Root Cause Theme":       "Operating Effectiveness",
        "Risk Level 2":           "Third Party",
    },

    # ISS-011 -- AE-1, INVALID Risk Level 2 ("Made Up Risk Category"). Track B
    # invariant: when source value does NOT normalize to a taxonomy L2,
    # ingest_prsa logs a WARNING and tags provenance as 'mapper' (fallback).
    {
        "Issue ID":             "ISS-011",
        "Issue Title":          "Bogus L2 tag on credit limit control",
        "Issue Owner":          "Quincy Patel",
        "Issue Status":         "Open",
        "Issue Status Rating":  "On Track",
        "Issue Impact Rating":  "Low",
        "Issue Identifier":     "INTERNAL",
        "Control ID (PRSA)":    "CTRL-002A",
        "Control ID (RCSA)":    "",
        "Issue Description": (
            "Filer tagged this issue with a Risk Level 2 value that does not "
            "match any canonical taxonomy L2. Provenance must fall back to "
            "the PRSA mapper output and emit a WARNING."
        ),
        "Root Cause Description": "Filer typo in IRM Archer freeform field.",
        "Root Cause Sub-Theme":   "Data Entry",
        "Root Cause Theme":       "Data Quality",
        "Risk Level 2":           "Made Up Risk Category",
    },

    # ISS-012 -- Track C: PG-flagged WITH a PRSA control. Issue Description
    # starts with `#PG`. Appears as both a PRSA pill and a PG Gap pill in
    # Impact of Issues, and shows up in BOTH Source - PRSA Issues AND
    # Source - PG Gaps Excel tabs (intentional duplication, Lu-confirmed).
    {
        "Issue ID":             "ISS-012",
        "Issue Title":          "PG gap: portfolio rebalancing thresholds out of policy",
        "Issue Owner":          "Sasha Lin",
        "Issue Status":         "Open",
        "Issue Status Rating":  "On Track",
        "Issue Impact Rating":  "High",
        "Issue Identifier":     "INTERNAL",
        "Control ID (PRSA)":    "CTRL-020",
        "Control ID (RCSA)":    "",
        "Issue Description": (
            "#PG Portfolio rebalancing process gap identified during 2026 PG review: "
            "drift threshold configuration is out of policy alignment and the control "
            "design does not enforce the documented limit."
        ),
        "Root Cause Description": "PG gap identified during quarterly review.",
        "Root Cause Sub-Theme":   "Policy Alignment",
        "Root Cause Theme":       "Control Design",
        "Risk Level 2":           "Processing, Execution and Change",
    },

    # ISS-013 -- Track C: PG-flagged WITHOUT a PRSA control. The responsible
    # team has not yet entered a PRSA control mapping in IRM Archer. Track C
    # invariant: this row is RETAINED in the Frankenstein with blank AE/Control
    # fields (only the Issue block populated). It appears ONLY in
    # Source - PG Gaps and contributes to the banner unmapped count.
    {
        "Issue ID":             "ISS-013",
        "Issue Title":          "PG gap awaiting PRSA control entry",
        "Issue Owner":          "Tara Volkov",
        "Issue Status":         "Open",
        "Issue Status Rating":  "On Track",
        "Issue Impact Rating":  "Medium",
        "Issue Identifier":     "INTERNAL",
        "Control ID (PRSA)":    "",
        "Control ID (RCSA)":    "",
        "Issue Description": (
            "PG Reconciliation gap discovered in 2026 PG sweep. The owning team has "
            "not yet entered a PRSA control mapping in IRM Archer; until they do, "
            "the gap cannot be attributed to a specific AE in LUminate."
        ),
        "Root Cause Description": "Awaiting PRSA control entry by owning team.",
        "Root Cause Sub-Theme":   "Mapping Gap",
        "Root Cause Theme":       "Data Quality",
        "Risk Level 2":           "Processing, Execution and Change",
    },
]


# ---------------------------------------------------------------------------
# Expected Frankenstein output schema (matches taxonomy_config.yaml columns.prsa
# AFTER the parallel drop of: Issue Breakdown Type, Issue Identified By Group,
# Issue Owning Business Unit, Process Owner). Cross-AE column is NOT included
# here -- it is derived at pipeline ingest time, not at build time.
# ---------------------------------------------------------------------------

EXPECTED_FRANKENSTEIN_COLUMNS: list[str] = [
    # AE block
    "AE ID",
    "AE Name",
    "Audit Leader",
    "Core Audit Team",
    "Audit Engagement ID",
    "All PRSAs Tagged to AE",
    # Issue block
    "Issue ID",
    "Issue Rating",
    "Issue Status",
    "Issue Identifier",
    "Issue Title",
    "Issue Description",
    "Issue Owner",
    "Root Cause Description",
    "Root Cause Sub-Theme",
    "Root Cause Theme",
    "Risk Level 2",
    # Control block
    "Control ID (PRSA)",
    "PRSA ID",
    "Process Title",
    "Control Title",
    # PG flag (Track C)
    "Is PG Gap",
]


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def build_archer_df() -> pd.DataFrame:
    """Build File 2 (PRSA_IRM_Archer): one row per Issue."""
    archer_columns = [
        "Issue ID",
        "Issue Title",
        "Issue Owner",
        "Issue Status",
        "Issue Status Rating",
        "Issue Impact Rating",
        "Issue Identifier",
        "Control ID (PRSA)",
        "Control ID (RCSA)",
        "Issue Description",
        "Root Cause Description",
        "Root Cause Sub-Theme",
        "Root Cause Theme",
        "Risk Level 2",
    ]
    rows = [{col: issue.get(col, "") for col in archer_columns} for issue in ISSUES]
    return pd.DataFrame(rows, columns=archer_columns)


def build_controls_map_df() -> pd.DataFrame:
    """Build File 3 (PRSA_Controls_Map): one row per control."""
    rows = [
        {
            "Control ID":    cid,
            "Control Title": ctitle,
            "Process ID":    pid,
            "Process Title": ptitle,
        }
        for (cid, ctitle, pid, ptitle) in CONTROLS_MAP
    ]
    return pd.DataFrame(rows, columns=["Control ID", "Control Title", "Process ID", "Process Title"])


def _controls_by_id() -> dict[str, dict]:
    return {
        cid: {"control_title": ctitle, "process_id": pid, "process_title": ptitle}
        for (cid, ctitle, pid, ptitle) in CONTROLS_MAP
    }


def _aes_tagged_to_prsa(prsa_id: str) -> list[str]:
    """Return AE IDs whose AE_PRSA_MAP list contains the given PRSA, in AE-id order."""
    return [aeid for aeid, prsa_list in AE_PRSA_MAP.items() if prsa_id in prsa_list]


_PG_FLAG_PREFIX_RE = re.compile(r"^(#?PG)(\b|\s|$)")


def _is_pg_gap(issue: dict) -> bool:
    """Mirror build_prsa_frankenstein._detect_pg_flag for golden expectations."""
    desc = str(issue.get("Issue Description", "") or "").lstrip()
    if not desc:
        return False
    return _PG_FLAG_PREFIX_RE.match(desc) is not None


def build_expected_frankenstein_df() -> pd.DataFrame:
    """Build the expected Frankenstein output (the golden file).

    Logic mirrors build_prsa_frankenstein.py:

      1. For each Issue, drop if Control ID (PRSA) is blank AND not PG-flagged
         (RCSA-only / pure unmapped rows). PG-flagged unmapped rows are
         retained with blank AE/Control fields.
      2. For mapped issues: explode Control ID (PRSA) on newline.
      3. Look up each control in CONTROLS_MAP -> get PRSA ID + titles.
      4. For each (Issue, control) pair, emit one row per AE whose
         AE_PRSA_MAP[AE] contains the control's PRSA ID.
      5. Each emitted row carries the AE's full PRSA tag list in
         "All PRSAs Tagged to AE" (newline-delimited).
      6. PG-flagged unmapped issues emit one row each with blank AE/Control
         block. Is PG Gap = "Yes" for PG-flagged rows, "No" otherwise.
    """
    controls = _controls_by_id()
    rows: list[dict] = []

    for issue in ISSUES:
        prsa_ctrl_raw = str(issue.get("Control ID (PRSA)", "")).strip()
        is_pg = _is_pg_gap(issue)
        pg_label = "Yes" if is_pg else "No"

        if not prsa_ctrl_raw:
            if not is_pg:
                continue  # RCSA-only / pure unmapped: drop
            # PG-unmapped: retain with blank AE/Control block
            rows.append({
                "AE ID":                  "",
                "AE Name":                "",
                "Audit Leader":           "",
                "Core Audit Team":        "",
                "Audit Engagement ID":    "",
                "All PRSAs Tagged to AE": "",
                "Issue ID":               issue["Issue ID"],
                "Issue Rating":           issue["Issue Impact Rating"],
                "Issue Status":           issue["Issue Status"],
                "Issue Identifier":       issue["Issue Identifier"],
                "Issue Title":            issue["Issue Title"],
                "Issue Description":      issue["Issue Description"],
                "Issue Owner":            issue["Issue Owner"],
                "Root Cause Description": issue.get("Root Cause Description", ""),
                "Root Cause Sub-Theme":   issue.get("Root Cause Sub-Theme", ""),
                "Root Cause Theme":       issue.get("Root Cause Theme", ""),
                "Risk Level 2":           issue.get("Risk Level 2", ""),
                "Control ID (PRSA)":      "",
                "PRSA ID":                "",
                "Process Title":          "",
                "Control Title":          "",
                "Is PG Gap":              pg_label,
            })
            continue

        ctrl_ids = [c.strip() for c in prsa_ctrl_raw.split("\n") if c.strip()]
        for ctrl_id in ctrl_ids:
            ctrl = controls.get(ctrl_id)
            if ctrl is None:
                # Defensive: an issue references a control not in the map.
                # Skip rather than silently emit a partial row.
                continue
            prsa_id = ctrl["process_id"]
            for ae_id in _aes_tagged_to_prsa(prsa_id):
                ae_name, audit_leader, team, eng_id = AE_CATALOG[ae_id]
                rows.append({
                    "AE ID":                  ae_id,
                    "AE Name":                ae_name,
                    "Audit Leader":           audit_leader,
                    "Core Audit Team":        team,
                    "Audit Engagement ID":    eng_id,
                    "All PRSAs Tagged to AE": "\n".join(AE_PRSA_MAP[ae_id]),
                    "Issue ID":               issue["Issue ID"],
                    "Issue Rating":           issue["Issue Impact Rating"],
                    "Issue Status":           issue["Issue Status"],
                    "Issue Identifier":       issue["Issue Identifier"],
                    "Issue Title":            issue["Issue Title"],
                    "Issue Description":      issue["Issue Description"],
                    "Issue Owner":            issue["Issue Owner"],
                    "Root Cause Description": issue.get("Root Cause Description", ""),
                    "Root Cause Sub-Theme":   issue.get("Root Cause Sub-Theme", ""),
                    "Root Cause Theme":       issue.get("Root Cause Theme", ""),
                    "Risk Level 2":           issue.get("Risk Level 2", ""),
                    "Control ID (PRSA)":      ctrl_id,
                    "PRSA ID":                prsa_id,
                    "Process Title":          ctrl["process_title"],
                    "Control Title":          ctrl["control_title"],
                    "Is PG Gap":              pg_label,
                })

    return pd.DataFrame(rows, columns=EXPECTED_FRANKENSTEIN_COLUMNS)


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def _verify(archer_path: Path, controls_path: Path, expected_path: Path) -> None:
    """Read each file back and assert structural invariants."""
    archer = pd.read_excel(archer_path)
    controls = pd.read_excel(controls_path)
    expected = pd.read_excel(expected_path)

    archer_required = {
        "Issue ID", "Issue Title", "Issue Owner", "Issue Status",
        "Issue Status Rating", "Issue Impact Rating", "Issue Identifier",
        "Control ID (PRSA)", "Control ID (RCSA)", "Issue Description",
        "Root Cause Description", "Root Cause Sub-Theme",
        "Root Cause Theme", "Risk Level 2",
    }
    missing = archer_required - set(archer.columns)
    assert not missing, f"Archer file missing columns: {missing}"

    controls_required = {"Control ID", "Control Title", "Process ID", "Process Title"}
    missing = controls_required - set(controls.columns)
    assert not missing, f"Controls Map file missing columns: {missing}"

    expected_required = set(EXPECTED_FRANKENSTEIN_COLUMNS)
    missing = expected_required - set(expected.columns)
    assert not missing, f"Expected Frankenstein missing columns: {missing}"

    # No "Other AEs With This PRSA" in the build output -- that's pipeline-derived
    assert "Other AEs With This PRSA" not in expected.columns, (
        "Expected Frankenstein must NOT include 'Other AEs With This PRSA' "
        "(that column is built by ingest_prsa, not by the build script)."
    )

    # Compute expected row count from source semantics
    controls_lookup = _controls_by_id()
    expected_count = 0
    for issue in ISSUES:
        prsa_ctrl_raw = str(issue.get("Control ID (PRSA)", "")).strip()
        is_pg = _is_pg_gap(issue)
        if not prsa_ctrl_raw:
            if is_pg:
                # Track C: PG-flagged unmapped row retained as a single row
                # with blank AE/Control block.
                expected_count += 1
            continue
        ctrl_ids = [c.strip() for c in prsa_ctrl_raw.split("\n") if c.strip()]
        for ctrl_id in ctrl_ids:
            ctrl = controls_lookup.get(ctrl_id)
            if ctrl is None:
                continue
            expected_count += len(_aes_tagged_to_prsa(ctrl["process_id"]))
    assert len(expected) == expected_count, (
        f"Expected Frankenstein row count mismatch: "
        f"file has {len(expected)}, computed {expected_count}"
    )

    # ISS-005 (RCSA-only, non-PG) MUST NOT appear (regression check)
    assert "ISS-005" not in set(expected["Issue ID"].astype(str)), (
        "ISS-005 (RCSA-only, non-PG) leaked into expected Frankenstein"
    )

    # ISS-003 (Closed) MUST appear
    assert "ISS-003" in set(expected["Issue ID"].astype(str)), (
        "ISS-003 (Closed) missing from expected Frankenstein"
    )

    # AE-7 (no failing issues) MUST NOT appear in any row's AE ID
    assert "AE-7" not in set(expected["AE ID"].astype(str)), (
        "AE-7 has no failing issues but appeared in expected Frankenstein"
    )

    # Track C invariants
    # 1. ISS-012 (PG mapped) MUST appear with Is PG Gap = Yes and a populated AE
    iss012 = expected[expected["Issue ID"].astype(str) == "ISS-012"]
    assert not iss012.empty, "ISS-012 (PG mapped) missing from expected Frankenstein"
    assert (iss012["Is PG Gap"] == "Yes").all(), "ISS-012 must have Is PG Gap = Yes"
    assert (iss012["AE ID"].astype(str).str.strip() != "").all(), (
        "ISS-012 (PG mapped) must have a populated AE ID"
    )

    # 2. ISS-013 (PG unmapped) MUST appear exactly once with Is PG Gap = Yes
    #    and BLANK AE / Control fields. Excel converts our empty-string writes
    #    back to NaN on read, so accept either "" or "nan" as "blank".
    def _is_blank_cell(s: str) -> bool:
        return s.strip() == "" or s.strip().lower() == "nan"

    iss013 = expected[expected["Issue ID"].astype(str) == "ISS-013"]
    assert len(iss013) == 1, (
        f"ISS-013 (PG unmapped) should have exactly one row, found {len(iss013)}"
    )
    assert (iss013["Is PG Gap"] == "Yes").all(), "ISS-013 must have Is PG Gap = Yes"
    assert iss013["AE ID"].astype(str).apply(_is_blank_cell).all(), (
        "ISS-013 (PG unmapped) must have blank AE ID"
    )
    assert iss013["Control ID (PRSA)"].astype(str).apply(_is_blank_cell).all(), (
        "ISS-013 (PG unmapped) must have blank Control ID (PRSA)"
    )

    # 3. Non-PG issues MUST have Is PG Gap = No
    non_pg_issues = {issue["Issue ID"] for issue in ISSUES if not _is_pg_gap(issue)}
    non_pg_in_expected = expected[expected["Issue ID"].astype(str).isin(non_pg_issues)]
    assert (non_pg_in_expected["Is PG Gap"] == "No").all(), (
        "Non-PG issues should have Is PG Gap = No"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    archer_df = build_archer_df()
    controls_df = build_controls_map_df()
    expected_df = build_expected_frankenstein_df()

    archer_path   = OUTPUT_DIR / "PRSA_IRM_Archer_test_dummy.xlsx"
    controls_path = OUTPUT_DIR / "PRSA_Controls_Map_test_dummy.xlsx"
    expected_path = OUTPUT_DIR / "prsa_report_test_dummy.xlsx"

    with pd.ExcelWriter(archer_path, engine="openpyxl") as w:
        archer_df.to_excel(w, index=False)
    with pd.ExcelWriter(controls_path, engine="openpyxl") as w:
        controls_df.to_excel(w, index=False)
    with pd.ExcelWriter(expected_path, engine="openpyxl") as w:
        expected_df.to_excel(w, index=False)

    print(f"Created: {archer_path}")
    print(f"  Issues:                       {len(archer_df)}")
    print(f"  Issues with PRSA control:     {(archer_df['Control ID (PRSA)'].astype(str).str.strip() != '').sum()}")
    print(f"  Issues RCSA-only (dropped):   {(archer_df['Control ID (RCSA)'].astype(str).str.strip().ne('') & archer_df['Control ID (PRSA)'].astype(str).str.strip().eq('')).sum()}")
    print(f"  Issues with multi-control:    {archer_df['Control ID (PRSA)'].astype(str).str.contains(chr(10)).sum()}")
    print(f"  Issues with blank L2:         {(archer_df['Risk Level 2'].astype(str).str.strip() == '').sum()}")
    print(f"  Closed issues:                {(archer_df['Issue Status'] == 'Closed').sum()}")
    pg_flagged = sum(1 for i in ISSUES if _is_pg_gap(i))
    print(f"  PG-flagged issues:            {pg_flagged}")

    print(f"\nCreated: {controls_path}")
    print(f"  Controls:                     {len(controls_df)}")
    print(f"  PRSAs in map:                 {controls_df['Process ID'].nunique()}")
    print(f"  PRSAs with multiple controls: {(controls_df.groupby('Process ID').size() >= 2).sum()}")
    referenced_in_issues = set()
    for issue in ISSUES:
        for c in str(issue.get("Control ID (PRSA)", "")).split("\n"):
            c = c.strip()
            if c:
                referenced_in_issues.add(c)
    no_issue_controls = [cid for (cid, *_rest) in CONTROLS_MAP if cid not in referenced_in_issues]
    print(f"  Controls with no failing issue: {len(no_issue_controls)}  ({no_issue_controls})")

    print(f"\nCreated: {expected_path}")
    print(f"  Frankenstein rows:            {len(expected_df)}")
    print(f"  Unique AEs in output:         {expected_df['AE ID'].nunique()}")
    print(f"  Unique Issues in output:      {expected_df['Issue ID'].nunique()}")
    print(f"  Unique PRSAs in output:       {expected_df['PRSA ID'].nunique()}")
    print(f"  Unique controls in output:    {expected_df['Control ID (PRSA)'].nunique()}")

    print("\nScenario coverage:")
    print("  - AE-1 has 4 PRSAs (PRSA-001/002/003/100), multiple with issues")
    print("  - PRSA-003 shared across AE-1, AE-3, AE-5 (3+ AEs)")
    print("  - PRSA-100 shared across AE-1, AE-6 (cross-AE, no issues)")
    print("  - AE-7 tagged to PRSA-018, PRSA-019 -> 0 Frankenstein rows")
    print("  - ISS-002 has 2 PRSA controls (newline-delimited) -> 2 rows for AE-1")
    print("  - ISS-004 has 3 PRSA controls (newline-delimited) -> 3 rows for AE-4")
    print("  - ISS-003 has 1 control on shared PRSA-003 -> 3 rows (AE-1, AE-3, AE-5)")
    print("  - ISS-005 is RCSA-only (non-PG) -> dropped (must NOT appear)")
    print("  - ISS-006 has blank Risk Level 2 (preserved blank, falls back to mapper)")
    print("  - ISS-007 has blank Root Cause fields (preserved blank)")
    print("  - ISS-011 has invalid Risk Level 2 ('Made Up Risk Category') -> mapper fallback + WARNING")
    print("  - ISS-003 has Issue Status = Closed -> still appears in Frankenstein")
    print("  - Issue Impact Ratings cover Low / Medium / High / Critical")
    print("  - Issue Identifier mix: INTERNAL and EXTERNAL")
    print("  - CTRL-005 (PRSA-005) and CTRL-018A (PRSA-018) have no failing issue")
    print("  - Track C: ISS-012 PG-flagged WITH PRSA control -> mapped row + Is PG Gap = Yes")
    print("  - Track C: ISS-013 PG-flagged WITHOUT PRSA control -> retained with blank AE/Control")
    pg_total = sum(1 for i in ISSUES if _is_pg_gap(i))
    pg_unmapped_count = sum(
        1 for i in ISSUES
        if _is_pg_gap(i) and not str(i.get("Control ID (PRSA)", "")).strip()
    )
    print(f"  - PG fixture coverage: {pg_total} total PG, {pg_unmapped_count} unmapped")

    # Verify
    _verify(archer_path, controls_path, expected_path)
    print("\nAll structural assertions passed.")


if __name__ == "__main__":
    main()
