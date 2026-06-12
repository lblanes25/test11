"""Unit tests for mapping._deduplicate_transformed_rows.

Characterization tests pinning all 6 documented dedup branches, the
evidence-merge shapes ("Finding detail:" / "(also: Findings)") from
branches 3/4, and the "(dedup: kept higher)" method annotation from
branches 5/6.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from risk_taxonomy_transformer.constants import Method
from risk_taxonomy_transformer.mapping import _deduplicate_transformed_rows
from risk_taxonomy_transformer.rating import _make_row


ENTITY = "AE-TEST"


def _row(l2="Data", *, method, likelihood=None, pillar="Operational",
         evidence=""):
    return _make_row(
        ENTITY, "Operational and Compliance", l2,
        likelihood=likelihood,
        source_legacy_pillar=pillar,
        method=method,
        key_risk_evidence=evidence,
    )


def test_no_collision_keeps_both_rows():
    rows = [
        _row("Data", method=Method.DIRECT, likelihood=3),
        _row("Commercial", method=Method.DIRECT, likelihood=2, pillar="Credit"),
    ]
    out = _deduplicate_transformed_rows(list(rows), ENTITY)
    assert out == rows


# --- Branch 1: new issue_confirmed replaces blank-method placeholder ---------

def test_branch1_issue_confirmed_replaces_blank_placeholder():
    placeholder = _row(method=Method.EVALUATED_NO_EVIDENCE,
                       evidence="siblings_with_evidence: Commercial")
    confirmed = _row(method=Method.ISSUE_CONFIRMED, pillar="Findings",
                     evidence="F-1: Bad thing (High, Open)")
    out = _deduplicate_transformed_rows([placeholder, confirmed], ENTITY)
    assert len(out) == 1
    assert out[0] is confirmed
    assert out[0]["method"] == Method.ISSUE_CONFIRMED
    assert out[0]["source_legacy_pillar"] == "Findings"


# --- Branch 2: blank-method placeholder never displaces issue_confirmed ------

def test_branch2_blank_placeholder_does_not_displace_issue_confirmed():
    confirmed = _row(method=Method.ISSUE_CONFIRMED, pillar="Findings",
                     evidence="F-1: Bad thing (High, Open)")
    placeholder = _row(method=Method.NO_EVIDENCE_ALL_CANDIDATES)
    out = _deduplicate_transformed_rows([confirmed, placeholder], ENTITY)
    assert len(out) == 1
    assert out[0] is confirmed
    assert out[0]["method"] == Method.ISSUE_CONFIRMED
    # Branch 2 is a pure keep: no annotation of any kind.
    assert out[0]["source_legacy_pillar"] == "Findings"
    assert out[0]["key_risk_evidence"] == "F-1: Bad thing (High, Open)"


# --- Branch 3: existing issue_confirmed + new rated row ----------------------

def test_branch3_rated_row_wins_and_appends_finding_detail():
    confirmed = _row(method=Method.ISSUE_CONFIRMED, pillar="Findings",
                     evidence="F-1: Bad thing (High, Open)")
    rated = _row(method=Method.DIRECT, likelihood=3, pillar="Operational",
                 evidence="rationale: data governance")
    out = _deduplicate_transformed_rows([confirmed, rated], ENTITY)
    assert len(out) == 1
    assert out[0] is rated
    assert out[0]["key_risk_evidence"] == (
        "rationale: data governance\nFinding detail: F-1: Bad thing (High, Open)"
    )
    assert out[0]["source_legacy_pillar"] == "Operational (also: Findings)"
    # Branches 3/4 do NOT annotate the method (no "(dedup: ...)" suffix).
    assert out[0]["method"] == Method.DIRECT


def test_branch3_no_keyword_evidence_keeps_finding_detail_only():
    confirmed = _row(method=Method.ISSUE_CONFIRMED, pillar="Findings",
                     evidence="F-1: Bad thing (High, Open)")
    rated = _row(method=Method.DIRECT, likelihood=3, evidence="")
    out = _deduplicate_transformed_rows([confirmed, rated], ENTITY)
    assert out[0]["key_risk_evidence"] == \
        "Finding detail: F-1: Bad thing (High, Open)"


def test_branch3_strips_preexisting_finding_detail_prefix():
    # An issue_confirmed row that already carries a "Finding detail:" prefix
    # (e.g. from a prior merge) is not double-prefixed.
    confirmed = _row(method=Method.ISSUE_CONFIRMED, pillar="Findings",
                     evidence="Finding detail: F-1: Bad thing (High, Open)")
    rated = _row(method=Method.DIRECT, likelihood=2,
                 evidence="rationale: pii")
    out = _deduplicate_transformed_rows([confirmed, rated], ENTITY)
    assert out[0]["key_risk_evidence"] == (
        "rationale: pii\nFinding detail: F-1: Bad thing (High, Open)"
    )


def test_branch3_empty_finding_evidence_keeps_keyword_evidence():
    confirmed = _row(method=Method.ISSUE_CONFIRMED, pillar="Findings",
                     evidence="")
    rated = _row(method=Method.DIRECT, likelihood=3,
                 evidence="rationale: pii")
    out = _deduplicate_transformed_rows([confirmed, rated], ENTITY)
    assert out[0]["key_risk_evidence"] == "rationale: pii"
    # The "(also: Findings)" pillar annotation still applies.
    assert out[0]["source_legacy_pillar"] == "Operational (also: Findings)"


# --- Branch 4: new issue_confirmed + existing rated row ----------------------

def test_branch4_existing_rated_row_kept_and_appends_finding_detail():
    rated = _row(method="evidence_match (primary)", likelihood=2,
                 pillar="Operational", evidence="rationale: data quality")
    confirmed = _row(method=Method.ISSUE_CONFIRMED, pillar="Findings",
                     evidence="F-2: Other thing (Medium, Open)")
    out = _deduplicate_transformed_rows([rated, confirmed], ENTITY)
    assert len(out) == 1
    assert out[0] is rated
    assert out[0]["key_risk_evidence"] == (
        "rationale: data quality\nFinding detail: F-2: Other thing (Medium, Open)"
    )
    assert out[0]["source_legacy_pillar"] == "Operational (also: Findings)"
    assert out[0]["method"] == "evidence_match (primary)"


def test_branch4_existing_without_keyword_evidence():
    rated = _row(method=Method.DIRECT, likelihood=2, evidence="")
    confirmed = _row(method=Method.ISSUE_CONFIRMED, pillar="Findings",
                     evidence="F-2: Other thing (Medium, Open)")
    out = _deduplicate_transformed_rows([rated, confirmed], ENTITY)
    assert out[0]["key_risk_evidence"] == \
        "Finding detail: F-2: Other thing (Medium, Open)"


# --- Branch 5: both rated, new is higher --------------------------------------

def test_branch5_higher_new_rating_wins_with_annotations():
    lower = _row(method=Method.DIRECT, likelihood=2, pillar="Credit")
    higher = _row(method="evidence_match (primary)", likelihood=3,
                  pillar="Operational")
    out = _deduplicate_transformed_rows([lower, higher], ENTITY)
    assert len(out) == 1
    assert out[0] is higher
    assert out[0]["likelihood"] == 3
    assert out[0]["source_legacy_pillar"] == "Operational (also: Credit)"
    assert out[0]["method"] == "evidence_match (primary) (dedup: kept higher)"


# --- Branch 6: both rated, existing equal or higher ----------------------------

def test_branch6_existing_higher_rating_kept_with_annotations():
    higher = _row(method=Method.DIRECT, likelihood=4, pillar="Operational")
    lower = _row(method="evidence_match (primary)", likelihood=2,
                 pillar="Credit")
    out = _deduplicate_transformed_rows([higher, lower], ENTITY)
    assert len(out) == 1
    assert out[0] is higher
    assert out[0]["likelihood"] == 4
    assert out[0]["source_legacy_pillar"] == "Operational (also: Credit)"
    assert out[0]["method"] == "direct (dedup: kept higher)"


def test_branch6_equal_ratings_keep_existing():
    first = _row(method=Method.DIRECT, likelihood=2, pillar="Operational")
    second = _row(method=Method.DIRECT, likelihood=2, pillar="Credit")
    out = _deduplicate_transformed_rows([first, second], ENTITY)
    assert len(out) == 1
    assert out[0] is first
    assert out[0]["source_legacy_pillar"] == "Operational (also: Credit)"
    assert out[0]["method"] == "direct (dedup: kept higher)"


def test_branch6_method_not_reannotated_on_second_dedup():
    first = _row(method=Method.DIRECT, likelihood=3, pillar="Operational")
    second = _row(method=Method.DIRECT, likelihood=2, pillar="Credit")
    third = _row(method=Method.DIRECT, likelihood=1, pillar="Market")
    out = _deduplicate_transformed_rows([first, second, third], ENTITY)
    assert len(out) == 1
    # Pillar attribution accumulates; the dedup suffix is applied only once.
    assert out[0]["source_legacy_pillar"] == \
        "Operational (also: Credit) (also: Market)"
    assert out[0]["method"] == "direct (dedup: kept higher)"
