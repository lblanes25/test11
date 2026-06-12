"""Unit tests for enrichment.derive_inherent_risk_rating.

Pins the Likelihood x max(Impact) matrix, None/NaN handling, and the
source_not_applicable label path.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from risk_taxonomy_transformer.enrichment import derive_inherent_risk_rating

IMPACT_COLS = ["impact_financial", "impact_reputational",
               "impact_consumer_harm", "impact_regulatory"]


def _df(rows: list[dict]) -> pd.DataFrame:
    base = {
        "method": "direct",
        "likelihood": None,
        "impact_financial": None,
        "impact_reputational": None,
        "impact_consumer_harm": None,
        "impact_regulatory": None,
    }
    return pd.DataFrame([dict(base, **r) for r in rows])


def _derive_one(row: dict):
    out = derive_inherent_risk_rating(_df([row]))
    r = out.iloc[0]
    def _v(x):
        return None if pd.isna(x) else x
    return (_v(r["overall_impact"]), _v(r["inherent_risk_rating"]),
            _v(r["inherent_risk_rating_label"]))


# --- representative matrix combos ------------------------------------------------

@pytest.mark.parametrize("likelihood,impact,rating,label", [
    (1, 1, 1, "Low"),
    (1, 2, 1, "Low"),
    (1, 4, 2, "Medium"),
    (2, 2, 2, "Medium"),
    (2, 4, 3, "High"),
    (3, 1, 2, "Medium"),
    (3, 3, 3, "High"),
    (3, 4, 4, "Critical"),
    (4, 1, 2, "Medium"),
    (4, 2, 3, "High"),
    (4, 4, 4, "Critical"),
])
def test_matrix_uniform_impacts(likelihood, impact, rating, label):
    row = {"likelihood": likelihood, **{c: impact for c in IMPACT_COLS}}
    assert _derive_one(row) == (impact, rating, label)


def test_overall_impact_is_max_of_dimensions():
    row = {"likelihood": 2, "impact_financial": 1, "impact_reputational": 4,
           "impact_consumer_harm": 2, "impact_regulatory": 1}
    # max impact 4, likelihood 2 -> rating 3 High
    assert _derive_one(row) == (4, 3, "High")


def test_partial_impacts_use_available_dimensions_only():
    row = {"likelihood": 4, "impact_financial": 1}
    # Only one valid impact -> overall 1; (4,1) -> 2 Medium
    assert _derive_one(row) == (1, 2, "Medium")


# --- None / NaN handling -----------------------------------------------------------

def test_no_likelihood_yields_all_none():
    row = {c: 3 for c in IMPACT_COLS}
    assert _derive_one(row) == (None, None, None)


def test_nan_likelihood_yields_all_none():
    row = {"likelihood": float("nan"), **{c: 3 for c in IMPACT_COLS}}
    assert _derive_one(row) == (None, None, None)


def test_likelihood_without_any_impact_yields_all_none():
    row = {"likelihood": 3}
    assert _derive_one(row) == (None, None, None)


# --- source_not_applicable path -------------------------------------------------------

def test_source_not_applicable_gets_na_label():
    row = {"method": "source_not_applicable", "likelihood": 3,
           **{c: 3 for c in IMPACT_COLS}}
    assert _derive_one(row) == (None, None, "Not Applicable")


def test_full_frame_adds_three_columns():
    df = _df([
        {"likelihood": 2, **{c: 2 for c in IMPACT_COLS}},
        {"likelihood": None},
    ])
    out = derive_inherent_risk_rating(df)
    for col in ("overall_impact", "inherent_risk_rating",
                "inherent_risk_rating_label"):
        assert col in out.columns
    assert len(out) == 2
