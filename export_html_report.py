"""
Static HTML Report Generator (AmEx Branded)

Reads the transformer's Excel output and generates a self-contained, brand-styled
HTML file that can be uploaded to SharePoint and opened in any browser.

Aligned with the Streamlit dashboard (dashboard.py) - same views, same data,
same drill-down logic.

Usage:
    python export_html_report.py                      # uses latest output
    python export_html_report.py path/to/output.xlsx  # specific file

Or called from the transformer:
    from export_html_report import generate_html_report
    generate_html_report(excel_path, html_path)
"""

import pandas as pd
import json
import sys
import yaml
from pathlib import Path
from datetime import datetime

_PROJECT_ROOT = Path(__file__).parent
_CONFIG_PATH = _PROJECT_ROOT / "config" / "taxonomy_config.yaml"


def _safe_json(df: pd.DataFrame) -> str:
    """Convert DataFrame to JSON string, handling NaN and special types."""
    return df.fillna("").to_json(orient="records")


def _load_inventory(input_dir: Path, pattern: str) -> pd.DataFrame:
    """Load the most recent file matching pattern. Return empty DataFrame if none found."""
    matches = sorted(input_dir.glob(pattern))
    if not matches:
        print(f"  Warning: no files match pattern '{pattern}' - inventory will be empty")
        return pd.DataFrame()
    latest = max(matches, key=lambda p: p.stat().st_mtime)
    try:
        return pd.read_excel(latest)
    except Exception:
        return pd.DataFrame()


# ========================================================================
# COLUMN ALLOWLISTS
# Every DataFrame embedded as JSON is pruned to just the columns the JS
# reads. Each allowlist is the union of every column name referenced in
# the _JS template for the corresponding data source (including snake_case
# / Title Case fallback pairs).
# ========================================================================

ENTITY_META_COLS = [
    "Entity Name", "Entity Overview", "Audit Leader", "PGA", "Core Audit Team",
]

AUDIT_COLS = [
    "Entity ID", "New L1", "New L2",
    "Status", "Confidence", "Inherent Risk Rating",
    "Likelihood", "Overall Impact",
    "Legacy Source", "Decision Basis", "Additional Signals",
    "Control Effectiveness Baseline", "Impact of Issues", "Control Signals",
    "IAG Control Effectiveness", "Aligned Assurance Rating", "Management Awareness Rating",
]

DETAIL_COLS = [
    "entity_id", "new_l2",
    "source_legacy_pillar", "source_risk_rating_raw", "source_rationale",
    "method",
]

FINDINGS_COLS = [
    "entity_id", "Audit Entity ID",
    "issue_id", "Finding ID",
    "issue_title", "Finding Name",
    "Finding Description", "finding_description",
    "severity", "Final Reportable Finding Risk Rating",
    "status", "Finding Status",
    "l2_risk", "Mapped To L2(s)", "Risk Dimension Categories",
    "Mapping Status",
]

SUB_RISKS_COLS = [
    "entity_id", "Audit Entity", "Audit Entity ID",
    "legacy_l1", "Level 1 Risk Category",
    "risk_id", "Key Risk ID",
    "risk_description", "Key Risk Description",
    "sub_risk_rating", "Inherent Risk Rating",
    "L2 Keyword Matches", "Contributed To (keyword matches)",
]

ORE_COLS = [
    "entity_id", "Audit Entity (Operational Risk Events)", "Audit Entity ID",
    "Event ID", "Event Title", "Event Description",
    "Final Event Classification", "Event Status",
    "Mapped L2s", "l2_risk",
    "Mapping Status",
]

PRSA_COLS = [
    "AE ID", "Audit Entity", "Audit Entity ID",
    "PRSA ID", "Issue ID", "Issue Title", "Issue Description",
    "Control Title", "Process Title",
    "Issue Rating", "Issue Status",
    "Control ID (PRSA)", "Other AEs With This PRSA",
    "Mapped L2s", "Mapping Status",
]

BMA_COLS = [
    "Related Audit Entity", "Audit Entity ID",
    "Activity Instance ID", "Related BM Activity Title",
    "Summary of Results", "If yes, please describe impact",
    "Business Monitoring Cases", "Planned Instance Completion Date",
]

GRA_RAPS_COLS = [
    "Audit Entity ID",
    "RAP ID", "RAP Header", "RAP Status",
    "BU Corrective Action Due Date", "RAP Details",
    "Related Exams and Findings", "GRA RAPS",
    "Mapped L2s", "Mapping Status",
]

LEGACY_RATINGS_COLS = [
    "Entity ID", "Audit Entity ID",
    "Risk Pillar",
    "Inherent Risk Rating", "Inherent Risk Rationale",
    "Control Assessment", "Control Assessment Rationale",
]

LEGACY_STATIC_COLS = [
    "Audit Entity ID",
    "Hand-offs from Other Audit Entities",
    "Hand-offs to Other Audit Entities",
    "Hand-off Description",
    "Models (View Only)",
]


def _project_cols(df: pd.DataFrame, allowlist) -> pd.DataFrame:
    """Return df restricted to columns from allowlist that actually exist."""
    if df.empty:
        return df
    keep = [c for c in allowlist if c in df.columns]
    return df[keep]


def _collect_inventory_ids(legacy_df: pd.DataFrame, id_columns) -> set:
    """Union of IDs referenced across the named legacy columns (newline/semicolon split)."""
    ids = set()
    if legacy_df is None or legacy_df.empty:
        return ids
    import re
    for col in id_columns:
        if col not in legacy_df.columns:
            continue
        for val in legacy_df[col].dropna().tolist():
            s = str(val).strip()
            if not s or s.lower() == "nan":
                continue
            for part in re.split(r"[;\r\n]+", s):
                part = part.strip()
                if part and part.lower() not in ("nan", "none", "n/a", "not applicable", "not available"):
                    ids.add(part)
    return ids


def _filter_inventory(df: pd.DataFrame, id_column: str, id_set: set) -> pd.DataFrame:
    """Keep only rows whose id_column value is in id_set. Empty id_set => empty df."""
    if df is None or df.empty or not id_column or id_column not in df.columns:
        return df
    if not id_set:
        return df.iloc[0:0]
    mask = df[id_column].astype(str).str.strip().isin(id_set)
    return df[mask]



# ========================================================================
# EMBEDDED ASSETS (CSS / HTML body template / JS)
# Module-level string literals. Placeholders (__NAME__) are substituted
# at render time inside generate_html_report().
# ========================================================================

_CSS = r"""
/* ================================================================
   Streamlit-Inspired Visual Theme
   ================================================================ */
:root {
    /* Base */
    --bg: #ffffff; --fg: #31333F; --bg2: #f0f2f6; --border: #e6e9ef;
    --accent: #ff4b4b; --primary: #ff4b4b; --blue: #1f77b4;
    --gray: #808495; --gray-light: #bfc5d3;
    --row-alt: #f8f9fb; --hover-row: #eef1f8;
    --sidebar-bg: #f0f2f6;
    --font: "Source Sans Pro", sans-serif;
    --font-mono: "Source Code Pro", "SF Mono", "Cascadia Code", monospace;

    /* Callout palette (one system for banners / boxes / status callouts) */
    --success-bg: #dff0d8; --success-border: #0e8a16; --success-fg: #0e5c2f;
    --warning-bg: #fff3cd; --warning-border: #ffad1f; --warning-fg: #664d03;
    --info-bg: #d1ecf1; --info-border: #0c5460; --info-fg: #0c5460;
    --error-bg: #f8d7da; --error-border: #ff4b4b; --error-fg: #842029;

    /* Pill palette (severity tiers) - shared by severity, ORE class,
       control rating, and IAG status via makePill(). See JS PILL_PALETTES. */
    --pill-sev-critical-bg: #FCEBEB; --pill-sev-critical-fg: #791F1F;
    --pill-sev-high-bg:     #FAD8C1; --pill-sev-high-fg:     #7A2E0F;
    --pill-sev-medium-bg:   #FAEEDA; --pill-sev-medium-fg:   #633806;
    --pill-sev-low-bg:      #EAF3DE; --pill-sev-low-fg:      #27500A;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: var(--font); background: var(--bg); color: var(--fg); line-height: 1.6; font-size: 14px; }

/* -- Header bar -- */
.report-header {
    background: #262730; color: #fafafa; padding: 16px 32px;
    display: flex; align-items: center; gap: 16px; border-bottom: 1px solid #3d3d4e;
}
.header-info h1 {
    font-family: var(--font); font-size: 1.25em; font-weight: 700; color: #fafafa;
}
.header-info .sub { color: rgba(250,250,250,0.5); font-size: 0.82em; margin-top: 2px; font-weight: 400; }

/* -- Layout -- */
.wrap { margin: 0 auto; padding: 0; }
.sidebar-layout { display: flex; gap: 0; min-height: calc(100vh - 60px); }
.sidebar {
    width: 260px; flex-shrink: 0; position: sticky; top: 0; max-height: calc(100vh - 60px); overflow-y: auto;
    padding: 24px 20px; background: var(--sidebar-bg); border-right: 1px solid var(--border);
}
.main-content { flex: 1; min-width: 0; padding: 24px 32px; }

/* -- Headings -- */
h2 {
    margin: 28px 0 12px; color: var(--fg);
    font-family: var(--font); font-weight: 700; font-size: 1.25em;
    border-bottom: none; padding-bottom: 0;
}
h3 { margin: 18px 0 8px; color: var(--fg); font-weight: 600; font-size: 1em; }

/* -- Sub-tabs (Streamlit st.tabs style) -- */
.sub-tabs {
    display: flex; gap: 0; border-bottom: 1px solid var(--border); margin-bottom: 20px;
}
.sub-tab {
    padding: 10px 20px; cursor: pointer; border: none;
    border-bottom: 2px solid transparent; background: transparent;
    color: var(--gray); font-weight: 400; font-size: 0.9em; transition: all 0.15s;
    font-family: var(--font);
}
.sub-tab.active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }
.sub-tab:hover { color: var(--fg); }
.sub-tab-content { display: none; }
.sub-tab-content.active { display: block; }

/* ================================================================
   Tables -- shared base + per-context tweaks
   Base: bare <table>. Data tables (built via buildTableHTML / makeTable)
   get .data-table, which opts them into sortable headers, cell-expand,
   and column-resize. Tables that are pure label/value or compact
   reference use per-context classes below without .data-table.
   Overrides: .rating-table, .md-table, .drill-findings-table, .legacy-table
   ================================================================ */
table { width: 100%; border-collapse: collapse; font-size: 13px; margin: 8px 0; table-layout: fixed; }
th {
    background: var(--bg2); color: var(--fg); padding: 8px 12px; text-align: left;
    position: sticky; top: 0; user-select: none;
    font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px;
    border-bottom: 2px solid var(--border); overflow: hidden; text-overflow: ellipsis;
    white-space: nowrap; position: relative;
}
.data-table th { cursor: pointer; }
.data-table th:hover { background: #e4e7ed; }
th.th-tool { background: #e3f2fd; }
.data-table th.th-tool:hover { background: #d0e7fa; }
.data-table tbody td { cursor: pointer; }
th .col-resize {
    position: absolute; right: 0; top: 0; bottom: 0; width: 5px;
    cursor: col-resize; z-index: 2;
}
th .col-resize:hover, th .col-resize.active { background: var(--accent); opacity: 0.6; }
td {
    padding: 8px 12px; border-bottom: 1px solid var(--border); vertical-align: top;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    max-width: 0; cursor: default;
}
td.cell-expanded {
    white-space: normal; word-wrap: break-word; overflow: visible;
    background: #fffde7; outline: 2px solid #ffcc02; z-index: 1; position: relative;
}
tr:nth-child(even) { background: var(--row-alt); }
tr:hover { background: var(--hover-row); }
.table-wrap {
    max-height: 600px; overflow: auto; border: 1px solid var(--border);
    border-radius: 8px; background: var(--bg);
}

/* Rating table (drill-down): label/value pairs, no borders */
.rating-table { width: auto; border-collapse: collapse; margin: 6px 0 10px; }
.rating-table td {
    padding: 3px 16px 3px 0; border: none; white-space: nowrap;
    vertical-align: top; max-width: none; cursor: default;
}
.rating-table td:first-child {
    color: var(--gray); font-weight: 600; font-size: 13px;
    text-transform: uppercase; letter-spacing: 0.3px;
}
.rating-table .breakdown { color: var(--gray); font-size: 12px; font-weight: 400; display: block; margin-top: 2px; text-transform: none; letter-spacing: 0; white-space: normal; }

/* Drill-down findings mini-table: wraps content, fixed layout.
   Although this is a .data-table (sortable), cells don't benefit from
   click-to-expand since content already wraps, so keep default cursor. */
.drill-findings-table { width: 100%; border-collapse: collapse; font-size: 13px; margin: 4px 0; table-layout: fixed; }
.drill-findings-table th, .drill-findings-table td {
    padding: 6px 10px; border-bottom: 1px solid var(--border);
    vertical-align: top; line-height: 1.4;
    white-space: normal; overflow: visible; text-overflow: clip;
    max-width: none; word-wrap: break-word;
}
.data-table.drill-findings-table tbody td { cursor: default; }
.drill-findings-table td.cell-expanded { background: transparent; outline: none; }
.drill-findings-table th {
    background: var(--bg2); text-align: left; font-weight: 600;
    font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;
    border-bottom: 2px solid var(--border);
}

/* Markdown-style table (used in risk view) */
.md-table { width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 13px; table-layout: fixed; }
.md-table th {
    background: var(--bg2); color: var(--fg); padding: 10px 12px; text-align: left;
    font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px;
    border-bottom: 2px solid var(--border);
}
.md-table td { padding: 10px 12px; border-bottom: 1px solid var(--border); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 0; }
.md-table td.cell-expanded { white-space: normal; word-wrap: break-word; overflow: visible; background: #fffde7; outline: 2px solid #ffcc02; }
.md-table tr:nth-child(even) { background: var(--row-alt); }

/* Legacy Profile table: wraps content */
.legacy-table { table-layout: fixed; width: 100%; border-collapse: collapse; font-size: 13px; margin: 8px 0; }
.legacy-table th, .legacy-table td {
    padding: 8px 12px; border-bottom: 1px solid var(--border);
    vertical-align: top; line-height: 1.5;
    white-space: normal; overflow: visible; text-overflow: clip;
    word-wrap: break-word; max-width: none; cursor: default;
}
.legacy-table th {
    background: var(--bg2); text-align: left; font-weight: 600;
    font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px;
    border-bottom: 2px solid var(--border);
}
.legacy-table tr:nth-child(even) { background: var(--row-alt); }

/* -- Form controls (Streamlit widget style) -- */
select {
    padding: 6px 12px; border: 1px solid var(--border); border-radius: 6px;
    background: var(--bg); color: var(--fg); font-size: 14px; font-family: var(--font);
    min-width: 200px; outline: none; transition: border-color 0.2s;
}
select:focus { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
.filters { display: flex; gap: 15px; flex-wrap: wrap; align-items: center; margin: 10px 0 15px; }
.filters label { font-weight: 600; font-size: 13px; color: var(--fg); display: flex; flex-direction: column; gap: 4px; }

/* -- Sidebar controls -- */
.sidebar h3 { font-size: 15px; margin: 0 0 4px; font-weight: 700; color: var(--fg); }
.sidebar label { display: block; font-weight: 600; font-size: 13px; color: var(--fg); margin-bottom: 4px; }
.sidebar select { width: 100%; margin-bottom: 14px; font-size: 13px; padding: 7px 10px; }
.sidebar .divider { border-top: 1px solid var(--border); margin: 16px 0; }
.view-radio { display: flex; flex-direction: column; gap: 2px; margin: 8px 0; }
.view-radio label {
    font-weight: 400; cursor: pointer; display: flex; align-items: center; gap: 8px;
    padding: 6px 8px; border-radius: 6px; transition: background 0.15s; font-size: 13px;
}
.view-radio label:hover { background: #e4e7ed; }
.view-radio input { accent-color: var(--accent); }
.filter-group { margin-bottom: 8px; }
.filter-group select { width: 100%; }
.filter-group label { font-size: 12px; }
.checkbox-group { display: flex; flex-direction: column; gap: 2px; }
.checkbox-group label {
    font-weight: 400; font-size: 12px; cursor: pointer;
    display: flex; align-items: center; gap: 6px;
    padding: 4px 6px; border-radius: 4px;
}
.checkbox-group label:hover { background: #e4e7ed; }

/* ================================================================
   Unified callouts -- one system for all inline status messages.
   Renamed box variants (.info-box, .warning-box, .success-box,
   .error-box) are gone; use banner-* everywhere.
   ================================================================ */
.banner {
    padding: 16px 20px; border-radius: 0 8px 8px 0; margin: 12px 0;
    font-size: 14px; line-height: 1.5;
}
.banner-ok     { background: var(--success-bg); border-left: 4px solid var(--success-border); color: var(--success-fg); }
.banner-warn   { background: var(--warning-bg); border-left: 4px solid var(--warning-border); color: var(--warning-fg); }
.banner-info   { background: var(--info-bg);    border-left: 4px solid var(--info-border);    color: var(--info-fg); }
.banner-danger { background: var(--error-bg);   border-left: 4px solid var(--error-border);   color: var(--error-fg); }

/* -- Metrics -- */
.metrics { display: flex; gap: 12px; margin: 16px 0; flex-wrap: wrap; }
.metric-card {
    background: var(--bg); border: 1px solid var(--border); border-radius: 8px;
    padding: 14px 20px; min-width: 130px; flex: 1;
}
.metric-card .value { font-size: 2em; font-weight: 700; color: var(--fg); line-height: 1.1; font-family: var(--font); }
.metric-card .label { font-size: 13px; color: var(--gray); margin-top: 2px; font-weight: 400; }

/* -- Expanders -- */
.expander { border: 1px solid var(--border); border-radius: 8px; margin: 8px 0; overflow: hidden; }
.expander-header {
    padding: 12px 16px; cursor: pointer; font-weight: 400; font-size: 14px;
    display: flex; justify-content: space-between; align-items: center;
    transition: background 0.15s;
}
.expander-header:hover { background: var(--bg2); }
.expander-body {
    display: none; padding: 16px 20px; border-top: 1px solid var(--border);
    font-size: 14px; background: var(--bg);
}
.expander.open .expander-body { display: block; }
.expander-arrow { transition: transform 0.2s; color: var(--gray); font-size: 12px; }
.expander.open .expander-arrow { transform: rotate(90deg); }

/* -- Signals -- */
.signal { padding: 3px 0; font-size: 14px; }
.signal-control { color: #842029; font-weight: 600; }
.signal-meta { color: var(--gray); }

/* -- Drill-down sections -- */
.drill-section { margin: 10px 0; }
.drill-section .label { color: var(--fg); font-weight: 500; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; display: block; }
.drill-inline-meta { color: var(--gray); font-size: 13px; margin: 4px 0; }

/* Drill-down sub-risk list */
.subrisk-row { display: flex; gap: 10px; padding: 2px 0; align-items: baseline; }
.subrisk-id { font-family: var(--font-mono); font-size: 12px; color: var(--gray-light); min-width: 50px; }
.subrisk-name { color: var(--fg); font-size: 13px; }

/* Drill-down Additional Signals */
.signal-row { padding: 4px 0; font-size: 13px; color: var(--fg); }
.signal-tag {
    display: inline-block; font-size: 11px; padding: 1px 7px;
    border-radius: 4px; background: var(--bg2); color: var(--gray);
    margin-right: 6px; vertical-align: baseline;
}
.signal-ids { font-family: var(--font-mono); font-size: 12px; color: var(--gray-light); margin: 0 2px; }
.signal-hint { color: var(--gray); }
.signal-contradiction { color: #842029; font-weight: 600; }

/* Drill-down count chips */
.count-chips { display: flex; gap: 8px; flex-wrap: wrap; margin: 4px 0; }
.count-chip { display: inline-flex; align-items: baseline; gap: 6px; padding: 6px 10px; background: var(--bg2); border-radius: 6px; }
.count-chip-n { font-size: 15px; font-weight: 500; color: var(--fg); }
.count-chip-label { font-size: 12px; color: var(--gray); }

.drill-findings-id { font-family: var(--font-mono); font-size: 12px; color: var(--gray); }

.drill-header-row {
    display: flex; align-items: baseline; gap: 0;
    margin-bottom: 4px; flex-wrap: wrap;
}
.drill-header-summary {
    display: inline-flex; align-items: center; gap: 8px;
    margin-left: 10px; font-size: 12px;
}
.drill-header-summary .sep { color: var(--gray-light); }
.drill-header-summary .count { color: var(--gray); text-transform: none; letter-spacing: 0; font-weight: 400; }

/* Drill-down super-section groupings (Why applies / How controlled) */
.drill-supersection {
    border-top: 1px solid var(--border);
    padding-top: 12px;
    margin: 18px 0 10px;
    font-size: 14px; font-weight: 500; color: var(--fg);
}

/* Drill-down Additional Signals: 2-col grid */
.drill-signal-grid {
    display: grid; grid-template-columns: minmax(180px, auto) 1fr;
    gap: 6px 16px; font-size: 13px; margin-top: 4px;
}
.drill-signal-grid .label-cell { color: var(--fg); }
.drill-signal-grid .ids-cell { font-family: var(--font-mono); font-size: 12px; color: var(--gray); }
.drill-signal-grid .full-cell { grid-column: 1 / -1; color: var(--fg); }
.drill-section .label em.label-suffix {
    text-transform: none; letter-spacing: 0; font-weight: 400;
    color: var(--gray); font-style: normal;
}

/* Drill-down inline cards (1-2 findings/events) */
.drill-inline-card {
    display: flex; align-items: center; gap: 12px;
    padding: 10px 12px; border: 1px solid var(--border);
    border-radius: 6px; margin: 4px 0;
}
.drill-inline-card .card-id { font-family: var(--font-mono); font-size: 12px; color: var(--gray); white-space: nowrap; }
.drill-inline-card .card-title { flex: 1; color: var(--fg); font-size: 13px; line-height: 1.4; }
.drill-inline-card .card-pill { white-space: nowrap; }

/* IAG Issues contradiction warning */
.drill-iag-warning {
    display: flex; align-items: center; gap: 6px;
    color: #633806; font-size: 12px; margin: 2px 0 8px;
}

/* -- Pills -- */
.pill {
    display: inline-block; font-size: 11px; padding: 2px 8px;
    border-radius: 10px; font-weight: 600; white-space: nowrap;
}
.pill-neutral { background: var(--bg2); color: var(--gray); }
.empty-cell { color: var(--gray-light); }
.rating-bar { font-family: var(--font-mono); font-size: 13px; line-height: 1.8; }

/* -- Misc -- */
blockquote {
    border-left: 3px solid var(--gray-light); padding: 10px 18px; margin: 10px 0;
    background: var(--bg2); font-style: italic; font-size: 14px; border-radius: 0 8px 8px 0;
    color: #555;
}
.overview { color: var(--gray); font-size: 13px; }
.overview p { margin: 4px 0; }
.overview ul.overview-list { margin: 4px 0 4px 18px; padding: 0; }
.overview ul.overview-list li { margin: 2px 0; }
.overview-toggle { font-size: 12px; color: var(--blue); cursor: pointer; text-decoration: underline; margin-left: 4px; }

.handoff-stack { margin: 6px 0 0; }
.handoff-col { margin-bottom: 12px; }
.handoff-col:last-child { margin-bottom: 0; }
.handoff-col-label {
    font-size: 11px; color: var(--gray); text-transform: uppercase;
    letter-spacing: 0.4px; font-weight: 600; margin-bottom: 4px;
}
.handoff-entry { display: flex; gap: 10px; margin-bottom: 4px; align-items: baseline; }
.handoff-id { font-family: var(--font-mono); font-size: 12px; color: var(--gray-light); min-width: 50px; flex-shrink: 0; }
.handoff-name { color: var(--fg); font-size: 13px; line-height: 1.5; }
.handoff-desc { margin-top: 10px; color: var(--fg); font-size: 13px; }

.meta { color: var(--gray); font-size: 13px; }
.entity-context { margin-bottom: 14px; }
.chart-container { max-width: 700px; margin: 16px 0; }
.divider { border-top: 1px solid var(--border); margin: 24px 0; }
.tab-content { display: none; }
.tab-content.active { display: block; }

/* -- Footer -- */
.report-footer {
    background: var(--bg2); border-top: 1px solid var(--border);
    padding: 16px 32px; display: flex; justify-content: space-between; align-items: center;
    margin-top: 40px;
}
.report-footer .ft { color: var(--gray); font-size: 12px; line-height: 1.6; }

p.meta, span.meta { font-weight: 400; }
strong { font-weight: 600; }
"""

