"""
Risk Taxonomy Transformer — Audit Leader Dashboard
===================================================
Designed around the audit leader's primary question:
"What needs my decision, and can I trust the rest?"

Layout follows the leader's workflow:
  1. Triage  — What needs my attention, and what ARE those items?
  2. Entity walkthrough — Pick my entity, see all 23 L2s sorted by priority
  3. Drill-down — Expand any row, structured by what the leader needs to DO
  4. Traceability — How legacy pillars fanned out or converged
  5. Source data — Findings and sub-risks for verification

Usage:
    streamlit run dashboard.py
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path

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
# STATUS DEFINITIONS — single source of truth
# =============================================================================

STATUS_CONFIG = {
    "Applicability Undetermined": {"icon": "⚠️", "sort": 0},
    "Assumed Not Applicable":     {"icon": "🔶", "sort": 1},
    "Applicable":                 {"icon": "✅", "sort": 2},
    "Not Applicable":             {"icon": "⬜", "sort": 3},
    "Not Assessed":               {"icon": "🔵", "sort": 4},
}

CONFIDENCE_COLORS = {
    "high": "#28A745",
    "medium": "#E8923C",
    "low": "#DC3545",
    "none": "#6C757D",
}


# =============================================================================
# DATA LOADING
# =============================================================================

@st.cache_data
def load_data(file_path: str) -> dict[str, pd.DataFrame]:
    sheets = {}
    xls = pd.ExcelFile(file_path)
    for name in ["Audit_Review", "Side_by_Side", "Findings_Source", "Sub_Risks_Source"]:
        if name in xls.sheet_names:
            sheets[name] = pd.read_excel(xls, sheet_name=name)
    return sheets


def find_latest_output() -> Path | None:
    files = sorted(OUTPUT_DIR.glob("transformed_risk_taxonomy_*.xlsx"),
                   key=lambda f: f.stat().st_mtime)
    return files[-1] if files else None


# =============================================================================
# HELPERS
# =============================================================================

def is_empty(val) -> bool:
    """Check if a value is empty, NaN, None, or literal 'nan'."""
    if val is None:
        return True
    if isinstance(val, float) and pd.isna(val):
        return True
    return str(val).strip().lower() in ("", "nan", "none")


def rating_display(val) -> str:
    if is_empty(val):
        return None
    v = int(val)
    bars = "█" * v + "░" * (4 - v)
    labels = {1: "Low", 2: "Medium", 3: "High", 4: "Critical"}
    return f"{bars} {v} ({labels.get(v, '')})"


def status_label(status: str) -> str:
    """Status text with emoji prefix for theme-safe visibility."""
    cfg = STATUS_CONFIG.get(status, {"icon": "❓"})
    return f'{cfg["icon"]} {status}'


# =============================================================================
# DRILL-DOWN RENDERERS — structured by what the leader needs to DO
# =============================================================================

def _render_signals(row):
    """Render Additional Signals if present."""
    signals = row.get("Additional Signals", "")
    if is_empty(signals):
        return
    st.markdown("**Additional Signals**")
    for signal in str(signals).split(" | "):
        signal = signal.strip()
        if not signal:
            continue
        if "well controlled" in signal.lower():
            st.error(f"🚨 {signal}")
        elif "application" in signal.lower() or "engagement" in signal.lower():
            st.warning(f"📎 {signal}")
        elif "auxiliary" in signal.lower():
            st.info(f"📌 {signal}")
        else:
            st.write(f"ℹ️ {signal}")


def _render_ratings(row):
    """Render inherited ratings — only if at least one rating exists."""
    rating_fields = [
        ("Likelihood", "Likelihood"),
        ("Impact — Financial", "Impact - Financial"),
        ("Impact — Reputational", "Impact - Reputational"),
        ("Impact — Consumer Harm", "Impact - Consumer Harm"),
        ("Impact — Regulatory", "Impact - Regulatory"),
        ("IAG Control Effectiveness", "IAG Control Effectiveness"),
        ("Aligned Assurance Rating", "Aligned Assurance Rating"),
        ("Management Awareness Rating", "Management Awareness Rating"),
    ]
    displays = [(label, rating_display(row.get(col))) for label, col in rating_fields]
    non_null = [(label, val) for label, val in displays if val is not None]

    if not non_null:
        st.caption("No ratings carried forward — legacy source was N/A or not assessed.")
        return

    st.markdown("**Inherited Ratings** *(starting point — team will adjust)*")
    left, right = st.columns(2)
    mid = len(non_null) // 2 + len(non_null) % 2
    with left:
        for label, val in non_null[:mid]:
            st.write(f"{label}: {val}")
    with right:
        for label, val in non_null[mid:]:
            st.write(f"{label}: {val}")


def _render_evidence(detail_row):
    """Render evidence trail from Side_by_Side if present."""
    evidence = str(detail_row.get("sub_risk_evidence", ""))
    if is_empty(evidence):
        return
    st.markdown("**Evidence Trail** *(keyword matches from rationale and sub-risks)*")
    st.code(evidence, language=None)


def _render_source_rationale(detail_row):
    """Render the source rationale text prominently."""
    rationale = str(detail_row.get("source_rationale", ""))
    if is_empty(rationale):
        return
    st.markdown("**Source Rationale Text**")
    st.markdown(f"> {rationale}")


def _render_technical_detail(detail_row):
    """Render method and dims_parsed behind a secondary expander."""
    method = str(detail_row.get("method", ""))
    dims_parsed = detail_row.get("dims_parsed_from_rationale", False)
    if is_empty(method):
        return
    with st.expander("🔧 Technical Detail", expanded=False):
        st.write(f"Method: `{method}`")
        st.write(f"Dimensions parsed from rationale: {'Yes' if dims_parsed else 'No'}")


def render_drilldown_assumed_na(row, detail_row):
    """Assumed Not Applicable: Leader reads rationale, decides if L2 applies."""
    # Lead with the rationale — this is what the leader needs to evaluate
    if detail_row is not None:
        _render_source_rationale(detail_row)

    st.markdown("**Decision Basis**")
    st.info(str(row.get("Decision Basis", "—")))

    _render_signals(row)
    _render_ratings(row)

    if detail_row is not None:
        _render_technical_detail(detail_row)


def render_drilldown_undetermined(row, detail_row, entity_detail_df):
    """Applicability Undetermined: Leader sees what DID match from same pillar,
    then reads rationale to decide which candidates apply."""
    legacy_source = str(row.get("Legacy Source", ""))

    # Show what other L2s from the same pillar DID match
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
                conf = m.get("confidence", "")
                st.write(f"• ✅ {m['new_l2']} ({conf} confidence)")

    st.markdown("**Decision Basis**")
    st.info(str(row.get("Decision Basis", "—")))

    if detail_row is not None:
        _render_source_rationale(detail_row)

    _render_signals(row)
    _render_ratings(row)

    if detail_row is not None:
        _render_technical_detail(detail_row)


def render_drilldown_applicable(row, detail_row):
    """Applicable: Leader verifies the evidence and checks ratings."""
    # Lead with evidence — this is what justifies the mapping
    if detail_row is not None:
        _render_evidence(detail_row)

    st.markdown("**Decision Basis**")
    st.success(str(row.get("Decision Basis", "—")))

    _render_signals(row)
    _render_ratings(row)

    if detail_row is not None:
        _render_technical_detail(detail_row)


def render_drilldown_informational(row):
    """Not Applicable / Not Assessed: Minimal display — informational only."""
    st.caption(str(row.get("Decision Basis", "—")))
    _render_signals(row)


# =============================================================================
# MAIN APP
# =============================================================================

def main():
    latest = find_latest_output()
    if latest is None:
        st.error("No transformer output found in `data/output/`. Run `risk_taxonomy_transformer.py` first.")
        return

    sheets = load_data(str(latest))
    audit_df = sheets.get("Audit_Review")
    detail_df = sheets.get("Side_by_Side")
    findings_df = sheets.get("Findings_Source")
    sub_risks_df = sheets.get("Sub_Risks_Source")

    if audit_df is None:
        st.error("Audit_Review sheet not found.")
        return

    # =========================================================================
    # SIDEBAR
    # =========================================================================
    with st.sidebar:
        st.header("📋 Risk Taxonomy Review")
        st.caption(f"Source: {latest.name}")
        st.divider()

        entities = sorted(audit_df["Entity ID"].unique())
        entity_options = ["── All Entities ──"] + list(entities)
        selected_entity = st.selectbox("Select Audit Entity", entity_options, index=0)

        st.divider()
        st.subheader("Filters")
        all_statuses = list(STATUS_CONFIG.keys())
        selected_statuses = st.multiselect(
            "Status", options=all_statuses, default=all_statuses,
            label_visibility="collapsed",
        )
        show_signals_only = st.checkbox("Only rows with Additional Signals")
        show_action_only = st.checkbox("Only items requiring attention")

    # Apply filters
    filtered = audit_df.copy()
    is_entity_view = selected_entity != "── All Entities ──"

    if is_entity_view:
        filtered = filtered[filtered["Entity ID"] == selected_entity]
    filtered = filtered[filtered["Status"].isin(selected_statuses)]

    if show_signals_only and "Additional Signals" in filtered.columns:
        filtered = filtered[
            filtered["Additional Signals"].apply(lambda x: not is_empty(x))
        ]
    if show_action_only:
        filtered = filtered[filtered["Status"].isin([
            "Applicability Undetermined", "Assumed Not Applicable"
        ])]

    # Add sort key
    filtered = filtered.copy()
    filtered["_status_sort"] = filtered["Status"].map(
        {s: cfg["sort"] for s, cfg in STATUS_CONFIG.items()}
    ).fillna(99)
    filtered = filtered.sort_values(["Entity ID", "_status_sort", "New L2"])

    # =========================================================================
    # SECTION 1: TRIAGE
    # One banner answers "how many need attention."
    # Below it: a compact table of WHAT those items are — not just counts.
    # =========================================================================
    if is_entity_view:
        st.title(f"Entity: {selected_entity}")
    else:
        st.title("Portfolio Overview")
        st.caption(f"{audit_df['Entity ID'].nunique()} entities · {len(audit_df)} total mappings")

    undetermined = filtered[filtered["Status"] == "Applicability Undetermined"]
    assumed_na = filtered[filtered["Status"] == "Assumed Not Applicable"]
    action_total = len(undetermined) + len(assumed_na)

    if action_total > 0:
        st.warning(
            f"**{action_total} items require attention** — "
            f"{len(undetermined)} applicability undetermined, "
            f"{len(assumed_na)} assumed not applicable (verify or override)"
        )

        # Show WHAT the action items are — not just how many
        st.subheader("Action Items")
        action_items = pd.concat([undetermined, assumed_na])
        action_display = action_items[[
            "Entity ID", "New L1", "New L2", "Status", "Legacy Source"
        ]].copy() if "Legacy Source" in action_items.columns else action_items[[
            "Entity ID", "New L1", "New L2", "Status"
        ]].copy()
        action_display["Status"] = action_display["Status"].apply(status_label)
        st.dataframe(action_display.reset_index(drop=True), use_container_width=True,
                      height=min(35 * len(action_display) + 38, 400))
    else:
        st.success("**No items require attention** — all mappings determined automatically")

    # Confidence chart — only if there's variance to show
    if action_total > 0:
        conf_counts = pd.concat([undetermined, assumed_na])["Confidence"].value_counts()
        if len(conf_counts) > 1:
            fig_conf = go.Figure(go.Pie(
                labels=conf_counts.index,
                values=conf_counts.values,
                marker_colors=[CONFIDENCE_COLORS.get(str(c).lower(), "#ccc") for c in conf_counts.index],
                hole=0.4,
            ))
            fig_conf.update_layout(
                title="Confidence Distribution (Action Items)",
                height=280,
                margin=dict(l=0, r=0, t=40, b=20),
            )
            st.plotly_chart(fig_conf, use_container_width=True)

    st.divider()

    # =========================================================================
    # SECTION 2: RISK PROFILE TABLE
    # No background colors — uses emoji status indicators for theme safety.
    # Action items sort to top. Rating Source removed (too verbose for overview).
    # =========================================================================
    if is_entity_view:
        st.header("Risk Profile — All L2 Risks")
    else:
        st.header("Filtered Results")

    # Build display table with emoji status
    overview_cols = ["Entity ID", "New L1", "New L2", "Status", "Confidence", "Decision Basis"]
    if "Additional Signals" in filtered.columns:
        overview_cols.append("Additional Signals")
    overview_cols = [c for c in overview_cols if c in filtered.columns]

    display_df = filtered[overview_cols].copy()
    display_df["Status"] = display_df["Status"].apply(status_label)

    # Clean Additional Signals — hide nan
    if "Additional Signals" in display_df.columns:
        display_df["Additional Signals"] = display_df["Additional Signals"].apply(
            lambda x: "" if is_empty(x) else str(x)
        )

    st.dataframe(display_df.reset_index(drop=True), use_container_width=True, height=500)

    st.divider()

    # =========================================================================
    # SECTION 3: DRILL-DOWN — structured by status type
    # Each status gets a different drill-down layout matching what the
    # leader needs to DO with that row.
    # =========================================================================
    if is_entity_view:
        st.header("Drill-Down by L2 Risk")
        st.caption("Expand any L2 to see evidence and context. Action items auto-expand.")

        # Get entity detail from Side_by_Side
        entity_detail = None
        if detail_df is not None:
            entity_detail = detail_df[detail_df["entity_id"].astype(str) == selected_entity]

        for _, row in filtered.iterrows():
            l2 = row.get("New L2", "")
            status_raw = row.get("Status", "")
            # Recover raw status from the emoji-prefixed display
            for s in STATUS_CONFIG:
                if s in status_raw:
                    status_raw = s
                    break
            confidence = row.get("Confidence", "")
            cfg = STATUS_CONFIG.get(status_raw, {"icon": "❓", "sort": 99})

            label = f"{cfg['icon']} {row.get('New L1', '')} / {l2}  ·  {status_raw}  ·  {confidence} confidence"
            expanded = status_raw in ("Applicability Undetermined", "Assumed Not Applicable")

            # Get matching detail row
            detail_row = None
            if entity_detail is not None and not entity_detail.empty:
                match = entity_detail[entity_detail["new_l2"] == l2]
                if not match.empty:
                    detail_row = match.iloc[0]

            with st.expander(label, expanded=expanded):
                if status_raw == "Assumed Not Applicable":
                    render_drilldown_assumed_na(row, detail_row)
                elif status_raw == "Applicability Undetermined":
                    render_drilldown_undetermined(row, detail_row, entity_detail)
                elif status_raw == "Applicable":
                    render_drilldown_applicable(row, detail_row)
                else:
                    render_drilldown_informational(row)

        st.divider()

    # =========================================================================
    # SECTION 4: LEGACY → NEW TRACEABILITY
    # Audit trail — verifying completeness, not making decisions.
    # Fan-out: did the legacy rating get adequately covered by new L2s?
    # Convergence: when pillars collided on the same L2, what was kept?
    # =========================================================================
    if is_entity_view and detail_df is not None:
        entity_detail_df = detail_df[detail_df["entity_id"].astype(str) == selected_entity]

        if not entity_detail_df.empty and "source_legacy_pillar" in entity_detail_df.columns:
            st.header("Legacy → New Traceability")

            # --- Helper: extract base pillar name from dedup annotations ---
            def base_pillar(source_str):
                """'Operational (also: Compliance)' → 'Operational'"""
                return str(source_str).split(" (also")[0].strip()

            # --- Helper: derive status from method (mirrors _derive_status) ---
            def method_to_status(method):
                m = str(method)
                if "source_not_applicable" in m:
                    return "Not Applicable"
                if "evaluated_no_evidence" in m:
                    return "Assumed Not Applicable"
                if "no_evidence_all_candidates" in m:
                    return "Applicability Undetermined"
                if "true_gap_fill" in m or "gap_fill" in m:
                    return "Not Assessed"
                if ("direct" in m or "evidence_match" in m
                        or "llm_override" in m or "issue_confirmed" in m
                        or "dedup" in m):
                    return "Applicable"
                return "Applicability Undetermined"

            def status_icon(status):
                return STATUS_CONFIG.get(status, {"icon": "❓"})["icon"]

            # --- FAN-OUT ---
            # Group rows by their BASE pillar (strip dedup annotations)
            # Only show pillars that map to multiple L2s (skip 1:1 directs)
            st.subheader("Multi-Mapping Fan-Out")
            st.caption("How each legacy pillar's rating was distributed across new L2 risks")

            entity_detail_df = entity_detail_df.copy()
            entity_detail_df["_base_pillar"] = entity_detail_df["source_legacy_pillar"].apply(base_pillar)

            # Get unique base pillars, excluding Findings and blank
            base_pillars = sorted([
                p for p in entity_detail_df["_base_pillar"].unique()
                if p and p not in ("", "nan", "None", "Findings")
            ])

            for pillar in base_pillars:
                pillar_rows = entity_detail_df[entity_detail_df["_base_pillar"] == pillar]

                # Skip 1:1 mappings — no fan to show
                if len(pillar_rows) <= 1:
                    continue

                # Get the original rating for this pillar
                raw_rating = pillar_rows["source_risk_rating_raw"].dropna().unique()
                rating_str = str(raw_rating[0]) if len(raw_rating) > 0 else "unknown"

                # Count statuses for the summary label
                statuses = pillar_rows["method"].apply(method_to_status)
                status_counts = statuses.value_counts()

                summary_parts = []
                for s in ["Applicable", "Applicability Undetermined", "Assumed Not Applicable",
                           "Not Applicable", "Not Assessed"]:
                    count = status_counts.get(s, 0)
                    if count > 0:
                        icon = status_icon(s)
                        # Short labels for the summary
                        short = {
                            "Applicable": "applicable",
                            "Applicability Undetermined": "undetermined",
                            "Assumed Not Applicable": "assumed N/A",
                            "Not Applicable": "N/A",
                            "Not Assessed": "not assessed",
                        }.get(s, s.lower())
                        summary_parts.append(f"{count} {icon} {short}")

                label = f"📂 {pillar} (rated {rating_str}) → {', '.join(summary_parts)}"

                with st.expander(label):
                    for _, pr in pillar_rows.iterrows():
                        l2 = pr.get("new_l2", "")
                        method = str(pr.get("method", ""))
                        status = method_to_status(method)
                        icon = status_icon(status)
                        conf = pr.get("confidence", "")

                        # Build a readable method description
                        if "evidence_match" in method:
                            how = "keyword evidence matched"
                        elif "issue_confirmed" in method:
                            how = "confirmed by open finding"
                        elif "direct" in method:
                            how = "direct mapping"
                        elif "source_not_applicable" in method:
                            how = "source rated N/A"
                        elif "evaluated_no_evidence" in method:
                            how = "no evidence found"
                        elif "no_evidence_all_candidates" in method:
                            how = "no evidence — all candidates populated"
                        else:
                            how = method

                        st.write(f"{icon} **{l2}** — {status} ({how}, {conf} confidence)")

            # --- CONVERGENCE / DEDUP ---
            # Show L2s where multiple legacy pillars competed
            dedup_rows = entity_detail_df[
                entity_detail_df["source_legacy_pillar"].astype(str).str.contains("also:", na=False)
            ]
            if not dedup_rows.empty:
                st.subheader("Convergence (Deduplication)")
                st.caption(
                    "L2 risks where multiple legacy pillars mapped to the same target. "
                    "The tool kept the higher-priority or higher-rated source."
                )

                resolution_rows = []
                for _, dr in dedup_rows.iterrows():
                    l2 = dr.get("new_l2", "")
                    source_raw = str(dr.get("source_legacy_pillar", ""))
                    method = str(dr.get("method", ""))
                    rating = dr.get("source_risk_rating_raw", "")
                    status = method_to_status(method)

                    # Parse contributing pillars from "(also: X) (also: Y)"
                    primary = source_raw.split(" (also:")[0].strip()
                    also_parts = []
                    remainder = source_raw
                    while "(also:" in remainder:
                        start = remainder.index("(also:") + 6
                        end = remainder.index(")", start)
                        also_parts.append(remainder[start:end].strip())
                        remainder = remainder[end + 1:]

                    all_sources = [primary] + also_parts
                    sources_str = " + ".join(all_sources)

                    # Build resolution summary
                    rating_str = str(rating) if not is_empty(rating) else "no rating"

                    if "issue_confirmed" in method:
                        resolution = f"Kept as {status} — confirmed by finding"
                    elif "dedup: kept higher" in method:
                        resolution = f"Kept {primary} rating ({rating_str}) — higher than other source(s)"
                    elif "source_not_applicable" in method:
                        resolution = f"Kept as Not Applicable — all sources were N/A"
                    elif "evaluated_no_evidence" in method:
                        resolution = f"Kept as Assumed Not Applicable — no evidence from any source"
                    elif "evidence_match" in method:
                        resolution = f"Kept {primary} ({rating_str}) — had keyword evidence"
                    elif "direct" in method:
                        resolution = f"Kept {primary} ({rating_str}) — direct mapping took priority"
                    else:
                        resolution = f"Resolved to {status} ({rating_str})"

                    resolution_rows.append({
                        "L2 Risk": l2,
                        "Contributing Pillars": sources_str,
                        "Kept Rating": rating_str,
                        "Resolution": resolution,
                    })

                resolution_df = pd.DataFrame(resolution_rows)
                st.dataframe(resolution_df, use_container_width=True)

        st.divider()

    # =========================================================================
    # SECTION 5: SOURCE DATA — Findings and Sub-Risks
    # =========================================================================
    if is_entity_view:
        source_left, source_right = st.columns(2)

        with source_left:
            if findings_df is not None:
                eid_col = next((c for c in ("entity_id", "Audit Entity ID") if c in findings_df.columns), None)
                if eid_col:
                    entity_findings = findings_df[findings_df[eid_col].astype(str).str.strip() == selected_entity]
                    st.header(f"Findings ({len(entity_findings)})")
                    if entity_findings.empty:
                        st.info("No findings for this entity")
                    else:
                        if "Disposition" in entity_findings.columns:
                            disp = entity_findings["Disposition"].value_counts()
                            for d, count in disp.items():
                                st.write(f"• {d}: **{count}**")
                        st.dataframe(entity_findings.reset_index(drop=True),
                                     use_container_width=True, height=300)

        with source_right:
            if sub_risks_df is not None:
                eid_col = next((c for c in ("entity_id", "Audit Entity ID") if c in sub_risks_df.columns), None)
                if eid_col:
                    entity_subs = sub_risks_df[sub_risks_df[eid_col].astype(str).str.strip() == selected_entity]
                    st.header(f"Sub-Risks ({len(entity_subs)})")
                    if entity_subs.empty:
                        st.info("No sub-risk descriptions for this entity")
                    else:
                        st.dataframe(entity_subs.reset_index(drop=True),
                                     use_container_width=True, height=300)

    # =========================================================================
    # SECTION 6: PORTFOLIO VIEWS — only when viewing all entities
    # =========================================================================
    if not is_entity_view:
        st.header("Portfolio Analysis")

        action_df = audit_df[audit_df["Status"].isin([
            "Applicability Undetermined", "Assumed Not Applicable"
        ])]

        if not action_df.empty:
            analysis_left, analysis_right = st.columns(2)

            with analysis_left:
                st.subheader("L2s Requiring Most Team Decisions")
                l2_action = action_df.groupby("New L2")["Entity ID"].nunique().sort_values(ascending=True)
                fig_l2 = go.Figure(go.Bar(
                    x=l2_action.values,
                    y=l2_action.index,
                    orientation="h",
                    marker_color="#E8923C",
                ))
                fig_l2.update_layout(
                    height=max(300, len(l2_action) * 25),
                    margin=dict(l=0, r=20, t=10, b=20),
                    xaxis_title="Entities needing decision",
                )
                st.plotly_chart(fig_l2, use_container_width=True)

            with analysis_right:
                st.subheader("Entities Requiring Most Decisions")
                entity_action = action_df.groupby("Entity ID").size().sort_values(ascending=False).head(20)
                fig_entity = go.Figure(go.Bar(
                    x=entity_action.index,
                    y=entity_action.values,
                    marker_color="#FFC107",
                ))
                fig_entity.update_layout(
                    height=300,
                    margin=dict(l=0, r=20, t=10, b=20),
                    yaxis_title="Action items",
                )
                st.plotly_chart(fig_entity, use_container_width=True)

        # Signals summary
        if "Additional Signals" in audit_df.columns:
            signals_df = audit_df[audit_df["Additional Signals"].apply(lambda x: not is_empty(x))]
            if not signals_df.empty:
                st.subheader(f"Additional Signals Across Portfolio ({len(signals_df)} rows)")
                sig1, sig2, sig3 = st.columns(3)
                with sig1:
                    ct = signals_df["Additional Signals"].str.contains("Well Controlled", na=False).sum()
                    st.metric("🚨 Control Contradictions", ct)
                with sig2:
                    ct = signals_df["Additional Signals"].str.contains("application|engagement", case=False, na=False).sum()
                    st.metric("📎 App/Engagement Flags", ct)
                with sig3:
                    ct = signals_df["Additional Signals"].str.contains("auxiliary", case=False, na=False).sum()
                    st.metric("📌 Auxiliary Risk Flags", ct)


if __name__ == "__main__":
    main()
