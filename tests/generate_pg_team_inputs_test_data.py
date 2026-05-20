"""Generate dummy PG team inputs file for the Track C2 (FND_ID bridge) integration.

Emits ``data/input/project_guardian_aera_inputs_test_dummy.xlsx`` — one sheet,
four columns (per YAML ``columns.pg_team_inputs``):

  - Gap ID
  - Impact Rating
  - Issue ID (Archer IRM)        joins to PRSA Frankenstein Issue ID
  - Archer eGRC FND ID           joins to findings_data Finding ID

Six rows, one per diagnostic verdict case (see scripts/compare_pg_mappings.py):

  GAP-001  match            ISS-010 (PRSA -> AE-9 / Third Party) + F-9002
                            (findings -> AE-9 / Third Party after L1 strip)
  GAP-002  pg-only          ISS-013 (PG-flagged, no PRSA control) + F-3001 (-> AE-3)
  GAP-003  pg-team-only     PG-ONLY-001 (absent from PRSA) + F-1010 (-> AE-1)
  GAP-004  disagree         ISS-004 (PRSA -> AE-4)  + F-3002 (findings -> AE-3)
  GAP-005  prsa-only        ISS-001 (PRSA -> AE-1)  + blank Finding ID
  GAP-006  both-empty       blank Issue ID + blank Finding ID

Cross-file consistency: Issue IDs and Finding IDs used here exist in
``tests/generate_prsa_source_test_data.py`` (ISS-001..ISS-013) and
``tests/generate_test_data.py`` (F-1001, F-1010, F-3001, F-3002) respectively,
except ``PG-ONLY-001`` which is intentionally absent from PRSA to exercise
the pg-team-only path.

Usage:
    python tests/generate_pg_team_inputs_test_data.py
"""

from __future__ import annotations

import pandas as pd
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = _PROJECT_ROOT / "data" / "input"

GAP_ID_COL = "Gap ID"
IMPACT_RATING_COL = "Impact Rating"
ISSUE_ID_COL = "Issue ID (Archer IRM)"
FINDING_ID_COL = "Archer eGRC FND ID"

COLUMNS: list[str] = [GAP_ID_COL, IMPACT_RATING_COL, ISSUE_ID_COL, FINDING_ID_COL]


GAPS: list[dict] = [
    # GAP-001: match -- both routes resolve to AE-9 / Third Party. ISS-010
    # PRSA route -> AE-9 via CTRL-024 / PRSA-024 (Risk Level 2 "Third Party").
    # F-9002 findings route -> AE-9 / Third Party (after stripping the
    # "Operational - " L1 prefix in normalize_l2_name).
    {
        GAP_ID_COL:        "GAP-001",
        IMPACT_RATING_COL: "High",
        ISSUE_ID_COL:      "ISS-010",
        FINDING_ID_COL:    "F-9002",
        "_case":           "match",
    },

    # GAP-002: pg-only -- ISS-013 has no PRSA control so PRSA route fails;
    # F-3001 resolves to AE-3 via findings.
    {
        GAP_ID_COL:        "GAP-002",
        IMPACT_RATING_COL: "Medium",
        ISSUE_ID_COL:      "ISS-013",
        FINDING_ID_COL:    "F-3001",
        "_case":           "pg-only",
    },

    # GAP-003: pg-team-only -- Issue ID absent from PRSA Frankenstein entirely;
    # synthesized row surfaces in Source - PG Gaps with the PG team's rating.
    {
        GAP_ID_COL:        "GAP-003",
        IMPACT_RATING_COL: "Critical",
        ISSUE_ID_COL:      "PG-ONLY-001",
        FINDING_ID_COL:    "F-1010",
        "_case":           "pg-team-only",
    },

    # GAP-004: disagree -- ISS-004 PRSA route -> AE-4; F-3002 findings -> AE-3.
    {
        GAP_ID_COL:        "GAP-004",
        IMPACT_RATING_COL: "High",
        ISSUE_ID_COL:      "ISS-004",
        FINDING_ID_COL:    "F-3002",
        "_case":           "disagree",
    },

    # GAP-005: blank-FND -- PRSA route resolves to AE-1 via ISS-001 but the
    # FND bridge has nothing to look up (data quality case).
    {
        GAP_ID_COL:        "GAP-005",
        IMPACT_RATING_COL: "Low",
        ISSUE_ID_COL:      "ISS-001",
        FINDING_ID_COL:    "",
        "_case":           "prsa-only (blank-FND)",
    },

    # GAP-006: full-orphan -- neither bridge populated. Surfaces in the
    # diagnostic's data-quality footer.
    {
        GAP_ID_COL:        "GAP-006",
        IMPACT_RATING_COL: "Medium",
        ISSUE_ID_COL:      "",
        FINDING_ID_COL:    "",
        "_case":           "both-empty (full-orphan)",
    },
]


