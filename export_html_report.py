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
    return df.fillna("").to_json(orient="records", date_format="iso")


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
    "Audit Entity Status",
]

AUDIT_COLS = [
    "Entity ID", "New L1", "New L2", "L2 Definition",
    "Status", "Confidence", "Inherent Risk Rating",
    "Likelihood", "Overall Impact",
    "Legacy Source", "Decision Basis", "Decision Type", "Method", "Additional Signals",
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
    "key_risk_rating", "Inherent Risk Rating",
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
   Base: bare <table>. Data tables (built via buildTableHTML) get
   .data-table, which opts them into sortable headers, cell-expand,
   and column-resize. Tables that are pure label/value or compact
   reference use per-context classes below without .data-table.
   Overrides: .rating-table, .md-table, .drill-findings-table, .legacy-table
   ================================================================ */
/* Table layout — fixed for every table. Column widths are driven by
   <colgroup><col> entries, which buildTableHTML now always emits. This
   is essential for column resize: the resize handler updates
   col.style.width, and fixed layout honors those widths on re-layout.
   Earlier attempts with table-layout:auto were unreliable -- auto mode
   treats th.style.width as a hint that content min-widths can override,
   and any td max-width would cap the column against resize-to-grow. */
table { width: auto; min-width: 100%; border-collapse: collapse; font-size: 13px; margin: 8px 0; table-layout: fixed; }
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
    position: absolute; right: 0; top: 0; bottom: 0; width: 10px;
    cursor: col-resize; z-index: 2;
    border-right: 2px solid rgba(0,0,0,0.18);
}
th:hover .col-resize { border-right-color: rgba(0,0,0,0.30); }
th .col-resize:hover, th .col-resize.active { background: var(--accent); border-right-color: var(--accent); opacity: 0.6; }
/* During column drag: lock cursor to col-resize everywhere and suppress text selection */
body.col-resizing { cursor: col-resize !important; -webkit-user-select: none; user-select: none; }
body.col-resizing * { cursor: col-resize !important; }
td {
    padding: 8px 12px; border-bottom: 1px solid var(--border); vertical-align: top;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    max-width: 0; cursor: default;
}
td.cell-expanded {
    white-space: normal; word-wrap: break-word; overflow: visible;
    background: #fffde7; outline: 2px solid #ffcc02; z-index: 1; position: relative;
}
/* Column-wide expand — visually identical to cell-expanded minus the
   yellow highlight. In table-layout:fixed the column width stays put;
   content wraps (rows grow taller) + overflows visibly across row bounds
   via position:relative/overflow:visible. Same spec the single-cell
   expand uses, so there's no behavioral mismatch between the two. */
