"""Tests for the IRM ORE consolidation pre-step (consolidate_ore_irm.py).

Builds the stacked raw fixture, runs build(--test-dummy), and asserts the
collapse to one row per ORE ID, ore-level first-non-blank carry, distinct
newline rollups for cause/risk, impact counts, and the Impact Assessment
Closed Yes/No rule for each crafted case.

Run:
    python -m pytest tests/test_ore_irm_consolidate.py -q
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

import consolidate_ore_irm as cons
from tests.generate_ore_irm_raw_test_data import main as gen_raw_main


def _build_consolidated() -> pd.DataFrame:
    gen_raw_main()
    args = argparse.Namespace(test_dummy=True, raw=None, output=None)
    out_path = cons.build(args)
    assert out_path.exists(), f"consolidation output not written: {out_path}"
    return pd.read_excel(out_path, dtype=str, keep_default_na=False)


def _row(df: pd.DataFrame, ore_id: str) -> pd.Series:
    sub = df[df["ORE ID"] == ore_id]
    assert len(sub) == 1, f"expected exactly one row for {ore_id}, got {len(sub)}"
    return sub.iloc[0]


def test_one_row_per_ore_id():
    df = _build_consolidated()
    assert df["ORE ID"].is_unique
    expected = {
        "ORE-1135446", "ORE-2000001", "ORE-2000002", "ORE-2000003",
        "ORE-2000004", "ORE-2000005", "ORE-2000006",
    }
    assert set(df["ORE ID"]) == expected


def test_ore_level_first_non_blank():
    df = _build_consolidated()
    r = _row(df, "ORE-1135446")
    assert r["ORE Title"] == "Settlement reconciliation control failure"
    assert r["ORE Category"] == "Material ORE"
    assert r["Risk Pillar"] == "Operational"


def test_cause_risk_distinct_newline_rollup():
    df = _build_consolidated()
    r = _row(df, "ORE-2000001")
    causes = r["Cause ID"].split("\n")
    assert causes == ["C-10", "C-11"]
    # Two risk rows both carry the same Risk Level 2 -> distinct collapses to one.
    assert r["Risk Level 2"] == "Information and Cyber Security"
    rl4 = r["Risk Level 4"].split("\n")
    assert rl4 == ["Account Compromise", "Data Exfiltration"]


def test_53_impact_ore_counts_and_status():
    df = _build_consolidated()
    r = _row(df, "ORE-1135446")
    assert int(r["Source Row Count"]) == 1 + 1 + 53
    assert int(r["Cause Row Count"]) == 1
    assert int(r["Risk Row Count"]) == 1
    assert int(r["Impact Assessment Row Count"]) == 53
    assert r["Impact Assessment Status Counts"] == "Completed (53)"
    assert r["Impact Assessment Closed"] == "Yes"


def test_impact_closed_in_progress_is_open():
    df = _build_consolidated()
    r = _row(df, "ORE-2000001")
    assert int(r["Impact Assessment Row Count"]) == 3
    assert r["Impact Assessment Closed"] == "No"


def test_impact_closed_not_needed_cancelled_is_closed():
    df = _build_consolidated()
    r = _row(df, "ORE-2000002")
    assert int(r["Impact Assessment Row Count"]) == 3
    assert r["Impact Assessment Closed"] == "Yes"


def test_impact_closed_blank_status_is_open():
    df = _build_consolidated()
    r = _row(df, "ORE-2000003")
    assert int(r["Impact Assessment Row Count"]) == 2
    assert r["Impact Assessment Closed"] == "No"
    assert "(blank) (1)" in r["Impact Assessment Status Counts"]


def test_base_only_ore_is_not_closed():
    df = _build_consolidated()
    r = _row(df, "ORE-2000004")
    assert int(r["Impact Assessment Row Count"]) == 0
    assert int(r["Cause Row Count"]) == 0
    assert int(r["Risk Row Count"]) == 0
    assert r["Impact Assessment Closed"] == "No"
    assert r["Impact Assessment Status Counts"] == ""


def test_duplicate_impact_rows_counted():
    df = _build_consolidated()
    r = _row(df, "ORE-2000006")
    # Three impact rows (IMP-E1 twice, IMP-E2 once) all Completed.
    assert int(r["Impact Assessment Row Count"]) == 3
    assert r["Impact Assessment Status Counts"] == "Completed (3)"
    # Impact ID rollup is distinct.
    assert r["Impact ID"].split("\n") == ["IMP-E1", "IMP-E2"]
    assert r["Impact Assessment Closed"] == "Yes"


def test_consolidated_ore_status_column():
    """Consolidation writes a full ORE Status the mapper/ingestion read."""
    df = _build_consolidated()
    status = dict(zip(df["ORE ID"], df["ORE Status"]))
    assert status["ORE-1135446"] == "Closed"   # Material, all phases done
    assert status["ORE-2000001"] == "Open"      # impact In-Progress
    assert status["ORE-2000002"] == "Closed"    # impacts Not Needed/Cancelled
    assert status["ORE-2000003"] == "Open"      # blank impact status
    assert status["ORE-2000004"] == "Open"      # no impacts => impact phase open
    assert status["ORE-2000005"] == ""          # Below Threshold => non-Material
    assert status["ORE-2000006"] == "Closed"
    # Exactly the Closed ones are what the mapper will skip.
    closed = {oid for oid, s in status.items() if s == "Closed"}
    assert closed == {"ORE-1135446", "ORE-2000002", "ORE-2000006"}


def test_derive_status_uses_consolidated_closed_flag():
    """The ingestion impact phase honors the consolidated Closed flag."""
    from risk_taxonomy_transformer.ingestion import _derive_irm_ore_status

    cols = {
        "ore_category": "ORE Category",
        "capture_status": "Capture Status",
        "rca_status": "RCA Status",
        "impact_assessment_status": "Impact Assessment Status",
        "stop_ongoing_impact_status": "Stop ongoing impact Status",
    }
    completed = {"completed", "complete"}

    base = {
        "ORE Category": "Material ORE",
        "Capture Status": "Completed",
        "RCA Status": "Completed",
        "Stop ongoing impact Status": "Completed",
        "Impact Assessment Status": "Completed",  # would be Closed by flat path
    }
    # Consolidated flag says open -> Open even though flat status is Completed.
    open_row = dict(base, **{"Impact Assessment Closed": "No"})
    assert _derive_irm_ore_status(open_row, cols, completed) == "Open"

    closed_row = dict(base, **{"Impact Assessment Closed": "Yes"})
    assert _derive_irm_ore_status(closed_row, cols, completed) == "Closed"

    # No flag -> falls back to flat impact_assessment_status check.
    flat_row = dict(base)
    assert _derive_irm_ore_status(flat_row, cols, completed) == "Closed"

    # Non-material category (Below Threshold) -> blank regardless.
    nonmat = dict(base, **{"ORE Category": "Below Threshold", "Impact Assessment Closed": "No"})
    assert _derive_irm_ore_status(nonmat, cols, completed) == ""

    # Blank category -> treated as Material (cautious rule), so still scored.
    blankcat = dict(base, **{"ORE Category": "", "Impact Assessment Closed": "Yes"})
    assert _derive_irm_ore_status(blankcat, cols, completed) == "Closed"