def build_df() -> pd.DataFrame:
    rows = [{col: gap.get(col, "") for col in COLUMNS} for gap in GAPS]
    return pd.DataFrame(rows, columns=COLUMNS)


def _verify(out_path: Path) -> None:
    df = pd.read_excel(out_path)
    missing = [c for c in COLUMNS if c not in df.columns]
    assert not missing, f"Output missing columns: {missing}"
    assert len(df) == len(GAPS), f"Row count mismatch: file has {len(df)}, expected {len(GAPS)}"
    # Spot-check the match-case row
    gap1 = df[df[GAP_ID_COL] == "GAP-001"]
    assert len(gap1) == 1, "GAP-001 missing"
    assert gap1.iloc[0][ISSUE_ID_COL] == "ISS-010"
    assert gap1.iloc[0][FINDING_ID_COL] == "F-9002"
    # Spot-check the full-orphan row reads back as blank-equivalent
    gap6 = df[df[GAP_ID_COL] == "GAP-006"]
    assert len(gap6) == 1, "GAP-006 missing"
    iid = str(gap6.iloc[0][ISSUE_ID_COL]).strip()
    fid = str(gap6.iloc[0][FINDING_ID_COL]).strip()
    assert iid in ("", "nan"), f"GAP-006 Issue ID should be blank, got {iid!r}"
    assert fid in ("", "nan"), f"GAP-006 Finding ID should be blank, got {fid!r}"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "project_guardian_aera_inputs_test_dummy.xlsx"
    df = build_df()
    with pd.ExcelWriter(out_path, engine="openpyxl") as w:
        df.to_excel(w, index=False)

    print(f"Created: {out_path}")
    print(f"  Total rows: {len(df)}")
    print(f"  Columns:    {list(df.columns)}")

    has_issue = (df[ISSUE_ID_COL].astype(str).str.strip() != "").sum()
    has_fnd = (df[FINDING_ID_COL].astype(str).str.strip() != "").sum()
    has_both = (
        (df[ISSUE_ID_COL].astype(str).str.strip() != "")
        & (df[FINDING_ID_COL].astype(str).str.strip() != "")
    ).sum()
    has_neither = (
        (df[ISSUE_ID_COL].astype(str).str.strip() == "")
        & (df[FINDING_ID_COL].astype(str).str.strip() == "")
    ).sum()
    print(f"  Rows with Issue ID:        {has_issue}")
    print(f"  Rows with Finding ID:      {has_fnd}")
    print(f"  Rows with both populated:  {has_both}")
    print(f"  Rows with neither:         {has_neither}")

    print("\nVerdict-case breakdown (one row per case):")
    for gap in GAPS:
        print(f"  {gap[GAP_ID_COL]:<8} {gap['_case']:<28} "
              f"Issue={gap[ISSUE_ID_COL] or '(blank)':<14} "
              f"FND={gap[FINDING_ID_COL] or '(blank)'}")

    print("\nCross-file ID references:")
    print("  PRSA Issue IDs used:    ISS-001, ISS-004, ISS-010, ISS-013")
    print("  PRSA Issue IDs absent:  PG-ONLY-001 (intentional pg-team-only case)")
    print("  Finding IDs used:       F-1010 (AE-1), F-3001 (AE-3), F-3002 (AE-3), F-9002 (AE-9)")

    _verify(out_path)
    print("\nAll structural assertions passed.")


if __name__ == "__main__":
    main()
