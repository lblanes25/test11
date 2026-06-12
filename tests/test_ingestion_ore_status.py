"""Unit tests for ingestion._derive_irm_ore_status / _derive_irm_ore_statuses.

Characterization tests pinning the Open/Closed derivation: all-phases-done,
any-phase-open, cancelled-capture short-circuit, consolidated "Impact
Assessment Closed" gating vs the flat fallback, and the per-ORE roll-up where
a single unfinished impact row keeps the ORE Open.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from risk_taxonomy_transformer.ingestion import (
    _derive_irm_ore_status,
    _derive_irm_ore_statuses,
)

COLS = {
    "ore_id": "ORE ID",
    "impact_id": "Impact ID",
    "ore_category": "ORE Category",
    "capture_status": "Capture Status",
    "rca_status": "RCA Status",
    "impact_assessment_status": "Impact Assessment Status",
    "stop_ongoing_impact_status": "Stop ongoing impact Status",
}
COMPLETED = {"completed", "complete", "not needed", "cancelled"}

ALL_DONE = {
    "Capture Status": "Completed",
    "RCA Status": "Completed",
    "Stop ongoing impact Status": "Completed",
    "Impact Assessment Status": "Completed",
}


# --- _derive_irm_ore_status (single row) ---------------------------------------

def test_all_phases_done_is_closed():
    assert _derive_irm_ore_status(dict(ALL_DONE), COLS, COMPLETED) == "Closed"


def test_completed_values_matched_case_insensitively():
    row = {k: v.upper() for k, v in ALL_DONE.items()}
    assert _derive_irm_ore_status(row, COLS, COMPLETED) == "Closed"


def test_any_phase_open_is_open():
    for phase in ("Capture Status", "RCA Status",
                  "Stop ongoing impact Status", "Impact Assessment Status"):
        row = dict(ALL_DONE, **{phase: "In-Progress"})
        assert _derive_irm_ore_status(row, COLS, COMPLETED) == "Open", phase


def test_blank_phase_is_open():
    row = dict(ALL_DONE, **{"RCA Status": ""})
    assert _derive_irm_ore_status(row, COLS, COMPLETED) == "Open"


def test_cancelled_capture_short_circuits_to_closed():
    row = dict(ALL_DONE, **{
        "Capture Status": "Cancelled",
        "RCA Status": "In-Progress",
        "Impact Assessment Status": "In-Progress",
    })
    assert _derive_irm_ore_status(row, COLS, COMPLETED) == "Closed"
    # American spelling too.
    row["Capture Status"] = "Canceled"
    assert _derive_irm_ore_status(row, COLS, COMPLETED) == "Closed"


def test_cancelled_beats_consolidated_open_flag():
    row = dict(ALL_DONE, **{
        "Capture Status": "Cancelled",
        "Impact Assessment Closed": "No",
    })
    assert _derive_irm_ore_status(row, COLS, COMPLETED) == "Closed"


def test_consolidated_flag_gates_impact_phase():
    # Flat status says Completed, but the consolidated flag says No -> Open.
    open_row = dict(ALL_DONE, **{"Impact Assessment Closed": "No"})
    assert _derive_irm_ore_status(open_row, COLS, COMPLETED) == "Open"

    closed_row = dict(ALL_DONE, **{"Impact Assessment Closed": "Yes"})
    assert _derive_irm_ore_status(closed_row, COLS, COMPLETED) == "Closed"


def test_blank_consolidated_flag_falls_back_to_flat_status():
    flat_closed = dict(ALL_DONE, **{"Impact Assessment Closed": ""})
    assert _derive_irm_ore_status(flat_closed, COLS, COMPLETED) == "Closed"

    flat_open = dict(ALL_DONE, **{
        "Impact Assessment Closed": "nan",
        "Impact Assessment Status": "In-Progress",
    })
    assert _derive_irm_ore_status(flat_open, COLS, COMPLETED) == "Open"


def test_materiality_does_not_affect_status():
    row = dict(ALL_DONE, **{"ORE Category": "Below Threshold"})
    assert _derive_irm_ore_status(row, COLS, COMPLETED) == "Closed"


# --- _derive_irm_ore_statuses (roll-up across stacked rows) ---------------------

def _stacked(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_rollup_all_impacts_done_is_closed():
    df = _stacked([
        {"ORE ID": "ORE-1", "Impact ID": "", **ALL_DONE},
        {"ORE ID": "ORE-1", "Impact ID": "IMP-1", **ALL_DONE},
        {"ORE ID": "ORE-1", "Impact ID": "IMP-2", **ALL_DONE},
    ])
    assert _derive_irm_ore_statuses(df, COLS, COMPLETED) == {"ORE-1": "Closed"}


def test_rollup_one_unfinished_impact_keeps_ore_open():
    df = _stacked([
        {"ORE ID": "ORE-1", "Impact ID": "", **ALL_DONE},
        {"ORE ID": "ORE-1", "Impact ID": "IMP-1", **ALL_DONE},
        {"ORE ID": "ORE-1", "Impact ID": "IMP-2",
         **dict(ALL_DONE, **{"Impact Assessment Status": "In-Progress"})},
    ])
    assert _derive_irm_ore_statuses(df, COLS, COMPLETED) == {"ORE-1": "Open"}


def test_rollup_no_impact_rows_is_open():
    # No impact-bearing rows at all -> impact phase judged unfinished.
    df = _stacked([
        {"ORE ID": "ORE-1", "Impact ID": "",
         **dict(ALL_DONE, **{"Impact Assessment Status": ""})},
    ])
    assert _derive_irm_ore_statuses(df, COLS, COMPLETED) == {"ORE-1": "Open"}


def test_rollup_honors_consolidated_flag_over_impact_rows():
    # First non-blank "Impact Assessment Closed" wins; impact rows ignored.
    df = _stacked([
        {"ORE ID": "ORE-1", "Impact ID": "", "Impact Assessment Closed": "Yes",
         **ALL_DONE},
        {"ORE ID": "ORE-1", "Impact ID": "IMP-1",
         "Impact Assessment Closed": "",
         **dict(ALL_DONE, **{"Impact Assessment Status": "In-Progress"})},
    ])
    assert _derive_irm_ore_statuses(df, COLS, COMPLETED) == {"ORE-1": "Closed"}


def test_rollup_first_nonblank_carry_for_phase_columns():
    # Phase statuses are collapsed first-non-blank across stacked rows.
    df = _stacked([
        {"ORE ID": "ORE-1", "Impact ID": "", "Capture Status": "",
         "RCA Status": "Completed", "Stop ongoing impact Status": "Completed",
         "Impact Assessment Status": ""},
        {"ORE ID": "ORE-1", "Impact ID": "IMP-1", "Capture Status": "Completed",
         "RCA Status": "", "Stop ongoing impact Status": "",
         "Impact Assessment Status": "Completed"},
    ])
    assert _derive_irm_ore_statuses(df, COLS, COMPLETED) == {"ORE-1": "Closed"}


def test_rollup_multiple_ores_independent():
    df = _stacked([
        {"ORE ID": "ORE-1", "Impact ID": "IMP-1", **ALL_DONE},
        {"ORE ID": "ORE-2", "Impact ID": "IMP-2",
         **dict(ALL_DONE, **{"Capture Status": "In-Progress"})},
        {"ORE ID": "ORE-3", "Impact ID": "IMP-3",
         **dict(ALL_DONE, **{"Capture Status": "Cancelled",
                             "RCA Status": "In-Progress"})},
    ])
    assert _derive_irm_ore_statuses(df, COLS, COMPLETED) == {
        "ORE-1": "Closed", "ORE-2": "Open", "ORE-3": "Closed",
    }


def test_rollup_missing_ore_id_column_returns_empty():
    df = pd.DataFrame([{"Something": "x"}])
    assert _derive_irm_ore_statuses(df, COLS, COMPLETED) == {}
