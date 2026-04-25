"""
Enrichment functions for the Risk Taxonomy Transformer.

Derives inherent risk ratings, control effectiveness baselines,
status labels, and decision basis explanations for transformed rows.
"""

from __future__ import annotations

import logging

import pandas as pd

from risk_taxonomy_transformer.config import CROSSWALK_CONFIG
from risk_taxonomy_transformer.constants import Method, Status, _clean_str
from risk_taxonomy_transformer.utils import _format_date_month_year, _format_item_listings, _build_impact_summary

logger = logging.getLogger(__name__)

# Inherent Risk Rating matrix: (likelihood, overall_impact) -> rating
_RISK_MATRIX = {
    (1, 1): 1, (1, 2): 1, (1, 3): 2, (1, 4): 2,
    (2, 1): 1, (2, 2): 2, (2, 3): 2, (2, 4): 3,
    (3, 1): 2, (3, 2): 2, (3, 3): 3, (3, 4): 4,
    (4, 1): 2, (4, 2): 3, (4, 3): 4, (4, 4): 4,
}

_RATING_LABELS = {1: "Low", 2: "Medium", 3: "High", 4: "Critical"}


def derive_inherent_risk_rating(transformed_df: pd.DataFrame) -> pd.DataFrame:
    """Derive the composite Inherent Risk Rating from Likelihood x max(Impact dimensions).

    Adds columns: overall_impact, inherent_risk_rating, inherent_risk_rating_label.
    """
    impact_cols = ["impact_financial", "impact_reputational",
                   "impact_consumer_harm", "impact_regulatory"]

    def _compute(row):
        method = str(row.get("method", ""))

        # Source N/A rows get an explicit "N/A" label -- this is a real determination
        if Method.SOURCE_NOT_APPLICABLE in method:
            return None, None, "Not Applicable"

        likelihood = row.get("likelihood")
        if pd.isna(likelihood) or likelihood is None:
            return None, None, None

        impacts = [row.get(c) for c in impact_cols]
        valid_impacts = [int(v) for v in impacts if v is not None and not pd.isna(v)]
        if not valid_impacts:
            return None, None, None

        overall_impact = max(valid_impacts)
        rating = _RISK_MATRIX.get((int(likelihood), overall_impact))
        label = _RATING_LABELS.get(rating, "") if rating else None
        return overall_impact, rating, label

    results = transformed_df.apply(_compute, axis=1, result_type="expand")
    results.columns = ["overall_impact", "inherent_risk_rating", "inherent_risk_rating_label"]
    transformed_df = pd.concat([transformed_df, results], axis=1)

    rated = transformed_df["inherent_risk_rating"].notna().sum()
    logger.info(f"  Inherent Risk Rating derived for {rated} of {len(transformed_df)} rows")

    return transformed_df


def _format_baseline(audit_info: dict, baseline_map: dict) -> str:
    """Construct the Control Effectiveness Baseline string from audit metadata.

    Args:
        audit_info: dict with keys 'rating', 'date', 'next_date'
        baseline_map: {lowercase_rating: label} mapping
    """
    raw_rating = audit_info.get("rating", "")
    raw_date = audit_info.get("date", "")
    raw_next_date = audit_info.get("next_date", "")

    if raw_rating and raw_rating.lower() not in ("nan", "none", ""):
        baseline_label = baseline_map.get(raw_rating.lower(), raw_rating)
        last_display = _format_date_month_year(raw_date) or "date unknown"
        next_display = _format_date_month_year(raw_next_date) or "not scheduled"
        return (f"{baseline_label} (Last audit: {raw_rating}, "
                f"{last_display} \u00b7 Next planned: {next_display})")
    else:
        return "No engagement rating available"


