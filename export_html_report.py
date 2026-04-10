"""
Static HTML Report Generator (AmEx Branded)
============================================
Reads the transformer's Excel output and generates a self-contained, brand-styled
HTML file that can be uploaded to SharePoint and opened in any browser.

Aligned with the Streamlit dashboard (dashboard.py) — same views, same data,
same drill-down logic.

Usage:
    python export_html_report.py                    # uses latest output
    python export_html_report.py path/to/output.xlsx  # specific file

Or called from the transformer:
    from export_html_report import generate_html_report
    generate_html_report(excel_path, html_path)
"""

import pandas as pd
import json
import sys
from pathlib import Path
from datetime import datetime

_PROJECT_ROOT = Path(__file__).parent


def _safe_json(df: pd.DataFrame) -> str:
    """Convert DataFrame to JSON string, handling NaN and special types."""
    return df.fillna("").to_json(orient="records")


def generate_html_report(excel_path: str, html_path: str):
    """Generate a self-contained HTML report from the transformer output Excel."""

    # Read sheets — same set as dashboard.py
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

    # Parse timestamp from filename
    stem = Path(excel_path).stem
    ts_str = stem.replace("transformed_risk_taxonomy_", "")
    try:
        dt = datetime.strptime(ts_str, "%m%d%Y%I%M%p")
        run_timestamp = dt.strftime("%B %d, %Y %I:%M %p").replace(" 0", " ")
    except ValueError:
        run_timestamp = ts_str

    # Embed data as JSON
    audit_json = _safe_json(audit_df)
    detail_json = _safe_json(detail_df)
    findings_json = _safe_json(findings_df)
    sub_risks_json = _safe_json(sub_risks_df)
    ore_json = _safe_json(ore_df)
    prsa_json = _safe_json(prsa_df)
    bma_json = _safe_json(bma_df)
    gra_raps_json = _safe_json(gra_raps_df)
    legacy_ratings_json = _safe_json(legacy_ratings_df)

    # Get unique values for filters
    entities = sorted(audit_df["Entity ID"].unique().tolist()) if "Entity ID" in audit_df.columns else []
    l2_risks = sorted(audit_df["New L2"].unique().tolist()) if "New L2" in audit_df.columns else []

    # Org filter values
    audit_leaders = sorted([str(x) for x in audit_df["Audit Leader"].dropna().unique() if str(x) != "nan"]) if "Audit Leader" in audit_df.columns else []
    pgas = sorted([str(x) for x in audit_df["PGA"].dropna().unique() if str(x) != "nan"]) if "PGA" in audit_df.columns else []
    core_teams = sorted([str(x) for x in audit_df["Core Audit Team"].dropna().unique() if str(x) != "nan"]) if "Core Audit Team" in audit_df.columns else []

    total_rows = len(audit_df)
    total_entities = audit_df["Entity ID"].nunique() if "Entity ID" in audit_df.columns else 0

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Risk Taxonomy Review</title>
<link href="https://fonts.googleapis.com/css2?family=Source+Sans+Pro:wght@300;400;600;700&family=Source+Code+Pro:wght@400;600&display=swap" rel="stylesheet">
<style>
/* ================================================================
   Streamlit-Inspired Visual Theme
   Matches the Streamlit dashboard's look & feel for familiarity
   ================================================================ */
:root {{
    --bg: #ffffff; --fg: #31333F; --bg2: #f0f2f6; --border: #e6e9ef;
    --accent: #ff4b4b; --primary: #ff4b4b; --blue: #1f77b4;
    --success-bg: #dff0d8; --success-border: #0e8a16; --success-fg: #0e5c2f;
    --warning-bg: #fff3cd; --warning-border: #ffad1f; --warning-fg: #664d03;
    --info-bg: #d1ecf1; --info-border: #0c5460; --info-fg: #0c5460;
    --error-bg: #f8d7da; --error-border: #ff4b4b; --error-fg: #842029;
    --gray: #808495; --gray-light: #bfc5d3;
    --row-alt: #f8f9fb; --hover-row: #eef1f8;
    --sidebar-bg: #f0f2f6;
    --font: "Source Sans Pro", sans-serif;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: var(--font); background: var(--bg); color: var(--fg); line-height: 1.6; font-size: 14px; }}

/* ---- Header bar ---- */
.report-header {{
    background: #262730; color: #fafafa; padding: 16px 32px;
    display: flex; align-items: center; gap: 16px; border-bottom: 1px solid #3d3d4e;
}}
.header-info h1 {{
    font-family: var(--font); font-size: 1.25em; font-weight: 700; color: #fafafa;
}}
.header-info .sub {{ color: rgba(250,250,250,0.5); font-size: 0.82em; margin-top: 2px; font-weight: 400; }}

/* ---- Layout ---- */
.wrap {{ margin: 0 auto; padding: 0; }}
.sidebar-layout {{ display: flex; gap: 0; min-height: calc(100vh - 60px); }}
.sidebar {{
    width: 260px; flex-shrink: 0; position: sticky; top: 0; max-height: calc(100vh - 60px); overflow-y: auto;
    padding: 24px 20px; background: var(--sidebar-bg); border-right: 1px solid var(--border);
}}
.main-content {{ flex: 1; min-width: 0; padding: 24px 32px; }}

/* ---- Headings ---- */
h2 {{
    margin: 28px 0 12px; color: var(--fg);
    font-family: var(--font); font-weight: 700; font-size: 1.25em;
    border-bottom: none; padding-bottom: 0;
}}
h3 {{ margin: 18px 0 8px; color: var(--fg); font-weight: 600; font-size: 1em; }}

/* ---- Sub-tabs (Streamlit st.tabs style) ---- */
.sub-tabs {{
    display: flex; gap: 0; border-bottom: 1px solid var(--border); margin-bottom: 20px;
}}
.sub-tab {{
    padding: 10px 20px; cursor: pointer; border: none;
    border-bottom: 2px solid transparent; background: transparent;
    color: var(--gray); font-weight: 400; font-size: 0.9em; transition: all 0.15s;
    font-family: var(--font);
}}
.sub-tab.active {{ color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }}
.sub-tab:hover {{ color: var(--fg); }}
.sub-tab-content {{ display: none; }}
.sub-tab-content.active {{ display: block; }}

