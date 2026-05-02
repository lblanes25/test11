"""
Excel export for the Risk Taxonomy Transformer.

Writes the multi-sheet output workbook, enriches source tabs, and applies
all formatting via the formatting module.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import yaml
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill

from risk_taxonomy_transformer.config import KEYWORD_MAP, get_config
from risk_taxonomy_transformer.constants import Status
from risk_taxonomy_transformer.formatting import (
    _build_dashboard_sheet,
    _color_rows_by_column,
    _find_header_column,
    _format_audit_review_sheet,
    _format_risk_owner_review_sheet,
    _format_risk_owner_summary_sheet,
    style_header,
)
from risk_taxonomy_transformer.normalization import normalize_l2_name
from risk_taxonomy_transformer.review_builders import (
    build_audit_review_df,
    build_review_queue_df,
    build_risk_owner_review_df,
    build_ro_summary_df,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Source enrichment helpers
# ---------------------------------------------------------------------------

def _enrich_findings_source(
    findings_path: str,
    column_name_map: dict,
    transformed_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build an enriched findings source tab showing what each finding mapped to.

    Reads the raw findings file (before filtering) and annotates each row with:
    - Mapping Status: what happened to this finding (Included, Filtered, Closed)
    - Mapped L2(s): which L2 risk(s) this finding confirmed applicability for
    """
    if findings_path.endswith(".csv"):
        df = pd.read_csv(findings_path)
    else:
        df = pd.read_excel(findings_path)
    df.columns = [c.strip() for c in df.columns]

    # Rename to internal names for consistency
    rename = {}
    for internal, actual in column_name_map.items():
        if actual and actual in df.columns:
            rename[actual] = internal
    df = df.rename(columns=rename)
    df["entity_id"] = df["entity_id"].astype(str).str.strip()

    # Determine disposition for each row
    dispositions = []
    mapped_l2s_col = []

    # Build a set of (entity_id, l2) pairs that were issue_confirmed in the output
    confirmed = set()
    if transformed_df is not None:
        for _, row in transformed_df.iterrows():
            if "issue_confirmed" in str(row.get("method", "")):
                confirmed.add((str(row["entity_id"]), str(row["new_l2"])))

    # Active finding statuses -- only these are actionable
    _active_statuses = {"open", "in validation", "in sustainability"}

    for _, row in df.iterrows():
        # If finding is closed/inactive, suppress filter-reason noise
        status = str(row.get("status", row.get("Finding Status", ""))).strip()
        if status and status.lower() not in _active_statuses:
            dispositions.append("Closed")
            mapped_l2s_col.append("")
            continue

        # Check approval -- try internal name first (renamed), then original column name
        approval = str(row.get("approval_status", row.get("Finding Approval Status", ""))).strip()
        if approval and approval != "Approved":
            dispositions.append(f"Filtered \u2014 not approved ({approval})")
            mapped_l2s_col.append("")
            continue

        # Check severity
        sev = row.get("severity")
        if pd.isna(sev) or str(sev).strip() == "":
            dispositions.append("Filtered \u2014 blank severity")
            mapped_l2s_col.append("")
            continue

        # Check L2 mapping
        raw_l2 = str(row.get("l2_risk", ""))
        if not raw_l2 or raw_l2 == "nan":
            dispositions.append("Filtered \u2014 blank L2 risk category")
            mapped_l2s_col.append("")
            continue

        # Normalize and check each L2 value (could be multi-value)
        l2_parts = raw_l2.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        mapped = []
        unmapped = []
        for part in l2_parts:
            normalized = normalize_l2_name(part.strip())
            if normalized:
                eid = str(row["entity_id"])
                if (eid, normalized) in confirmed:
                    mapped.append(normalized)
                else:
                    mapped.append(f"{normalized} (not active/applicable)")
            elif part.strip():
                unmapped.append(part.strip())

        if mapped:
            dispositions.append("Included")
            mapped_l2s_col.append("; ".join(mapped))
        elif unmapped:
            dispositions.append(f"Filtered \u2014 unmappable L2 ({'; '.join(unmapped)})")
            mapped_l2s_col.append("")
        else:
            dispositions.append("Filtered \u2014 L2 not resolved")
            mapped_l2s_col.append("")

    df["Mapping Status"] = dispositions
    df["Mapped To L2(s)"] = mapped_l2s_col

    return df