def derive_control_effectiveness(
    transformed_df: pd.DataFrame,
    legacy_df: pd.DataFrame,
    entity_id_col: str,
    config: dict,
    findings_index: dict | None = None,
    ore_index: dict | None = None,
    enterprise_findings_index: dict | None = None,
    prsa_index: dict | None = None,
    rap_index: dict | None = None,
) -> pd.DataFrame:
    """Derive Control Effectiveness Baseline and Impact of Issues for each row.

    Populates two columns:
    - control_effectiveness_baseline: e.g. 'Well Controlled (Last audit: Satisfactory, June 2024 . Next planned: June 2026)'
    - impact_of_issues: item-level listings with IDs for traceability
    """
    logger.info("Deriving control effectiveness assessment")

    baseline_map = {k.lower(): v for k, v in
                    config.get("audit_rating_baseline_map", {}).items()}

    # Read column names from centralized config, fall back to legacy config
    col_cfg = config.get("columns", {}).get("control_effectiveness", {})
    if not col_cfg:
        ce_cols = config.get("control_effectiveness_columns", {})
        col_cfg = ce_cols
    rating_col = col_cfg.get("last_engagement_rating", "Last Engagement Rating")
    date_col = col_cfg.get("last_audit_completion_date", "Last Audit Completion Date")
    next_date_col = col_cfg.get("next_planned_audit_date", "Next Planned Audit Date")

    # Build entity metadata lookup for audit rating and dates
    entity_audit_info = {}
    for _, row in legacy_df.iterrows():
        eid = str(row[entity_id_col]).strip()
        raw_rating = str(row.get(rating_col, "") or "").strip()
        raw_date = row.get(date_col, "")
        raw_next_date = row.get(next_date_col, "")
        entity_audit_info[eid] = {
            "rating": raw_rating,
            "date": raw_date,
            "next_date": raw_next_date,
        }

    baselines = []
    impacts = []

    for _, row in transformed_df.iterrows():
        eid = str(row["entity_id"])
        l2 = row["new_l2"]

        # --- Control Effectiveness Baseline ---
        audit_info = entity_audit_info.get(eid, {})
        baselines.append(_format_baseline(audit_info, baseline_map))

        # --- Impact of Issues ---
        issue_parts = []

        # Audit findings
        findings = (findings_index or {}).get(eid, {}).get(l2, [])
        active_findings = [
            f for f in findings
            if str(f.get("status", "")).strip().lower()
            in ("open", "in validation", "in sustainability")
        ]
        issue_parts.append(_format_item_listings(
            active_findings, "audit findings",
            id_key="issue_id", title_key="issue_title",
            severity_key="severity", status_key="status",
        ))

        # OREs — classify open/closed by event_status, sort open first
        ores = (ore_index or {}).get(eid, {}).get(l2, [])
        _CLOSED_STATUSES = {"closed", "canceled", "draft canceled", "draft expired",
                            "draft", "pending cancelation by event admin"}
        def _ore_is_open(o):
            s = str(o.get("event_status", "")).strip().lower()
            return s not in _CLOSED_STATUSES if s else True  # unknown status treated as open
        ores_sorted = sorted(ores, key=lambda o: (0 if _ore_is_open(o) else 1))
        open_ores = [o for o in ores if _ore_is_open(o)]

        issue_parts.append(_format_item_listings(
            ores_sorted, "OREs",
            id_key="event_id", title_key="event_title",
            severity_key="event_classification", status_key="event_status",
        ))

        # Enterprise findings
        ent_findings = (enterprise_findings_index or {}).get(eid, {}).get(l2, [])
        issue_parts.append(_format_item_listings(
            ent_findings, "enterprise findings",
            id_key="finding_id", title_key="finding_title",
            severity_key="severity", status_key="status",
        ))

        # PRSA issues — exclude closed issues from active listing
        prsa_items = (prsa_index or {}).get(eid, {}).get(l2, [])
        _PRSA_CLOSED = {"closed", "canceled", "cancelled"}
        active_prsa = [
            p for p in prsa_items
            if str(p.get("issue_status", "")).strip().lower() not in _PRSA_CLOSED
        ]
        issue_parts.append(_format_item_listings(
            active_prsa, "PRSA issues",
            id_key="issue_id", title_key="issue_title",
            severity_key="issue_rating", status_key="issue_status",
        ))

        # GRA RAPs (regulatory findings)
        raps = (rap_index or {}).get(eid, {}).get(l2, [])
        issue_parts.append(_format_item_listings(
            raps, "regulatory findings",
            id_key="rap_id", title_key="rap_header",
            severity_key=None, status_key="rap_status",
        ))

        # Build final string
        all_empty = all("No " in p for p in issue_parts)
        if all_empty:
            impacts.append("No open items")
        else:
            real_parts = [p for p in issue_parts if not p.startswith("No ")]
            detail = "\n".join(real_parts)

            # Build summary line from raw item lists (only open OREs in summary)
            summary = _build_impact_summary([
                ("audit findings", active_findings, "severity"),
                ("OREs", open_ores, "event_classification"),
                ("enterprise findings", ent_findings, "severity"),
                ("PRSA issues", active_prsa, "issue_rating"),
                ("regulatory findings", raps, None),
            ])
            if summary:
                impacts.append(f"{summary}\n\n{detail}")
            else:
                impacts.append(detail)

    transformed_df["control_effectiveness_baseline"] = baselines
    transformed_df["impact_of_issues"] = impacts

    has_baseline = sum(1 for b in baselines if b != "No engagement rating available")
    has_items = sum(1 for i in impacts if i != "No open items")
    logger.info(f"  Control effectiveness: {has_baseline} rows with baseline, "
                f"{has_items} rows with open items")

    return transformed_df


