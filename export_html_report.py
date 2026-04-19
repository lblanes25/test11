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
        print(f"  Warning: no files match pattern '{pattern}' — inventory will be empty")
        return pd.DataFrame()
    latest = max(matches, key=lambda p: p.stat().st_mtime)
    try:
        return pd.read_excel(latest)
    except Exception:
        return pd.DataFrame()


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
    legacy_json = _safe_json(legacy_df)
    applications_inventory_json = _safe_json(applications_df)
    policies_inventory_json = _safe_json(policies_df)
    laws_inventory_json = _safe_json(laws_df)
    thirdparties_inventory_json = _safe_json(thirdparties_df)

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
th.th-tool {{ background: #e3f2fd; }}
th.th-tool:hover {{ background: #d0e7fa; }}
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
.signal-meta {{ color: var(--gray); }}

/* ---- Rating table (drill-down) ---- */
.rating-table {{ width: auto; border-collapse: collapse; margin: 6px 0 10px; }}
.rating-table td {{
    padding: 3px 16px 3px 0; border: none; white-space: nowrap;
    vertical-align: top; max-width: none; cursor: default;
}}
.rating-table td:first-child {{
    color: var(--gray); font-weight: 600; font-size: 13px;
    text-transform: uppercase; letter-spacing: 0.3px;
}}
.rating-table .breakdown {{ color: var(--gray); font-size: 12px; font-weight: 400; display: block; margin-top: 2px; text-transform: none; letter-spacing: 0; white-space: normal; }}
.drill-section {{ margin: 10px 0; }}
.drill-section .label {{ color: var(--fg); font-weight: 500; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; display: block; }}
.drill-inline-meta {{ color: var(--gray); font-size: 13px; margin: 4px 0; }}

/* ---- Drill-down sub-risk list ---- */
.subrisk-row {{ display: flex; gap: 10px; padding: 2px 0; align-items: baseline; }}
.subrisk-id {{
    font-family: "Source Code Pro", "SF Mono", "Cascadia Code", monospace;
    font-size: 12px; color: var(--gray-light); min-width: 50px;
}}
.subrisk-name {{ color: var(--fg); font-size: 13px; }}

/* ---- Drill-down Additional Signals ---- */
.signal-row {{ padding: 4px 0; font-size: 13px; color: var(--fg); }}
.signal-tag {{
    display: inline-block; font-size: 11px; padding: 1px 7px;
    border-radius: 4px; background: var(--bg2); color: var(--gray);
    margin-right: 6px; vertical-align: baseline;
}}
.signal-ids {{
    font-family: "Source Code Pro", "SF Mono", "Cascadia Code", monospace;
    font-size: 12px; color: var(--gray-light); margin: 0 2px;
}}
.signal-hint {{ color: var(--gray); }}
.signal-contradiction {{ color: #842029; font-weight: 600; }}

/* ---- Drill-down count chips ---- */
.count-chips {{ display: flex; gap: 8px; flex-wrap: wrap; margin: 4px 0; }}
.count-chip {{
    display: inline-flex; align-items: baseline; gap: 6px;
    padding: 6px 10px; background: var(--bg2); border-radius: 6px;
}}
.count-chip-n {{ font-size: 15px; font-weight: 500; color: var(--fg); }}
.count-chip-label {{ font-size: 12px; color: var(--gray); }}

/* ---- Drill-down findings mini-table ---- */
.drill-findings-table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin: 4px 0; table-layout: fixed; }}
.drill-findings-table th, .drill-findings-table td {{
    padding: 6px 10px; border-bottom: 1px solid var(--border);
    vertical-align: top; line-height: 1.4; cursor: default;
    white-space: normal; overflow: visible; text-overflow: clip;
    max-width: none; word-wrap: break-word;
}}
.drill-findings-table th {{
    background: var(--bg2); text-align: left; font-weight: 600;
    font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;
    border-bottom: 2px solid var(--border);
}}
.drill-findings-id {{
    font-family: "Source Code Pro", "SF Mono", "Cascadia Code", monospace;
    font-size: 12px; color: var(--gray);
}}
.drill-header-row {{
    display: flex; align-items: baseline; gap: 0;
    margin-bottom: 4px; flex-wrap: wrap;
}}
.drill-header-summary {{
    display: inline-flex; align-items: center; gap: 8px;
    margin-left: 10px; font-size: 12px;
}}
.drill-header-summary .sep {{ color: var(--gray-light); }}
.drill-header-summary .count {{ color: var(--gray); text-transform: none; letter-spacing: 0; font-weight: 400; }}

/* ---- Misc ---- */
blockquote {{
    border-left: 3px solid var(--gray-light); padding: 10px 18px; margin: 10px 0;
    background: var(--bg2); font-style: italic; font-size: 14px; border-radius: 0 8px 8px 0;
    color: #555;
}}
.overview {{ color: var(--gray); font-size: 13px; }}
.overview p {{ margin: 4px 0; }}
.overview ul.overview-list {{ margin: 4px 0 4px 18px; padding: 0; }}
.overview ul.overview-list li {{ margin: 2px 0; }}
.overview-toggle {{
    font-size: 12px; color: var(--blue); cursor: pointer;
    text-decoration: underline; margin-left: 4px;
}}
.handoff-stack {{ margin: 6px 0 0; }}
.handoff-col {{ margin-bottom: 12px; }}
.handoff-col:last-child {{ margin-bottom: 0; }}
.handoff-col-label {{
    font-size: 11px; color: var(--gray); text-transform: uppercase;
    letter-spacing: 0.4px; font-weight: 600; margin-bottom: 4px;
}}
.handoff-entry {{ display: flex; gap: 10px; margin-bottom: 4px; align-items: baseline; }}
.handoff-id {{
    font-family: "Source Code Pro", "SF Mono", "Cascadia Code", monospace;
    font-size: 12px; color: var(--gray-light); min-width: 50px; flex-shrink: 0;
}}
.handoff-name {{ color: var(--fg); font-size: 13px; line-height: 1.5; }}
.handoff-desc {{ margin-top: 10px; color: var(--fg); font-size: 13px; }}

/* ---- Legacy Profile table ---- */
.legacy-table {{
    table-layout: fixed; width: 100%; border-collapse: collapse;
    font-size: 13px; margin: 8px 0;
}}
.legacy-table th, .legacy-table td {{
    padding: 8px 12px; border-bottom: 1px solid var(--border);
    vertical-align: top; line-height: 1.5;
    white-space: normal; overflow: visible; text-overflow: clip;
    word-wrap: break-word; max-width: none; cursor: default;
}}
.legacy-table th {{
    background: var(--bg2); text-align: left; font-weight: 600;
    font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px;
    border-bottom: 2px solid var(--border);
}}
.legacy-table tr:nth-child(even) {{ background: var(--row-alt); }}

/* ---- Expandable-row tables (Legacy Profile + Source Data) ---- */
.expandable-rows tbody tr {{ cursor: pointer; transition: background 0.15s; }}
.expandable-rows tbody tr:hover {{ background: var(--hover-row); }}
.expandable-rows tbody td {{ cursor: pointer; }}
.expandable-rows tr.open td {{
    white-space: normal; overflow: visible; max-width: none;
    text-overflow: clip;
}}
.expandable-rows .row-arrow {{
    display: inline-block; color: var(--gray); font-size: 12px;
    transition: transform 0.2s; margin-right: 6px;
}}
.expandable-rows tr.open .row-arrow {{ transform: rotate(90deg); }}
.expandable-rows .truncate-cell {{
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}}
.expandable-rows tr.open .truncate-cell {{
    white-space: normal; line-height: 1.5;
}}
.pill {{
    display: inline-block; font-size: 11px; padding: 2px 8px;
    border-radius: 10px; font-weight: 600; white-space: nowrap;
}}
.pill-neutral {{ background: var(--bg2); color: var(--gray); }}
.empty-cell {{ color: var(--gray-light); }}
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
        <div class="sub-tab" onclick="switchEntityTab('drill')">Drill-Down</div>
        <div class="sub-tab" onclick="switchEntityTab('legacy')">Legacy Profile</div>
        <div class="sub-tab" onclick="switchEntityTab('source')">Source Data</div>
        <div class="sub-tab" onclick="switchEntityTab('trace')" style="display:none;">Traceability</div>
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
const legacyData = {legacy_json};
const applicationsInventory = {applications_inventory_json};
const policiesInventory = {policies_inventory_json};
const lawsInventory = {laws_inventory_json};
const thirdpartiesInventory = {thirdparties_inventory_json};
const INVENTORY_COLS = {json.dumps(inventory_cols)};
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
        let label = (typeof h === "object") ? h.label : h;
        let cls = (typeof h === "object" && h.tool) ? ' class="th-tool"' : '';
        html += `<th${{cls}} onclick="sortTable('${{id}}',${{i}},'${{t}}')">${{label}} \\u25B4\\u25BE<span class="col-resize" onmousedown="startResize(event)"></span></th>`;
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
    if (e.target.tagName === "A") return;
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

function toggleExpandableRow(tr) {{
    tr.classList.toggle("open");
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

// ==================== ABSENCE DETECTION ====================
// A value is an "absence" if it conveys that nothing was found / is available.
// Absence values should not render as loud callouts — they render as muted
// inline text (when meaningful as reassurance) or are omitted entirely.
function isAbsence(v) {{
    if (isEmpty(v)) return true;
    let s = String(v).trim().toLowerCase();
    if (s === "n/a" || s === "none" || s === "not available") return true;
    if (s === "no open items") return true;
    if (/^no .+ available$/.test(s)) return true;  // "No engagement rating available", etc.
    return false;
}}

function formatOverview(raw, id) {{
    let text = String(raw || "").replace(/\\r\\n/g, "\\n").trim();
    if (!text) return "";
    let paragraphs = text.split(/\\n\\s*\\n/).map(p => p.trim()).filter(Boolean);
    if (!paragraphs.length) return "";
    let bulletRe = /^[\\u2022\\-\\*]\\s+|^\\d+[.)]\\s+/;
    function renderPara(p) {{
        let lines = p.split("\\n").map(l => l.trim()).filter(Boolean);
        let allBullets = lines.length > 1 && lines.every(l => bulletRe.test(l));
        if (allBullets) {{
            let items = lines.map(l => "<li>" + esc(l.replace(bulletRe, "").trim()) + "</li>").join("");
            return '<ul class="overview-list">' + items + '</ul>';
        }}
        return "<p>" + esc(lines.join(" ")) + "</p>";
    }}
    let truncate = text.length > 400 && paragraphs.length > 1;
    if (!truncate) return paragraphs.map(renderPara).join("");
    let tid = "overview-more-" + id;
    return renderPara(paragraphs[0]) +
        `<div id="${{tid}}" style="display:none;">${{paragraphs.slice(1).map(renderPara).join("")}}</div>` +
        `<a href="javascript:void(0)" class="overview-toggle" onclick="toggleOverview('${{tid}}', this)">Show more</a>`;
}}

function toggleOverview(id, el) {{
    let div = document.getElementById(id);
    let hidden = div.style.display === "none";
    div.style.display = hidden ? "block" : "none";
    el.textContent = hidden ? "Show less" : "Show more";
}}

function severitySummary(rows, getVal, order) {{
    let counts = {{}};
    rows.forEach(r => {{
        let v = String(getVal(r) || "").trim();
        if (!v || v.toLowerCase() === "nan") return;
        counts[v] = (counts[v] || 0) + 1;
    }});
    if (!Object.keys(counts).length) return "";
    let parts = [];
    order.forEach(label => {{
        if (counts[label]) {{
            parts.push(counts[label] + " " + label);
            delete counts[label];
        }}
    }});
    Object.keys(counts).forEach(k => parts.push(counts[k] + " " + k));
    return " \\u2014 " + parts.join(", ");
}}

// ==================== PILL HELPERS ====================
function severityStyle(v) {{
    let lower = String(v||"").trim().toLowerCase();
    let map = {{
        "critical": "background:#FCEBEB;color:#791F1F;",
        "high":     "background:#FAD8C1;color:#7A2E0F;",
        "medium":   "background:#FAEEDA;color:#633806;",
        "low":      "background:#EAF3DE;color:#27500A;",
    }};
    return map[lower] || "background:var(--bg2);color:var(--gray);";
}}
function severityPill(v) {{
    let s = String(v||"").trim();
    let lower = s.toLowerCase();
    if (!s || lower === "n/a" || lower === "na" || lower === "not applicable") {{
        return `<span class="pill pill-neutral">${{esc(s || "N/A")}}</span>`;
    }}
    let style = severityStyle(s);
    return `<span class="pill" style="${{style}}">${{esc(s)}}</span>`;
}}
function oreClassStyle(v) {{
    let lower = String(v||"").trim().toLowerCase();
    let map = {{
        "class a": "background:#FCEBEB;color:#791F1F;",
        "class b": "background:#FAD8C1;color:#7A2E0F;",
        "class c": "background:#FAEEDA;color:#633806;",
    }};
    return map[lower] || "background:var(--bg2);color:var(--gray);";
}}
function oreClassPill(v) {{
    let s = String(v||"").trim();
    if (!s) return `<span class="pill pill-neutral">\\u2014</span>`;
    let style = oreClassStyle(s);
    return `<span class="pill" style="${{style}}">${{esc(s)}}</span>`;
}}
function iagStatusPill(v) {{
    let s = String(v||"").trim();
    if (!s) return `<span class="pill pill-neutral">\\u2014</span>`;
    if (s.toLowerCase() === "closed") {{
        return `<span class="pill pill-neutral">${{esc(s)}}</span>`;
    }}
    return `<span class="pill" style="background:#FAEEDA;color:#633806;">${{esc(s)}}</span>`;
}}
function controlRatingPill(v) {{
    let s = String(v||"").trim();
    let lower = s.toLowerCase();
    if (!s || lower === "n/a" || lower === "na" || lower === "not applicable") {{
        return `<span class="pill pill-neutral">${{esc(s || "N/A")}}</span>`;
    }}
    let map = {{
        "well controlled":           "background:#EAF3DE;color:#27500A;",
        "moderately controlled":     "background:#FAEEDA;color:#633806;",
        "insufficiently controlled": "background:#FCEBEB;color:#791F1F;",
        "inadequately controlled":   "background:#FCEBEB;color:#791F1F;",
        "poorly controlled":         "background:#FCEBEB;color:#791F1F;",
    }};
    let style = map[lower];
    if (!style) return `<span class="pill pill-neutral">${{esc(s)}}</span>`;
    return `<span class="pill" style="${{style}}">${{esc(s)}}</span>`;
}}

// ==================== SIGNAL RENDERING ====================
// Signals are parsed into: leading [TAG] (rendered as a chip), statement body,
// inline ID lists (rendered mono/tertiary), and a trailing em-dash action hint
// (rendered secondary). Control contradictions ("well controlled but ...
// review whether") get alert styling instead.
function renderSignals(signals) {{
    if (isEmpty(signals)) return "";
    let items = String(signals).split(/\\n| \\| /).filter(s => s.trim());
    if (!items.length) return "";
    let html = '<div class="drill-section"><span class="label">Additional Signals</span>';
    items.forEach(raw => {{
        let s = raw.trim();
        let lower = s.toLowerCase();
        let isContradiction = lower.includes("well controlled but") || lower.includes("review whether");
        if (isContradiction) {{
            html += `<div class="signal-row signal-contradiction">\\ud83d\\udea8 ${{esc(s)}}</div>`;
            return;
        }}
        // Extract leading [TAG] chip
        let tagHtml = "";
        let body = s;
        let tagMatch = body.match(/^\\[([^\\]]+)\\]\\s*/);
        if (tagMatch) {{
            tagHtml = `<span class="signal-tag">${{esc(tagMatch[1])}}</span>`;
            body = body.substring(tagMatch[0].length);
        }}
        // Extract trailing " \u2014 hint"
        let hintHtml = "";
        let emIdx = body.indexOf("\\u2014");
        if (emIdx >= 0) {{
            let hint = body.substring(emIdx + 1).trim();
            body = body.substring(0, emIdx).trim();
            if (hint) hintHtml = ` <span class="signal-hint">\\u2014 ${{esc(hint)}}</span>`;
        }}
        // Transform inline parenthesized ID lists (only when they contain ';' — avoids
        // mangling quoted-keyword parens in cross-boundary signals).
        let bodyHtml = "";
        let cursor = 0;
        while (cursor < body.length) {{
            let open = body.indexOf("(", cursor);
            if (open < 0) {{ bodyHtml += esc(body.substring(cursor)); break; }}
            let close = body.indexOf(")", open);
            if (close < 0) {{ bodyHtml += esc(body.substring(cursor)); break; }}
            let inner = body.substring(open + 1, close);
            if (inner.includes(";")) {{
                bodyHtml += esc(body.substring(cursor, open));
                let ids = inner.split(";").map(x => x.trim()).filter(Boolean).join(", ");
                bodyHtml += `<span class="signal-ids">${{esc(ids)}}</span>`;
                cursor = close + 1;
            }} else {{
                bodyHtml += esc(body.substring(cursor, close + 1));
                cursor = close + 1;
            }}
        }}
        html += `<div class="signal-row">${{tagHtml}}${{bodyHtml}}${{hintHtml}}</div>`;
    }});
    html += '</div>';
    return html;
}}

// ==================== SECTION RENDERERS ====================
// Colored callouts announce the row's decision outcome (Decision Basis, one
// per panel, color by status) or a hard contradiction the reviewer must read
// (Control Signals). Everything else is plain text with a muted label.

function renderDecisionBasis(row, status) {{
    let basis = row["Decision Basis"] || "";
    if (isEmpty(basis)) return "";
    let cls = "info-box";
    if (status === "Applicable") cls = "success-box";
    else if (status === "Applicability Undetermined") cls = "warning-box";
    else if (status === "Not Assessed") {{
        return `<div class="drill-section"><span class="label">Decision Basis</span><div>${{esc(basis)}}</div></div>`;
    }}
    return `<div class="${{cls}}"><strong>Decision Basis</strong><br>${{esc(basis)}}</div>`;
}}

function renderSiblingMatches(row, entityDetailRows) {{
    let legacySource = String(row["Legacy Source"] || "");
    if (!entityDetailRows || isEmpty(legacySource)) return "";
    let bp = basePillar(legacySource);
    let matched = entityDetailRows.filter(d =>
        String(d["source_legacy_pillar"]||"").includes(bp) &&
        !String(d["method"]||"").includes("no_evidence_all_candidates") &&
        !String(d["method"]||"").includes("evaluated_no_evidence")
    );
    if (!matched.length) return "";
    let html = `<div class="drill-section"><span class="label">Other L2s from ${{esc(bp)}} that DID match</span>`;
    matched.forEach(m => {{ html += `<div>\\u2022 \\u2705 ${{esc(m["new_l2"])}}</div>`; }});
    html += '</div>';
    return html;
}}

function renderSubRiskDescriptions(detailRow, eid, l2) {{
    if (!detailRow || isEmpty(eid) || isEmpty(l2)) return "";
    let pillar = basePillar(detailRow["source_legacy_pillar"]||"");
    if (isEmpty(pillar)) return "";
    let es = subRisksData.filter(s => {{
        let sEid = String(s["entity_id"]||s["Audit Entity"]||s["Audit Entity ID"]||"");
        let sL1 = String(s["legacy_l1"]||s["Level 1 Risk Category"]||"");
        if (sEid !== String(eid) || sL1 !== pillar) return false;
        let matches = String(s["L2 Keyword Matches"]||s["Contributed To (keyword matches)"]||"");
        let contributedTo = matches.split(";").map(x => x.trim().replace(/\\s*\\(.*/, ""));
        return contributedTo.includes(l2);
    }});
    if (!es.length) return "";
    let html = '<div class="drill-section"><span class="label">Sub-risks that contributed evidence for this L2</span>';
    es.forEach(s => {{
        let rid = s["risk_id"]||s["Key Risk ID"]||"";
        let desc = String(s["risk_description"]||s["Key Risk Description"]||"").substring(0,200);
        html += `<div class="subrisk-row"><span class="subrisk-id">${{esc(String(rid))}}</span><span class="subrisk-name">${{esc(desc)}}</span></div>`;
    }});
    html += '</div>';
    return html;
}}

function renderSourceRationale(detailRow) {{
    if (!detailRow) return "";
    let rat = detailRow["source_rationale"] || "";
    if (isEmpty(rat)) return "";
    return `<div class="drill-section"><span class="label">Source Rationale</span><blockquote>${{esc(rat)}}</blockquote></div>`;
}}

function renderSectionHeader(labelText, summaryInner) {{
    if (!summaryInner) return `<span class="label">${{esc(labelText)}}</span>`;
    return '<div class="drill-header-row">'
        + `<span class="label" style="margin-bottom:0;">${{esc(labelText)}}</span>`
        + `<span class="drill-header-summary">${{summaryInner}}</span>`
        + '</div>';
}}

function _countBySeverity(items, getSev) {{
    let counts = {{}};
    items.forEach(it => {{
        let s = String(getSev(it)||"").trim();
        if (!s) return;
        counts[s] = (counts[s] || 0) + 1;
    }});
    return counts;
}}

function _orderedSevPills(counts, order, styleFn) {{
    let pills = order
        .filter(sev => counts[sev] > 0)
        .map(sev => `<span class="pill" style="${{styleFn(sev)}}">${{counts[sev]}} ${{esc(sev)}}</span>`);
    Object.keys(counts).forEach(sev => {{
        if (order.includes(sev) || counts[sev] <= 0) return;
        pills.push(`<span class="pill pill-neutral">${{counts[sev]}} ${{esc(sev)}}</span>`);
    }});
    return pills;
}}

function renderRelevantFindings(eid, l2) {{
    if (isEmpty(eid) || isEmpty(l2)) return "";
    let ef = findingsData.filter(f => {{
        let fEid = String(f["entity_id"]||f["Audit Entity ID"]||"");
        let fL2 = String(f["l2_risk"]||f["Mapped To L2(s)"]||f["Risk Dimension Categories"]||"");
        return fEid === String(eid) && fL2.includes(l2);
    }});
    if (!ef.length) {{
        return '<div class="drill-section">'
            + '<span class="label">IAG Issues</span>'
            + '<div class="drill-inline-meta">No IAG issues tagged to this L2.</div>'
            + '</div>';
    }}
    let counts = _countBySeverity(ef, f => f["severity"]||f["Final Reportable Finding Risk Rating"]||"");
    let pills = _orderedSevPills(counts, ["Critical","High","Medium","Low"], severityStyle);
    let summary = pills.length
        ? `<span class="sep">\\u00b7</span>` + pills.join('<span class="sep" style="margin:0 2px;">\\u00b7</span>')
        : "";
    let html = '<div class="drill-section">' + renderSectionHeader("IAG Issues", summary);
    html += '<table class="drill-findings-table" style="table-layout:fixed;">';
    html += '<colgroup><col style="width:90px"><col><col style="width:100px"><col style="width:90px"></colgroup>';
    html += '<thead><tr><th>ID</th><th>Title</th><th>Severity</th><th>Status</th></tr></thead><tbody>';
    ef.forEach(f => {{
        let id = f["issue_id"]||f["Finding ID"]||"";
        let title = f["issue_title"]||f["Finding Name"]||"";
        let sev = f["severity"]||f["Final Reportable Finding Risk Rating"]||"";
        let status = f["status"]||f["Finding Status"]||"";
        html += '<tr>'
            + `<td><span class="drill-findings-id">${{esc(String(id))}}</span></td>`
            + `<td>${{esc(String(title))}}</td>`
            + `<td>${{severityPill(sev)}}</td>`
            + `<td>${{iagStatusPill(status)}}</td>`
            + '</tr>';
    }});
    html += '</tbody></table></div>';
    return html;
}}

function renderRelevantOREs(eid, l2) {{
    if (isEmpty(eid) || isEmpty(l2) || !oreData.length) return "";
    let eidCol = oreData[0].hasOwnProperty("entity_id") ? "entity_id" :
        (oreData[0].hasOwnProperty("Audit Entity (Operational Risk Events)") ? "Audit Entity (Operational Risk Events)" :
         (oreData[0].hasOwnProperty("Audit Entity ID") ? "Audit Entity ID" : null));
    if (!eidCol) return "";
    let seen = new Set();
    let eo = [];
    oreData.forEach(o => {{
        let oEid = String(o[eidCol]||"").trim();
        if (oEid !== String(eid)) return;
        let mappedList = String(o["Mapped L2s"]||o["l2_risk"]||"").split(/[;\\r\\n]+/).map(s => s.trim());
        if (!mappedList.includes(l2)) return;
        let evid = String(o["Event ID"]||"").trim();
        if (evid && seen.has(evid)) return;
        if (evid) seen.add(evid);
        eo.push(o);
    }});
    if (!eo.length) return "";
    let counts = _countBySeverity(eo, o => o["Final Event Classification"]||"");
    let pills = _orderedSevPills(counts, ["Class A","Class B","Class C"], oreClassStyle);
    let summary = pills.length
        ? `<span class="sep">\\u00b7</span>` + pills.join('<span class="sep" style="margin:0 2px;">\\u00b7</span>')
        : "";
    let html = '<div class="drill-section">' + renderSectionHeader("Operational Risk Events", summary);
    html += '<table class="drill-findings-table" style="table-layout:fixed;">';
    html += '<colgroup><col style="width:90px"><col><col style="width:100px"><col style="width:90px"></colgroup>';
    html += '<thead><tr><th>ID</th><th>Title</th><th>Class</th><th>Status</th></tr></thead><tbody>';
    eo.forEach(o => {{
        let id = o["Event ID"]||"";
        let title = o["Event Title"]||"";
        let cls = o["Final Event Classification"]||"";
        let status = o["Event Status"]||"";
        html += '<tr>'
            + `<td><span class="drill-findings-id">${{esc(String(id))}}</span></td>`
            + `<td>${{esc(String(title))}}</td>`
            + `<td>${{oreClassPill(cls)}}</td>`
            + `<td>${{iagStatusPill(status)}}</td>`
            + '</tr>';
    }});
    html += '</tbody></table></div>';
    return html;
}}

function renderRelevantPRSA(eid, l2) {{
    if (isEmpty(eid) || isEmpty(l2) || !prsaData.length) return "";
    let eidCol = prsaData[0].hasOwnProperty("AE ID") ? "AE ID"
        : (prsaData[0].hasOwnProperty("Audit Entity ID") ? "Audit Entity ID" : null);
    if (!eidCol) return "";
    // Deduplicate by Issue ID — a single issue may appear as multiple control rows
    let seen = new Set();
    let ep = [];
    prsaData.forEach(p => {{
        let pEid = String(p[eidCol]||"").trim();
        if (pEid !== String(eid)) return;
        let mappedList = String(p["Mapped L2s"]||"").split(/[;\\r\\n]+/).map(s => s.trim());
        if (!mappedList.includes(l2)) return;
        let iid = String(p["Issue ID"]||"").trim();
        if (iid && seen.has(iid)) return;
        if (iid) seen.add(iid);
        ep.push(p);
    }});
    if (!ep.length) return "";
    let counts = _countBySeverity(ep, p => p["Issue Rating"]||"");
    let pills = _orderedSevPills(counts, ["Critical","High","Medium","Low"], severityStyle);
    let summary = pills.length
        ? `<span class="sep">\\u00b7</span>` + pills.join('<span class="sep" style="margin:0 2px;">\\u00b7</span>')
        : "";
    let html = '<div class="drill-section">' + renderSectionHeader("PRSA Issues", summary);
    html += '<table class="drill-findings-table" style="table-layout:fixed;">';
    html += '<colgroup><col style="width:90px"><col><col style="width:100px"><col style="width:90px"></colgroup>';
    html += '<thead><tr><th>ID</th><th>Title</th><th>Rating</th><th>Status</th></tr></thead><tbody>';
    ep.forEach(p => {{
        let id = p["Issue ID"]||"";
        let title = p["Issue Title"]||"";
        let sev = p["Issue Rating"]||"";
        let status = p["Issue Status"]||"";
        html += '<tr>'
            + `<td><span class="drill-findings-id">${{esc(String(id))}}</span></td>`
            + `<td>${{esc(String(title))}}</td>`
            + `<td>${{severityPill(sev)}}</td>`
            + `<td>${{iagStatusPill(status)}}</td>`
            + '</tr>';
    }});
    html += '</tbody></table></div>';
    return html;
}}

function renderRelevantRAPs(eid, l2) {{
    if (isEmpty(eid) || isEmpty(l2) || !graRapsData.length) return "";
    let eidCol = graRapsData[0].hasOwnProperty("Audit Entity ID") ? "Audit Entity ID" : null;
    if (!eidCol) return "";
    let er = graRapsData.filter(g => {{
        let gEid = String(g[eidCol]||"").trim();
        if (gEid !== String(eid)) return false;
        let mappedList = String(g["Mapped L2s"]||"").split(/[;\\r\\n]+/).map(s => s.trim());
        return mappedList.includes(l2);
    }});
    if (!er.length) return "";
    let html = '<div class="drill-section">' + renderSectionHeader("GRA RAPs", "");
    html += '<table class="drill-findings-table" style="table-layout:fixed;">';
    html += '<colgroup><col style="width:90px"><col><col style="width:90px"></colgroup>';
    html += '<thead><tr><th>ID</th><th>Header</th><th>Status</th></tr></thead><tbody>';
    er.forEach(g => {{
        let id = g["RAP ID"]||"";
        let header = g["RAP Header"]||"";
        let status = g["RAP Status"]||"";
        html += '<tr>'
            + `<td><span class="drill-findings-id">${{esc(String(id))}}</span></td>`
            + `<td>${{esc(String(header))}}</td>`
            + `<td>${{iagStatusPill(status)}}</td>`
            + '</tr>';
    }});
    html += '</tbody></table></div>';
    return html;
}}

// ==================== CONTROL ASSESSMENT ====================
// Parses the "Impact of Issues" summary line into (type, severity) count chips.
// Source format: "Open items: 3 IAG issues (1 Critical, 2 High) \u00b7 1 Class B ORE".
// IAG/regulatory findings get split per severity (one chip each); OREs are
// already per-class in the source. Chips render as:
//   [ N TYPE [pill] ]
function parseImpactToChips(impact) {{
    let chips = [];
    let firstLine = String(impact||"").split(/\\r?\\n/).map(s => s.trim())
        .find(s => s && s.toLowerCase() !== "nan");
    if (!firstLine) return chips;
    let body = firstLine.replace(/^Open items:\\s*/i, "").trim();
    if (!body) return chips;
    let segments = body.split(/\\s+\\u00b7\\s+/);
    segments.forEach(seg => {{
        seg = seg.trim();
        if (!seg) return;
        // "N TYPE (sev1, sev2)" — split per severity
        let parenMatch = seg.match(/^(\\d+)\\s+(.+?)\\s+\\(([^)]+)\\)$/);
        if (parenMatch) {{
            let label = parenMatch[2];
            let parenBody = parenMatch[3];
            let sevParts = parenBody.split(/,\\s*/);
            let parsed = sevParts.map(p => {{
                let mm = p.match(/^(\\d+)\\s+(.+)$/);
                return mm ? {{count: parseInt(mm[1]), severity: mm[2].trim()}} : null;
            }}).filter(Boolean);
            if (parsed.length) {{
                parsed.forEach(({{count, severity}}) => chips.push({{count, label, severity, kind: "severity"}}));
                return;
            }}
        }}
        // "N Class X ORE[s]"
        let oreMatch = seg.match(/^(\\d+)\\s+Class\\s+([ABC])\\s+(ORE|OREs)$/i);
        if (oreMatch) {{
            chips.push({{count: parseInt(oreMatch[1]), label: "ORE", severity: "Class " + oreMatch[2].toUpperCase(), kind: "ore"}});
            return;
        }}
        // Bare "N LABEL"
        let bare = seg.match(/^(\\d+)\\s+(.+)$/);
        if (bare) {{
            chips.push({{count: parseInt(bare[1]), label: bare[2], severity: null, kind: null}});
        }}
    }});
    return chips;
}}

function labelFor(label, count) {{
    let plural = count > 1;
    if (/IAG issue/i.test(label)) return plural ? "IAG issues" : "IAG issue";
    if (/^ORE/i.test(label)) return plural ? "OREs" : "ORE";
    if (/regulatory finding/i.test(label)) return plural ? "regulatory findings" : "regulatory finding";
    if (/enterprise finding/i.test(label)) return plural ? "enterprise findings" : "enterprise finding";
    return label;
}}

function worstOpenIagSeverity(eid, l2) {{
    if (isEmpty(eid) || isEmpty(l2)) return null;
    let openStatuses = new Set(["open", "in validation", "in sustainability"]);
    let ef = findingsData.filter(f => {{
        let fEid = String(f["entity_id"]||f["Audit Entity ID"]||"");
        let fL2 = String(f["l2_risk"]||f["Mapped To L2(s)"]||f["Risk Dimension Categories"]||"");
        let status = String(f["status"]||f["Finding Status"]||"").toLowerCase().trim();
        return fEid === String(eid) && fL2.includes(l2) && openStatuses.has(status);
    }});
    let sevs = ef.map(f => String(f["severity"]||f["Final Reportable Finding Risk Rating"]||"").toLowerCase());
    if (sevs.some(s => s.includes("critical"))) return "Critical";
    if (sevs.some(s => s.includes("high"))) return "High";
    return null;
}}

function renderControlAssessment(row, eid, l2) {{
    let baseline = row["Control Effectiveness Baseline"] || "";
    if (isAbsence(baseline)) return "";

    let m = String(baseline).match(/^(.+?) \\(Last audit: (.+?), (.+?) \\u00b7 Next planned: (.+?)\\)$/)
        || String(baseline).match(/^(.+?) \\(Last audit: (.+?), (.+?) \\u00B7 Next planned: (.+?)\\)$/)
        || String(baseline).match(/^(.+?) \\(Last audit: (.+?), (.+?) · Next planned: (.+?)\\)$/);
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
    let contextText = segments.join(" \\u00b7 ");

    html += '<div>'
        + `<span style="margin-right:8px;">${{controlRatingPill(rating)}}</span>`
        + (contextText ? `<span style="font-size:13px;color:var(--gray);">${{esc(contextText)}}</span>` : "")
        + '</div>';

    // Amber warning: Well Controlled rating + open Critical/High IAG on this L2
    if (/^well controlled/i.test(rating)) {{
        let worst = worstOpenIagSeverity(eid, l2);
        if (worst) {{
            html += '<div style="display:flex;gap:8px;align-items:baseline;margin-top:6px;color:#633806;">'
                + '<span style="font-size:12px;">\\u26a0</span>'
                + `<span style="font-size:12px;">Open ${{esc(worst)}} issue below \\u2014 review whether this rating reflects current state</span>`
                + '</div>';
        }}
    }}

    html += '</div>';
    return html;
}}

function renderControlRatings(row) {{
    let controls = [["IAG Control Effectiveness", row["IAG Control Effectiveness"]],
                   ["Aligned Assurance Rating", row["Aligned Assurance Rating"]],
                   ["Management Awareness Rating", row["Management Awareness Rating"]]];
    let valid = controls.filter(([,v]) => !isEmpty(v));
    if (!valid.length) return "";
    let html = `<div class="drill-section"><span class="label">Control Ratings <em style="text-transform:none;letter-spacing:0;font-weight:400;">(starting point)</em></span>`;
    html += '<table class="rating-table">';
    valid.forEach(([l,v]) => {{ html += `<tr><td>${{esc(l)}}</td><td><span class="rating-bar">${{ratingBar(v)}}</span></td></tr>`; }});
    html += '</table></div>';
    return html;
}}

// ==================== DRILL-DOWN BODY (unified) ====================
// Reading order: outcome (Decision Basis) -> context (sub-risks, rationale,
// signals) -> evaluation (rating, controls, issues). Same order across all
// statuses; sections self-suppress when empty.
function renderDrilldownBody(row, detailRow, entityDetailRows, eid) {{
    let status = row["Status"] || "";
    let l2 = row["New L2"] || "";
    let html = "";

    html += renderDecisionBasis(row, status);
    if (status === "Applicability Undetermined") {{
        html += renderSiblingMatches(row, entityDetailRows);
    }}
    html += renderSubRiskDescriptions(detailRow, eid, l2);
    html += renderSourceRationale(detailRow);
    html += renderSignals(row["Additional Signals"]);
    html += renderControlRatings(row);
    html += renderControlAssessment(row, eid, l2);
    html += renderRelevantFindings(eid, l2);
    html += renderRelevantOREs(eid, l2);
    html += renderRelevantPRSA(eid, l2);
    html += renderRelevantRAPs(eid, l2);

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
    let idx = ["profile","drill","legacy","source","trace"].indexOf(name);
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
        let unmapped = ef.filter(f => String(f["Mapping Status"]||"").startsWith("Filtered") && String(f["Mapping Status"]||"").toLowerCase().includes("unmappable"));
        if (unmapped.length) {{
            let legacyCats = new Set();
            unmapped.forEach(f => {{
                let d = String(f["Mapping Status"]||"");
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
    if (!isEmpty(first["Entity Overview"])) ctxHtml += `<div class="overview">${{formatOverview(first["Entity Overview"], eid)}}</div>`;
    let meta = [];
    if (!isEmpty(first["Audit Leader"])) meta.push("Audit Leader: " + first["Audit Leader"]);
    if (!isEmpty(first["PGA"])) meta.push("PGA: " + first["PGA"]);
    if (meta.length) ctxHtml += `<p class="meta">${{meta.join(" \\u00B7 ")}}</p>`;

    let legacyRow = legacyData.find(r => String(r["Audit Entity ID"]||"").trim() === eid);
    if (legacyRow) {{
        let hFrom = legacyRow["Hand-offs from Other Audit Entities"];
        let hTo = legacyRow["Hand-offs to Other Audit Entities"];
        let hDesc = legacyRow["Hand-off Description"];
        if (!isAbsence(hFrom) || !isAbsence(hTo) || !isAbsence(hDesc)) {{
            let parseIds = v => isAbsence(v) ? [] : String(v).split(/[;\\r\\n]+/).map(s => s.trim()).filter(Boolean);
            let fromIds = parseIds(hFrom);
            let toIds = parseIds(hTo);
            let renderCol = (ids, labelText) => {{
                if (!ids.length) return "";
                let entries = ids.map(id => {{
                    let name = entityNameMap[id] || "";
                    return `<div class="handoff-entry"><span class="handoff-id">${{esc(id)}}</span><span class="handoff-name">${{esc(name)}}</span></div>`;
                }}).join("");
                return `<div class="handoff-col"><div class="handoff-col-label">${{labelText}} (${{ids.length}})</div>${{entries}}</div>`;
            }};
            let fromCol = renderCol(fromIds, "\\u2190 From");
            let toCol = renderCol(toIds, "To \\u2192");
            let grid = (fromCol || toCol) ? `<div class="handoff-stack">${{fromCol}}${{toCol}}</div>` : "";
            let descHtml = isAbsence(hDesc) ? "" : `<div class="handoff-desc">${{esc(String(hDesc))}}</div>`;
            ctxHtml += `<div class="drill-section"><span class="label">Handoffs</span>${{grid}}${{descHtml}}</div>`;
        }}
    }}

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
    let overviewCols = ["New L1","New L2","Status","Confidence","Inherent Risk Rating","Legacy Source","Decision Basis","Additional Signals"];
    if (rows.length && rows[0].hasOwnProperty("Control Effectiveness Baseline")) overviewCols.push("Control Effectiveness Baseline");
    if (rows.length && rows[0].hasOwnProperty("Impact of Issues")) overviewCols.push("Impact of Issues");
    if (rows.length && rows[0].hasOwnProperty("Control Signals")) overviewCols.push("Control Signals");
    let profileRows = rows.map(r => overviewCols.map(c => {{
        let v = r[c];
        if (c === "Status") return statusLabel(v);
        if (c === "Inherent Risk Rating") return isEmpty(v) ? "\\u2014" : String(v);
        return isEmpty(v) ? "" : String(v);
    }}));
    let profileHeaderOverride = {{"Inherent Risk Rating": "Legacy Rating"}};
    let profileToolCols = new Set(["Status", "Confidence", "Decision Basis", "Additional Signals"]);
    let profileHeaders = overviewCols.map(c => ({{
        label: profileHeaderOverride[c] || c,
        tool: profileToolCols.has(c),
    }}));
    makeTable("entity-profile-table", profileHeaders, profileRows);

    // --- Legacy Profile tab ---
    let legacyHtml = "";
    let irrPillColors = {{
        "critical": "background:#FCEBEB;color:#791F1F;",
        "high":     "background:#FAD8C1;color:#7A2E0F;",
        "medium":   "background:#FAEEDA;color:#633806;",
        "low":      "background:#EAF3DE;color:#27500A;",
    }};
    let controlPillColors = {{
        "well controlled":           "background:#EAF3DE;color:#27500A;",
        "moderately controlled":     "background:#FAEEDA;color:#633806;",
        "insufficiently controlled": "background:#FCEBEB;color:#791F1F;",
    }};
    let legacyIrrPill = v => {{
        let s = String(v||"").trim();
        let lower = s.toLowerCase();
        if (!s || lower === "n/a" || lower === "na" || lower === "not applicable") {{
            return `<span class="pill pill-neutral">${{esc(s || "N/A")}}</span>`;
        }}
        let style = irrPillColors[lower];
        if (!style) return `<span class="pill pill-neutral">${{esc(s)}}</span>`;
        return `<span class="pill" style="${{style}}">${{esc(s)}}</span>`;
    }};
    let legacyControlPill = v => {{
        let s = String(v||"").trim();
        let lower = s.toLowerCase();
        if (!s || lower === "n/a" || lower === "na" || lower === "not applicable") {{
            return `<span class="pill pill-neutral">${{esc(s || "N/A")}}</span>`;
        }}
        let style = controlPillColors[lower];
        if (!style) return `<span class="pill pill-neutral">${{esc(s)}}</span>`;
        return `<span class="pill" style="${{style}}">${{esc(s)}}</span>`;
    }};
    if (legacyRatingsData.length) {{
        let eidCol = legacyRatingsData[0].hasOwnProperty("Entity ID") ? "Entity ID" : (legacyRatingsData[0].hasOwnProperty("Audit Entity ID") ? "Audit Entity ID" : null);
        if (eidCol) {{
            let lr = legacyRatingsData.filter(r => String(r[eidCol]||"").trim() === eid);
            if (lr.length) {{
                let emptyCell = '<span class="empty-cell">\\u2014</span>';
                legacyHtml += '<div class="table-wrap"><table class="legacy-table expandable-rows">';
                legacyHtml += '<colgroup>'
                    + '<col style="width:160px">'
                    + '<col style="width:110px">'
                    + '<col>'
                    + '<col style="width:180px">'
                    + '<col>'
                    + '</colgroup>';
                legacyHtml += '<thead><tr>'
                    + '<th>Risk Pillar</th>'
                    + '<th>Inherent Risk</th>'
                    + '<th>Risk Rationale</th>'
                    + '<th>Control Assessment</th>'
                    + '<th>Control Rationale</th>'
                    + '</tr></thead><tbody>';
                lr.forEach(r => {{
                    let riskRatInner = isEmpty(r["Inherent Risk Rationale"]) ? emptyCell : esc(String(r["Inherent Risk Rationale"]));
                    let ctrlRatInner = isEmpty(r["Control Assessment Rationale"]) ? emptyCell : esc(String(r["Control Assessment Rationale"]));
                    legacyHtml += '<tr onclick="toggleExpandableRow(this)">'
                        + '<td><span class="row-arrow">\\u25B6</span>' + esc(String(r["Risk Pillar"]||"")) + '</td>'
                        + '<td>' + legacyIrrPill(r["Inherent Risk Rating"]) + '</td>'
                        + '<td><div class="truncate-cell">' + riskRatInner + '</div></td>'
                        + '<td>' + legacyControlPill(r["Control Assessment"]) + '</td>'
                        + '<td><div class="truncate-cell">' + ctrlRatInner + '</div></td>'
                        + '</tr>';
                }});
                legacyHtml += '</tbody></table></div>';
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
        let body = renderDrilldownBody(r, detail, entityDetail, eid);
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
    let mkExpander = (open, headerLabel, bodyHtml) => {{
        let cls = open ? "expander open" : "expander";
        return `<div class="${{cls}}"><div class="expander-header" onclick="toggleExpander(this)">
            <span>${{headerLabel}}</span><span class="expander-arrow">\\u25B6</span>
        </div><div class="expander-body">${{bodyHtml}}</div></div>`;
    }};

    // === Scope group ===
    srcHtml += "<h2>Scope</h2>";

    // Inventories (from legacy source data; IDs enriched with inventory lookups)
    let invBody = "";
    let invBodyInitial = invBody;
    let invHeader = "Inventories";
    if (legacyRow) {{
        let splitList = v => String(v||"").split(/[;\\r\\n]+/).map(s => s.trim()).filter(Boolean);
        let plural = (n, s, p) => n + " " + (n === 1 ? s : p);

        let appById = {{}};
        applicationsInventory.forEach(a => {{ let k = String(a[INVENTORY_COLS.appId]||"").trim(); if (k) appById[k] = a; }});
        let pspById = {{}};
        policiesInventory.forEach(p => {{ let k = String(p[INVENTORY_COLS.pspId]||"").trim(); if (k) pspById[k] = p; }});
        let manById = {{}};
        lawsInventory.forEach(m => {{ let k = String(m[INVENTORY_COLS.manId]||"").trim(); if (k) manById[k] = m; }});
        let tpById = {{}};
        thirdpartiesInventory.forEach(t => {{ let k = String(t[INVENTORY_COLS.tpId]||"").trim(); if (k) tpById[k] = t; }});

        let tierRank = {{Primary:0, Secondary:1, Applicable:0, Additional:1}};
        let byTierThenName = (a, b) => {{
            let ta = tierRank[a.tier] ?? 9, tb = tierRank[b.tier] ?? 9;
            if (ta !== tb) return ta - tb;
            return String(a.sortKey||"").localeCompare(String(b.sortKey||""));
        }};

        let primaryApps = splitList(legacyRow[INVENTORY_COLS.legacyPrimaryIT]).filter(x => !isAbsence(x));
        let secondaryApps = splitList(legacyRow[INVENTORY_COLS.legacySecondaryIT]).filter(x => !isAbsence(x));
        let primaryTPs = splitList(legacyRow[INVENTORY_COLS.legacyPrimaryTP]).filter(x => !isAbsence(x));
        let secondaryTPs = splitList(legacyRow[INVENTORY_COLS.legacySecondaryTP]).filter(x => !isAbsence(x));
        let modelList = splitList(legacyRow["Models (View Only)"]).filter(x => !isAbsence(x));
        let policyList = splitList(legacyRow[INVENTORY_COLS.legacyPolicies]).filter(x => !isAbsence(x));
        let lawsApplic = splitList(legacyRow[INVENTORY_COLS.legacyLawsApplic]).filter(x => !isAbsence(x));
        let lawsAdd = splitList(legacyRow[INVENTORY_COLS.legacyLawsAdd]).filter(x => !isAbsence(x));

        let hasApps = primaryApps.length || secondaryApps.length;
        let hasTPs = primaryTPs.length || secondaryTPs.length;
        let hasModels = modelList.length;
        let hasPolicies = policyList.length;
        let hasLaws = lawsApplic.length || lawsAdd.length;

        if (hasApps || hasTPs || hasModels || hasPolicies || hasLaws) {{
            let invCounts = [];
            if (hasApps) invCounts.push(plural(primaryApps.length + secondaryApps.length, "application", "applications"));
            if (hasTPs) invCounts.push(plural(primaryTPs.length + secondaryTPs.length, "third party", "third parties"));
            if (hasModels) invCounts.push(plural(modelList.length, "model", "models"));
            if (hasPolicies) invCounts.push(plural(policyList.length, "policy", "policies"));
            if (hasLaws) invCounts.push(plural(lawsApplic.length + lawsAdd.length, "mandate", "mandates"));
            invHeader = "Inventories \\u2014 " + invCounts.join(", ");

            if (hasApps) {{
                let items = [];
                let pushApp = (id, tier) => {{
                    let rec = appById[id];
                    items.push({{tier, id, rec, sortKey: (rec && rec[INVENTORY_COLS.appName]) || id}});
                }};
                primaryApps.forEach(id => pushApp(id, "Primary"));
                secondaryApps.forEach(id => pushApp(id, "Secondary"));
                items.sort(byTierThenName);
                let body = items.map(r => {{
                    if (!r.rec) return `<tr><td><span class="meta">(not found in applications inventory)</span></td><td>\\u2014</td><td>\\u2014</td><td>\\u2014</td><td>${{esc(r.tier)}}</td><td>${{esc(r.id)}}</td></tr>`;
                    let rec = r.rec;
                    return `<tr><td>${{esc(String(rec[INVENTORY_COLS.appName]||""))}}</td><td>${{severityPill(rec[INVENTORY_COLS.appConfidence]||"")}}</td><td>${{severityPill(rec[INVENTORY_COLS.appAvailability]||"")}}</td><td>${{severityPill(rec[INVENTORY_COLS.appIntegrity]||"")}}</td><td>${{esc(r.tier)}}</td><td>${{esc(r.id)}}</td></tr>`;
                }}).join("");
                invBody += "<h4>Applications</h4>";
                invBody += `<p class="meta">${{plural(items.length, "application", "applications")}} \\u2014 ${{primaryApps.length}} Primary, ${{secondaryApps.length}} Secondary</p>`;
                invBody += `<div class="table-wrap"><table><thead><tr><th>Name</th><th>Confidentiality</th><th>Availability</th><th>Integrity</th><th>Tier</th><th>ID</th></tr></thead><tbody>${{body}}</tbody></table></div>`;
            }}

            if (hasTPs) {{
                let items = [];
                let pushTP = (id, tier) => {{
                    let rec = tpById[id];
                    items.push({{tier, id, rec, sortKey: (rec && rec[INVENTORY_COLS.tpName]) || id}});
                }};
                primaryTPs.forEach(id => pushTP(id, "Primary"));
                secondaryTPs.forEach(id => pushTP(id, "Secondary"));
                items.sort(byTierThenName);
                let body = items.map(r => {{
                    if (!r.rec) return `<tr><td><span class="meta">(not found in third parties inventory)</span></td><td>\\u2014</td><td>${{esc(r.tier)}}</td><td>${{esc(r.id)}}</td></tr>`;
                    let nm = r.rec[INVENTORY_COLS.tpName] || "";
                    let risk = r.rec[INVENTORY_COLS.tpOverallRisk] || "";
                    return `<tr><td>${{esc(String(nm))}}</td><td>${{severityPill(risk)}}</td><td>${{esc(r.tier)}}</td><td>${{esc(r.id)}}</td></tr>`;
                }}).join("");
                invBody += "<h4>Third Parties</h4>";
                invBody += `<p class="meta">${{plural(items.length, "third party", "third parties")}} \\u2014 ${{primaryTPs.length}} Primary, ${{secondaryTPs.length}} Secondary</p>`;
                invBody += `<div class="table-wrap"><table><thead><tr><th>Name</th><th>Overall Risk</th><th>Tier</th><th>TLM ID</th></tr></thead><tbody>${{body}}</tbody></table></div>`;
            }}

            if (hasModels) {{
                let sorted = modelList.slice().sort((a,b) => String(a).localeCompare(String(b)));
                let body = sorted.map(n => `<tr><td>${{esc(n)}}</td></tr>`).join("");
                invBody += "<h4>Models</h4>";
                invBody += `<p class="meta">${{plural(modelList.length, "model", "models")}}</p>`;
                invBody += `<div class="table-wrap"><table><thead><tr><th>Name</th></tr></thead><tbody>${{body}}</tbody></table></div>`;
            }}

            if (hasPolicies) {{
                let items = policyList.map(id => {{
                    let rec = pspById[id];
                    return {{id, rec, sortKey: (rec && rec[INVENTORY_COLS.pspName]) || id}};
                }});
                items.sort((a,b) => String(a.sortKey).localeCompare(String(b.sortKey)));
                let body = items.map(r => {{
                    if (!r.rec) return `<tr><td><span class="meta">(not found in policies inventory)</span></td><td>${{esc(r.id)}}</td></tr>`;
                    return `<tr><td>${{esc(String(r.rec[INVENTORY_COLS.pspName]||""))}}</td><td>${{esc(r.id)}}</td></tr>`;
                }}).join("");
                invBody += "<h4>Policies / Standards / Procedures</h4>";
                invBody += `<p class="meta">${{plural(items.length, "policy", "policies")}}</p>`;
                invBody += `<div class="table-wrap"><table><thead><tr><th>Name</th><th>ID</th></tr></thead><tbody>${{body}}</tbody></table></div>`;
            }}

            if (hasLaws) {{
                let seen = new Set();
                let ids = [];
                [...lawsApplic, ...lawsAdd].forEach(id => {{ if (id && !seen.has(id)) {{ seen.add(id); ids.push(id); }} }});
                let items = ids.map(id => {{
                    let rec = manById[id];
                    return {{id, rec, sortKey: (rec && rec[INVENTORY_COLS.manTitle]) || id}};
                }});
                items.sort((a, b) => String(a.sortKey).localeCompare(String(b.sortKey)));
                let body = items.map(r => {{
                    if (!r.rec) return `<tr onclick="toggleExpandableRow(this)"><td><span class="meta">(not found in mandates inventory)</span></td><td><div class="truncate-cell">\\u2014</div></td><td>${{esc(r.id)}}</td></tr>`;
                    return `<tr onclick="toggleExpandableRow(this)"><td>${{esc(String(r.rec[INVENTORY_COLS.manTitle]||""))}}</td><td><div class="truncate-cell">${{esc(String(r.rec[INVENTORY_COLS.manApplicability]||"\\u2014"))}}</div></td><td>${{esc(r.id)}}</td></tr>`;
                }}).join("");
                invBody += "<h4>Laws & Regulations</h4>";
                invBody += `<p class="meta">${{plural(items.length, "mandate", "mandates")}}</p>`;
                invBody += `<div class="table-wrap"><table class="expandable-rows"><thead><tr><th>Name</th><th>Applicability</th><th>ID</th></tr></thead><tbody>${{body}}</tbody></table></div>`;
            }}
        }}
    }}
    if (invBody === invBodyInitial) invBody += "<p class='meta'>No inventory items for this entity.</p>";
    srcHtml += mkExpander(true, invHeader, invBody);

    // Sub-Risks
    let es = subRisksData.filter(s => String(s["entity_id"]||s["Audit Entity"]||s["Audit Entity ID"]||"").trim() === eid);
    let subHeader = `Sub-Risks \\u2014 ${{es.length}} sub-risk${{es.length === 1 ? "" : "s"}}`;
    let subBody = "";
    if (es.length) {{
        subBody += '<div class="table-wrap"><table><thead><tr><th>Risk ID</th><th>Description</th><th>Legacy L1</th><th>Rating</th><th class="th-tool">L2 Keyword Matches</th></tr></thead><tbody>';
        es.forEach(s => {{
            subBody += `<tr><td>${{s["risk_id"]||s["Key Risk ID"]||""}}</td>
                <td>${{String(s["risk_description"]||s["Key Risk Description"]||"").substring(0,200)}}</td>
                <td>${{s["legacy_l1"]||s["Level 1 Risk Category"]||""}}</td>
                <td>${{s["sub_risk_rating"]||s["Inherent Risk Rating"]||""}}</td>
                <td>${{s["L2 Keyword Matches"]||s["Contributed To (keyword matches)"]||""}}</td></tr>`;
        }});
        subBody += "</tbody></table></div>";
    }} else {{
        subHeader = "Sub-Risks";
        subBody = "<p class='meta'>No sub-risk descriptions for this entity.</p>";
    }}
    srcHtml += mkExpander(true, subHeader, subBody);

    srcHtml += "<div class='divider'></div>";

    // === Issues & Events group ===
    srcHtml += "<h2>Issues & Events</h2>";

    // IAG Issues
    let efAll = findingsData.filter(f => String(f["entity_id"]||f["Audit Entity ID"]||"").trim() === eid);
    let iagHeader = "IAG Issues";
    let iagBody = '<div class="banner banner-warn">Only Approved findings with active statuses (Open, In Validation, In Sustainability) drive L2 applicability. Findings still in L1/L2 review workflow, or with Closed / Cancelled / Not Started status, are listed here for reference but do not fire an "Issue confirmed" decision.</div>';
    if (efAll.length) {{
        iagHeader = `IAG Issues \\u2014 ${{efAll.length}} issue${{efAll.length === 1 ? "" : "s"}}${{severitySummary(efAll, f => f["severity"]||f["Final Reportable Finding Risk Rating"], ["Critical","High","Medium","Low"])}}`;
        iagBody += '<div class="table-wrap"><table class="expandable-rows"><thead><tr><th>Finding ID</th><th>Title</th><th>Description</th><th>Severity</th><th>Status</th><th class="th-tool">L2 Risk</th><th class="th-tool">Mapping Status</th></tr></thead><tbody>';
        efAll.forEach(f => {{
            let fid = String(f["issue_id"]||f["Finding ID"]||"");
            let ftitle = String(f["issue_title"]||f["Finding Name"]||"");
            let fdesc = String(f["Finding Description"]||f["finding_description"]||"");
            iagBody += `<tr onclick="toggleExpandableRow(this)">`
                + `<td>${{esc(fid)}}</td>`
                + `<td><div class="truncate-cell">${{esc(ftitle)}}</div></td>`
                + `<td><div class="truncate-cell">${{esc(fdesc)}}</div></td>`
                + `<td>${{f["severity"]||f["Final Reportable Finding Risk Rating"]||""}}</td>`
                + `<td>${{f["status"]||f["Finding Status"]||""}}</td>`
                + `<td>${{f["l2_risk"]||f["Risk Dimension Categories"]||""}}</td>`
                + `<td>${{f["Mapping Status"]||""}}</td>`
                + `</tr>`;
        }});
        iagBody += "</tbody></table></div>";
    }} else {{
        iagBody += "<p class='meta'>No IAG issues for this entity.</p>";
    }}
    srcHtml += mkExpander(false, iagHeader, iagBody);

    // OREs
    let oreHeader = "Operational Risk Events (OREs)";
    let oreBody = '<div class="banner banner-info">ORE events are mapped to L2 risks by semantic similarity of event title and description to the new taxonomy definitions. Closed and canceled events, and events missing a title or description, are excluded before mapping. All remaining events are shown regardless of mapping status.</div>';
    if (oreData.length) {{
        let oreEidCol = oreData[0].hasOwnProperty("entity_id") ? "entity_id" : (oreData[0].hasOwnProperty("Audit Entity (Operational Risk Events)") ? "Audit Entity (Operational Risk Events)" : (oreData[0].hasOwnProperty("Audit Entity ID") ? "Audit Entity ID" : null));
        if (oreEidCol) {{
            let eo = oreData.filter(o => String(o[oreEidCol]||"").trim() === eid);
            if (eo.length) {{
                oreHeader = `Operational Risk Events (OREs) \\u2014 ${{eo.length}} ORE${{eo.length === 1 ? "" : "s"}}${{severitySummary(eo, o => o["Final Event Classification"], ["Class A","Class B","Class C","Near Miss"])}}`;
                let oreApproved = [
                    {{k:"Event ID"}}, {{k:"Event Title"}}, {{k:"Event Description", trunc:true}},
                    {{k:"Final Event Classification"}}, {{k:"Event Status"}},
                    {{k:"Mapped L2s", label:"Suggested L2s", tool:true, trunc:true}},
                    {{k:"Mapping Status", tool:true}},
                ];
                let cols = oreApproved.filter(c => eo[0].hasOwnProperty(c.k));

                oreBody += '<div class="table-wrap"><table class="expandable-rows"><thead><tr>' + cols.map(c => `<th${{c.tool ? ' class="th-tool"' : ''}}>${{esc(c.label || c.k)}}</th>`).join("") + '</tr></thead><tbody>';
                eo.forEach(o => {{
                    oreBody += '<tr onclick="toggleExpandableRow(this)">' + cols.map(c => {{
                        let val = esc(String(o[c.k]||""));
                        let content = c.trunc ? `<div class="truncate-cell">${{val}}</div>` : val;
                        return `<td>${{content}}</td>`;
                    }}).join("") + '</tr>';
                }});
                oreBody += "</tbody></table></div>";
            }} else {{ oreBody += "<p class='meta'>No OREs for this entity.</p>"; }}
        }} else {{ oreBody += "<p class='meta'>ORE data missing entity ID column.</p>"; }}
    }} else {{ oreBody += "<p class='meta'>No ORE data in workbook.</p>"; }}
    srcHtml += mkExpander(false, oreHeader, oreBody);

    // PRSA Issues
    let prsaHeader = "PRSA Issues";
    let prsaBody = '<div class="banner banner-info">PRSA issues are mapped to L2 risks by semantic similarity of issue text to the new taxonomy definitions. All issues are shown regardless of mapping status.</div>';
    if (prsaData.length) {{
        let prsaEidCol = prsaData[0].hasOwnProperty("AE ID") ? "AE ID" : (prsaData[0].hasOwnProperty("Audit Entity") ? "Audit Entity" : (prsaData[0].hasOwnProperty("Audit Entity ID") ? "Audit Entity ID" : null));
        if (prsaEidCol) {{
            let ep = prsaData.filter(p => String(p[prsaEidCol]||"").trim() === eid);
            if (ep.length) {{
                prsaHeader = `PRSA Issues \\u2014 ${{ep.length}} record${{ep.length === 1 ? "" : "s"}}${{severitySummary(ep, p => p["Issue Rating"], ["Critical","High","Medium","Low"])}}`;
                let prsaApproved = ["PRSA ID", "Issue ID", "Issue Title", "Issue Description", "Control Title", "Process Title", "Issue Rating", "Issue Status", "Control ID (PRSA)", "Other AEs With This PRSA", "Mapped L2s", "Mapping Status"];
                let cols = prsaApproved.filter(c => ep[0].hasOwnProperty(c));

                prsaBody += '<div class="table-wrap"><table><thead><tr>' + cols.map(c => `<th>${{esc(c)}}</th>`).join("") + '</tr></thead><tbody>';
                ep.forEach(p => {{ prsaBody += '<tr>' + cols.map(c => `<td>${{esc(String(p[c]||""))}}</td>`).join("") + '</tr>'; }});
                prsaBody += "</tbody></table></div>";
            }} else {{ prsaBody += "<p class='meta'>No PRSA data for this entity.</p>"; }}
        }} else {{ prsaBody += "<p class='meta'>PRSA data missing entity column.</p>"; }}
    }} else {{ prsaBody += "<p class='meta'>No PRSA data in workbook.</p>"; }}
    srcHtml += mkExpander(false, prsaHeader, prsaBody);

    // GRA RAPs
    let graHeader = "GRA RAPs (Regulatory Findings)";
    let graBody = '<div class="banner banner-info">GRA RAPs are mapped to L2 risks by semantic similarity of RAP header and details to the new taxonomy definitions. All RAPs are shown regardless of mapping status.</div>';
    if (graRapsData.length) {{
        let graEidCol = graRapsData[0].hasOwnProperty("Audit Entity ID") ? "Audit Entity ID" : null;
        if (graEidCol) {{
            let eg = graRapsData.filter(g => String(g[graEidCol]||"").trim() === eid);
            if (eg.length) {{
                graHeader = `GRA RAPs (Regulatory Findings) \\u2014 ${{eg.length}} RAP${{eg.length === 1 ? "" : "s"}}`;
                let graApproved = ["RAP ID", "RAP Header", "RAP Status", "BU Corrective Action Due Date", "RAP Details", "Related Exams and Findings", "GRA RAPS", "Mapped L2s", "Mapping Status"];
                let cols = graApproved.filter(c => eg[0].hasOwnProperty(c));

                graBody += '<div class="table-wrap"><table><thead><tr>' + cols.map(c => `<th>${{esc(c)}}</th>`).join("") + '</tr></thead><tbody>';
                eg.forEach(g => {{ graBody += '<tr>' + cols.map(c => `<td>${{esc(String(g[c]||""))}}</td>`).join("") + '</tr>'; }});
                graBody += "</tbody></table></div>";
            }} else {{ graBody += "<p class='meta'>No GRA RAPs for this entity.</p>"; }}
        }} else {{ graBody += "<p class='meta'>GRA RAPs data missing entity column.</p>"; }}
    }} else {{ graBody += "<p class='meta'>No GRA RAPs data in workbook.</p>"; }}
    srcHtml += mkExpander(false, graHeader, graBody);

    // BM Activities
    let bmaHeader = "Business Monitoring Activities";
    let bmaBody = '<div class="banner banner-warn">Activities with a planned completion date before July 1, 2025 are not shown. See the source workbook for the complete history.</div>';
    if (bmaData.length) {{
        let bmaEidCol = bmaData[0].hasOwnProperty("Related Audit Entity") ? "Related Audit Entity" : (bmaData[0].hasOwnProperty("Audit Entity ID") ? "Audit Entity ID" : null);
        if (bmaEidCol) {{
            let eb = bmaData.filter(b => String(b[bmaEidCol]||"").trim() === eid);
            if (eb.length) {{
                bmaHeader = `Business Monitoring Activities \\u2014 ${{eb.length}} instance${{eb.length === 1 ? "" : "s"}}`;
                let bmaApproved = ["Activity Instance ID", "Related BM Activity Title", "Summary of Results", "If yes, please describe impact", "Business Monitoring Cases", "Planned Instance Completion Date"];
                let cols = bmaApproved.filter(c => eb[0].hasOwnProperty(c));

                bmaBody += '<div class="table-wrap"><table><thead><tr>' + cols.map(c => `<th>${{esc(c)}}</th>`).join("") + '</tr></thead><tbody>';
                eb.forEach(b => {{ bmaBody += '<tr>' + cols.map(c => `<td>${{esc(String(b[c]||""))}}</td>`).join("") + '</tr>'; }});
                bmaBody += "</tbody></table></div>";
            }} else {{ bmaBody += "<p class='meta'>No BM Activities for this entity.</p>"; }}
        }} else {{ bmaBody += "<p class='meta'>BMA data missing entity column.</p>"; }}
    }} else {{ bmaBody += "<p class='meta'>No BM Activities data in workbook.</p>"; }}
    srcHtml += mkExpander(false, bmaHeader, bmaBody);

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
        body += renderDrilldownBody(r, detail, entityDetailRows, eid2);
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