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
                  "Source - GRA RAPs"]:
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
<style>
/* ================================================================
   AmEx Brand Palette
   Bright Blue: #006FCF  |  Deep Blue: #00175A  |  Neutrals
   Per Communication Guidelines (June 2018) — informational use
   ================================================================ */
:root {{
    --bg: #ffffff; --fg: #333333; --bg2: #F7F8F9; --border: #E0E0E0;
    --accent: #006FCF; --deep-blue: #00175A;
    --success: #28a745; --warning: #ffc107; --danger: #dc3545;
    --orange: #e8923c; --info: #006FCF; --gray: #8E9BAE;
    --row-alt: #F7F8F9; --hover-row: #EBF4FF;
}}
@media (prefers-color-scheme: dark) {{
    :root {{
        --bg: #0A1628; --fg: #E0E4E8; --bg2: #0F1D33; --border: #1B3A6B;
        --row-alt: #0D1A2E; --hover-row: #12264A; --deep-blue: #4A9FE8;
        --accent: #4AADFF; --gray: #9EADBE;
    }}
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
       background: var(--bg); color: var(--fg); line-height: 1.6; }}

/* ---- Header bar ---- */
.report-header {{
    background: var(--deep-blue); color: #fff; padding: 22px 40px;
    display: flex; align-items: center; gap: 20px;
}}
.logo-mark {{
    background: var(--accent); color: #fff; font-weight: 800; font-size: 10px;
    letter-spacing: 1.2px; padding: 10px 11px; line-height: 1.15;
    text-align: center; border-radius: 4px; flex-shrink: 0;
}}
.logo-mark span {{ display: block; }}
.header-info h1 {{
    font-family: Georgia, "Times New Roman", serif;
    font-size: 1.5em; font-weight: 400; letter-spacing: 0.2px; color: #fff;
}}
.header-info .sub {{ color: rgba(255,255,255,0.6); font-size: 0.85em; margin-top: 2px; }}

/* ---- Layout ---- */
.wrap {{ max-width: 1400px; margin: 0 auto; padding: 20px 40px; }}
.sidebar-layout {{ display: flex; gap: 30px; }}
.sidebar {{ width: 280px; flex-shrink: 0; position: sticky; top: 0; max-height: 100vh; overflow-y: auto;
            padding: 20px; background: var(--bg2); border-right: 1px solid var(--border); border-radius: 6px; }}
.main-content {{ flex: 1; min-width: 0; }}

/* ---- Headings ---- */
h2 {{
    margin: 24px 0 10px; color: var(--deep-blue);
    font-family: Georgia, "Times New Roman", serif;
    font-weight: 400; font-size: 1.2em;
    border-bottom: 2px solid var(--border); padding-bottom: 5px;
}}
h3 {{ margin: 15px 0 8px; color: var(--deep-blue); }}

/* ---- Sub-tabs inside entity view ---- */
.sub-tabs {{ display: flex; gap: 0; border-bottom: 2px solid var(--border); margin-bottom: 15px; }}
.sub-tab {{
    padding: 9px 18px; cursor: pointer; border: none;
    border-bottom: 3px solid transparent; background: transparent;
    color: var(--gray); font-weight: 500; font-size: 0.88em; transition: all 0.15s;
}}
.sub-tab.active {{ color: var(--accent); border-bottom-color: var(--accent); font-weight: 700; }}
.sub-tab:hover {{ color: var(--fg); background: var(--bg2); }}
.sub-tab-content {{ display: none; }}
.sub-tab-content.active {{ display: block; }}

/* ---- Tables ---- */
table {{ width: 100%; border-collapse: collapse; font-size: 0.85em; margin: 10px 0; }}
th {{
    background: var(--accent); color: #fff; padding: 10px 12px; text-align: left;
    cursor: pointer; position: sticky; top: 0; user-select: none;
    font-weight: 500; letter-spacing: 0.2px;
}}
th:hover {{ opacity: 0.92; }}
td {{ padding: 8px 12px; border-bottom: 1px solid var(--border); }}
tr:nth-child(even) {{ background: var(--row-alt); }}
tr:hover {{ background: var(--hover-row); }}
.table-wrap {{ max-height: 600px; overflow: auto; border: 1px solid var(--border); border-radius: 6px; }}