def _derive_decision_basis(row) -> str:
    """Plain-language explanation of mapping method for a transformed row.

    Checks base method substrings before the dedup suffix so the explanation
    reflects the original method. If cross_boundary_flag evidence exists, it
    is appended to the primary basis so reviewers see the weak-applicability
    hint inline when they expand the cell.

    NOTE: The ordering of substring checks matters. More specific methods
    (e.g. "llm_confirmed_na") must be checked before less specific ones
    (e.g. "direct") to avoid false matches when a method string contains
    multiple substrings.
    """
    basis = _derive_decision_basis_primary(row)
    cbf = str(row.get("cross_boundary_flag", "") or "").strip()
    if cbf and cbf.lower() not in ("nan", "none"):
        basis = f"{basis}\n\nAlso: {cbf}"
    return basis


def _derive_decision_basis_primary(row) -> str:
    method = str(row.get("method", ""))
    pillar = str(row.get("source_legacy_pillar", "")).split(" (also")[0].strip()
    evidence = str(row.get("sub_risk_evidence", ""))
    rating = str(row.get("source_risk_rating_raw", ""))
    if rating in ("", "nan", "None"):
        rating = "unknown"
    if Method.LLM_CONFIRMED_NA in method:
        # Extract reasoning from sub_risk_evidence if present
        reasoning = ""
        if evidence.startswith("AI review: "):
            reasoning = evidence[len("AI review: "):]
        if reasoning:
            basis = (f"AI review confirmed this L2 is not applicable for the {pillar} pillar "
                     f"(rated {rating}). Basis: {reasoning}")
            return basis
        basis = (f"Proposed not applicable by AI review of the {pillar} pillar "
                 f"(rated {rating}) rationale and sub-risk descriptions.")
        return basis
    if Method.SOURCE_NOT_APPLICABLE in method:
        basis = (f"The legacy {pillar} pillar was rated Not Applicable for this entity, "
                 f"so this L2 risk is also marked as not applicable.")
        return basis
    if Method.EVALUATED_NO_EVIDENCE in method:
        # Extract sibling L2s from sub_risk_evidence if available
        siblings = ""
        if evidence and evidence.startswith("siblings_with_evidence:"):
            siblings = evidence.replace("siblings_with_evidence:", "").strip()
        if siblings:
            l2_name = str(row.get("new_l2", ""))
            basis = (f"The {pillar} pillar (rated {rating}) maps to multiple L2 risks. "
                     f"Other L2s from this pillar \u2014 {siblings} \u2014 had keyword matches in the "
                     f"rationale or sub-risk descriptions. This L2 ({l2_name}) did not.")
            return basis
        basis = (f"The {pillar} pillar (rated {rating}) rationale was reviewed for relevance to this L2 risk. "
                 f"No direct connection was found, so this L2 is marked as not applicable "
                 f"for this entity.")
        return basis
    if Method.NO_EVIDENCE_ALL_CANDIDATES in method:
        basis = (f"The {pillar} pillar (rated {rating}) covers multiple L2 risks. "
                 f"The rationale didn't clearly indicate which ones apply, so all candidates "
                 f"are shown with the original rating as a starting point.")
        return basis
    if Method.TRUE_GAP_FILL in method or "gap_fill" in method:
        return ("No legacy pillar maps to this L2 risk. This is a new risk category "
                "that will need to be assessed from scratch.")
    if Method.DIRECT in method:
        basis = (f"The legacy {pillar} pillar maps directly to this L2 risk. "
                 f"The original rating ({rating}) is carried forward as a starting point.")
        return basis
    if Method.ISSUE_CONFIRMED in method:
        basis = (f"Confirmed applicable based on an open finding tagged to this L2 risk. "
                 f"Finding detail: {evidence}")
        return basis
    if Method.EVIDENCE_MATCH in method:
        # Check if the source pillar is a multi-mapping with multiple targets
        clean_pillar = str(row.get("source_legacy_pillar", "")).split(" (also")[0].strip()
        pillar_cfg = CROSSWALK_CONFIG.get(clean_pillar, {})
        targets = pillar_cfg.get("targets", [])
        confidence = str(row.get("confidence", ""))

        groups = evidence.split("; ")
        formatted_evidence = "\n".join(f"  - {g}" for g in groups)

        if len(targets) > 1 and evidence:
            basis = (f"The {pillar} pillar (rated {rating}) maps to {len(targets)} candidate "
                     f"L2 risks. This L2 was matched with {confidence} confidence based on "
                     f"references in the rationale and sub-risk descriptions. "
                     f"Matched references:\n{formatted_evidence}")
            return basis
        if evidence:
            basis = (f"This L2 was mapped from the {pillar} pillar (rated {rating}) based on "
                     f"references found in the rationale and sub-risk descriptions. "
                     f"Matched references:\n{formatted_evidence}")
            return basis
        basis = (f"This L2 was mapped from the {pillar} pillar (rated {rating}) based on "
                 f"keyword evidence in the rationale text.")
        return basis
    if Method.LLM_OVERRIDE in method:
        # Extract reasoning from sub_risk_evidence if present
        reasoning = ""
        if evidence.startswith("AI review: "):
            reasoning = evidence[len("AI review: "):]
        if reasoning:
            basis = (f"AI review of the {pillar} pillar proposed this L2 as applicable. "
                     f"Basis: {reasoning}")
            return basis
        basis = (f"This L2 was classified based on an AI review of the {pillar} pillar "
                 f"rationale and sub-risk descriptions.")
        return basis
    return method


def _derive_status(method) -> str:
    """Map a mapping method string to a human-readable status.

    Checks base method substrings before the dedup suffix, so a deduped
    evaluated_no_evidence stays "Not Applicable" rather than flipping to "Applicable".
    """
    method = str(method)
    if Method.LLM_CONFIRMED_NA in method:
        return Status.NOT_APPLICABLE
    if Method.SOURCE_NOT_APPLICABLE in method:
        return Status.NOT_APPLICABLE
    if Method.EVALUATED_NO_EVIDENCE in method:
        return Status.NO_EVIDENCE
    if Method.NO_EVIDENCE_ALL_CANDIDATES in method:
        return Status.UNDETERMINED
    if Method.TRUE_GAP_FILL in method or "gap_fill" in method:
        return Status.NOT_ASSESSED
    if (Method.DIRECT in method or Method.EVIDENCE_MATCH in method
            or Method.LLM_OVERRIDE in method or Method.ISSUE_CONFIRMED in method
            or "dedup" in method):
        return Status.APPLICABLE
    return Status.NEEDS_REVIEW
