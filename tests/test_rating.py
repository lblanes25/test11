"""Unit tests for rating.convert_risk_rating and parse_rationale_for_dimensions.

Characterization tests: these pin the regexes' actual current behavior,
including documented forms that do NOT parse today (see the abbreviation
tests — the "L:" / "I:" patterns are case-sensitive against lowercased text
and never match).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from risk_taxonomy_transformer.rating import (
    convert_control_rating,
    convert_risk_rating,
    parse_rationale_for_dimensions,
)


# --- convert_risk_rating --------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("Low", 1), ("Medium", 2), ("High", 3), ("Critical", 4),
    ("low", 1), (" HIGH ", 3),
    ("l", 1), ("m", 2), ("h", 3), ("c", 4),
    ("1", 1), ("2", 2), ("3", 3), ("4", 4),
])
def test_convert_risk_rating_known_values(raw, expected):
    assert convert_risk_rating(raw) == expected


@pytest.mark.parametrize("raw", [
    "Not Applicable", "N/A", "", "unknown rating", "5",
])
def test_convert_risk_rating_unmapped_strings_return_none(raw):
    assert convert_risk_rating(raw) is None


def test_convert_risk_rating_nan_and_none_return_none():
    assert convert_risk_rating(None) is None
    assert convert_risk_rating(float("nan")) is None


def test_convert_control_rating_known_values():
    assert convert_control_rating("Well Controlled") == 1
    assert convert_control_rating("Moderately Controlled") == 2
    assert convert_control_rating("Insufficiently Controlled") == 4
    assert convert_control_rating("Satisfactory") == 1


def test_convert_control_rating_na_maps_to_none():
    # "not applicable"/"n/a" are explicit null entries in control_rating_map.
    assert convert_control_rating("Not Applicable") is None
    assert convert_control_rating("N/A") is None
    assert convert_control_rating(None) is None


# --- parse_rationale_for_dimensions: separator forms -----------------------------

@pytest.mark.parametrize("text,expected", [
    ("Likelihood is high.", {"likelihood": 3}),
    ("likelihood: medium", {"likelihood": 2}),
    ("likelihood(high)", {"likelihood": 3}),
    ("likelihood - low", {"likelihood": 1}),
    ("likelihood = critical", {"likelihood": 4}),
    ("likelihood rating: high", {"likelihood": 3}),
    ("likelihood is rated medium", {"likelihood": 2}),
])
def test_likelihood_separator_forms(text, expected):
    assert parse_rationale_for_dimensions(text) == expected


def test_generic_impact_separator_form():
    assert parse_rationale_for_dimensions("Impact: medium") == {"impact": 2}


def test_combined_likelihood_and_impact():
    assert parse_rationale_for_dimensions(
        "Likelihood is high. Impact: medium."
    ) == {"likelihood": 3, "impact": 2}


# --- "the likelihood of X is high" (words in between) ------------------------------

def test_likelihood_with_intervening_words():
    assert parse_rationale_for_dimensions(
        "the likelihood of a loss event is high"
    ) == {"likelihood": 3}


# --- "high likelihood" (rating-first form) -------------------------------------------

def test_rating_first_form():
    assert parse_rationale_for_dimensions(
        "high likelihood of failure") == {"likelihood": 3}


# --- abbreviations L: / I: -------------------------------------------------------

def test_abbreviations_do_not_parse_today():
    # CHARACTERIZATION OF A QUIRK: the docstring claims "L: Low, I: High" is
    # handled, but the abbreviation regexes use uppercase \bL / \bI while the
    # text has already been lowercased — they can never match. Pinned as-is;
    # flagged in the test report.
    assert parse_rationale_for_dimensions("L: Low, I: High") == {}
    assert parse_rationale_for_dimensions("L-Low, I-Medium") == {}
    assert parse_rationale_for_dimensions("L=High") == {}


# --- per-impact-type splits ---------------------------------------------------------

def test_specific_impact_types():
    assert parse_rationale_for_dimensions(
        "financial impact is high; reputational impact: low"
    ) == {"impact": 3, "impact_financial": 3, "impact_reputational": 1}


def test_regulatory_impact_dash_form():
    assert parse_rationale_for_dimensions(
        "impact - regulatory: medium") == {"impact_regulatory": 2}


def test_consumer_impact_maps_to_consumer_harm_key():
    assert parse_rationale_for_dimensions(
        "consumer impact is critical") == {
            "impact": 4, "impact_consumer_harm": 4}


def test_rating_first_specific_impact():
    # Rating-first form only matches the specific-impact pattern; the generic
    # "impact" pattern needs a separator or rating-adjacent form.
    assert parse_rationale_for_dimensions(
        "high financial impact expected") == {"impact_financial": 3}


def test_parenthesized_impact_type_does_not_parse_today():
    # CHARACTERIZATION OF A QUIRK: "impact (financial): high" matches none of
    # the three specific-impact patterns (the `[):]?` consumes only one of the
    # two closing characters). Pinned as-is.
    assert parse_rationale_for_dimensions("impact (financial): high") == {}


def test_generic_impact_also_set_by_specific_impact_phrase():
    # "financial impact is high" also satisfies the generic "impact is high"
    # pattern, so both keys are populated.
    found = parse_rationale_for_dimensions("financial impact is high")
    assert found == {"impact": 3, "impact_financial": 3}


# --- empty / no-mention input ---------------------------------------------------------

def test_empty_and_none_input():
    assert parse_rationale_for_dimensions("") == {}
    assert parse_rationale_for_dimensions(None) == {}


def test_text_without_dimension_mentions():
    assert parse_rationale_for_dimensions(
        "Strong governance and oversight in place.") == {}
