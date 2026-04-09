"""
Review dataframe builders for the Risk Taxonomy Transformer.

Builds the Audit Review, Review Queue, Risk Owner Review, and Risk Owner
Summary dataframes used in the Excel output.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from risk_taxonomy_transformer.config import L2_TO_L1, NEW_TAXONOMY, get_config
from risk_taxonomy_transformer.constants import Status, _clean_str
from risk_taxonomy_transformer.enrichment import _derive_decision_basis, _derive_status

logger = logging.getLogger(__name__)


_L2_SHORT_DISPLAY = {
    "Information and Cyber Security": "InfoSec",
    "Processing, Execution and Change": "Proc/Exec",
    "Customer / client protection and product compliance": "Customer Protection",
    "Prudential & bank administration compliance": "Prudential Compliance",
    "Fraud (External and Internal)": "Fraud",
    "Consumer and Small Business": "Consumer/SMB",
    "Financial Reporting": "Fin. Reporting",
    "Financial crimes": "Fin. Crimes",
    "FX and Price": "FX/Price",
    "Interest Rate": "Interest Rate",
    "Human Capital": "Human Capital",
    "Third Party": "Third Party",
    "Technology": "Technology",
    "Privacy": "Privacy",
    "Data": "Data",
    "Legal": "Legal",
    "Conduct": "Conduct",
    "Earnings": "Earnings",
    "Capital": "Capital",
    "Funding & Liquidity": "Funding/Liquidity",
    "Country": "Country",
    "Model": "Model",
    "Reputational": "Reputational",
}


# ---------------------------------------------------------------------------
# Helpers promoted to module-level (Phase 5)
# ---------------------------------------------------------------------------

def _split_signals(val) -> tuple[str, str]:
    """Split an Additional Signals value into (control_signals, other_signals)."""
    if pd.isna(val) or str(val).strip().lower() in ("", "nan"):
        return "", ""
    parts = str(val).split(" | ")
    control = []
    other = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if "well controlled" in p.lower():
            control.append(p)
        else:
            other.append(p)
    return " | ".join(control), " | ".join(other)


def _row_sort_key(row) -> int:
    """Compute a sort key for ordering rows within an entity in Audit Review."""
    status = row.get("Proposed Status", "")
    rating = row.get("Proposed Rating", "")
    has_signals = not pd.isna(row.get("Control Signals", "")) and str(row.get("Control Signals", "")).strip() not in ("", "nan")

    if status == Status.UNDETERMINED:
        return 0
    if has_signals and status not in (Status.NOT_APPLICABLE, Status.NOT_ASSESSED):
        return 1
    if status == Status.NO_EVIDENCE:
        return 2
    if status == Status.APPLICABLE and rating in ("High", "Critical"):
        return 3
    if status == Status.APPLICABLE:
        return 4
    if status == Status.NOT_APPLICABLE:
        return 5
    if status == Status.NOT_ASSESSED:
        return 6
    return 7


def _parse_keyword_hits(sub_risk_evidence: str, method: str) -> str:
    """Extract keyword portions from sub_risk_evidence for the Keyword Hits column."""
    if not sub_risk_evidence or sub_risk_evidence == "nan":
        return ""
    if sub_risk_evidence.startswith("siblings_with_evidence:"):
        return ""
    if "issue_confirmed" in str(method):
        return ""
    keywords = []
    for part in sub_risk_evidence.split("; "):
        part = part.strip()
        if not part:
            continue
        # "sub-risk KR-123 [desc...]: kw1, kw2" -> extract after ":"
        # "rationale: kw1, kw2" -> extract after ":"
        if ": " in part:
            kw_part = part.split(": ", 1)[1]
            keywords.append(kw_part)
        else:
            keywords.append(part)
    return ", ".join(keywords) if keywords else ""


def _parse_sub_risk_ids(sub_risk_evidence: str, method: str) -> str:
    """Extract sub-risk IDs (e.g. KR-123) from sub_risk_evidence."""
    if not sub_risk_evidence or sub_risk_evidence == "nan":
        return ""
    if sub_risk_evidence.startswith("siblings_with_evidence:"):
        return ""
    if "issue_confirmed" in str(method):
        return ""
    ids = []
    for part in sub_risk_evidence.split("; "):
        part = part.strip()
        if part.startswith("sub-risk "):
            # "sub-risk KR-123 [desc...]: kw1, kw2"
            id_part = part.replace("sub-risk ", "").split(" [")[0].strip()
            if id_part:
                ids.append(id_part)
    return ", ".join(ids) if ids else ""


def _format_finding_reference(findings_index: dict | None, entity_id: str,
                              l2: str) -> str:
    """Format finding references for an entity + L2 from findings_index."""
    if not findings_index:
        return ""
    entity_findings = findings_index.get(entity_id, {})
    l2_findings = entity_findings.get(l2, [])
    if not l2_findings:
        return ""
    refs = []
    for f in l2_findings[:3]:
        issue_id = f.get("issue_id", "")
        severity = f.get("severity", "")
        status = f.get("status", "")
        refs.append(f"{issue_id} ({severity}, {status})")
    return "; ".join(refs)


def _compute_priority_score(status: str, confidence: str, rating: str,
                            sibling_alert: str, has_any_signal: bool) -> int:
    """Compute review priority score per the RCO priority scoring spec."""
    na_adjacent = status in (
        Status.NOT_APPLICABLE, Status.NO_EVIDENCE, Status.NOT_ASSESSED
    )
    # 100: N/A-adjacent with any signal
    if na_adjacent and has_any_signal:
        return 100
    # 95: sibling alert populated (N/A-adjacent implied by alert logic)
    if sibling_alert:
        return 95
    # 90: Undetermined
    if status == Status.UNDETERMINED:
        return 90
    # 80: Applicable with low/medium confidence
    if status == Status.APPLICABLE and str(confidence).lower() in ("medium", "low"):
        return 80
    # 70: Assumed N/A with no signals
    if status == Status.NO_EVIDENCE and not has_any_signal:
        return 70
    # 60: No Legacy Source
    if status == Status.NOT_ASSESSED:
        return 60
    # 50: Applicable High/Critical
    if status == Status.APPLICABLE and str(rating) in ("High", "Critical"):
        return 50
    # 40: Applicable Low/Medium
    if status == Status.APPLICABLE and str(rating) in ("Low", "Medium"):
        return 40
    # 20: Not Applicable with no signals
    if status == Status.NOT_APPLICABLE and not has_any_signal:
        return 20
    return 10


def _compute_sibling_context(
    l2: str,
    l1: str,
    entity_id: str,
    status: str,
    entity_l2_lookup: dict,
) -> tuple[str, str]:
    """Compute sibling summary and sibling alert for a row.

    Returns:
        (sibling_summary, sibling_alert)
    """
    parent_l1 = L2_TO_L1.get(l2, l1)
    sibling_l2s = [s for s in NEW_TAXONOMY.get(parent_l1, []) if s != l2]
    rating_rank = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}

    if not sibling_l2s:
        return "Only L2 under this L1", ""

    # Collect only Applicable siblings with (rank, short_name, rating, source)
    applicable_siblings = []
    alert_candidate = None

    for sib in sibling_l2s:
        sib_info = entity_l2_lookup.get(entity_id, {}).get(sib)
        if not sib_info:
            continue
        sib_status = sib_info["status"]
        sib_rating = _clean_str(sib_info["rating"])
        sib_source = sib_info["source"]

        # Only include Applicable siblings in summary
        if sib_status == Status.APPLICABLE:
            short = _L2_SHORT_DISPLAY.get(sib, sib)
            rank = rating_rank.get(sib_rating, 0)
            applicable_siblings.append((rank, short, sib_rating, sib_source))

        # Sibling alert: sibling Applicable High/Critical, this row N/A-adjacent
        if (sib_status == Status.APPLICABLE
                and sib_rating in ("High", "Critical")
                and status in (Status.NOT_APPLICABLE,
                               Status.NO_EVIDENCE,
                               Status.NOT_ASSESSED)):
            rank = rating_rank.get(sib_rating, 0)
            if alert_candidate is None or rank > alert_candidate[0]:
                alert_candidate = (rank, sib, sib_rating, sib_source)

    # Sort by rating descending, limit to 6
    applicable_siblings.sort(key=lambda x: x[0], reverse=True)
    overflow = max(0, len(applicable_siblings) - 6)
    display_siblings = applicable_siblings[:6]

    if display_siblings:
        parts = []
        for _, short, sib_r, src in display_siblings:
            tag = " \u2713RCO" if src == "rco_override" else ""
            parts.append(f"{short} ({sib_r}){tag}" if sib_r else short)
        sibling_summary = " | ".join(parts)
        if overflow:
            sibling_summary += f" +{overflow} more"
    else:
        sibling_summary = "None applicable"

    if alert_candidate:
        _, alert_l2, alert_rating, alert_source = alert_candidate
        validated = " (RCO-validated)" if alert_source == "rco_override" else ""
        sibling_alert = (f"\u26a0 {alert_l2} is {alert_rating}{validated} "
                         f"but this L2 is {status}")
    else:
        sibling_alert = ""

    return sibling_summary, sibling_alert


def _format_business_line_comparison(
    status: str,
    rating: str,
    bl: str,
    l2: str,
    has_pga: bool,
    peer_ratings: dict,
) -> str:
    """Format the Business Line Comparison string for a row.

    Args:
        status: The row's proposed status
        rating: The row's proposed rating label
        bl: The entity's business line
        l2: The L2 risk name
        has_pga: Whether PGA column exists in legacy data
        peer_ratings: {(business_line, l2): Counter of ratings}
    """
    if not has_pga or not bl:
        return "Business line data not available"

    peer_counter = peer_ratings.get((bl, l2))
    if not peer_counter or sum(peer_counter.values()) < 3:
        return "Fewer than 3 entities in this business line \u2014 no comparison available"

    total_peers = sum(peer_counter.values())
    modal_rating = peer_counter.most_common(1)[0][0]
    modal_count = peer_counter[modal_rating]
    bl_comparison = f"Most common rating in this business line: {modal_rating} ({modal_count} of {total_peers} entities)"
    if status == Status.APPLICABLE and rating and rating != modal_rating:
        bl_comparison += f". This entity is rated {rating}."
    return bl_comparison


# ---------------------------------------------------------------------------
# Audit Review
# ---------------------------------------------------------------------------

def _summarize_unmapped_findings(unmapped_findings: dict, entity_id: str) -> str:
    """Build a summary string for unmapped findings for a given entity.

    Returns e.g. "3 findings with unmappable categories (Compliance: 2, Liquidity: 1)"
    or "" if the entity has no unmapped findings.
    """
    items = unmapped_findings.get(entity_id, [])
    if not items:
        return ""
    category_counts: dict[str, int] = {}
    for item in items:
        raw = item.get("raw_l2", "")
        # Use the raw L2 value as the category label
        if raw and raw.lower() not in ("", "nan", "none"):
            category_counts[raw] = category_counts.get(raw, 0) + 1
        else:
            category_counts["(blank)"] = category_counts.get("(blank)", 0) + 1
    total = len(items)
    breakdown = ", ".join(f"{cat}: {ct}" for cat, ct in
                          sorted(category_counts.items(), key=lambda x: -x[1]))
    return f"{total} finding(s) with unmappable categories ({breakdown})"


def build_audit_review_df(transformed_df: pd.DataFrame,
                          legacy_df: pd.DataFrame = None,
                          entity_id_col: str = "Audit Entity",
                          unmapped_findings: dict | None = None) -> pd.DataFrame:
    """Build the auditor-facing Audit Review dataframe with plain-language columns."""
    _CFG = get_config()
    df = transformed_df.copy()

    # Join organizational metadata from legacy data if available
    _org = _CFG.get("columns", {}).get("org_metadata", {})
    org_cols = [
        _org.get("audit_leader", "Audit Leader"),
        _org.get("pga", "PGA/ASL"),
        _org.get("core_audit_team", "Core Audit Team"),
        _org.get("entity_name", "Audit Entity Name"),
        _org.get("entity_overview", "Audit Entity Overview"),
    ]
    if legacy_df is not None:
        available_org = [c for c in org_cols if c in legacy_df.columns]
        if available_org and entity_id_col in legacy_df.columns:
            org_data = legacy_df[[entity_id_col] + available_org].copy()
            org_data = org_data.rename(columns={entity_id_col: "entity_id"})
            org_data["entity_id"] = org_data["entity_id"].astype(str).str.strip()
            df = df.merge(org_data, on="entity_id", how="left")

    df["Status"] = df["method"].apply(_derive_status)
    df["Decision Basis"] = df.apply(_derive_decision_basis, axis=1)

    # Rating Source column
    def derive_rating_source(row):
        has_ratings = row.get("likelihood") is not None and not pd.isna(row.get("likelihood", None))
        if not has_ratings:
            return "No ratings \u2014 legacy source was N/A or not assessed"

        parts = []
        if row.get("dims_parsed_from_rationale"):
            parts.append("Inherent Risk: Parsed from rationale \u2014 likelihood and impact stated separately")
        else:
            raw = row.get("source_risk_rating_raw", "")
            parts.append(f"Inherent Risk: Carried from legacy pillar rating {raw}")

        baseline = row.get("control_effectiveness_baseline", "")
        if baseline and str(baseline).strip().lower() not in ("", "nan", "none",
                                                               "no engagement rating available"):
            parts.append(f"Control: {baseline}")
        else:
            parts.append("Control: No engagement rating available")

        return " | ".join(parts)

    df["Rating Source"] = df.apply(derive_rating_source, axis=1)

    # Unmapped Findings — entity-level summary of findings that couldn't map to L2
    _unmapped = unmapped_findings or {}
    df["Unmapped Findings"] = df["entity_id"].apply(
        lambda eid: _summarize_unmapped_findings(_unmapped, str(eid).strip())
    )

    # Build Control Signals from control_flag, Additional Signals from the rest
    def _collect_flag(row, col):
        val = row.get(col, "")
        if pd.isna(val):
            return ""
        return str(val).strip()

    df["Control Signals"] = df.apply(lambda r: _collect_flag(r, "control_flag"), axis=1)

    def _collect_non_control_signals(row):
        prefixes = {
            "app_flag": "[App] ",
            "aux_flag": "[Aux] ",
            "cross_boundary_flag": "[Cross-boundary] ",
        }
        signals = []
        for col, prefix in prefixes.items():
            val = row.get(col, "")
            if pd.isna(val):
                continue
            val = str(val).strip()
            if val:
                signals.append(f"{prefix}{val}")
        return "\n".join(signals)

    df["Additional Signals"] = df.apply(_collect_non_control_signals, axis=1)

    # Add source rationale and control rationale from detail if available
    if "source_rationale" in df.columns:
        df["Source Rationale"] = df["source_rationale"].apply(
            lambda x: "" if pd.isna(x) or str(x).strip().lower() in ("", "nan") else str(x)
        )
    if "source_control_rationale" in df.columns:
        df["Source Control Rationale"] = df["source_control_rationale"].apply(
            lambda x: "" if pd.isna(x) or str(x).strip().lower() in ("", "nan") else str(x)
        )

    # Select and rename columns -- structured for reviewer workflow
    audit_cols = {
        # Entity context
        "entity_id": "Entity ID",
        _org.get("entity_name", "Audit Entity Name"): "Entity Name",
        _org.get("entity_overview", "Audit Entity Overview"): "Entity Overview",
        _org.get("audit_leader", "Audit Leader"): "Audit Leader",
        _org.get("pga", "PGA/ASL"): "PGA",
        _org.get("core_audit_team", "Core Audit Team"): "Core Audit Team",
        "Unmapped Findings": "Unmapped Findings",
        # Risk mapping
        "new_l1": "New L1",
        "new_l2": "New L2",
        # Tool proposals
        "Status": "Proposed Status",
        "inherent_risk_rating_label": "Proposed Rating",
        "confidence": "Confidence",
        "source_legacy_pillar": "Legacy Source",
        "Decision Basis": "Decision Basis",
        "Additional Signals": "Additional Signals",
        "Control Signals": "Control Signals",
        "Source Rationale": "Source Rationale",
        "Source Control Rationale": "Source Control Rationale",
        # Rating detail
        "likelihood": "Likelihood",
        "overall_impact": "Overall Impact",
        "impact_financial": "Impact - Financial",
        "impact_reputational": "Impact - Reputational",
        "impact_consumer_harm": "Impact - Consumer Harm",
        "impact_regulatory": "Impact - Regulatory",
        "control_effectiveness_baseline": "Control Effectiveness Baseline",
        "impact_of_issues": "Impact of Issues",
        "Rating Source": "Rating Source",
    }

    available = {k: v for k, v in audit_cols.items() if k in df.columns}
    result = df[list(available.keys())].copy()
    result.columns = list(available.values())

    # --- Clear Proposed Rating for non-direct mappings ---
    # Only carry forward legacy ratings when there is a clear 1:1 (direct) mapping.
    # All other rows get a blank rating so reviewers must actively assign one.
    if "Proposed Rating" in result.columns:
        is_direct = df["method"].astype(str).str.startswith("direct")
        non_direct_mask = ~is_direct
        # Save the legacy rating in Source Rating for reference
        result["Source Rating"] = ""
        result.loc[non_direct_mask, "Source Rating"] = result.loc[non_direct_mask, "Proposed Rating"]
        result.loc[non_direct_mask, "Proposed Rating"] = ""

    # Control Signals and Additional Signals are already built separately above

    # --- L2 Definition column (hidden, for reference) ---
    l2_def_file = Path(__file__).parent.parent / "data" / "input" / "L2_Risk_Taxonomy.xlsx"
    if l2_def_file.exists():
        l2_defs_df = pd.read_excel(l2_def_file)
        l2_def_map = dict(zip(l2_defs_df["L2"], l2_defs_df["L2 Definition"]))
        result["L2 Definition"] = result["New L2"].map(l2_def_map).fillna("")
    else:
        result["L2 Definition"] = ""

    # --- Reviewer columns ---
    # Reviewer Status is always empty — reviewers fill it in manually
    result["Reviewer Status"] = ""
    result["Reviewer Rating Override"] = ""
    result["Reviewer Notes"] = ""

    # --- Sort: entity-first, then within-entity priority ---
    result["_sort_key"] = result.apply(_row_sort_key, axis=1)

    # Sort by Audit Leader (if available) -> Entity ID -> within-entity priority
    sort_cols = []
    if "Audit Leader" in result.columns:
        sort_cols.append("Audit Leader")
    sort_cols.extend(["Entity ID", "_sort_key"])
    result = result.sort_values(sort_cols).drop(columns=["_sort_key"])

    # --- Final column order ---
    final_order = [
        # Entity context
        "Entity ID", "Entity Name", "Audit Leader", "PGA", "Core Audit Team", "Entity Overview",
        "Unmapped Findings",
        # Risk identity
        "New L1", "New L2",
        # Tool proposal
        "Proposed Status", "Proposed Rating", "Confidence", "Legacy Source", "Decision Basis",
        # Applicability signals
        "Additional Signals", "Source Rationale",
        # Control effectiveness
        "Control Signals", "Control Effectiveness Baseline", "Impact of Issues", "Source Control Rationale",
        # Rating detail (all grouped/hidden)
        "Rating Source", "Source Rating", "Likelihood", "Overall Impact",
        "Impact - Financial", "Impact - Reputational", "Impact - Consumer Harm", "Impact - Regulatory",
        # Reference (grouped/hidden)
        "L2 Definition",
        # Reviewer columns
        "Reviewer Status", "Reviewer Rating Override", "Reviewer Notes",
    ]
    # Only include columns that actually exist
    final_order = [c for c in final_order if c in result.columns]
    # Append any columns not in the order (safety net)
    remaining = [c for c in result.columns if c not in final_order]
    result = result[final_order + remaining]

    return result


# ---------------------------------------------------------------------------
# Review Queue
# ---------------------------------------------------------------------------

def build_review_queue_df(transformed_df: pd.DataFrame) -> pd.DataFrame:
    """Build redesigned Review Queue including both defaults and evaluated-no-evidence."""
    mask = transformed_df["method"].isin(["no_evidence_all_candidates", "evaluated_no_evidence"])
    df = transformed_df[mask].copy()

    if df.empty:
        return df

    # Review Type column
    def derive_review_type(method):
        if method == "no_evidence_all_candidates":
            return "Determine Applicability \u2014 all candidate L2s populated, team decides which apply"
        if method == "evaluated_no_evidence":
            return "Assumed N/A \u2014 verify whether this L2 is relevant"
        return ""

    df["Review Type"] = df["method"].apply(derive_review_type)

    df["Decision Basis"] = df.apply(_derive_decision_basis, axis=1)

    review_cols = [
        "entity_id", "Review Type", "new_l1", "new_l2", "Decision Basis",
        "source_legacy_pillar", "source_risk_rating_raw", "source_rationale",
        "sub_risk_evidence",
    ]
    available = [c for c in review_cols if c in df.columns]
    result = df[available].copy()

    col_rename = {
        "entity_id": "Entity ID", "new_l1": "New L1", "new_l2": "New L2",
        "source_legacy_pillar": "Legacy Source", "source_risk_rating_raw": "Source Rating",
        "source_rationale": "Source Rationale", "sub_risk_evidence": "Sub-Risk Evidence",
    }
    result = result.rename(columns=col_rename)

    # Sort: Determine Applicability first, then Confirm Not Applicable
    result = result.sort_values(["Review Type", "Entity ID"])

    return result


# ---------------------------------------------------------------------------
# Risk Owner Review
# ---------------------------------------------------------------------------

def build_risk_owner_review_df(
    transformed_df: pd.DataFrame,
    legacy_df: pd.DataFrame,
    entity_id_col: str,
    findings_index: dict | None = None,
    rco_overrides: dict | None = None,
) -> pd.DataFrame:
    """Build the Risk Owner Review dataframe with all entity x L2 rows,
    enriched with sibling context, false-negative flags, and peer comparison."""
    logger.info("Building Risk Owner Review dataframe")
    _CFG = get_config()

    # --- Pre-build entity metadata lookup ---
    _org_ro = _CFG.get("columns", {}).get("org_metadata", {})
    _pga_col = _org_ro.get("pga", "PGA/ASL")
    _name_col = _org_ro.get("entity_name", "Audit Entity Name")
    _overview_col = _org_ro.get("entity_overview", "Audit Entity Overview")
    _leader_col = _org_ro.get("audit_leader", "Audit Leader")
    has_pga = _pga_col in legacy_df.columns
    entity_meta = {}
    for _, row in legacy_df.iterrows():
        eid = str(row[entity_id_col]).strip()
        overview_raw = _clean_str(row.get(_overview_col, ""))
        entity_meta[eid] = {
            "name": _clean_str(row.get(_name_col, "")),
            "overview": overview_raw[:300] + ("..." if len(overview_raw) > 300 else ""),
            "leader": _clean_str(row.get(_leader_col, "")),
            "business_line": _clean_str(row.get(_pga_col, "")) if has_pga else "",
        }

    # --- Pre-build entity-L2 lookup for sibling computation ---
    entity_l2_lookup = defaultdict(dict)
    for _, row in transformed_df.iterrows():
        eid = str(row["entity_id"])
        l2 = row["new_l2"]
        entity_l2_lookup[eid][l2] = {
            "status": _derive_status(row["method"]),
            "rating": _clean_str(row.get("inherent_risk_rating_label", "")),
            "source": "tool",
        }
    # Overlay RCO overrides
    if rco_overrides:
        for (eid, l2), override in rco_overrides.items():
            entity_l2_lookup[eid][l2] = {
                "status": override["status"],
                "rating": override.get("rating") or "",
                "source": "rco_override",
            }

    # --- Pre-build peer group data ---
    # {(business_line, l2): Counter of ratings among Applicable entities}
    peer_ratings = defaultdict(Counter)
    if has_pga:
        for _, row in transformed_df.iterrows():
            eid = str(row["entity_id"])
            meta = entity_meta.get(eid, {})
            bl = meta.get("business_line", "")
            if not bl:
                continue
            status = _derive_status(row["method"])
            if status == Status.APPLICABLE:
                r = _clean_str(row.get("inherent_risk_rating_label", ""))
                if r:
                    peer_ratings[(bl, row["new_l2"])][r] += 1
    # Overlay RCO overrides into peer comparison
    if rco_overrides and has_pga:
        for (eid, l2), override in rco_overrides.items():
            if override["status"] == "Confirmed Applicable":
                bl = entity_meta.get(eid, {}).get("business_line", "")
                r = _clean_str(override.get("rating"))
                if bl and r:
                    peer_ratings[(bl, l2)][r] += 1

    # --- Build rows ---
    output_rows = []
    for _, row in transformed_df.iterrows():
        eid = str(row["entity_id"])
        l2 = row["new_l2"]
        l1 = row["new_l1"]
        method = _clean_str(row.get("method", ""))
        status = _derive_status(method)
        rating = _clean_str(row.get("inherent_risk_rating_label", ""))
        # Only carry forward ratings for direct 1:1 mappings
        if not method.startswith("direct"):
            rating = ""
        meta = entity_meta.get(eid, {})
        evidence = _clean_str(row.get("sub_risk_evidence", ""))

        # --- Sibling context (Phase 5 extraction) ---
        sibling_summary, sibling_alert = _compute_sibling_context(
            l2, l1, eid, status, entity_l2_lookup,
        )

        # --- Business Line Comparison (Phase 5 extraction) ---
        bl = meta.get("business_line", "")
        bl_comparison = _format_business_line_comparison(
            status, rating, bl, l2, has_pga, peer_ratings,
        )

        # --- Signal flags ---
        app_flag = _clean_str(row.get("app_flag", ""))
        aux_flag = _clean_str(row.get("aux_flag", ""))
        cross_flag = _clean_str(row.get("cross_boundary_flag", ""))
        control_flag = _clean_str(row.get("control_flag", ""))
        has_any_signal = bool(
            app_flag or aux_flag or cross_flag or control_flag or sibling_alert
        )

        # --- Priority score ---
        priority = _compute_priority_score(
            status, row.get("confidence", ""), rating, sibling_alert, has_any_signal
        )

        # --- Finding reference ---
        finding_ref = _format_finding_reference(findings_index, eid, l2)

        # --- Build output row ---
        rationale_raw = _clean_str(row.get("source_rationale", ""))
        rationale_excerpt = rationale_raw[:300] + ("..." if len(rationale_raw) > 300 else "")
        out = {
            # Entity context
            "Entity ID": eid,
            "Entity Name": meta.get("name", ""),
            "Entity Overview": meta.get("overview", ""),
            "Audit Leader": meta.get("leader", ""),
            "Business Line": bl,
            # Risk identity
            "L1": l1,
            "L2": l2,
            "Review Priority": priority,
            # Tool proposal
            "Proposed Status": status,
            "Proposed Rating": rating,
            "Confidence": _clean_str(row.get("confidence", "")),
            "Legacy Source": _clean_str(row.get("source_legacy_pillar", "")),
            "Legacy Pillar Rating": _clean_str(row.get("source_risk_rating_raw", "")),
            "Method": method,
            "Decision Basis": _derive_decision_basis(row),
            # Evidence
            "Keyword Hits": _parse_keyword_hits(evidence, method),
            "Sub-Risk IDs": _parse_sub_risk_ids(evidence, method),
            "Finding Reference": finding_ref,
            "Source Rationale Excerpt": rationale_excerpt,
            # Signals
            "Application Flag": app_flag,
            "Auxiliary Risk Flag": aux_flag,
            "Cross-Boundary Flag": cross_flag,
            "Control Flag": control_flag,
            # Sibling context
            "Applicable Siblings": sibling_summary,
            "Sibling Alert": sibling_alert,
            "Business Line Comparison": bl_comparison,
            # Rating detail (for grouping/hiding)
            "Likelihood": row.get("likelihood"),
            "Overall Impact": row.get("overall_impact"),
            "Impact - Financial": row.get("impact_financial"),
            "Impact - Reputational": row.get("impact_reputational"),
            "Impact - Consumer Harm": row.get("impact_consumer_harm"),
            "Impact - Regulatory": row.get("impact_regulatory"),
            "Control Effectiveness Baseline": _clean_str(row.get("control_effectiveness_baseline", "")),
            "Impact of Issues": _clean_str(row.get("impact_of_issues", "")),
            # RCO action columns
            "RCO Agrees": "",
            "RCO Recommended Status": "",
            "RCO Recommended Rating": "",
            "RCO Comment": "",
            # Internal (used for formatting, dropped before writing)
            "_priority": priority,
        }
        output_rows.append(out)

    result = pd.DataFrame(output_rows)

    # Sort: L2 ascending -> priority descending -> business line -> entity name
    result = result.sort_values(
        ["L2", "Review Priority", "Business Line", "Entity Name"],
        ascending=[True, False, True, True],
    )

    logger.info(f"  Risk Owner Review: {len(result)} rows, "
                f"{result['L2'].nunique()} unique L2s")
    return result


# ---------------------------------------------------------------------------
# Risk Owner Summary
# ---------------------------------------------------------------------------

def build_ro_summary_df(
    ro_review_df: pd.DataFrame,
    findings_index: dict | None = None,
) -> pd.DataFrame:
    """Build the Risk Owner Summary dataframe with one row per L2."""
    logger.info("Building Risk Owner Summary dataframe")

    summary_rows = []
    total_entities = ro_review_df["Entity ID"].nunique()

    # Get all L2s from taxonomy to ensure every L2 appears
    all_l2s = []
    for l1, l2_list in NEW_TAXONOMY.items():
        for l2 in l2_list:
            all_l2s.append((l1, l2))

    for l1, l2 in all_l2s:
        l2_rows = ro_review_df[ro_review_df["L2"] == l2]

        applicable = (l2_rows["Proposed Status"] == Status.APPLICABLE).sum()
        not_applicable = (l2_rows["Proposed Status"] == Status.NOT_APPLICABLE).sum()
        no_evidence = (l2_rows["Proposed Status"] == Status.NO_EVIDENCE).sum()
        undetermined = (l2_rows["Proposed Status"] == Status.UNDETERMINED).sum()
        not_assessed = (l2_rows["Proposed Status"] == Status.NOT_ASSESSED).sum()

        high_crit = l2_rows["Proposed Rating"].isin(["High", "Critical"]).sum()

        # Contradicted N/A: priority 100 rows
        contradicted = (l2_rows["_priority"] == 100).sum() if "_priority" in l2_rows.columns else 0

        sibling_alerts = l2_rows["Sibling Alert"].apply(
            lambda x: bool(x and str(x) not in ("", "nan"))
        ).sum()

        # Open findings
        open_findings_count = 0
        if findings_index:
            for eid in l2_rows["Entity ID"].unique():
                entity_findings = findings_index.get(eid, {})
                if l2 in entity_findings and len(entity_findings[l2]) > 0:
                    open_findings_count += 1

        # RCO reviews done
        rco_done = l2_rows["RCO Agrees"].apply(
            lambda x: bool(x and str(x).strip() not in ("", "nan"))
        ).sum()

        summary_rows.append({
            "L1": l1,
            "L2": l2,
            "Total Entities": total_entities,
            "Applicable": applicable,
            "Applicable %": applicable / total_entities if total_entities > 0 else 0,
            "Not Applicable": not_applicable,
            "Assumed N/A \u2014 Verify": no_evidence,
            "Undetermined": undetermined,
            "No Legacy Source": not_assessed,
            "High/Critical": high_crit,
            "Contradicted N/A": contradicted,
            "Sibling Alerts": sibling_alerts,
            "Open Findings": open_findings_count,
            "RCO Reviews Done": rco_done,
        })

    result = pd.DataFrame(summary_rows)
    result = result.sort_values(["L1", "L2"])
    logger.info(f"  Risk Owner Summary: {len(result)} L2 rows")
    return result