_HTML_BODY = r"""<!-- ==================== HEADER (Streamlit-style toolbar) ==================== -->
<div class="report-header">
    <div class="header-info">
        <h1>&#128203; Risk Taxonomy Review</h1>
        <div class="sub">Last Run: __RUN_TIMESTAMP__ &middot; __TOTAL_ENTITIES__ entities &middot; __TOTAL_ROWS__ total mappings</div>
    </div>
</div>

<div class="wrap">
<div class="sidebar-layout">

<!-- ==================== SIDEBAR ==================== -->
<div class="sidebar" id="sidebar">
    <h3>&#128203; Risk Taxonomy Review</h3>
    <div class="meta">Last Run: __RUN_TIMESTAMP__</div>
    <div class="divider"></div>

    <label>View</label>
    <div class="view-radio">
        <label><input type="radio" name="view" value="entity" checked onchange="switchView(this.value)"> Entity View</label>
        <label><input type="radio" name="view" value="risk" onchange="switchView(this.value)"> Risk Category View</label>
    </div>
    <div class="divider"></div>

    <div id="sidebar-entity-select">
        <label>Select Audit Entity</label>
        <select id="entity-select" onchange="renderEntityView()"></select>
        <div class="divider"></div>
    </div>

    <div id="sidebar-risk-select" style="display:none;">
        <label>Select L2 Risk</label>
        <select id="risk-select" onchange="renderRiskView()"></select>
        <div class="divider"></div>
    </div>

    <div id="sidebar-status-filter">
        <label>Status Filter</label>
        <div class="checkbox-group" id="status-checkboxes">
            <label><input type="checkbox" value="Applicability Undetermined" onchange="applyFilters()"> &#9888;&#65039; Applicability Undetermined</label>
            <label><input type="checkbox" value="Needs Review" onchange="applyFilters()"> &#128270; Needs Review</label>
            <label><input type="checkbox" value="No Evidence Found &#8212; Verify N/A" onchange="applyFilters()"> &#128310; No Evidence Found &#8212; Verify N/A</label>
            <label><input type="checkbox" value="Applicable" onchange="applyFilters()"> &#9989; Applicable</label>
            <label><input type="checkbox" value="Not Applicable" onchange="applyFilters()"> &#11036; Not Applicable</label>
            <label><input type="checkbox" value="Not Assessed" onchange="applyFilters()"> &#128309; Not Assessed</label>
        </div>
        <div class="meta" style="margin-top:4px;">Leave unchecked to show all.</div>
        <div class="divider"></div>
    </div>

    <div id="sidebar-org-filters" style="display:none;">
        <label>Organization</label>
        <div class="filter-group">
            <label>Audit Leader</label>
            <select id="filter-al" onchange="applyFilters()"><option value="">All</option></select>
        </div>
        <div class="filter-group">
            <label>PGA</label>
            <select id="filter-pga" onchange="applyFilters()"><option value="">All</option></select>
        </div>
        <div class="filter-group">
            <label>Core Audit Team</label>
            <select id="filter-team" onchange="applyFilters()"><option value="">All</option></select>
        </div>
    </div>
</div>

<!-- ==================== MAIN CONTENT ==================== -->
<div class="main-content">

<!-- ==================== ENTITY TAB ==================== -->
<div id="tab-entity" class="tab-content active">
    <div id="entity-title"></div>
    <div id="entity-banner"></div>
    <div id="unmapped-findings-banner"></div>
    <div id="entity-context"></div>

    <div class="sub-tabs" id="entity-sub-tabs">
        <button type="button" class="sub-tab active" onclick="switchEntityTab('profile')">Risk Profile</button>
        <button type="button" class="sub-tab" onclick="switchEntityTab('drill')">Drill-Down</button>
        <button type="button" class="sub-tab" onclick="switchEntityTab('legacy')">Legacy Profile</button>
        <button type="button" class="sub-tab" onclick="switchEntityTab('source')">Source Data</button>
        <button type="button" class="sub-tab" onclick="switchEntityTab('trace')">Traceability</button>
    </div>

    <div id="entity-tab-profile" class="sub-tab-content active">
        <div class="table-wrap"><table id="entity-profile-table"></table></div>
    </div>
    <div id="entity-tab-drill" class="sub-tab-content">
        <div class="meta" style="margin-bottom:10px;">Expand any L2 to see evidence and context.</div>
        <div id="entity-drilldown"></div>
    </div>
    <div id="entity-tab-legacy" class="sub-tab-content">
        <div class="meta" style="margin-bottom:10px;">Legacy pillar ratings from the most recent assessment cycle.</div>
        <div id="entity-legacy-ratings"></div>
    </div>
    <div id="entity-tab-source" class="sub-tab-content">
        <div id="entity-sources"></div>
    </div>
    <div id="entity-tab-trace" class="sub-tab-content">
        <div id="entity-traceability"></div>
    </div>
</div>

<!-- ==================== RISK CATEGORY TAB ==================== -->
<div id="tab-risk" class="tab-content">
    <div id="risk-title"></div>
    <div id="risk-banner"></div>
    <div id="risk-metrics" class="metrics"></div>
    <h2>Entity Breakdown</h2>
    <div class="table-wrap"><table id="risk-entity-table"></table></div>
    <h2>Rating Concentration</h2>
    <div class="chart-container" id="concentration-chart"></div>
    <h2>Entity Drill-Down</h2>
    <div id="risk-drilldown"></div>
    <h2>IAG Issues for this L2</h2>
    <div id="risk-findings"></div>
</div>

</div><!-- /.main-content -->
</div><!-- /.sidebar-layout -->
</div><!-- /.wrap -->

<!-- ==================== BRANDED FOOTER ==================== -->
<div class="report-footer">
    <div class="ft">Generated by Risk Taxonomy Transformer on __RUN_TIMESTAMP__.<br>
    For interactive features, contact the QA team for Streamlit dashboard access.</div>
</div>
"""