/* ---- Tables (Streamlit dataframe style — truncated cells, resizable cols) ---- */
table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin: 8px 0; table-layout: fixed; }}
th {{
    background: var(--bg2); color: var(--fg); padding: 8px 12px; text-align: left;
    cursor: pointer; position: sticky; top: 0; user-select: none;
    font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px;
    border-bottom: 2px solid var(--border); overflow: hidden; text-overflow: ellipsis;
    white-space: nowrap; position: relative;
}}
th:hover {{ background: #e4e7ed; }}
th .col-resize {{
    position: absolute; right: 0; top: 0; bottom: 0; width: 5px;
    cursor: col-resize; z-index: 2;
}}
th .col-resize:hover, th .col-resize.active {{ background: var(--accent); opacity: 0.6; }}
td {{
    padding: 8px 12px; border-bottom: 1px solid var(--border); vertical-align: top;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    max-width: 0; cursor: default;
}}
td.cell-expanded {{
    white-space: normal; word-wrap: break-word; overflow: visible;
    background: #fffde7; outline: 2px solid #ffcc02; z-index: 1; position: relative;
}}
tr:nth-child(even) {{ background: var(--row-alt); }}
tr:hover {{ background: var(--hover-row); }}
.table-wrap {{
    max-height: 600px; overflow: auto; border: 1px solid var(--border);
    border-radius: 8px; background: var(--bg);
}}

/* ---- Form controls (Streamlit widget style) ---- */
select {{
    padding: 6px 12px; border: 1px solid var(--border); border-radius: 6px;
    background: var(--bg); color: var(--fg); font-size: 14px; font-family: var(--font);
    min-width: 200px; outline: none; transition: border-color 0.2s;
}}
select:focus {{ border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }}
.filters {{ display: flex; gap: 15px; flex-wrap: wrap; align-items: center; margin: 10px 0 15px; }}
.filters label {{ font-weight: 600; font-size: 13px; color: var(--fg); display: flex; flex-direction: column; gap: 4px; }}

/* ---- Sidebar controls (Streamlit sidebar style) ---- */
.sidebar h3 {{
    font-size: 15px; margin: 0 0 4px; font-weight: 700; color: var(--fg);
}}
.sidebar label {{
    display: block; font-weight: 600; font-size: 13px; color: var(--fg);
    margin-bottom: 4px;
}}
.sidebar select {{ width: 100%; margin-bottom: 14px; font-size: 13px; padding: 7px 10px; }}
.sidebar .divider {{ border-top: 1px solid var(--border); margin: 16px 0; }}
.view-radio {{ display: flex; flex-direction: column; gap: 2px; margin: 8px 0; }}
.view-radio label {{
    font-weight: 400; cursor: pointer; display: flex; align-items: center; gap: 8px;
    padding: 6px 8px; border-radius: 6px; transition: background 0.15s; font-size: 13px;
}}
.view-radio label:hover {{ background: #e4e7ed; }}
.view-radio input {{ accent-color: var(--accent); }}
.filter-group {{ margin-bottom: 8px; }}
.filter-group select {{ width: 100%; }}
.filter-group label {{ font-size: 12px; }}
.checkbox-group {{ display: flex; flex-direction: column; gap: 2px; }}
.checkbox-group label {{
    font-weight: 400; font-size: 12px; cursor: pointer;
    display: flex; align-items: center; gap: 6px;
    padding: 4px 6px; border-radius: 4px;
}}
.checkbox-group label:hover {{ background: #e4e7ed; }}

/* ---- Banners (Streamlit st.warning/success/info/error style) ---- */
.banner {{
    padding: 16px 20px; border-radius: 8px; margin: 12px 0; font-size: 14px;
    line-height: 1.5;
}}
.banner-warn {{
    background: var(--warning-bg); border-left: 4px solid var(--warning-border);
    color: var(--warning-fg); border-radius: 0 8px 8px 0;
}}
.banner-ok {{
    background: var(--success-bg); border-left: 4px solid var(--success-border);
    color: var(--success-fg); border-radius: 0 8px 8px 0;
}}
.banner-info {{
    background: var(--info-bg); border-left: 4px solid var(--info-border);
    color: var(--info-fg); border-radius: 0 8px 8px 0;
}}
.banner-danger {{
    background: var(--error-bg); border-left: 4px solid var(--error-border);
    color: var(--error-fg); border-radius: 0 8px 8px 0;
}}

/* ---- Metrics (Streamlit st.metric style) ---- */
.metrics {{ display: flex; gap: 12px; margin: 16px 0; flex-wrap: wrap; }}
.metric-card {{
    background: var(--bg); border: 1px solid var(--border); border-radius: 8px;
    padding: 14px 20px; min-width: 130px; flex: 1;
}}
.metric-card .value {{
    font-size: 2em; font-weight: 700; color: var(--fg); line-height: 1.1;
    font-family: var(--font);
}}
.metric-card .label {{
    font-size: 13px; color: var(--gray); margin-top: 2px; font-weight: 400;
}}

/* ---- Expanders (Streamlit st.expander style) ---- */
.expander {{ border: 1px solid var(--border); border-radius: 8px; margin: 8px 0; overflow: hidden; }}
.expander-header {{
    padding: 12px 16px; cursor: pointer; font-weight: 400; font-size: 14px;
    display: flex; justify-content: space-between; align-items: center;
    transition: background 0.15s;
}}
.expander-header:hover {{ background: var(--bg2); }}
.expander-body {{
    display: none; padding: 16px 20px; border-top: 1px solid var(--border);
    font-size: 14px; background: var(--bg);
}}
.expander.open .expander-body {{ display: block; }}
.expander-arrow {{ transition: transform 0.2s; color: var(--gray); font-size: 12px; }}
.expander.open .expander-arrow {{ transform: rotate(90deg); }}

/* ---- Status boxes (Streamlit callout style) ---- */
.info-box {{
    background: var(--info-bg); border-left: 4px solid var(--info-border);
    padding: 14px 18px; border-radius: 0 8px 8px 0; margin: 10px 0;
    color: var(--info-fg); font-size: 14px;
}}
.success-box {{
    background: var(--success-bg); border-left: 4px solid var(--success-border);
    padding: 14px 18px; border-radius: 0 8px 8px 0; margin: 10px 0;
    color: var(--success-fg); font-size: 14px;
}}
.warning-box {{
    background: var(--warning-bg); border-left: 4px solid var(--warning-border);
    padding: 14px 18px; border-radius: 0 8px 8px 0; margin: 10px 0;
    color: var(--warning-fg); font-size: 14px;
}}
.error-box {{
    background: var(--error-bg); border-left: 4px solid var(--error-border);
    padding: 14px 18px; border-radius: 0 8px 8px 0; margin: 10px 0;
    color: var(--error-fg); font-size: 14px;
}}

/* ---- Signals ---- */
.signal {{ padding: 3px 0; font-size: 14px; }}
.signal-control {{ color: #842029; font-weight: 600; }}
.signal-app {{ color: #b45309; }}
.signal-aux {{ color: var(--blue); }}

/* ---- Misc ---- */
blockquote {{
    border-left: 3px solid var(--gray-light); padding: 10px 18px; margin: 10px 0;
    background: var(--bg2); font-style: italic; font-size: 14px; border-radius: 0 8px 8px 0;
    color: #555;
}}
.rating-bar {{
    font-family: "Source Code Pro", "SF Mono", "Cascadia Code", monospace;
    font-size: 13px; line-height: 1.8;
}}
.meta {{ color: var(--gray); font-size: 13px; }}
.entity-context {{ margin-bottom: 14px; }}
.chart-container {{ max-width: 700px; margin: 16px 0; }}
.md-table {{ width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 13px; table-layout: fixed; }}
.md-table th {{
    background: var(--bg2); color: var(--fg); padding: 10px 12px; text-align: left;
    font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px;
    border-bottom: 2px solid var(--border);
}}
.md-table td {{ padding: 10px 12px; border-bottom: 1px solid var(--border); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 0; }}
.md-table td.cell-expanded {{ white-space: normal; word-wrap: break-word; overflow: visible; background: #fffde7; outline: 2px solid #ffcc02; }}
.md-table tr:nth-child(even) {{ background: var(--row-alt); }}
.divider {{ border-top: 1px solid var(--border); margin: 24px 0; }}
.tab-content {{ display: none; }}
.tab-content.active {{ display: block; }}

/* ---- Footer ---- */
.report-footer {{
    background: var(--bg2); border-top: 1px solid var(--border);
    padding: 16px 32px; display: flex; justify-content: space-between; align-items: center;
    margin-top: 40px;
}}
.report-footer .ft {{ color: var(--gray); font-size: 12px; line-height: 1.6; }}

/* ---- Streamlit-style caption ---- */
p.meta, span.meta {{ font-weight: 400; }}
strong {{ font-weight: 600; }}
</style>
</head>
<body>

<!-- ==================== HEADER (Streamlit-style toolbar) ==================== -->
<div class="report-header">
    <div class="header-info">
        <h1>&#128203; Risk Taxonomy Review</h1>
        <div class="sub">Last Run: {run_timestamp} &middot; {total_entities} entities &middot; {total_rows} total mappings</div>
    </div>
</div>

<div class="wrap">
<div class="sidebar-layout">

<!-- ==================== SIDEBAR ==================== -->
<div class="sidebar" id="sidebar">
    <h3>&#128203; Risk Taxonomy Review</h3>
    <div class="meta">Last Run: {run_timestamp}</div>
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
        <div class="sub-tab active" onclick="switchEntityTab('profile')">Risk Profile</div>
        <div class="sub-tab" onclick="switchEntityTab('legacy')">Legacy Profile</div>
        <div class="sub-tab" onclick="switchEntityTab('drill')">Drill-Down</div>
        <div class="sub-tab" onclick="switchEntityTab('trace')">Traceability</div>
        <div class="sub-tab" onclick="switchEntityTab('source')">Source Data</div>
    </div>

    <div id="entity-tab-profile" class="sub-tab-content active">
        <div class="table-wrap"><table id="entity-profile-table"></table></div>
    </div>
    <div id="entity-tab-legacy" class="sub-tab-content">
        <div class="meta" style="margin-bottom:10px;">Legacy pillar ratings from the most recent assessment cycle.</div>
        <div id="entity-legacy-ratings"></div>
    </div>
    <div id="entity-tab-drill" class="sub-tab-content">
        <div class="meta" style="margin-bottom:10px;">Expand any L2 to see evidence and context.</div>
        <div id="entity-drilldown"></div>
    </div>
    <div id="entity-tab-trace" class="sub-tab-content">
        <div id="entity-traceability"></div>
    </div>
    <div id="entity-tab-source" class="sub-tab-content">
        <div id="entity-sources"></div>
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
    <div class="ft">Generated by Risk Taxonomy Transformer on {run_timestamp}.<br>
    For interactive features, contact the QA team for Streamlit dashboard access.</div>
</div>

<script>
// ==================== EMBEDDED DATA ====================
const auditData = {audit_json};
const detailData = {detail_json};
const findingsData = {findings_json};
const subRisksData = {sub_risks_json};
const oreData = {ore_json};
const prsaData = {prsa_json};
const bmaData = {bma_json};
const graRapsData = {gra_raps_json};
const legacyRatingsData = {legacy_ratings_json};
const entities = {json.dumps(entities)};
const l2Risks = {json.dumps(l2_risks)};
const auditLeaders = {json.dumps(audit_leaders)};
const pgaList = {json.dumps(pgas)};
const coreTeams = {json.dumps(core_teams)};

// ==================== STATUS CONFIG ====================
const STATUS_CONFIG = {{
    "Applicability Undetermined": {{"icon": "\\u26A0\\uFE0F", "sort": 0}},
    "Needs Review": {{"icon": "\\ud83d\\udd0e", "sort": 1}},
    "No Evidence Found \\u2014 Verify N/A": {{"icon": "\\ud83d\\udd36", "sort": 2}},
    "Applicable": {{"icon": "\\u2705", "sort": 3}},
    "Not Applicable": {{"icon": "\\u2B1C", "sort": 4}},
    "Not Assessed": {{"icon": "\\ud83d\\udd35", "sort": 5}},
}};
const RATING_RANK = {{"Low":1,"Medium":2,"High":3,"Critical":4,"low":1,"medium":2,"high":3,"critical":4}};
// Build entity-to-name mapping from audit data
const entityNameMap = {{}};
auditData.forEach(r => {{
    if (r["Entity ID"] && r["Entity Name"] && !entityNameMap[r["Entity ID"]]) {{
        entityNameMap[r["Entity ID"]] = r["Entity Name"];
    }}
}});
const RANK_LABEL = {{1:"Low",2:"Medium",3:"High",4:"Critical"}};

// ==================== HELPERS ====================
function isEmpty(v) {{ return v === null || v === undefined || v === "" || v === "nan" || v === "None" || (typeof v === "number" && isNaN(v)); }}
function esc(s) {{
    if (!s) return "";
    let d = document.createElement("div");
    d.textContent = String(s);
    return d.innerHTML;
}}
function icon(status) {{
    let cfg = STATUS_CONFIG[status];
    return cfg ? cfg.icon : "\\u2753";
}}
function statusLabel(status) {{ return icon(status) + " " + status; }}
function ratingBar(v) {{
    if (isEmpty(v)) return "\\u2014";
    let n = parseInt(v);
    let labels = {{1:"Low",2:"Medium",3:"High",4:"Critical"}};
    return "\\u2588".repeat(n) + "\\u2591".repeat(4-n) + " " + n + " (" + (labels[n]||"") + ")";
}}
function basePillar(s) {{ return String(s || "").split(" (also")[0].trim(); }}
function methodToStatus(m) {{
    m = String(m);
    if (m.includes("llm_confirmed_na")) return "Not Applicable";
    if (m.includes("source_not_applicable")) return "Not Applicable";
    if (m.includes("evaluated_no_evidence")) return "No Evidence Found \\u2014 Verify N/A";
    if (m.includes("no_evidence_all_candidates")) return "Applicability Undetermined";
    if (m.includes("true_gap_fill") || m.includes("gap_fill")) return "Not Assessed";
    if (m.includes("direct") || m.includes("evidence_match") || m.includes("llm_override") || m.includes("issue_confirmed") || m.includes("dedup")) return "Applicable";
    return "Needs Review";
}}

function sortTable(tableId, col, type) {{
    let table = document.getElementById(tableId);
    let rows = Array.from(table.querySelectorAll("tbody tr"));
    let asc = table.dataset.sortCol === String(col) && table.dataset.sortDir === "asc";
    rows.sort((a, b) => {{
        let va = a.cells[col].textContent.trim();
        let vb = b.cells[col].textContent.trim();
        if (type === "num") {{ va = parseFloat(va) || 0; vb = parseFloat(vb) || 0; }}
        if (va < vb) return asc ? 1 : -1;
        if (va > vb) return asc ? -1 : 1;
        return 0;
    }});
    table.dataset.sortCol = String(col);
    table.dataset.sortDir = asc ? "desc" : "asc";
    let tbody = table.querySelector("tbody");
    rows.forEach(r => tbody.appendChild(r));
}}

function makeTable(id, headers, rows, types) {{
    let html = "<thead><tr>";
    headers.forEach((h, i) => {{
        let t = (types && types[i]) || "str";
        html += `<th onclick="sortTable('${{id}}',${{i}},'${{t}}')">${{h}} \\u25B4\\u25BE<span class="col-resize" onmousedown="startResize(event)"></span></th>`;
    }});
    html += "</tr></thead><tbody>";
    rows.forEach(r => {{
        html += "<tr>" + r.map(c => `<td>${{c}}</td>`).join("") + "</tr>";
    }});
    html += "</tbody>";
    document.getElementById(id).innerHTML = html;
}}

// ==================== CELL CLICK-TO-EXPAND ====================
document.addEventListener("click", function(e) {{
    let td = e.target.closest("td");
    if (!td) return;
    // Don't expand if clicking inside an expander body or on a link
    if (td.closest(".expander-body") || e.target.tagName === "A") return;
    td.classList.toggle("cell-expanded");
}});

// ==================== COLUMN RESIZE ====================
let _resizeCol = null, _resizeStartX = 0, _resizeStartW = 0;
function startResize(e) {{
    e.stopPropagation();
    e.preventDefault();
    let th = e.target.parentElement;
    _resizeCol = th;
    _resizeStartX = e.pageX;
    _resizeStartW = th.offsetWidth;
    e.target.classList.add("active");
    document.addEventListener("mousemove", doResize);
    document.addEventListener("mouseup", stopResize);
}}
function doResize(e) {{
    if (!_resizeCol) return;
    let w = Math.max(40, _resizeStartW + (e.pageX - _resizeStartX));
    _resizeCol.style.width = w + "px";
}}
function stopResize(e) {{
    if (_resizeCol) {{
        let handle = _resizeCol.querySelector(".col-resize");
        if (handle) handle.classList.remove("active");
    }}
    _resizeCol = null;
    document.removeEventListener("mousemove", doResize);
    document.removeEventListener("mouseup", stopResize);
}}

function toggleExpander(el) {{
    let exp = el.closest(".expander");
    let wasOpen = exp.classList.contains("open");
    exp.classList.toggle("open");
    // Lazy render: build body content on first open
    if (!wasOpen && exp.dataset.lazy) {{
        let bodyEl = exp.querySelector(".expander-body");
        let fn = window["_lazy_" + exp.dataset.lazy];
        if (fn && !exp.dataset.rendered) {{
            bodyEl.innerHTML = fn();
            exp.dataset.rendered = "1";
        }}
    }}
}}

function makeBanner(containerId, total, undetermined, assumedNA, contextLabel) {{
    let action = undetermined + assumedNA;
    let el = document.getElementById(containerId);
    if (action > 0) {{
        el.innerHTML = `<div class="banner banner-warn"><strong>${{action}} of ${{total}} items</strong> ${{contextLabel ? "for " + esc(contextLabel) + " " : ""}}need your review &mdash; ${{undetermined}} applicability undetermined, ${{assumedNA}} no evidence found (verify N/A).</div>`;
    }} else {{
        el.innerHTML = `<div class="banner banner-ok"><strong>All ${{total}} items</strong> ${{contextLabel ? "for " + esc(contextLabel) + " " : ""}}have proposed applicability \\u2014 review to confirm.</div>`;
    }}
}}

function renderSignals(signals) {{
    if (isEmpty(signals)) return "";
    return String(signals).split(/\\n| \\| /).filter(s => s.trim()).map(s => {{
        let cls = "signal";
        let prefix = "\\u2139\\uFE0F";
        let lower = s.toLowerCase();
        if (lower.includes("well controlled") || lower.includes("review whether")) {{ cls = "signal signal-control"; prefix = "\\ud83d\\udea8"; }}
        else if (lower.includes("[app]") || lower.includes("application") || lower.includes("engagement")) {{ cls = "signal signal-app"; prefix = "\\ud83d\\udcce"; }}
        else if (lower.includes("[aux]") || lower.includes("auxiliary")) {{ cls = "signal signal-aux"; prefix = "\\ud83d\\udccc"; }}
        else if (lower.includes("[cross-boundary]") || lower.includes("outside normal")) {{ cls = "signal signal-aux"; prefix = "\\ud83d\\udd00"; }}
        return `<div class="${{cls}}">${{prefix}} ${{esc(s.trim())}}</div>`;
    }}).join("");
}}

// ==================== CONTROL ASSESSMENT (matches dashboard) ====================
function renderControlAssessment(row) {{
    let cs = row["Control Signals"] || "";
    let baseline = row["Control Effectiveness Baseline"] || "";
    let impact = row["Impact of Issues"] || "";
    if (isEmpty(cs) && isEmpty(baseline) && isEmpty(impact)) return "";
    let html = '<div class="divider"></div><p><strong>Control Assessment</strong></p>';
    if (!isEmpty(cs)) html += `<div class="error-box">\\ud83d\\udea8 ${{esc(cs)}}</div>`;
    if (!isEmpty(baseline)) html += `<div class="info-box">${{esc(baseline)}}</div>`;
    if (!isEmpty(impact)) {{
        let impStr = String(impact).trim();
        if (impStr.toLowerCase() === "no open items") {{
            html += `<div class="success-box">No open items</div>`;
        }} else {{
            let cats = impStr.split(/\\r?\\n/);
            cats.forEach(c => {{
                c = c.trim();
                if (c && c.toLowerCase() !== "nan") html += `<div>\\u2022 ${{esc(c)}}</div>`;
            }});
        }}
    }}
    return html;
}}

// ==================== DRILL-DOWN RENDERERS — status-specific (matches dashboard) ====================
function renderDrilldownApplicable(row, detailRow) {{
    let html = "";
    let basis = row["Decision Basis"] || "";
    if (!isEmpty(basis)) html += `<div class="success-box"><strong>Decision Basis</strong><br>${{esc(basis)}}</div>`;
    if (detailRow) {{
        let rat = detailRow["source_rationale"] || "";
        if (!isEmpty(rat)) html += `<p><strong>Source Rationale Text</strong></p><blockquote>${{esc(rat)}}</blockquote>`;
    }}
    html += renderSignals(row["Additional Signals"]);
    html += renderRatings(row, detailRow);
    html += renderControlAssessment(row);
    return html;
}}

function renderDrilldownAssumedNA(row, detailRow) {{
    let html = "";
    let basis = row["Decision Basis"] || "";
    if (!isEmpty(basis)) html += `<div class="info-box"><strong>Decision Basis</strong><br>${{esc(basis)}}</div>`;
    if (detailRow) {{
        let rat = detailRow["source_rationale"] || "";
        if (!isEmpty(rat)) html += `<p><strong>Source Rationale Text</strong></p><blockquote>${{esc(rat)}}</blockquote>`;
    }}
    html += renderSignals(row["Additional Signals"]);
    html += renderControlAssessment(row);
    return html;
}}

function renderDrilldownUndetermined(row, detailRow, entityDetailRows) {{
    let html = "";
    let legacySource = String(row["Legacy Source"] || "");
    if (entityDetailRows && !isEmpty(legacySource)) {{
        let bp = basePillar(legacySource);
        let matched = entityDetailRows.filter(d =>
            String(d["source_legacy_pillar"]||"").includes(bp) &&
            !String(d["method"]||"").includes("no_evidence_all_candidates") &&
            !String(d["method"]||"").includes("evaluated_no_evidence")
        );
        if (matched.length) {{
            html += `<p><strong>Other L2s from ${{esc(bp)}} that DID match:</strong></p>`;
            matched.forEach(m => {{ html += `<div>\\u2022 \\u2705 ${{esc(m["new_l2"])}}</div>`; }});
        }}
    }}
    let basis = row["Decision Basis"] || "";
    if (!isEmpty(basis)) html += `<div class="warning-box"><strong>Decision Basis</strong><br>${{esc(basis)}}</div>`;
    if (detailRow) {{
        let rat = detailRow["source_rationale"] || "";
        if (!isEmpty(rat)) html += `<p><strong>Source Rationale Text</strong></p><blockquote>${{esc(rat)}}</blockquote>`;
    }}
    html += renderSignals(row["Additional Signals"]);
    html += renderRatings(row, detailRow);
    html += renderControlAssessment(row);
    return html;
}}

function renderDrilldownInformational(row) {{
    let html = `<span class="meta">${{esc(row["Decision Basis"] || "\\u2014")}}</span>`;
    html += renderSignals(row["Additional Signals"]);
    html += renderControlAssessment(row);
    return html;
}}

function renderDrilldownDispatch(row, detailRow, entityDetailRows) {{
    let status = row["Status"] || "";
    if (status === "No Evidence Found \\u2014 Verify N/A") return renderDrilldownAssumedNA(row, detailRow);
    if (status === "Applicability Undetermined") return renderDrilldownUndetermined(row, detailRow, entityDetailRows);
    if (status === "Applicable") return renderDrilldownApplicable(row, detailRow);
    return renderDrilldownInformational(row);
}}

function renderRatings(row, detailRow) {{
    let lk = row["Likelihood"];
    if (isEmpty(lk)) return "";
    let html = "";
    // Check if this row has a proposed rating (non-direct mappings may have blank ratings)
    let proposedRating = row["Inherent Risk Rating"];
    if (isEmpty(proposedRating)) {{
        html += `<div class="info-box">Not proposed \\u2014 this is a non-direct mapping. The legacy rating is preserved in Source Rating for reference.</div>`;
        return html;
    }}
    let irrLabel = null;
    if (detailRow) irrLabel = detailRow["inherent_risk_rating_label"];
    if (isEmpty(irrLabel)) irrLabel = proposedRating;
    html += `<p><strong>Proposed Inherent Risk Rating: ${{isEmpty(irrLabel) ? "\\u2014" : esc(String(irrLabel))}}</strong></p>`;
    html += `<div class="rating-bar">Likelihood: ${{ratingBar(lk)}}</div>`;
    let impacts = [["Financial", row["Impact - Financial"]], ["Reputational", row["Impact - Reputational"]],
                  ["Consumer Harm", row["Impact - Consumer Harm"]], ["Regulatory", row["Impact - Regulatory"]]];
    let valid = impacts.filter(([,v]) => !isEmpty(v));
    if (valid.length) {{
        let maxI = Math.max(...valid.map(([,v]) => parseInt(v)));
        let breakdown = valid.map(([l,v]) => l+"="+parseInt(v)).join(", ");
        html += `<div class="rating-bar">Overall Impact: ${{ratingBar(maxI)}} \\u2190 max of: ${{breakdown}}</div>`;
    }}
    let controls = [["IAG Control Effectiveness", row["IAG Control Effectiveness"]],
                   ["Aligned Assurance Rating", row["Aligned Assurance Rating"]],
                   ["Management Awareness Rating", row["Management Awareness Rating"]]];
    let validC = controls.filter(([,v]) => !isEmpty(v));
    if (validC.length) {{
        html += `<p><strong>Control Ratings</strong> <em>(starting point)</em></p>`;
        validC.forEach(([l,v]) => {{ html += `<div class="rating-bar">${{l}}: ${{ratingBar(v)}}</div>`; }});
    }}
    return html;
}}

// ==================== FILTERING ====================
let currentView = "entity";

function getSelectedStatuses() {{
    let checked = [];
    document.querySelectorAll("#status-checkboxes input:checked").forEach(cb => checked.push(cb.value));
    return checked;
}}

function applyFilters() {{
    if (currentView === "entity") renderEntityView();
    else if (currentView === "risk") renderRiskView();
}}

function getFilteredAuditData(baseFilter) {{
    let data = baseFilter || auditData;
    let statuses = getSelectedStatuses();
    if (statuses.length > 0) {{
        data = data.filter(r => statuses.includes(r["Status"]));
    }}
    if (currentView !== "entity") {{
        let al = document.getElementById("filter-al").value;
        let pga = document.getElementById("filter-pga").value;
        let team = document.getElementById("filter-team").value;
        if (al) data = data.filter(r => String(r["Audit Leader"]) === al);
        if (pga) data = data.filter(r => String(r["PGA"]) === pga);
        if (team) data = data.filter(r => String(r["Core Audit Team"]) === team);
    }}
    return data;
}}

// ==================== VIEW SWITCHING ====================
function switchView(name) {{
    currentView = name;
    document.querySelectorAll(".tab-content").forEach(t => t.classList.remove("active"));
    document.getElementById("tab-" + name).classList.add("active");
    document.getElementById("sidebar-entity-select").style.display = name === "entity" ? "block" : "none";
    document.getElementById("sidebar-risk-select").style.display = name === "risk" ? "block" : "none";
    document.getElementById("sidebar-status-filter").style.display = "block";
    document.getElementById("sidebar-org-filters").style.display = name !== "entity" ? "block" : "none";
    if (name === "entity") renderEntityView();
    if (name === "risk") renderRiskView();
}}

function switchEntityTab(name) {{
    document.querySelectorAll(".sub-tab-content").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".sub-tab").forEach(t => t.classList.remove("active"));
    document.getElementById("entity-tab-" + name).classList.add("active");
    let idx = ["profile","legacy","drill","trace","source"].indexOf(name);
    document.querySelectorAll(".sub-tab")[idx].classList.add("active");
}}

// ==================== ENTITY VIEW ====================
function renderEntityView() {{
    let eid = document.getElementById("entity-select").value;
    if (!eid) return;
    let baseRows = auditData.filter(r => r["Entity ID"] === eid);
    let rows = getFilteredAuditData(baseRows);
    if (!rows.length) {{
        document.getElementById("entity-title").innerHTML = `<h2 style="border:none;margin-top:0;">Entity: ${{esc(eid)}}</h2>`;
        document.getElementById("entity-banner").innerHTML = '<div class="banner banner-info">No rows match the current filters.</div>';
        return;
    }}
    let first = rows[0];
    let undetermined = rows.filter(r => r["Status"] === "Applicability Undetermined").length;
    let assumedNA = rows.filter(r => r["Status"] === "No Evidence Found \\u2014 Verify N/A").length;

    document.getElementById("entity-title").innerHTML = `<h2 style="border:none;margin-top:0;">Entity: ${{esc(eid)}}</h2>`;
    makeBanner("entity-banner", rows.length, undetermined, assumedNA, eid);

    // Unmapped findings banner
    let unmappedHtml = "";
    let eidColF = findingsData.length > 0 ? (findingsData[0].hasOwnProperty("entity_id") ? "entity_id" : "Audit Entity ID") : "";
    if (eidColF) {{
        let ef = findingsData.filter(f => String(f[eidColF]||"").trim() === eid);
        let unmapped = ef.filter(f => String(f["Disposition"]||"").startsWith("Filtered") && String(f["Disposition"]||"").toLowerCase().includes("unmappable"));
        if (unmapped.length) {{
            let legacyCats = new Set();
            unmapped.forEach(f => {{
                let d = String(f["Disposition"]||"");
                let ps = d.indexOf("("), pe = d.indexOf(")");
                if (ps !== -1 && pe !== -1) d.substring(ps+1, pe).split(";").forEach(c => {{ c = c.trim(); if (c) legacyCats.add(c); }});
            }});
            let catList = legacyCats.size ? Array.from(legacyCats).sort().join(", ") : "legacy risk categories";
            unmappedHtml = `<div class="banner banner-warn">This entity has <strong>${{unmapped.length}} IAG issue(s)</strong> tagged to legacy risk categories (${{esc(catList)}}) that could not be mapped to a specific L2 risk. These are not reflected in any L2 row below. See <strong>Source Data &gt; IAG Issues</strong> for details.</div>`;
        }}
    }}
    document.getElementById("unmapped-findings-banner").innerHTML = unmappedHtml;

    // Context
    let ctxHtml = '<div class="entity-context">';
    if (!isEmpty(first["Entity Name"])) ctxHtml += `<h3>${{esc(first["Entity Name"])}}</h3>`;
    if (!isEmpty(first["Entity Overview"])) ctxHtml += `<p class="meta">${{esc(first["Entity Overview"])}}</p>`;
    let meta = [];
    if (!isEmpty(first["Audit Leader"])) meta.push("Audit Leader: " + first["Audit Leader"]);
    if (!isEmpty(first["PGA"])) meta.push("PGA: " + first["PGA"]);
    if (meta.length) ctxHtml += `<p class="meta">${{meta.join(" \\u00B7 ")}}</p>`;
    ctxHtml += "</div><div class='divider'></div>";
    document.getElementById("entity-context").innerHTML = ctxHtml;

    // Sort
    let statusOrder = {{}};
    Object.keys(STATUS_CONFIG).forEach(s => statusOrder[s] = STATUS_CONFIG[s].sort);
    rows.sort((a,b) => {{
        let sa = statusOrder[a["Status"]]??99, sb = statusOrder[b["Status"]]??99;
        if (sa !== sb) return sa - sb;
        let ra = RATING_RANK[a["Inherent Risk Rating"]]||0, rb = RATING_RANK[b["Inherent Risk Rating"]]||0;
        return rb - ra;
    }});

    let entityDetail = detailData.filter(d => String(d["entity_id"]) === String(eid));

    // --- Risk Profile tab ---
    let overviewCols = ["New L1","New L2","Status","Inherent Risk Rating","Confidence","Legacy Source","Decision Basis","Additional Signals"];
    if (rows.length && rows[0].hasOwnProperty("Control Effectiveness Baseline")) overviewCols.push("Control Effectiveness Baseline");
    if (rows.length && rows[0].hasOwnProperty("Impact of Issues")) overviewCols.push("Impact of Issues");
    if (rows.length && rows[0].hasOwnProperty("Control Signals")) overviewCols.push("Control Signals");
    let profileRows = rows.map(r => overviewCols.map(c => {{
        let v = r[c];
        if (c === "Status") return statusLabel(v);
        if (c === "Inherent Risk Rating") return isEmpty(v) ? "\\u2014" : String(v);
        return isEmpty(v) ? "" : String(v);
    }}));
    makeTable("entity-profile-table", overviewCols, profileRows);

    // --- Legacy Profile tab ---
    let legacyHtml = "";
    if (legacyRatingsData.length) {{
        let eidCol = legacyRatingsData[0].hasOwnProperty("Entity ID") ? "Entity ID" : (legacyRatingsData[0].hasOwnProperty("Audit Entity ID") ? "Audit Entity ID" : null);
        if (eidCol) {{
            let lr = legacyRatingsData.filter(r => String(r[eidCol]||"").trim() === eid);
            if (lr.length) {{
                let cols = Object.keys(lr[0]).filter(c => !isEmpty(lr[0][c]) || lr.some(r => !isEmpty(r[c])));
                legacyHtml += '<div class="table-wrap"><table><thead><tr>' + cols.map(c => `<th>${{esc(c)}}</th>`).join("") + '</tr></thead><tbody>';
                lr.forEach(r => {{ legacyHtml += '<tr>' + cols.map(c => `<td>${{esc(String(r[c]||""))}}</td>`).join("") + '</tr>'; }});
                legacyHtml += "</tbody></table></div>";
            }} else {{ legacyHtml = "<p class='meta'>No legacy ratings found for this entity.</p>"; }}
        }} else {{ legacyHtml = "<p class='meta'>Legacy ratings data missing entity column.</p>"; }}
    }} else {{ legacyHtml = "<p class='meta'>No legacy ratings data in workbook.</p>"; }}
    document.getElementById("entity-legacy-ratings").innerHTML = legacyHtml;

    // --- Drill-Down tab ---
    let ddHtml = "";
    rows.forEach(r => {{
        let l2 = r["New L2"]||"";
        let status = r["Status"]||"";
        let irr = r["Inherent Risk Rating"]||"";
        let label = icon(status) + " " + (r["New L1"]||"") + " / " + l2 + " \\u00B7 " + status;
        if (!isEmpty(irr) && irr !== "Not Applicable" && irr !== "\\u2014") label += " \\u00B7 " + irr;
        let detail = detailData.find(d => String(d["entity_id"])===eid && d["new_l2"]===l2);
        let body = renderDrilldownDispatch(r, detail, entityDetail);
        let ef = findingsData.filter(f => {{
            let fEid = String(f["entity_id"]||f["Audit Entity ID"]||"");
            let fL2 = String(f["l2_risk"]||f["Mapped To L2(s)"]||f["Risk Dimension Categories"]||"");
            return fEid === eid && fL2.includes(l2);
        }});
        if (ef.length) {{
            body += "<p><strong>Relevant IAG Issues</strong></p>";
            ef.forEach(f => {{
                body += `<div>\\u2022 ${{f["issue_id"]||f["Finding ID"]||""}}: ${{f["issue_title"]||f["Finding Name"]||""}} (${{f["severity"]||""}}, ${{f["status"]||f["Finding Status"]||""}})</div>`;
            }});
        }}
        if (detail) {{
            let pillar = basePillar(detail["source_legacy_pillar"]||"");
            if (!isEmpty(pillar)) {{
                let es = subRisksData.filter(s => {{
                    let sEid = String(s["entity_id"]||s["Audit Entity"]||s["Audit Entity ID"]||"");
                    let sL1 = String(s["legacy_l1"]||s["Level 1 Risk Category"]||"");
                    return sEid === eid && sL1 === pillar;
                }});
                if (es.length) {{
                    body += "<p><strong>Relevant Sub-Risk Descriptions</strong></p>";
                    es.forEach(s => {{
                        let desc = String(s["risk_description"]||s["Key Risk Description"]||"").substring(0,200);
                        body += `<div>\\u2022 ${{s["risk_id"]||s["Key Risk ID"]||""}}: ${{desc}}</div>`;
                    }});
                }}
            }}
        }}
        ddHtml += `<div class="expander"><div class="expander-header" onclick="toggleExpander(this)">
            <span>${{label}}</span><span class="expander-arrow">\\u25B6</span>
        </div><div class="expander-body">${{body}}</div></div>`;
    }});
    document.getElementById("entity-drilldown").innerHTML = ddHtml;

    // --- Traceability tab ---
    let traceHtml = "";
    if (entityDetail.length) {{
        traceHtml += "<h3>Multi-Mapping Fan-Out</h3>";
        let pillars = [...new Set(entityDetail.map(d => basePillar(d["source_legacy_pillar"]||"")))].filter(p => p && p !== "nan" && p !== "None" && p !== "Findings").sort();
        pillars.forEach(pillar => {{
            let pr = entityDetail.filter(d => String(d["source_legacy_pillar"]||"").includes(pillar));
            if (pr.length <= 1) return;
            let rawR = pr.map(d => d["source_risk_rating_raw"]).filter(x => !isEmpty(x));
            let rStr = rawR.length ? String(rawR[0]) : "unknown";
            let statusCounts = {{}};
            pr.forEach(p => {{
                let s = methodToStatus(String(p["method"]||""));
                statusCounts[s] = (statusCounts[s]||0) + 1;
            }});
            let parts = [];
            Object.keys(STATUS_CONFIG).forEach(s => {{
                if (statusCounts[s]) parts.push(statusCounts[s] + " " + STATUS_CONFIG[s].icon);
            }});
            let label = "\\ud83d\\udcc2 " + esc(pillar) + " (rated " + esc(rStr) + ") \\u2192 " + parts.join(", ");
            let body = "";
            pr.forEach(p => {{
                let s = methodToStatus(String(p["method"]||""));
                let ic = STATUS_CONFIG[s] ? STATUS_CONFIG[s].icon : "?";
                body += `<div>${{ic}} <strong>${{esc(p["new_l2"])}}</strong> \\u2014 ${{esc(s)}}</div>`;
            }});
            traceHtml += `<div class="expander"><div class="expander-header" onclick="toggleExpander(this)">
                <span>${{label}}</span><span class="expander-arrow">\\u25B6</span>
            </div><div class="expander-body">${{body}}</div></div>`;
        }});

        let dedupRows = entityDetail.filter(d => String(d["source_legacy_pillar"]||"").includes("also:"));
        if (dedupRows.length) {{
            traceHtml += "<h3>Convergence</h3>";
            dedupRows.forEach(dr => {{
                let src = String(dr["source_legacy_pillar"]||"");
                let primary = src.split(" (also:")[0].trim();
                let also = [];
                let rem = src;
                while (rem.includes("(also:")) {{
                    let s = rem.indexOf("(also:") + 6;
                    let e = rem.indexOf(")", s);
                    if (e === -1) break;
                    also.push(rem.substring(s, e).trim());
                    rem = rem.substring(e + 1);
                }}
                let r = dr["source_risk_rating_raw"];
                let rStr = isEmpty(r) ? "no rating" : String(r);
                traceHtml += `<div><strong>${{esc(dr["new_l2"])}}</strong> \\u2190 ${{esc([primary, ...also].join(" + "))}} \\u2192 kept ${{esc(rStr)}}</div>`;
            }});
        }}
    }} else {{
        traceHtml = '<p class="meta">No traceability data available.</p>';
    }}
    document.getElementById("entity-traceability").innerHTML = traceHtml;

    // --- Source Data tab ---
    let srcHtml = "";

    // IAG Issues
    srcHtml += "<h3>IAG Issues</h3>";
    let efAll = findingsData.filter(f => String(f["entity_id"]||f["Audit Entity ID"]||"").trim() === eid);
    if (efAll.length) {{
        srcHtml += `<p class="meta">${{efAll.length}} IAG issue(s)</p>`;
        srcHtml += '<div class="table-wrap"><table><thead><tr><th>Finding ID</th><th>L2 Risk</th><th>Severity</th><th>Status</th><th>Title</th><th>Disposition</th></tr></thead><tbody>';
        efAll.forEach(f => {{
            srcHtml += `<tr><td>${{f["issue_id"]||f["Finding ID"]||""}}</td><td>${{f["l2_risk"]||f["Risk Dimension Categories"]||""}}</td>
                <td>${{f["severity"]||f["Final Reportable Finding Risk Rating"]||""}}</td><td>${{f["status"]||f["Finding Status"]||""}}</td>
                <td>${{f["issue_title"]||f["Finding Name"]||""}}</td><td>${{f["Disposition"]||""}}</td></tr>`;
        }});
        srcHtml += "</tbody></table></div>";
    }} else {{ srcHtml += "<p class='meta'>No IAG issues for this entity.</p>"; }}

    // OREs
    srcHtml += "<div class='divider'></div><h3>Operational Risk Events (OREs)</h3>";
    if (oreData.length) {{
        let oreEidCol = oreData[0].hasOwnProperty("entity_id") ? "entity_id" : (oreData[0].hasOwnProperty("Audit Entity (Operational Risk Events)") ? "Audit Entity (Operational Risk Events)" : (oreData[0].hasOwnProperty("Audit Entity ID") ? "Audit Entity ID" : null));
        if (oreEidCol) {{
            let eo = oreData.filter(o => String(o[oreEidCol]||"").trim() === eid);
            if (eo.length) {{
                srcHtml += `<p class="meta">${{eo.length}} ORE(s)</p>`;
                let cols = Object.keys(eo[0]).filter(c => !isEmpty(eo[0][c]) || eo.some(r => !isEmpty(r[c])));

                srcHtml += '<div class="table-wrap"><table><thead><tr>' + cols.map(c => `<th>${{esc(c)}}</th>`).join("") + '</tr></thead><tbody>';
                eo.forEach(o => {{ srcHtml += '<tr>' + cols.map(c => `<td>${{esc(String(o[c]||""))}}</td>`).join("") + '</tr>'; }});
                srcHtml += "</tbody></table></div>";
            }} else {{ srcHtml += "<p class='meta'>No OREs for this entity.</p>"; }}
        }} else {{ srcHtml += "<p class='meta'>ORE data missing entity ID column.</p>"; }}
    }} else {{ srcHtml += "<p class='meta'>No ORE data in workbook.</p>"; }}

    // PRSA Issues
    srcHtml += "<div class='divider'></div><h3>PRSA Issues</h3>";
    if (prsaData.length) {{
        let prsaEidCol = prsaData[0].hasOwnProperty("AE ID") ? "AE ID" : (prsaData[0].hasOwnProperty("Audit Entity") ? "Audit Entity" : (prsaData[0].hasOwnProperty("Audit Entity ID") ? "Audit Entity ID" : null));
        if (prsaEidCol) {{
            let ep = prsaData.filter(p => String(p[prsaEidCol]||"").trim() === eid);
            if (ep.length) {{
                srcHtml += `<p class="meta">${{ep.length}} PRSA record(s)</p>`;
                let cols = Object.keys(ep[0]).filter(c => !isEmpty(ep[0][c]) || ep.some(r => !isEmpty(r[c])));

                srcHtml += '<div class="table-wrap"><table><thead><tr>' + cols.map(c => `<th>${{esc(c)}}</th>`).join("") + '</tr></thead><tbody>';
                ep.forEach(p => {{ srcHtml += '<tr>' + cols.map(c => `<td>${{esc(String(p[c]||""))}}</td>`).join("") + '</tr>'; }});
                srcHtml += "</tbody></table></div>";
            }} else {{ srcHtml += "<p class='meta'>No PRSA data for this entity.</p>"; }}
        }} else {{ srcHtml += "<p class='meta'>PRSA data missing entity column.</p>"; }}
    }} else {{ srcHtml += "<p class='meta'>No PRSA data in workbook.</p>"; }}

    // GRA RAPs
    srcHtml += "<div class='divider'></div><h3>GRA RAPs (Regulatory Findings)</h3>";
    if (graRapsData.length) {{
        let graEidCol = graRapsData[0].hasOwnProperty("Audit Entity ID") ? "Audit Entity ID" : null;
        if (graEidCol) {{
            let eg = graRapsData.filter(g => String(g[graEidCol]||"").trim() === eid);
            if (eg.length) {{
                srcHtml += `<p class="meta">${{eg.length}} RAP(s)</p>`;
                let cols = Object.keys(eg[0]).filter(c => !isEmpty(eg[0][c]) || eg.some(r => !isEmpty(r[c])));

                srcHtml += '<div class="table-wrap"><table><thead><tr>' + cols.map(c => `<th>${{esc(c)}}</th>`).join("") + '</tr></thead><tbody>';
                eg.forEach(g => {{ srcHtml += '<tr>' + cols.map(c => `<td>${{esc(String(g[c]||""))}}</td>`).join("") + '</tr>'; }});
                srcHtml += "</tbody></table></div>";
            }} else {{ srcHtml += "<p class='meta'>No GRA RAPs for this entity.</p>"; }}
        }} else {{ srcHtml += "<p class='meta'>GRA RAPs data missing entity column.</p>"; }}
    }} else {{ srcHtml += "<p class='meta'>No GRA RAPs data in workbook.</p>"; }}

    // BM Activities
    srcHtml += "<div class='divider'></div><h3>Business Monitoring Activities</h3>";
    if (bmaData.length) {{
        let bmaEidCol = bmaData[0].hasOwnProperty("Related Audit Entity") ? "Related Audit Entity" : (bmaData[0].hasOwnProperty("Audit Entity ID") ? "Audit Entity ID" : null);
        if (bmaEidCol) {{
            let eb = bmaData.filter(b => String(b[bmaEidCol]||"").trim() === eid);
            if (eb.length) {{
                srcHtml += `<p class="meta">${{eb.length}} BMA instance(s)</p>`;
                let cols = Object.keys(eb[0]).filter(c => !isEmpty(eb[0][c]) || eb.some(r => !isEmpty(r[c])));

                srcHtml += '<div class="table-wrap"><table><thead><tr>' + cols.map(c => `<th>${{esc(c)}}</th>`).join("") + '</tr></thead><tbody>';
                eb.forEach(b => {{ srcHtml += '<tr>' + cols.map(c => `<td>${{esc(String(b[c]||""))}}</td>`).join("") + '</tr>'; }});
                srcHtml += "</tbody></table></div>";
            }} else {{ srcHtml += "<p class='meta'>No BM Activities for this entity.</p>"; }}
        }} else {{ srcHtml += "<p class='meta'>BMA data missing entity column.</p>"; }}
    }} else {{ srcHtml += "<p class='meta'>No BM Activities data in workbook.</p>"; }}

    // Sub-Risks
    srcHtml += "<div class='divider'></div><h3>Sub-Risks</h3>";
    let es = subRisksData.filter(s => String(s["entity_id"]||s["Audit Entity"]||s["Audit Entity ID"]||"").trim() === eid);
    if (es.length) {{
        srcHtml += `<p class="meta">${{es.length}} sub-risk(s)</p>`;
        srcHtml += '<div class="table-wrap"><table><thead><tr><th>Risk ID</th><th>Description</th><th>L1 Category</th><th>Rating</th><th>Contributed To</th></tr></thead><tbody>';
        es.forEach(s => {{
            srcHtml += `<tr><td>${{s["risk_id"]||s["Key Risk ID"]||""}}</td>
                <td>${{String(s["risk_description"]||s["Key Risk Description"]||"").substring(0,200)}}</td>
                <td>${{s["legacy_l1"]||s["Level 1 Risk Category"]||""}}</td>
                <td>${{s["sub_risk_rating"]||s["Inherent Risk Rating"]||""}}</td>
                <td>${{s["Contributed To (keyword matches)"]||""}}</td></tr>`;
        }});
        srcHtml += "</tbody></table></div>";
    }} else {{ srcHtml += "<p class='meta'>No sub-risk descriptions for this entity.</p>"; }}

    document.getElementById("entity-sources").innerHTML = srcHtml;
}}

// ==================== RISK CATEGORY VIEW ====================
function renderRiskView() {{
    let l2 = document.getElementById("risk-select").value;
    if (!l2) return;
    let baseRows = auditData.filter(r => r["New L2"] === l2);
    let rows = getFilteredAuditData(baseRows);
    if (!rows.length) {{
        document.getElementById("risk-title").innerHTML = `<h2 style="border:none;margin-top:0;">Risk Category: ${{esc(l2)}}</h2>`;
        document.getElementById("risk-banner").innerHTML = '<div class="banner banner-info">No rows match the current filters.</div>';
        document.getElementById("risk-metrics").innerHTML = "";
        return;
    }}

    let l1Vals = [...new Set(rows.map(r => r["New L1"]).filter(x => !isEmpty(x)))];
    let l1Label = l1Vals.length ? l1Vals[0] : "";
    let titleHtml = `<h2 style="border:none;margin-top:0;">Risk Category: ${{esc(l2)}}</h2>`;
    if (l1Label) titleHtml += `<div class="meta">L1: ${{esc(l1Label)}} \\u00B7 ${{new Set(rows.map(r=>r["Entity ID"])).size}} entities in scope</div>`;
    document.getElementById("risk-title").innerHTML = titleHtml;

    let undetermined = rows.filter(r => r["Status"] === "Applicability Undetermined").length;
    let assumedNA = rows.filter(r => r["Status"] === "No Evidence Found \\u2014 Verify N/A").length;
    makeBanner("risk-banner", rows.length, undetermined, assumedNA, l2);

    // Summary metrics
    let totalEntities = new Set(rows.map(r => r["Entity ID"])).size;
    let applicableMask = rows.filter(r => r["Status"] === "Applicable");
    let isAI = r => String(r["Decision Basis"]||"").startsWith("AI review");
    let evidenceEntities = new Set(applicableMask.filter(r => !isAI(r)).map(r => r["Entity ID"])).size;
    let aiEntities = new Set(applicableMask.filter(r => isAI(r)).map(r => r["Entity ID"])).size;
    let applicableEntities = new Set(applicableMask.map(r => r["Entity ID"])).size;
    let pctApp = totalEntities ? (applicableEntities / totalEntities * 100).toFixed(0) : 0;
    document.getElementById("risk-metrics").innerHTML = `
        <div class="metric-card"><div class="value">${{totalEntities}}</div><div class="label">Total Entities</div></div>
        <div class="metric-card"><div class="value">${{evidenceEntities}}</div><div class="label">Evidence-Based</div></div>
        <div class="metric-card"><div class="value">${{aiEntities}}</div><div class="label">AI-Proposed</div></div>
        <div class="metric-card"><div class="value">${{pctApp}}%</div><div class="label">% Applicable</div></div>`;

    let statusOrder = {{}};
    Object.keys(STATUS_CONFIG).forEach(s => statusOrder[s] = STATUS_CONFIG[s].sort);
    rows.sort((a,b) => {{
        let ra = RATING_RANK[a["Inherent Risk Rating"]]||0, rb = RATING_RANK[b["Inherent Risk Rating"]]||0;
        if (rb !== ra) return rb - ra;
        return (statusOrder[a["Status"]]||9) - (statusOrder[b["Status"]]||9);
    }});
    let tRows = rows.map(r => [
        r["Entity ID"]||"", r["Entity Name"]||"", r["Audit Leader"]||"",
        isEmpty(r["Inherent Risk Rating"]) ? "\\u2014" : r["Inherent Risk Rating"],
        statusLabel(r["Status"]),
        isEmpty(r["Likelihood"]) ? "\\u2014" : r["Likelihood"],
        isEmpty(r["Overall Impact"]) ? "\\u2014" : r["Overall Impact"],
        r["Legacy Source"]||"", r["Decision Basis"]||"",
        isEmpty(r["Additional Signals"]) ? "" : r["Additional Signals"]
    ]);
    makeTable("risk-entity-table",
        ["Entity ID","Entity Name","Audit Leader","Rating","Status","Likelihood","Impact","Legacy Source","Decision Basis","Signals"],
        tRows, ["str","str","str","str","str","num","num","str","str","str"]);

    let ratingCounts = {{"Critical":0,"High":0,"Medium":0,"Low":0,"Not Applicable":0,"No Rating":0}};
    rows.forEach(r => {{
        let irr = r["Inherent Risk Rating"];
        if (isEmpty(irr)) ratingCounts["No Rating"]++;
        else if (ratingCounts.hasOwnProperty(irr)) ratingCounts[irr]++;
        else ratingCounts["No Rating"]++;
    }});
    let chartLabels = Object.keys(ratingCounts).filter(k => ratingCounts[k] > 0);
    let chartColors = {{"Critical":"#dc3545","High":"#e8923c","Medium":"#ffc107","Low":"#28a745","Not Applicable":"#6c757d","No Rating":"#adb5bd"}};
    let maxVal = Math.max(...chartLabels.map(k => ratingCounts[k]), 1);
    let barHtml = '<div style="display:flex;flex-direction:column;gap:6px;">';
    chartLabels.forEach(k => {{
        let v = ratingCounts[k];
        let pct = (v / maxVal * 100).toFixed(0);
        let color = chartColors[k] || "#ccc";
        barHtml += `<div style="display:flex;align-items:center;gap:8px;">
            <div style="width:110px;text-align:right;font-size:12px;font-weight:600;color:var(--fg);white-space:nowrap;">${{k}}</div>
            <div style="flex:1;background:var(--bg2);border-radius:4px;height:22px;overflow:hidden;">
                <div style="width:${{pct}}%;background:${{color}};height:100%;border-radius:4px;min-width:${{v > 0 ? '2px' : '0'}};"></div>
            </div>
            <div style="width:30px;font-size:12px;font-weight:600;color:var(--fg);">${{v}}</div>
        </div>`;
    }});
    barHtml += '</div>';
    document.getElementById("concentration-chart").innerHTML = barHtml;

    // Per-entity drill-down
    let ddHtml = "";
    rows.forEach(r => {{
        let eid2 = r["Entity ID"]||"";
        let status = r["Status"]||"";
        let irr = r["Inherent Risk Rating"]||"";
        let ename = r["Entity Name"]||"";
        let parts = [icon(status) + " " + eid2];
        if (!isEmpty(ename)) parts.push(ename);
        parts.push(status);
        if (!isEmpty(irr) && irr !== "Not Applicable") parts.push(irr);
        let label = parts.join(" \\u00B7 ");
        let detail = detailData.find(d => String(d["entity_id"])===eid2 && d["new_l2"]===l2);
        let entityDetailRows = detailData.filter(d => String(d["entity_id"]) === String(eid2));

        let body = '<div class="entity-context">';
        if (!isEmpty(ename)) body += `<strong>${{esc(ename)}}</strong><br>`;
        if (!isEmpty(r["Entity Overview"])) body += `<span class="meta">${{esc(r["Entity Overview"])}}</span><br>`;
        let meta2 = [];
        if (!isEmpty(r["Audit Leader"])) meta2.push("AL: " + esc(r["Audit Leader"]));
        if (!isEmpty(r["PGA"])) meta2.push("PGA: " + esc(r["PGA"]));
        if (meta2.length) body += `<span class="meta">${{meta2.join(" \\u00B7 ")}}</span>`;
        body += "</div><hr style='border:none;border-top:1px solid var(--border);margin:8px 0'>";
        body += renderDrilldownDispatch(r, detail, entityDetailRows);
        let ef = findingsData.filter(f => {{
            let fEid = String(f["entity_id"]||f["Audit Entity ID"]||"");
            let fL2 = String(f["l2_risk"]||f["Mapped To L2(s)"]||f["Risk Dimension Categories"]||"");
            return fEid === eid2 && fL2.includes(l2);
        }});
        if (ef.length) {{
            body += "<p><strong>Relevant IAG Issues</strong></p>";
            ef.forEach(f => {{
                body += `<div>\\u2022 ${{f["issue_id"]||f["Finding ID"]||""}}: ${{f["issue_title"]||f["Finding Name"]||""}} (${{f["severity"]||""}}, ${{f["status"]||f["Finding Status"]||""}})</div>`;
            }});
        }}
        if (detail) {{
            let pillar = basePillar(detail["source_legacy_pillar"]||"");
            if (!isEmpty(pillar)) {{
                let esr = subRisksData.filter(s => {{
                    let sEid = String(s["entity_id"]||s["Audit Entity"]||s["Audit Entity ID"]||"");
                    let sL1 = String(s["legacy_l1"]||s["Level 1 Risk Category"]||"");
                    return sEid === eid2 && sL1 === pillar;
                }});
                if (esr.length) {{
                    body += "<p><strong>Relevant Sub-Risk Descriptions</strong></p>";
                    esr.forEach(s => {{
                        let desc = String(s["risk_description"]||s["Key Risk Description"]||"").substring(0,200);
                        body += `<div>\\u2022 ${{s["risk_id"]||s["Key Risk ID"]||""}}: ${{desc}}</div>`;
                    }});
                }}
            }}
        }}
        ddHtml += `<div class="expander"><div class="expander-header" onclick="toggleExpander(this)">
            <span>${{label}}</span><span class="expander-arrow">\\u25B6</span>
        </div><div class="expander-body">${{body}}</div></div>`;
    }});
    document.getElementById("risk-drilldown").innerHTML = ddHtml;

    // IAG Issues for this L2
    let allFindings = findingsData.filter(f => {{
        let fL2 = String(f["l2_risk"]||f["Mapped To L2(s)"]||f["Risk Dimension Categories"]||"");
        return fL2.includes(l2);
    }});
    let inScope = new Set(rows.map(r => String(r["Entity ID"])));
    allFindings = allFindings.filter(f => inScope.has(String(f["entity_id"]||f["Audit Entity ID"]||"")));
    let fHtml = "";
    if (allFindings.length) {{
        let fEntities = new Set(allFindings.map(f => f["entity_id"]||f["Audit Entity ID"]));
        fHtml = `<div class="banner banner-info"><strong>${{allFindings.length}} IAG issues</strong> across <strong>${{fEntities.size}} entities</strong> tagged to this L2.</div>`;
        fHtml += '<div class="table-wrap"><table><thead><tr><th>Entity</th><th>Finding ID</th><th>Severity</th><th>Status</th><th>Title</th></tr></thead><tbody>';
        allFindings.forEach(f => {{
            fHtml += `<tr><td>${{f["entity_id"]||f["Audit Entity ID"]||""}}</td><td>${{f["issue_id"]||f["Finding ID"]||""}}</td>
                <td>${{f["severity"]||""}}</td><td>${{f["status"]||f["Finding Status"]||""}}</td><td>${{f["issue_title"]||f["Finding Name"]||""}}</td></tr>`;
        }});
        fHtml += "</tbody></table></div>";
    }} else {{ fHtml = "<p class='meta'>No IAG issues tagged to this L2 in the current scope.</p>"; }}
    document.getElementById("risk-findings").innerHTML = fHtml;
}}

// ==================== INITIALIZATION ====================
window.addEventListener("load", () => {{
    let eSelect = document.getElementById("entity-select");
    entities.forEach(e => {{ let o = document.createElement("option"); o.value = e; o.text = entityNameMap[e] ? e + " - " + entityNameMap[e] : e; eSelect.add(o); }});
    let rSelect = document.getElementById("risk-select");
    l2Risks.forEach(l => {{ let o = document.createElement("option"); o.value = l; o.text = l; rSelect.add(o); }});
    let alSelect = document.getElementById("filter-al");
    auditLeaders.forEach(v => {{ let o = document.createElement("option"); o.value = v; o.text = v; alSelect.add(o); }});
    let pgaSelect = document.getElementById("filter-pga");
    pgaList.forEach(v => {{ let o = document.createElement("option"); o.value = v; o.text = v; pgaSelect.add(o); }});
    let teamSelect = document.getElementById("filter-team");
    coreTeams.forEach(v => {{ let o = document.createElement("option"); o.value = v; o.text = v; teamSelect.add(o); }});
    renderEntityView();
}});
</script>
</body>
</html>"""

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