/* ---- Form controls ---- */
select {{
    padding: 8px 14px; border: 1px solid var(--border); border-radius: 4px;
    background: var(--bg); color: var(--fg); font-size: 0.9em; min-width: 200px;
}}
select:focus {{ outline: none; border-color: var(--accent); box-shadow: 0 0 0 2px rgba(0,111,207,0.15); }}
.filters {{ display: flex; gap: 15px; flex-wrap: wrap; align-items: center; margin: 10px 0 15px; }}
.filters label {{ font-weight: 600; font-size: 0.85em; color: var(--deep-blue); display: flex; flex-direction: column; gap: 4px; }}

/* ---- Sidebar controls ---- */
.sidebar h3 {{ font-size: 1em; margin: 12px 0 6px; }}
.sidebar label {{ display: block; font-weight: 600; font-size: 0.82em; color: var(--deep-blue); margin-bottom: 4px; }}
.sidebar select {{ width: 100%; margin-bottom: 12px; }}
.sidebar .divider {{ border-top: 1px solid var(--border); margin: 14px 0; }}
.view-radio {{ display: flex; flex-direction: column; gap: 6px; margin: 8px 0; }}
.view-radio label {{ font-weight: 400; cursor: pointer; display: flex; align-items: center; gap: 6px; }}
.view-radio input {{ accent-color: var(--accent); }}
.filter-group {{ margin-bottom: 10px; }}
.filter-group select {{ width: 100%; }}
.checkbox-group {{ display: flex; flex-direction: column; gap: 4px; }}
.checkbox-group label {{ font-weight: 400; font-size: 0.82em; cursor: pointer; display: flex; align-items: center; gap: 5px; }}

