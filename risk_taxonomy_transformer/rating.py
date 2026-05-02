"""
Rating conversion and rationale parsing for the Risk Taxonomy Transformer.

Handles conversion of legacy risk/control ratings to numeric scales and
extraction of explicit likelihood/impact mentions from rationale text.
"""

from __future__ import annotations

import re

import pandas as pd

from risk_taxonomy_transformer.config import (
    RISK_RATING_MAP,
    CONTROL_RATING_MAP,
    RATING_WORDS,
)


def _make_row(
    entity_id: str, l1: str, l2: str, *,
    likelihood=None, impact_financial=None, impact_reputational=None,
    impact_consumer_harm=None, impact_regulatory=None,
    source_legacy_pillar=None, source_risk_rating_raw=None,
    source_rationale="", source_control_raw=None, source_control_rationale="",
    mapping_type="", confidence="", method="",
    dims_parsed_from_rationale=False, key_risk_evidence="", needs_review=False,
    # Control effectiveness -- populated by derive_control_effectiveness() post-pipeline
    control_effectiveness_baseline="", impact_of_issues="",
) -> dict:
    """Build a single transformed row dict with consistent keys."""
    return {
        "entity_id": entity_id,
        "new_l1": l1,
        "new_l2": l2,
        "composite_key": f"{l2} {entity_id}",
        "likelihood": likelihood,
        "impact_financial": impact_financial,
        "impact_reputational": impact_reputational,
        "impact_consumer_harm": impact_consumer_harm,
        "impact_regulatory": impact_regulatory,
        "control_effectiveness_baseline": control_effectiveness_baseline,
        "impact_of_issues": impact_of_issues,
        "source_legacy_pillar": source_legacy_pillar,
        "source_risk_rating_raw": source_risk_rating_raw,
        "source_rationale": source_rationale,
        "source_control_raw": source_control_raw,
        "source_control_rationale": source_control_rationale,
        "mapping_type": mapping_type,
        "confidence": confidence,
        "method": method,
        "dims_parsed_from_rationale": dims_parsed_from_rationale,
        "key_risk_evidence": key_risk_evidence,
        "needs_review": needs_review,
    }


def convert_risk_rating(value) -> int | None:
    """Convert legacy risk rating to 1-4 numeric scale."""
    if pd.isna(value):
        return None
    return RISK_RATING_MAP.get(str(value).strip().lower())


def convert_control_rating(value) -> int | None:
    """Convert legacy control assessment to 1-4 numeric scale."""
    if pd.isna(value):
        return None
    return CONTROL_RATING_MAP.get(str(value).strip().lower())


def parse_rationale_for_dimensions(rationale: str) -> dict:
    """Extract explicit likelihood/impact mentions from rationale text.

    Handles many free-text formats:
      "likelihood is high"           "impact: medium"
      "likelihood(high)"             "impact (medium)"
      "the likelihood is medium"     "impact is high because..."
      "L: Low, I: High"             "high likelihood"
      "likelihood - low"             "likelihood = critical"
      "likelihood rating: high"      "impact rating is medium"

    Returns dict with any found dimensions; empty dict if none found.
    """
    if not rationale or pd.isna(rationale):
        return {}

    text = str(rationale).lower()
    found = {}
    for dimension in ["likelihood", "impact"]:
        # Pattern 1: "dimension <separator> rating"
        # Handles: is, :, -, =, (, and optional words like "is rated", "rating:"
        match = re.search(
            rf"{dimension}\s*(?:rating\s*)?(?:is\s*(?:rated\s*)?|:|\u2013|-|=|\()\s*({RATING_WORDS})",
            text
        )
        if match:
            found[dimension] = RISK_RATING_MAP.get(match.group(1))
            continue

        # Pattern 2: "the dimension ... is/of rating" (words in between, up to 5)
        match = re.search(
            rf"(?:the\s+)?{dimension}\s+(?:\w+\s+){{0,5}}(?:is|of)\s+({RATING_WORDS})",
            text
        )
        if match:
            found[dimension] = RISK_RATING_MAP.get(match.group(1))
            continue

        # Pattern 3: "rating dimension" (e.g., "high likelihood")
        match = re.search(
            rf"({RATING_WORDS})\s+{dimension}",
            text
        )
        if match:
            found[dimension] = RISK_RATING_MAP.get(match.group(1))

    # Abbreviation patterns: "L: Low" / "I: High" / "L-Low, I-Medium"
    abbrev_match = re.search(
        rf"\bL\s*[:\-=]\s*({RATING_WORDS})", text
    )
    if abbrev_match and "likelihood" not in found:
        found["likelihood"] = RISK_RATING_MAP.get(abbrev_match.group(1))

    abbrev_match = re.search(
        rf"\bI\s*[:\-=]\s*({RATING_WORDS})", text
    )
    if abbrev_match and "impact" not in found:
        found["impact"] = RISK_RATING_MAP.get(abbrev_match.group(1))

    # Specific impact types: financial, reputational, regulatory, consumer
    # Map regex word -> output key (consumer matches text, but column is consumer_harm)
    impact_key_map = {
        "financial": "impact_financial",
        "reputational": "impact_reputational",
        "regulatory": "impact_regulatory",
        "consumer": "impact_consumer_harm",
    }
    for impact_type in impact_key_map:
        # "financial impact <sep> rating" or "impact <sep> financial <sep> rating"
        match = re.search(
            rf"{impact_type}\s+impact\s*(?:rating\s*)?(?:is\s*(?:rated\s*)?|:|\u2013|-|=|\()?\s*({RATING_WORDS})",
            text
        )
        if match:
            found[impact_key_map[impact_type]] = RISK_RATING_MAP.get(match.group(1))
            continue

        # "rating financial impact"
        match = re.search(
            rf"({RATING_WORDS})\s+{impact_type}\s+impact",
            text
        )
        if match:
            found[impact_key_map[impact_type]] = RISK_RATING_MAP.get(match.group(1))
            continue

        # "impact - financial: rating" or "impact (financial): rating"
        match = re.search(
            rf"impact\s*[\-(]\s*{impact_type}\s*[):]?\s*(?:is\s*)?({RATING_WORDS})" ,
            text
        )
        if match:
            found[impact_key_map[impact_type]] = RISK_RATING_MAP.get(match.group(1))

    return found