_JS = r"""
// ==================== EMBEDDED DATA ====================
const auditData = __AUDIT_JSON__;
const detailData = __DETAIL_JSON__;
const findingsData = __FINDINGS_JSON__;
const subRisksData = __SUB_RISKS_JSON__;
const oreData = __ORE_JSON__;
const prsaData = __PRSA_JSON__;
const bmaData = __BMA_JSON__;
const graRapsData = __GRA_RAPS_JSON__;
const legacyRatingsData = __LEGACY_RATINGS_JSON__;
const legacyData = __LEGACY_JSON__;
const applicationsInventory = __APPS_INV_JSON__;
const policiesInventory = __POLICIES_INV_JSON__;
const lawsInventory = __LAWS_INV_JSON__;
const thirdpartiesInventory = __TP_INV_JSON__;
const INVENTORY_COLS = __INVENTORY_COLS_JSON__;
const entities = __ENTITIES_JSON__;
const l2Risks = __L2_RISKS_JSON__;
const auditLeaders = __AUDIT_LEADERS_JSON__;
const pgaList = __PGAS_JSON__;
const coreTeams = __CORE_TEAMS_JSON__;
const entityMeta = __ENTITY_META_JSON__;

function getEntityMeta(eid) { return entityMeta[eid] || {}; }

// ==================== STATUS CONFIG ====================
const STATUS_CONFIG = {
    "Applicability Undetermined": {"icon": "\u26A0\uFE0F", "sort": 0},
    "Needs Review": {"icon": "\ud83d\udd0e", "sort": 1},
    "No Evidence Found \u2014 Verify N/A": {"icon": "\ud83d\udd36", "sort": 2},
    "Applicable": {"icon": "\u2705", "sort": 3},
    "Not Applicable": {"icon": "\u2B1C", "sort": 4},
    "Not Assessed": {"icon": "\ud83d\udd35", "sort": 5},
};
const RATING_RANK = {"Low":1,"Medium":2,"High":3,"Critical":4,"low":1,"medium":2,"high":3,"critical":4};
const RANK_LABEL = {1:"Low",2:"Medium",3:"High",4:"Critical"};
const IAG_ACTIVE_STATUSES = new Set(["open", "in validation", "in sustainability"]);
function isActiveIagStatus(status) {
    return IAG_ACTIVE_STATUSES.has(String(status||"").toLowerCase().trim());
}

// Build entity-to-name mapping from hoisted entity metadata
const entityNameMap = {};
Object.keys(entityMeta).forEach(eid => {
    let nm = entityMeta[eid] && entityMeta[eid]["Entity Name"];
    if (nm) entityNameMap[eid] = nm;
});

// ================================================================
// PILL PALETTES -- single source of truth for all color-coded pills.
// Consumed by makePill(value, paletteName) and pillStyleFor().
// ================================================================
const PILL_PALETTES = {
    severity: {
        "critical": {bg: "#FCEBEB", fg: "#791F1F"},
        "high":     {bg: "#FAD8C1", fg: "#7A2E0F"},
        "medium":   {bg: "#FAEEDA", fg: "#633806"},
        "low":      {bg: "#EAF3DE", fg: "#27500A"},
    },
    oreClass: {
        "class a": {bg: "#FCEBEB", fg: "#791F1F"},
        "class b": {bg: "#FAD8C1", fg: "#7A2E0F"},
        "class c": {bg: "#FAEEDA", fg: "#633806"},
    },
    controlRating: {
        "well controlled":           {bg: "#EAF3DE", fg: "#27500A"},
        "moderately controlled":     {bg: "#FAEEDA", fg: "#633806"},
        "insufficiently controlled": {bg: "#FCEBEB", fg: "#791F1F"},
        "inadequately controlled":   {bg: "#FCEBEB", fg: "#791F1F"},
        "poorly controlled":         {bg: "#FCEBEB", fg: "#791F1F"},
    },
    // iagStatus: "closed" renders neutral; all other non-empty values warn.
    // Handled specially in makePill() below.
    iagStatus: {
        "open":              {bg: "#FAEEDA", fg: "#633806"},
        "in validation":     {bg: "#FAEEDA", fg: "#633806"},
        "in sustainability": {bg: "#FAEEDA", fg: "#633806"},
    },
};

// ==================== HELPERS ====================
function isEmpty(v) { return v === null || v === undefined || v === "" || v === "nan" || v === "None" || (typeof v === "number" && isNaN(v)); }
function esc(s) {
    if (!s) return "";
    let d = document.createElement("div");
    d.textContent = String(s);
    return d.innerHTML;
}
function icon(status) {
    let cfg = STATUS_CONFIG[status];
    return cfg ? cfg.icon : "\u2753";
}
function statusLabel(status) { return icon(status) + " " + status; }
function ratingBar(v) {
    if (isEmpty(v)) return "\u2014";
    let n = parseInt(v);
    return "\u2588".repeat(n) + "\u2591".repeat(4-n) + " " + n + " (" + (RANK_LABEL[n]||"") + ")";
}
function basePillar(s) { return String(s || "").split(" (also")[0].trim(); }
function methodToStatus(m) {
    m = String(m);
    if (m.includes("llm_confirmed_na")) return "Not Applicable";
    if (m.includes("source_not_applicable")) return "Not Applicable";
    if (m.includes("evaluated_no_evidence")) return "No Evidence Found \u2014 Verify N/A";
    if (m.includes("no_evidence_all_candidates")) return "Applicability Undetermined";
    if (m.includes("true_gap_fill") || m.includes("gap_fill")) return "Not Assessed";
    if (m.includes("direct") || m.includes("evidence_match") || m.includes("llm_override") || m.includes("issue_confirmed") || m.includes("dedup")) return "Applicable";
    return "Needs Review";
}

// resolveCol: pick the first candidate column name that exists on row 0 of
// `data`. Consolidates the "snake_case ? snake : TitleCase" pattern used by
// every source-data block. Returns null if none match or data is empty.
function resolveCol(data, candidates) {
    if (!data || !data.length) return null;
    let row = data[0];
    for (let c of candidates) {
        if (row.hasOwnProperty(c)) return c;
    }
    return null;
}

// isAbsence: a value is an "absence" if it conveys that nothing was found /
// is available. Absence values should not render as loud callouts -- they
// render as muted inline text (when meaningful as reassurance) or are
// omitted entirely. Distinct from isEmpty() which just checks for no data.
function isAbsence(v) {
    if (isEmpty(v)) return true;
    let s = String(v).trim().toLowerCase();
    if (s === "n/a" || s === "none" || s === "not available") return true;
    if (s === "no open items") return true;
    if (/^no .+ available$/.test(s)) return true;
    return false;
}

// ================================================================
// PILL RENDERING
// ================================================================
// Single pill factory: looks up `value` in the named palette and renders a
// styled <span>. Empty/N/A values render neutral. Unknown values render
// neutral. Handles the IAG "closed is neutral" special case.
function makePill(value, paletteName) {
    let s = String(value || "").trim();
    let lower = s.toLowerCase();
    if (!s || lower === "n/a" || lower === "na" || lower === "not applicable") {
        return '<span class="pill pill-neutral">' + esc(s || "N/A") + '</span>';
    }
    if (paletteName === "iagStatus" && lower === "closed") {
        return '<span class="pill pill-neutral">' + esc(s) + '</span>';
    }
    let palette = PILL_PALETTES[paletteName] || {};
    let entry = palette[lower];
    if (!entry) {
        return '<span class="pill pill-neutral">' + esc(s) + '</span>';
    }
    return '<span class="pill" style="background:' + entry.bg + ';color:' + entry.fg + ';">' + esc(s) + '</span>';
}

// pillStyleFor: returns a raw CSS style string for a palette entry, or "" if
// no match. Used by chip-in-header summaries (where we want to style inline
// rather than rebuild a pill).
function pillStyleFor(value, paletteName) {
    let lower = String(value || "").trim().toLowerCase();
    let palette = PILL_PALETTES[paletteName] || {};
    let entry = palette[lower];
    return entry ? ("background:" + entry.bg + ";color:" + entry.fg + ";") : "";
}

// ==================== TABLE SORTING / MAKE TABLE ====================
// ==================== TABLE BUILDING / SORTING / PERSIST STATE ====================
//
// Every data table in the report is built through one of two entry points:
//
//   buildTableHTML(opts) -> HTML string
//     For tables embedded inside a larger innerHTML assignment (inventory
//     blocks, source-data expanders, risk view IAG Issues, etc.).
//
//   makeTable(id, headers, rows, types)
//     For the two tables that have a pre-allocated <table id="..."> in the
//     static HTML body (entity-profile-table, risk-entity-table). Thin
//     wrapper around buildTableHTML.
//
// Both produce the same markup: a .data-table with sortable ▴▾ headers,
// draggable column-resize handles, and click-cell-to-expand. Sort state
// is persisted per table ID in _tableSortState and re-applied on re-render,
// so filter changes no longer reset the auditor's sort.

const _tableSortState = {}; // { tableId: {col: number, dir: "asc"|"desc"} }

function _normHeader(h, idx) {
    // Accept: "Label" | {label, tool?, width?, type?, noSort?}
    if (typeof h === "string") return {label: h, tool: false, width: null, type: "str", noSort: false};
    return {
        label: h.label || "",
        tool: !!h.tool,
        width: h.width || null,
        type: h.type || "str",
        noSort: !!h.noSort,
    };
}

// buildTableHTML({id, headers, rows, wrap?, tableClass?}) -> string
//   headers: Array of string | {label, tool?, width?, type?, noSort?}
//   rows:    Array of Array of HTML strings (one per column)
//   wrap:    default true -- wrap in <div class="table-wrap">
//   tableClass: extra class(es) appended to "data-table"
function buildTableHTML(opts) {
    let id = opts.id;
    let headers = (opts.headers || []).map(_normHeader);
    let rows = opts.rows || [];
    let wrap = opts.wrap !== false;
    let extraClass = opts.tableClass ? (" " + opts.tableClass) : "";

    let saved = _tableSortState[id]; // may be undefined
    if (saved) {
        rows = _sortRowsByState(rows, headers, saved);
    }

    let hasColWidths = headers.some(h => h.width);
    let parts = [];
    parts.push('<table id="' + id + '" class="data-table' + extraClass + '"');
    if (saved) {
        parts.push(' data-sort-col="' + saved.col + '" data-sort-dir="' + saved.dir + '"');
    }
    parts.push('>');
    if (hasColWidths) {
        parts.push('<colgroup>');
        headers.forEach(h => {
            parts.push('<col' + (h.width ? ' style="width:' + h.width + '"' : '') + '>');
        });
        parts.push('</colgroup>');
    }
    parts.push('<thead><tr>');
    headers.forEach((h, i) => {
        let cls = [];
        if (h.tool) cls.push("th-tool");
        if (h.noSort) cls.push("th-nosort");
        let clsAttr = cls.length ? ' class="' + cls.join(" ") + '"' : '';
        let onClick = h.noSort ? "" : ' onclick="sortTable(\'' + id + '\',' + i + ',\'' + h.type + '\')"';
        let arrow = h.noSort ? "" : " \u25B4\u25BE";
        let arrowInd = "";
        if (saved && saved.col === i) {
            arrowInd = saved.dir === "asc" ? " \u25B4" : " \u25BE";
            arrow = arrowInd;
        }
        parts.push('<th' + clsAttr + onClick + '>' + h.label + arrow
            + '<span class="col-resize" onmousedown="startResize(event)"></span></th>');
    });
    parts.push('</tr></thead><tbody>');
    rows.forEach(r => {
        parts.push('<tr>');
        r.forEach(cell => parts.push('<td>' + cell + '</td>'));
        parts.push('</tr>');
    });
    parts.push('</tbody></table>');

    let html = parts.join("");
    if (wrap) html = '<div class="table-wrap">' + html + '</div>';
    return html;
}

// makeTable: legacy entry point that writes into a pre-allocated <table>
// element. Used by the two tables baked into the static HTML body.
function makeTable(id, headers, rows, types) {
    // If caller provided a types array, merge into headers
    let merged = headers.map((h, i) => {
        let norm = _normHeader(h, i);
        if (types && types[i]) norm.type = types[i];
        return norm;
    });
    let html = buildTableHTML({id: id, headers: merged, rows: rows, wrap: false});
    // Extract innerHTML (strip outer <table ...>...</table> wrapper) and
    // drop it into the existing element, so we preserve its id and the
    // surrounding .table-wrap container from the HTML body.
    let el = document.getElementById(id);
    if (!el) return;
    let openEnd = html.indexOf(">") + 1;
    let closeStart = html.lastIndexOf("</table>");
    // Also copy data-sort attrs onto the real element
    let saved = _tableSortState[id];
    if (saved) {
        el.setAttribute("data-sort-col", saved.col);
        el.setAttribute("data-sort-dir", saved.dir);
    } else {
        el.removeAttribute("data-sort-col");
        el.removeAttribute("data-sort-dir");
    }
    // Ensure the element has the data-table class
    if (!el.classList.contains("data-table")) el.classList.add("data-table");
    el.innerHTML = html.substring(openEnd, closeStart);
}

function _sortRowsByState(rows, headers, state) {
    let col = state.col, dir = state.dir;
    let type = (headers[col] && headers[col].type) || "str";
    let asc = dir === "asc";
    let copy = rows.slice();
    copy.sort((a, b) => {
        let va = _cellSortValue(a[col]);
        let vb = _cellSortValue(b[col]);
        if (type === "num") { va = parseFloat(va) || 0; vb = parseFloat(vb) || 0; }
        if (va < vb) return asc ? -1 : 1;
        if (va > vb) return asc ? 1 : -1;
        return 0;
    });
    return copy;
}

function _cellSortValue(cellHtml) {
    // Strip tags and normalize whitespace so pills/spans sort by their text
    let tmp = document.createElement("div");
    tmp.innerHTML = String(cellHtml || "");
    return (tmp.textContent || "").trim();
}

function sortTable(tableId, col, type) {
    let table = document.getElementById(tableId);
    if (!table) return;
    let currentCol = table.dataset.sortCol;
    let currentDir = table.dataset.sortDir;
    let dir;
    if (currentCol === String(col)) {
        dir = currentDir === "asc" ? "desc" : "asc";
    } else {
        dir = "asc";
    }
    _tableSortState[tableId] = {col: col, dir: dir};

    // Re-sort the existing DOM rows in place
    let bodyRows = Array.from(table.querySelectorAll("tbody tr"));
    let asc = dir === "asc";
    bodyRows.sort((a, b) => {
        let va = a.cells[col].textContent.trim();
        let vb = b.cells[col].textContent.trim();
        if (type === "num") { va = parseFloat(va) || 0; vb = parseFloat(vb) || 0; }
        if (va < vb) return asc ? -1 : 1;
        if (va > vb) return asc ? 1 : -1;
        return 0;
    });
    table.dataset.sortCol = String(col);
    table.dataset.sortDir = dir;
    let tbody = table.querySelector("tbody");
    bodyRows.forEach(r => tbody.appendChild(r));

    // Update arrow indicators on headers
    let ths = table.querySelectorAll("thead th");
    ths.forEach((th, i) => {
        let base = th.innerHTML.replace(/[\u25B4\u25BE]/g, "").replace(/\s+<span class="col-resize"/, '<span class="col-resize"');
        // reinsert arrow
        let resizeIdx = base.indexOf('<span class="col-resize"');
        let labelPart = resizeIdx >= 0 ? base.substring(0, resizeIdx) : base;
        let resizePart = resizeIdx >= 0 ? base.substring(resizeIdx) : "";
        let arrow;
        if (i === col) arrow = asc ? " \u25B4" : " \u25BE";
        else if (th.classList.contains("th-nosort")) arrow = "";
        else arrow = " \u25B4\u25BE";
        th.innerHTML = labelPart.replace(/\s*$/, "") + arrow + resizePart;
    });
}

// ==================== CELL CLICK-TO-EXPAND (scoped to .data-table) ====================
// Only tables with .data-table opt into this behavior. Static decorative
// tables (.rating-table etc.) don't trigger it.
document.addEventListener("click", function(e) {
    let td = e.target.closest(".data-table td");
    if (!td) return;
    if (e.target.tagName === "A") return;
    // Don't toggle if the user started a column-resize drag
    if (e.target.classList && e.target.classList.contains("col-resize")) return;
    td.classList.toggle("cell-expanded");
});

// ==================== COLUMN RESIZE ====================
let _resizeCol = null, _resizeStartX = 0, _resizeStartW = 0;
function startResize(e) {
    e.stopPropagation();
    e.preventDefault();
    let th = e.target.parentElement;
    _resizeCol = th;
    _resizeStartX = e.pageX;
    _resizeStartW = th.offsetWidth;
    e.target.classList.add("active");
    document.addEventListener("mousemove", doResize);
    document.addEventListener("mouseup", stopResize);
}
function doResize(e) {
    if (!_resizeCol) return;
    let w = Math.max(40, _resizeStartW + (e.pageX - _resizeStartX));
    _resizeCol.style.width = w + "px";
}
function stopResize(e) {
    if (_resizeCol) {
        let handle = _resizeCol.querySelector(".col-resize");
        if (handle) handle.classList.remove("active");
    }
    _resizeCol = null;
    document.removeEventListener("mousemove", doResize);
    document.removeEventListener("mouseup", stopResize);
}

// Expander state persistence. When a caller provides a stable `key`, we
// remember the user's last explicit open/closed choice for that key so it
// survives a re-render (e.g. after a filter change). Expanders without a
// key are stateless and always fall back to their default.
const _expanderUserState = {}; // { key: true (open) | false (closed) }

function toggleExpander(el) {
    let exp = el.closest(".expander");
    let wasOpen = exp.classList.contains("open");
    exp.classList.toggle("open");
    let key = exp.dataset.key;
    if (key) _expanderUserState[key] = !wasOpen;
    if (!wasOpen && exp.dataset.lazy) {
        let bodyEl = exp.querySelector(".expander-body");
        let fn = window["_lazy_" + exp.dataset.lazy];
        if (fn && !exp.dataset.rendered) {
            bodyEl.innerHTML = fn();
            exp.dataset.rendered = "1";
        }
    }
}

// mkExpander(defaultOpen, headerLabel, bodyHtml, key?)
//   defaultOpen: open/closed state used when the user hasn't interacted
//   key:         optional stable ID. When provided, the user's last
//                explicit toggle choice for this key survives re-render.
function mkExpander(defaultOpen, headerLabel, bodyHtml, key) {
    let effectiveOpen = defaultOpen;
    if (key && Object.prototype.hasOwnProperty.call(_expanderUserState, key)) {
        effectiveOpen = _expanderUserState[key];
    }
    let cls = effectiveOpen ? "expander open" : "expander";
    let keyAttr = key ? ' data-key="' + esc(key) + '"' : "";
    return '<div class="' + cls + '"' + keyAttr + '><div class="expander-header" onclick="toggleExpander(this)">'
        + '<span>' + headerLabel + '</span><span class="expander-arrow">\u25B6</span>'
        + '</div><div class="expander-body">' + bodyHtml + '</div></div>';
}

function makeBanner(containerId, total, undetermined, assumedNA, contextLabel) {
    let action = undetermined + assumedNA;
    let el = document.getElementById(containerId);
    if (action > 0) {
        el.innerHTML = '<div class="banner banner-warn"><strong>' + action + ' of ' + total + ' items</strong> '
            + (contextLabel ? "for " + esc(contextLabel) + " " : "")
            + 'need your review \u2014 ' + undetermined + ' applicability undetermined, ' + assumedNA + ' no evidence found (verify N/A).</div>';
    } else {
        el.innerHTML = '<div class="banner banner-ok"><strong>All ' + total + ' items</strong> '
            + (contextLabel ? "for " + esc(contextLabel) + " " : "")
            + 'have proposed applicability \u2014 review to confirm.</div>';
    }
}

function formatOverview(raw, id) {
    let text = String(raw || "").replace(/\r\n/g, "\n").trim();
    if (!text) return "";
    let paragraphs = text.split(/\n\s*\n/).map(p => p.trim()).filter(Boolean);
    if (!paragraphs.length) return "";
    let bulletRe = /^[\u2022\-\*]\s+|^\d+[.)]\s+/;
    function renderPara(p) {
        let lines = p.split("\n").map(l => l.trim()).filter(Boolean);
        let allBullets = lines.length > 1 && lines.every(l => bulletRe.test(l));
        if (allBullets) {
            let items = lines.map(l => "<li>" + esc(l.replace(bulletRe, "").trim()) + "</li>").join("");
            return '<ul class="overview-list">' + items + '</ul>';
        }
        return "<p>" + esc(lines.join(" ")) + "</p>";
    }
    let truncate = text.length > 400 && paragraphs.length > 1;
    if (!truncate) return paragraphs.map(renderPara).join("");
    let tid = "overview-more-" + id;
    return renderPara(paragraphs[0]) +
        '<div id="' + tid + '" style="display:none;">' + paragraphs.slice(1).map(renderPara).join("") + '</div>' +
        '<a href="javascript:void(0)" class="overview-toggle" onclick="toggleOverview(\'' + tid + '\', this)">Show more</a>';
}

function toggleOverview(id, el) {
    let div = document.getElementById(id);
    let hidden = div.style.display === "none";
    div.style.display = hidden ? "block" : "none";
    el.textContent = hidden ? "Show less" : "Show more";
}

function severitySummary(rows, getVal, order) {
    let counts = {};
    rows.forEach(r => {
        let v = String(getVal(r) || "").trim();
        if (!v || v.toLowerCase() === "nan") return;
        counts[v] = (counts[v] || 0) + 1;
    });
    if (!Object.keys(counts).length) return "";
    let parts = [];
    order.forEach(label => {
        if (counts[label]) {
            parts.push(counts[label] + " " + label);
            delete counts[label];
        }
    });
    Object.keys(counts).forEach(k => parts.push(counts[k] + " " + k));
    return " \u2014 " + parts.join(", ");
}

// ================================================================
// SIGNAL RENDERING
// ================================================================
// Signals are parsed into: leading [TAG] (rendered as a chip), statement
// body, inline ID lists (rendered mono/tertiary), and a trailing em-dash
// action hint (rendered secondary). Control contradictions ("well controlled
// but ... review whether") get alert styling instead.
function renderSignals(signals) {
    if (isEmpty(signals)) return "";
    let items = String(signals).split(/\n| \| /).filter(s => s.trim());
    if (!items.length) return "";

    let parsed = items.map(raw => {
        let s = raw.trim();
        let lower = s.toLowerCase();
        let isContradiction = lower.includes("well controlled but") || lower.includes("review whether");
        if (isContradiction) return { kind: "contradiction", text: s };

        let body = s;
        let tagMatch = body.match(/^\[([^\]]+)\]\s*/);
        if (tagMatch) body = body.substring(tagMatch[0].length);

        let hint = "";
        let emIdx = body.indexOf("\u2014");
        if (emIdx >= 0) {
            hint = body.substring(emIdx + 1).trim();
            body = body.substring(0, emIdx).trim();
        }

        let ids = "";
        let openIdx = body.indexOf("(");
        if (openIdx >= 0) {
            let closeIdx = body.indexOf(")", openIdx);
            if (closeIdx > openIdx) {
                let inner = body.substring(openIdx + 1, closeIdx);
                if (inner.includes(";")) {
                    ids = inner.split(";").map(x => x.trim()).filter(Boolean).join(" \u00B7 ");
                    body = (body.substring(0, openIdx).trim() + " " + body.substring(closeIdx + 1).trim()).trim();
                }
            }
        }

        return { kind: "signal", body, ids, hint };
    });

    let signalRows = parsed.filter(p => p.kind === "signal");
    let sharedHint = "";
    if (signalRows.length >= 2) {
        let firstHint = signalRows[0].hint;
        if (firstHint && signalRows.every(r => r.hint === firstHint)) {
            sharedHint = firstHint;
            signalRows.forEach(r => { r.hint = ""; });
        }
    }

    let labelHtml = "Additional Signals";
    if (sharedHint) {
        labelHtml += ' <em class="label-suffix">(' + esc(sharedHint) + ')</em>';
    }

    let html = '<div class="drill-section"><span class="label">' + labelHtml + '</span>';

    parsed.filter(p => p.kind === "contradiction").forEach(p => {
        html += '<div class="signal-row signal-contradiction">\ud83d\udea8 ' + esc(p.text) + '</div>';
    });

    if (signalRows.length > 0) {
        html += '<div class="drill-signal-grid">';
        signalRows.forEach(r => {
            let bodyText = r.body || "";
            if (r.hint) bodyText += ' \u2014 ' + r.hint;
            if (r.ids) {
                html += '<div class="label-cell">' + esc(bodyText) + '</div>';
                html += '<div class="ids-cell">' + esc(r.ids) + '</div>';
            } else {
                html += '<div class="full-cell">' + esc(bodyText) + '</div>';
            }
        });
        html += '</div>';
    }

    html += '</div>';
    return html;
}

// ================================================================
// DECISION / CONTEXT SECTION RENDERERS
// ================================================================
function renderDecisionBasis(row, status) {
    let basis = row["Decision Basis"] || "";
    if (isEmpty(basis)) return "";
    // Applicable -> ok banner, Undetermined -> warn banner, other ->
    // info banner, except Not Assessed which gets a muted plain section.
    let cls = "banner-info";
    if (status === "Applicable") cls = "banner-ok";
    else if (status === "Applicability Undetermined") cls = "banner-warn";
    else if (status === "Not Assessed") {
        return '<div class="drill-section"><span class="label">Decision Basis</span><div>' + esc(basis) + '</div></div>';
    }
    return '<div class="banner ' + cls + '"><strong>Decision Basis</strong><br>' + esc(basis) + '</div>';
}

function renderSiblingMatches(row, entityDetailRows) {
    let legacySource = String(row["Legacy Source"] || "");
    if (!entityDetailRows || isEmpty(legacySource)) return "";
    let bp = basePillar(legacySource);
    let matched = entityDetailRows.filter(d =>
        String(d["source_legacy_pillar"]||"").includes(bp) &&
        !String(d["method"]||"").includes("no_evidence_all_candidates") &&
        !String(d["method"]||"").includes("evaluated_no_evidence")
    );
    if (!matched.length) return "";
    let html = '<div class="drill-section"><span class="label">Other L2s from ' + esc(bp) + ' that DID match</span>';
    matched.forEach(m => { html += '<div>\u2022 \u2705 ' + esc(m["new_l2"]) + '</div>'; });
    html += '</div>';
    return html;
}

function renderSubRiskDescriptions(detailRow, eid, l2) {
    if (!detailRow || isEmpty(eid) || isEmpty(l2)) return "";
    let pillar = basePillar(detailRow["source_legacy_pillar"]||"");
    if (isEmpty(pillar)) return "";
    let es = subRisksData.filter(s => {
        let sEid = String(s["entity_id"]||s["Audit Entity"]||s["Audit Entity ID"]||"");
        let sL1 = String(s["legacy_l1"]||s["Level 1 Risk Category"]||"");
        if (sEid !== String(eid) || sL1 !== pillar) return false;
        let matches = String(s["L2 Keyword Matches"]||s["Contributed To (keyword matches)"]||"");
        let contributedTo = matches.split(";").map(x => x.trim().replace(/\s*\(.*/, ""));
        return contributedTo.includes(l2);
    });
    if (!es.length) return "";
    let html = '<div class="drill-section"><span class="label">Sub-risks that contributed evidence for this L2</span>';
    es.forEach(s => {
        let rid = s["risk_id"]||s["Key Risk ID"]||"";
        let desc = String(s["risk_description"]||s["Key Risk Description"]||"").substring(0,200);
        html += '<div class="subrisk-row"><span class="subrisk-id">' + esc(String(rid)) + '</span><span class="subrisk-name">' + esc(desc) + '</span></div>';
    });
    html += '</div>';
    return html;
}

function renderSourceRationale(detailRow) {
    if (!detailRow) return "";
    let rat = detailRow["source_rationale"] || "";
    if (isEmpty(rat)) return "";
    return '<div class="drill-section"><span class="label">Source Rationale</span><blockquote>' + esc(rat) + '</blockquote></div>';
}

function renderSectionHeader(labelText, summaryInner) {
    if (!summaryInner) return '<span class="label">' + esc(labelText) + '</span>';
    return '<div class="drill-header-row">'
        + '<span class="label" style="margin-bottom:0;">' + esc(labelText) + '</span>'
        + '<span class="drill-header-summary">' + summaryInner + '</span>'
        + '</div>';
}

function _countBySeverity(items, getSev) {
    let counts = {};
    items.forEach(it => {
        let s = String(getSev(it)||"").trim();
        if (!s) return;
        counts[s] = (counts[s] || 0) + 1;
    });
    return counts;
}

function _orderedSevPills(counts, order, paletteName) {
    let pills = order
        .filter(sev => counts[sev] > 0)
        .map(sev => {
            let style = pillStyleFor(sev, paletteName);
            if (style) {
                return '<span class="pill" style="' + style + '">' + counts[sev] + ' ' + esc(sev) + '</span>';
            }
            return '<span class="pill pill-neutral">' + counts[sev] + ' ' + esc(sev) + '</span>';
        });
    Object.keys(counts).forEach(sev => {
        if (order.includes(sev) || counts[sev] <= 0) return;
        pills.push('<span class="pill pill-neutral">' + counts[sev] + ' ' + esc(sev) + '</span>');
    });
    return pills;
}

// ================================================================
// EVIDENCE SECTION (unified)
// ================================================================
// Replaces renderRelevantFindings / renderRelevantOREs /
// renderRelevantPRSA / renderRelevantRAPs. Callers pre-filter data into a
// normalized shape {id, title, severity?, status?} and pass config here.
//
// cfg fields:
//   label            - section heading ("IAG Issues", etc.)
//   rows             - normalized rows to render
//   idLabel          - table header for ID column (default "ID")
//   titleLabel       - table header for title column (default "Title")
//   severityLabel    - table header for severity column (default "Severity")
//   statusLabel      - table header for status column (default "Status")
//   severityOrder    - array for ordering severity pills in header summary
//   severityPalette  - palette name for severity pills ("severity",
//                      "oreClass", etc.)
//   hasSeverity      - bool (falsy means omit severity column/pill)
//   hasStatus        - bool (falsy means omit status column/pill)
//   emptyMessage     - if provided, render empty section with this note
//                      instead of returning ""
//   contradictionWarning - optional HTML string shown above the content
//                          (used by IAG for the "well controlled" flag)
function renderEvidenceSection(cfg) {
    let rows = cfg.rows || [];
    let label = cfg.label;

    if (!rows.length) {
        if (cfg.emptyMessage) {
            return '<div class="drill-section">'
                + '<span class="label">' + esc(label) + '</span>'
                + '<div class="drill-inline-meta">' + esc(cfg.emptyMessage) + '</div>'
                + '</div>';
        }
        return "";
    }

    let hasSev = cfg.hasSeverity !== false;
    let hasStatus = cfg.hasStatus !== false;
    let sevPalette = cfg.severityPalette || "severity";

    // Header summary: severity count pills next to the section label.
    // Shown for every evidence table; the pills give a quick read of
    // severity mix before the auditor scans the rows.
    let summary = "";
    if (hasSev && cfg.severityOrder) {
        let counts = _countBySeverity(rows, r => r.severity || "");
        let pills = _orderedSevPills(counts, cfg.severityOrder, sevPalette);
        if (pills.length) {
            summary = '<span class="sep">\u00b7</span>' + pills.join('<span class="sep" style="margin:0 2px;">\u00b7</span>');
        }
    }

    let html = '<div class="drill-section">' + renderSectionHeader(label, summary);

    if (cfg.contradictionWarning) {
        html += cfg.contradictionWarning;
    }

    // Build a .data-table so it matches every other data table in the
    // report (sortable headers, cell-expand, column resize).
    let headers = [
        {label: cfg.idLabel || "ID", width: "90px"},
        {label: cfg.titleLabel || "Title"},
    ];
    if (hasSev) headers.push({label: cfg.severityLabel || "Severity", width: "110px"});
    if (hasStatus) headers.push({label: cfg.statusLabel || "Status", width: "110px"});

    let tableId = cfg.tableId || ("evtbl-" + Math.random().toString(36).slice(2, 8));
    let tableRows = rows.map(r => {
        let row = [
            '<span class="drill-findings-id">' + esc(String(r.id || "")) + '</span>',
            esc(String(r.title || "")),
        ];
        if (hasSev) row.push(makePill(r.severity || "", sevPalette));
        if (hasStatus) row.push(makePill(r.status || "", "iagStatus"));
        return row;
    });
    html += buildTableHTML({
        id: tableId,
        headers: headers,
        rows: tableRows,
        wrap: false,
        tableClass: "drill-findings-table",
    });
    html += '</div>';
    return html;
}

// ================================================================
// EVIDENCE SECTION -- thin wrappers per data source
// Each wrapper: filter + normalize, then delegate to renderEvidenceSection.
// ================================================================

function worstOpenIagSeverity(eid, l2) {
    if (isEmpty(eid) || isEmpty(l2)) return null;
    let ef = findingsData.filter(f => {
        let fEid = String(f["entity_id"]||f["Audit Entity ID"]||"");
        let fL2 = String(f["l2_risk"]||f["Mapped To L2(s)"]||f["Risk Dimension Categories"]||"");
        return fEid === String(eid) && fL2.includes(l2) && isActiveIagStatus(f["status"]||f["Finding Status"]);
    });
    let sevs = ef.map(f => String(f["severity"]||f["Final Reportable Finding Risk Rating"]||"").toLowerCase());
    if (sevs.some(s => s.includes("critical"))) return "Critical";
    if (sevs.some(s => s.includes("high"))) return "High";
    return null;
}

function renderRelevantFindings(row, eid, l2) {
    if (isEmpty(eid) || isEmpty(l2)) return "";
    let ef = findingsData.filter(f => {
        let fEid = String(f["entity_id"]||f["Audit Entity ID"]||"");
        let fL2 = String(f["l2_risk"]||f["Mapped To L2(s)"]||f["Risk Dimension Categories"]||"");
        return fEid === String(eid) && fL2.includes(l2) && isActiveIagStatus(f["status"]||f["Finding Status"]);
    });

    let rows = ef.map(f => ({
        id: f["issue_id"]||f["Finding ID"]||"",
        title: f["issue_title"]||f["Finding Name"]||"",
        severity: f["severity"]||f["Final Reportable Finding Risk Rating"]||"",
        status: f["status"]||f["Finding Status"]||"",
    }));

    // Contradiction warning: "Well Controlled" rating but open Critical/High
    // IAG finding on this L2. Rendered on IAG Issues (not Control Assessment)
    // so it sits next to its referent.
    let contradictionWarning = "";
    let baseline = (row && row["Control Effectiveness Baseline"]) || "";
    let ratingText = String(baseline).split("(")[0].trim();
    if (/^well controlled/i.test(ratingText) && rows.length) {
        let worst = worstOpenIagSeverity(eid, l2);
        if (worst) {
            contradictionWarning = '<div class="drill-iag-warning">'
                + '<span>\u26a0</span>'
                + '<span>Review whether the ' + esc(ratingText) + ' rating above still reflects current state</span>'
                + '</div>';
        }
    }

    return renderEvidenceSection({
        label: "IAG Issues",
        rows: rows,
        severityOrder: ["Critical","High","Medium","Low"],
        severityPalette: "severity",
        emptyMessage: "No IAG issues tagged to this L2.",
        contradictionWarning: contradictionWarning,
    });
}

function renderRelevantOREs(eid, l2) {
    if (isEmpty(eid) || isEmpty(l2) || !oreData.length) return "";
    let eidCol = resolveCol(oreData, ["entity_id", "Audit Entity (Operational Risk Events)", "Audit Entity ID"]);
    if (!eidCol) return "";
    let seen = new Set();
    let eo = [];
    oreData.forEach(o => {
        let oEid = String(o[eidCol]||"").trim();
        if (oEid !== String(eid)) return;
        let mappedList = String(o["Mapped L2s"]||o["l2_risk"]||"").split(/[;\r\n]+/).map(s => s.trim());
        if (!mappedList.includes(l2)) return;
        let evid = String(o["Event ID"]||"").trim();
        if (evid && seen.has(evid)) return;
        if (evid) seen.add(evid);
        eo.push(o);
    });
    let rows = eo.map(o => ({
        id: o["Event ID"]||"",
        title: o["Event Title"]||"",
        severity: o["Final Event Classification"]||"",
        status: o["Event Status"]||"",
    }));
    return renderEvidenceSection({
        label: "Operational Risk Events",
        rows: rows,
        severityLabel: "Class",
        severityOrder: ["Class A","Class B","Class C"],
        severityPalette: "oreClass",
    });
}

function renderRelevantPRSA(eid, l2) {
    if (isEmpty(eid) || isEmpty(l2) || !prsaData.length) return "";
    let eidCol = resolveCol(prsaData, ["AE ID", "Audit Entity ID"]);
    if (!eidCol) return "";
    // Deduplicate by Issue ID -- a single issue may appear as multiple
    // control rows.
    let seen = new Set();
    let ep = [];
    prsaData.forEach(p => {
        let pEid = String(p[eidCol]||"").trim();
        if (pEid !== String(eid)) return;
        let mappedList = String(p["Mapped L2s"]||"").split(/[;\r\n]+/).map(s => s.trim());
        if (!mappedList.includes(l2)) return;
        let iid = String(p["Issue ID"]||"").trim();
        if (iid && seen.has(iid)) return;
        if (iid) seen.add(iid);
        ep.push(p);
    });
    let rows = ep.map(p => ({
        id: p["Issue ID"]||"",
        title: p["Issue Title"]||"",
        severity: p["Issue Rating"]||"",
        status: p["Issue Status"]||"",
    }));
    return renderEvidenceSection({
        label: "PRSA Issues",
        rows: rows,
        severityLabel: "Rating",
        severityOrder: ["Critical","High","Medium","Low"],
        severityPalette: "severity",
    });
}

function renderRelevantRAPs(eid, l2) {
    if (isEmpty(eid) || isEmpty(l2) || !graRapsData.length) return "";
    let eidCol = resolveCol(graRapsData, ["Audit Entity ID"]);
    if (!eidCol) return "";
    let er = graRapsData.filter(g => {
        let gEid = String(g[eidCol]||"").trim();
        if (gEid !== String(eid)) return false;
        let mappedList = String(g["Mapped L2s"]||"").split(/[;\r\n]+/).map(s => s.trim());
        return mappedList.includes(l2);
    });
    let rows = er.map(g => ({
        id: g["RAP ID"]||"",
        title: g["RAP Header"]||"",
        status: g["RAP Status"]||"",
    }));
    return renderEvidenceSection({
        label: "GRA RAPs",
        rows: rows,
        idLabel: "ID",
        titleLabel: "Header",
        hasSeverity: false,
    });
}

// ================================================================
// CONTROL ASSESSMENT
// ================================================================
function renderControlAssessment(row, eid, l2) {
    let baseline = row["Control Effectiveness Baseline"] || "";
    if (isAbsence(baseline)) return "";

    let m = String(baseline).match(/^(.+?) \(Last audit: (.+?), (.+?) \u00b7 Next planned: (.+?)\)$/);
    let rating = m ? m[1].trim() : String(baseline).trim();
    let auditResult = m ? m[2].trim() : "";
    let auditDate = m ? m[3].trim() : "";
    let nextDate = m ? m[4].trim() : "";
    let isPh = v => !v || v === "date unknown" || v === "not scheduled" || v.toLowerCase() === "nan";

    let html = '<div class="drill-section"><span class="label">Control Assessment</span>';
    let segments = [];
    if (!isPh(auditResult)) segments.push("Last audit " + auditResult);
    if (!isPh(auditDate)) segments.push(auditDate);
    if (!isPh(nextDate)) segments.push("next planned " + nextDate);
    let contextText = segments.join(" \u00b7 ");

    html += '<div>'
        + '<span style="margin-right:8px;">' + makePill(rating, "controlRating") + '</span>'
        + (contextText ? '<span style="font-size:13px;color:var(--gray);">' + esc(contextText) + '</span>' : "")
        + '</div>';
    html += '</div>';
    return html;
}

function renderControlRatings(row) {
    let controls = [["IAG Control Effectiveness", row["IAG Control Effectiveness"]],
                   ["Aligned Assurance Rating", row["Aligned Assurance Rating"]],
                   ["Management Awareness Rating", row["Management Awareness Rating"]]];
    let valid = controls.filter(([,v]) => !isEmpty(v));
    if (!valid.length) return "";
    let html = '<div class="drill-section"><span class="label">Control Ratings <em style="text-transform:none;letter-spacing:0;font-weight:400;">(starting point)</em></span>';
    html += '<table class="rating-table">';
    valid.forEach(([l,v]) => { html += '<tr><td>' + esc(l) + '</td><td><span class="rating-bar">' + ratingBar(v) + '</span></td></tr>'; });
    html += '</table></div>';
    return html;
}

// ================================================================
// DRILL-DOWN BODY (unified)
// Reading order:
//   1. Outcome: Decision Basis (+ sibling matches for Undetermined rows)
//   2. "Why this risk applies" -- sub-risks, source rationale, signals
//   3. "How it's controlled" -- control ratings, control assessment, IAG
//      issues (with contradiction warning), OREs, PRSA, RAPs
// Sections self-suppress when empty; super-section headers only render
// when the group has at least one non-empty section.
// ================================================================
function renderDrilldownBody(row, detailRow, entityDetailRows, eid) {
    let status = row["Status"] || "";
    let l2 = row["New L2"] || "";
    let html = "";

    html += renderDecisionBasis(row, status);
    if (status === "Applicability Undetermined") {
        html += renderSiblingMatches(row, entityDetailRows);
    }

    // Group 1: Why this risk applies
    let whyContent = "";
    whyContent += renderSubRiskDescriptions(detailRow, eid, l2);
    whyContent += renderSourceRationale(detailRow);
    whyContent += renderSignals(row["Additional Signals"]);
    if (whyContent) {
        html += '<div class="drill-supersection">Why this risk applies</div>' + whyContent;
    }

    // Group 2: How it's controlled
    let howContent = "";
    howContent += renderControlRatings(row);
    howContent += renderControlAssessment(row, eid, l2);
    howContent += renderRelevantFindings(row, eid, l2);
    howContent += renderRelevantOREs(eid, l2);
    howContent += renderRelevantPRSA(eid, l2);
    howContent += renderRelevantRAPs(eid, l2);
    if (howContent) {
        html += '<div class="drill-supersection">How it\u2019s controlled</div>' + howContent;
    }

    return html;
}

// ================================================================
// INVENTORY RENDERERS
// ================================================================
// One focused function per inventory type. Previously all five (apps, TPs,
// models, policies, laws) were inlined inside renderEntityView.

const _tierRank = {Primary:0, Secondary:1, Applicable:0, Additional:1};
function _byTierThenName(a, b) {
    let ta = _tierRank[a.tier] ?? 9, tb = _tierRank[b.tier] ?? 9;
    if (ta !== tb) return ta - tb;
    return String(a.sortKey||"").localeCompare(String(b.sortKey||""));
}
function _plural(n, s, p) { return n + " " + (n === 1 ? s : p); }
function _splitList(v) { return String(v||"").split(/[;\r\n]+/).map(s => s.trim()).filter(Boolean); }

function renderAppsInventory(primaryIds, secondaryIds) {
    if (!primaryIds.length && !secondaryIds.length) return "";
    let appById = {};
    applicationsInventory.forEach(a => { let k = String(a[INVENTORY_COLS.appId]||"").trim(); if (k) appById[k] = a; });

    let items = [];
    primaryIds.forEach(id => items.push({tier: "Primary", id, rec: appById[id], sortKey: (appById[id] && appById[id][INVENTORY_COLS.appName]) || id}));
    secondaryIds.forEach(id => items.push({tier: "Secondary", id, rec: appById[id], sortKey: (appById[id] && appById[id][INVENTORY_COLS.appName]) || id}));
    items.sort(_byTierThenName);

    let rows = items.map(r => {
        if (!r.rec) return [
            '<span class="meta">(not found in applications inventory)</span>',
            '\u2014', '\u2014', '\u2014', esc(r.tier), esc(r.id),
        ];
        let rec = r.rec;
        return [
            esc(String(rec[INVENTORY_COLS.appName]||"")),
            makePill(rec[INVENTORY_COLS.appConfidence]||"", "severity"),
            makePill(rec[INVENTORY_COLS.appAvailability]||"", "severity"),
            makePill(rec[INVENTORY_COLS.appIntegrity]||"", "severity"),
            esc(r.tier),
            esc(r.id),
        ];
    });

    return '<h4>Applications</h4>'
        + '<p class="meta">' + _plural(items.length, "application", "applications") + ' \u2014 ' + primaryIds.length + ' Primary, ' + secondaryIds.length + ' Secondary</p>'
        + buildTableHTML({
            id: "inv-apps",
            headers: ["Name", "Confidentiality", "Availability", "Integrity", "Tier", "ID"],
            rows: rows,
        });
}

function renderThirdPartiesInventory(primaryIds, secondaryIds) {
    if (!primaryIds.length && !secondaryIds.length) return "";
    let tpById = {};
    thirdpartiesInventory.forEach(t => { let k = String(t[INVENTORY_COLS.tpId]||"").trim(); if (k) tpById[k] = t; });

    let items = [];
    primaryIds.forEach(id => items.push({tier: "Primary", id, rec: tpById[id], sortKey: (tpById[id] && tpById[id][INVENTORY_COLS.tpName]) || id}));
    secondaryIds.forEach(id => items.push({tier: "Secondary", id, rec: tpById[id], sortKey: (tpById[id] && tpById[id][INVENTORY_COLS.tpName]) || id}));
    items.sort(_byTierThenName);

    let rows = items.map(r => {
        if (!r.rec) return [
            '<span class="meta">(not found in third parties inventory)</span>',
            '\u2014', esc(r.tier), esc(r.id),
        ];
        let nm = r.rec[INVENTORY_COLS.tpName] || "";
        let risk = r.rec[INVENTORY_COLS.tpOverallRisk] || "";
        return [
            esc(String(nm)),
            makePill(risk, "severity"),
            esc(r.tier),
            esc(r.id),
        ];
    });

    return '<h4>Third Parties</h4>'
        + '<p class="meta">' + _plural(items.length, "third party", "third parties") + ' \u2014 ' + primaryIds.length + ' Primary, ' + secondaryIds.length + ' Secondary</p>'
        + buildTableHTML({
            id: "inv-tps",
            headers: ["Name", "Overall Risk", "Tier", "TLM ID"],
            rows: rows,
        });
}

function renderModelsInventory(modelList) {
    if (!modelList.length) return "";
    let sorted = modelList.slice().sort((a,b) => String(a).localeCompare(String(b)));
    let rows = sorted.map(n => [esc(n)]);
    return '<h4>Models</h4>'
        + '<p class="meta">' + _plural(modelList.length, "model", "models") + '</p>'
        + buildTableHTML({
            id: "inv-models",
            headers: ["Name"],
            rows: rows,
        });
}

function renderPoliciesInventory(policyIds) {
    if (!policyIds.length) return "";
    let pspById = {};
    policiesInventory.forEach(p => { let k = String(p[INVENTORY_COLS.pspId]||"").trim(); if (k) pspById[k] = p; });

    let items = policyIds.map(id => {
        let rec = pspById[id];
        return {id, rec, sortKey: (rec && rec[INVENTORY_COLS.pspName]) || id};
    });
    items.sort((a,b) => String(a.sortKey).localeCompare(String(b.sortKey)));

    let rows = items.map(r => {
        if (!r.rec) return ['<span class="meta">(not found in policies inventory)</span>', esc(r.id)];
        return [esc(String(r.rec[INVENTORY_COLS.pspName]||"")), esc(r.id)];
    });

    return '<h4>Policies / Standards / Procedures</h4>'
        + '<p class="meta">' + _plural(items.length, "policy", "policies") + '</p>'
        + buildTableHTML({
            id: "inv-policies",
            headers: ["Name", "ID"],
            rows: rows,
        });
}

function renderLawsInventory(applicIds, additionalIds) {
    if (!applicIds.length && !additionalIds.length) return "";
    let manById = {};
    lawsInventory.forEach(m => { let k = String(m[INVENTORY_COLS.manId]||"").trim(); if (k) manById[k] = m; });

    let seen = new Set();
    let ids = [];
    [...applicIds, ...additionalIds].forEach(id => { if (id && !seen.has(id)) { seen.add(id); ids.push(id); } });

    let items = ids.map(id => {
        let rec = manById[id];
        return {id, rec, sortKey: (rec && rec[INVENTORY_COLS.manTitle]) || id};
    });
    items.sort((a, b) => String(a.sortKey).localeCompare(String(b.sortKey)));

    let rows = items.map(r => {
        if (!r.rec) return ['<span class="meta">(not found in mandates inventory)</span>', '\u2014', esc(r.id)];
        return [
            esc(String(r.rec[INVENTORY_COLS.manTitle]||"")),
            esc(String(r.rec[INVENTORY_COLS.manApplicability]||"\u2014")),
            esc(r.id),
        ];
    });

    return '<h4>Laws &amp; Regulations</h4>'
        + '<p class="meta">' + _plural(items.length, "mandate", "mandates") + '</p>'
        + buildTableHTML({
            id: "inv-laws",
            headers: ["Name", "Applicability", "ID"],
            rows: rows,
        });
}

// Build the inventories expander header (count summary) + body HTML.
function renderInventoriesSection(legacyRow) {
    if (!legacyRow) return {header: "Inventories", body: "<p class='meta'>No inventory items for this entity.</p>"};

    let primaryApps = _splitList(legacyRow[INVENTORY_COLS.legacyPrimaryIT]).filter(x => !isAbsence(x));
    let secondaryApps = _splitList(legacyRow[INVENTORY_COLS.legacySecondaryIT]).filter(x => !isAbsence(x));
    let primaryTPs = _splitList(legacyRow[INVENTORY_COLS.legacyPrimaryTP]).filter(x => !isAbsence(x));
    let secondaryTPs = _splitList(legacyRow[INVENTORY_COLS.legacySecondaryTP]).filter(x => !isAbsence(x));
    let modelList = _splitList(legacyRow["Models (View Only)"]).filter(x => !isAbsence(x));
    let policyList = _splitList(legacyRow[INVENTORY_COLS.legacyPolicies]).filter(x => !isAbsence(x));
    let lawsApplic = _splitList(legacyRow[INVENTORY_COLS.legacyLawsApplic]).filter(x => !isAbsence(x));
    let lawsAdd = _splitList(legacyRow[INVENTORY_COLS.legacyLawsAdd]).filter(x => !isAbsence(x));

    let hasApps = primaryApps.length || secondaryApps.length;
    let hasTPs = primaryTPs.length || secondaryTPs.length;
    let hasModels = modelList.length;
    let hasPolicies = policyList.length;
    let hasLaws = lawsApplic.length || lawsAdd.length;

    if (!(hasApps || hasTPs || hasModels || hasPolicies || hasLaws)) {
        return {header: "Inventories", body: "<p class='meta'>No inventory items for this entity.</p>"};
    }

    let invCounts = [];
    if (hasApps) invCounts.push(_plural(primaryApps.length + secondaryApps.length, "application", "applications"));
    if (hasTPs) invCounts.push(_plural(primaryTPs.length + secondaryTPs.length, "third party", "third parties"));
    if (hasModels) invCounts.push(_plural(modelList.length, "model", "models"));
    if (hasPolicies) invCounts.push(_plural(policyList.length, "policy", "policies"));
    if (hasLaws) invCounts.push(_plural(lawsApplic.length + lawsAdd.length, "mandate", "mandates"));
    let header = "Inventories \u2014 " + invCounts.join(", ");

    let body = "";
    body += renderAppsInventory(primaryApps, secondaryApps);
    body += renderThirdPartiesInventory(primaryTPs, secondaryTPs);
    body += renderModelsInventory(modelList);
    body += renderPoliciesInventory(policyList);
    body += renderLawsInventory(lawsApplic, lawsAdd);

    return {header, body};
}

// ==================== FILTERING ====================
let currentView = "entity";

function getSelectedStatuses() {
    let checked = [];
    document.querySelectorAll("#status-checkboxes input:checked").forEach(cb => checked.push(cb.value));
    return checked;
}

function applyFilters() {
    if (currentView === "entity") renderEntityView();
    else if (currentView === "risk") renderRiskView();
}

function getFilteredAuditData(baseFilter) {
    let data = baseFilter || auditData;
    let statuses = getSelectedStatuses();
    if (statuses.length > 0) {
        data = data.filter(r => statuses.includes(r["Status"]));
    }
    if (currentView !== "entity") {
        let al = document.getElementById("filter-al").value;
        let pga = document.getElementById("filter-pga").value;
        let team = document.getElementById("filter-team").value;
        if (al) data = data.filter(r => String(getEntityMeta(r["Entity ID"])["Audit Leader"] || "") === al);
        if (pga) data = data.filter(r => String(getEntityMeta(r["Entity ID"])["PGA"] || "") === pga);
        if (team) data = data.filter(r => String(getEntityMeta(r["Entity ID"])["Core Audit Team"] || "") === team);
    }
    return data;
}

// ==================== VIEW SWITCHING ====================
function switchView(name) {
    currentView = name;
    document.querySelectorAll(".tab-content").forEach(t => t.classList.remove("active"));
    document.getElementById("tab-" + name).classList.add("active");
    document.getElementById("sidebar-entity-select").style.display = name === "entity" ? "block" : "none";
    document.getElementById("sidebar-risk-select").style.display = name === "risk" ? "block" : "none";
    document.getElementById("sidebar-status-filter").style.display = "block";
    document.getElementById("sidebar-org-filters").style.display = name !== "entity" ? "block" : "none";
    if (name === "entity") renderEntityView();
    if (name === "risk") renderRiskView();
}

function switchEntityTab(name) {
    document.querySelectorAll(".sub-tab-content").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".sub-tab").forEach(t => t.classList.remove("active"));
    document.getElementById("entity-tab-" + name).classList.add("active");
    let idx = ["profile","drill","legacy","source","trace"].indexOf(name);
    document.querySelectorAll(".sub-tab")[idx].classList.add("active");
}

// ==================== ENTITY VIEW ====================
function renderEntityView() {
    let eid = document.getElementById("entity-select").value;
    if (!eid) return;
    let baseRows = auditData.filter(r => r["Entity ID"] === eid);
    let rows = getFilteredAuditData(baseRows);
    if (!rows.length) {
        document.getElementById("entity-title").innerHTML = '<h2 style="border:none;margin-top:0;">Entity: ' + esc(eid) + '</h2>';
        document.getElementById("entity-banner").innerHTML = '<div class="banner banner-info">No rows match the current filters.</div>';
        return;
    }
    let undetermined = rows.filter(r => r["Status"] === "Applicability Undetermined").length;
    let assumedNA = rows.filter(r => r["Status"] === "No Evidence Found \u2014 Verify N/A").length;

    document.getElementById("entity-title").innerHTML = '<h2 style="border:none;margin-top:0;">Entity: ' + esc(eid) + '</h2>';
    makeBanner("entity-banner", rows.length, undetermined, assumedNA, eid);

    // Unmapped findings banner
    let unmappedHtml = "";
    let eidColF = resolveCol(findingsData, ["entity_id", "Audit Entity ID"]);
    if (eidColF) {
        let ef = findingsData.filter(f => String(f[eidColF]||"").trim() === eid);
        let unmapped = ef.filter(f => String(f["Mapping Status"]||"").startsWith("Filtered") && String(f["Mapping Status"]||"").toLowerCase().includes("unmappable"));
        if (unmapped.length) {
            let legacyCats = new Set();
            unmapped.forEach(f => {
                let d = String(f["Mapping Status"]||"");
                let ps = d.indexOf("("), pe = d.indexOf(")");
                if (ps !== -1 && pe !== -1) d.substring(ps+1, pe).split(";").forEach(c => { c = c.trim(); if (c) legacyCats.add(c); });
            });
            let catList = legacyCats.size ? Array.from(legacyCats).sort().join(", ") : "legacy risk categories";
            unmappedHtml = '<div class="banner banner-warn">This entity has <strong>' + unmapped.length + ' IAG issue(s)</strong> tagged to legacy risk categories (' + esc(catList) + ') that could not be mapped to a specific L2 risk. These are not reflected in any L2 row below. See <strong>Source Data &gt; IAG Issues</strong> for details.</div>';
        }
    }
    document.getElementById("unmapped-findings-banner").innerHTML = unmappedHtml;

    // Context
    let em = getEntityMeta(eid);
    let ctxHtml = '<div class="entity-context">';
    if (!isEmpty(em["Entity Name"])) ctxHtml += '<h3>' + esc(em["Entity Name"]) + '</h3>';
    if (!isEmpty(em["Entity Overview"])) ctxHtml += '<div class="overview">' + formatOverview(em["Entity Overview"], eid) + '</div>';
    let meta = [];
    if (!isEmpty(em["Audit Leader"])) meta.push("Audit Leader: " + em["Audit Leader"]);
    if (!isEmpty(em["PGA"])) meta.push("PGA: " + em["PGA"]);
    if (meta.length) ctxHtml += '<p class="meta">' + meta.join(" \u00B7 ") + '</p>';

    let legacyRow = legacyData.find(r => String(r["Audit Entity ID"]||"").trim() === eid);
    if (legacyRow) {
        let hFrom = legacyRow["Hand-offs from Other Audit Entities"];
        let hTo = legacyRow["Hand-offs to Other Audit Entities"];
        let hDesc = legacyRow["Hand-off Description"];
        if (!isAbsence(hFrom) || !isAbsence(hTo) || !isAbsence(hDesc)) {
            let parseIds = v => isAbsence(v) ? [] : String(v).split(/[;\r\n]+/).map(s => s.trim()).filter(Boolean);
            let fromIds = parseIds(hFrom);
            let toIds = parseIds(hTo);
            let renderCol = (ids, labelText) => {
                if (!ids.length) return "";
                let entries = ids.map(id => {
                    let name = entityNameMap[id] || "";
                    return '<div class="handoff-entry"><span class="handoff-id">' + esc(id) + '</span><span class="handoff-name">' + esc(name) + '</span></div>';
                }).join("");
                return '<div class="handoff-col"><div class="handoff-col-label">' + labelText + ' (' + ids.length + ')</div>' + entries + '</div>';
            };
            let fromCol = renderCol(fromIds, "\u2190 From");
            let toCol = renderCol(toIds, "To \u2192");
            let grid = (fromCol || toCol) ? '<div class="handoff-stack">' + fromCol + toCol + '</div>' : "";
            let descHtml = isAbsence(hDesc) ? "" : '<div class="handoff-desc">' + esc(String(hDesc)) + '</div>';
            ctxHtml += '<div class="drill-section"><span class="label">Handoffs</span>' + grid + descHtml + '</div>';
        }
    }

    ctxHtml += "</div><div class='divider'></div>";
    document.getElementById("entity-context").innerHTML = ctxHtml;

    // Sort
    let statusOrder = {};
    Object.keys(STATUS_CONFIG).forEach(s => statusOrder[s] = STATUS_CONFIG[s].sort);
    rows.sort((a,b) => {
        let sa = statusOrder[a["Status"]]??99, sb = statusOrder[b["Status"]]??99;
        if (sa !== sb) return sa - sb;
        let ra = RATING_RANK[a["Inherent Risk Rating"]]||0, rb = RATING_RANK[b["Inherent Risk Rating"]]||0;
        return rb - ra;
    });

    let entityDetail = detailData.filter(d => String(d["entity_id"]) === String(eid));

    // --- Risk Profile tab ---
    let overviewCols = ["New L1","New L2","Status","Confidence","Inherent Risk Rating","Legacy Source","Decision Basis","Additional Signals"];
    if (rows.length && rows[0].hasOwnProperty("Control Effectiveness Baseline")) overviewCols.push("Control Effectiveness Baseline");
    if (rows.length && rows[0].hasOwnProperty("Impact of Issues")) overviewCols.push("Impact of Issues");
    if (rows.length && rows[0].hasOwnProperty("Control Signals")) overviewCols.push("Control Signals");
    let profileRows = rows.map(r => overviewCols.map(c => {
        let v = r[c];
        if (c === "Status") return statusLabel(v);
        if (c === "Inherent Risk Rating") return isEmpty(v) ? "\u2014" : String(v);
        return isEmpty(v) ? "" : String(v);
    }));
    let profileHeaderOverride = {"Inherent Risk Rating": "Legacy Rating"};
    let profileToolCols = new Set(["Status", "Confidence", "Decision Basis", "Additional Signals"]);
    let profileHeaders = overviewCols.map(c => ({
        label: profileHeaderOverride[c] || c,
        tool: profileToolCols.has(c),
    }));
    makeTable("entity-profile-table", profileHeaders, profileRows);

    // --- Legacy Profile tab ---
    let legacyHtml = "";
    if (legacyRatingsData.length) {
        let eidCol = resolveCol(legacyRatingsData, ["Entity ID", "Audit Entity ID"]);
        if (eidCol) {
            let lr = legacyRatingsData.filter(r => String(r[eidCol]||"").trim() === eid);
            if (lr.length) {
                let emptyCell = '<span class="empty-cell">\u2014</span>';
                let rows = lr.map(r => [
                    esc(String(r["Risk Pillar"]||"")),
                    makePill(r["Inherent Risk Rating"]||"", "severity"),
                    isEmpty(r["Inherent Risk Rationale"]) ? emptyCell : esc(String(r["Inherent Risk Rationale"])),
                    makePill(r["Control Assessment"]||"", "controlRating"),
                    isEmpty(r["Control Assessment Rationale"]) ? emptyCell : esc(String(r["Control Assessment Rationale"])),
                ]);
                legacyHtml = buildTableHTML({
                    id: "legacy-ratings-table",
                    headers: [
                        {label: "Risk Pillar", width: "160px"},
                        {label: "Inherent Risk", width: "110px"},
                        {label: "Risk Rationale"},
                        {label: "Control Assessment", width: "180px"},
                        {label: "Control Rationale"},
                    ],
                    rows: rows,
                });
            } else { legacyHtml = "<p class='meta'>No legacy ratings found for this entity.</p>"; }
        } else { legacyHtml = "<p class='meta'>Legacy ratings data missing entity column.</p>"; }
    } else { legacyHtml = "<p class='meta'>No legacy ratings data in workbook.</p>"; }
    document.getElementById("entity-legacy-ratings").innerHTML = legacyHtml;

    // --- Drill-Down tab ---
    let ddHtml = "";
    rows.forEach(r => {
        let l2 = r["New L2"]||"";
        let status = r["Status"]||"";
        let irr = r["Inherent Risk Rating"]||"";
        let label = icon(status) + " " + (r["New L1"]||"") + " / " + l2 + " \u00B7 " + status;
        if (!isEmpty(irr) && irr !== "Not Applicable" && irr !== "\u2014") label += " \u00B7 " + irr;
        let detail = detailData.find(d => String(d["entity_id"])===eid && d["new_l2"]===l2);
        let body = renderDrilldownBody(r, detail, entityDetail, eid);
        ddHtml += mkExpander(false, label, body, "entity-drill:" + eid + ":" + l2);
    });
    document.getElementById("entity-drilldown").innerHTML = ddHtml;

    // --- Traceability tab ---
    let traceHtml = "";
    if (entityDetail.length) {
        traceHtml += "<h3>Multi-Mapping Fan-Out</h3>";
        let pillars = [...new Set(entityDetail.map(d => basePillar(d["source_legacy_pillar"]||"")))].filter(p => p && p !== "nan" && p !== "None" && p !== "Findings").sort();
        pillars.forEach(pillar => {
            let pr = entityDetail.filter(d => String(d["source_legacy_pillar"]||"").includes(pillar));
            if (pr.length <= 1) return;
            let rawR = pr.map(d => d["source_risk_rating_raw"]).filter(x => !isEmpty(x));
            let rStr = rawR.length ? String(rawR[0]) : "unknown";
            let statusCounts = {};
            pr.forEach(p => {
                let s = methodToStatus(String(p["method"]||""));
                statusCounts[s] = (statusCounts[s]||0) + 1;
            });
            let parts = [];
            Object.keys(STATUS_CONFIG).forEach(s => {
                if (statusCounts[s]) parts.push(statusCounts[s] + " " + STATUS_CONFIG[s].icon);
            });
            let label = "\ud83d\udcc2 " + esc(pillar) + " (rated " + esc(rStr) + ") \u2192 " + parts.join(", ");
            let body = "";
            pr.forEach(p => {
                let s = methodToStatus(String(p["method"]||""));
                let ic = STATUS_CONFIG[s] ? STATUS_CONFIG[s].icon : "?";
                body += '<div>' + ic + ' <strong>' + esc(p["new_l2"]) + '</strong> \u2014 ' + esc(s) + '</div>';
            });
            traceHtml += mkExpander(false, label, body, "trace:" + eid + ":" + pillar);
        });

        let dedupRows = entityDetail.filter(d => String(d["source_legacy_pillar"]||"").includes("also:"));
        if (dedupRows.length) {
            traceHtml += "<h3>Convergence</h3>";
            dedupRows.forEach(dr => {
                let src = String(dr["source_legacy_pillar"]||"");
                let primary = src.split(" (also:")[0].trim();
                let also = [];
                let rem = src;
                while (rem.includes("(also:")) {
                    let s = rem.indexOf("(also:") + 6;
                    let e = rem.indexOf(")", s);
                    if (e === -1) break;
                    also.push(rem.substring(s, e).trim());
                    rem = rem.substring(e + 1);
                }
                let r = dr["source_risk_rating_raw"];
                let rStr = isEmpty(r) ? "no rating" : String(r);
                traceHtml += '<div><strong>' + esc(dr["new_l2"]) + '</strong> \u2190 ' + esc([primary, ...also].join(" + ")) + ' \u2192 kept ' + esc(rStr) + '</div>';
            });
        }
    } else {
        traceHtml = '<p class="meta">No traceability data available.</p>';
    }
    document.getElementById("entity-traceability").innerHTML = traceHtml;

    // --- Source Data tab ---
    let srcHtml = "";

    // === Scope group ===
    srcHtml += "<h2>Scope</h2>";

    // Inventories
    let inv = renderInventoriesSection(legacyRow);
    srcHtml += mkExpander(true, inv.header, inv.body, "src-inventories");

    // Sub-Risks
    let es = subRisksData.filter(s => String(s["entity_id"]||s["Audit Entity"]||s["Audit Entity ID"]||"").trim() === eid);
    let subHeader = 'Sub-Risks \u2014 ' + es.length + ' sub-risk' + (es.length === 1 ? "" : "s");
    let subBody = "";
    if (es.length) {
        let subRows = es.map(s => [
            esc(String(s["risk_id"]||s["Key Risk ID"]||"")),
            esc(String(s["risk_description"]||s["Key Risk Description"]||"").substring(0,200)),
            esc(String(s["legacy_l1"]||s["Level 1 Risk Category"]||"")),
            esc(String(s["sub_risk_rating"]||s["Inherent Risk Rating"]||"")),
            esc(String(s["L2 Keyword Matches"]||s["Contributed To (keyword matches)"]||"")),
        ]);
        subBody = buildTableHTML({
            id: "src-subrisks-table",
            headers: [
                "Risk ID", "Description", "Legacy L1", "Rating",
                {label: "L2 Keyword Matches", tool: true},
            ],
            rows: subRows,
        });
    } else {
        subHeader = "Sub-Risks";
        subBody = "<p class='meta'>No sub-risk descriptions for this entity.</p>";
    }
    srcHtml += mkExpander(true, subHeader, subBody, "src-subrisks");

    srcHtml += "<div class='divider'></div>";

    // === Issues & Events group ===
    srcHtml += "<h2>Issues &amp; Events</h2>";

    // IAG Issues
    let efEidCol = resolveCol(findingsData, ["entity_id", "Audit Entity ID"]);
    let efAll = efEidCol ? findingsData.filter(f => String(f[efEidCol]||"").trim() === eid) : [];
    let iagHeader = "IAG Issues";
    let iagBody = '<div class="banner banner-warn">Only Approved findings with active statuses (Open, In Validation, In Sustainability) drive L2 applicability. Findings still in L1/L2 review workflow, or with Closed / Cancelled / Not Started status, are listed here for reference but do not fire an "Issue confirmed" decision.</div>';
    if (efAll.length) {
        iagHeader = 'IAG Issues \u2014 ' + efAll.length + ' issue' + (efAll.length === 1 ? "" : "s") + severitySummary(efAll, f => f["severity"]||f["Final Reportable Finding Risk Rating"], ["Critical","High","Medium","Low"]);
        let iagRows = efAll.map(f => [
            esc(String(f["issue_id"]||f["Finding ID"]||"")),
            esc(String(f["issue_title"]||f["Finding Name"]||"")),
            esc(String(f["Finding Description"]||f["finding_description"]||"")),
            makePill(f["severity"]||f["Final Reportable Finding Risk Rating"]||"", "severity"),
            esc(String(f["status"]||f["Finding Status"]||"")),
            esc(String(f["l2_risk"]||f["Risk Dimension Categories"]||"")),
            esc(String(f["Mapping Status"]||"")),
        ]);
        iagBody += buildTableHTML({
            id: "src-iag-table",
            headers: [
                "Finding ID", "Title", "Description", "Severity", "Status",
                {label: "L2 Risk", tool: true},
                {label: "Mapping Status", tool: true},
            ],
            rows: iagRows,
        });
    } else {
        iagBody += "<p class='meta'>No IAG issues for this entity.</p>";
    }
    srcHtml += mkExpander(false, iagHeader, iagBody, "src-iag");

    // OREs
    let oreHeader = "Operational Risk Events (OREs)";
    let oreBody = '<div class="banner banner-info">ORE events are mapped to L2 risks by semantic similarity of event title and description to the new taxonomy definitions. Closed and canceled events, and events missing a title or description, are excluded before mapping. All remaining events are shown regardless of mapping status.</div>';
    if (oreData.length) {
        let oreEidCol = resolveCol(oreData, ["entity_id", "Audit Entity (Operational Risk Events)", "Audit Entity ID"]);
        if (oreEidCol) {
            let eo = oreData.filter(o => String(o[oreEidCol]||"").trim() === eid);
            if (eo.length) {
                oreHeader = 'Operational Risk Events (OREs) \u2014 ' + eo.length + ' ORE' + (eo.length === 1 ? "" : "s") + severitySummary(eo, o => o["Final Event Classification"], ["Class A","Class B","Class C","Near Miss"]);
                let oreApproved = [
                    {k:"Event ID"}, {k:"Event Title"}, {k:"Event Description"},
                    {k:"Final Event Classification", pill:"oreClass"}, {k:"Event Status"},
                    {k:"Mapped L2s", label:"Suggested L2s", tool:true},
                    {k:"Mapping Status", tool:true},
                ];
                let cols = oreApproved.filter(c => eo[0].hasOwnProperty(c.k));
                let oreHeaders = cols.map(c => ({label: c.label || c.k, tool: !!c.tool}));
                let oreRows = eo.map(o => cols.map(c => {
                    let raw = o[c.k] || "";
                    if (c.pill) return makePill(raw, c.pill);
                    return esc(String(raw));
                }));
                oreBody += buildTableHTML({
                    id: "src-ore-table",
                    headers: oreHeaders,
                    rows: oreRows,
                });
            } else { oreBody += "<p class='meta'>No OREs for this entity.</p>"; }
        } else { oreBody += "<p class='meta'>ORE data missing entity ID column.</p>"; }
    } else { oreBody += "<p class='meta'>No ORE data in workbook.</p>"; }
    srcHtml += mkExpander(false, oreHeader, oreBody, "src-ore");

    // PRSA Issues
    let prsaHeader = "PRSA Issues";
    let prsaBody = '<div class="banner banner-info">PRSA issues are mapped to L2 risks by semantic similarity of issue text to the new taxonomy definitions. All issues are shown regardless of mapping status.</div>';
    if (prsaData.length) {
        let prsaEidCol = resolveCol(prsaData, ["AE ID", "Audit Entity", "Audit Entity ID"]);
        if (prsaEidCol) {
            let ep = prsaData.filter(p => String(p[prsaEidCol]||"").trim() === eid);
            if (ep.length) {
                prsaHeader = 'PRSA Issues \u2014 ' + ep.length + ' record' + (ep.length === 1 ? "" : "s") + severitySummary(ep, p => p["Issue Rating"], ["Critical","High","Medium","Low"]);
                let prsaApproved = ["PRSA ID", "Issue ID", "Issue Title", "Issue Description", "Control Title", "Process Title", "Issue Rating", "Issue Status", "Control ID (PRSA)", "Other AEs With This PRSA", "Mapped L2s", "Mapping Status"];
                let cols = prsaApproved.filter(c => ep[0].hasOwnProperty(c));
                let prsaRows = ep.map(p => cols.map(c => {
                    if (c === "Issue Rating") return makePill(p[c]||"", "severity");
                    return esc(String(p[c]||""));
                }));
                prsaBody += buildTableHTML({
                    id: "src-prsa-table",
                    headers: cols,
                    rows: prsaRows,
                });
            } else { prsaBody += "<p class='meta'>No PRSA data for this entity.</p>"; }
        } else { prsaBody += "<p class='meta'>PRSA data missing entity column.</p>"; }
    } else { prsaBody += "<p class='meta'>No PRSA data in workbook.</p>"; }
    srcHtml += mkExpander(false, prsaHeader, prsaBody, "src-prsa");

    // GRA RAPs
    let graHeader = "GRA RAPs (Regulatory Findings)";
    let graBody = '<div class="banner banner-info">GRA RAPs are mapped to L2 risks by semantic similarity of RAP header and details to the new taxonomy definitions. All RAPs are shown regardless of mapping status.</div>';
    if (graRapsData.length) {
        let graEidCol = resolveCol(graRapsData, ["Audit Entity ID"]);
        if (graEidCol) {
            let eg = graRapsData.filter(g => String(g[graEidCol]||"").trim() === eid);
            if (eg.length) {
                graHeader = 'GRA RAPs (Regulatory Findings) \u2014 ' + eg.length + ' RAP' + (eg.length === 1 ? "" : "s");
                let graApproved = ["RAP ID", "RAP Header", "RAP Status", "BU Corrective Action Due Date", "RAP Details", "Related Exams and Findings", "GRA RAPS", "Mapped L2s", "Mapping Status"];
                let cols = graApproved.filter(c => eg[0].hasOwnProperty(c));
                let graRows = eg.map(g => cols.map(c => esc(String(g[c]||""))));
                graBody += buildTableHTML({
                    id: "src-gra-table",
                    headers: cols,
                    rows: graRows,
                });
            } else { graBody += "<p class='meta'>No GRA RAPs for this entity.</p>"; }
        } else { graBody += "<p class='meta'>GRA RAPs data missing entity column.</p>"; }
    } else { graBody += "<p class='meta'>No GRA RAPs data in workbook.</p>"; }
    srcHtml += mkExpander(false, graHeader, graBody, "src-gra");

    // BM Activities
    let bmaHeader = "Business Monitoring Activities";
    let bmaBody = '<div class="banner banner-warn">Activities with a planned completion date before July 1, 2025 are not shown. See the source workbook for the complete history.</div>';
    if (bmaData.length) {
        let bmaEidCol = resolveCol(bmaData, ["Related Audit Entity", "Audit Entity ID"]);
        if (bmaEidCol) {
            let eb = bmaData.filter(b => String(b[bmaEidCol]||"").trim() === eid);
            if (eb.length) {
                bmaHeader = 'Business Monitoring Activities \u2014 ' + eb.length + ' instance' + (eb.length === 1 ? "" : "s");
                let bmaApproved = ["Activity Instance ID", "Related BM Activity Title", "Summary of Results", "If yes, please describe impact", "Business Monitoring Cases", "Planned Instance Completion Date"];
                let cols = bmaApproved.filter(c => eb[0].hasOwnProperty(c));
                let bmaRows = eb.map(b => cols.map(c => esc(String(b[c]||""))));
                bmaBody += buildTableHTML({
                    id: "src-bma-table",
                    headers: cols,
                    rows: bmaRows,
                });
            } else { bmaBody += "<p class='meta'>No BM Activities for this entity.</p>"; }
        } else { bmaBody += "<p class='meta'>BMA data missing entity column.</p>"; }
    } else { bmaBody += "<p class='meta'>No BM Activities data in workbook.</p>"; }
    srcHtml += mkExpander(false, bmaHeader, bmaBody, "src-bma");

    document.getElementById("entity-sources").innerHTML = srcHtml;
}

// ==================== RISK CATEGORY VIEW ====================
function renderRiskView() {
    let l2 = document.getElementById("risk-select").value;
    if (!l2) return;
    let baseRows = auditData.filter(r => r["New L2"] === l2);
    let rows = getFilteredAuditData(baseRows);
    if (!rows.length) {
        document.getElementById("risk-title").innerHTML = '<h2 style="border:none;margin-top:0;">Risk Category: ' + esc(l2) + '</h2>';
        document.getElementById("risk-banner").innerHTML = '<div class="banner banner-info">No rows match the current filters.</div>';
        document.getElementById("risk-metrics").innerHTML = "";
        return;
    }

    let l1Vals = [...new Set(rows.map(r => r["New L1"]).filter(x => !isEmpty(x)))];
    let l1Label = l1Vals.length ? l1Vals[0] : "";
    let titleHtml = '<h2 style="border:none;margin-top:0;">Risk Category: ' + esc(l2) + '</h2>';
    if (l1Label) titleHtml += '<div class="meta">L1: ' + esc(l1Label) + ' \u00B7 ' + new Set(rows.map(r=>r["Entity ID"])).size + ' entities in scope</div>';
    document.getElementById("risk-title").innerHTML = titleHtml;

    let undetermined = rows.filter(r => r["Status"] === "Applicability Undetermined").length;
    let assumedNA = rows.filter(r => r["Status"] === "No Evidence Found \u2014 Verify N/A").length;
    makeBanner("risk-banner", rows.length, undetermined, assumedNA, l2);

    // Summary metrics
    let totalEntities = new Set(rows.map(r => r["Entity ID"])).size;
    let applicableMask = rows.filter(r => r["Status"] === "Applicable");
    let isAI = r => String(r["Decision Basis"]||"").startsWith("AI review");
    let evidenceEntities = new Set(applicableMask.filter(r => !isAI(r)).map(r => r["Entity ID"])).size;
    let aiEntities = new Set(applicableMask.filter(r => isAI(r)).map(r => r["Entity ID"])).size;
    let applicableEntities = new Set(applicableMask.map(r => r["Entity ID"])).size;
    let pctApp = totalEntities ? (applicableEntities / totalEntities * 100).toFixed(0) : 0;
    document.getElementById("risk-metrics").innerHTML =
        '<div class="metric-card"><div class="value">' + totalEntities + '</div><div class="label">Total Entities</div></div>'
        + '<div class="metric-card"><div class="value">' + evidenceEntities + '</div><div class="label">Evidence-Based</div></div>'
        + '<div class="metric-card"><div class="value">' + aiEntities + '</div><div class="label">AI-Proposed</div></div>'
        + '<div class="metric-card"><div class="value">' + pctApp + '%</div><div class="label">% Applicable</div></div>';

    let statusOrder = {};
    Object.keys(STATUS_CONFIG).forEach(s => statusOrder[s] = STATUS_CONFIG[s].sort);
    rows.sort((a,b) => {
        let ra = RATING_RANK[a["Inherent Risk Rating"]]||0, rb = RATING_RANK[b["Inherent Risk Rating"]]||0;
        if (rb !== ra) return rb - ra;
        return (statusOrder[a["Status"]]||9) - (statusOrder[b["Status"]]||9);
    });
    let tRows = rows.map(r => {
        let rm = getEntityMeta(r["Entity ID"]);
        return [
        r["Entity ID"]||"", rm["Entity Name"]||"", rm["Audit Leader"]||"",
        isEmpty(r["Inherent Risk Rating"]) ? "\u2014" : r["Inherent Risk Rating"],
        statusLabel(r["Status"]),
        isEmpty(r["Likelihood"]) ? "\u2014" : r["Likelihood"],
        isEmpty(r["Overall Impact"]) ? "\u2014" : r["Overall Impact"],
        r["Legacy Source"]||"", r["Decision Basis"]||"",
        isEmpty(r["Additional Signals"]) ? "" : r["Additional Signals"]
        ];
    });
    makeTable("risk-entity-table",
        ["Entity ID","Entity Name","Audit Leader","Rating","Status","Likelihood","Impact","Legacy Source","Decision Basis","Signals"],
        tRows, ["str","str","str","str","str","num","num","str","str","str"]);

    let ratingCounts = {"Critical":0,"High":0,"Medium":0,"Low":0,"Not Applicable":0,"No Rating":0};
    rows.forEach(r => {
        let irr = r["Inherent Risk Rating"];
        if (isEmpty(irr)) ratingCounts["No Rating"]++;
        else if (ratingCounts.hasOwnProperty(irr)) ratingCounts[irr]++;
        else ratingCounts["No Rating"]++;
    });
    let chartLabels = Object.keys(ratingCounts).filter(k => ratingCounts[k] > 0);
    let chartColors = {"Critical":"#dc3545","High":"#e8923c","Medium":"#ffc107","Low":"#28a745","Not Applicable":"#6c757d","No Rating":"#adb5bd"};
    let maxVal = Math.max(...chartLabels.map(k => ratingCounts[k]), 1);
    let barHtml = '<div style="display:flex;flex-direction:column;gap:6px;">';
    chartLabels.forEach(k => {
        let v = ratingCounts[k];
        let pct = (v / maxVal * 100).toFixed(0);
        let color = chartColors[k] || "#ccc";
        barHtml += '<div style="display:flex;align-items:center;gap:8px;">'
            + '<div style="width:110px;text-align:right;font-size:12px;font-weight:600;color:var(--fg);white-space:nowrap;">' + k + '</div>'
            + '<div style="flex:1;background:var(--bg2);border-radius:4px;height:22px;overflow:hidden;">'
            + '<div style="width:' + pct + '%;background:' + color + ';height:100%;border-radius:4px;min-width:' + (v > 0 ? "2px" : "0") + ';"></div>'
            + '</div>'
            + '<div style="width:30px;font-size:12px;font-weight:600;color:var(--fg);">' + v + '</div>'
            + '</div>';
    });
    barHtml += '</div>';
    document.getElementById("concentration-chart").innerHTML = barHtml;

    // Per-entity drill-down
    let ddHtml = "";
    rows.forEach(r => {
        let eid2 = r["Entity ID"]||"";
        let rm = getEntityMeta(eid2);
        let status = r["Status"]||"";
        let irr = r["Inherent Risk Rating"]||"";
        let ename = rm["Entity Name"]||"";
        let parts = [icon(status) + " " + eid2];
        if (!isEmpty(ename)) parts.push(ename);
        parts.push(status);
        if (!isEmpty(irr) && irr !== "Not Applicable") parts.push(irr);
        let label = parts.join(" \u00B7 ");
        let detail = detailData.find(d => String(d["entity_id"])===eid2 && d["new_l2"]===l2);
        let entityDetailRows = detailData.filter(d => String(d["entity_id"]) === String(eid2));

        let body = '<div class="entity-context">';
        if (!isEmpty(ename)) body += '<strong>' + esc(ename) + '</strong><br>';
        if (!isEmpty(rm["Entity Overview"])) body += '<span class="meta">' + esc(rm["Entity Overview"]) + '</span><br>';
        let meta2 = [];
        if (!isEmpty(rm["Audit Leader"])) meta2.push("AL: " + esc(rm["Audit Leader"]));
        if (!isEmpty(rm["PGA"])) meta2.push("PGA: " + esc(rm["PGA"]));
        if (meta2.length) body += '<span class="meta">' + meta2.join(" \u00B7 ") + '</span>';
        body += "</div><hr style='border:none;border-top:1px solid var(--border);margin:8px 0'>";
        body += renderDrilldownBody(r, detail, entityDetailRows, eid2);
        ddHtml += mkExpander(false, label, body, "risk-drill:" + l2 + ":" + eid2);
    });
    document.getElementById("risk-drilldown").innerHTML = ddHtml;

    // IAG Issues for this L2
    let allFindings = findingsData.filter(f => {
        let fL2 = String(f["l2_risk"]||f["Mapped To L2(s)"]||f["Risk Dimension Categories"]||"");
        return fL2.includes(l2);
    });
    let inScope = new Set(rows.map(r => String(r["Entity ID"])));
    allFindings = allFindings.filter(f => inScope.has(String(f["entity_id"]||f["Audit Entity ID"]||"")));
    let fHtml = "";
    if (allFindings.length) {
        let fEntities = new Set(allFindings.map(f => f["entity_id"]||f["Audit Entity ID"]));
        fHtml = '<div class="banner banner-info"><strong>' + allFindings.length + ' IAG issues</strong> across <strong>' + fEntities.size + ' entities</strong> tagged to this L2.</div>';
        let findingRows = allFindings.map(f => [
            esc(String(f["entity_id"]||f["Audit Entity ID"]||"")),
            esc(String(f["issue_id"]||f["Finding ID"]||"")),
            makePill(f["severity"]||"", "severity"),
            esc(String(f["status"]||f["Finding Status"]||"")),
            esc(String(f["issue_title"]||f["Finding Name"]||"")),
        ]);
        fHtml += buildTableHTML({
            id: "risk-iag-table",
            headers: ["Entity", "Finding ID", "Severity", "Status", "Title"],
            rows: findingRows,
        });
    } else { fHtml = "<p class='meta'>No IAG issues tagged to this L2 in the current scope.</p>"; }
    document.getElementById("risk-findings").innerHTML = fHtml;
}

// ==================== INITIALIZATION ====================
window.addEventListener("load", () => {
    let eSelect = document.getElementById("entity-select");
    entities.forEach(e => { let o = document.createElement("option"); o.value = e; o.text = entityNameMap[e] ? e + " - " + entityNameMap[e] : e; eSelect.add(o); });
    let rSelect = document.getElementById("risk-select");
    l2Risks.forEach(l => { let o = document.createElement("option"); o.value = l; o.text = l; rSelect.add(o); });
    let alSelect = document.getElementById("filter-al");
    auditLeaders.forEach(v => { let o = document.createElement("option"); o.value = v; o.text = v; alSelect.add(o); });
    let pgaSelect = document.getElementById("filter-pga");
    pgaList.forEach(v => { let o = document.createElement("option"); o.value = v; o.text = v; pgaSelect.add(o); });
    let teamSelect = document.getElementById("filter-team");
    coreTeams.forEach(v => { let o = document.createElement("option"); o.value = v; o.text = v; teamSelect.add(o); });
    renderEntityView();
});
"""