/* ---- Banners ---- */
.banner {{ padding: 14px 18px; border-radius: 6px; margin: 10px 0; font-size: 0.9em; }}
.banner-warn {{ background: #FFF8E6; border: 1px solid #FFD666; color: #7A5F00; }}
.banner-ok {{ background: #E6F7ED; border: 1px solid #7DD3A0; color: #0D6832; }}
.banner-info {{ background: #E8F2FC; border: 1px solid #B3D4F0; color: #003B73; }}
.banner-danger {{ background: #FDE8E8; border: 1px solid #F5A3A3; color: #7A1A1A; }}

/* ---- Metrics row ---- */
.metrics {{ display: flex; gap: 16px; margin: 15px 0; flex-wrap: wrap; }}
.metric-card {{
    background: var(--bg2); border: 1px solid var(--border); border-radius: 8px;
    padding: 16px 24px; min-width: 140px; text-align: center;
}}
.metric-card .value {{ font-size: 1.8em; font-weight: 700; color: var(--deep-blue); }}
.metric-card .label {{ font-size: 0.78em; color: var(--gray); margin-top: 2px; }}

/* ---- Expanders ---- */
.expander {{ border: 1px solid var(--border); border-radius: 6px; margin: 6px 0; }}
.expander-header {{
    padding: 12px 16px; cursor: pointer; font-weight: 500;
    display: flex; justify-content: space-between; align-items: center; transition: background 0.1s;
}}
.expander-header:hover {{ background: var(--bg2); }}
.expander-body {{ display: none; padding: 16px; border-top: 1px solid var(--border); font-size: 0.9em; }}
.expander.open .expander-body {{ display: block; }}
.expander-arrow {{ transition: transform 0.2s; color: var(--accent); }}
.expander.open .expander-arrow {{ transform: rotate(90deg); }}

/* ---- Status boxes ---- */
.info-box {{
    background: #E8F2FC; border-left: 4px solid var(--accent);
    padding: 12px 16px; border-radius: 0 4px 4px 0; margin: 8px 0; color: #003B73;
}}
.success-box {{
    background: #E6F7ED; border-left: 4px solid var(--success);
    padding: 12px 16px; border-radius: 0 4px 4px 0; margin: 8px 0; color: #0D6832;
}}
.warning-box {{
    background: #FFF8E6; border-left: 4px solid #FFD666;
    padding: 12px 16px; border-radius: 0 4px 4px 0; margin: 8px 0; color: #7A5F00;
}}
.error-box {{
    background: #FDE8E8; border-left: 4px solid var(--danger);
    padding: 12px 16px; border-radius: 0 4px 4px 0; margin: 8px 0; color: #7A1A1A;
}}

/* ---- Signals ---- */
.signal {{ padding: 4px 0; }}
.signal-control {{ color: var(--danger); font-weight: 600; }}
.signal-app {{ color: var(--orange); }}
.signal-aux {{ color: var(--accent); }}

/* ---- Misc ---- */
blockquote {{
    border-left: 3px solid var(--accent); padding: 10px 18px; margin: 8px 0;
    background: var(--bg2); font-style: italic; font-size: 0.9em; border-radius: 0 4px 4px 0;
}}
.rating-bar {{ font-family: "SF Mono", "Cascadia Code", "Fira Mono", monospace; font-size: 0.92em; }}
.meta {{ color: var(--gray); font-size: 0.85em; }}
.entity-context {{ margin-bottom: 12px; }}
.chart-container {{ max-width: 500px; margin: 15px 0; }}
.md-table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
.md-table th {{ background: var(--accent); color: #fff; padding: 10px 12px; text-align: left; font-weight: 500; }}
.md-table td {{ padding: 10px 12px; border-bottom: 1px solid var(--border); }}
.md-table tr:nth-child(even) {{ background: var(--row-alt); }}
.divider {{ border-top: 1px solid var(--border); margin: 20px 0; }}
.tab-content {{ display: none; }}
.tab-content.active {{ display: block; }}

/* ---- Footer ---- */
.report-footer {{
    background: var(--bg2); border-top: 1px solid var(--border);
    padding: 18px 40px; display: flex; justify-content: space-between; align-items: center;
    margin-top: 40px;
}}
.report-footer .ft {{ color: var(--gray); font-size: 0.78em; line-height: 1.6; }}
.footer-mark {{
    background: var(--accent); color: #fff; font-weight: 800; font-size: 7px;
    letter-spacing: 0.8px; padding: 5px 6px; line-height: 1.1; text-align: center; border-radius: 2px;
}}
.footer-mark span {{ display: block; }}
</style>
</head>
<body>

<!-- ==================== BRANDED HEADER ==================== -->
<div class="report-header">
    <div class="logo-mark"><span>AMERICAN</span><span>EXPRESS</span></div>
    <div class="header-info">
        <h1>Risk Taxonomy Review</h1>
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
        <label><input type="radio" name="view" value="portfolio" checked onchange="switchView(this.value)"> Portfolio Overview</label>
        <label><input type="radio" name="view" value="entity" onchange="switchView(this.value)"> Entity View</label>
        <label><input type="radio" name="view" value="risk" onchange="switchView(this.value)"> Risk Category View</label>
    </div>
    <div class="divider"></div>

    <div id="sidebar-entity-select" style="display:none;">
        <label>Select Audit Entity</label>
        <select id="entity-select" onchange="renderEntityView()"></select>
        <div class="divider"></div>
    </div>

    <div id="sidebar-risk-select" style="display:none;">
        <label>Select L2 Risk</label>
        <select id="risk-select" onchange="renderRiskView()"></select>
        <div class="divider"></div>
    </div>

    <div id="sidebar-status-filter" style="display:none;">
        <label>Status Filter</label>
        <div class="checkbox-group" id="status-checkboxes">
            <label><input type="checkbox" value="Applicability Undetermined" onchange="applyFilters()"> &#9888;&#65039; Applicability Undetermined</label>
            <label><input type="checkbox" value="Needs Review" onchange="applyFilters()"> &#128270; Needs Review</label>
            <label><input type="checkbox" value="Assumed N/A &#8212; Verify" onchange="applyFilters()"> &#128310; Assumed N/A &#8212; Verify</label>
            <label><input type="checkbox" value="Applicable" onchange="applyFilters()"> &#9989; Applicable</label>
            <label><input type="checkbox" value="Not Applicable" onchange="applyFilters()"> &#11036; Not Applicable</label>
            <label><input type="checkbox" value="No Legacy Source" onchange="applyFilters()"> &#128309; No Legacy Source</label>
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

<!-- ==================== PORTFOLIO TAB ==================== -->
<div id="tab-portfolio" class="tab-content active">
    <h2 style="border:none;margin-top:0;">Portfolio Overview</h2>
    <div class="meta" id="portfolio-subtitle"></div>
    <div id="portfolio-banner"></div>
    <h2>Status Distribution</h2>
    <div id="portfolio-summary"></div>
    <h2>Entity Summary</h2>
    <div class="meta" style="margin-bottom:10px;">To investigate a specific entity, switch to Entity View in the sidebar.</div>
    <div class="table-wrap"><table id="entity-summary-table"></table></div>
</div>

<!-- ==================== ENTITY TAB ==================== -->
<div id="tab-entity" class="tab-content">
    <div id="entity-title"></div>
    <div id="entity-banner"></div>
    <div id="unmapped-findings-banner"></div>
    <div id="entity-context"></div>

    <div class="sub-tabs" id="entity-sub-tabs">
        <div class="sub-tab active" onclick="switchEntityTab('profile')">Risk Profile</div>
        <div class="sub-tab" onclick="switchEntityTab('drill')">Drill-Down</div>
        <div class="sub-tab" onclick="switchEntityTab('trace')">Traceability</div>
        <div class="sub-tab" onclick="switchEntityTab('source')">Source Data</div>
    </div>

    <div id="entity-tab-profile" class="sub-tab-content active">
        <div class="table-wrap"><table id="entity-profile-table"></table></div>
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
    <div class="chart-container"><canvas id="concentration-chart"></canvas></div>
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
    <div class="footer-mark"><span>AM</span><span>EX</span></div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
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
const entities = {json.dumps(entities)};
const l2Risks = {json.dumps(l2_risks)};
const auditLeaders = {json.dumps(audit_leaders)};
const pgaList = {json.dumps(pgas)};
const coreTeams = {json.dumps(core_teams)};

// ==================== STATUS CONFIG ====================
const STATUS_CONFIG = {{
    "Applicability Undetermined": {{"icon": "\\u26A0\\uFE0F", "sort": 0}},
    "Needs Review": {{"icon": "\\ud83d\\udd0e", "sort": 1}},
    "Assumed N/A \\u2014 Verify": {{"icon": "\\ud83d\\udd36", "sort": 2}},
    "Applicable": {{"icon": "\\u2705", "sort": 3}},
    "Not Applicable": {{"icon": "\\u2B1C", "sort": 4}},
    "No Legacy Source": {{"icon": "\\ud83d\\udd35", "sort": 5}},
}};
const RATING_RANK = {{"Low":1,"Medium":2,"High":3,"Critical":4,"low":1,"medium":2,"high":3,"critical":4}};
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
    if (m.includes("evaluated_no_evidence")) return "Assumed N/A \\u2014 Verify";
    if (m.includes("no_evidence_all_candidates")) return "Applicability Undetermined";
    if (m.includes("true_gap_fill") || m.includes("gap_fill")) return "No Legacy Source";
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
        html += `<th onclick="sortTable('${{id}}',${{i}},'${{t}}')">${{h}} \\u25B4\\u25BE</th>`;
    }});
    html += "</tr></thead><tbody>";
    rows.forEach(r => {{
        html += "<tr>" + r.map(c => `<td>${{c}}</td>`).join("") + "</tr>";
    }});
    html += "</tbody>";
    document.getElementById(id).innerHTML = html;
}}

function toggleExpander(el) {{
    el.closest(".expander").classList.toggle("open");
}}

function makeBanner(containerId, total, undetermined, assumedNA, contextLabel) {{
    let action = undetermined + assumedNA;
    let el = document.getElementById(containerId);
    if (action > 0) {{
        el.innerHTML = `<div class="banner banner-warn"><strong>${{action}} of ${{total}} items</strong> ${{contextLabel ? "for " + esc(contextLabel) + " " : ""}}need your review &mdash; ${{undetermined}} applicability undetermined, ${{assumedNA}} no evidence found (verify N/A).</div>`;
    }} else {{
        el.innerHTML = `<div class="banner banner-ok"><strong>All ${{total}} items</strong> ${{contextLabel ? "for " + esc(contextLabel) + " " : ""}}were determined automatically.</div>`;
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
    if (status === "Assumed N/A \\u2014 Verify") return renderDrilldownAssumedNA(row, detailRow);
    if (status === "Applicability Undetermined") return renderDrilldownUndetermined(row, detailRow, entityDetailRows);
    if (status === "Applicable") return renderDrilldownApplicable(row, detailRow);
    return renderDrilldownInformational(row);
}}

function renderRatings(row, detailRow) {{
    let lk = row["Likelihood"];
    if (isEmpty(lk)) return "";
    let html = "";
    let irrLabel = null;
    if (detailRow) irrLabel = detailRow["inherent_risk_rating_label"];
    if (isEmpty(irrLabel)) irrLabel = row["Inherent Risk Rating"];
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
let currentView = "portfolio";

function getSelectedStatuses() {{
    let checked = [];
    document.querySelectorAll("#status-checkboxes input:checked").forEach(cb => checked.push(cb.value));
    return checked;
}}

function applyFilters() {{
    if (currentView === "portfolio") renderPortfolio();
    else if (currentView === "entity") renderEntityView();
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
    document.getElementById("sidebar-status-filter").style.display = name !== "portfolio" ? "block" : "none";
    document.getElementById("sidebar-org-filters").style.display = name !== "entity" ? "block" : "none";
    if (name === "portfolio") renderPortfolio();
    if (name === "entity") renderEntityView();
    if (name === "risk") renderRiskView();
}}

function switchEntityTab(name) {{
    document.querySelectorAll(".sub-tab-content").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".sub-tab").forEach(t => t.classList.remove("active"));
    document.getElementById("entity-tab-" + name).classList.add("active");
    let idx = ["profile","drill","trace","source"].indexOf(name);
    document.querySelectorAll(".sub-tab")[idx].classList.add("active");
}}

// ==================== PORTFOLIO VIEW ====================
function renderPortfolio() {{
    let data = getFilteredAuditData();
    let total = data.length;
    let totalEntities = new Set(data.map(r => r["Entity ID"])).size;
    document.getElementById("portfolio-subtitle").textContent = totalEntities + " entities \\u00B7 " + total + " total mappings";

    let undetermined = data.filter(r => r["Status"] === "Applicability Undetermined").length;
    let assumedNA = data.filter(r => r["Status"] === "Assumed N/A \\u2014 Verify").length;
    makeBanner("portfolio-banner", total, undetermined, assumedNA, "");

    let isAI = r => String(r["Decision Basis"]||"").startsWith("AI review");
    let evidenceCount = data.filter(r => r["Status"] === "Applicable" && !isAI(r)).length;
    let aiApplicable = data.filter(r => r["Status"] === "Applicable" && isAI(r)).length;
    let aiNA = data.filter(r => r["Status"] === "Not Applicable" && isAI(r)).length;
    let aiTotal = aiApplicable + aiNA;
    let naCount = data.filter(r => r["Status"] === "Not Applicable" && !isAI(r)).length;
    let notAssessed = data.filter(r => r["Status"] === "No Legacy Source").length;

    let cats = [
        ["\\u2705 Mapped with evidence", evidenceCount,
         "These L2 risks were matched based on keywords in the rationale text, sub-risk descriptions, or confirmed by open findings. Review the mappings but no applicability decision needed."],
        ["\\ud83e\\udd16 AI-proposed", aiTotal,
         "AI review proposed applicability for these rows (" + aiApplicable + " applicable, " + aiNA + " not applicable). The AI's reasoning is shown in the Decision Basis column. Review the proposal and override if needed."],
        ["\\u26A0\\uFE0F Team decision required", undetermined,
         "The tool could not determine which L2 risks apply from the available data. All possible L2s are shown with the legacy rating \\u2014 your team decides which ones are relevant and marks the rest N/A."],
        ["\\ud83d\\udd36 Assumed N/A \\u2014 Verify", assumedNA,
         "Other L2s from the same legacy pillar had evidence, but this one did not. Marked as not applicable by default. Override if this L2 is relevant to the entity."],
        ["\\u2B1C Source was N/A", naCount,
         "The legacy pillar was explicitly rated Not Applicable. Carried forward \\u2014 no action needed unless circumstances have changed."],
        ["\\ud83d\\udd35 No legacy coverage", notAssessed,
         "No legacy pillar maps to this L2 risk. This is a gap in the old taxonomy, not a team decision. Will need to be assessed from scratch."]
    ];
    cats.sort((a,b) => b[1] - a[1]);
    let summaryHtml = '<table class="md-table"><thead><tr><th>Category</th><th>Count</th><th>%</th><th>Reviewer Action</th></tr></thead><tbody>';
    cats.forEach(([cat, ct, action]) => {{
        let pct = total > 0 ? (ct/total*100).toFixed(1) + "%" : "0%";
        summaryHtml += `<tr><td>${{cat}}</td><td>${{ct}}</td><td>${{pct}}</td><td>${{action}}</td></tr>`;
    }});
    summaryHtml += "</tbody></table>";
    document.getElementById("portfolio-summary").innerHTML = summaryHtml;

    let entityMap = {{}};
    data.forEach(r => {{
        let eid = r["Entity ID"];
        if (!entityMap[eid]) entityMap[eid] = [];
        entityMap[eid].push(r);
    }});
    let eRows = [];
    Object.keys(entityMap).sort().forEach(eid => {{
        let rows = entityMap[eid];
        let first = rows[0];
        let applicableCt = rows.filter(r => r["Status"] === "Applicable").length;
        let actionRows = rows.filter(r => ["Applicability Undetermined","Assumed N/A \\u2014 Verify"].includes(r["Status"]));
        let highCrit = actionRows.filter(r => ["High","Critical"].includes(r["Inherent Risk Rating"])).length;
        let otherDec = actionRows.length - highCrit;
        let controlFlags = 0;
        if (rows[0].hasOwnProperty("Control Signals")) {{
            controlFlags = rows.filter(r => /review whether|open issues/i.test(String(r["Control Signals"]||""))).length;
        }} else {{
            controlFlags = rows.filter(r => (r["Additional Signals"]||"").includes("Well Controlled")).length;
        }}
        let ed = detailData.filter(d => String(d["entity_id"]) === String(eid));
        let legacyHighest = "";
        let legacyRank = 0;
        ed.forEach(d => {{
            let rank = RATING_RANK[String(d["source_risk_rating_raw"]).trim()] || 0;
            if (rank > legacyRank) {{ legacyRank = rank; legacyHighest = RANK_LABEL[rank]; }}
        }});
        let proposedHighest = "";
        let proposedRank = 0;
        rows.forEach(r => {{
            let rank = RATING_RANK[String(r["Inherent Risk Rating"]).trim()] || 0;
            if (rank > proposedRank) {{ proposedRank = rank; proposedHighest = RANK_LABEL[rank]; }}
        }});
        eRows.push([eid, first["Entity Name"]||"", first["Audit Leader"]||"", first["PGA"]||"",
                    first["Core Audit Team"]||"",
                    applicableCt,
                    highCrit + otherDec,
                    legacyHighest||"\\u2014", proposedHighest||"\\u2014",
                    highCrit, otherDec, controlFlags]);
    }});
    eRows.sort((a,b) => (b[9]-a[9]) || (b[10]-a[10]));
    makeTable("entity-summary-table",
        ["Entity ID","Entity Name","Audit Leader","PGA","Core Audit Team",
         "Applicable","Needs Review","Legacy Highest","Proposed Highest","High/Crit Decisions","Other Decisions","Control Flags"],
        eRows, ["str","str","str","str","str","num","num","str","str","num","num","num"]);
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
    let assumedNA = rows.filter(r => r["Status"] === "Assumed N/A \\u2014 Verify").length;

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
                    let sEid = String(s["entity_id"]||s["Audit Entity ID"]||"");
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
        let oreEidCol = oreData[0].hasOwnProperty("entity_id") ? "entity_id" : (oreData[0].hasOwnProperty("Audit Entity ID") ? "Audit Entity ID" : null);
        if (oreEidCol) {{
            let eo = oreData.filter(o => String(o[oreEidCol]||"").trim() === eid);
            if (eo.length) {{
                srcHtml += `<p class="meta">${{eo.length}} ORE(s)</p>`;
                let cols = Object.keys(eo[0]).filter(c => !isEmpty(eo[0][c]) || eo.some(r => !isEmpty(r[c])));
                if (cols.length > 8) cols = cols.slice(0, 8);
                srcHtml += '<div class="table-wrap"><table><thead><tr>' + cols.map(c => `<th>${{esc(c)}}</th>`).join("") + '</tr></thead><tbody>';
                eo.forEach(o => {{ srcHtml += '<tr>' + cols.map(c => `<td>${{esc(String(o[c]||""))}}</td>`).join("") + '</tr>'; }});
                srcHtml += "</tbody></table></div>";
            }} else {{ srcHtml += "<p class='meta'>No OREs for this entity.</p>"; }}
        }} else {{ srcHtml += "<p class='meta'>ORE data missing entity ID column.</p>"; }}
    }} else {{ srcHtml += "<p class='meta'>No ORE data in workbook.</p>"; }}

    // PRSA Issues
    srcHtml += "<div class='divider'></div><h3>PRSA Issues</h3>";
    if (prsaData.length) {{
        let prsaEidCol = prsaData[0].hasOwnProperty("Audit Entity") ? "Audit Entity" : (prsaData[0].hasOwnProperty("Audit Entity ID") ? "Audit Entity ID" : null);
        if (prsaEidCol) {{
            let ep = prsaData.filter(p => String(p[prsaEidCol]||"").trim() === eid);
            if (ep.length) {{
                srcHtml += `<p class="meta">${{ep.length}} PRSA record(s)</p>`;
                let cols = Object.keys(ep[0]).filter(c => !isEmpty(ep[0][c]) || ep.some(r => !isEmpty(r[c])));
                if (cols.length > 8) cols = cols.slice(0, 8);
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
                if (cols.length > 8) cols = cols.slice(0, 8);
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
                if (cols.length > 8) cols = cols.slice(0, 8);
                srcHtml += '<div class="table-wrap"><table><thead><tr>' + cols.map(c => `<th>${{esc(c)}}</th>`).join("") + '</tr></thead><tbody>';
                eb.forEach(b => {{ srcHtml += '<tr>' + cols.map(c => `<td>${{esc(String(b[c]||""))}}</td>`).join("") + '</tr>'; }});
                srcHtml += "</tbody></table></div>";
            }} else {{ srcHtml += "<p class='meta'>No BM Activities for this entity.</p>"; }}
        }} else {{ srcHtml += "<p class='meta'>BMA data missing entity column.</p>"; }}
    }} else {{ srcHtml += "<p class='meta'>No BM Activities data in workbook.</p>"; }}

    // Sub-Risks
    srcHtml += "<div class='divider'></div><h3>Sub-Risks</h3>";
    let es = subRisksData.filter(s => String(s["entity_id"]||s["Audit Entity ID"]||"").trim() === eid);
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
let concentrationChart = null;
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
    let assumedNA = rows.filter(r => r["Status"] === "Assumed N/A \\u2014 Verify").length;
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
    let chartValues = chartLabels.map(k => ratingCounts[k]);
    let chartColors = {{"Critical":"#dc3545","High":"#e8923c","Medium":"#ffc107","Low":"#28a745","Not Applicable":"#6c757d","No Rating":"#adb5bd"}};
    if (concentrationChart) concentrationChart.destroy();
    let ctx = document.getElementById("concentration-chart").getContext("2d");
    concentrationChart = new Chart(ctx, {{
        type: "bar",
        data: {{
            labels: chartLabels,
            datasets: [{{ data: chartValues, backgroundColor: chartLabels.map(l => chartColors[l]||"#ccc") }}]
        }},
        options: {{
            plugins: {{ legend: {{ display: false }} }},
            scales: {{ y: {{ beginAtZero: true, title: {{ display: true, text: "Entities" }} }} }}
        }}
    }});

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
                    let sEid = String(s["entity_id"]||s["Audit Entity ID"]||"");
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
    entities.forEach(e => {{ let o = document.createElement("option"); o.value = e; o.text = e; eSelect.add(o); }});
    let rSelect = document.getElementById("risk-select");
    l2Risks.forEach(l => {{ let o = document.createElement("option"); o.value = l; o.text = l; rSelect.add(o); }});
    let alSelect = document.getElementById("filter-al");
    auditLeaders.forEach(v => {{ let o = document.createElement("option"); o.value = v; o.text = v; alSelect.add(o); }});
    let pgaSelect = document.getElementById("filter-pga");
    pgaList.forEach(v => {{ let o = document.createElement("option"); o.value = v; o.text = v; pgaSelect.add(o); }});
    let teamSelect = document.getElementById("filter-team");
    coreTeams.forEach(v => {{ let o = document.createElement("option"); o.value = v; o.text = v; teamSelect.add(o); }});
    renderPortfolio();
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