_ACRONYM_DISPLAY = {
    "aml": "AML", "bcp": "BCP", "bsa": "BSA", "ccar": "CCAR", "ccpa": "CCPA",
    "cra": "CRA", "ddos": "DDoS", "dr": "DR", "fx": "FX", "gaap": "GAAP",
    "gdpr": "GDPR", "hr": "HR", "it": "IT", "kyc": "KYC", "mrm": "MRM",
    "nii": "NII", "ofac": "OFAC", "pii": "PII", "sar": "SAR", "sec": "SEC",
    "udaap": "UDAAP",
}


def _format_keyword_for_display(kw: str) -> str:
    tokens = kw.strip().split()
    return " ".join(_ACRONYM_DISPLAY.get(t.lower(), t) for t in tokens)


def _enrich_key_risks_source(
    key_risks_df: pd.DataFrame,
    transformed_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build an enriched key risks source tab showing what each key risk contributed to.

    Annotates each row with which L2(s) it provided keyword evidence for.
    """
    if key_risks_df is None or key_risks_df.empty:
        return pd.DataFrame()

    df = key_risks_df.copy()

    contributions = []
    for _, row in df.iterrows():
        eid = str(row.get("entity_id", ""))
        desc = str(row.get("risk_description", "")).lower()
        l1 = str(row.get("legacy_l1", ""))

        if not desc or desc == "nan":
            contributions.append("No description text")
            continue

        # Check which L2 keywords match this description
        matched_l2s = []
        for l2_name, keywords in KEYWORD_MAP.items():
            hits = [kw for kw in keywords if kw in desc]
            if hits:
                rendered = ", ".join(_format_keyword_for_display(h) for h in hits[:3])
                matched_l2s.append(f"{l2_name} ({rendered})")

        if matched_l2s:
            contributions.append("; ".join(matched_l2s))
        else:
            contributions.append("No keyword matches \u2014 did not contribute to any L2 mapping")

    df["L2 Keyword Matches"] = contributions

    return df


# ---------------------------------------------------------------------------
# Legacy ratings lookup builder
# ---------------------------------------------------------------------------

def _build_legacy_lookup(
    legacy_df: pd.DataFrame,
    pillar_columns: dict,
    entity_id_col: str,
) -> pd.DataFrame:
    """Unpivot legacy data into a clean lookup: one row per entity-pillar.

    Columns: Entity ID | Risk Pillar | Inherent Risk Rating |
             Inherent Risk Rationale | Control Assessment |
             Control Assessment Rationale
    """
    rows = []
    for _, entity_row in legacy_df.iterrows():
        eid = str(entity_row.get(entity_id_col, "")).strip()
        if not eid or eid == "nan":
            continue
        for pillar_name, cols in pillar_columns.items():
            rating = entity_row.get(cols["rating"], "")
            rationale = entity_row.get(cols.get("rationale") or "", "")
            control = entity_row.get(cols["control"], "")
            control_rationale = entity_row.get(cols.get("control_rationale") or "", "")
            # Convert NaN to empty string
            rating = "" if pd.isna(rating) else str(rating).strip()
            rationale = "" if pd.isna(rationale) else str(rationale).strip()
            control = "" if pd.isna(control) else str(control).strip()
            control_rationale = "" if pd.isna(control_rationale) else str(control_rationale).strip()
            rows.append({
                "Entity ID": eid,
                "Risk Pillar": pillar_name,
                "Inherent Risk Rating": rating,
                "Inherent Risk Rationale": rationale,
                "Control Assessment": control,
                "Control Assessment Rationale": control_rationale,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Methodology tab builder
# ---------------------------------------------------------------------------

def _build_methodology_data() -> list[list[str]]:
    """Load methodology content from YAML and convert to flat list-of-lists for Excel."""
    yaml_path = Path(__file__).parent / "methodology.yaml"
    with open(yaml_path, "r", encoding="utf-8") as f:
        content = yaml.safe_load(f)

    methodology_data = []
    for section in content["sections"]:
        title = section.get("title", "")
        header = section.get("header")
        rows = section.get("rows", [])

        methodology_data.append([title, ""])
        if header:
            methodology_data.append(header)
        for row in rows:
            methodology_data.append(row)
        methodology_data.append(["", ""])

    return methodology_data


# ---------------------------------------------------------------------------
# Main export function
# ---------------------------------------------------------------------------

def export_results(
    transformed_df: pd.DataFrame,
    legacy_df: pd.DataFrame,
    output_path: str,
    findings_df: pd.DataFrame = None,
    key_risks_df: pd.DataFrame = None,
    findings_path: str = None,
    findings_cols: dict = None,
    entity_id_col: str = "Audit Entity",
    findings_index: dict | None = None,
    rco_overrides: dict | None = None,
    ore_df: pd.DataFrame = None,
    pillar_columns: dict | None = None,
    prsa_df: pd.DataFrame = None,
    prsa_cols: dict | None = None,
    bma_df: pd.DataFrame = None,
    bma_cols: dict | None = None,
    gra_raps_df: pd.DataFrame = None,
    gra_raps_cols: dict | None = None,
    unmapped_findings: dict | None = None,
    unmapped_mapper_items: dict | None = None,
    key_inventory: dict | None = None,
):
    """Write multi-sheet Excel output."""
    logger.info(f"Writing output to {output_path}")

    # --- Audit Review (primary workspace) ---
    audit_df = build_audit_review_df(
        transformed_df, legacy_df, entity_id_col,
        unmapped_findings=unmapped_findings,
        unmapped_mapper_items=unmapped_mapper_items,
    )

    # --- Sheet 3: Review Queue (redesigned) ---
    review_df = build_review_queue_df(transformed_df)

    # --- Sheet 4: Side-by-side (debugging) ---
    trace_cols = [
        "composite_key", "entity_id", "new_l1", "new_l2",
        "inherent_risk_rating", "inherent_risk_rating_label", "overall_impact",
        "likelihood", "impact_financial", "impact_reputational",
        "impact_consumer_harm", "impact_regulatory",
        "control_effectiveness_baseline", "impact_of_issues",
        "source_legacy_pillar", "source_risk_rating_raw", "source_rationale",
        "source_control_raw", "source_control_rationale",
        "mapping_type", "confidence", "method",
        "dims_parsed_from_rationale", "key_risk_evidence", "needs_review",
        "control_flag", "app_flag", "tp_flag", "model_flag", "core_flag", "aux_flag", "cross_boundary_flag",
    ]
    available_trace_cols = [c for c in trace_cols if c in transformed_df.columns]
    trace_df = transformed_df[available_trace_cols].copy()

    # Build Methodology tab
    methodology_data = _build_methodology_data()
    methodology_df = pd.DataFrame(methodology_data, columns=["Topic", "Detail"])

    # Write sheets
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        # Visible tabs first
        audit_df.to_excel(writer, sheet_name="Audit_Review", index=False)
        methodology_df.to_excel(writer, sheet_name="Methodology", index=False, header=False)
        # Hidden tabs
        review_df.to_excel(writer, sheet_name="Review_Queue", index=False)
        trace_df.to_excel(writer, sheet_name="Side_by_Side", index=False)
        legacy_df.to_excel(writer, sheet_name="Source - Legacy Data", index=False)
        if findings_path and findings_cols:
            enriched_findings = _enrich_findings_source(
                findings_path, findings_cols, transformed_df)
            enriched_findings.to_excel(writer, sheet_name="Source - Findings", index=False)
        elif findings_df is not None and not findings_df.empty:
            findings_df.to_excel(writer, sheet_name="Source - Findings", index=False)
        if key_risks_df is not None and not key_risks_df.empty:
            enriched_key_risks = _enrich_key_risks_source(key_risks_df, transformed_df)
            enriched_key_risks.to_excel(writer, sheet_name="Source - Key Risks", index=False)
        if ore_df is not None and not ore_df.empty:
            # Rename internal lowercase columns back to user-friendly display names.
            # NB: ore_df is exploded one row per (ORE × L2). The original mapper
            # output already has a "Mapped L2s" column (semicolon-joined list of
            # all L2s for the ORE) — we rename the per-row exploded `l2_risk`
            # column to "Canonical L2" so it doesn't collide.
            _ore_cfg = get_config().get("columns", {}).get("ore_mappings", {})
            _ore_rename = {
                "event_id": _ore_cfg.get("event_id", "Event ID"),
                "entity_id": _ore_cfg.get("entity_id", "Audit Entity (Operational Risk Events)"),
                "l2_risk": "Canonical L2",
            }
            ore_out = ore_df.rename(columns={
                k: v for k, v in _ore_rename.items() if k in ore_df.columns
            })
            ore_out.to_excel(writer, sheet_name="Source - OREs", index=False)
        if prsa_df is not None and not prsa_df.empty:
            prsa_df.to_excel(writer, sheet_name="Source - PRSA Issues", index=False)
        if bma_df is not None and not bma_df.empty:
            bma_df.to_excel(writer, sheet_name="Source - BM Activities", index=False)
        if gra_raps_df is not None and not gra_raps_df.empty:
            gra_raps_df.to_excel(writer, sheet_name="Source - GRA RAPs", index=False)
        # Key Inventory (hidden) — per-entity "key" app/TP ID sets aggregated
        # from key risks. Non-key items do not drive risk per procedure;
        # HTML report reads this sheet to mark key IDs in drill-down and
        # Inventory views.
        if key_inventory:
            import json as _json
            ki_rows = []
            for eid, sets in key_inventory.items():
                apps_kpa = sets.get("key_apps_kpa", {})
                tps_kpa = sets.get("key_tps_kpa", {})
                # Serialize the per-ID KPA mapping as JSON so the HTML reader
                # can parse it. Sort KPA ids within each list for stable output.
                apps_kpa_json = _json.dumps(
                    {aid: sorted(k) for aid, k in apps_kpa.items()},
                    sort_keys=True,
                )
                tps_kpa_json = _json.dumps(
                    {tid: sorted(k) for tid, k in tps_kpa.items()},
                    sort_keys=True,
                )
                ki_rows.append({
                    "Entity ID": eid,
                    "Key Apps": "; ".join(sorted(sets.get("key_apps", set()))),
                    "Key TPs": "; ".join(sorted(sets.get("key_tps", set()))),
                    "Orphan Apps": "; ".join(sorted(sets.get("orphan_apps", set()))),
                    "Orphan TPs": "; ".join(sorted(sets.get("orphan_tps", set()))),
                    "Key Apps KPA JSON": apps_kpa_json,
                    "Key TPs KPA JSON": tps_kpa_json,
                })
            if ki_rows:
                ki_df = pd.DataFrame(ki_rows)
                ki_df.to_excel(writer, sheet_name="Key_Inventory", index=False)
        if pillar_columns:
            legacy_lookup = _build_legacy_lookup(legacy_df, pillar_columns, entity_id_col)
            legacy_lookup.to_excel(writer, sheet_name="Legacy Ratings Lookup", index=False)

        # --- Risk Owner Review tab ---
        ro_review_df = build_risk_owner_review_df(
            transformed_df, legacy_df, entity_id_col,
            findings_index=findings_index,
            rco_overrides=rco_overrides,
        )
        # Build summary before dropping internal columns (summary uses _priority)
        ro_summary_df = build_ro_summary_df(ro_review_df, findings_index=findings_index)
        # Drop internal columns before writing to Excel
        ro_review_clean = ro_review_df.drop(columns=[c for c in ro_review_df.columns if c.startswith("_")])
        ro_review_clean.to_excel(writer, sheet_name="Risk_Owner_Review", index=False)

        # --- Risk Owner Summary tab ---
        ro_summary_df.to_excel(writer, sheet_name="Risk_Owner_Summary", index=False)

    # Apply formatting
    wb = load_workbook(output_path)

    # Status color fills
    green_fill = PatternFill("solid", fgColor="C6EFCE")
    gray_fill = PatternFill("solid", fgColor="D9D9D9")
    yellow_fill = PatternFill("solid", fgColor="FFFF00")
    blue_fill = PatternFill("solid", fgColor="BDD7EE")
    orange_fill = PatternFill("solid", fgColor="FCE4D6")
    status_fills = {
        Status.APPLICABLE: green_fill,
        Status.NOT_APPLICABLE: gray_fill,
        Status.NO_EVIDENCE: orange_fill,
        Status.UNDETERMINED: yellow_fill,
        Status.NOT_ASSESSED: blue_fill,
    }

    review_type_fills = {
        "Determine Applicability": yellow_fill,
        "Assumed N/A": orange_fill,
    }

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        style_header(ws, ws.max_column)

        # Auto-width columns
        for col in ws.columns:
            max_len = 0
            col_letter = col[0].column_letter
            for cell in col:
                try:
                    if cell.value:
                        max_len = max(max_len, len(str(cell.value)))
                except (TypeError, ValueError):
                    pass
            # Cap wider for text-heavy columns
            cap = 60 if sheet_name in ("Review_Queue", "Audit_Review") else 40
            ws.column_dimensions[col_letter].width = min(max(max_len + 2, 12), cap)

        # Audit_Review -- full reviewer worksheet formatting
        if sheet_name == "Audit_Review":
            _format_audit_review_sheet(ws, status_fills)

        # Color-code Review_Queue by Review Type
        if sheet_name == "Review_Queue":
            col = _find_header_column(ws, "Review Type")
            if col:
                _color_rows_by_column(ws, col, review_type_fills, match_contains=True)

        # Highlight needs_review rows in yellow on Side_by_Side
        if sheet_name == "Side_by_Side":
            col = _find_header_column(ws, "needs_review")
            if col:
                _color_rows_by_column(ws, col, {True: yellow_fill})

    # Format Methodology tab
    if "Methodology" in wb.sheetnames:
        ws = wb["Methodology"]
        bold_font = Font(bold=True, size=11, name="Arial")
        title_font = Font(bold=True, size=14, name="Arial", color="2F5496")
        sub_header_font = Font(bold=True, size=10, name="Arial", color="2F5496")
        ws.column_dimensions["A"].width = 45
        ws.column_dimensions["B"].width = 120

        # Bold section headers and title
        section_headers = {
            "PURPOSE", "STATUS VALUES", "CONFIDENCE LEVELS",
            "EVIDENCE SOURCES (in priority order)", "ADDITIONAL SIGNALS COLUMN",
            "RATING SOURCE COLUMN", "CONTROL EFFECTIVENESS ASSESSMENT",
            "NOTE",
            "TABS IN THIS WORKBOOK",
            "FINDING FILTERS APPLIED", "DEDUPLICATION", "COMMON QUESTIONS",
            "RISK OWNER REVIEW \u2014 COLUMN GUIDE",
            "RISK OWNER REVIEW \u2014 HOW TO USE",
            "RISK OWNER REVIEW \u2014 PRIORITY SCORING",
        }
        sub_headers = {"Status", "Level", "Source", "Signal", "Value", "Tab", "Filter",
                       "Column", "Step", "Score", "Question", "Label"}

        for row in ws.iter_rows(min_row=1, max_row=ws.max_row):
            cell_val = str(row[0].value or "")
            if cell_val.startswith("Risk Taxonomy Transformer"):
                row[0].font = title_font
            elif cell_val in section_headers:
                row[0].font = bold_font
            elif cell_val in sub_headers:
                row[0].font = sub_header_font
                row[1].font = sub_header_font

    # --- Build Dashboard tab ---
    ar_ws = wb["Audit_Review"]
    _build_dashboard_sheet(wb, ar_ws)

    # --- Format Legacy Ratings Lookup tab ---
    if "Legacy Ratings Lookup" in wb.sheetnames:
        ll_ws = wb["Legacy Ratings Lookup"]
        style_header(ll_ws, ll_ws.max_column)
        ll_ws.column_dimensions["A"].width = 15   # Entity ID
        ll_ws.column_dimensions["B"].width = 25   # Risk Pillar
        ll_ws.column_dimensions["C"].width = 18   # Inherent Risk Rating
        ll_ws.column_dimensions["D"].width = 60   # Inherent Risk Rationale
        ll_ws.column_dimensions["E"].width = 20   # Control Assessment
        ll_ws.column_dimensions["F"].width = 60   # Control Assessment Rationale
        ll_ws.auto_filter.ref = ll_ws.dimensions

    # --- Format Risk_Owner_Review tab ---
    if "Risk_Owner_Review" in wb.sheetnames:
        _format_risk_owner_review_sheet(wb["Risk_Owner_Review"], status_fills)

    # --- Format Risk_Owner_Summary tab ---
    if "Risk_Owner_Summary" in wb.sheetnames:
        _format_risk_owner_summary_sheet(wb["Risk_Owner_Summary"])

    # --- Set tab visibility ---
    # Source tabs and Key_Inventory left visible so reviewers can trace
    # how findings, key risks, OREs, etc. flowed into Audit_Review.
    # Review_Queue and Side_by_Side stay hidden — Review_Queue is a filtered
    # subset of Audit_Review (the workspace), Side_by_Side is debug-only.
    hidden_tabs = ["Review_Queue", "Side_by_Side"]
    for tab_name in hidden_tabs:
        if tab_name in wb.sheetnames:
            wb[tab_name].sheet_state = "hidden"

    # --- Reorder tabs ---
    desired_order = [
        "Dashboard", "Audit_Review", "Legacy Ratings Lookup", "Methodology",
        "Risk_Owner_Summary", "Risk_Owner_Review",
        # Hidden tabs
        "Review_Queue", "Side_by_Side",
        "Source - Legacy Data", "Source - Findings", "Source - Key Risks",
        "Source - OREs", "Source - PRSA Issues", "Source - BM Activities",
        "Source - GRA RAPs",
    ]
    for i, name in enumerate(desired_order):
        if name in wb.sheetnames:
            current_idx = wb.sheetnames.index(name)
            wb.move_sheet(name, offset=i - current_idx)

    wb.save(output_path)
    logger.info(f"  Output saved: {output_path}")
    logger.info(f"  Sheets: {wb.sheetnames}")
