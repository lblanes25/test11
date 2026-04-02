"""
Static HTML Report Generator (AmEx Branded)
============================================
Reads the transformer's Excel output and generates a self-contained, brand-styled
HTML file that can be uploaded to SharePoint and opened in any browser.

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

    # Read sheets
    sheets = {}
    xls = pd.ExcelFile(excel_path)
    for name in ["Audit_Review", "Side_by_Side", "Findings_Source", "Sub_Risks_Source"]:
        if name in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=name)
            if name == "Audit_Review":
                df = df.rename(columns={"Proposed Status": "Status",
                                         "Proposed Rating": "Inherent Risk Rating"})
            sheets[name] = df

    audit_df = sheets.get("Audit_Review", pd.DataFrame())
    detail_df = sheets.get("Side_by_Side", pd.DataFrame())
    findings_df = sheets.get("Findings_Source", pd.DataFrame())
    sub_risks_df = sheets.get("Sub_Risks_Source", pd.DataFrame())

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

    # Get unique values for filters
    entities = sorted(audit_df["Entity ID"].unique().tolist()) if "Entity ID" in audit_df.columns else []
    l2_risks = sorted(audit_df["New L2"].unique().tolist()) if "New L2" in audit_df.columns else []

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

/* ---- Content wrapper ---- */
.wrap {{ max-width: 1400px; margin: 0 auto; padding: 20px 40px; }}

/* ---- Headings ---- */
h2 {{
    margin: 24px 0 10px; color: var(--deep-blue);
    font-family: Georgia, "Times New Roman", serif;
    font-weight: 400; font-size: 1.2em;
    border-bottom: 2px solid var(--border); padding-bottom: 5px;
}}
h3 {{ margin: 15px 0 8px; color: var(--deep-blue); }}

/* ---- Tabs ---- */
.tabs {{ display: flex; gap: 0; border-bottom: 2px solid var(--border); margin-bottom: 20px; }}
.tab {{
    padding: 11px 22px; cursor: pointer; border: none;
    border-bottom: 3px solid transparent; background: transparent;
    color: var(--gray); font-weight: 500; font-size: 0.95em; transition: all 0.15s;
}}
.tab.active {{ color: var(--deep-blue); border-bottom-color: var(--accent); font-weight: 700; }}
.tab:hover {{ color: var(--fg); background: var(--bg2); }}
.tab-content {{ display: none; }}
.tab-content.active {{ display: block; }}

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
    background: var(--bg); color: var(--fg); font-size: 0.9em; min-width: 220px;
}}
select:focus {{ outline: none; border-color: var(--accent); box-shadow: 0 0 0 2px rgba(0,111,207,0.15); }}
.filters {{ display: flex; gap: 15px; flex-wrap: wrap; align-items: center; margin: 10px 0 15px; }}
.filters label {{ font-weight: 600; font-size: 0.85em; color: var(--deep-blue); }}

/* ---- Banners ---- */
.banner {{ padding: 14px 18px; border-radius: 6px; margin: 10px 0; font-size: 0.9em; }}
.banner-warn {{ background: #FFF8E6; border: 1px solid #FFD666; color: #7A5F00; }}
.banner-ok {{ background: #E6F7ED; border: 1px solid #7DD3A0; color: #0D6832; }}

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

<div class="tabs">
    <div class="tab active" onclick="switchTab('portfolio')">Portfolio Overview</div>
    <div class="tab" onclick="switchTab('entity')">Entity View</div>
    <div class="tab" onclick="switchTab('risk')">Risk Category View</div>
</div>

<!-- ==================== PORTFOLIO TAB ==================== -->
<div id="tab-portfolio" class="tab-content active">
    <div id="portfolio-banner"></div>
    <h2>Status Distribution</h2>
    <div id="portfolio-summary"></div>
    <h2>Entity Summary</h2>
    <div class="filters" id="portfolio-filters"></div>
    <div class="table-wrap"><table id="entity-summary-table"></table></div>
    <p class="meta" style="margin-top:10px;">To investigate a specific entity, switch to the Entity View tab.</p>
</div>

<!-- ==================== ENTITY TAB ==================== -->
<div id="tab-entity" class="tab-content">
    <div class="filters">
        <label>Entity: <select id="entity-select" onchange="renderEntityView()"></select></label>
    </div>
    <div id="entity-banner"></div>
    <div id="entity-context"></div>
    <h2>Risk Profile</h2>
    <div class="table-wrap"><table id="entity-profile-table"></table></div>
    <h2>Drill-Down</h2>
    <div id="entity-drilldown"></div>
    <h2>Source Data</h2>
    <div id="entity-sources"></div>
</div>

<!-- ==================== RISK CATEGORY TAB ==================== -->
<div id="tab-risk" class="tab-content">
    <div class="filters">
        <label>L2 Risk: <select id="risk-select" onchange="renderRiskView()"></select></label>
    </div>
    <div id="risk-banner"></div>
    <h2>Entity Breakdown</h2>
    <div class="table-wrap"><table id="risk-entity-table"></table></div>
    <h2>Rating Concentration</h2>
    <div class="chart-container"><canvas id="concentration-chart"></canvas></div>
    <h2>Entity Drill-Down</h2>
    <div id="risk-drilldown"></div>
    <h2>Findings for this L2</h2>
    <div id="risk-findings"></div>
</div>

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
const entities = {json.dumps(entities)};
const l2Risks = {json.dumps(l2_risks)};

// ==================== STATUS CONFIG ====================
const STATUS_ICONS = {{
    "Applicability Undetermined": "\\u26A0\\uFE0F",
    "Assumed Not Applicable": "\\ud83d\\udd36",
    "Applicable": "\\u2705",
    "Not Applicable": "\\u2B1C",
    "Not Assessed": "\\ud83d\\udd35"
}};
const RATING_RANK = {{"Low":1,"Medium":2,"High":3,"Critical":4}};
const RANK_LABEL = {{1:"Low",2:"Medium",3:"High",4:"Critical"}};

// ==================== HELPERS ====================
function isEmpty(v) {{ return v === null || v === undefined || v === "" || v === "nan" || v === "None"; }}
function esc(s) {{
    if (!s) return "";
    let d = document.createElement("div");
    d.textContent = String(s);
    return d.innerHTML;
}}
function icon(status) {{ return STATUS_ICONS[status] || "\\u2753"; }}
function ratingBar(v) {{
    if (isEmpty(v)) return "\\u2014";
    let n = parseInt(v);
    let labels = {{1:"Low",2:"Medium",3:"High",4:"Critical"}};
    return "\\u2588".repeat(n) + "\\u2591".repeat(4-n) + " " + n + " (" + (labels[n]||"") + ")";
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

function makeBanner(containerId, total, undetermined, assumedNA) {{
    let action = undetermined + assumedNA;
    let el = document.getElementById(containerId);
    if (action > 0) {{
        el.innerHTML = `<div class="banner banner-warn"><strong>${{action}} items require attention</strong> &mdash; ${{undetermined}} applicability undetermined, ${{assumedNA}} assumed not applicable.</div>`;
    }} else {{
        el.innerHTML = `<div class="banner banner-ok"><strong>No items require attention</strong> &mdash; all mappings determined automatically.</div>`;
    }}
}}

function renderSignals(signals) {{
    if (isEmpty(signals)) return "";
    return signals.split(" | ").filter(s => s.trim()).map(s => {{
        let cls = "signal";
        let prefix = "\\u2139\\uFE0F";
        if (s.toLowerCase().includes("well controlled")) {{ cls = "signal signal-control"; prefix = "\\ud83d\\udea8"; }}
        else if (s.toLowerCase().includes("application") || s.toLowerCase().includes("engagement")) {{ cls = "signal signal-app"; prefix = "\\ud83d\\udcce"; }}
        else if (s.toLowerCase().includes("auxiliary")) {{ cls = "signal signal-aux"; prefix = "\\ud83d\\udccc"; }}
        else if (s.toLowerCase().includes("outside normal")) {{ cls = "signal signal-aux"; prefix = "\\ud83d\\udd00"; }}
        return `<div class="${{cls}}">${{prefix}} ${{esc(s)}}</div>`;
    }}).join("");
}}

function renderDrilldown(row, detailRow) {{
    let status = row["Status"] || "";
    let html = "";
    let basis = row["Decision Basis"] || "";
    if (!isEmpty(basis)) {{
        let boxClass = status === "Applicable" ? "success-box" : status.includes("Undetermined") ? "warning-box" : "info-box";
        html += `<div class="${{boxClass}}"><strong>Decision Basis</strong><br>${{esc(basis)}}</div>`;
    }}
    if (detailRow) {{
        let rat = detailRow["source_rationale"] || "";
        if (!isEmpty(rat)) html += `<p><strong>Source Rationale</strong></p><blockquote>${{esc(rat)}}</blockquote>`;
    }}
    let sig = renderSignals(row["Additional Signals"]);
    if (sig) html += `<p><strong>Additional Signals</strong></p>${{sig}}`;
    if (status === "Applicable" || status.includes("Undetermined")) {{
        let lk = row["Likelihood"];
        if (!isEmpty(lk)) {{
            let irr = row["Inherent Risk Rating"] || "";
            html += `<p><strong>Proposed Inherent Risk Rating: ${{isEmpty(irr) ? "\\u2014" : irr}}</strong></p>`;
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
        }}
    }}
    return html;
}}

// ==================== TAB SWITCHING ====================
function switchTab(name) {{
    document.querySelectorAll(".tab-content").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.getElementById("tab-" + name).classList.add("active");
    document.querySelectorAll(".tab")[["portfolio","entity","risk"].indexOf(name)].classList.add("active");
    if (name === "entity") renderEntityView();
    if (name === "risk") renderRiskView();
}}

// ==================== PORTFOLIO VIEW ====================
function renderPortfolio() {{
    let data = auditData;
    let total = data.length;
    let counts = {{}};
    ["Applicable","Applicability Undetermined","Assumed Not Applicable","Not Applicable","Not Assessed"].forEach(s => {{
        counts[s] = data.filter(r => r["Status"] === s).length;
    }});
    makeBanner("portfolio-banner", total, counts["Applicability Undetermined"], counts["Assumed Not Applicable"]);
    let cats = [
        ["\\u2705 Mapped with evidence", counts["Applicable"], "These L2 risks were matched based on keywords in the rationale text, sub-risk descriptions, or confirmed by open findings. Review the mappings but no applicability decision needed."],
        ["\\u26A0\\uFE0F Team decision required", counts["Applicability Undetermined"], "The tool could not determine which L2 risks apply from the available data. All possible L2s are shown with the legacy rating \\u2014 your team decides which ones are relevant and marks the rest N/A."],
        ["\\ud83d\\udd36 Assumed not applicable \\u2014 verify", counts["Assumed Not Applicable"], "Other L2s from the same legacy pillar had evidence, but this one did not. Marked as not applicable by default. Override if this L2 is relevant to the entity."],
        ["\\u2B1C Source was N/A", counts["Not Applicable"], "The legacy pillar was explicitly rated Not Applicable. Carried forward \\u2014 no action needed unless circumstances have changed."],
        ["\\ud83d\\udd35 No legacy coverage", counts["Not Assessed"], "No legacy pillar maps to this L2 risk. This is a gap in the old taxonomy, not a team decision. Will need to be assessed from scratch."]
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
        let applicable = rows.filter(r => r["Status"] === "Applicable").length;
        let actionRows = rows.filter(r => ["Applicability Undetermined","Assumed Not Applicable"].includes(r["Status"]));
        let highCrit = actionRows.filter(r => ["High","Critical"].includes(r["Inherent Risk Rating"])).length;
        let otherDec = actionRows.length - highCrit;
        let controlFlags = rows.filter(r => (r["Additional Signals"]||"").includes("Well Controlled")).length;
        let ed = detailData.filter(d => String(d["entity_id"]) === String(eid));
        let legacyRated = new Set(ed.filter(d => !isEmpty(d["source_risk_rating_raw"]) &&
            !["not applicable","n/a","na"].includes(String(d["source_risk_rating_raw"]).toLowerCase()))
            .map(d => String(d["source_legacy_pillar"]).split(" (also")[0])).size;
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
                    first["Core Audit Team"]||"", legacyRated + " \\u2192 " + applicable,
                    legacyHighest||"\\u2014", proposedHighest||"\\u2014",
                    highCrit, otherDec, controlFlags]);
    }});
    eRows.sort((a,b) => (b[8]-a[8]) || (b[9]-a[9]));
    makeTable("entity-summary-table",
        ["Entity ID","Entity Name","Audit Leader","PGA","Core Audit Team","Coverage",
         "Legacy Highest","Proposed Highest","High/Crit Decisions","Other Decisions","Control Flags"],
        eRows, ["str","str","str","str","str","str","str","str","num","num","num"]);
}}

// ==================== ENTITY VIEW ====================
function renderEntityView() {{
    let eid = document.getElementById("entity-select").value;
    if (!eid) return;
    let rows = auditData.filter(r => r["Entity ID"] === eid);
    if (!rows.length) return;
    let first = rows[0];
    let undetermined = rows.filter(r => r["Status"] === "Applicability Undetermined").length;
    let assumedNA = rows.filter(r => r["Status"] === "Assumed Not Applicable").length;
    makeBanner("entity-banner", rows.length, undetermined, assumedNA);
    let ctxHtml = '<div class="entity-context">';
    if (!isEmpty(first["Entity Name"])) ctxHtml += `<h3>${{esc(first["Entity Name"])}}</h3>`;
    if (!isEmpty(first["Entity Overview"])) ctxHtml += `<p class="meta">${{esc(first["Entity Overview"])}}</p>`;
    let meta = [];
    if (!isEmpty(first["Audit Leader"])) meta.push("Audit Leader: " + first["Audit Leader"]);
    if (!isEmpty(first["PGA"])) meta.push("PGA: " + first["PGA"]);
    if (meta.length) ctxHtml += `<p class="meta">${{meta.join(" \\u00B7 ")}}</p>`;
    ctxHtml += "</div>";
    document.getElementById("entity-context").innerHTML = ctxHtml;
    let statusOrder = {{"Applicability Undetermined":0,"Assumed Not Applicable":1,"Applicable":2,"Not Applicable":3,"Not Assessed":4}};
    rows.sort((a,b) => {{
        let sa = statusOrder[a["Status"]]||9, sb = statusOrder[b["Status"]]||9;
        if (sa !== sb) return sa - sb;
        let ra = RATING_RANK[a["Inherent Risk Rating"]]||0, rb = RATING_RANK[b["Inherent Risk Rating"]]||0;
        return rb - ra;
    }});
    let profileRows = rows.map(r => [
        r["New L1"]||"", r["New L2"]||"",
        icon(r["Status"]) + " " + r["Status"],
        isEmpty(r["Inherent Risk Rating"]) ? "\\u2014" : r["Inherent Risk Rating"],
        r["Confidence"]||"", r["Legacy Source"]||"",
        r["Decision Basis"]||"", isEmpty(r["Additional Signals"]) ? "" : r["Additional Signals"]
    ]);
    makeTable("entity-profile-table",
        ["L1","L2","Status","Rating","Confidence","Legacy Source","Decision Basis","Additional Signals"],
        profileRows);
    let ddHtml = "";
    rows.forEach(r => {{
        let l2 = r["New L2"]||"";
        let status = r["Status"]||"";
        let irr = r["Inherent Risk Rating"]||"";
        let label = icon(status) + " " + (r["New L1"]||"") + " / " + l2 + " \\u00B7 " + status;
        if (!isEmpty(irr) && irr !== "Not Applicable") label += " \\u00B7 " + irr;
        let detail = detailData.find(d => String(d["entity_id"])===eid && d["new_l2"]===l2);
        let body = renderDrilldown(r, detail);
        ddHtml += `<div class="expander"><div class="expander-header" onclick="toggleExpander(this)">
            <span>${{label}}</span><span class="expander-arrow">\\u25B6</span>
        </div><div class="expander-body">${{body}}</div></div>`;
    }});
    document.getElementById("entity-drilldown").innerHTML = ddHtml;
    let srcHtml = "";
    let ef = findingsData.filter(f => String(f["entity_id"]||f["Audit Entity ID"]||"") === eid);
    if (ef.length) {{
        srcHtml += `<h3>Findings (${{ef.length}})</h3><div class="table-wrap"><table><thead><tr>
            <th>Finding ID</th><th>L2 Risk</th><th>Severity</th><th>Status</th><th>Title</th><th>Disposition</th>
        </tr></thead><tbody>`;
        ef.forEach(f => {{
            srcHtml += `<tr><td>${{f["issue_id"]||f["Finding ID"]||""}}</td><td>${{f["l2_risk"]||f["Risk Dimension Categories"]||""}}</td>
                <td>${{f["severity"]||f["Final Reportable Finding Risk Rating"]||""}}</td><td>${{f["status"]||f["Finding Status"]||""}}</td>
                <td>${{f["issue_title"]||f["Finding Name"]||""}}</td><td>${{f["Disposition"]||""}}</td></tr>`;
        }});
        srcHtml += "</tbody></table></div>";
    }} else {{ srcHtml += "<p class='meta'>No findings for this entity.</p>"; }}
    let es = subRisksData.filter(s => String(s["entity_id"]||s["Audit Entity ID"]||"") === eid);
    if (es.length) {{
        srcHtml += `<h3>Sub-Risks (${{es.length}})</h3><div class="table-wrap"><table><thead><tr>
            <th>Risk ID</th><th>Description</th><th>L1 Category</th><th>Rating</th><th>Contributed To</th>
        </tr></thead><tbody>`;
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
    let rows = auditData.filter(r => r["New L2"] === l2);
    if (!rows.length) return;
    let undetermined = rows.filter(r => r["Status"] === "Applicability Undetermined").length;
    let assumedNA = rows.filter(r => r["Status"] === "Assumed Not Applicable").length;
    makeBanner("risk-banner", rows.length, undetermined, assumedNA);
    let statusOrder = {{"Applicability Undetermined":0,"Assumed Not Applicable":1,"Applicable":2,"Not Applicable":3,"Not Assessed":4}};
    rows.sort((a,b) => {{
        let ra = RATING_RANK[a["Inherent Risk Rating"]]||0, rb = RATING_RANK[b["Inherent Risk Rating"]]||0;
        if (rb !== ra) return rb - ra;
        return (statusOrder[a["Status"]]||9) - (statusOrder[b["Status"]]||9);
    }});
    let tRows = rows.map(r => [
        r["Entity ID"]||"", r["Entity Name"]||"", r["Audit Leader"]||"",
        isEmpty(r["Inherent Risk Rating"]) ? "\\u2014" : r["Inherent Risk Rating"],
        icon(r["Status"]) + " " + r["Status"],
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
    let ddHtml = "";
    rows.forEach(r => {{
        let eid = r["Entity ID"]||"";
        let status = r["Status"]||"";
        let irr = r["Inherent Risk Rating"]||"";
        let ename = r["Entity Name"]||"";
        let parts = [icon(status) + " " + eid];
        if (!isEmpty(ename)) parts.push(ename);
        parts.push(status);
        if (!isEmpty(irr) && irr !== "Not Applicable") parts.push(irr);
        let label = parts.join(" \\u00B7 ");
        let detail = detailData.find(d => String(d["entity_id"])===eid && d["new_l2"]===l2);
        let body = '<div class="entity-context">';
        if (!isEmpty(ename)) body += `<strong>${{esc(ename)}}</strong><br>`;
        if (!isEmpty(r["Entity Overview"])) body += `<span class="meta">${{esc(r["Entity Overview"])}}</span><br>`;
        let meta = [];
        if (!isEmpty(r["Audit Leader"])) meta.push("AL: " + esc(r["Audit Leader"]));
        if (!isEmpty(r["PGA"])) meta.push("PGA: " + esc(r["PGA"]));
        if (meta.length) body += `<span class="meta">${{meta.join(" \\u00B7 ")}}</span>`;
        body += "</div><hr style='border:none;border-top:1px solid var(--border);margin:8px 0'>";
        body += renderDrilldown(r, detail);
        let ef = findingsData.filter(f => {{
            let fEid = String(f["entity_id"]||f["Audit Entity ID"]||"");
            let fL2 = String(f["l2_risk"]||f["Mapped To L2(s)"]||f["Risk Dimension Categories"]||"");
            return fEid === eid && fL2.includes(l2);
        }});
        if (ef.length) {{
            body += "<p><strong>Relevant Findings</strong></p>";
            ef.forEach(f => {{
                body += `<div>\\u2022 ${{f["issue_id"]||f["Finding ID"]||""}}: ${{f["issue_title"]||f["Finding Name"]||""}} (${{f["severity"]||""}}, ${{f["status"]||f["Finding Status"]||""}})</div>`;
            }});
        }}
        if (detail) {{
            let pillar = String(detail["source_legacy_pillar"]||"").split(" (also")[0];
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
    document.getElementById("risk-drilldown").innerHTML = ddHtml;
    let allFindings = findingsData.filter(f => {{
        let fL2 = String(f["l2_risk"]||f["Mapped To L2(s)"]||f["Risk Dimension Categories"]||"");
        return fL2.includes(l2);
    }});
    let fHtml = "";
    if (allFindings.length) {{
        let fEntities = new Set(allFindings.map(f => f["entity_id"]||f["Audit Entity ID"]));
        fHtml = `<p><strong>${{allFindings.length}} findings</strong> across <strong>${{fEntities.size}} entities</strong> tagged to this L2.</p>`;
        fHtml += '<div class="table-wrap"><table><thead><tr><th>Entity</th><th>Finding ID</th><th>Severity</th><th>Status</th><th>Title</th></tr></thead><tbody>';
        allFindings.forEach(f => {{
            fHtml += `<tr><td>${{f["entity_id"]||f["Audit Entity ID"]||""}}</td><td>${{f["issue_id"]||f["Finding ID"]||""}}</td>
                <td>${{f["severity"]||""}}</td><td>${{f["status"]||f["Finding Status"]||""}}</td><td>${{f["issue_title"]||f["Finding Name"]||""}}</td></tr>`;
        }});
        fHtml += "</tbody></table></div>";
    }} else {{ fHtml = "<p class='meta'>No findings tagged to this L2.</p>"; }}
    document.getElementById("risk-findings").innerHTML = fHtml;
}}

// ==================== INITIALIZATION ====================
window.addEventListener("load", () => {{
    let eSelect = document.getElementById("entity-select");
    entities.forEach(e => {{ let o = document.createElement("option"); o.value = e; o.text = e; eSelect.add(o); }});
    let rSelect = document.getElementById("risk-select");
    l2Risks.forEach(l => {{ let o = document.createElement("option"); o.value = l; o.text = l; rSelect.add(o); }});
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