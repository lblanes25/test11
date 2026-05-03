"""
Constants and sentinel helpers for the Risk Taxonomy Transformer.

Provides canonical status labels, mapping-method identifiers, blank-method
detection, and lightweight string-cleaning utilities used throughout the
package.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Status labels — used in _derive_status and review builders
# ---------------------------------------------------------------------------

class Status:
    """Human-readable status values assigned to transformed rows."""
    APPLICABLE = "Applicable"
    NOT_APPLICABLE = "Not Applicable"
    NO_EVIDENCE = "Assumed N/A \u2014 Verify"
    UNDETERMINED = "Applicability Undetermined"
    NOT_ASSESSED = "No Legacy Source"
    NEEDS_REVIEW = "Needs Review"


# ---------------------------------------------------------------------------
# Method identifiers — the technical codes stored in the ``method`` column
# ---------------------------------------------------------------------------

class Method:
    """Mapping-method codes recorded in the *method* column of transformed rows."""
    ISSUE_CONFIRMED = "issue_confirmed"
    EVALUATED_NO_EVIDENCE = "evaluated_no_evidence"
    NO_EVIDENCE_ALL_CANDIDATES = "no_evidence_all_candidates"
    TRUE_GAP_FILL = "true_gap_fill"
    SOURCE_NOT_APPLICABLE = "source_not_applicable"
    LLM_OVERRIDE = "llm_override"
    LLM_CONFIRMED_NA = "llm_confirmed_na"
    OPTRO_CONFIRMED = "optro_confirmed"
    OPTRO_CONFIRMED_NA = "optro_confirmed_na"
    DIRECT = "direct"
    EVIDENCE_MATCH = "evidence_match"


# Methods that represent unrated/placeholder rows -- overridden by rated or
# confirmed rows during dedup.
BLANK_METHODS = (
    Method.EVALUATED_NO_EVIDENCE,
    "gap_fill",
    Method.TRUE_GAP_FILL,
    Method.NO_EVIDENCE_ALL_CANDIDATES,
)

# Values considered semantically empty across the codebase.
EMPTY_SENTINELS = {"", "nan", "none", "nat"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_empty(val) -> bool:
    """Return True when *val* is None, NaN, or one of the empty sentinels."""
    if val is None:
        return True
    if isinstance(val, float):
        import math
        if math.isnan(val):
            return True
    return str(val).strip().lower() in EMPTY_SENTINELS


def _clean_str(val) -> str:
    """Convert value to string, replacing NaN/None/nan with empty string."""
    if val is None or (isinstance(val, float) and is_empty(val)):
        return ""
    s = str(val).strip()
    return "" if s.lower() in ("nan", "none", "") else s
