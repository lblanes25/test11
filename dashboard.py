"""
Risk Taxonomy Transformer — Dashboard
======================================
Three views for three personas:
  1. Entity View — audit team walks through all 23 L2s with drill-down
  2. Risk Category View — risk owner sees one L2 across all entities
  3. Portfolio Overview — leadership sees entity-level before/after summary

Usage:
    streamlit run dashboard.py
"""

import re
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import html as html_lib
from pathlib import Path

from risk_taxonomy_transformer.config import get_config

_CFG = get_config()

_PROJECT_ROOT = Path(__file__).parent
OUTPUT_DIR = _PROJECT_ROOT / "data" / "output"

# =============================================================================
# PAGE CONFIG
# =============================================================================

st.set_page_config(
    page_title="Risk Taxonomy Review",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; }
</style>
""", unsafe_allow_html=True)

# =============================================================================
# STATUS DEFINITIONS
# =============================================================================

STATUS_CONFIG = {
    "Applicability Undetermined":       {"icon": "⚠️", "sort": 0},
    "Needs Review":                     {"icon": "🔎", "sort": 1},
    "Assumed N/A — Verify":             {"icon": "🔶", "sort": 2},
    "Applicable":                       {"icon": "✅", "sort": 3},
    "Not Applicable":                   {"icon": "⬜", "sort": 4},
    "No Legacy Source":                 {"icon": "🔵", "sort": 5},
}

_RATING_RANK = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4,
                "low": 1, "medium": 2, "high": 3, "critical": 4}
_RANK_LABEL = {1: "Low", 2: "Medium", 3: "High", 4: "Critical"}


# =============================================================================
# DATA LOADING
# =============================================================================

@st.cache_data
def load_data(file_path: str) -> dict[str, pd.DataFrame]:
    sheets = {}
    xls = pd.ExcelFile(file_path)
    for name in ["Audit_Review", "Side_by_Side",
                  "Source - Findings", "Source - Sub-Risks",
                  "Source - Legacy Data", "Source - OREs",
                  "Source - PRSA Issues",
                  "Source - BM Activities",
                  "Source - GRA RAPs"]:
        if name in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=name)
            # Normalize column names from transformer output
            rename_map = {
                "Proposed Status": "Status",
                "Proposed Rating": "Inherent Risk Rating",
            }
            df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
            sheets[name] = df
    return sheets


def find_latest_output() -> Path | None:
    files = sorted(OUTPUT_DIR.glob("transformed_risk_taxonomy_*.xlsx"),
                   key=lambda f: f.stat().st_mtime)
    return files[-1] if files else None


# =============================================================================
# HELPERS
# =============================================================================

def is_empty(val) -> bool:
    if val is None:
        return True
    if isinstance(val, float) and pd.isna(val):
        return True
    return str(val).strip().lower() in ("", "nan", "none")


def _esc(text) -> str:
    """Escape text for safe HTML/markdown embedding."""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    return html_lib.escape(str(text))


def rating_display(val) -> str:
    if is_empty(val):
        return None
    v = int(val)
    bars = "█" * v + "░" * (4 - v)
    labels = {1: "Low", 2: "Medium", 3: "High", 4: "Critical"}
    return f"{bars} {v} ({labels.get(v, '')})"


def status_label(status: str) -> str:
    cfg = STATUS_CONFIG.get(status, {"icon": "❓"})
    return f'{cfg["icon"]} {status}'


def format_run_timestamp(filepath: Path) -> str:
    """Extract and format the run timestamp from the output filename."""
    from datetime import datetime as _dt
    stem = filepath.stem
    ts_str = stem.replace("transformed_risk_taxonomy_", "")
    try:
        dt = _dt.strptime(ts_str, "%m%d%Y%I%M%p")
        return dt.strftime("%B %d, %Y %I:%M %p").replace(" 0", " ")
    except ValueError:
        return filepath.name


def clean_col(df, col):
    """Clean a column — replace NaN/nan with empty string."""
    if col in df.columns:
        df[col] = df[col].apply(lambda x: "" if is_empty(x) else str(x))
    return df


def get_detail_row(detail_df, entity_id, l2):
    """Get matching Side_by_Side row for an entity+L2."""
    if detail_df is None or detail_df.empty:
        return None
    match = detail_df[
        (detail_df["entity_id"].astype(str) == str(entity_id)) &
        (detail_df["new_l2"] == l2)
    ]
    return match.iloc[0] if not match.empty else None


# =============================================================================
# DRILL-DOWN COMPONENT RENDERERS
# =============================================================================

def _render_decision_basis(row, style="info"):
    basis = _esc(row.get("Decision Basis", "—"))
    st.markdown("**Decision Basis**")
    if style == "success":
        st.success(basis)
    elif style == "warning":
        st.warning(basis)
    else:
        st.info(basis)


def _render_signals(row):
    signals = row.get("Additional Signals", "")
    if is_empty(signals):
        return
    st.markdown("**Additional Signals**")
    # Signals are newline-separated between flag types, " | " within a type
    for signal in re.split(r"\n| \| ", str(signals)):
        signal = _esc(signal.strip())
        if not signal:
            continue
        signal_lower = signal.lower()
        if "[app]" in signal_lower or "application" in signal_lower or "engagement" in signal_lower:
            st.warning(f"📎 {signal}")
        elif "[aux]" in signal_lower or "auxiliary" in signal_lower:
            st.info(f"📌 {signal}")
        elif "[cross-boundary]" in signal_lower or "outside normal mapping" in signal_lower:
            st.info(f"🔀 {signal}")
        else:
            st.write(f"ℹ️ {signal}")


def _render_ratings(row, detail_row=None):
    likelihood = row.get("Likelihood")
    if is_empty(likelihood):
        st.caption("No ratings — legacy source was N/A or not assessed.")
        return

    irr_label = None
    if detail_row is not None:
        irr_label = detail_row.get("inherent_risk_rating_label")
    if is_empty(irr_label):
        irr_label = row.get("Inherent Risk Rating")

    if not is_empty(irr_label):
        st.markdown(f"**Proposed Inherent Risk Rating: {irr_label}**")
    else:
        st.markdown("**Inherent Risk Rating:** —")

    st.write(f"  Likelihood: {rating_display(likelihood)}")

    impact_fields = [
        ("Financial", "Impact - Financial"),
        ("Reputational", "Impact - Reputational"),
        ("Consumer Harm", "Impact - Consumer Harm"),
        ("Regulatory", "Impact - Regulatory"),
    ]
    impact_displays = [(label, row.get(col)) for label, col in impact_fields]
    valid_impacts = [(label, val) for label, val in impact_displays if not is_empty(val)]

    if valid_impacts:
        max_impact = max(int(val) for _, val in valid_impacts)
        breakdown = ", ".join(f"{label}={int(val)}" for label, val in valid_impacts)
        st.write(f"  Overall Impact: {rating_display(max_impact)}  ← max of: {breakdown}")

    control_fields = [
        ("IAG Control Effectiveness", "IAG Control Effectiveness"),
        ("Aligned Assurance Rating", "Aligned Assurance Rating"),
        ("Management Awareness Rating", "Management Awareness Rating"),
    ]
    control_displays = [(label, rating_display(row.get(col))) for label, col in control_fields]
    control_non_null = [(label, val) for label, val in control_displays if val is not None]

    if control_non_null:
        st.markdown("**Control Ratings** *(starting point — team will adjust)*")
        for label, val in control_non_null:
            st.write(f"  {label}: {val}")


def _render_source_rationale(detail_row):
    rationale = str(detail_row.get("source_rationale", ""))
    if is_empty(rationale):
        return
    st.markdown("**Source Rationale Text**")
    st.markdown(f"> {_esc(rationale)}")


def _render_control_effectiveness(row):
    """Render the control assessment story for one entity+L2 row."""
    control_signals = row.get("Control Signals", "")
    baseline = row.get("Control Effectiveness Baseline", "")
    impact = row.get("Impact of Issues", "")

    has_content = (not is_empty(control_signals) or
                   not is_empty(baseline) or
                   not is_empty(impact))
    if not has_content:
        return

    st.divider()
    st.markdown("**Control Assessment**")

    # Control Signals — contradiction alerts
    if not is_empty(control_signals):
        st.error(f"🚨 {_esc(str(control_signals))}")

    # Control Effectiveness Baseline — context
    if not is_empty(baseline):
        st.info(_esc(str(baseline)))

    # Impact of Issues — itemized findings/OREs/enterprise findings
    if not is_empty(impact):
        impact_str = str(impact)
        if impact_str.strip().lower() == "no open items":
            st.success("No open items")
        else:
            categories = impact_str.replace("\r\n", "\n").replace("\r", "\n").split("\n")
            for cat in categories:
                cat = cat.strip()
                if cat and cat.lower() != "nan":
                    st.markdown(f"- {_esc(cat)}")


# =============================================================================
# DRILL-DOWN RENDERERS — structured by status type
# =============================================================================

def render_drilldown_applicable(row, detail_row):
    """Applicable: Decision Basis → Rationale → Signals → Ratings → Control Assessment"""
    _render_decision_basis(row, style="success")
    if detail_row is not None:
        _render_source_rationale(detail_row)
    _render_signals(row)
    _render_ratings(row, detail_row)
    _render_control_effectiveness(row)


def render_drilldown_assumed_na(row, detail_row):
    """Assumed N/A: Decision Basis → Rationale → Signals → Control Assessment"""
    _render_decision_basis(row, style="info")
    if detail_row is not None:
        _render_source_rationale(detail_row)
    _render_signals(row)
    _render_control_effectiveness(row)


def render_drilldown_undetermined(row, detail_row, entity_detail_df):
    """Undetermined: Sibling context → Decision Basis → Rationale → Signals → Ratings"""
    legacy_source = str(row.get("Legacy Source", ""))
    if entity_detail_df is not None and not is_empty(legacy_source):
        base_pillar = legacy_source.split(" (also")[0].strip()
        same_pillar = entity_detail_df[
            entity_detail_df["source_legacy_pillar"].astype(str).str.contains(
                base_pillar, na=False
            )
        ]
        matched = same_pillar[
            ~same_pillar["method"].astype(str).str.contains(
                "no_evidence_all_candidates|evaluated_no_evidence", na=False
            )
        ]
        if not matched.empty:
            st.markdown(f"**Other L2s from {base_pillar} that DID match:**")
            for _, m in matched.iterrows():
                st.write(f"• ✅ {m['new_l2']}")

    _render_decision_basis(row, style="warning")
    if detail_row is not None:
        _render_source_rationale(detail_row)
    _render_signals(row)
    _render_ratings(row, detail_row)
    _render_control_effectiveness(row)


def render_drilldown_informational(row):
    """Not Applicable / No Legacy Source: Decision Basis only, no ratings."""
    st.caption(_esc(row.get("Decision Basis", "—")))
    _render_signals(row)
    _render_control_effectiveness(row)


def render_drilldown(row, detail_row, status_raw, entity_detail_df=None):
    """Dispatch to the right drill-down renderer based on status."""
    if status_raw == "Assumed N/A — Verify":
        render_drilldown_assumed_na(row, detail_row)
    elif status_raw == "Applicability Undetermined":
        render_drilldown_undetermined(row, detail_row, entity_detail_df)
    elif status_raw == "Applicable":
        render_drilldown_applicable(row, detail_row)
    else:
        render_drilldown_informational(row)


def _render_entity_context_compact(row):
    """Compact entity context for inside drill-down expanders."""
    name = row.get("Entity Name", "")
    overview = row.get("Entity Overview", "")
    al = row.get("Audit Leader", "")
    pga = row.get("PGA", "")
    if not is_empty(name):
        st.markdown(f"**{_esc(name)}**")
    if not is_empty(overview):
        st.caption(_esc(overview))
    meta = []
    if not is_empty(al):
        meta.append(f"Audit Leader: {_esc(al)}")
    if not is_empty(pga):
        meta.append(f"PGA: {_esc(pga)}")
    if meta:
        st.write("  ·  ".join(meta))


def _render_scoped_findings(findings_df, entity_id, selected_l2):
    """Show findings tagged to this entity+L2 only."""
    if findings_df is None:
        return
    eid_col = next((c for c in ("entity_id", "Audit Entity ID") if c in findings_df.columns), None)
    l2_col = next((c for c in ("l2_risk", "Mapped To L2(s)") if c in findings_df.columns), None)
    if not eid_col or not l2_col:
        return
    matched = findings_df[
        (findings_df[eid_col].astype(str).str.strip() == str(entity_id)) &
        (findings_df[l2_col].astype(str).str.contains(selected_l2, na=False))
    ]
    if matched.empty:
        return
    st.markdown("**Relevant IAG Issues**")
    for _, f in matched.iterrows():
        fid = f.get("issue_id", f.get("Finding ID", ""))
        title = f.get("issue_title", f.get("Finding Name", ""))
        severity = f.get("severity", f.get("Final Reportable Finding Risk Rating", ""))
        status = f.get("status", f.get("Finding Status", ""))
        st.write(f"• {fid}: {title} ({severity}, {status})")


def _render_scoped_sub_risks(sub_risks_df, entity_id, detail_row):
    """Show sub-risks from the source legacy pillar for this entity."""
    if sub_risks_df is None or detail_row is None:
        return
    pillar = str(detail_row.get("source_legacy_pillar", "")).split(" (also")[0].strip()
    if is_empty(pillar):
        return
    eid_col = next((c for c in ("entity_id", "Audit Entity ID") if c in sub_risks_df.columns), None)
    l1_col = next((c for c in ("legacy_l1", "Level 1 Risk Category") if c in sub_risks_df.columns), None)
    if not eid_col or not l1_col:
        return
    matched = sub_risks_df[
        (sub_risks_df[eid_col].astype(str).str.strip() == str(entity_id)) &
        (sub_risks_df[l1_col].astype(str).str.strip() == pillar)
    ]
    if matched.empty:
        return
    st.markdown("**Relevant Sub-Risk Descriptions**")
    desc_col = next((c for c in ("risk_description", "Key Risk Description") if c in matched.columns), None)
    id_col = next((c for c in ("risk_id", "Key Risk ID") if c in matched.columns), None)
    for _, sr in matched.iterrows():
        rid = sr.get(id_col, "") if id_col else ""
        desc = str(sr.get(desc_col, ""))[:200] if desc_col else ""
        st.write(f"• {rid}: {desc}")


def resolve_status(status_text):
    """Extract raw status from emoji-prefixed display text."""
    for s in STATUS_CONFIG:
        if s in str(status_text):
            return s
    return str(status_text)


# =============================================================================
# TRACEABILITY HELPERS
# =============================================================================

def base_pillar(source_str):
    return str(source_str).split(" (also")[0].strip()


def method_to_status(method):
    m = str(method)
    if "llm_confirmed_na" in m:
        return "Not Applicable"
    if "source_not_applicable" in m:
        return "Not Applicable"
    if "evaluated_no_evidence" in m:
        return "Assumed N/A — Verify"
    if "no_evidence_all_candidates" in m:
        return "Applicability Undetermined"
    if "true_gap_fill" in m or "gap_fill" in m:
        return "No Legacy Source"
    if ("direct" in m or "evidence_match" in m or "llm_override" in m
            or "issue_confirmed" in m or "dedup" in m):
        return "Applicable"
    return "Needs Review"


# =============================================================================
# MAIN APP
# =============================================================================

def main():
    latest = find_latest_output()
    if latest is None:
        st.error("No transformer output found in `data/output/`. "
                 "Run `risk_taxonomy_transformer.py` first.")
        return

    sheets = load_data(str(latest))
    audit_df = sheets.get("Audit_Review")
    detail_df = sheets.get("Side_by_Side")
    findings_df = sheets.get("Source - Findings")
    sub_risks_df = sheets.get("Source - Sub-Risks")
    prsa_df = sheets.get("Source - PRSA Issues")
    bma_df = sheets.get("Source - BM Activities")
    gra_raps_df = sheets.get("Source - GRA RAPs")
    ore_df = sheets.get("Source - OREs")

    if audit_df is None:
        st.error("Audit_Review sheet not found.")
        return

    # =========================================================================
    # SIDEBAR
    # =========================================================================
    with st.sidebar:
        st.header("📋 Risk Taxonomy Review")
        st.caption(f"Last Run: {format_run_timestamp(latest)}")
        st.divider()

        view_mode = st.radio(
            "View", ["Entity View", "Risk Category View", "Portfolio Overview"],
            index=0, horizontal=True,
        )
        st.divider()

        selected_entity = None
        selected_l2 = None

        if view_mode == "Entity View":
            entities = sorted(audit_df["Entity ID"].unique())
            selected_entity = st.selectbox("Select Audit Entity", entities, index=0)
        elif view_mode == "Risk Category View":
            all_l2s = sorted(audit_df["New L2"].unique())
            selected_l2 = st.selectbox("Select L2 Risk", all_l2s, index=0)

        # Status filter — Entity View and Risk Category View only
        selected_statuses = []
        if view_mode != "Portfolio Overview":
            st.divider()
            st.subheader("Filters")
            all_statuses = list(STATUS_CONFIG.keys())
            selected_statuses = st.multiselect(
                "Status", options=all_statuses, default=[],
                help="Leave empty to show all. Hides rows from all sections including the drill-down.",
            )

        # Org filters — portfolio and risk category views
        selected_al = selected_pga = selected_team = None
        if view_mode in ("Portfolio Overview", "Risk Category View"):
            st.divider()
            st.subheader("Organization")
            if "Audit Leader" in audit_df.columns:
                vals = sorted([str(x) for x in audit_df["Audit Leader"].dropna().unique()
                               if str(x) != "nan"])
                if vals:
                    selected_al = st.multiselect(
                        "Audit Leader", vals, default=[],
                        help="Leave empty to show all.")
            if "PGA" in audit_df.columns:
                vals = sorted([str(x) for x in audit_df["PGA"].dropna().unique()
                               if str(x) != "nan"])
                if vals:
                    selected_pga = st.multiselect(
                        "PGA", vals, default=[],
                        help="Leave empty to show all.")
            if "Core Audit Team" in audit_df.columns:
                vals = sorted([str(x) for x in audit_df["Core Audit Team"].dropna().unique()
                               if str(x) != "nan"])
                if vals:
                    selected_team = st.multiselect(
                        "Core Audit Team", vals, default=[],
                        help="Leave empty to show all.")

    is_entity_view = view_mode == "Entity View"
    is_risk_view = view_mode == "Risk Category View"
    is_portfolio_view = view_mode == "Portfolio Overview"

    # Apply filters
    filtered = audit_df.copy()
    if is_entity_view and selected_entity:
        filtered = filtered[filtered["Entity ID"] == selected_entity]
    elif is_risk_view and selected_l2:
        filtered = filtered[filtered["New L2"] == selected_l2]

    # Empty selection = no filter = show all
    if not is_entity_view:
        if selected_al and "Audit Leader" in filtered.columns:
            filtered = filtered[filtered["Audit Leader"].astype(str).isin(selected_al)]
        if selected_pga and "PGA" in filtered.columns:
            filtered = filtered[filtered["PGA"].astype(str).isin(selected_pga)]
        if selected_team and "Core Audit Team" in filtered.columns:
            filtered = filtered[filtered["Core Audit Team"].astype(str).isin(selected_team)]

    if selected_statuses:
        filtered = filtered[filtered["Status"].isin(selected_statuses)]

    # Sort
    filtered = filtered.copy()
    filtered["_status_sort"] = filtered["Status"].map(
        {s: cfg["sort"] for s, cfg in STATUS_CONFIG.items()}
    ).fillna(99)
    if "inherent_risk_rating" in filtered.columns:
        filtered["_rating_sort"] = filtered["inherent_risk_rating"].apply(
            lambda x: (5 - int(x)) if not is_empty(x) else 99
        )
    else:
        filtered["_rating_sort"] = 99
    filtered = filtered.sort_values(["Entity ID", "_status_sort", "_rating_sort", "New L2"])

    # Counts
    total = len(filtered)
    undetermined_count = (filtered["Status"] == "Applicability Undetermined").sum()
    assumed_na_count = (filtered["Status"] == "Assumed N/A — Verify").sum()
    action_total = undetermined_count + assumed_na_count

    # =========================================================================
    # TITLE & BANNER — context-specific per view
    # =========================================================================
    if is_entity_view:
        st.title(f"Entity: {selected_entity}")
        if action_total > 0:
            st.warning(
                f"**{action_total} of {total} L2 risks** for {selected_entity} need your review — "
                f"{undetermined_count} applicability undetermined, "
                f"{assumed_na_count} no evidence found (verify N/A)."
            )
        else:
            st.success(f"**All {total} L2 risks** for {selected_entity} have proposed applicability — review to confirm.")
    elif is_risk_view:
        l1_for_l2 = ""
        if "New L1" in filtered.columns and not filtered.empty:
            l1_vals = filtered["New L1"].dropna().unique()
            l1_for_l2 = str(l1_vals[0]) if len(l1_vals) > 0 else ""
        st.title(f"Risk Category: {selected_l2}")
        if l1_for_l2:
            st.caption(f"L1: {l1_for_l2} · {filtered['Entity ID'].nunique()} entities in scope")
        if action_total > 0:
            st.warning(
                f"**{action_total} entities** need a decision on {selected_l2} — "
                f"{undetermined_count} applicability undetermined, "
                f"{assumed_na_count} no evidence found (verify N/A)."
            )
        else:
            st.success(f"**No entities** need a decision on {selected_l2} — all have proposed applicability.")
    else:
        st.title("Portfolio Overview")
        st.caption(f"{audit_df['Entity ID'].nunique()} entities · {len(audit_df)} total mappings")
        if action_total > 0:
            st.warning(
                f"Across the portfolio, **{action_total} items** require attention — "
                f"{undetermined_count} applicability undetermined, "
                f"{assumed_na_count} no evidence found (verify N/A)."
            )
        else:
            st.success("Across the portfolio, **no items** require attention — "
                       "all have proposed applicability.")

    # =========================================================================
    # PORTFOLIO OVERVIEW
    # =========================================================================
    if is_portfolio_view:
        # --- Category summary table ---
        def pct(count):
            return f"{count / total * 100:.1f}%" if total > 0 else "0%"

        is_ai = filtered["Decision Basis"].astype(str).str.startswith("AI review") if "Decision Basis" in filtered.columns else pd.Series(False, index=filtered.index)
        evidence_count = ((filtered["Status"] == "Applicable") & ~is_ai).sum()
        ai_applicable_count = ((filtered["Status"] == "Applicable") & is_ai).sum()
        ai_na_count = ((filtered["Status"] == "Not Applicable") & is_ai).sum()
        ai_total = ai_applicable_count + ai_na_count
        na_count = ((filtered["Status"] == "Not Applicable") & ~is_ai).sum()
        not_assessed_count = (filtered["Status"] == "No Legacy Source").sum()

        summary_rows = [
            {"Category": "✅ Mapped with evidence", "Count": evidence_count,
             "%": (evidence_count / total * 100) if total > 0 else 0.0,
             "Reviewer Action": (
                 "These L2 risks were matched based on keywords in the rationale text, "
                 "sub-risk descriptions, or confirmed by open findings. "
                 "The evidence is strong — spot-check and confirm."
             )},
            {"Category": "🤖 AI-Proposed", "Count": ai_total,
             "%": (ai_total / total * 100) if total > 0 else 0.0,
             "Reviewer Action": (
                 f"AI review proposed applicability for these rows "
                 f"({ai_applicable_count} applicable, {ai_na_count} not applicable). "
                 "The AI's reasoning is shown in the Decision Basis column. "
                 "Review the proposal and override if needed."
             )},
            {"Category": "⚠️ Team decision required", "Count": undetermined_count,
             "%": (undetermined_count / total * 100) if total > 0 else 0.0,
             "Reviewer Action": (
                 "The tool could not propose which L2 risks apply from the available data. "
                 "All possible L2s are shown with the legacy rating — your team decides which "
                 "ones are relevant and marks the rest N/A."
             )},
            {"Category": "🔶 Assumed N/A — Verify", "Count": assumed_na_count,
             "%": (assumed_na_count / total * 100) if total > 0 else 0.0,
             "Reviewer Action": (
                 "Other L2s from the same legacy pillar had evidence, but this one did not. "
                 "Marked as not applicable by default. Override if this L2 is relevant to the entity."
             )},
            {"Category": "⬜ Source was N/A", "Count": na_count,
             "%": (na_count / total * 100) if total > 0 else 0.0,
             "Reviewer Action": (
                 "The legacy pillar was explicitly rated Not Applicable. Carried forward — "
                 "no action needed unless circumstances have changed."
             )},
            {"Category": "🔵 No legacy coverage", "Count": not_assessed_count,
             "%": (not_assessed_count / total * 100) if total > 0 else 0.0,
             "Reviewer Action": (
                 "No legacy pillar maps to this L2 risk. This is a gap in the old taxonomy, "
                 "not a team decision. Will need to be assessed from scratch."
             )},
        ]
        # Render as markdown table — st.dataframe column widths aren't reliably configurable
        summary_df = pd.DataFrame(summary_rows).sort_values("%", ascending=False)
        md_lines = ["| Category | Count | % | Reviewer Action |",
                     "|:---------|------:|----:|:---------------|"]
        for _, r in summary_df.iterrows():
            md_lines.append(
                f"| {r['Category']} | {int(r['Count'])} | {r['%']:.1f}% | {r['Reviewer Action']} |"
            )
        st.markdown("\n".join(md_lines))

        st.divider()

        # --- Entity summary table ---
        st.header("Entity Summary")
        st.caption("To investigate a specific entity, switch to Entity View in the sidebar.")

        entity_rows = []
        for eid in sorted(filtered["Entity ID"].unique()):
            e = filtered[filtered["Entity ID"] == eid]
            def _first(col):
                if col in e.columns:
                    vals = e[col].dropna().unique()
                    v = str(vals[0]) if len(vals) > 0 else ""
                    return "" if v == "nan" else v
                return ""

            # Before — from Side_by_Side
            legacy_rated = 0
            legacy_highest = ""
            legacy_highest_rank = 0
            if detail_df is not None:
                ed = detail_df[detail_df["entity_id"].astype(str) == eid]
                if not ed.empty:
                    rated = ed[ed["source_risk_rating_raw"].apply(
                        lambda x: not is_empty(x) and str(x).strip().lower() not in
                        ("not applicable", "n/a", "na"))]
                    legacy_rated = rated["source_legacy_pillar"].apply(base_pillar).nunique()
                    for raw in rated["source_risk_rating_raw"].dropna():
                        rank = _RATING_RANK.get(str(raw).strip(), 0)
                        if rank > legacy_highest_rank:
                            legacy_highest_rank = rank
                            legacy_highest = _RANK_LABEL.get(rank, str(raw))

            applicable_ct = (e["Status"] == "Applicable").sum()
            action_rows = e[e["Status"].isin(["Applicability Undetermined", "Assumed N/A — Verify"])]

            # Split decisions by severity
            high_crit_decisions = 0
            other_decisions = 0
            if "Inherent Risk Rating" in action_rows.columns:
                for _, ar in action_rows.iterrows():
                    irr = str(ar.get("Inherent Risk Rating", ""))
                    if irr in ("High", "Critical"):
                        high_crit_decisions += 1
                    else:
                        other_decisions += 1
            else:
                other_decisions = len(action_rows)

            proposed_highest = ""
            proposed_highest_rank = 0
            if "Inherent Risk Rating" in e.columns:
                for val in e["Inherent Risk Rating"].dropna():
                    rank = _RATING_RANK.get(str(val).strip(), 0)
                    if rank > proposed_highest_rank:
                        proposed_highest_rank = rank
                        proposed_highest = str(val).strip()

            # Control contradiction count only
            control_flags = 0
            if "Control Signals" in e.columns:
                control_flags = e["Control Signals"].astype(str).str.contains(
                    "review whether|open issues", na=False, case=False).sum()

            entity_rows.append({
                "Entity ID": eid,
                "Entity Name": _first("Entity Name"),
                "Audit Leader": _first("Audit Leader"),
                "PGA": _first("PGA"),
                "Core Audit Team": _first("Core Audit Team"),
                "Applicable": applicable_ct,
                "Needs Review": high_crit_decisions + other_decisions,
                "Legacy Highest": legacy_highest or "—",
                "Proposed Highest": proposed_highest or "—",
                "High/Crit Decisions": high_crit_decisions,
                "Other Decisions": other_decisions,
                "Control Flags": control_flags,
            })

        entity_summary = pd.DataFrame(entity_rows)
        entity_summary = entity_summary.sort_values(
            ["High/Crit Decisions", "Other Decisions"],
            ascending=[False, False],
        )

        summary_col_config = {
            "Entity ID": st.column_config.TextColumn(width="small"),
            "Applicable": st.column_config.NumberColumn(
                "Applicable", width="small",
                help="Number of L2 risks the tool proposed as applicable to this entity.",
            ),
            "Needs Review": st.column_config.NumberColumn(
                "Needs Review", width="small",
                help="Rows where the team must make an applicability decision (Undetermined + Assumed N/A).",
            ),
            "Legacy Highest": st.column_config.TextColumn(
                "Legacy Highest", width="small",
                help="The highest risk rating this entity had under the old 14-pillar taxonomy.",
            ),
            "Proposed Highest": st.column_config.TextColumn(
                "Proposed Highest", width="small",
                help="The highest risk rating carried into the new taxonomy. This is redistributed from legacy data, not a new assessment.",
            ),
            "High/Crit Decisions": st.column_config.NumberColumn(
                "High/Crit Decisions",
                help="Undetermined or assumed-not-applicable L2 risks rated High or Critical. These are the highest priority items for your team to review.",
            ),
            "Other Decisions": st.column_config.NumberColumn(
                "Other Decisions",
                help="Undetermined or assumed-not-applicable L2 risks rated Medium or Low. Still need review, but lower urgency.",
            ),
            "Control Flags": st.column_config.NumberColumn(
                "Control Flags",
                help="L2 risks where an open High/Critical finding contradicts a 'Well Controlled' rating. The control assessment may need updating.",
            ),
        }
        st.dataframe(entity_summary, use_container_width=True, hide_index=True,
                      height=min(35 * len(entity_summary) + 38, 600),
                      column_config=summary_col_config)


    # =========================================================================
    # ENTITY VIEW — tabs for Risk Profile, Drill-Down, Traceability, Source Data
    # =========================================================================
    if is_entity_view and selected_entity:
        entity_detail = detail_df[detail_df["entity_id"].astype(str) == selected_entity] if detail_df is not None else None

        # Entity context block — shown at top of each tab
        def _render_entity_context():
            if filtered.empty:
                return
            first = filtered.iloc[0]
            name = first.get("Entity Name", "")
            overview = first.get("Entity Overview", "")
            al = first.get("Audit Leader", "")
            pga = first.get("PGA", "")
            if not is_empty(name):
                st.subheader(_esc(name))
            if not is_empty(overview):
                st.caption(_esc(overview))
            meta_parts = []
            if not is_empty(al):
                meta_parts.append(f"Audit Leader: {_esc(al)}")
            if not is_empty(pga):
                meta_parts.append(f"PGA: {_esc(pga)}")
            if meta_parts:
                st.write("  ·  ".join(meta_parts))
            st.divider()

        # --- Unmapped findings warning banner ---
        if findings_df is not None:
            _disp_col = "Disposition" if "Disposition" in findings_df.columns else None
            _eid_col_f = next((c for c in ("entity_id", "Audit Entity ID")
                               if c in findings_df.columns), None)
            if _disp_col and _eid_col_f:
                _entity_findings = findings_df[
                    findings_df[_eid_col_f].astype(str).str.strip() == selected_entity
                ]
                _unmapped_f = _entity_findings[
                    _entity_findings[_disp_col].astype(str).str.startswith("Filtered")
                    & _entity_findings[_disp_col].astype(str).str.contains("unmappable", case=False, na=False)
                ]
                if not _unmapped_f.empty:
                    # Parse legacy category names from Disposition text
                    _legacy_cats = set()
                    for _d in _unmapped_f[_disp_col].astype(str):
                        # Pattern: "Filtered — unmappable L2 (Compliance; Liquidity)"
                        _paren_start = _d.find("(")
                        _paren_end = _d.find(")")
                        if _paren_start != -1 and _paren_end != -1:
                            for _cat in _d[_paren_start + 1:_paren_end].split(";"):
                                _cat = _cat.strip()
                                if _cat:
                                    _legacy_cats.add(_cat)
                    _cat_list = ", ".join(sorted(_legacy_cats)) if _legacy_cats else "legacy risk categories"
                    st.warning(
                        f"This entity has **{len(_unmapped_f)} IAG issue(s)** tagged to "
                        f"legacy risk categories ({_cat_list}) that could not be mapped "
                        f"to a specific L2 risk. These are not reflected in any L2 row "
                        f"below. See **Source Data > IAG Issues** for details."
                    )

        tab_profile, tab_drill, tab_trace, tab_source = st.tabs([
            "Risk Profile", "Drill-Down", "Traceability", "Source Data"
        ])

        with tab_profile:
            _render_entity_context()
            overview_cols = ["New L1", "New L2", "Status", "Inherent Risk Rating",
                             "Confidence", "Legacy Source", "Decision Basis",
                             "Additional Signals", "Control Effectiveness Baseline",
                             "Impact of Issues", "Control Signals"]
            overview_cols = [c for c in overview_cols if c in filtered.columns]
            display_df = filtered[overview_cols].copy()
            display_df["Status"] = display_df["Status"].apply(status_label)
            clean_col(display_df, "Additional Signals")
            if "Inherent Risk Rating" in display_df.columns:
                display_df["Inherent Risk Rating"] = display_df["Inherent Risk Rating"].apply(
                    lambda x: str(x) if not is_empty(x) else "—")
            st.dataframe(display_df.reset_index(drop=True), use_container_width=True, height=500,
                          column_config={
                    "Status": st.column_config.TextColumn(width="medium"),
                    "Inherent Risk Rating": st.column_config.TextColumn(width="small"),
                    "Confidence": st.column_config.TextColumn(width="small"),
                    "Decision Basis": st.column_config.TextColumn(width="large"),
                    "Additional Signals": st.column_config.TextColumn(width="large"),
                })

        with tab_drill:
            _render_entity_context()
            st.caption("Expand any L2 to see evidence and context.")
            for _, row in filtered.iterrows():
                l2 = row.get("New L2", "")
                status_raw = resolve_status(row.get("Status", ""))
                irr = row.get("Inherent Risk Rating", "")
                cfg = STATUS_CONFIG.get(status_raw, {"icon": "❓"})
                label = f"{cfg['icon']} {row.get('New L1', '')} / {l2}  ·  {status_raw}"
                if not is_empty(irr) and str(irr) not in ("Not Applicable", "—"):
                    label += f"  ·  {irr}"
                detail_row = get_detail_row(detail_df, selected_entity, l2)
                with st.expander(label, expanded=False):
                    render_drilldown(row, detail_row, status_raw, entity_detail)

        with tab_trace:
            _render_entity_context()
            if entity_detail is not None and not entity_detail.empty:
                st.subheader("Multi-Mapping Fan-Out")
                edc = entity_detail.copy()
                edc["_base_pillar"] = edc["source_legacy_pillar"].apply(base_pillar)

                for pillar in sorted([p for p in edc["_base_pillar"].unique()
                                       if p and p not in ("", "nan", "None", "Findings")]):
                    pr = edc[edc["_base_pillar"] == pillar]
                    if len(pr) <= 1:
                        continue
                    raw_r = pr["source_risk_rating_raw"].dropna().unique()
                    r_str = str(raw_r[0]) if len(raw_r) > 0 else "unknown"
                    statuses = pr["method"].apply(method_to_status).value_counts()
                    parts = []
                    for s in STATUS_CONFIG:
                        ct = statuses.get(s, 0)
                        if ct > 0:
                            parts.append(f"{ct} {STATUS_CONFIG[s]['icon']}")
                    with st.expander(f"📂 {pillar} (rated {r_str}) → {', '.join(parts)}"):
                        for _, p in pr.iterrows():
                            s = method_to_status(str(p.get("method", "")))
                            st.write(f"{STATUS_CONFIG.get(s, {}).get('icon', '?')} **{p['new_l2']}** — {s}")

                dedup_rows = edc[edc["source_legacy_pillar"].astype(str).str.contains("also:", na=False)]
                if not dedup_rows.empty:
                    st.subheader("Convergence")
                    for _, dr in dedup_rows.iterrows():
                        src = str(dr.get("source_legacy_pillar", ""))
                        primary = src.split(" (also:")[0].strip()
                        also = []
                        rem = src
                        while "(also:" in rem:
                            s = rem.index("(also:") + 6
                            e = rem.index(")", s)
                            also.append(rem[s:e].strip())
                            rem = rem[e + 1:]
                        r = dr.get("source_risk_rating_raw", "")
                        r_str = str(r) if not is_empty(r) else "no rating"
                        st.write(f"**{dr['new_l2']}** ← {' + '.join([primary] + also)} → kept {r_str}")

        with tab_source:
            _render_entity_context()

            # --- IAG Issues ---
            st.subheader("IAG Issues")
            if findings_df is not None:
                eid_col = next((c for c in ("entity_id", "Audit Entity ID")
                                if c in findings_df.columns), None)
                if eid_col:
                    ef = findings_df[findings_df[eid_col].astype(str).str.strip() == selected_entity]
                    _findings_cfg = _CFG.get("columns", {}).get("findings", {})
                    _f_severity_col = next((c for c in ("severity", _findings_cfg.get("severity", "Final Reportable Finding Risk Rating"))
                                            if c in ef.columns), None)
                    _f_status_col = next((c for c in ("status", _findings_cfg.get("status", "Finding Status"))
                                          if c in ef.columns), None)
                    if not ef.empty and _f_severity_col and _f_status_col:
                        # Cross-tabulate status × severity for an informative caption
                        _sev_order = ["High", "Medium", "Low"]
                        _status_order = ["Open", "In Validation", "In Sustainability"]
                        combo_parts = [f"{len(ef)} IAG issue(s)"]
                        for _st in _status_order:
                            for _sv in _sev_order:
                                mask = ((ef[_f_status_col].astype(str).str.strip() == _st) &
                                        (ef[_f_severity_col].astype(str).str.strip() == _sv))
                                cnt = mask.sum()
                                if cnt > 0:
                                    combo_parts.append(f"{cnt} {_st} {_sv}")
                        st.caption(" · ".join(combo_parts))
                    elif not ef.empty and _f_severity_col:
                        sev_counts = ef[_f_severity_col].astype(str).str.strip().value_counts()
                        sev_parts = [f"{len(ef)} IAG issue(s)"]
                        for sev in ["High", "Medium", "Low"]:
                            if sev in sev_counts.index:
                                sev_parts.append(f"{sev_counts[sev]} {sev}")
                        st.caption(" · ".join(sev_parts))
                    else:
                        st.caption(f"{len(ef)} IAG issue(s)")
                    if ef.empty:
                        st.info("No IAG issues for this entity")
                    else:
                        # Sort: Open first, then In Validation, then In Sustainability; within status by severity High→Medium→Low
                        _ef_display = ef.copy()
                        if _f_status_col and _f_status_col in _ef_display.columns:
                            _ef_display["_sort_status"] = pd.Categorical(
                                _ef_display[_f_status_col].astype(str).str.strip(),
                                categories=["Open", "In Validation", "In Sustainability"],
                                ordered=True,
                            )
                            sort_cols = ["_sort_status"]
                            if _f_severity_col and _f_severity_col in _ef_display.columns:
                                _ef_display["_sort_sev"] = pd.Categorical(
                                    _ef_display[_f_severity_col].astype(str).str.strip(),
                                    categories=["High", "Medium", "Low"],
                                    ordered=True,
                                )
                                sort_cols.append("_sort_sev")
                            _ef_display = _ef_display.sort_values(sort_cols).drop(columns=[c for c in ["_sort_status", "_sort_sev"] if c in _ef_display.columns])
                        st.dataframe(_ef_display.fillna("").reset_index(drop=True), use_container_width=True,
                                     height=min(300, 35 * (len(_ef_display) + 1)))
                else:
                    st.warning("IAG Issues sheet missing entity ID column")
            else:
                st.info("No IAG issues data in workbook")

            # --- OREs ---
            st.divider()
            st.subheader("Operational Risk Events (OREs)")
            if ore_df is not None:
                _ore_cfg = _CFG.get("columns", {}).get("ore_mappings", {})
                _ore_entity_cfg = _ore_cfg.get("entity_id", "Audit Entity ID")
                ore_entity_col = next((c for c in ("entity_id", _ore_entity_cfg, "Audit Entity ID")
                                       if c in ore_df.columns), _ore_entity_cfg)
                ore_event_id_col = _ore_cfg.get("event_id", "Event ID")
                ore_event_title_col = _ore_cfg.get("event_title", "Event Title")
                ore_severity_col = _ore_cfg.get("severity", "Event Severity")
                ore_status_col = _ore_cfg.get("ore_status", "Event Status")
                ore_classification_col = _ore_cfg.get("event_classification", "Final Event Classification")
                ore_mapped_l2s_col = _ore_cfg.get("mapped_l2s", "Mapped L2s")

                if ore_entity_col in ore_df.columns:
                    eo = ore_df[ore_df[ore_entity_col].astype(str).str.strip() == selected_entity]

                    if not eo.empty and ore_classification_col in eo.columns:
                        class_vals = eo[ore_classification_col].astype(str).str.strip()
                        class_letters = class_vals.str.extract(r"(Class\s+[A-Z])", expand=False).dropna()
                        cls_counts = class_letters.value_counts()
                        ore_parts = [f"{len(eo)} ORE(s)"]
                        for cls in sorted(cls_counts.index):
                            ore_parts.append(f"{cls_counts[cls]} {cls}")
                        st.caption(" · ".join(ore_parts))
                    else:
                        st.caption(f"{len(eo)} ORE(s) tagged to this entity")

                    if eo.empty:
                        st.info("No operational risk events tagged to this entity")
                    else:
                        ore_display_cols = [c for c in [
                            ore_event_id_col, ore_event_title_col,
                            ore_severity_col, ore_status_col,
                            ore_classification_col, ore_mapped_l2s_col,
                        ] if c in eo.columns]
                        # Sort by classification: Class A first, then B, then C
                        _eo_display = eo[ore_display_cols].copy()
                        if ore_classification_col in _eo_display.columns:
                            _eo_display["_sort_cls"] = pd.Categorical(
                                _eo_display[ore_classification_col].astype(str).str.strip().str.extract(r"(Class\s+[A-Z])", expand=False).fillna(""),
                                categories=["Class A", "Class B", "Class C"],
                                ordered=True,
                            )
                            _eo_display = _eo_display.sort_values("_sort_cls").drop(columns=["_sort_cls"])
                        st.dataframe(_eo_display.fillna("").reset_index(drop=True),
                                     use_container_width=True,
                                     height=min(300, 35 * (len(_eo_display) + 1)))
                else:
                    st.warning(f"ORE sheet missing '{ore_entity_col}' column")
            else:
                st.info("No ORE data in workbook")

            # PRSA Issues — full width
            st.divider()
            st.subheader("PRSA Issues")
            if prsa_df is not None:
                _prsa_cfg = _CFG.get("columns", {}).get("prsa", {})
                ae_col = _prsa_cfg.get("ae_id", "AE ID")
                prsa_id_col = _prsa_cfg.get("prsa_id", "PRSA ID")
                tagged_col = _prsa_cfg.get("all_prsas_tagged", "All PRSAs Tagged to AE")
                issue_id_col = _prsa_cfg.get("issue_id", "Issue ID")
                issue_rating_col = _prsa_cfg.get("issue_rating", "Issue Rating")
                issue_status_col = _prsa_cfg.get("issue_status", "Issue Status")
                issue_breakdown_col = _prsa_cfg.get("issue_breakdown_type", "Issue Breakdown Type")
                issue_title_col = _prsa_cfg.get("issue_title", "Issue Title")
                process_title_col = _prsa_cfg.get("process_title", "Process Title")
                control_title_col = _prsa_cfg.get("control_title", "Control Title")

                if ae_col in prsa_df.columns:
                    ep = prsa_df[prsa_df[ae_col].astype(str).str.strip() == selected_entity]

                    # Also show PRSAs tagged to this AE (from the multi-value column)
                    tagged_prsas = []
                    if tagged_col in prsa_df.columns:
                        ae_rows = prsa_df[prsa_df[ae_col].astype(str).str.strip() == selected_entity]
                        if not ae_rows.empty:
                            raw = str(ae_rows.iloc[0][tagged_col])
                            if raw and raw != "nan":
                                tagged_prsas = [p.strip() for p in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n") if p.strip()]

                    prsas_with_issues = set(ep[prsa_id_col].unique()) if not ep.empty and prsa_id_col in ep.columns else set()
                    clean_prsas = [p for p in tagged_prsas if p not in prsas_with_issues]

                    if tagged_prsas:
                        st.caption(f"{len(tagged_prsas)} PRSA(s) tagged · "
                                   f"{len(prsas_with_issues)} with issues · "
                                   f"{len(clean_prsas)} clean")

                    if ep.empty:
                        if tagged_prsas:
                            st.success(f"No PRSA control failures for this entity. "
                                       f"Tagged PRSAs: {', '.join(tagged_prsas)}")
                        else:
                            st.info("No PRSA data for this entity")
                    else:
                        # Show issue summary by PRSA
                        prsa_display_cols = [c for c in [
                            prsa_id_col, process_title_col, issue_id_col,
                            issue_rating_col, issue_status_col, issue_breakdown_col,
                            control_title_col, issue_title_col,
                            "Other AEs With This PRSA",
                        ] if c in ep.columns]
                        # Sort: Open issues first, then by rating High→Medium→Low
                        _ep_display = ep[prsa_display_cols].copy()
                        if issue_status_col in _ep_display.columns:
                            _ep_display["_sort_status"] = pd.Categorical(
                                _ep_display[issue_status_col].astype(str).str.strip(),
                                categories=["Open", "In Validation", "In Sustainability", "Closed"],
                                ordered=True,
                            )
                            sort_cols = ["_sort_status"]
                            if issue_rating_col in _ep_display.columns:
                                _ep_display["_sort_rating"] = pd.Categorical(
                                    _ep_display[issue_rating_col].astype(str).str.strip(),
                                    categories=["High", "Medium", "Low"],
                                    ordered=True,
                                )
                                sort_cols.append("_sort_rating")
                            _ep_display = _ep_display.sort_values(sort_cols).drop(columns=[c for c in ["_sort_status", "_sort_rating"] if c in _ep_display.columns])
                        st.dataframe(_ep_display.fillna("").reset_index(drop=True),
                                     use_container_width=True,
                                     height=min(300, 35 * (len(_ep_display) + 1)))

                        # Highlight cross-AE shared PRSAs
                        shared_col = "Other AEs With This PRSA"
                        if shared_col in ep.columns:
                            shared = ep[ep[shared_col].apply(lambda x: not is_empty(x))]
                            if not shared.empty:
                                shared_prsas = shared[[prsa_id_col, shared_col]].drop_duplicates()
                                for _, sp in shared_prsas.iterrows():
                                    st.warning(f"**{sp[prsa_id_col]}** is shared with: {sp[shared_col]}")

                        if clean_prsas:
                            st.success(f"PRSAs with no issues: {', '.join(clean_prsas)}")
                else:
                    st.warning(f"PRSA sheet missing '{ae_col}' column")
            else:
                st.info("No PRSA data in workbook")

            # GRA RAPs — full width
            st.divider()
            st.subheader("GRA RAPs (Regulatory Findings)")
            if gra_raps_df is not None:
                _gra_cfg = _CFG.get("columns", {}).get("gra_raps", {})
                gra_entity_col = _gra_cfg.get("entity_id", "Audit Entity ID")
                gra_rap_id_col = _gra_cfg.get("rap_id", "RAP ID")
                gra_rap_header_col = _gra_cfg.get("rap_header", "RAP Header")
                gra_rap_details_col = _gra_cfg.get("rap_details", "RAP Details")
                gra_rap_status_col = _gra_cfg.get("rap_status", "RAP Status")
                gra_due_date_col = _gra_cfg.get("bu_corrective_action_due_date", "BU Corrective Action Due Date")
                gra_related_col = _gra_cfg.get("related_exams_and_findings", "Related Exams and Findings")

                if gra_entity_col in gra_raps_df.columns:
                    eg = gra_raps_df[gra_raps_df[gra_entity_col].astype(str).str.strip() == selected_entity]

                    if not eg.empty and gra_rap_status_col in eg.columns:
                        statuses = eg[gra_rap_status_col].astype(str).str.strip()
                        active_count = statuses.isin(["Open", "Initial Validation"]).sum()
                        completed_count = statuses.isin(["Sustainability Validation", "Validation-Completed"]).sum()
                        st.caption(f"{len(eg)} RAP(s) · "
                                   f"{active_count} open · "
                                   f"{completed_count} completed")
                    else:
                        st.caption(f"{len(eg)} RAP(s) tagged to this entity")

                    if eg.empty:
                        st.info("No GRA RAPs tagged to this entity")
                    else:
                        gra_display_cols = [c for c in [
                            gra_rap_id_col, gra_rap_header_col, gra_rap_details_col,
                            gra_rap_status_col, gra_due_date_col, gra_related_col,
                        ] if c in eg.columns]
                        # Sort: Open/Initial Validation first, then Sustainability, then Completed
                        _eg_display = eg[gra_display_cols].copy()
                        if gra_rap_status_col in _eg_display.columns:
                            _eg_display["_sort_status"] = pd.Categorical(
                                _eg_display[gra_rap_status_col].astype(str).str.strip(),
                                categories=["Open", "Initial Validation", "Sustainability Validation", "Validation-Completed"],
                                ordered=True,
                            )
                            _eg_display = _eg_display.sort_values("_sort_status").drop(columns=["_sort_status"])
                        st.dataframe(_eg_display.fillna("").reset_index(drop=True),
                                     use_container_width=True,
                                     height=min(300, 35 * (len(_eg_display) + 1)))
                else:
                    st.warning(f"GRA RAPs sheet missing '{gra_entity_col}' column")
            else:
                st.info("No GRA RAPs data in workbook")

            # BM Activities — full width
            st.divider()
            st.subheader("Business Monitoring Activities")
            if bma_df is not None:
                _bma_cfg = _CFG.get("columns", {}).get("bma", {})
                bma_entity_col = _bma_cfg.get("entity_id", "Related Audit Entity")
                bma_instance_col = _bma_cfg.get("instance_id", "Activity Instance ID")
                bma_activity_title_col = _bma_cfg.get("activity_title", "Related BM Activity Title")
                bma_date_col = _bma_cfg.get("planned_completion_date", "Planned Instance Completion Date")
                bma_occurred_col = _bma_cfg.get("activity_occurred", "Did this activity occur?")
                bma_cases_col = _bma_cfg.get("monitoring_cases", "Business Monitoring Cases")
                bma_summary_col = _bma_cfg.get("summary_of_results", "Summary of Results")
                bma_impact_desc_col = _bma_cfg.get("impact_description", "If yes, please describe impact")

                if bma_entity_col in bma_df.columns:
                    eb = bma_df[bma_df[bma_entity_col].astype(str).str.strip() == selected_entity]

                    if not eb.empty and bma_occurred_col in eb.columns:
                        occurred_vals = eb[bma_occurred_col].astype(str).str.strip().str.lower()
                        occurred_count = (occurred_vals == "yes").sum()
                        not_occurred_count = (occurred_vals == "no").sum()
                        other_count = len(eb) - occurred_count - not_occurred_count
                        caption_parts = [f"{len(eb)} BMA instance(s)"]
                        caption_parts.append(f"{occurred_count} occurred")
                        caption_parts.append(f"{not_occurred_count} pending")
                        if other_count > 0:
                            caption_parts.append(f"{other_count} unspecified")
                        st.caption(" · ".join(caption_parts))
                    else:
                        st.caption(f"{len(eb)} BMA instance(s) tagged to this entity")

                    if eb.empty:
                        st.info("No business monitoring activities tagged to this entity")
                    else:
                        bma_display_cols = [c for c in [
                            bma_activity_title_col, bma_instance_col,
                            bma_date_col, bma_occurred_col, bma_cases_col,
                            bma_summary_col, bma_impact_desc_col,
                        ] if c in eb.columns]
                        # Sort: activities that occurred ("Yes") first, then pending ("No")
                        _eb_display = eb[bma_display_cols].copy()
                        if bma_occurred_col in _eb_display.columns:
                            _eb_display["_sort_occurred"] = pd.Categorical(
                                _eb_display[bma_occurred_col].astype(str).str.strip(),
                                categories=["Yes", "No"],
                                ordered=True,
                            )
                            _eb_display = _eb_display.sort_values("_sort_occurred").drop(columns=["_sort_occurred"])
                        st.dataframe(_eb_display.fillna("").reset_index(drop=True),
                                     use_container_width=True,
                                     height=min(300, 35 * (len(_eb_display) + 1)))

                    st.warning("⚠️ Note: It appears not all BM activities across IAG are tagged to an audit entity. "
                               "Review the complete BM Activities source for untagged items.")
                else:
                    st.warning(f"BMA sheet missing '{bma_entity_col}' column")
            else:
                st.info("No BM Activities data in workbook")

            # --- Sub-Risks ---
            st.divider()
            st.subheader("Sub-Risks")
            if sub_risks_df is not None:
                eid_col = next((c for c in ("entity_id", "Audit Entity ID")
                                if c in sub_risks_df.columns), None)
                if eid_col:
                    es = sub_risks_df[sub_risks_df[eid_col].astype(str).str.strip() == selected_entity]
                    st.caption(f"{len(es)} sub-risk(s)")
                    if es.empty:
                        st.info("No sub-risk descriptions for this entity")
                    else:
                        st.dataframe(es.reset_index(drop=True), use_container_width=True,
                                     height=min(300, 35 * (len(es) + 1)))
                else:
                    st.warning("Sub-risks sheet missing entity ID column")
            else:
                st.info("No sub-risk data in workbook")

    # =========================================================================
    # RISK CATEGORY VIEW
    # =========================================================================
    if is_risk_view and selected_l2:
        st.divider()

        # --- Summary metrics ---
        total_entities = filtered["Entity ID"].nunique()
        applicable_mask = filtered["Status"].astype(str).str.contains(
            "Applicable", na=False) & ~filtered["Status"].astype(str).str.contains(
            "Not Applicable|Undetermined", na=False)
        ai_mask = filtered["Decision Basis"].astype(str).str.startswith("AI review") if "Decision Basis" in filtered.columns else pd.Series(False, index=filtered.index)
        evidence_entities = filtered.loc[applicable_mask & ~ai_mask, "Entity ID"].nunique()
        ai_entities = filtered.loc[applicable_mask & ai_mask, "Entity ID"].nunique()
        applicable_entities = filtered.loc[applicable_mask, "Entity ID"].nunique()
        pct = (applicable_entities / total_entities * 100) if total_entities else 0
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Entities", total_entities)
        m2.metric("Evidence-Based", evidence_entities)
        m3.metric("AI-Proposed", ai_entities)
        m4.metric("% Applicable", f"{pct:.0f}%")

        # --- Entity heatmap table ---
        st.header(f"Entity Breakdown: {selected_l2}")
        heat_cols = ["Entity ID"]
        for c in ["Entity Name", "Audit Leader", "Inherent Risk Rating", "Status",
                   "Likelihood", "Overall Impact", "Legacy Source", "Decision Basis",
                   "Additional Signals"]:
            if c in filtered.columns:
                heat_cols.append(c)

        heat_df = filtered[heat_cols].copy()
        heat_df["Status"] = heat_df["Status"].apply(status_label)
        clean_col(heat_df, "Additional Signals")
        if "Inherent Risk Rating" in heat_df.columns:
            heat_df["Inherent Risk Rating"] = heat_df["Inherent Risk Rating"].apply(
                lambda x: str(x) if not is_empty(x) else "—")

        st.dataframe(heat_df.reset_index(drop=True), use_container_width=True,
                      height=min(35 * len(heat_df) + 38, 600),
                      column_config={
                "Entity ID": st.column_config.TextColumn(width="small"),
                "Inherent Risk Rating": st.column_config.TextColumn(width="small"),
                "Status": st.column_config.TextColumn(width="medium"),
                "Decision Basis": st.column_config.TextColumn(width="large"),
                "Additional Signals": st.column_config.TextColumn(width="large"),
            })

        st.divider()

        # --- Concentration chart ---
        st.header("Rating Concentration")
        rating_counts = {}
        if "Inherent Risk Rating" in filtered.columns:
            for val in filtered["Inherent Risk Rating"]:
                val_str = str(val).strip() if not is_empty(val) else "No Rating"
                rating_counts[val_str] = rating_counts.get(val_str, 0) + 1

        if rating_counts:
            ordered = ["Critical", "High", "Medium", "Low", "Not Applicable", "No Rating"]
            chart_data = {r: rating_counts.get(r, 0) for r in ordered if rating_counts.get(r, 0) > 0}
            colors = {"Critical": "#DC3545", "High": "#E8923C", "Medium": "#FFC107",
                       "Low": "#28A745", "Not Applicable": "#6C757D", "No Rating": "#ADB5BD"}
            fig = go.Figure(go.Bar(
                x=list(chart_data.keys()), y=list(chart_data.values()),
                marker_color=[colors.get(r, "#ccc") for r in chart_data.keys()]))
            fig.update_layout(height=300, margin=dict(l=0, r=20, t=10, b=20),
                              yaxis_title="Entities")
            st.plotly_chart(fig, use_container_width=True)

        st.divider()

        # --- Per-entity drill-down ---
        st.header("Entity Drill-Down")
        st.caption(f"Expand any entity for evidence on {selected_l2}")

        for _, row in filtered.iterrows():
            eid = row.get("Entity ID", "")
            status_raw = resolve_status(row.get("Status", ""))
            irr = row.get("Inherent Risk Rating", "")
            irr_display = str(irr) if not is_empty(irr) else "—"
            cfg = STATUS_CONFIG.get(status_raw, {"icon": "❓"})
            ename = str(row.get("Entity Name", "")) if "Entity Name" in row.index else ""
            label_parts = [f"{cfg['icon']} {eid}"]
            if ename and ename != "nan":
                label_parts.append(ename)
            label_parts.append(status_raw)
            if not is_empty(irr) and str(irr) not in ("Not Applicable", "—"):
                label_parts.append(str(irr))
            label = "  ·  ".join(label_parts)

            detail_row = get_detail_row(detail_df, eid, selected_l2)
            # Load entity's full Side_by_Side for sibling context
            entity_detail_for_ctx = (
                detail_df[detail_df["entity_id"].astype(str) == str(eid)]
                if detail_df is not None else None
            )

            with st.expander(label, expanded=False):
                _render_entity_context_compact(row)
                render_drilldown(row, detail_row, status_raw, entity_detail_for_ctx)
                _render_scoped_findings(findings_df, eid, selected_l2)
                _render_scoped_sub_risks(sub_risks_df, eid, detail_row)

        st.divider()

        # --- IAG Issues cross-reference ---
        if findings_df is not None:
            eid_col = next((c for c in ("entity_id", "Audit Entity ID")
                            if c in findings_df.columns), None)
            l2_col = next((c for c in ("l2_risk", "Mapped To L2(s)")
                           if c in findings_df.columns), None)
            if eid_col and l2_col:
                l2f = findings_df[findings_df[l2_col].astype(str).str.contains(
                    selected_l2, na=False)]
                in_scope = set(filtered["Entity ID"].astype(str).unique())
                l2f = l2f[l2f[eid_col].astype(str).isin(in_scope)]
                st.header(f"IAG Issues for {selected_l2}")
                if not l2f.empty:
                    ct = len(l2f)
                    ect = l2f[eid_col].nunique()
                    st.info(f"**{ct} IAG issues** across **{ect} entities** tagged to this L2.")
                    st.dataframe(l2f.fillna("").reset_index(drop=True), use_container_width=True,
                                 height=min(300, 35 * (len(l2f) + 1)))
                else:
                    st.info("No IAG issues tagged to this L2 in the current scope.")


if __name__ == "__main__":
    main()