def generate_html_report(excel_path: str, html_path: str):
    """Generate a self-contained HTML report from the transformer output Excel."""

    # Read sheets - same set as dashboard.py
    sheets = {}
    xls = pd.ExcelFile(excel_path)
    for name in ["Audit_Review", "Side_by_Side",
                 "Findings_Source", "Sub_Risks_Source",
                 "Source - Findings", "Source - Sub-Risks",
                 "Source - Legacy Data", "Source - OREs",
                 "Source - PRSA Issues",
                 "Source - BM Activities",
                 "Source - GRA RAPs",
                 "Legacy Ratings Lookup",
                 "Legacy_Ratings_Lookup"]:
        if name in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=name)
            if name == "Audit_Review":
                df = df.rename(columns={"Proposed Status": "Status",
                                        "Proposed Rating": "Inherent Risk Rating"})
            sheets[name] = df

    audit_df = sheets.get("Audit_Review", pd.DataFrame())
    detail_df = sheets.get("Side_by_Side", pd.DataFrame())
    # Support both old and new sheet names for findings/sub-risks
    findings_df = sheets.get("Source - Findings", sheets.get("Findings_Source", pd.DataFrame()))
    sub_risks_df = sheets.get("Source - Sub-Risks", sheets.get("Sub_Risks_Source", pd.DataFrame()))
    ore_df = sheets.get("Source - OREs", pd.DataFrame())
    prsa_df = sheets.get("Source - PRSA Issues", pd.DataFrame())
    bma_df = sheets.get("Source - BM Activities", pd.DataFrame())
    gra_raps_df = sheets.get("Source - GRA RAPs", pd.DataFrame())
    legacy_ratings_df = sheets.get("Legacy Ratings Lookup", sheets.get("Legacy_Ratings_Lookup", pd.DataFrame()))
    legacy_df = sheets.get("Source - Legacy Data", pd.DataFrame())

    # Load inventory source files (apps, policies, laws) directly from data/input/
    input_dir = _PROJECT_ROOT / "data" / "input"
    inventory_patterns = {"applications": "all_applications_*.xlsx",
                          "policies": "policystandardprocedure_*.xlsx",
                          "laws": "lawsandapplicability_*.xlsx",
                          "thirdparties": "all_thirdparties_*.xlsx"}
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            _cfg = yaml.safe_load(f) or {}
        _col_cfg = _cfg.get("columns", {})
        inventory_patterns = {k: _col_cfg.get("inventory_files", {}).get(k, v)
                              for k, v in inventory_patterns.items()}
    except Exception:
        _col_cfg = {}
    applications_df = _load_inventory(input_dir, inventory_patterns["applications"])
    policies_df = _load_inventory(input_dir, inventory_patterns["policies"])
    laws_df = _load_inventory(input_dir, inventory_patterns["laws"])
    thirdparties_df = _load_inventory(input_dir, inventory_patterns["thirdparties"])

    # Parse timestamp from filename
    stem = Path(excel_path).stem
    ts_str = stem.replace("transformed_risk_taxonomy_", "")
    try:
        dt = datetime.strptime(ts_str, "%m%d%Y%I%M%p")
        run_timestamp = dt.strftime("%B %d, %Y %I:%M %p").replace(" 0", " ")
    except ValueError:
        run_timestamp = ts_str

    apps_inv_cfg = _col_cfg.get("applications_inventory", {})
    policies_inv_cfg = _col_cfg.get("policies_inventory", {})
    laws_inv_cfg = _col_cfg.get("laws_inventory", {})
    tp_inv_cfg = _col_cfg.get("thirdparties_inventory", {})
    legacy_apps_cfg = _col_cfg.get("applications", {})
    legacy_pl_cfg = _col_cfg.get("policies_laws", {})
    inventory_cols = {
        "appId": apps_inv_cfg.get("id", "ARA ID"),
        "appName": apps_inv_cfg.get("name", "Application Name"),
        "appConfidence": apps_inv_cfg.get("confidence", "Confidentiality Risk"),
        "appAvailability": apps_inv_cfg.get("availability", "Availability Risk"),
        "appIntegrity": apps_inv_cfg.get("integrity", "Integrity Risk"),
        "pspId": policies_inv_cfg.get("id", "PSP ID"),
        "pspName": policies_inv_cfg.get("name", "Policy/Standard/Procedure Name"),
        "manId": laws_inv_cfg.get("id", "Applicable Mandates ID"),
        "manTitle": laws_inv_cfg.get("title", "Mandate Title"),
        "manApplicability": laws_inv_cfg.get("applicability", "Applicability to Audit Entity"),
        "tpId": tp_inv_cfg.get("id", "TLM ID"),
        "tpName": tp_inv_cfg.get("name", "Third Party Name (L3)"),
        "tpOverallRisk": tp_inv_cfg.get("overall_risk", "Overall Risk"),
        "legacyPrimaryIT": legacy_apps_cfg.get("primary_it", "PRIMARY IT APPLICATIONS (MAPPED)"),
        "legacySecondaryIT": legacy_apps_cfg.get("secondary_it", "SECONDARY IT APPLICATIONS (RELATED OR RELIED ON)"),
        "legacyPrimaryTP": legacy_apps_cfg.get("primary_tp", "PRIMARY TLM THIRD PARTY ENGAGEMENT"),
        "legacySecondaryTP": legacy_apps_cfg.get("secondary_tp", "SECONDARY TLM THIRD PARTY ENGAGEMENTS (RELATED OR RELIED ON)"),
        "legacyPolicies": legacy_pl_cfg.get("policies", "POLICIES/STANDARDS/PROCEDURES"),
        "legacyLawsApplic": legacy_pl_cfg.get("laws_applicable", "Laws & Regulations Applicability"),
        "legacyLawsAdd": legacy_pl_cfg.get("laws_additional", "Additional Laws or Regulatory Compliance"),
    }

    # Build entity metadata map (Entity ID -> {field: value}) before pruning
    # columns from audit_df. Hoisted fields are constant per entity and get
    # embedded once, not per-row.
    entity_meta = {}
    if "Entity ID" in audit_df.columns:
        meta_cols_present = [c for c in ENTITY_META_COLS if c in audit_df.columns]
        meta_df = audit_df.drop_duplicates(subset=["Entity ID"], keep="first")
        for _, r in meta_df.iterrows():
            eid = r["Entity ID"]
            if pd.isna(eid) or str(eid).strip() == "":
                continue
            eid_str = str(eid)
            vals = {}
            for c in meta_cols_present:
                v = r[c]
                vals[c] = "" if pd.isna(v) else v
            entity_meta[eid_str] = vals

    # Org filter values (pulled before audit_df is column-pruned)
    audit_leaders = sorted([str(x) for x in audit_df["Audit Leader"].dropna().unique() if str(x) != "nan"]) if "Audit Leader" in audit_df.columns else []
    pgas = sorted([str(x) for x in audit_df["PGA"].dropna().unique() if str(x) != "nan"]) if "PGA" in audit_df.columns else []
    core_teams = sorted([str(x) for x in audit_df["Core Audit Team"].dropna().unique() if str(x) != "nan"]) if "Core Audit Team" in audit_df.columns else []

    # Get unique values for filters
    entities = sorted(audit_df["Entity ID"].unique().tolist()) if "Entity ID" in audit_df.columns else []
    l2_risks = sorted(audit_df["New L2"].unique().tolist()) if "New L2" in audit_df.columns else []

    total_rows = len(audit_df)
    total_entities = audit_df["Entity ID"].nunique() if "Entity ID" in audit_df.columns else 0

    # Row-filter inventories to only IDs referenced by the legacy rows we have
    app_ids = _collect_inventory_ids(legacy_df, [inventory_cols["legacyPrimaryIT"], inventory_cols["legacySecondaryIT"]])
    tp_ids = _collect_inventory_ids(legacy_df, [inventory_cols["legacyPrimaryTP"], inventory_cols["legacySecondaryTP"]])
    policy_ids = _collect_inventory_ids(legacy_df, [inventory_cols["legacyPolicies"]])
    law_ids = _collect_inventory_ids(legacy_df, [inventory_cols["legacyLawsApplic"], inventory_cols["legacyLawsAdd"]])
    applications_df = _filter_inventory(applications_df, inventory_cols["appId"], app_ids)
    thirdparties_df = _filter_inventory(thirdparties_df, inventory_cols["tpId"], tp_ids)
    policies_df = _filter_inventory(policies_df, inventory_cols["pspId"], policy_ids)
    laws_df = _filter_inventory(laws_df, inventory_cols["manId"], law_ids)

    # Legacy column allowlist: static set + configured inventory columns
    legacy_cols = list(LEGACY_STATIC_COLS) + [
        inventory_cols["legacyPrimaryIT"], inventory_cols["legacySecondaryIT"],
        inventory_cols["legacyPrimaryTP"], inventory_cols["legacySecondaryTP"],
        inventory_cols["legacyPolicies"],
        inventory_cols["legacyLawsApplic"], inventory_cols["legacyLawsAdd"],
    ]

    # Embed data as JSON (pruned to columns the JS actually reads)
    audit_json = _safe_json(_project_cols(audit_df, AUDIT_COLS))
    detail_json = _safe_json(_project_cols(detail_df, DETAIL_COLS))
    findings_json = _safe_json(_project_cols(findings_df, FINDINGS_COLS))
    sub_risks_json = _safe_json(_project_cols(sub_risks_df, SUB_RISKS_COLS))
    ore_json = _safe_json(_project_cols(ore_df, ORE_COLS))
    prsa_json = _safe_json(_project_cols(prsa_df, PRSA_COLS))
    bma_json = _safe_json(_project_cols(bma_df, BMA_COLS))
    gra_raps_json = _safe_json(_project_cols(gra_raps_df, GRA_RAPS_COLS))
    legacy_ratings_json = _safe_json(_project_cols(legacy_ratings_df, LEGACY_RATINGS_COLS))
    legacy_json = _safe_json(_project_cols(legacy_df, legacy_cols))
    applications_inventory_json = _safe_json(applications_df)
    policies_inventory_json = _safe_json(policies_df)
    laws_inventory_json = _safe_json(laws_df)
    thirdparties_inventory_json = _safe_json(thirdparties_df)

    entity_meta_json = json.dumps(entity_meta, default=str)

    # Build HTML by substituting placeholders. We use .replace() rather than
    # f-strings so embedded CSS/JS (with their own { } braces) don't need to
    # be doubly escaped.
    js_body = (_JS
        .replace("__AUDIT_JSON__", audit_json)
        .replace("__DETAIL_JSON__", detail_json)
        .replace("__FINDINGS_JSON__", findings_json)
        .replace("__SUB_RISKS_JSON__", sub_risks_json)
        .replace("__ORE_JSON__", ore_json)
        .replace("__PRSA_JSON__", prsa_json)
        .replace("__BMA_JSON__", bma_json)
        .replace("__GRA_RAPS_JSON__", gra_raps_json)
        .replace("__LEGACY_RATINGS_JSON__", legacy_ratings_json)
        .replace("__LEGACY_JSON__", legacy_json)
        .replace("__APPS_INV_JSON__", applications_inventory_json)
        .replace("__POLICIES_INV_JSON__", policies_inventory_json)
        .replace("__LAWS_INV_JSON__", laws_inventory_json)
        .replace("__TP_INV_JSON__", thirdparties_inventory_json)
        .replace("__INVENTORY_COLS_JSON__", json.dumps(inventory_cols))
        .replace("__ENTITIES_JSON__", json.dumps(entities))
        .replace("__L2_RISKS_JSON__", json.dumps(l2_risks))
        .replace("__AUDIT_LEADERS_JSON__", json.dumps(audit_leaders))
        .replace("__PGAS_JSON__", json.dumps(pgas))
        .replace("__CORE_TEAMS_JSON__", json.dumps(core_teams))
        .replace("__ENTITY_META_JSON__", entity_meta_json)
    )

    html_body = (_HTML_BODY
        .replace("__RUN_TIMESTAMP__", str(run_timestamp))
        .replace("__TOTAL_ENTITIES__", str(total_entities))
        .replace("__TOTAL_ROWS__", str(total_rows))
    )

    html = (
        '<!DOCTYPE html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        '<title>Risk Taxonomy Review</title>\n'
        '<link href="https://fonts.googleapis.com/css2?family=Source+Sans+Pro:wght@300;400;600;700&family=Source+Code+Pro:wght@400;600&display=swap" rel="stylesheet">\n'
        '<style>\n' + _CSS + '\n</style>\n'
        '</head>\n'
        '<body>\n'
        + html_body +
        '\n<script>\n' + js_body + '\n</script>\n'
        '</body>\n'
        '</html>\n'
    )

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  HTML report saved: {html_path}")


# =============================================================================
# CLI
# =============================================================================
if __name__ == "__main__":
    output_dir = _PROJECT_ROOT / "data" / "output"

    if len(sys.argv) > 1:
        excel_path = sys.argv[1]
    else:
        files = sorted(output_dir.glob("transformed_risk_taxonomy_*.xlsx"),
                       key=lambda f: f.stat().st_mtime)
        if not files:
            print("No transformer output found in data/output/")
            sys.exit(1)
        excel_path = str(files[-1])

    stem = Path(excel_path).stem
    ts = stem.replace("transformed_risk_taxonomy_", "")
    html_path = str(output_dir / f"risk_taxonomy_report_{ts}.html")

    generate_html_report(excel_path, html_path)
