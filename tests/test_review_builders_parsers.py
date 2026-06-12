"""Unit tests for review_builders._parse_keyword_hits and _parse_key_risk_ids.

Characterization tests pinning current parsing behavior, including the
"Finding detail:" guards (dedup-appended tail and finding-prose-only
evidence -> blank Keyword Hits).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from risk_taxonomy_transformer.review_builders import (
    _parse_key_risk_ids,
    _parse_keyword_hits,
)


# --- _parse_keyword_hits ------------------------------------------------------

def test_rationale_keywords_extracted():
    assert _parse_keyword_hits(
        "rationale: data governance, data quality", "evidence_match (primary)"
    ) == "data governance, data quality"


def test_key_risk_keywords_extracted():
    assert _parse_keyword_hits(
        "key risk KR-1 [account data flows]: pii", "evidence_match (primary)"
    ) == "pii"


def test_mixed_rationale_and_key_risk_parts():
    assert _parse_keyword_hits(
        "rationale: data governance; key risk KR-2 [desc]: pii, data breach",
        "evidence_match (primary)",
    ) == "data governance, pii, data breach"


def test_empty_and_nan_evidence_return_blank():
    assert _parse_keyword_hits("", "direct") == ""
    assert _parse_keyword_hits("nan", "direct") == ""


def test_siblings_with_evidence_returns_blank():
    assert _parse_keyword_hits(
        "siblings_with_evidence: Data; Commercial", "evaluated_no_evidence"
    ) == ""


def test_issue_confirmed_method_returns_blank():
    assert _parse_keyword_hits(
        "F-1: Dual-control bypass (High, Open)", "issue_confirmed"
    ) == ""


def test_issue_confirmed_dedup_variant_also_blank():
    # Substring match on method: dedup-suffixed issue_confirmed still blanks.
    assert _parse_keyword_hits(
        "F-1: Dual-control bypass (High, Open)",
        "issue_confirmed (dedup: kept higher)",
    ) == ""


def test_dedup_appended_finding_detail_tail_dropped():
    assert _parse_keyword_hits(
        "rationale: pii\nFinding detail: F-1: Bad thing (High, Open)",
        "direct",
    ) == "pii"


def test_finding_detail_only_evidence_returns_blank():
    # The 1.2 fix: evidence that is ONLY dedup-merged finding prose must not
    # leak into Keyword Hits.
    assert _parse_keyword_hits(
        "Finding detail: F-1: Bad thing (High, Open)", "direct"
    ) == ""


def test_mid_list_finding_detail_part_stops_parsing():
    assert _parse_keyword_hits(
        "rationale: pii; Finding detail: F-1: Bad thing (High, Open)",
        "direct",
    ) == "pii"


def test_part_without_colon_kept_verbatim():
    assert _parse_keyword_hits("loose text", "direct") == "loose text"


# --- _parse_key_risk_ids --------------------------------------------------------

def test_key_risk_id_extracted_from_bracketed_form():
    assert _parse_key_risk_ids(
        "key risk KR-1 [account data flows]: pii", "evidence_match (primary)"
    ) == "KR-1"


def test_multiple_key_risk_ids():
    assert _parse_key_risk_ids(
        "rationale: pii; key risk KR-2 [d]: x; key risk KR-3 [d]: y",
        "evidence_match (primary)",
    ) == "KR-2, KR-3"


def test_rationale_only_evidence_yields_no_ids():
    assert _parse_key_risk_ids(
        "rationale: data governance", "evidence_match (primary)"
    ) == ""


def test_key_risk_ids_blank_for_issue_confirmed_and_siblings():
    assert _parse_key_risk_ids("key risk KR-1 [d]: x", "issue_confirmed") == ""
    assert _parse_key_risk_ids(
        "siblings_with_evidence: Data", "evaluated_no_evidence") == ""
    assert _parse_key_risk_ids("", "direct") == ""
    assert _parse_key_risk_ids("nan", "direct") == ""


def test_bracketless_key_risk_label_leaks_keywords_into_id():
    # CHARACTERIZATION OF A QUIRK: mapping.py currently emits bracket-less
    # labels ("key risk KR-1: pii" — the [desc] insert was dropped; the
    # `truncated` variable at mapping.py:121 is computed but unused). The
    # parser splits on " [" and therefore returns the whole "ID: keywords"
    # tail instead of just the ID. Pinned as-is; flagged in the test report.
    assert _parse_key_risk_ids(
        "key risk KR-1: pii", "evidence_match (primary)"
    ) == "KR-1: pii"