td.col-expanded-all {
    white-space: normal; word-wrap: break-word; overflow: visible;
    position: relative;
}
/* Header expand button, next to sort arrow and resize handle. */
.th-expand-btn {
    display: inline-block; margin-left: 6px; padding: 0 4px;
    opacity: 0.7; cursor: pointer; font-size: 13px;
    user-select: none; color: var(--gray);
}
.th-expand-btn:hover { opacity: 1; color: #1a4b8c; background: #e8f0fe; border-radius: 3px; }
.th-expand-btn.active { opacity: 1; color: #b36b00; background: #fff4e0; border-radius: 3px; }

/* Column hide: CSS-only removal of a column (header, cells, colgroup) */
th.col-hidden, td.col-hidden, col.col-hidden { display: none; }

/* Per-table toolbar (Columns menu, Clear filters, etc.) */
.table-outer { margin: 8px 0; position: relative; }
.table-outer .table-wrap { margin: 0; }
.table-toolbar {
    display: flex; gap: 6px; align-items: center;
    padding: 4px 0; font-size: 12px;
}
.table-toolbar-btn {
    padding: 4px 12px; border-radius: 4px; border: 1px solid var(--border);
    background: var(--bg); color: var(--fg); cursor: pointer;
    font-size: 12px; font-family: var(--font); font-weight: 500;
}
.table-toolbar-btn:hover { background: var(--bg2); border-color: #1a4b8c; color: #1a4b8c; }
.table-toolbar-btn.active { color: #1a4b8c; border-color: #1a4b8c; background: #e8f0fe; }

.table-cols-menu {
    position: absolute; top: 28px; left: 0; z-index: 200;
    background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.12);
    min-width: 200px; max-height: 320px; overflow-y: auto;
    padding: 6px 0; display: none;
}
.table-cols-menu.open { display: block; }
.table-cols-menu .cols-menu-header {
    padding: 4px 12px 6px; font-size: 11px; color: var(--gray);
    text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid var(--border);
}
.table-cols-menu label {
    display: flex; align-items: center; gap: 6px;
    padding: 4px 12px; cursor: pointer; font-size: 12px; color: var(--fg);
    font-weight: 400;
}
.table-cols-menu label:hover { background: var(--bg2); }
.table-cols-menu input[type="checkbox"] { margin: 0; cursor: pointer; }
.table-cols-menu .cols-menu-footer {
    padding: 6px 12px; border-top: 1px solid var(--border);
    display: flex; justify-content: flex-end;
}
.table-cols-menu .cols-menu-footer button {
    padding: 3px 10px; border-radius: 4px; border: 1px solid var(--border);
    background: var(--bg); color: var(--gray); cursor: pointer; font-size: 11px;
}
.table-cols-menu .cols-menu-footer button:hover { background: var(--bg2); color: var(--fg); }

/* Column header filter button + dropdown (Excel-style autofilter).
   Hosts an SVG funnel icon (see _FILTER_ICON_SVG) rather than a text
   character, so inline-flex centers the glyph vertically without
   relying on font metrics. */
.th-filter-btn {
    display: inline-flex; align-items: center; justify-content: center;
    margin-left: 4px; padding: 1px 4px; min-width: 18px;
    opacity: 0.7; cursor: pointer;
    user-select: none; color: var(--gray);
    border: 1px solid transparent; border-radius: 3px;
    vertical-align: middle;
}
.th-filter-btn:hover { opacity: 1; color: #1a4b8c; background: #e8f0fe; border-color: #a6c5f0; }
.th-filter-btn.active { opacity: 1; color: #1a4b8c; background: #d0e7fa; border-color: #1a4b8c; }

.filter-dropdown {
    position: fixed; z-index: 300;
    background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.14);
    min-width: 220px; max-width: 340px;
    padding: 8px; display: none;
    text-transform: none; letter-spacing: 0; font-weight: 400;
}
.filter-dropdown.open { display: block; }
.filter-dropdown input.filter-search {
    width: 100%; padding: 4px 8px; border: 1px solid var(--border);
    border-radius: 4px; margin-bottom: 6px; box-sizing: border-box;
    font-family: var(--font); font-size: 12px;
}
.filter-dropdown .filter-values {
    max-height: 240px; overflow-y: auto;
    border: 1px solid var(--border); border-radius: 4px; padding: 4px;
}
.filter-dropdown label {
    display: flex; align-items: center; gap: 6px;
    padding: 2px 4px; cursor: pointer; font-size: 12px; color: var(--fg);
    font-weight: 400; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.filter-dropdown label:hover { background: var(--bg2); }
.filter-dropdown label.filter-select-all {
    font-weight: 600; border-bottom: 1px solid var(--border); margin-bottom: 4px; padding-bottom: 4px;
}
.filter-dropdown .filter-actions {
    margin-top: 8px; display: flex; justify-content: flex-end; gap: 4px;
}
.filter-dropdown .filter-actions button {
    padding: 3px 10px; border-radius: 4px; border: 1px solid var(--border);
    background: var(--bg); color: var(--fg); cursor: pointer; font-size: 11px;
}
.filter-dropdown .filter-actions button.primary {
    background: var(--accent); color: white; border-color: var(--accent);
}
.filter-dropdown .filter-actions button:hover { opacity: 0.9; }

tr.row-hidden { display: none; }

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
.inactive-toggle-label {
    display: flex; align-items: center; gap: 6px;
    font-size: 12px; color: var(--gray); margin: 6px 0 10px;
    cursor: pointer; user-select: none;
}
.inactive-toggle-label input { margin: 0; }
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
/* -- Typeahead combobox (used for Entity + Risk selectors) -- */
.typeahead { position: relative; margin-bottom: 14px; }
.typeahead-input {
    width: 100%; box-sizing: border-box;
    padding: 7px 10px; font-size: 13px; font-family: var(--font);
    border: 1px solid var(--border); border-radius: 6px;
    background: var(--bg); color: var(--fg); outline: none;
    transition: border-color 0.2s;
}
.typeahead-input:focus { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
.typeahead-list {
    display: none; position: absolute; left: 0; right: 0; top: 100%;
    margin-top: 2px; max-height: 260px; overflow-y: auto;
    background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.08); z-index: 100;
}
.typeahead-item {
    padding: 6px 10px; font-size: 13px; color: var(--fg);
    cursor: pointer; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.typeahead-item:hover, .typeahead-item.active { background: #e4e7ed; }
.typeahead-empty { padding: 6px 10px; font-size: 12px; color: var(--gray); font-style: italic; }

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
/* Two-tier header system:
   .drill-supersection ("Why this risk applies" / "How it's controlled") —
     small-caps gray, 11px, bottom border.
   .drill-section .label (sub-sections: IAG Issues, OREs, Sub-risks, etc.) —
     same small-caps gray treatment, 10px, no border, indented inside the
     super-section via .drill-section-inner. */
.drill-section { margin: 8px 0; }
.drill-section .label { color: var(--gray); font-weight: 700; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; display: block; }
.drill-section-inner { padding-left: 14px; }
.drill-inline-meta { color: var(--gray); font-size: 13px; margin: 4px 0; }

/* Drill-down key risk list */
.subrisk-row { display: flex; gap: 10px; padding: 2px 0; align-items: baseline; }
.subrisk-id { font-family: var(--font-mono); font-size: 12px; color: var(--gray-light); min-width: 50px; }
.subrisk-name { color: var(--fg); font-size: 13px; }

/* Unified monospace ID chip — used for key risk IDs, signal IDs, and all
   ID cells in drill-down / source-data evidence tables. */
.id-chip {
    font-family: var(--font-mono); font-size: 11px;
    padding: 1px 6px; border-radius: 3px;
    background: var(--bg2); color: var(--gray);
    white-space: nowrap;
}
/* Key app/TP ID — left border stripe signals this ID is in the entity's
   "key" inventory set. Non-key IDs render as plain id-chip. */
.id-chip-key {
    border-left: 3px solid #1e7a3a;
    padding-left: 4px;
    color: #1e4620;
    font-weight: 600;
}
/* Orphan ID — flagged as key in a key risk but not present in the entity's
   PRIMARY/SECONDARY inventory columns. Subtle amber left border. */
.id-chip-orphan {
    border-left: 3px solid #c97b00;
    padding-left: 4px;
    color: #7a4700;
}
/* "(none key)" suffix on the Additional Signals summary chip — signals that
   the apps/TPs tagged to this entity for this L2 are all non-key, so per
   procedure they do not drive risk. */
.chip-nonkey-suffix {
    font-weight: 400;
    opacity: 0.7;
    margin-left: 2px;
    font-size: 9px;
    text-transform: none;
    letter-spacing: 0;
}
.subrisk-row .id-chip { flex-shrink: 0; min-width: 55px; }
/* Alias: existing signal ID chips pick up the unified look. */
.signal-id-chip {
    font-family: var(--font-mono); font-size: 11px;
    padding: 1px 6px; border-radius: 3px;
    background: var(--bg2); color: var(--gray);
    white-space: nowrap;
}

/* Drill-down Additional Signals */
.signal-contradiction { color: #842029; font-weight: 600; }
.signal-group { margin: 8px 0; }
.signal-group:first-child { margin-top: 4px; }
.signal-group-header {
    display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
    margin-bottom: 4px;
}
.signal-tag {
    display: inline-block; font-size: 10px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.5px;
    padding: 2px 8px; border-radius: 10px;
    background: var(--bg2); color: var(--gray);
}
.signal-tag-app           { background: #e8f0fe; color: #1a4b8c; }
.signal-tag-tp            { background: #e6f4ea; color: #1e4620; }
.signal-tag-model         { background: #f3e8fd; color: #4a148c; }
.signal-tag-cross-boundary{ background: #fff4e0; color: #8a5200; }
.signal-tag-aux           { background: #ede5f8; color: #533a8a; }
.signal-tag-core          { background: #ede5f8; color: #533a8a; }
.signal-group-hint { font-size: 12px; color: var(--gray); font-style: italic; }
.signal-list { list-style: none; padding: 0; margin: 0; }
.signal-item {
    padding: 3px 0; font-size: 13px; line-height: 1.7;
}
.signal-item + .signal-item {
    border-top: 1px dashed var(--border);
    padding-top: 6px; margin-top: 3px;
}
.signal-body { color: var(--fg); margin-right: 6px; }
.signal-hint-inline { color: var(--gray); font-size: 12px; }
.signal-ids {
    display: inline; white-space: normal;
}
.signal-ids .id-chip,
.signal-ids .signal-id-chip { margin-right: 3px; }

/* Risk Profile "Additional Signals" cell: chip summary collapsed,
   full drill-down-style detail on click. Distinct from the generic
   .cell-expanded click-to-expand (different class, different contract). */
td.cell-signals {
    white-space: normal; word-wrap: break-word;
    max-width: none; vertical-align: top;
    padding: 6px 10px;
    cursor: pointer;
}
.signals-summary {
    display: flex; flex-wrap: wrap; gap: 4px;
    align-items: center;
}
.signals-detail { display: none; }
td.cell-signals.expanded .signals-summary,
td.cell-signals.col-expanded-all .signals-summary { display: none; }
td.cell-signals.expanded .signals-detail,
td.cell-signals.col-expanded-all .signals-detail { display: block; }
td.cell-signals.expanded {
    background: #fffde7; outline: 2px solid #ffcc02;
    z-index: 1; position: relative;
}
.signal-summary-chip {
    display: inline-flex; align-items: center; gap: 3px;
    font-size: 10px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.4px;
    padding: 2px 7px; border-radius: 10px;
    background: var(--bg2); color: var(--gray);
    white-space: nowrap;
}
.signal-summary-chip-app            { background: #e8f0fe; color: #1a4b8c; }
.signal-summary-chip-tp             { background: #e6f4ea; color: #1e4620; }
.signal-summary-chip-model          { background: #f3e8fd; color: #4a148c; }
.signal-summary-chip-cross-boundary { background: #fff4e0; color: #8a5200; }
.signal-summary-chip-aux            { background: #ede5f8; color: #533a8a; }
.signal-summary-chip-core           { background: #ede5f8; color: #533a8a; }
/* Impact-of-Issues count chips: color by worst severity present in the group */
.signal-summary-chip-impact-critical { background: #fde2e2; color: #7a1515; }
.signal-summary-chip-impact-high     { background: #fde9d7; color: #8a3b00; }
.signal-summary-chip-impact-medium   { background: #fef3c7; color: #7a5c00; }
.signal-summary-chip-impact-low      { background: #e6f4ea; color: #1e4620; }
.signal-summary-chip-impact-none     { background: var(--bg2); color: var(--gray); }
.signal-summary-chip .count {
    font-weight: 400; opacity: 0.7;
    margin-left: 1px;
}

/* Decision-type chips (Risk Profile "Decision Basis" cell).
   Semantic palette: neutral gray = no interpretation applied;
   warn-yellow = reviewer action required (matches .banner-warn hue);
   blue/orange/purple = meaningful differentiation between mapping paths.
   Collides intentionally with .signal-summary-chip-* hues in other columns. */
.decision-chip {
    display: inline-flex; align-items: center;
    font-size: 10px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.4px;
    padding: 2px 7px; border-radius: 10px;
    white-space: nowrap; margin-right: 4px;
}
.decision-chip-direct       { background: #f1f3f4; color: #5f6368; }
.decision-chip-legacy-na    { background: #f1f3f4; color: #5f6368; }
.decision-chip-gap          { background: #e8eaed; color: #3c4043; }
.decision-chip-keyword      { background: #e8f0fe; color: #1a4b8c; }
.decision-chip-issue        { background: #fff4e0; color: #8a5200; }
.decision-chip-ai-applied   { background: #f3e8fd; color: #4a148c; }
.decision-chip-ai-na        { background: #ede5f8; color: #533a8a; }
.decision-chip-undetermined { background: var(--warning-bg); color: var(--warning-fg); }
.decision-chip-assumed-na   { background: var(--warning-bg); color: var(--warning-fg); }

/* Decision Basis, Impact, and L2-name cells — same expand/collapse pattern as cell-signals */
td.cell-decision-basis, td.cell-impact, td.cell-l2-name {
    white-space: normal; word-wrap: break-word;
    max-width: none; vertical-align: top;
    padding: 6px 10px;
    cursor: pointer;
}
.decision-summary, .impact-summary, .l2-name-summary {
    display: flex; flex-wrap: wrap; gap: 4px;
    align-items: center;
}
.decision-detail, .impact-detail, .l2-name-detail { display: none; }
td.cell-decision-basis.expanded .decision-summary,
td.cell-impact.expanded .impact-summary,
td.cell-l2-name.expanded .l2-name-summary,
td.cell-decision-basis.col-expanded-all .decision-summary,
td.cell-impact.col-expanded-all .impact-summary,
td.cell-l2-name.col-expanded-all .l2-name-summary { display: none; }
td.cell-decision-basis.expanded .decision-detail,
td.cell-impact.expanded .impact-detail,
td.cell-l2-name.expanded .l2-name-detail,
td.cell-decision-basis.col-expanded-all .decision-detail,
td.cell-impact.col-expanded-all .impact-detail,
td.cell-l2-name.col-expanded-all .l2-name-detail { display: block; }
td.cell-decision-basis.expanded,
td.cell-impact.expanded,
td.cell-l2-name.expanded {
    background: #fffde7; outline: 2px solid #ffcc02;
    z-index: 1; position: relative;
}
.decision-detail, .impact-detail, .l2-name-detail {
    font-size: 13px; color: var(--fg); line-height: 1.5;
}
/* Decision Basis prose contains \n line breaks and bulleted blocks
   (Matched references / Finding detail). Preserve them on render.
   Scoped to .decision-detail only — do not bleed into .impact-detail
   or .signals-detail. */
.decision-detail { white-space: pre-wrap; }
/* L2 name summary: plain text (no pill styling) — matches current visual
   for the New L2 column, just adds click-to-expand affordance. */
.l2-name-summary { font-weight: 400; color: var(--fg); }
.l2-name-detail { white-space: pre-wrap; }
.signals-expand-hint {
    color: var(--gray-light); font-size: 10px;
    margin-left: auto; padding-left: 4px;
    font-weight: 400; text-transform: none; letter-spacing: 0;
}
.signals-collapse-hint {
    display: block;
    font-size: 10px; color: var(--gray-light);
    margin-top: 6px; padding-top: 4px; border-top: 1px solid var(--border);
    text-align: right;
}

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
    font-size: 11px; color: var(--gray);
    text-transform: uppercase; letter-spacing: 0.5px; font-weight: 700;
    border-bottom: 1px solid var(--border);
    padding-bottom: 3px;
    margin: 18px 0 8px;
}

/* Control Assessment soft-orange note for "review whether rating still
   reflects current state" — replaces the older .drill-iag-warning inline
   warning emitted next to IAG Issues. */
.ca-note {
    color: #b45309; font-size: 12px; margin-top: 6px;
    background: #fff8ec; border-left: 3px solid #f0b87a;
    padding: 6px 10px; border-radius: 0 3px 3px 0;
}
.ca-note::before { content: "\u26A0 "; }

/* Drill-down / source-data table column widths. Applied via <colgroup>
   emitted by buildTableHTML when a `colgroup` array is passed. */
table.data-table col.c-id       { width: 90px; }
table.data-table col.c-sev      { width: 90px; }
table.data-table col.c-status   { width: 110px; }
table.data-table col.c-title    { width: auto; }

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
.overview { color: var(--fg); font-size: 13px; }
.overview p { margin: 4px 0; }
.overview ul.overview-list { margin: 4px 0 4px 18px; padding: 0; }
.overview ul.overview-list li { margin: 2px 0; }
.overview-toggle { font-size: 12px; color: var(--blue); cursor: pointer; text-decoration: underline; margin-left: 4px; }
.overview-table {
    border-collapse: collapse; margin: 6px 0;
    font-size: 13px; width: auto;
}
.overview-table th, .overview-table td {
    padding: 4px 8px; border: 1px solid var(--border);
    vertical-align: top; color: var(--fg);
}
.overview-table th { background: var(--bg2); font-weight: 600; }
.overview-dl { margin: 6px 0; }
.overview-dl dt { font-weight: 600; color: var(--fg); margin-top: 6px; }
.overview-dl dd { margin: 2px 0 0 12px; color: var(--fg); }

.handoff-grid-wrapper {
    container-type: inline-size;
    container-name: handoff-container;
}
.handoff-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 12px;
}
@container handoff-container (min-width: 640px) {
    .handoff-grid { grid-template-columns: minmax(0, 720px) minmax(0, 720px); }
}
.handoff-group { min-width: 0; }
.handoff-group:last-child { margin-bottom: 0; }
.handoff-group .table-wrap { width: 100%; }
.handoff-group table { width: 100%; table-layout: fixed; }
.handoff-col-label {
    font-size: 11px; color: var(--gray); text-transform: uppercase;
    letter-spacing: 0.4px; font-weight: 600; margin-bottom: 4px;
}
.handoff-table td:first-child,
.handoff-table td:nth-child(1) {
    font-family: var(--font-mono, "Source Code Pro", "Consolas", monospace);
    font-size: 12px; color: var(--gray);
}
.handoff-group .expander-body { max-height: 280px; overflow-y: auto; }
.handoff-desc { margin-top: 10px; color: var(--fg); font-size: 13px; }
.ae-flag {
    color: #c0392b;
    font-weight: 700;
    cursor: help;
}

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
        <div class="typeahead" id="entity-typeahead">
            <input type="text" id="entity-select" class="typeahead-input" autocomplete="off" placeholder="Type to search...">
            <div class="typeahead-list" id="entity-typeahead-list"></div>
        </div>
        <label class="inactive-toggle-label">
            <input type="checkbox" id="show-inactive-toggle" onchange="toggleShowInactive(this)">
            Show inactive entities
        </label>
        <div class="divider"></div>
    </div>

    <div id="sidebar-risk-select" style="display:none;">
        <label>Select L2 Risk</label>
        <div class="typeahead" id="risk-typeahead">
            <input type="text" id="risk-select" class="typeahead-input" autocomplete="off" placeholder="Type to search...">
            <div class="typeahead-list" id="risk-typeahead-list"></div>
        </div>
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
        <button type="button" class="sub-tab" onclick="switchEntityTab('legacy')">Legacy Profile</button>
        <button type="button" class="sub-tab" onclick="switchEntityTab('source')">Source Data</button>
        <button type="button" id="sub-tab-trace" class="sub-tab" onclick="switchEntityTab('trace')" style="display:none;">Traceability</button>
    </div>

    <div id="entity-tab-profile" class="sub-tab-content active">
        <div id="entity-profile-host"></div>
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
    <div id="risk-entity-host"></div>
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
// Per-entity sets of "key" application / third-party IDs aggregated from
// key risk rows. Per procedure, non-key items do not drive risk; the UI
// marks key IDs in drill-down and Source Data inventory tables. The summary
// Additional Signals chip adds "(none key)" when ALL IDs tagged to the entity
// for that L2 are non-key.
//   shape: {eid: {keyApps: [...], keyTps: [...], orphanApps: [...], orphanTps: [...]}}
const keyInventory = __KEY_INVENTORY_JSON__;

function getKeyInv(eid) {
    return keyInventory[eid] || {
        keyApps: [], keyTps: [], orphanApps: [], orphanTps: [],
        keyAppsKpa: {}, keyTpsKpa: {},
    };
}
function isKeyApp(eid, id) {
    return getKeyInv(eid).keyApps.indexOf(String(id)) >= 0;
}
function isKeyTp(eid, id) {
    return getKeyInv(eid).keyTps.indexOf(String(id)) >= 0;
}
// Return the list of KPA IDs where this app/TP is "key" for the entity.
// Empty array if not key or no KPA attribution available.
function keyAppKpas(eid, id) {
    let m = getKeyInv(eid).keyAppsKpa || {};
    return m[String(id)] || [];
}
function keyTpKpas(eid, id) {
    let m = getKeyInv(eid).keyTpsKpa || {};
    return m[String(id)] || [];
}

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

let _showInactiveEntities = false;
function getEntityStatus(eid) { return getEntityMeta(eid)["Audit Entity Status"] || ""; }
function isActiveEntity(eid) { return String(getEntityStatus(eid)).trim().toLowerCase() === "active"; }

// ==================== TYPEAHEAD COMBOBOX ====================
// Shared factory used for Entity + Risk selectors. Option shape: {value, label}.
// getOptions() returns the live option list; onSelect(value) fires when
// the user picks an item. The input element's `value` holds the current label;
// its `dataset.value` holds the selected option's underlying value.
const _typeaheads = {};

function makeTypeahead(inputId, listId, getOptions, onSelect) {
    const input = document.getElementById(inputId);
    const list = document.getElementById(listId);
    if (!input || !list) return null;
    const state = { options: [], filtered: [], active: -1, getOptions, onSelect, input, list };
    _typeaheads[inputId] = state;

    function render() {
        list.innerHTML = "";
        if (!state.filtered.length) {
            const empty = document.createElement("div");
            empty.className = "typeahead-empty";
            empty.textContent = "No matches";
            list.appendChild(empty);
            return;
        }
        state.filtered.forEach((opt, idx) => {
            const div = document.createElement("div");
            div.className = "typeahead-item" + (idx === state.active ? " active" : "");
            div.textContent = opt.label;
            div.addEventListener("mousedown", (e) => {
                e.preventDefault();
                pick(opt);
            });
            list.appendChild(div);
        });
    }

    function filter(q) {
        const needle = String(q || "").trim().toLowerCase();
        if (!needle) {
            state.filtered = state.options.slice();
        } else {
            state.filtered = state.options.filter(o =>
                String(o.label || "").toLowerCase().includes(needle) ||
                String(o.value || "").toLowerCase().includes(needle)
            );
        }
        state.active = state.filtered.length ? 0 : -1;
        render();
    }

    function open() {
        list.style.display = "block";
        filter(input.value);
    }
    function close() {
        list.style.display = "none";
        state.active = -1;
    }
    function pick(opt) {
        input.value = opt.label;
        input.dataset.value = opt.value;
        close();
        if (state.onSelect) state.onSelect(opt.value);
    }

    input.addEventListener("focus", open);
    input.addEventListener("input", () => { open(); });
    input.addEventListener("keydown", (e) => {
        if (e.key === "ArrowDown") {
            e.preventDefault();
            if (list.style.display !== "block") { open(); return; }
            if (!state.filtered.length) return;
            state.active = (state.active + 1) % state.filtered.length;
            render();
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            if (!state.filtered.length) return;
            state.active = (state.active - 1 + state.filtered.length) % state.filtered.length;
            render();
        } else if (e.key === "Enter") {
            if (state.active >= 0 && state.filtered[state.active]) {
                e.preventDefault();
                pick(state.filtered[state.active]);
            }
        } else if (e.key === "Escape") {
            close();
            input.blur();
        }
    });
    document.addEventListener("mousedown", (e) => {
        if (!list.contains(e.target) && e.target !== input) close();
    });

    // Expose a rebuild hook: call when underlying options change.
    state.rebuild = function(selectValue) {
        state.options = (state.getOptions() || []).map(o => ({
            value: String(o.value),
            label: String(o.label == null ? o.value : o.label),
        }));
        // Preserve current selection if still present; otherwise pick first.
        let current = selectValue != null ? String(selectValue) : (input.dataset.value || "");
        let match = state.options.find(o => o.value === current);
        if (!match && state.options.length) match = state.options[0];
        if (match) {
            input.value = match.label;
            input.dataset.value = match.value;
        } else {
            input.value = "";
            input.dataset.value = "";
        }
        state.filtered = state.options.slice();
        state.active = state.filtered.length ? 0 : -1;
        if (list.style.display === "block") render();
    };

    return state;
}

function getTypeaheadValue(inputId) {
    const input = document.getElementById(inputId);
    return input ? (input.dataset.value || "") : "";
}

function _buildEntityOptions() {
    const opts = [];
    entities.forEach(eid => {
        let active = isActiveEntity(eid);
        if (!active && !_showInactiveEntities) return;
        let name = entityNameMap[eid] || "";
        let label = name ? (eid + " - " + name) : eid;
        if (!active) label += " (Inactive)";
        opts.push({ value: eid, label });
    });
    return opts;
}

function rebuildEntitySelect() {
    const ta = _typeaheads["entity-select"];
    if (ta) ta.rebuild();
}

function toggleShowInactive(el) {
    _showInactiveEntities = el.checked;
    const ta = _typeaheads["entity-select"];
    if (ta) {
        const prev = getTypeaheadValue("entity-select");
        ta.rebuild(prev);
    }
    renderEntityView();
}

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
        // New terminology (2026-04-21). Three-level baseline.
        "satisfactory":              {bg: "#EAF3DE", fg: "#27500A"},
        "partially effective":       {bg: "#FAEEDA", fg: "#633806"},
        "ineffective":               {bg: "#FCEBEB", fg: "#791F1F"},
        // Legacy terminology (still appears in legacy per-pillar control
        // effectiveness column and older outputs).
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
    if (s === "n/a" || s === "na" || s === "none" || s === "not available" || s === "not applicable") return true;
    if (s === "no open items") return true;
    if (/^no .+ available$/.test(s)) return true;
    if (/^(n\/a|na)\s*[-–—:]\s*not applicable$/.test(s)) return true;
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

// ==================== TABLE BUILDING / SORTING / PERSIST STATE ====================
//
// Every data table in the report is built through a single entry point:
//
//   buildTableHTML(opts) -> HTML string
//     Produces a .data-table with sortable arrow headers, draggable
//     column-resize handles, optional click-to-expand cells, and
//     (when wrap=true && !minimal) a toolbar with a Columns menu,
//     Clear-filters affordance, and per-column filter dropdowns.
//
// Per-header opt-ins / opt-outs:
//   tool: true      -- blue-tinted header background (decision tools)
//   noSort: true    -- suppress sort arrows + click-to-sort on column
//   noFilter: true  -- suppress filter dropdown on column
//   expand: true    -- show column-wide expand icon on column (opt-IN;
//                       default is no expand icon)
//
// Per-table opts:
//   wrap: false     -- emit only the <table>, no surrounding wrappers
//                       or toolbar. Used for tables rendered inside
//                       cell drill-downs (Impact of Issues nested
//                       tables). Suppresses the filter icon in every
//                       header as a side effect, since no dropdown
//                       host exists for clicks to find.
//   minimal: true   -- skip the toolbar (Columns menu, clear filters,
//                       filter dropdowns) for small reference tables
//                       where those affordances would be pure noise.
//                       Suppresses filter icons for the same reason
//                       as wrap=false.
//
// Sort state is persisted per table ID in _tableSortState and re-applied
// on re-render, alongside column-expand, hidden-column, and filter state
// in their respective maps (all keyed on tableId so they survive entity
// switches).

const _tableSortState = {}; // { tableId: {col: number, dir: "asc"|"desc"} }

// Filter-icon glyph. A three-decreasing-lines SVG ("funnel" in abstract
// form) rather than a U+25BE caret, because the caret was visually
// indistinguishable from the sort-descending arrow (same U+25BE
// character in both places), and the ambiguity was especially bad once
// a sort had been applied -- the collapsed sort arrow sat next to the
// filter caret and read as a single ▴▾ pair. The SVG uses
// currentColor so the .th-filter-btn color rules (default / hover /
// active) keep working as-is.
const _FILTER_ICON_SVG = '<svg width="10" height="10" viewBox="0 0 16 16"'
    + ' fill="none" stroke="currentColor" stroke-width="1.8"'
    + ' stroke-linecap="round" aria-hidden="true"'
    + ' style="vertical-align:middle;">'
    + '<path d="M2 4 L14 4"/>'
    + '<path d="M4 8 L12 8"/>'
    + '<path d="M6 12 L10 12"/>'
    + '</svg>';

// Column-wide expand state. Keyed by tableId, value is a Set of column
// indices currently expanded. State survives sort (sort only re-orders
// rows in place; classes on td stay with their tr) and re-render
// (buildTableHTML re-applies the class to matching cells at build time).
const _tableColExpanded = {};
function _isColExpanded(tableId, colIdx) {
    const s = _tableColExpanded[tableId];
    return !!(s && s.has(colIdx));
}
function toggleColExpanded(tableId, colIdx) {
    const table = document.getElementById(tableId);
    if (!table) return;
    let s = _tableColExpanded[tableId];
    if (!s) { s = new Set(); _tableColExpanded[tableId] = s; }
    const isOn = !s.has(colIdx);
    if (isOn) s.add(colIdx); else s.delete(colIdx);
    // :scope > so nested tables inside expanded Impact-of-Issues cells
    // aren't affected by the outer table's column expand.
    const cells = table.querySelectorAll(
        ':scope > tbody > tr > td:nth-child(' + (colIdx + 1) + ')'
    );
    cells.forEach(td => td.classList.toggle('col-expanded-all', isOn));
    const btn = table.querySelector(
        ':scope > thead > tr > th:nth-child(' + (colIdx + 1) + ') .th-expand-btn'
    );
    if (btn) btn.classList.toggle('active', isOn);
}

// Column hide/show state. Keyed by tableId, value is a Set of hidden
// column indices. Same survival semantics as col-expand state.
const _tableColHidden = {};

// Column width state. Keyed by tableId, value is an object mapping
// column index -> width string (e.g. "180px"). Populated by the
// resize handler on mouseup and by double-click auto-fit, read by
// buildTableHTML when emitting <col> style.width values. Survives
// re-render so drag-resize widths persist across entity switches.
const _tableColWidths = {};
function _isColHidden(tableId, colIdx) {
    const s = _tableColHidden[tableId];
    return !!(s && s.has(colIdx));
}
function toggleColHidden(tableId, colIdx, shouldHide) {
    const table = document.getElementById(tableId);
    if (!table) return;
    let s = _tableColHidden[tableId];
    if (!s) { s = new Set(); _tableColHidden[tableId] = s; }
    if (shouldHide) s.add(colIdx); else s.delete(colIdx);
    // Apply to outer-table th, td, and col — scoped to not leak into nested tables.
    const th = table.querySelector(
        ':scope > thead > tr > th:nth-child(' + (colIdx + 1) + ')'
    );
    if (th) th.classList.toggle('col-hidden', shouldHide);
    const cells = table.querySelectorAll(
        ':scope > tbody > tr > td:nth-child(' + (colIdx + 1) + ')'
    );
    cells.forEach(td => td.classList.toggle('col-hidden', shouldHide));
    const col = table.querySelector(
        ':scope > colgroup > col:nth-child(' + (colIdx + 1) + ')'
    );
    if (col) col.classList.toggle('col-hidden', shouldHide);
}
function resetCols(tableId) {
    const s = _tableColHidden[tableId];
    if (s && s.size) {
        const idxs = Array.from(s);
        idxs.forEach(i => toggleColHidden(tableId, i, false));
    }
    // Clear any user-resized widths so the table falls back to
    // header defaults on the next re-render.
    if (_tableColWidths[tableId]) {
        delete _tableColWidths[tableId];
    }
    // Also clear inline col widths and reset table to auto width
    const table = document.getElementById(tableId);
    if (table) {
        table.querySelectorAll(':scope > colgroup > col').forEach(col => {
            col.style.width = '';
        });
        table.style.width = '';
        delete table.dataset.fixedLayout;
    }
    // Uncheck menu checkboxes to match
    const menu = document.getElementById('cols-menu-' + tableId);
    if (menu) {
        menu.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = true);
    }
}
function toggleColsMenu(tableId) {
    const menu = document.getElementById('cols-menu-' + tableId);
    if (!menu) return;
    const isOpen = menu.classList.contains('open');
    // Close any other open cols menu
    document.querySelectorAll('.table-cols-menu.open').forEach(m => m.classList.remove('open'));
    if (!isOpen) menu.classList.add('open');
}
// Click-outside-closes for cols menu
document.addEventListener('mousedown', function(e) {
    if (e.target.closest('.table-cols-menu') || e.target.closest('.table-cols-btn')) return;
    document.querySelectorAll('.table-cols-menu.open').forEach(m => m.classList.remove('open'));
});

// Column filter state. Keyed by tableId, value is {colIdx: Set<string>}
// where the Set holds ALLOWED values. Absence of a colIdx key = no filter
// on that column (all rows pass).
const _tableColFilters = {};

function _cellDisplayText(td) {
    return (td && td.textContent ? td.textContent : '').trim();
}

// Extract individual chip labels from a cell. Used by both:
//   1. buildTableHTML (at build time, on raw cell data with HTML strings)
//   2. _applyAllRowFilters (at runtime, on rendered <td> elements)
// `source` can be a DOM element (<td>) or a raw cell value (string or
// {html: "..."} object). `chipSelector` is a CSS selector like
// ".decision-chip" or ".signal-summary-chip".
function _extractChipLabels(source, chipSelector) {
    let container;
    if (source && source.nodeType === 1) {
        // DOM element — query directly
        container = source;
    } else {
        // Raw cell data — parse HTML
        let html = '';
        if (source && typeof source === 'object' && source.html !== undefined) html = source.html;
        else if (typeof source === 'string') html = source;
        if (!html) return [];
        container = document.createElement('div');
        container.innerHTML = html;
    }
    const chips = container.querySelectorAll(chipSelector);
    if (!chips.length) return [];
    return Array.from(chips).map(c => {
        // First text node = label (excludes <span class="count">, suffixes)
        for (let n = c.firstChild; n; n = n.nextSibling) {
            if (n.nodeType === 3) {
                let t = n.textContent.trim();
                if (t) return t;
            }
        }
        return c.textContent.trim();
    }).filter(Boolean);
}

function _applyAllRowFilters(tableId) {
    const table = document.getElementById(tableId);
    if (!table) return;
    const f = _tableColFilters[tableId];
    // Resolve which columns use tag-based filtering by checking the
    // data-filter-chips attribute on each <th>.
    const ths = table.querySelectorAll(':scope > thead > tr > th');
    const chipSelectors = {};
    ths.forEach((th, i) => {
        const sel = th.dataset.filterChips;
        if (sel) chipSelectors[i] = sel;
    });
    const rows = table.querySelectorAll(':scope > tbody > tr');
    rows.forEach(tr => {
        if (!f || Object.keys(f).length === 0) {
            tr.classList.remove('row-hidden');
            return;
        }
        let passes = true;
        for (const k in f) {
            const allowed = f[k];
            if (!allowed || allowed.size === 0) continue;
            const colIdx = parseInt(k, 10);
            const td = tr.children[colIdx];
            if (!td) continue;
            if (chipSelectors[colIdx]) {
                // Tag-based: pass if ANY chip label is in the allowed set
                const tags = _extractChipLabels(td, chipSelectors[colIdx]);
                if (!tags.length || !tags.some(t => allowed.has(t))) {
                    passes = false; break;
                }
            } else {
                if (!allowed.has(_cellDisplayText(td))) { passes = false; break; }
            }
        }
        tr.classList.toggle('row-hidden', !passes);
    });
}

function toggleFilterDropdown(tableId, colIdx, ev) {
    if (ev) ev.stopPropagation();
    const el = document.getElementById('filter-dropdown-' + tableId + '-' + colIdx);
    if (!el) return;
    // Close any other open dropdowns first.
    document.querySelectorAll('.filter-dropdown.open').forEach(d => {
        if (d !== el) d.classList.remove('open');
    });
    if (el.classList.contains('open')) { el.classList.remove('open'); return; }
    // Position below the filter button (fixed positioning, viewport-relative).
    const btn = document.querySelector('#' + tableId
        + ' > thead > tr > th:nth-child(' + (colIdx+1) + ') .th-filter-btn');
    if (btn) {
        const rect = btn.getBoundingClientRect();
        el.style.top = (rect.bottom + 2) + 'px';
        el.style.left = Math.max(4, Math.min(rect.left, window.innerWidth - 360)) + 'px';
    }
    el.classList.add('open');
}

function filterSearchChange(input) {
    const el = input.closest('.filter-dropdown');
    if (!el) return;
    const q = input.value.toLowerCase();
    el.querySelectorAll('.filter-values label').forEach(lbl => {
        const txt = lbl.textContent.toLowerCase();
        lbl.style.display = (!q || txt.indexOf(q) >= 0) ? 'flex' : 'none';
    });
}

function filterSelectAll(input) {
    const el = input.closest('.filter-dropdown');
    if (!el) return;
    el.querySelectorAll('.filter-values input[type="checkbox"]').forEach(cb => {
        if (cb.closest('label').style.display !== 'none') cb.checked = input.checked;
    });
}

function applyColumnFilter(tableId, colIdx) {
    const el = document.getElementById('filter-dropdown-' + tableId + '-' + colIdx);
    if (!el) return;
    const all = new Set();
    const checked = new Set();
    el.querySelectorAll('.filter-values input[type="checkbox"]').forEach(cb => {
        all.add(cb.value);
        if (cb.checked) checked.add(cb.value);
    });
    let f = _tableColFilters[tableId] || {};
    if (checked.size === all.size) {
        delete f[colIdx];
    } else {
        f[colIdx] = checked;
    }
    if (Object.keys(f).length) _tableColFilters[tableId] = f;
    else delete _tableColFilters[tableId];
    _applyAllRowFilters(tableId);
    const btn = document.querySelector('#' + tableId
        + ' > thead > tr > th:nth-child(' + (colIdx+1) + ') .th-filter-btn');
    if (btn) btn.classList.toggle('active', !!(_tableColFilters[tableId] && _tableColFilters[tableId][colIdx]));
    _updateClearFiltersBtn(tableId);
    el.classList.remove('open');
}

function clearAllFilters(tableId) {
    delete _tableColFilters[tableId];
    _applyAllRowFilters(tableId);
    const table = document.getElementById(tableId);
    if (table) {
        table.querySelectorAll(':scope > thead > tr > th .th-filter-btn.active')
            .forEach(b => b.classList.remove('active'));
    }
    // Re-check all checkboxes across all dropdowns for this table.
    document.querySelectorAll('[id^="filter-dropdown-' + tableId + '-"]').forEach(el => {
        el.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = true);
        el.classList.remove('open');
    });
    _updateClearFiltersBtn(tableId);
}

function _updateClearFiltersBtn(tableId) {
    const btn = document.getElementById('clear-filters-' + tableId);
    if (!btn) return;
    const f = _tableColFilters[tableId];
    const hasAny = f && Object.keys(f).length > 0;
    btn.style.display = hasAny ? '' : 'none';
}

// Close open filter dropdowns on outside click (not on the button itself).
document.addEventListener('mousedown', function(e) {
    if (e.target.closest('.filter-dropdown') || e.target.closest('.th-filter-btn')) return;
    document.querySelectorAll('.filter-dropdown.open').forEach(d => d.classList.remove('open'));
}, true);

// Close open filter dropdowns when the user scrolls the page or any
// scrollable ancestor OUTSIDE the dropdown itself. The dropdown is
// position:fixed relative to its filter-btn, so an outer scroll would
// detach it visually. But scrolling INSIDE the dropdown's own
// .filter-values list (the scroll the user is likely doing to find a
// value) must NOT close it -- we guard against that by checking the
// scroll event's target.
window.addEventListener('scroll', function(e) {
    const t = e.target;
    if (t && t.closest && t.closest('.filter-dropdown')) return;
    document.querySelectorAll('.filter-dropdown.open').forEach(d => d.classList.remove('open'));
}, true);

function _normHeader(h, idx) {
    // Accept: "Label" | {label, tool?, width?, type?, noSort?, noFilter?, expand?, filterChips?}
    //
    //   noSort:      true = no sort arrows / no click-to-sort on this column
    //   noFilter:    true = no column-header filter dropdown on this column
    //                       (does not affect the row-filter AND across other
    //                        columns; that still applies)
    //   expand:      true = show the column-wide expand icon on this column.
    //                       Opt-IN -- columns do NOT get expand by default.
    //                       Long-prose columns (descriptions, rationales,
    //                       signals) are the ones worth opting in.
    //   filterChips: CSS selector (e.g. ".decision-chip") — when set,
    //                the filter dropdown shows individual chip labels
    //                extracted via querySelectorAll, not the full cell text.
    if (typeof h === "string") {
        return {label: h, tool: false, width: null, type: "str",
                noSort: false, noFilter: false, expand: false};
    }
    return {
        label: h.label || "",
        tool: !!h.tool,
        width: h.width || null,
        type: h.type || "str",
        noSort: !!h.noSort,
        noFilter: !!h.noFilter,
        expand: !!h.expand,
        filterChips: h.filterChips || null,
    };
}

// buildTableHTML({id, headers, rows, wrap?, tableClass?, colgroup?}) -> string
//   headers:  Array of string | {label, tool?, width?, type?, noSort?}
//   rows:     Array of Array of HTML strings (one per column)
//   wrap:     default true -- wrap in <div class="table-wrap">
//   tableClass: extra class(es) appended to "data-table"
//   colgroup: optional Array<string> of class names ("c-id"|"c-sev"|"c-status"
//             |"c-title"|""), one per column. Emits a <colgroup> before
//             <thead> so CSS can pin column widths via table-layout:fixed.
//             Takes precedence over per-header `width` hints.
function buildTableHTML(opts) {
    let id = opts.id;
    let headers = (opts.headers || []).map(_normHeader);
    let rows = opts.rows || [];
    let wrap = opts.wrap !== false;
    let extraClass = opts.tableClass ? (" " + opts.tableClass) : "";
    let colgroup = opts.colgroup || null;

    let saved = _tableSortState[id]; // may be undefined
    if (saved) {
        rows = _sortRowsByState(rows, headers, saved);
    }

    // Column-expand + column-hidden + filter state to re-apply at build
    // time (same pattern sort uses). Declared BEFORE colgroup emission
    // because the loop below references _hiddenCls / savedHidden.
    const savedExpanded = _tableColExpanded[id];
    const savedHidden = _tableColHidden[id];
    const savedFilters = _tableColFilters[id];
    const _hiddenCls = (i) => (savedHidden && savedHidden.has(i)) ? ' col-hidden' : '';

    let parts = [];
    // If there are persisted column widths, the table needs an explicit
    // pixel width so table-layout:fixed actually takes effect. We sum
    // the persisted widths and use that as the table width. Without this,
    // re-rendered tables fall back to width:auto and ignore col widths.
    const savedWidths = _tableColWidths[id];
    let tableStyle = '';
    if (savedWidths && Object.keys(savedWidths).length > 0) {
        let totalW = 0;
        headers.forEach((h, i) => {
            const w = savedWidths[i] || h.width || null;
            if (w && w.endsWith('px')) totalW += parseInt(w, 10);
            else totalW += 150; // fallback for columns without explicit px width
        });
        tableStyle = ' style="width:' + totalW + 'px" data-fixed-layout="1"';
    }
    parts.push('<table id="' + id + '" class="data-table' + extraClass + '"');
    if (saved) {
        parts.push(' data-sort-col="' + saved.col + '" data-sort-dir="' + saved.dir + '"');
    }
    parts.push(tableStyle + '>');
    // Always emit a <colgroup> with one <col> per header. This gives
    // the resize handler a stable target (it sets col.style.width on
    // drag), lets the hide-column feature toggle `.col-hidden` on the
    // col element (display:none on a col cascades to every cell in
    // that column), and lets header configs pass explicit widths.
    parts.push('<colgroup>');
    if (colgroup && colgroup.length) {
        // Caller passed a custom colgroup class list (e.g. drill-findings
        // tables using c-id / c-sev / c-status / c-title for widths).
        const savedW1 = _tableColWidths[id] || {};
        colgroup.forEach((cls, i) => {
            const hid = _hiddenCls(i);
            const classes = [];
            if (cls) classes.push(cls);
            if (hid) classes.push('col-hidden');
            const clsAttr = classes.length ? ' class="' + classes.join(' ') + '"' : '';
            const styleAttr = savedW1[i] ? ' style="width:' + savedW1[i] + '"' : '';
            parts.push('<col' + clsAttr + styleAttr + '>');
        });
    } else {
        // Default: one <col> per header. User-resized widths
        // (_tableColWidths) take priority; then h.width (string like
        // "90px" or "25%"); absence means the column gets the browser's
        // default fixed-layout share until the user manually resizes.
        const savedW2 = _tableColWidths[id] || {};
        headers.forEach((h, i) => {
            const hid = _hiddenCls(i);
            const clsAttr = hid ? ' class="col-hidden"' : '';
            const w = savedW2[i] || h.width || null;
            const styleAttr = w ? ' style="width:' + w + '"' : '';
            parts.push('<col' + clsAttr + styleAttr + '>');
        });
    }
    parts.push('</colgroup>');

    // Distinct values per filterable column, for filter dropdown contents.
    function _cellTextForFilter(cell) {
        let src = cell;
        if (cell && typeof cell === 'object' && cell.html !== undefined) src = cell.html;
        if (typeof src !== 'string') src = String(src == null ? '' : src);
        const tmp = document.createElement('div');
        tmp.innerHTML = src;
        return (tmp.textContent || '').trim();
    }
    const distinctByCol = headers.map((h, i) => {
        if (h.noFilter) return null;
        const s = new Set();
        if (h.filterChips) {
            // Tag-based: extract individual chip labels from each cell
            rows.forEach(r => {
                _extractChipLabels(r[i], h.filterChips).forEach(t => s.add(t));
            });
        } else {
            rows.forEach(r => { s.add(_cellTextForFilter(r[i])); });
        }
        return Array.from(s).filter(v => v !== '' && v != null).sort((a,b) => a.localeCompare(b));
    });

    // Filter UI is only emitted when the wrapper that hosts the
    // filter-dropdown <div> elements is also emitted. With wrap=false
    // (nested drill-findings tables) or minimal=true (small reference
    // tables) there IS no dropdown element for a click handler to find,
    // so we suppress the filter icon itself rather than leave a dead
    // click target that silently does nothing.
    const filterUIEnabled = wrap && !opts.minimal;

    parts.push('<thead><tr>');
    headers.forEach((h, i) => {
        let cls = [];
        if (h.tool) cls.push("th-tool");
        if (h.noSort) cls.push("th-nosort");
        let clsAttr = cls.length ? ' class="' + cls.join(" ") + '"' : '';
        let onClick = h.noSort ? "" : ' onclick="sortTable(\'' + id + '\',' + i + ',\'' + h.type + '\')"';
        // Sort arrow lives in its own <span class="th-arrow"> so
        // sortTable() can update its text via textContent without
        // rewriting the surrounding <th> innerHTML. Rewriting innerHTML
        // would risk dropping the expand/filter span elements and their
        // bound onclick handlers, and would also reorder them visually.
        let arrowText = h.noSort ? "" : " \u25B4\u25BE";
        if (saved && saved.col === i) {
            arrowText = saved.dir === "asc" ? " \u25B4" : " \u25BE";
        }
        const arrowHtml = '<span class="th-arrow">' + arrowText + '</span>';
        // Column-wide expand button. Opt-IN per column via {expand: true}
        // on the header config. stopPropagation prevents the click from
        // bubbling to the <th> onclick (which would trigger sort).
        let expandActive = (savedExpanded && savedExpanded.has(i)) ? ' active' : '';
        let expandBtn = h.expand
            ? '<span class="th-expand-btn' + expandActive
              + '" title="Expand column" onclick="event.stopPropagation();toggleColExpanded(\''
              + id + '\',' + i + ');">\u2195</span>'
            : '';
        // Column filter button. Suppressed when (a) the host wrapper
        // won't emit a dropdown, (b) the column opted out via noFilter,
        // or (c) the distinct-value set for this column is empty.
        const filterActive = (savedFilters && savedFilters[i]) ? ' active' : '';
        const canFilter = filterUIEnabled && !h.noFilter
            && distinctByCol[i] && distinctByCol[i].length > 0;
        const filterBtn = canFilter
            ? '<span class="th-filter-btn' + filterActive
              + '" title="Filter column" onclick="toggleFilterDropdown(\''
              + id + '\',' + i + ',event);">' + _FILTER_ICON_SVG + '</span>'
            : '';
        const hiddenTh = _hiddenCls(i);
        if (hiddenTh) clsAttr = ' class="' + (cls.length ? (cls.join(' ') + ' col-hidden') : 'col-hidden') + '"';
        const chipAttr = h.filterChips ? ' data-filter-chips="' + h.filterChips + '"' : '';
        parts.push('<th' + clsAttr + chipAttr + onClick + '>' + h.label + arrowHtml
            + expandBtn + filterBtn
            + '<span class="col-resize" onmousedown="startResize(event)" onclick="event.stopPropagation()"></span></th>');
    });
    parts.push('</tr></thead><tbody>');
    // Row-level filter check at build time (state re-applied on re-render).
    function _rowPassesBuildFilters(r) {
        if (!savedFilters) return true;
        for (const k in savedFilters) {
            const allowed = savedFilters[k];
            if (!allowed || allowed.size === 0) continue;
            const idx = parseInt(k, 10);
            const h = headers[idx];
            if (h && h.filterChips) {
                // Tag-based: pass if ANY chip label is in the allowed set
                const tags = _extractChipLabels(r[idx], h.filterChips);
                if (!tags.length || !tags.some(t => allowed.has(t))) return false;
            } else {
                if (!allowed.has(_cellTextForFilter(r[idx]))) return false;
            }
        }
        return true;
    }
    rows.forEach(r => {
        const passes = _rowPassesBuildFilters(r);
        parts.push(passes ? '<tr>' : '<tr class="row-hidden">');
        r.forEach((cell, colIdx) => {
            // Cell may be a plain HTML string OR an object
            //   {html: "...", tdClass: "cell-signals"}
            // which lets the caller put a class on the <td> itself
            // (used for Risk Profile "Additional Signals" chip cells).
            const expandCls = (savedExpanded && savedExpanded.has(colIdx)) ? 'col-expanded-all' : '';
            const hiddenClsTd = _hiddenCls(colIdx) ? 'col-hidden' : '';
            const extras = [expandCls, hiddenClsTd].filter(Boolean).join(' ');
            if (cell && typeof cell === "object" && cell.html !== undefined) {
                const baseCls = cell.tdClass || '';
                const combined = (baseCls + (extras ? ' ' + extras : '')).trim();
                const cls = combined ? ' class="' + combined + '"' : '';
                parts.push('<td' + cls + '>' + cell.html + '</td>');
            } else {
                const cls = extras ? ' class="' + extras + '"' : '';
                parts.push('<td' + cls + '>' + cell + '</td>');
            }
        });
        parts.push('</tr>');
    });
    parts.push('</tbody></table>');

    let html = parts.join("");
    if (wrap) html = '<div class="table-wrap">' + html + '</div>';

    // Toolbar + Columns menu + per-column filter dropdowns. Skipped
    // when opts.minimal is true (small reference tables where these
    // affordances would be pure noise) or when wrap is false (nested
    // drill-findings tables that render inline inside an expanded
    // cell -- no outer wrapper to host a toolbar).
    if (wrap && !opts.minimal) {
        let menuHtml = '<div class="table-cols-menu" id="cols-menu-' + id + '">';
        menuHtml += '<div class="cols-menu-header">Show/hide columns</div>';
        headers.forEach((h, i) => {
            const isHidden = savedHidden && savedHidden.has(i);
            const checked = isHidden ? '' : ' checked';
            menuHtml += '<label><input type="checkbox"' + checked
                + ' onchange="toggleColHidden(\'' + id + '\',' + i + ',!this.checked)"> '
                + (h.label || ('Col ' + (i+1))) + '</label>';
        });
        menuHtml += '<div class="cols-menu-footer"><button onclick="resetCols(\'' + id + '\')">Reset</button></div>';
        menuHtml += '</div>';

        // Per-column filter dropdowns (one div per filterable column).
        let filterDropdowns = '';
        headers.forEach((h, i) => {
            if (h.noFilter || !distinctByCol[i] || distinctByCol[i].length === 0) return;
            const selected = (savedFilters && savedFilters[i]) || null;
            let body = '<input type="text" class="filter-search" placeholder="Search values..." oninput="filterSearchChange(this)">';
            body += '<label class="filter-select-all"><input type="checkbox" checked onchange="filterSelectAll(this)"> (Select all)</label>';
            body += '<div class="filter-values">';
            distinctByCol[i].forEach(v => {
                const isChecked = !selected || selected.has(v);
                const safeVal = (v + '').replace(/"/g, '&quot;');
                body += '<label><input type="checkbox" value="' + safeVal + '"'
                    + (isChecked ? ' checked' : '') + '> ' + safeVal + '</label>';
            });
            body += '</div>';
            body += '<div class="filter-actions">'
                + '<button onclick="document.getElementById(\'filter-dropdown-' + id + '-' + i + '\').classList.remove(\'open\');">Cancel</button>'
                + '<button class="primary" onclick="applyColumnFilter(\'' + id + '\',' + i + ');">Apply</button>'
                + '</div>';
            filterDropdowns += '<div class="filter-dropdown" id="filter-dropdown-' + id + '-' + i + '">' + body + '</div>';
        });

        const hasAnyFilter = !!(savedFilters && Object.keys(savedFilters).length > 0);
        const clearBtn = '<button class="table-toolbar-btn" id="clear-filters-' + id + '"'
            + ' style="' + (hasAnyFilter ? '' : 'display:none;') + '"'
            + ' onclick="clearAllFilters(\'' + id + '\')">Clear filters</button>';

        const toolbar = '<div class="table-toolbar">'
            + '<button class="table-toolbar-btn table-cols-btn" onclick="toggleColsMenu(\'' + id + '\')">Columns \u25BE</button>'
            + clearBtn
            + menuHtml
            + '</div>';
        html = '<div class="table-outer">' + toolbar + html + filterDropdowns + '</div>';
    }
    return html;
}

// makeTable was the legacy entry point that wrote into a pre-allocated
// <table> element in the static HTML body. It could only emit the
// <table> innerHTML, never the surrounding .table-outer wrapper that
// holds the toolbar + filter dropdowns, so the two flagship tables it
// served (entity-profile-table, risk-entity-table) silently lacked
// filter functionality even though filter icons rendered in their
// headers. Both callers now build into a host <div> via
// buildTableHTML(wrap: true) and this function has been removed.

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
    // Strip tags and normalize whitespace so pills/spans sort by their text.
    // Unwrap object-form cells ({html, tdClass}) before extracting text.
    let src = cellHtml;
    if (src && typeof src === "object" && src.html !== undefined) src = src.html;
    let tmp = document.createElement("div");
    tmp.innerHTML = String(src || "");
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

    // Re-sort the existing DOM rows in place. IMPORTANT: use :scope selectors
    // so we only touch the OUTER table's rows. Cells can contain nested tables
    // (e.g. Risk Profile "Impact of Issues" expands into IAG/ORE/PRSA/RAP
    // tables) and an unscoped "tbody tr" would hoist their rows into the
    // outer sort.
    let tbody = table.querySelector(":scope > tbody");
    if (!tbody) return;
    let bodyRows = Array.from(tbody.children).filter(el => el.tagName === "TR");
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
    bodyRows.forEach(r => tbody.appendChild(r));

    // Update arrow indicators on the OUTER thead only. Nested tables
    // have their own thead which we must not touch, hence the :scope >
    // chain. We target the dedicated .th-arrow span in each <th> so
    // this is a pure textContent update -- no innerHTML rewrite, no
    // risk of stripping the expand/filter button spans or their
    // onclick handlers.
    let ths = table.querySelectorAll(":scope > thead > tr > th");
    ths.forEach((th, i) => {
        let arrowSpan = th.querySelector(":scope > .th-arrow");
        if (!arrowSpan) return;
        let arrow;
        if (i === col) arrow = asc ? " \u25B4" : " \u25BE";
        else if (th.classList.contains("th-nosort")) arrow = "";
        else arrow = " \u25B4\u25BE";
        arrowSpan.textContent = arrow;
    });
}

// ==================== CELL CLICK-TO-EXPAND (scoped to .data-table) ====================
// Two distinct click-to-expand contracts share this listener:
//   .cell-signals  — Risk Profile "Additional Signals" cell. Toggles the
//                    `expanded` class; swaps chip-summary <-> full detail.
//   .cell-expanded — default data-table cell overflow expander. Generic
//                    yellow-highlight toggle for any other wide cell.
// A td.cell-signals NEVER gets .cell-expanded (different styling contracts).
document.addEventListener("click", function(e) {
    if (e.target.tagName === "A") return;
    if (e.target.classList && e.target.classList.contains("col-resize")) return;
    // Tail end of a drag-select: don't yank the cell closed mid-copy.
    const _sel = window.getSelection && window.getSelection();
    if (_sel && _sel.toString().length > 0) return;
    let summaryTd = e.target.closest(
        "td.cell-signals, td.cell-decision-basis, td.cell-impact, td.cell-l2-name"
    );
    if (summaryTd) {
        summaryTd.classList.toggle("expanded");
        return;
    }
    let td = e.target.closest(".data-table td");
    if (!td) return;
    td.classList.toggle("cell-expanded");
});

// ==================== COLUMN RESIZE ====================
// IMPORTANT: the base table CSS uses width:auto, which means
// table-layout:fixed is NOT active by default (per the CSS spec,
// fixed layout requires an explicit width). This is intentional --
// auto lets the browser size columns by content for initial render.
//
// When the user grabs a resize handle, _ensureFixedLayout() converts
// the table to an explicit pixel width, freezes every column's
// rendered width into its <col> element, and only THEN does
// table-layout:fixed take effect. From that point, col.style.width
// changes are authoritative.
//
// During drag, the table's overall width grows by the same delta as
// the column, so other columns keep their widths (Excel-like behavior)
// and .table-wrap shows a horizontal scrollbar if needed.

let _resizeTh = null, _resizeColEl = null, _resizeStartX = 0, _resizeStartW = 0;
let _resizeTableId = null, _resizeColIdx = -1;
let _resizeTable = null, _resizeTableStartW = 0;

function _resolveResizeTargets(handle) {
    const th = handle.parentElement;
    const tr = th && th.parentElement;
    if (!th || !tr) return null;
    const thIdx = Array.prototype.indexOf.call(tr.children, th);
    const table = th.closest('table');
    const colEl = table && table.querySelector(
        ':scope > colgroup > col:nth-child(' + (thIdx + 1) + ')'
    );
    if (!colEl) return null;
    return { th: th, colEl: colEl, thIdx: thIdx, table: table };
}

// Freeze a table to explicit pixel width + pixel column widths.
// This activates table-layout:fixed (which requires width != auto)
// and locks every column to its current rendered width so switching
// layout mode doesn't cause columns to jump.
function _ensureFixedLayout(table) {
    if (table.dataset.fixedLayout) return; // already frozen
    const ths = table.querySelectorAll(':scope > thead > tr > th');
    const cols = table.querySelectorAll(':scope > colgroup > col');
    // Snapshot rendered widths BEFORE setting explicit table width
    const widths = [];
    ths.forEach(th => widths.push(th.offsetWidth));
    // Set explicit table width (activates table-layout:fixed)
    table.style.width = table.offsetWidth + 'px';
    // Freeze each column to its rendered width
    widths.forEach((w, i) => {
        if (cols[i]) cols[i].style.width = w + 'px';
    });
    table.dataset.fixedLayout = '1';
}

function startResize(e) {
    e.stopPropagation();
    e.preventDefault();
    const info = _resolveResizeTargets(e.target);
    if (!info) return;
    // Activate fixed layout if not already active
    _ensureFixedLayout(info.table);
    _resizeTh = info.th;
    _resizeColEl = info.colEl;
    _resizeColIdx = info.thIdx;
    _resizeTable = info.table;
    _resizeTableId = info.table.id || null;
    _resizeStartX = e.pageX;
    _resizeStartW = info.th.offsetWidth;
    _resizeTableStartW = info.table.offsetWidth;
    e.target.classList.add("active");
    document.body.classList.add("col-resizing");
    document.addEventListener("mousemove", doResize);
    document.addEventListener("mouseup", stopResize);
}
function doResize(e) {
    if (!_resizeColEl || !_resizeTable) return;
    const delta = e.pageX - _resizeStartX;
    const colW = Math.max(40, _resizeStartW + delta);
    _resizeColEl.style.width = colW + "px";
    // Grow table by same delta so other columns don't squeeze
    const tableW = Math.max(_resizeTableStartW, _resizeTableStartW + delta);
    _resizeTable.style.width = tableW + "px";
}
function stopResize(e) {
    // Persist final column width so it survives re-renders
    if (_resizeColEl && _resizeTableId) {
        const finalW = _resizeColEl.style.width;
        if (finalW) {
            if (!_tableColWidths[_resizeTableId]) _tableColWidths[_resizeTableId] = {};
            _tableColWidths[_resizeTableId][_resizeColIdx] = finalW;
        }
    }
    if (_resizeTh) {
        const handle = _resizeTh.querySelector(".col-resize");
        if (handle) handle.classList.remove("active");
    }
    document.body.classList.remove("col-resizing");
    _resizeTh = null;
    _resizeColEl = null;
    _resizeTable = null;
    _resizeTableId = null;
    _resizeColIdx = -1;
    document.removeEventListener("mousemove", doResize);
    document.removeEventListener("mouseup", stopResize);
}

// ==================== DOUBLE-CLICK AUTO-FIT ====================
// Double-clicking a resize handle auto-sizes the column to fit its
// widest content, similar to Excel's auto-fit behavior. Activates
// fixed layout, measures natural content widths using an off-screen
// probe, then applies the max to the <col> and grows the table.
function autoFitColumn(e) {
    e.stopPropagation();
    e.preventDefault();
    const info = _resolveResizeTargets(e.target);
    if (!info) return;
    const { th, colEl, thIdx, table } = info;
    const tableId = table.id || null;

    // Activate fixed layout if not already active
    _ensureFixedLayout(table);

    const oldColW = th.offsetWidth;

    // Measure header text width
    const probe = document.createElement('span');
    probe.style.cssText = 'position:absolute;visibility:hidden;white-space:nowrap;'
        + 'font:' + getComputedStyle(th).font + ';padding:0 24px;';
    document.body.appendChild(probe);
    probe.textContent = th.textContent.replace(/[\u25B4\u25BE\u2195]/g, '').trim();
    let maxW = probe.offsetWidth + 8; // +8 for sort/expand/filter icons

    // Measure each visible cell in this column
    const cells = table.querySelectorAll(
        ':scope > tbody > tr:not(.row-hidden) > td:nth-child(' + (thIdx + 1) + ')'
    );
    const cellStyle = cells.length ? getComputedStyle(cells[0]) : null;
    if (cellStyle) {
        probe.style.font = cellStyle.font;
        probe.style.padding = '0 24px';
    }
    cells.forEach(td => {
        probe.textContent = (td.textContent || '').trim();
        if (probe.offsetWidth > maxW) maxW = probe.offsetWidth;
    });
    document.body.removeChild(probe);

    // Clamp to reasonable bounds
    const fitW = Math.max(60, Math.min(maxW, 800));
    colEl.style.width = fitW + 'px';

    // Grow/shrink table by the column width delta
    const tableW = table.offsetWidth + (fitW - oldColW);
    table.style.width = Math.max(tableW, 200) + 'px';

    // Persist
    if (tableId) {
        if (!_tableColWidths[tableId]) _tableColWidths[tableId] = {};
        _tableColWidths[tableId][thIdx] = fitW + 'px';
    }
}

// Attach dblclick handler to all resize handles (event delegation)
document.addEventListener('dblclick', function(e) {
    if (e.target.classList && e.target.classList.contains('col-resize')) {
        autoFitColumn(e);
    }
});

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
    let text = String(raw || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    if (!text.trim()) return "";
    let rawLen = text.length;
    let blocks = text.split(/\n\s*\n+/).map(b => b.trim()).filter(Boolean);
    if (!blocks.length) return "";

    let bulletRe = /^\s*(?:[\u2022\-\*]|\d+[.)])\s+/;
    let mdRowRe = /^\s*\|?\s*([^|]*\|\s*)+\|?\s*$/;
    let mdSepRe = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/;

    function renderProse(block) {
        let joined = block.split("\n").map(l => l.trim()).filter(Boolean).join(" ");
        return "<p>" + esc(joined) + "</p>";
    }

    function tryMarkdownTable(block) {
        let lines = block.split("\n").map(l => l.trim()).filter(Boolean);
        if (lines.length < 2) return null;
        let matches = lines.filter(l => mdRowRe.test(l)).length;
        if (matches / lines.length < 0.6) return null;
        let rows = [];
        for (let l of lines) {
            if (mdSepRe.test(l)) continue;
            if (!mdRowRe.test(l)) continue;
            let parts = l.split("|").map(c => c.trim());
            while (parts.length && parts[0] === "") parts.shift();
            while (parts.length && parts[parts.length - 1] === "") parts.pop();
            if (parts.length) rows.push(parts);
        }
        if (!rows.length) return null;
        let ncols = rows[0].length;
        if (ncols < 2) return null;
        let headers = rows[0];
        let body = rows.slice(1);
        let html = '<table class="overview-table"><thead><tr>';
        for (let h of headers) html += "<th>" + esc(h) + "</th>";
        html += "</tr></thead><tbody>";
        for (let r of body) {
            html += "<tr>";
            for (let i = 0; i < ncols; i++) {
                let cell = i < r.length ? r[i] : "";
                html += "<td>" + esc(cell) + "</td>";
            }
            html += "</tr>";
        }
        html += "</tbody></table>";
        return html;
    }

    function tryBulletList(block) {
        let lines = block.split("\n").map(l => l.trim()).filter(Boolean);
        if (lines.length < 2) return null;
        if (!lines.every(l => bulletRe.test(l))) return null;
        let items = lines.map(l => "<li>" + esc(l.replace(bulletRe, "").trim()) + "</li>").join("");
        return '<ul class="overview-list">' + items + "</ul>";
    }

    function isHeaderLike(s) {
        if (!s) return false;
        let t = s.trim();
        if (!t) return false;
        if (/^\d{4}\b/.test(t)) return true;
        if (/\(.+\)/.test(t)) return true;
        if (/[a-zA-Z]/.test(t) && t === t.toUpperCase() && /[A-Z]/.test(t)) return true;
        if (/^[A-Z]/.test(t) && t.length < 30 && !/[.!?]\s*$/.test(t)) return true;
        return false;
    }

    function classify(block) {
        try {
            let md = tryMarkdownTable(block);
            if (md) return {type: "html", html: md};
        } catch (e) {}
        try {
            let bl = tryBulletList(block);
            if (bl) return {type: "html", html: bl};
        } catch (e) {}
        let lines = block.split("\n").map(l => l.trim()).filter(Boolean);
        if (lines.length === 1) {
            let t = lines[0];
            if (t.length < 80 && !/[.!?]\s*$/.test(t)) {
                return {type: "short-line", text: t, headerLike: isHeaderLike(t)};
            }
        }
        return {type: "prose", block: block};
    }

    function renderExportedTableRun(cells) {
        try {
            for (let n = Math.min(6, cells.length - 1); n >= 2; n--) {
                if (cells.length < 2 * n) continue;
                let firstN = cells.slice(0, n);
                let allHeader = firstN.every(c => isHeaderLike(c));
                if (!allHeader) continue;
                let distinct = new Set(firstN.map(c => c.toLowerCase())).size === n;
                if (!distinct) continue;
                let html = '<table class="overview-table"><thead><tr>';
                for (let h of firstN) html += "<th>" + esc(h) + "</th>";
                html += "</tr></thead><tbody>";
                let body = cells.slice(n);
                for (let i = 0; i < body.length; i += n) {
                    html += "<tr>";
                    for (let j = 0; j < n; j++) {
                        let v = i + j < body.length ? body[i + j] : "";
                        let out = v === "-" ? "\u2014" : v;
                        html += "<td>" + esc(out) + "</td>";
                    }
                    html += "</tr>";
                }
                html += "</tbody></table>";
                return html;
            }
            if (cells.length >= 4 && cells.length % 2 === 0) {
                let html = '<dl class="overview-dl">';
                for (let i = 0; i < cells.length; i += 2) {
                    html += "<dt>" + esc(cells[i]) + "</dt>";
                    html += "<dd>" + esc(cells[i + 1]) + "</dd>";
                }
                html += "</dl>";
                return html;
            }
            let items = cells.map(c => "<li>" + esc(c) + "</li>").join("");
            return '<ul class="overview-list">' + items + "</ul>";
        } catch (e) {
            return "<p>" + esc(cells.join(" \u00b7 ")) + "</p>";
        }
    }

    let classified;
    try {
        classified = blocks.map(classify);
    } catch (e) {
        return "<p>" + esc(text) + "</p>";
    }

    let merged = [];
    let i = 0;
    while (i < classified.length) {
        let item = classified[i];
        if (item.type === "short-line") {
            let j = i;
            let run = [];
            while (j < classified.length && classified[j].type === "short-line") {
                run.push(classified[j].text);
                j++;
            }
            if (run.length >= 6) {
                merged.push({type: "html", html: renderExportedTableRun(run)});
            } else {
                for (let k = 0; k < run.length; k++) {
                    merged.push({type: "html", html: "<p>" + esc(run[k]) + "</p>"});
                }
            }
            i = j;
            continue;
        }
        if (item.type === "html") {
            merged.push(item);
        } else {
            try {
                merged.push({type: "html", html: renderProse(item.block)});
            } catch (e) {
                merged.push({type: "html", html: "<p>" + esc(item.block) + "</p>"});
            }
        }
        i++;
    }

    if (!merged.length) return "";
    let rendered = merged.map(m => m.html);

    let truncate = rawLen > 800 && rendered.length > 2;
    if (!truncate) return rendered.join("");
    let tid = "overview-more-" + id;
    return rendered.slice(0, 2).join("") +
        '<div id="' + tid + '" style="display:none;">' + rendered.slice(2).join("") + '</div>' +
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
// parseSignalsForRender: pure parser. Returns
//   { orderedKeys, groupMap, contradictions }
// or null when signals are empty / yield no groups or contradictions.
// No HTML emission — shared by the drill-down full renderer and the
// Risk Profile cell chip-summary renderer.
function parseSignalsForRender(signals) {
    if (isEmpty(signals)) return null;
    let raw = String(signals);
    if (!raw.trim()) return null;

    // Split by newline-line first, then by " | " inside each line, so we know
    // which atoms share a newline-line and can inherit a leading [TAG].
    let lines = raw.split(/\n/);
    let atoms = [];
    lines.forEach(line => {
        let pieces = line.split(" | ").map(s => s.trim()).filter(Boolean);
        pieces.forEach((piece, idx) => {
            atoms.push({ raw: piece, isContinuation: idx > 0 });
        });
    });

    // Second-pass split: some inputs glue two tagged atoms together without
    // " | " (e.g. "...applicable [Aux] Listed..."). Split at " [Tag] "
    // boundaries. Leading-space requirement avoids matching prose like
    // "see [Exhibit A]".
    let rebuilt = [];
    atoms.forEach(a => {
        let rest = a.raw;
        const tagBoundary = /\s\[[A-Za-z][A-Za-z0-9 \-]*\]\s/g;
        let cuts = [];
        let m;
        while ((m = tagBoundary.exec(rest)) !== null) {
            cuts.push(m.index);
        }
        if (!cuts.length) {
            rebuilt.push(a);
            return;
        }
        let parts = [];
        let lastCut = 0;
        cuts.forEach(idx => {
            let segment = rest.substring(lastCut, idx).trim();
            if (segment) parts.push(segment);
            lastCut = idx + 1;
        });
        let tail = rest.substring(lastCut).trim();
        if (tail) parts.push(tail);
        parts.forEach((p, i) => {
            rebuilt.push({
                raw: p,
                isContinuation: i === 0 ? a.isContinuation : false,
            });
        });
    });
    atoms = rebuilt;

    const ID_LIST_RE = /^[A-Z]{2,5}-?\d+(\s*[;,]\s*[A-Z]{2,5}-?\d+)+$/;
    const ID_TOKEN_RE = /^[A-Z]{2,5}-?\d+$/;

    let parsed = [];
    let lastTagOnLine = null;
    let prevWasContinuation = false;
    atoms.forEach(a => {
        if (!a.isContinuation) lastTagOnLine = null;

        let s = a.raw;
        let lower = s.toLowerCase();
        if (lower.includes("well controlled but") || lower.includes("review whether")) {
            parsed.push({ kind: "contradiction", text: s });
            return;
        }

        let body = s;
        let tag = null;
        let tagMatch = body.match(/^\[([^\]]+)\]\s*/);
        if (tagMatch) {
            tag = tagMatch[1].trim();
            body = body.substring(tagMatch[0].length);
            if (!a.isContinuation) lastTagOnLine = tag;
        } else if (a.isContinuation && lastTagOnLine) {
            tag = lastTagOnLine;
        }

        let hint = "";
        let emIdx = body.indexOf("\u2014");
        if (emIdx >= 0) {
            hint = body.substring(emIdx + 1).trim();
            body = body.substring(0, emIdx).trim();
        }

        // Scan ALL parenthesized groups; collect IDs from any paren whose
        // inner text is a ID-list (2+ ID-shaped tokens separated by ; or ,).
        let ids = [];
        let cleaned = "";
        let i = 0;
        while (i < body.length) {
            let open = body.indexOf("(", i);
            if (open < 0) { cleaned += body.substring(i); break; }
            let close = body.indexOf(")", open);
            if (close < 0) { cleaned += body.substring(i); break; }
            let inner = body.substring(open + 1, close).trim();
            if (ID_LIST_RE.test(inner)) {
                inner.split(/\s*[;,]\s*/).forEach(tok => {
                    tok = tok.trim();
                    if (tok && ID_TOKEN_RE.test(tok)) ids.push(tok);
                });
                // drop the paren (and the single space that may precede it)
                let pre = body.substring(i, open);
                if (pre.endsWith(" ")) pre = pre.slice(0, -1);
                cleaned += pre;
                i = close + 1;
                // also swallow a redundant space immediately after the drop
                if (body[i] === " ") i += 1;
            } else {
                cleaned += body.substring(i, close + 1);
                i = close + 1;
            }
        }
        body = cleaned.replace(/\s+/g, " ").trim();

        parsed.push({ kind: "signal", tag: tag, body: body, hint: hint, ids: ids });
    });

    // Grouping: ordered by priority list, then unknown tags (insertion order),
    // then untagged last.
    const ORDER = ["Applicability", "App", "TP", "Model", "Core", "Aux"];
    let groupMap = {}; // tag -> { tag, label, items }
    let insertionOrder = [];
    parsed.filter(p => p.kind === "signal").forEach(p => {
        let key = p.tag || "__untagged__";
        if (!groupMap[key]) {
            groupMap[key] = { tag: p.tag, items: [] };
            insertionOrder.push(key);
        }
        groupMap[key].items.push(p);
    });

    let orderedKeys = [];
    ORDER.forEach(t => { if (groupMap[t]) orderedKeys.push(t); });
    insertionOrder.forEach(k => {
        if (k === "__untagged__") return;
        if (orderedKeys.indexOf(k) < 0) orderedKeys.push(k);
    });
    if (groupMap["__untagged__"]) orderedKeys.push("__untagged__");

    // Per-group shared-hint hoist
    orderedKeys.forEach(k => {
        let g = groupMap[k];
        if (g.items.length === 0) { g.sharedHint = ""; return; }
        let first = g.items[0].hint;
        if (first && g.items.every(it => it.hint === first)) {
            g.sharedHint = first;
            g.items.forEach(it => { it.hint = ""; });
        } else {
            g.sharedHint = "";
        }
    });

    let contradictions = parsed.filter(p => p.kind === "contradiction");
    if (!contradictions.length && !orderedKeys.length) return null;
    return { orderedKeys: orderedKeys, groupMap: groupMap, contradictions: contradictions };
}

// Emit the drill-down-style inner HTML for a parsed signals payload.
// Does NOT include the outer .drill-section / "Additional Signals" label
// wrapper — that's added only by renderSignalsFullHTML. This inner HTML
// is what the Risk Profile cell reuses inside .signals-detail.
//
// eid (optional): when provided, id-chips under [App] and [TP] groups are
// marked .id-chip-key if they're in the entity's "key" inventory set.
function _renderSignalsInnerHTML(parsed, eid) {
    let html = "";
    parsed.contradictions.forEach(p => {
        html += '<div class="signal-contradiction">\ud83d\udea8 <span>' + esc(p.text) + '</span></div>';
    });
    parsed.orderedKeys.forEach(k => {
        let g = parsed.groupMap[k];
        let isUntagged = (k === "__untagged__");
        html += '<div class="signal-group">';
        html += '<div class="signal-group-header">';
        if (isUntagged) {
            html += '<span class="signal-tag">Other</span>';
        } else {
            let slug = String(g.tag || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
            html += '<span class="signal-tag signal-tag-' + slug + '">' + esc(g.tag) + '</span>';
        }
        if (g.sharedHint) {
            html += '<span class="signal-group-hint">' + esc(g.sharedHint) + '</span>';
        }
        html += '</div>';
        html += '<ul class="signal-list">';
        const tag = g.tag;
        const isApp = tag === "App";
        const isTp = tag === "TP";
        g.items.forEach(it => {
            html += '<li class="signal-item">';
            html += '<span class="signal-body">' + esc(it.body) + '</span>';
            if (it.hint) {
                html += '<span class="signal-hint-inline">\u2014 ' + esc(it.hint) + '</span>';
            }
            if (it.ids && it.ids.length) {
                html += '<span class="signal-ids">';
                it.ids.forEach(id => {
                    let cls = "id-chip";
                    if (eid && isApp && isKeyApp(eid, id)) cls += " id-chip-key";
                    else if (eid && isTp && isKeyTp(eid, id)) cls += " id-chip-key";
                    html += '<span class="' + cls + '">' + esc(id) + '</span>';
                });
                html += '</span>';
            }
            html += '</li>';
        });
        html += '</ul>';
        html += '</div>';
    });
    return html;
}

// Full drill-down renderer: emits the same HTML that the original
// renderSignals returned, wrapped in <div class="drill-section">
// with the "Additional Signals" label.
function renderSignalsFullHTML(parsed, eid) {
    let html = '<div class="drill-section"><span class="label">Additional Signals</span>';
    html += _renderSignalsInnerHTML(parsed, eid);
    html += '</div>';
    return html;
}

// Risk Profile cell renderer: emits a chip summary + a hidden detail
// block. The enclosing <td class="cell-signals"> is added by the caller
// so expand/collapse toggles on the td. Returns "" for empty.
function renderSignalsForCell(parsed, eid) {
    let summaryHtml = '<span class="signals-summary">';
    parsed.orderedKeys.forEach(k => {
        let g = parsed.groupMap[k];
        let label = (k === "__untagged__") ? "Other" : g.tag;
        let slug = String(label || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
        // "(none key)" suffix: App/TP chips get a muted suffix when
        // ALL IDs tagged to the entity for this L2 are non-key.
        let nonKeySuffix = "";
        if (eid && (k === "App" || k === "TP")) {
            let allIds = [];
            g.items.forEach(it => { if (it.ids) allIds = allIds.concat(it.ids); });
            if (allIds.length) {
                const keyFn = (k === "App") ? isKeyApp : isKeyTp;
                const anyKey = allIds.some(id => keyFn(eid, id));
                if (!anyKey) nonKeySuffix = '<span class="chip-nonkey-suffix">(none key)</span>';
            }
        }
        summaryHtml += '<span class="signal-summary-chip signal-summary-chip-' + slug + '">'
            + esc(label) + '<span class="count">\u00d7' + g.items.length + '</span>'
            + nonKeySuffix + '</span>';
    });
    if (parsed.contradictions.length) {
        summaryHtml += '<span class="signal-summary-chip" style="background:#f8d7da;color:#721c24;">'
            + '\u26a0<span class="count">\u00d7' + parsed.contradictions.length + '</span></span>';
    }
    summaryHtml += '<span class="signals-expand-hint">click to expand</span></span>';

    let detailHtml = '<div class="signals-detail">';
    detailHtml += _renderSignalsInnerHTML(parsed, eid);
    detailHtml += '<span class="signals-collapse-hint">click to collapse</span>';
    detailHtml += '</div>';

    return summaryHtml + detailHtml;
}

// Thin back-compat wrapper retained for drill-down callers.
function renderSignals(signals, eid) {
    let parsed = parseSignalsForRender(signals);
    return parsed ? renderSignalsFullHTML(parsed, eid) : "";
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

function renderKeyRiskDescriptions(detailRow, eid, l2) {
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
        html += '<div class="subrisk-row"><span class="id-chip">' + esc(String(rid)) + '</span><span class="subrisk-name">' + esc(desc) + '</span></div>';
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

    // Sub-section header: label only — count pills removed. The severity
    // column in the table below already communicates the same information,
    // so duplicating it in the header was noisy.
    let html = '<div class="drill-section">' + renderSectionHeader(label, "");

    if (cfg.contradictionWarning) {
        html += cfg.contradictionWarning;
    }

    // Column order: ID, severity, status, title. Rating/status pills sit
    // directly after the ID so the auditor scans them first; the title
    // takes the remaining width. Widths pinned via <colgroup>.
    let headers = [{label: cfg.idLabel || "ID"}];
    let colClasses = ["c-id"];
    if (hasSev) {
        headers.push({label: cfg.severityLabel || "Severity"});
        colClasses.push("c-sev");
    }
    if (hasStatus) {
        headers.push({label: cfg.statusLabel || "Status"});
        colClasses.push("c-status");
    }
    headers.push({label: cfg.titleLabel || "Title"});
    colClasses.push("c-title");

    let tableId = cfg.tableId || ("evtbl-" + Math.random().toString(36).slice(2, 8));
    let tableRows = rows.map(r => {
        let row = ['<span class="id-chip">' + esc(String(r.id || "")) + '</span>'];
        if (hasSev) row.push(makePill(r.severity || "", sevPalette));
        if (hasStatus) row.push(makePill(r.status || "", "iagStatus"));
        row.push(esc(String(r.title || "")));
        return row;
    });
    html += buildTableHTML({
        id: tableId,
        headers: headers,
        rows: tableRows,
        wrap: false,
        tableClass: "drill-findings-table",
        colgroup: colClasses,
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

    // Note: the "Well Controlled but open Critical/High finding" contradiction
    // warning now renders inside renderControlAssessment (next to the rating
    // it questions) rather than above the IAG Issues table.

    return renderEvidenceSection({
        label: "IAG Issues",
        rows: rows,
        severityOrder: ["Critical","High","Medium","Low"],
        severityPalette: "severity",
        emptyMessage: "No IAG issues tagged to this L2.",
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
// DECISION BASIS + IMPACT OF ISSUES — Risk Profile cell renderers
// ================================================================
// Method substring -> chip slug. Mirrors _derive_decision_type in
// review_builders.py; order is most-specific-first so e.g. "llm_confirmed_na"
// doesn't match inside a method string containing "direct".
const _DECISION_CHIP_MAP = [
    ["llm_confirmed_na",           "ai-na"],
    ["source_not_applicable",      "legacy-na"],
    ["evaluated_no_evidence",      "assumed-na"],
    ["no_evidence_all_candidates", "undetermined"],
    ["true_gap_fill",              "gap"],
    ["gap_fill",                   "gap"],
    ["llm_override",               "ai-applied"],
    ["issue_confirmed",            "issue"],
    ["evidence_match",             "keyword"],
    ["direct",                     "direct"],
];
function decisionChipSlug(method) {
    let m = String(method || "");
    for (let i = 0; i < _DECISION_CHIP_MAP.length; i++) {
        if (m.indexOf(_DECISION_CHIP_MAP[i][0]) >= 0) return _DECISION_CHIP_MAP[i][1];
    }
    return "";
}

// Matching findings for the issue-confirmed chip. Same filter contract as
// renderRelevantFindings so the id-chip row matches what drill-down shows.
function _issueConfirmedFindingIds(eid, l2) {
    if (isEmpty(eid) || isEmpty(l2)) return [];
    return findingsData.filter(f => {
        let fEid = String(f["entity_id"]||f["Audit Entity ID"]||"");
        let fL2 = String(f["l2_risk"]||f["Mapped To L2(s)"]||f["Risk Dimension Categories"]||"");
        return fEid === String(eid) && fL2.indexOf(l2) >= 0
            && isActiveIagStatus(f["status"]||f["Finding Status"]);
    }).map(f => String(f["issue_id"]||f["Finding ID"]||"")).filter(Boolean);
}

// Decision Basis cell: chip summary + full-prose detail.
function renderDecisionBasisCell(row, eid, l2) {
    let prose = String(row["Decision Basis"] || "");
    let method = String(row["Method"] || "");
    let label = String(row["Decision Type"] || "");
    if (isEmpty(prose) && isEmpty(label)) return "";

    let slug = decisionChipSlug(method);
    if (!slug && !label) return prose ? esc(prose) : "";

    let summaryHtml = '<span class="decision-summary">';
    if (slug) {
        summaryHtml += '<span class="decision-chip decision-chip-' + slug + '">'
            + esc(label || slug) + '</span>';
    }

    // Issue Confirmed: append matching finding id-chips
    if (slug === "issue") {
        let ids = _issueConfirmedFindingIds(eid, l2);
        let shown = ids.slice(0, 3);
        shown.forEach(id => {
            summaryHtml += '<span class="id-chip">' + esc(id) + '</span>';
        });
        if (ids.length > shown.length) {
            summaryHtml += '<span class="meta" style="font-size:11px;">+'
                + (ids.length - shown.length) + ' more</span>';
        }
    }

    summaryHtml += '</span>';

    let detailHtml = '<div class="decision-detail">' + esc(prose) + '</div>';
    return { html: summaryHtml + detailHtml, tdClass: "cell-decision-basis" };
}

// L2 name cell renderer: plain L2 name as summary, full L2 Definition
// (with rolled-up L3/L4 sub-definitions where applicable) as the detail.
// Reuses the "L2 Definition" column from Audit_Review, which review_builders
// already populates with the L2 def + L3 sub-entries (e.g. External Fraud
// shows the parent L2 def followed by First Party / Victim Fraud L3 defs).
function renderL2NameCell(row) {
    const l2 = String(row["New L2"] || "").trim();
    if (!l2) return "";
    const definition = String(row["L2 Definition"] || "").trim();
    const summaryHtml = '<span class="l2-name-summary">' + esc(l2) + '</span>';
    // If there's no definition (not yet populated, or reference file missing),
    // fall back to plain text — no click-to-expand affordance.
    if (!definition) return esc(l2);
    const detailHtml = '<div class="l2-name-detail">' + esc(definition) + '</div>';
    return { html: summaryHtml + detailHtml, tdClass: "cell-l2-name" };
}

// Worst severity slug for an Impact of Issues source group. Maps all four
// source types onto a common critical|high|medium|low palette for summary
// chip colouring. ORE classes follow the amendment: A=critical, B=high,
// C=medium, Near Miss=low.
function _worstImpactSeverity(rows, severityGetter, classMap) {
    let best = null;
    let rank = {critical: 4, high: 3, medium: 2, low: 1};
    rows.forEach(r => {
        let raw = String(severityGetter(r) || "").trim();
        let slug = classMap ? classMap[raw.toLowerCase()] : null;
        if (!slug) {
            let lower = raw.toLowerCase();
            if (lower.indexOf("critical") >= 0) slug = "critical";
            else if (lower.indexOf("high") >= 0) slug = "high";
            else if (lower.indexOf("medium") >= 0) slug = "medium";
            else if (lower.indexOf("low") >= 0) slug = "low";
        }
        if (!slug) return;
        if (!best || rank[slug] > rank[best]) best = slug;
    });
    return best || "none";
}

function _iagImpactItems(eid, l2) {
    if (isEmpty(eid) || isEmpty(l2)) return [];
    return findingsData.filter(f => {
        let fEid = String(f["entity_id"]||f["Audit Entity ID"]||"");
        let fL2 = String(f["l2_risk"]||f["Mapped To L2(s)"]||f["Risk Dimension Categories"]||"");
        return fEid === String(eid) && fL2.indexOf(l2) >= 0
            && isActiveIagStatus(f["status"]||f["Finding Status"]);
    });
}
function _oreImpactItems(eid, l2) {
    if (isEmpty(eid) || isEmpty(l2) || !oreData.length) return [];
    let eidCol = resolveCol(oreData, ["entity_id", "Audit Entity (Operational Risk Events)", "Audit Entity ID"]);
    if (!eidCol) return [];
    let seen = new Set();
    let out = [];
    oreData.forEach(o => {
        if (String(o[eidCol]||"").trim() !== String(eid)) return;
        let mapped = String(o["Mapped L2s"]||o["l2_risk"]||"").split(/[;\r\n]+/).map(s => s.trim());
        if (mapped.indexOf(l2) < 0) return;
        let id = String(o["Event ID"]||"").trim();
        if (id && seen.has(id)) return;
        if (id) seen.add(id);
        out.push(o);
    });
    return out;
}
function _prsaImpactItems(eid, l2) {
    if (isEmpty(eid) || isEmpty(l2) || !prsaData.length) return [];
    let eidCol = resolveCol(prsaData, ["AE ID", "Audit Entity ID"]);
    if (!eidCol) return [];
    let seen = new Set();
    let out = [];
    prsaData.forEach(p => {
        if (String(p[eidCol]||"").trim() !== String(eid)) return;
        let mapped = String(p["Mapped L2s"]||"").split(/[;\r\n]+/).map(s => s.trim());
        if (mapped.indexOf(l2) < 0) return;
        let id = String(p["Issue ID"]||"").trim();
        if (id && seen.has(id)) return;
        if (id) seen.add(id);
        out.push(p);
    });
    return out;
}
function _rapImpactItems(eid, l2) {
    if (isEmpty(eid) || isEmpty(l2) || !graRapsData.length) return [];
    let eidCol = resolveCol(graRapsData, ["Audit Entity ID"]);
    if (!eidCol) return [];
    return graRapsData.filter(g => {
        if (String(g[eidCol]||"").trim() !== String(eid)) return false;
        let mapped = String(g["Mapped L2s"]||"").split(/[;\r\n]+/).map(s => s.trim());
        return mapped.indexOf(l2) >= 0;
    });
}

// Impact of Issues cell: one chip per source type colored by worst severity;
// expanded detail = the four existing renderer outputs (full evidence tables).
function renderImpactForCell(row, eid, l2) {
    let iag = _iagImpactItems(eid, l2);
    let ores = _oreImpactItems(eid, l2);
    let prsa = _prsaImpactItems(eid, l2);
    let raps = _rapImpactItems(eid, l2);
    if (!iag.length && !ores.length && !prsa.length && !raps.length) return "";

    const _ORE_CLASS_MAP = {
        "class a": "critical", "class b": "high",
        "class c": "medium",   "near miss": "low",
    };

    let summaryHtml = '<span class="impact-summary">';
    function chip(label, items, sevGetter, classMap) {
        if (!items.length) return;
        let sev = _worstImpactSeverity(items, sevGetter, classMap);
        summaryHtml += '<span class="signal-summary-chip signal-summary-chip-impact-' + sev + '">'
            + esc(label) + '<span class="count">×' + items.length + '</span></span>';
    }
    chip("IAG",  iag,  f => f["severity"]||f["Final Reportable Finding Risk Rating"]);
    chip("OREs", ores, o => o["Final Event Classification"], _ORE_CLASS_MAP);
    chip("PRSA", prsa, p => p["Issue Rating"]);
    chip("RAPs", raps, g => g["severity"]||"");
    summaryHtml += '<span class="signals-expand-hint">click to expand</span></span>';

    let detailHtml = '<div class="impact-detail">'
        + renderRelevantFindings(row, eid, l2)
        + renderRelevantOREs(eid, l2)
        + renderRelevantPRSA(eid, l2)
        + renderRelevantRAPs(eid, l2)
        + '<span class="signals-collapse-hint">click to collapse</span>'
        + '</div>';

    return { html: summaryHtml + detailHtml, tdClass: "cell-impact" };
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

    // Contradiction note: "Well Controlled" rating but an open Critical/High
    // IAG finding on this L2 — nudge the auditor to re-confirm the rating.
    let ratingText = String(baseline).split("(")[0].trim();
    if (/^well controlled/i.test(ratingText) && worstOpenIagSeverity(eid, l2)) {
        html += '<div class="ca-note">Review whether the ' + esc(ratingText)
            + ' rating above still reflects current state</div>';
    }

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
//   2. "Why this risk applies" -- key risks, source rationale, signals
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
    whyContent += renderKeyRiskDescriptions(detailRow, eid, l2);
    whyContent += renderSourceRationale(detailRow);
    whyContent += renderSignals(row["Additional Signals"], eid);
    if (whyContent) {
        html += '<div class="drill-supersection">Why this risk applies</div>'
            + '<div class="drill-section-inner">' + whyContent + '</div>';
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
        html += '<div class="drill-supersection">How it\u2019s controlled</div>'
            + '<div class="drill-section-inner">' + howContent + '</div>';
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

function renderHandoffsSection(legacyRow, eid) {
    let fromIds = _splitList(legacyRow["Hand-offs from Other Audit Entities"]).filter(x => !isAbsence(x));
    let toIds = _splitList(legacyRow["Hand-offs to Other Audit Entities"]).filter(x => !isAbsence(x));
    let hDesc = legacyRow["Hand-off Description"];
    if (fromIds.length === 0 && toIds.length === 0 && isAbsence(hDesc)) return "";

    let useExpander = Math.max(fromIds.length, toIds.length) > 10;

    function formatHandoffName(id) {
        let name = entityNameMap[id] || "";
        if (!id || isActiveEntity(id)) return esc(name);
        let status = getEntityStatus(id).trim() || "Inactive";
        return esc(name) + ' <span style="color: var(--gray); font-size: 12px;">(' + esc(status) + ')</span>';
    }
    function renderGroup(ids, label, keySuffix) {
        if (ids.length === 0) return "";
        let rows = ids.map(id => [esc(id), formatHandoffName(id)]);
        let tableHtml = buildTableHTML({
            id: "handoff-" + keySuffix + "-" + eid,
            headers: [{label: "ID", width: "90px"}, {label: "Name"}],
            rows: rows,
            wrap: true,
            tableClass: "handoff-table",
            minimal: true,
        });
        let headerText = label + " (" + ids.length + ")";
        if (useExpander) {
            return '<div class="handoff-group">' + mkExpander(false, headerText, tableHtml, "handoff:" + keySuffix + ":" + eid) + '</div>';
        }
        return '<div class="handoff-group">'
            + '<div class="handoff-col-label">' + headerText + '</div>'
            + tableHtml
            + '</div>';
    }

    let fromGroup = renderGroup(fromIds, "\u2190 From", "from");
    let toGroup = renderGroup(toIds, "To \u2192", "to");
    let gridHtml = '<div class="handoff-grid-wrapper"><div class="handoff-grid">' + fromGroup + toGroup + '</div></div>';
    let taggedIds = new Set([...fromIds, ...toIds]);
    let descHtml = renderHandoffDescription(hDesc, eid, taggedIds);
    return gridHtml + descHtml;
}

function annotateHandoffDesc(text, taggedIdSet) {
    const parts = [];
    let lastIdx = 0;
    const re = /\bAE-\d+\b/g;
    let m;
    while ((m = re.exec(text)) !== null) {
        if (m.index > lastIdx) parts.push(esc(text.substring(lastIdx, m.index)));
        const aeId = m[0];
        if (taggedIdSet.has(aeId)) {
            parts.push(esc(aeId));
        } else if (entityMeta && entityMeta[aeId]) {
            parts.push('<span class="ae-flag" '
                + 'title="Referenced in description but not in From/To handoff tables above \u2014 review whether handoff tagging is complete">'
                + esc(aeId) + '</span>');
        } else {
            parts.push('<span class="ae-flag" '
                + 'title="Not in this report \u2014 may be inactive, out of scope, or a typo">'
                + esc(aeId) + '</span>');
        }
        lastIdx = m.index + aeId.length;
    }
    if (lastIdx < text.length) parts.push(esc(text.substring(lastIdx)));
    return parts.join('');
}

function renderHandoffDescription(raw, eid, taggedIds) {
    if (isAbsence(raw)) return "";
    const text = String(raw);

    if (text.length <= 400) {
        return '<div class="handoff-desc">' + annotateHandoffDesc(text, taggedIds) + '</div>';
    }

    let cut = -1;
    for (let i = 400; i >= 200; i--) {
        if (text[i] === '.' && (text[i+1] === ' ' || text[i+1] === '\n' || i+1 === text.length)) {
            cut = i + 1;
            break;
        }
    }
    if (cut < 0) {
        cut = text.lastIndexOf(' ', 400);
        if (cut < 200) cut = 400;
    }

    const visible = text.substring(0, cut).trim();
    const hidden = text.substring(cut).trim();
    const tid = "handoff-desc-more-" + eid;

    return '<div class="handoff-desc">'
        + annotateHandoffDesc(visible, taggedIds)
        + '<span id="' + tid + '" style="display:none;"> '
        + annotateHandoffDesc(hidden, taggedIds)
        + '</span> '
        + '<a href="javascript:void(0)" class="overview-toggle" '
        + 'onclick="toggleOverview(\'' + tid + '\', this)">Show more</a>'
        + '</div>';
}

function renderAppsInventory(primaryIds, secondaryIds, eid) {
    if (!primaryIds.length && !secondaryIds.length) return "";
    let appById = {};
    applicationsInventory.forEach(a => { let k = String(a[INVENTORY_COLS.appId]||"").trim(); if (k) appById[k] = a; });

    let items = [];
    primaryIds.forEach(id => items.push({
        tier: "Primary", id, rec: appById[id], isKey: !!(eid && isKeyApp(eid, id)),
        sortKey: (appById[id] && appById[id][INVENTORY_COLS.appName]) || id
    }));
    secondaryIds.forEach(id => items.push({
        tier: "Secondary", id, rec: appById[id], isKey: !!(eid && isKeyApp(eid, id)),
        sortKey: (appById[id] && appById[id][INVENTORY_COLS.appName]) || id
    }));
    // Sort: key first within each tier (per audit procedure non-key apps
    // do not drive risk).
    items.sort((a, b) => {
        let ta = _tierRank[a.tier] ?? 9, tb = _tierRank[b.tier] ?? 9;
        if (ta !== tb) return ta - tb;
        if (a.isKey !== b.isKey) return a.isKey ? -1 : 1;
        return String(a.sortKey||"").localeCompare(String(b.sortKey||""));
    });

    // Key column: render the list of KPA IDs where this app is "key" for
    // the entity. Falls back to a solid green dot when no KPA attribution is
    // available (older outputs before KPA ID was ingested).
    let keyCell = (isKey, id) => {
        if (!isKey) return '';
        let kpas = eid ? keyAppKpas(eid, id) : [];
        if (!kpas.length) return '<span style="color:#1e7a3a;font-weight:700;">\u25cf</span>';
        return kpas.map(k => '<span class="id-chip id-chip-key">' + esc(k) + '</span>').join(' ');
    };
    let rows = items.map(r => {
        if (!r.rec) return [
            '<span class="meta">(not found in applications inventory)</span>',
            '\u2014', '\u2014', '\u2014', keyCell(r.isKey, r.id), esc(r.tier), esc(r.id),
        ];
        let rec = r.rec;
        return [
            esc(String(rec[INVENTORY_COLS.appName]||"")),
            makePill(rec[INVENTORY_COLS.appConfidence]||"", "severity"),
            makePill(rec[INVENTORY_COLS.appAvailability]||"", "severity"),
            makePill(rec[INVENTORY_COLS.appIntegrity]||"", "severity"),
            keyCell(r.isKey, r.id),
            esc(r.tier),
            esc(r.id),
        ];
    });

    let keyCount = items.filter(i => i.isKey).length;
    let keyCountText = keyCount > 0 ? ', \u25cf ' + keyCount + ' key' : '';
    return '<h4>Applications</h4>'
        + '<p class="meta">' + _plural(items.length, "application", "applications") + ' \u2014 ' + primaryIds.length + ' Primary, ' + secondaryIds.length + ' Secondary' + keyCountText + '</p>'
        + buildTableHTML({
            id: "inv-apps",
            headers: [
                {label: "Name",            noFilter: true},
                {label: "Confidentiality", noFilter: true},
                {label: "Availability",    noFilter: true},
                {label: "Integrity",       noFilter: true},
                {label: "Key",             noFilter: true},
                {label: "Tier",            noFilter: true},
                {label: "ID",              noFilter: true},
            ],
            rows: rows,
        });
}

function renderThirdPartiesInventory(primaryIds, secondaryIds, eid) {
    if (!primaryIds.length && !secondaryIds.length) return "";
    let tpById = {};
    thirdpartiesInventory.forEach(t => { let k = String(t[INVENTORY_COLS.tpId]||"").trim(); if (k) tpById[k] = t; });

    let items = [];
    primaryIds.forEach(id => items.push({
        tier: "Primary", id, rec: tpById[id], isKey: !!(eid && isKeyTp(eid, id)),
        sortKey: (tpById[id] && tpById[id][INVENTORY_COLS.tpName]) || id
    }));
    secondaryIds.forEach(id => items.push({
        tier: "Secondary", id, rec: tpById[id], isKey: !!(eid && isKeyTp(eid, id)),
        sortKey: (tpById[id] && tpById[id][INVENTORY_COLS.tpName]) || id
    }));
    items.sort((a, b) => {
        let ta = _tierRank[a.tier] ?? 9, tb = _tierRank[b.tier] ?? 9;
        if (ta !== tb) return ta - tb;
        if (a.isKey !== b.isKey) return a.isKey ? -1 : 1;
        return String(a.sortKey||"").localeCompare(String(b.sortKey||""));
    });

    let keyCell = (isKey, id) => {
        if (!isKey) return '';
        let kpas = eid ? keyTpKpas(eid, id) : [];
        if (!kpas.length) return '<span style="color:#1e7a3a;font-weight:700;">\u25cf</span>';
        return kpas.map(k => '<span class="id-chip id-chip-key">' + esc(k) + '</span>').join(' ');
    };
    let rows = items.map(r => {
        if (!r.rec) return [
            '<span class="meta">(not found in third parties inventory)</span>',
            '\u2014', keyCell(r.isKey, r.id), esc(r.tier), esc(r.id),
        ];
        let nm = r.rec[INVENTORY_COLS.tpName] || "";
        let risk = r.rec[INVENTORY_COLS.tpOverallRisk] || "";
        return [
            esc(String(nm)),
            makePill(risk, "severity"),
            keyCell(r.isKey, r.id),
            esc(r.tier),
            esc(r.id),
        ];
    });

    let keyCount = items.filter(i => i.isKey).length;
    let keyCountText = keyCount > 0 ? ', \u25cf ' + keyCount + ' key' : '';
    return '<h4>Third Parties</h4>'
        + '<p class="meta">' + _plural(items.length, "third party", "third parties") + ' \u2014 ' + primaryIds.length + ' Primary, ' + secondaryIds.length + ' Secondary' + keyCountText + '</p>'
        + buildTableHTML({
            id: "inv-tps",
            headers: [
                {label: "Name",         noFilter: true},
                {label: "Overall Risk", noFilter: true},
                {label: "Key",          noFilter: true},
                {label: "Tier",         noFilter: true},
                {label: "TLM ID",       noFilter: true},
            ],
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
            minimal: true,
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
            minimal: true,
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
            minimal: true,
        });
}

// Build the inventories expander header (count summary) + body HTML.
function renderInventoriesSection(legacyRow, eid) {
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
    // Subtle orphan warning: key IDs flagged in key risks but not present
    // in the entity PRIMARY/SECONDARY inventory columns.
    let ki = eid ? getKeyInv(eid) : null;
    if (ki && (ki.orphanApps.length || ki.orphanTps.length)) {
        let parts = [];
        if (ki.orphanApps.length) parts.push('<strong>' + ki.orphanApps.length + ' application' + (ki.orphanApps.length === 1 ? '' : 's') + '</strong> (' + ki.orphanApps.map(esc).join(', ') + ')');
        if (ki.orphanTps.length) parts.push('<strong>' + ki.orphanTps.length + ' third part' + (ki.orphanTps.length === 1 ? 'y' : 'ies') + '</strong> (' + ki.orphanTps.map(esc).join(', ') + ')');
        body += '<div class="banner banner-warn" style="margin-bottom:10px;">'
            + '<strong>Entity inventory gap:</strong> '
            + parts.join(' and ')
            + ' flagged as key in key risks but not in entity PRIMARY/SECONDARY inventory. Review whether the entity inventory is complete.'
            + '</div>';
    }
    body += renderAppsInventory(primaryApps, secondaryApps, eid);
    body += renderThirdPartiesInventory(primaryTPs, secondaryTPs, eid);
    body += renderModelsInventory(modelList);
    body += renderPoliciesInventory(policyList);
    body += renderLawsInventory(lawsApplic, lawsAdd);

    return {header, body};
}

// ==================== FILTERING ====================
let currentView = "entity";

function applyFilters() {
    if (currentView === "entity") renderEntityView();
    else if (currentView === "risk") renderRiskView();
}

function getFilteredAuditData(baseFilter) {
    let data = baseFilter || auditData;
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
    document.getElementById("sidebar-org-filters").style.display = name !== "entity" ? "block" : "none";
    if (name === "entity") renderEntityView();
    if (name === "risk") renderRiskView();
}

function switchEntityTab(name) {
    document.querySelectorAll(".sub-tab-content").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".sub-tab").forEach(t => t.classList.remove("active"));
    document.getElementById("entity-tab-" + name).classList.add("active");
    let idx = ["profile","legacy","source","trace"].indexOf(name);
    document.querySelectorAll(".sub-tab")[idx].classList.add("active");
}

// ==================== ENTITY VIEW ====================
function renderEntityView() {
    let eid = getTypeaheadValue("entity-select");
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
        let inner = renderHandoffsSection(legacyRow, eid);
        if (inner) {
            ctxHtml += '<div class="drill-section"><span class="label">Handoffs</span>' + inner + '</div>';
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
    let overviewCols = ["New L1","New L2","Status","Inherent Risk Rating","Legacy Source","Decision Basis","Additional Signals"];
    if (rows.length && rows[0].hasOwnProperty("Control Effectiveness Baseline")) overviewCols.push("Control Effectiveness Baseline");
    if (rows.length && rows[0].hasOwnProperty("Impact of Issues")) overviewCols.push("Impact of Issues");
    if (rows.length && rows[0].hasOwnProperty("Control Signals")) overviewCols.push("Control Signals");
    let profileRows = rows.map(r => overviewCols.map(c => {
        let v = r[c];
        if (c === "Status") return statusLabel(v);
        if (c === "Inherent Risk Rating") return isEmpty(v) ? "\u2014" : String(v);
        if (c === "New L2") {
            let cell = renderL2NameCell(r);
            return cell || (isEmpty(v) ? "" : String(v));
        }
        if (c === "Additional Signals") {
            let parsed = parseSignalsForRender(v);
            if (!parsed) return "";
            return { html: renderSignalsForCell(parsed, eid), tdClass: "cell-signals" };
        }
        if (c === "Decision Basis") {
            let cell = renderDecisionBasisCell(r, eid, r["New L2"]);
            return cell || (isEmpty(v) ? "" : String(v));
        }
        if (c === "Impact of Issues") {
            let cell = renderImpactForCell(r, eid, r["New L2"]);
            return cell || "";
        }
        return isEmpty(v) ? "" : String(v);
    }));
    let profileHeaderOverride = {"Inherent Risk Rating": "Legacy Rating"};
    let profileToolCols = new Set(["Status", "Decision Basis", "Additional Signals"]);
    // Columns that get the column-wide expand icon. Long-prose columns
    // the auditor needs to scan down the column at a glance.
    let profileExpandCols = new Set(["Decision Basis", "Additional Signals", "Impact of Issues"]);
    // Default widths: non-expand columns get compact fixed widths so
    // that expand columns (Decision Basis, Additional Signals, Impact
    // of Issues) share the remaining space generously.
    let profileWidths = {
        "New L1": "100px", "New L2": "140px", "Status": "90px",
        "Inherent Risk Rating": "100px", "Legacy Source": "100px",
        "Control Effectiveness Baseline": "130px", "Control Signals": "120px",
    };
    // Tag-based filtering: instead of showing every unique cell text
    // in the filter dropdown, extract individual chip labels so the
    // user can filter by tag type (e.g. "Keyword Match", "IAG", "App").
    let profileFilterChips = {
        "Decision Basis": ".decision-chip",
        "Additional Signals": ".signal-summary-chip",
        "Impact of Issues": ".signal-summary-chip",
    };
    let profileHeaders = overviewCols.map(c => ({
        label: profileHeaderOverride[c] || c,
        tool: profileToolCols.has(c),
        expand: profileExpandCols.has(c),
        width: profileWidths[c] || undefined,
        filterChips: profileFilterChips[c] || undefined,
    }));
    document.getElementById("entity-profile-host").innerHTML = buildTableHTML({
        id: "entity-profile-table",
        headers: profileHeaders,
        rows: profileRows,
    });

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
                    minimal: true,
                });
            } else { legacyHtml = "<p class='meta'>No legacy ratings found for this entity.</p>"; }
        } else { legacyHtml = "<p class='meta'>Legacy ratings data missing entity column.</p>"; }
    } else { legacyHtml = "<p class='meta'>No legacy ratings data in workbook.</p>"; }
    document.getElementById("entity-legacy-ratings").innerHTML = legacyHtml;

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
    let inv = renderInventoriesSection(legacyRow, eid);
    srcHtml += mkExpander(true, inv.header, inv.body, "src-inventories");

    // Key Risks
    let es = subRisksData.filter(s => String(s["entity_id"]||s["Audit Entity"]||s["Audit Entity ID"]||"").trim() === eid);
    let subHeader = 'Key Risks \u2014 ' + es.length + ' key risk' + (es.length === 1 ? "" : "s");
    let subBody = "";
    if (es.length) {
        let subRows = es.map(s => [
            esc(String(s["risk_id"]||s["Key Risk ID"]||"")),
            esc(String(s["risk_description"]||s["Key Risk Description"]||"").substring(0,200)),
            esc(String(s["legacy_l1"]||s["Level 1 Risk Category"]||"")),
            esc(String(s["key_risk_rating"]||s["Inherent Risk Rating"]||"")),
            esc(String(s["L2 Keyword Matches"]||s["Contributed To (keyword matches)"]||"")),
        ]);
        subBody = buildTableHTML({
            id: "src-subrisks-table",
            headers: [
                "Risk ID",
                {label: "Description", expand: true},
                "Legacy L1", "Rating",
                {label: "L2 Keyword Matches", tool: true},
            ],
            rows: subRows,
        });
    } else {
        subHeader = "Key Risks";
        subBody = "<p class='meta'>No key risk descriptions for this entity.</p>";
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
            '<span class="id-chip">' + esc(String(f["issue_id"]||f["Finding ID"]||"")) + '</span>',
            makePill(f["severity"]||f["Final Reportable Finding Risk Rating"]||"", "severity"),
            esc(String(f["status"]||f["Finding Status"]||"")),
            esc(String(f["issue_title"]||f["Finding Name"]||"")),
            esc(String(f["Finding Description"]||f["finding_description"]||"")),
            esc(String(f["l2_risk"]||f["Risk Dimension Categories"]||"")),
            esc(String(f["Mapping Status"]||"")),
        ]);
        iagBody += buildTableHTML({
            id: "src-iag-table",
            headers: [
                "Finding ID", "Severity", "Status", "Title",
                {label: "Description", expand: true},
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
                // Column order: ID, classification pill, status, title, then
                // remaining detail columns.
                let oreApproved = [
                    {k:"Event ID", idChip:true},
                    {k:"Final Event Classification", pill:"oreClass"},
                    {k:"Event Status"},
                    {k:"Event Title"},
                    {k:"Event Description", expand: true},
                    {k:"Mapped L2s", label:"Suggested L2s", tool:true},
                    {k:"Mapping Status", tool:true},
                ];
                let cols = oreApproved.filter(c => eo[0].hasOwnProperty(c.k));
                let oreHeaders = cols.map(c => ({
                    label: c.label || c.k,
                    tool: !!c.tool,
                    expand: !!c.expand,
                }));
                let oreRows = eo.map(o => cols.map(c => {
                    let raw = o[c.k] || "";
                    if (c.pill) return makePill(raw, c.pill);
                    if (c.idChip) return '<span class="id-chip">' + esc(String(raw)) + '</span>';
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
                // Column order: ID, rating pill, status, title, then remaining
                // PRSA detail columns.
                let prsaApproved = ["Issue ID", "Issue Rating", "Issue Status", "Issue Title", "Issue Description", "PRSA ID", "Control Title", "Process Title", "Control ID (PRSA)", "Other AEs With This PRSA", "Mapped L2s", "Mapping Status"];
                let prsaExpandCols = new Set(["Issue Description"]);
                let cols = prsaApproved.filter(c => ep[0].hasOwnProperty(c));
                let prsaHeaders = cols.map(c =>
                    prsaExpandCols.has(c) ? {label: c, expand: true} : c
                );
                let prsaRows = ep.map(p => cols.map(c => {
                    if (c === "Issue Rating") return makePill(p[c]||"", "severity");
                    if (c === "Issue ID") return '<span class="id-chip">' + esc(String(p[c]||"")) + '</span>';
                    return esc(String(p[c]||""));
                }));
                prsaBody += buildTableHTML({
                    id: "src-prsa-table",
                    headers: prsaHeaders,
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
                // Column order: ID, status, header (title), then detail.
                let graApproved = ["RAP ID", "RAP Status", "RAP Header", "BU Corrective Action Due Date", "RAP Details", "Related Exams and Findings", "GRA RAPS", "Mapped L2s", "Mapping Status"];
                let graExpandCols = new Set(["RAP Details"]);
                let cols = graApproved.filter(c => eg[0].hasOwnProperty(c));
                let graHeaders = cols.map(c =>
                    graExpandCols.has(c) ? {label: c, expand: true} : c
                );
                let graRows = eg.map(g => cols.map(c => {
                    if (c === "RAP ID") return '<span class="id-chip">' + esc(String(g[c]||"")) + '</span>';
                    return esc(String(g[c]||""));
                }));
                graBody += buildTableHTML({
                    id: "src-gra-table",
                    headers: graHeaders,
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
                let bmaRows = eb.map(b => cols.map(c => {
                    if (c === "Activity Instance ID") return '<span class="id-chip">' + esc(String(b[c]||"")) + '</span>';
                    return esc(String(b[c]||""));
                }));
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
    let l2 = getTypeaheadValue("risk-select");
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
    document.getElementById("risk-entity-host").innerHTML = buildTableHTML({
        id: "risk-entity-table",
        headers: [
            {label: "Entity ID",     type: "str"},
            {label: "Entity Name",   type: "str"},
            {label: "Audit Leader",  type: "str"},
            {label: "Rating",        type: "str"},
            {label: "Status",        type: "str"},
            {label: "Likelihood",    type: "num"},
            {label: "Impact",        type: "num"},
            {label: "Legacy Source", type: "str"},
            {label: "Decision Basis", type: "str", expand: true},
            {label: "Signals",        type: "str", expand: true},
        ],
        rows: tRows,
    });

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
            minimal: true,
        });
    } else { fHtml = "<p class='meta'>No IAG issues tagged to this L2 in the current scope.</p>"; }
    document.getElementById("risk-findings").innerHTML = fHtml;
}

// ==================== INITIALIZATION ====================
window.addEventListener("load", () => {
    // Entity typeahead
    const entityTA = makeTypeahead(
        "entity-select",
        "entity-typeahead-list",
        _buildEntityOptions,
        (val) => { renderEntityView(); }
    );
    if (entityTA) entityTA.rebuild();
    // Risk (L2) typeahead
    const riskTA = makeTypeahead(
        "risk-select",
        "risk-typeahead-list",
        () => l2Risks.map(l => ({ value: l, label: l })),
        (val) => { renderRiskView(); }
    );
    if (riskTA) riskTA.rebuild();
    let alSelect = document.getElementById("filter-al");
    auditLeaders.forEach(v => { let o = document.createElement("option"); o.value = v; o.text = v; alSelect.add(o); });
    let pgaSelect = document.getElementById("filter-pga");
    pgaList.forEach(v => { let o = document.createElement("option"); o.value = v; o.text = v; pgaSelect.add(o); });
    let teamSelect = document.getElementById("filter-team");
    coreTeams.forEach(v => { let o = document.createElement("option"); o.value = v; o.text = v; teamSelect.add(o); });
    renderEntityView();
    document.addEventListener("keydown", (e) => {
        if (e.key !== "T" || !e.shiftKey || e.ctrlKey || e.metaKey || e.altKey) return;
        const t = e.target;
        if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
        const btn = document.getElementById("sub-tab-trace");
        if (!btn) return;
        btn.style.display = (btn.style.display === "none") ? "" : "none";
    });
});
"""


def generate_html_report(excel_path: str, html_path: str):
    """Generate a self-contained HTML report from the transformer output Excel."""

    # Read sheets - same set as dashboard.py
    sheets = {}
    xls = pd.ExcelFile(excel_path)
    for name in ["Audit_Review", "Side_by_Side",
                 "Findings_Source", "Sub_Risks_Source",
                 "Source - Findings", "Source - Key Risks",
                 "Source - Legacy Data", "Source - OREs",
                 "Source - PRSA Issues",
                 "Source - BM Activities",
                 "Source - GRA RAPs",
                 "Legacy Ratings Lookup",
                 "Legacy_Ratings_Lookup",
                 "Key_Inventory"]:
        if name in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=name)
            if name == "Audit_Review":
                df = df.rename(columns={"Proposed Status": "Status",
                                        "Proposed Rating": "Inherent Risk Rating"})
            sheets[name] = df

    audit_df = sheets.get("Audit_Review", pd.DataFrame())
    detail_df = sheets.get("Side_by_Side", pd.DataFrame())
    # Support both old and new sheet names for findings/key risks
    findings_df = sheets.get("Source - Findings", sheets.get("Findings_Source", pd.DataFrame()))
    key_risks_df = sheets.get("Source - Key Risks", sheets.get("Sub_Risks_Source", pd.DataFrame()))
    ore_df = sheets.get("Source - OREs", pd.DataFrame())
    prsa_df = sheets.get("Source - PRSA Issues", pd.DataFrame())
    bma_df = sheets.get("Source - BM Activities", pd.DataFrame())
    gra_raps_df = sheets.get("Source - GRA RAPs", pd.DataFrame())
    legacy_ratings_df = sheets.get("Legacy Ratings Lookup", sheets.get("Legacy_Ratings_Lookup", pd.DataFrame()))
    legacy_df = sheets.get("Source - Legacy Data", pd.DataFrame())
    key_inventory_df = sheets.get("Key_Inventory", pd.DataFrame())

    # Convert Key_Inventory sheet into a JS-friendly dict:
    # {eid: {keyApps: [...], keyTps: [...], orphanApps: [...], orphanTps: [...]}}
    def _split_ids(raw):
        if raw is None or (isinstance(raw, float) and pd.isna(raw)):
            return []
        s = str(raw).strip()
        if not s or s.lower() in ("nan", "none"):
            return []
        return [p.strip() for p in s.split(";") if p.strip()]

    def _parse_kpa_json(raw):
        if raw is None or (isinstance(raw, float) and pd.isna(raw)):
            return {}
        s = str(raw).strip()
        if not s or s.lower() in ("nan", "none", "{}"):
            return {}
        try:
            return json.loads(s)
        except Exception:
            return {}

    key_inventory_dict = {}
    if not key_inventory_df.empty:
        for _, r in key_inventory_df.iterrows():
            key_inventory_dict[str(r["Entity ID"]).strip()] = {
                "keyApps": _split_ids(r.get("Key Apps", "")),
                "keyTps": _split_ids(r.get("Key TPs", "")),
                "orphanApps": _split_ids(r.get("Orphan Apps", "")),
                "orphanTps": _split_ids(r.get("Orphan TPs", "")),
                "keyAppsKpa": _parse_kpa_json(r.get("Key Apps KPA JSON", "")),
                "keyTpsKpa": _parse_kpa_json(r.get("Key TPs KPA JSON", "")),
            }

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

    # Pull Audit Entity Status from legacy_df (not merged into Audit_Review)
    if not legacy_df.empty and "Audit Entity ID" in legacy_df.columns and "Audit Entity Status" in legacy_df.columns:
        for _, r in legacy_df.drop_duplicates(subset=["Audit Entity ID"], keep="first").iterrows():
            eid = r["Audit Entity ID"]
            if pd.isna(eid) or str(eid).strip() == "":
                continue
            eid_str = str(eid)
            status_val = r["Audit Entity Status"]
            status_val = "" if pd.isna(status_val) else status_val
            if eid_str not in entity_meta:
                entity_meta[eid_str] = {}
            entity_meta[eid_str]["Audit Entity Status"] = status_val

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
    key_risks_json = _safe_json(_project_cols(key_risks_df, SUB_RISKS_COLS))
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
        .replace("__SUB_RISKS_JSON__", key_risks_json)
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
        .replace("__KEY_INVENTORY_JSON__", json.dumps(key_inventory_dict))
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
