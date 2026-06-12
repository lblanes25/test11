"""Unit tests for normalization.normalize_l2_name.

Characterization tests: pin the current resolution order (L1-prefix strip ->
unmappable check -> alias/exact lookup) against the live YAML config.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from risk_taxonomy_transformer.config import L2_TO_L1
from risk_taxonomy_transformer.normalization import normalize_l2_name


# --- Exact canonical match -------------------------------------------------

def test_exact_canonical_name_passes_through():
    assert normalize_l2_name("Data") == "Data"
    assert normalize_l2_name("Liquidity") == "Liquidity"


def test_exact_match_is_case_insensitive():
    assert normalize_l2_name("data") == "Data"
    assert normalize_l2_name("LIQUIDITY") == "Liquidity"


def test_every_canonical_l2_round_trips():
    for l2 in L2_TO_L1:
        assert normalize_l2_name(l2) == l2


# --- L1-prefix stripping ----------------------------------------------------

def test_l1_prefix_stripped_hyphen():
    assert normalize_l2_name("Operational - Data") == "Data"


def test_l1_prefix_stripped_en_dash():
    assert normalize_l2_name("Operational – Data") == "Data"


def test_l1_prefix_stripped_without_spaces():
    assert normalize_l2_name("Operational- Data") == "Data"


def test_compliance_prefix_stripped():
    assert normalize_l2_name(
        "Compliance - Financial crimes") == "Financial crimes"


def test_external_fraud_l3_names_not_treated_as_prefix():
    # "External Fraud" is not in the L1-prefix alternation; the full string
    # resolves via the alias map instead.
    assert normalize_l2_name(
        "External Fraud - First Party") == "External Fraud - First Party"
    assert normalize_l2_name(
        "External Fraud - Victim Third Party") == "External Fraud - Victim Fraud"


# --- YAML l2_aliases resolution ----------------------------------------------

def test_alias_resolution():
    assert normalize_l2_name("infosec") == "Information and Cyber Security"
    assert normalize_l2_name("cybersecurity") == "Information and Cyber Security"
    assert normalize_l2_name("financial crime") == "Financial crimes"


def test_alias_resolution_is_case_insensitive():
    assert normalize_l2_name("InfoSec") == "Information and Cyber Security"
    assert normalize_l2_name("Financial Crime") == "Financial crimes"


def test_prefix_strip_then_alias():
    # Prefix is stripped first, then the remainder resolves via alias.
    assert normalize_l2_name(
        "Operational - cyber security") == "Information and Cyber Security"


# --- l2_unmappable -> None ----------------------------------------------------

@pytest.mark.parametrize("raw", [
    "Operational", "Credit", "Market", "Compliance", "Strategic",
    "Reputational", "Reputation", "Country",
])
def test_unmappable_old_l1_names_return_none(raw):
    assert normalize_l2_name(raw) is None


def test_unmappable_is_case_insensitive():
    assert normalize_l2_name("OPERATIONAL") is None


def test_liquidity_is_not_unmappable():
    # Liquidity was removed from l2_unmappable because it is also a canonical
    # evaluated L2 — it must resolve, not drop.
    assert normalize_l2_name("Liquidity") == "Liquidity"


# --- whitespace / case / empty handling --------------------------------------

def test_surrounding_whitespace_stripped():
    assert normalize_l2_name("  Data  ") == "Data"


def test_empty_string_returns_none():
    assert normalize_l2_name("") is None


def test_whitespace_only_returns_none():
    assert normalize_l2_name("   ") is None


def test_nan_string_returns_none():
    assert normalize_l2_name("nan") is None
    assert normalize_l2_name("NaN") is None


def test_float_nan_returns_none():
    assert normalize_l2_name(float("nan")) is None


def test_unknown_value_returns_none():
    assert normalize_l2_name("Made Up Risk Category") is None
