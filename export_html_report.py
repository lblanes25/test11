"""
Static HTML Report Generator (AmEx Branded)

Reads the transformer's Excel output and generates a self-contained, brand-styled
HTML file that can be uploaded to SharePoint and opened in any browser.

Usage:
    python export_html_report.py                      # uses latest output
    python export_html_report.py path/to/output.xlsx  # specific file

Or called from the transformer:
    from export_html_report import generate_html_report
    generate_html_report(excel_path, html_path)
"""

import logging
import pandas as pd
import json
import sys
import yaml
from pathlib import Path
from datetime import datetime

from risk_taxonomy_transformer.utils import latest_input, split_id_list

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent
_CONFIG_PATH = _PROJECT_ROOT / "config" / "taxonomy_config.yaml"
_BANNERS_PATH = _PROJECT_ROOT / "config" / "banners.yaml"


def _load_banners() -> dict:
    """Load static source-tab banner copy from config/banners.yaml.

    Returns the ``source_banners`` mapping: {key: {style, body}}.
    Edit copy in YAML; do not edit banner prose in Python.
    """
    with open(_BANNERS_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    return cfg.get("source_banners", {})


_BANNERS = _load_banners()


def _load_methodology_rows() -> list[list[str]]:
    """Load the LUminate Methodology section from methodology.yaml.

    Returns a flat list of [topic, detail] tuples in display order. Mirrors
    risk_taxonomy_transformer.export._build_methodology_data — we duplicate
    a tiny amount of YAML walking here rather than importing across the
    package boundary so this script stays runnable standalone.
    """
    yaml_path = _PROJECT_ROOT / "risk_taxonomy_transformer" / "methodology.yaml"
    if not yaml_path.exists():
        return []
    with open(yaml_path, "r", encoding="utf-8") as f:
        content = yaml.safe_load(f) or {}

    rows: list[list[str]] = []
    for section in content.get("sections", []):
        if section.get("tab") != "LUminate Methodology":
            continue
        title = section.get("title", "")
        body = section.get("body")
        rows.append([title, ""])
        if body:
            for para in _split_methodology_body(body):
                rows.append(["", para])
        rows.append(["", ""])
    return rows


def _load_provenance_line(excel_path: str) -> str:
    """Read the Run Provenance block from the workbook's Methodology sheet.

    Returns a concise one-line summary (commit · timestamp · spaCy model)
    or "" when the block is absent. The block is written by
    risk_taxonomy_transformer.export as the first rows of the Methodology tab.
    """
    try:
        mdf = pd.read_excel(excel_path, sheet_name="Methodology", header=None)
    except (ValueError, FileNotFoundError):
        return ""
    prov = {}
    for _, row in mdf.iterrows():
        topic = str(row.iloc[0]).strip()
        detail = str(row.iloc[1]).strip() if len(row) > 1 else ""
        if topic in ("Tool commit", "Run timestamp", "spaCy model"):
            prov[topic] = detail
        if topic and topic not in ("Run Provenance", "Tool commit",
                                   "Run timestamp", "spaCy model",
                                   "Library versions", "nan", ""):
            break
    if not prov:
        return ""
    parts = []
    if prov.get("Tool commit"):
        parts.append(f"commit {prov['Tool commit']}")
    if prov.get("Run timestamp"):
        parts.append(prov["Run timestamp"])
    if prov.get("spaCy model"):
        parts.append(f"spaCy {prov['spaCy model']}")
    return " &middot; ".join(parts)


_METHODOLOGY_LABELED_PREFIXES = (
    "Scope.", "Attribution.", "Interpretation.", "Use.", "Caveats.",
    "Failure modes", "Source-specific failure mode",
)


def _split_methodology_body(body: str) -> list[str]:
    """Same split rule as export._split_body_paragraphs (kept in sync)."""
    paragraphs: list[str] = []
    current: list[str] = []

    def _flush() -> None:
        if current:
            paragraphs.append(" ".join(current))
            current.clear()

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            _flush()
            continue
        if line.startswith("- "):
            _flush()
            paragraphs.append("• " + line[2:].strip())
            continue
        if any(line.startswith(p) for p in _METHODOLOGY_LABELED_PREFIXES):
            _flush()
            current.append(line)
            continue
        current.append(line)
    _flush()
    return paragraphs


# Source tabs in the workbook that ship a merged disclosure banner at row 1
# and the column header at row 2. Must mirror _SOURCE_TAB_BANNER_KEYS in
# risk_taxonomy_transformer/export.py.
_BANNER_SOURCE_TABS = frozenset({
    "Source - Findings",
    "Source - OREs",
    "Source - ORE IRM",
    "Source - PRSA Issues",
    "Source - PG Gaps",
    "Source - GRA RAPs",
    "Source - BM Activities",
    "Source - Key Risks",
    "Source - L2 Taxonomy",
    "Source - Models",
    "Source - Legacy Data",
    "Upstream Tagging Gaps",
})


def _banner_html(key: str, format_kwargs: dict | None = None) -> str:
    """Render a banner div from the YAML config by key (e.g. 'iag', 'prsa').

    Banners that contain Python-style ``{placeholder}`` tokens require
    matching keys in ``format_kwargs``. Banners without placeholders are
    unaffected — ``str.format()`` is a no-op on strings with no ``{...}``
    sequences, and existing banner copy contains none.

    If a banner contains a placeholder but the caller doesn't supply the
    matching key, ``str.format()`` raises ``KeyError`` and the exception is
    propagated so the misconfiguration fails loudly rather than emitting a
    raw, unsubstituted ``{placeholder}`` in the rendered HTML. If the YAML
    body ever needs literal braces, escape them as ``{{`` / ``}}``.
    """
    cfg = _BANNERS.get(key)
    if not cfg:
        print(f"  Warning: banners.yaml missing required key: '{key}' - banner will be empty in rendered HTML")
        return ""
    style = cfg.get("style", "info")
    body = cfg.get("body", "").rstrip()
    body = body.format(**(format_kwargs or {}))
    return f'<div class="banner banner-{style}">{body}</div>'


def _banner_body(key: str) -> str:
    """Raw banner body text (no wrapping div) from banners.yaml, for inline append."""
    cfg = _BANNERS.get(key)
    return cfg.get("body", "").rstrip() if cfg else ""


def _safe_json(df: pd.DataFrame) -> str:
    """Convert DataFrame to JSON string, handling NaN and special types."""
    return df.fillna("").to_json(orient="records", date_format="iso")


def _load_inventory(input_dir: Path, pattern: str) -> pd.DataFrame:
    """Load the most recent file matching pattern. Return empty DataFrame if none found.

    Strips whitespace from column headers — Excel exports often carry trailing
    spaces that defeat downstream column-name lookups.
    """
    latest = latest_input(input_dir, [pattern], log_label=pattern)
    if latest is None:
        print(f"  Warning: no files match pattern '{pattern}' - inventory will be empty")
        return pd.DataFrame()
    try:
        df = pd.read_excel(latest)
        df.columns = [str(c).strip() for c in df.columns]
        return df
    except Exception as exc:
        logger.warning(f"  Could not read inventory file {latest.name}: {exc} "
                       f"- inventory will be empty")
        return pd.DataFrame()


# ========================================================================
# COLUMN ALLOWLISTS
# Every DataFrame embedded as JSON is pruned to just the columns the JS
# reads. Each allowlist is the union of every column name referenced in
# the templates/report.js template for the corresponding data source (including snake_case
# / Title Case fallback pairs).
# ========================================================================

ENTITY_META_COLS = [
    "Entity Name", "Entity Overview", "Audit Leader", "PGA", "Core Audit Team",
    "Audit Entity Status",
]

AUDIT_COLS = [
    "Entity ID", "New L1", "New L2", "L2 Definition",
    "Status", "Confidence", "Inherent Risk Rating",
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

# IRM ORE columns sourced from the Excel "Source - ORE IRM" tab. Headers
# are user-facing IRM labels (per columns.ore_irm in YAML). Tool-added
# columns include L2 Source, Mapped L2s, Mapping Status.
ORE_IRM_COLS = [
    "ORE ID", "ORE Title", "Capture Status", "ORE Rating",
    "Identified By", "Identified By Sub-Group", "ORE Owner Business Unit (L1, L2, L3)",
    "ORE Description", "ORE Root Cause",
    "Root Cause Description", "Root Cause Level 1", "Root Cause Level 2",
    "Risk Level 2", "Risk Level 4",
    "Remediation ID", "Legacy Event ID",
    # Tool-added.
    "L2 Source", "Mapped L2s", "Mapping Status",
]

PRSA_COLS = [
    "AE ID", "Audit Entity", "Audit Entity ID",
    "PRSA ID", "Issue ID", "Issue Title", "Issue Description",
    "Control Title", "Process Title",
    "Issue Rating", "Issue Status",
    "Control ID (PRSA)", "Other AEs With This PRSA",
    "Mapped L2s", "Mapping Status",
    # Track B: filer-tagged vs mapper-inferred L2 provenance per issue.
    # Header text is a placeholder ("L2 Source") — audit-leader picks final
    # display text. Values are 'source' or 'mapper' (lowercase for now).
    "L2 Source",
    # Track C: PG flag carried through so the JS pill renderer can opt into
    # the PG-gap data attribute on a per-issue basis without re-reading the
    # PG Gaps tab.
    "Is PG Gap",
]

PG_GAP_COLS = [
    "Issue ID", "Issue Rating", "Issue Status",
    "Issue Title", "Issue Description",
    "Risk Level 2", "Is PG Gap",
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


def _collect_model_ids(legacy_df: pd.DataFrame, models_col: str) -> set:
    """Extract numeric model IDs (>=4 consecutive digits) from semicolon-separated chunks.

    Production format: each chunk is `<name>-<numeric-ID>-<extra>`. We extract
    every >=4-digit numeric token per chunk; downstream `_filter_inventory`
    discards tokens that don't match an inventory row, so stray years or
    version numbers are harmless.
    """
    ids = set()
    if legacy_df is None or legacy_df.empty or models_col not in legacy_df.columns:
        return ids
    import re
    for val in legacy_df[models_col].dropna().tolist():
        s = str(val).strip()
        if not s or s.lower() in ("nan", "none"):
            continue
        for part in re.split(r"[;\r\n]+", s):
            part = part.strip()
            if not part or part.lower() in ("nan", "none", "n/a", "not applicable", "not available"):
                continue
            for tok in re.findall(r"\d{2,}", part):
                ids.add(tok)
    return ids


def _norm_id_series(s: pd.Series) -> pd.Series:
    """Normalize an ID column to clean strings so isin() matches reliably.

    Excel columns load as float64 when any cell is blank, so int IDs come
    through as "1178.0" via astype(str) and miss when compared to legacy-
    derived "1178". Strip the trailing ".0" for numeric-looking values.
    """
    out = s.astype(str).str.strip()
    out = out.str.replace(r"\.0+$", "", regex=True)
    return out


def _filter_inventory(df: pd.DataFrame, id_column: str, id_set: set,
                       label: str = "inventory") -> pd.DataFrame:
    """Keep only rows whose id_column value is in id_set. Empty id_set => empty df.

    Logs a warning if the column is missing (config mismatch) or if every
    row gets filtered out despite a non-empty id_set (likely dtype mismatch).
    """
    if df is None or df.empty:
        return df
    if not id_column or id_column not in df.columns:
        if df is not None and not df.empty and id_column:
            print(f"  Warning: {label} file has no column {id_column!r} — "
                  f"check YAML config vs. actual headers. Available: {list(df.columns)}")
        return df
    if not id_set:
        return df.iloc[0:0]
    mask = _norm_id_series(df[id_column]).isin(id_set)
    if mask.sum() == 0 and len(df) > 0:
        sample_inv = _norm_id_series(df[id_column]).head(5).tolist()
        sample_ref = list(id_set)[:5]
        print(f"  Warning: {label} filtered to 0 rows — none of "
              f"{len(id_set)} referenced ID(s) matched any of {len(df)} "
              f"inventory row(s). "
              f"Inventory sample: {sample_inv}  Referenced sample: {sample_ref}")
    return df[mask]



# ========================================================================
# EMBEDDED ASSETS (CSS / HTML body template / JS)
# Stored verbatim in templates/ (report.css, report_body.html, report.js)
# and loaded at generation time. Placeholders (__NAME__) are substituted
# inside generate_html_report().
# ========================================================================

_TEMPLATES_DIR = _PROJECT_ROOT / "templates"


def _load_template(filename: str) -> str:
    """Read an embedded-asset template (CSS / HTML body / JS) from templates/.

    Templates are stored verbatim with __NAME__ placeholders; substitution
    happens via .replace() in generate_html_report() (no brace escaping).
    """
    return (_TEMPLATES_DIR / filename).read_text(encoding="utf-8")


def _read_workbook_sheets(excel_path: str) -> dict:
    """Read the report's source sheets from the transformer workbook.

    Returns {sheet_name: DataFrame}. Banner-bearing "Source - *" tabs are
    read with header=1; Audit_Review display renames and the
    "PG Gap" -> "Is PG Gap" restore are applied here.
    """
    sheets = {}
    xls = pd.ExcelFile(excel_path)
    for name in ["Audit_Review", "Side_by_Side",
                 "Findings_Source", "Sub_Risks_Source",
                 "Source - Findings", "Source - Key Risks",
                 "Source - Legacy Data", "Source - OREs",
                 "Source - ORE IRM",
                 "Source - PRSA Issues",
                 "Source - PG Gaps",
                 "Source - BM Activities",
                 "Source - GRA RAPs",
                 "Legacy Ratings Lookup",
                 "Legacy_Ratings_Lookup",
                 "Key_Inventory"]:
        if name in xls.sheet_names:
            # All "Source - *" tabs that ship a merged disclosure banner have
            # the column header at row 2 (row 1 is the banner). Non-source
            # sheets and any "Source - *" tab without a banner stay at row 1.
            if name in _BANNER_SOURCE_TABS:
                df = pd.read_excel(xls, sheet_name=name, header=1)
            else:
                df = pd.read_excel(xls, sheet_name=name)
            if name == "Audit_Review":
                df = df.rename(columns={"Suggested Status": "Status",
                                        "Legacy Risk Rating": "Inherent Risk Rating"})
            # Track C: Excel sheet headers carry the audit-leader display label
            # "PG Gap"; the HTML reader's allowlists (PRSA_COLS / PG_GAP_COLS)
            # and JS lookups (p["Is PG Gap"]) use the original internal name.
            # Restore the internal name on read so the projection step doesn't
            # silently drop the column and the chip/drill-down stay populated.
            if name in ("Source - PRSA Issues", "Source - PG Gaps"):
                if "PG Gap" in df.columns and "Is PG Gap" not in df.columns:
                    df = df.rename(columns={"PG Gap": "Is PG Gap"})
            sheets[name] = df
    return sheets


def _lift_method_columns(audit_df: pd.DataFrame, detail_df: pd.DataFrame) -> pd.DataFrame:
    """Merge Method + Decision Type onto Audit_Review records from Side_by_Side.

    Diagnostic columns moved off Audit_Review (auditors don't read them) but
    the HTML report's decision-type chips at renderDecisionBasisCell still
    need them. Side_by_Side is row-aligned with Audit_Review (sorted same
    way in export.py); we still join on (entity_id, new_l2) for safety.
    """
    if not audit_df.empty and not detail_df.empty:
        if {"entity_id", "new_l2"}.issubset(detail_df.columns):
            cols_to_lift = [c for c in ("method", "decision_type") if c in detail_df.columns]
            if cols_to_lift and "Entity ID" in audit_df.columns and "New L2" in audit_df.columns:
                lift = detail_df[["entity_id", "new_l2"] + cols_to_lift].rename(
                    columns={"entity_id": "Entity ID", "new_l2": "New L2",
                             "method": "Method", "decision_type": "Decision Type"}
                )
                # Drop duplicate (Entity ID, New L2) keys defensively before merge
                lift = lift.drop_duplicates(subset=["Entity ID", "New L2"], keep="first")
                audit_df = audit_df.merge(lift, on=["Entity ID", "New L2"], how="left")
    return audit_df


def _prep_key_inventory(key_inventory_df: pd.DataFrame) -> dict:
    """Convert Key_Inventory sheet into a JS-friendly dict:
    {eid: {keyApps: [...], keyTps: [...], orphanApps: [...], orphanTps: [...]}}
    """
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
    return key_inventory_dict


def _load_inventories() -> tuple[dict, dict]:
    """Load inventory source files (apps, policies, laws, third parties,
    models) directly from data/input/.

    Returns ({source_key: DataFrame}, col_cfg) where col_cfg is the
    ``columns:`` section of taxonomy_config.yaml ({} when unreadable).
    """
    input_dir = _PROJECT_ROOT / "data" / "input"
    inventory_patterns = {"applications": "all_applications_*.xlsx",
                          "policies": "policystandardprocedure_*.xlsx",
                          "laws": "lawsandapplicability_*.xlsx",
                          "thirdparties": "all_thirdparties_*.xlsx",
                          "models": "model_inventory_*.xlsx"}
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            _cfg = yaml.safe_load(f) or {}
        _col_cfg = _cfg.get("columns", {})
        inventory_patterns = {k: _col_cfg.get("inventory_files", {}).get(k, v)
                              for k, v in inventory_patterns.items()}
    except Exception:
        _col_cfg = {}
    inventory_dfs = {key: _load_inventory(input_dir, pattern)
                     for key, pattern in inventory_patterns.items()}
    return inventory_dfs, _col_cfg


def _parse_run_timestamp(excel_path: str) -> str:
    """Parse the run timestamp from the workbook filename."""
    stem = Path(excel_path).stem
    ts_str = stem.replace("transformed_risk_taxonomy_", "")
    try:
        dt = datetime.strptime(ts_str, "%m%d%Y%I%M%p")
        return dt.strftime("%B %d, %Y %I:%M %p").replace(" 0", " ")
    except ValueError:
        return ts_str


def _build_inventory_cols(col_cfg: dict) -> dict:
    """Resolve inventory / legacy column names from the ``columns:`` config
    section, with fallback defaults."""
    apps_inv_cfg = col_cfg.get("applications_inventory", {})
    policies_inv_cfg = col_cfg.get("policies_inventory", {})
    laws_inv_cfg = col_cfg.get("laws_inventory", {})
    tp_inv_cfg = col_cfg.get("thirdparties_inventory", {})
    model_inv_cfg = col_cfg.get("model_inventory", {})
    legacy_apps_cfg = col_cfg.get("applications", {})
    legacy_pl_cfg = col_cfg.get("policies_laws", {})
    return {
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
        "modelId": model_inv_cfg.get("id", "Model ID"),
        "modelName": model_inv_cfg.get("name", "Model Name"),
        "modelMarkets": model_inv_cfg.get("markets", "Markets"),
        "modelImpact": model_inv_cfg.get("impact", "Model Impact Category"),
        "modelClass": model_inv_cfg.get("model_class", "Model Class"),
        "legacyPrimaryIT": legacy_apps_cfg.get("primary_it", "PRIMARY IT APPLICATIONS (MAPPED)"),
        "legacySecondaryIT": legacy_apps_cfg.get("secondary_it", "SECONDARY IT APPLICATIONS (RELATED OR RELIED ON)"),
        "legacyPrimaryTP": legacy_apps_cfg.get("primary_tp", "PRIMARY TLM THIRD PARTY ENGAGEMENT"),
        "legacySecondaryTP": legacy_apps_cfg.get("secondary_tp", "SECONDARY TLM THIRD PARTY ENGAGEMENTS (RELATED OR RELIED ON)"),
        "legacyModels": col_cfg.get("applications", {}).get("models", "Models"),
        "legacyPolicies": legacy_pl_cfg.get("policies", "POLICIES/STANDARDS/PROCEDURES"),
        "legacyLawsApplic": legacy_pl_cfg.get("laws_applicable", "Laws & Regulations Applicability"),
        "legacyLawsAdd": legacy_pl_cfg.get("laws_additional", "Additional Laws or Regulatory Compliance"),
    }


def _build_entity_meta(audit_df: pd.DataFrame, legacy_df: pd.DataFrame) -> dict:
    """Build entity metadata map (Entity ID -> {field: value}) before pruning
    columns from audit_df. Hoisted fields are constant per entity and get
    embedded once, not per-row.
    """
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
    return entity_meta


def _build_ore_irm_rows(ore_irm_df: pd.DataFrame, legacy_df: pd.DataFrame,
                        col_cfg: dict) -> list[dict]:
    """Build the IRM half of the combined ORE JS data array.

    IRM rows are normalized to the legacy ORE column shape so existing JS
    (resolveCol, _oreImpactItems, etc.) doesn't need branchy fallbacks. Each
    IRM row carries an `ore_source: "IRM"` discriminator so legacy-only
    filters can opt out.
    """
    ore_irm_rows_js: list[dict] = []
    if ore_irm_df is not None and not ore_irm_df.empty and not legacy_df.empty:
        # Per-ORE metadata lookup keyed off ORE ID (the column header from the
        # Source - ORE IRM tab is "ORE ID", set by columns.ore_irm in YAML).
        irm_ore_id_col = "ORE ID"
        irm_meta_by_id = {}
        if irm_ore_id_col in ore_irm_df.columns:
            for _, r in ore_irm_df.iterrows():
                oid = str(r.get(irm_ore_id_col, "")).strip()
                if oid:
                    irm_meta_by_id[oid] = r.to_dict()

        # Build (eid, ore_id, mapped_l2_string) tuples by reading the legacy
        # IRM ORE ID column (newline-delimited list per AE).
        irm_legacy_col = col_cfg.get("legacy_extras", {}).get("irm_ore_id", "IRM ORE")
        legacy_eid_col = "Audit Entity ID"
        if irm_legacy_col in legacy_df.columns and legacy_eid_col in legacy_df.columns:
            seen_by_eid: dict[str, set] = {}
            for _, lrow in legacy_df.iterrows():
                eid = str(lrow.get(legacy_eid_col, "")).strip()
                if not eid or eid.lower() in ("nan", "none"):
                    continue
                seen_oids = seen_by_eid.setdefault(eid, set())
                for oid in split_id_list(lrow.get(irm_legacy_col, "")):
                    if oid in seen_oids:
                        continue
                    seen_oids.add(oid)
                    meta = irm_meta_by_id.get(oid)
                    if meta is None:
                        continue
                    meta_ci = {str(k).strip().lower(): k for k in meta.keys()}

                    def _g(key):
                        actual = key if key in meta else meta_ci.get(str(key).strip().lower())
                        v = meta.get(actual, "") if actual is not None else ""
                        if v is None or (isinstance(v, float) and pd.isna(v)):
                            return ""
                        return v
                    cap_status = _g("Capture Status")
                    ore_irm_rows_js.append({
                        "Audit Entity ID": eid,
                        "Event ID": _g("ORE ID"),
                        "Event Title": _g("ORE Title"),
                        "Event Description": _g("ORE Description"),
                        "Final Event Classification": "",  # IRM has no severity class
                        "Event Status": cap_status,
                        "Mapped L2s": _g("Mapped L2s"),
                        "Mapping Status": _g("Mapping Status"),
                        "ore_source": "IRM",
                        "Capture Status": cap_status,
                        "RCA Status": _g("RCA Status"),
                        "Impact Assessment Status": _g("Impact Assessment Status"),
                        "Stop Ongoing Impact Status": _g("Stop Ongoing Impact Status"),
                        "ORE Category": _g("ORE Category"),
                        "ORE Status": _g("ORE Status"),
                        "ORE Materiality": _g("ORE Materiality"),
                        "ORE Rating": _g("ORE Rating"),
                        "Identified By": _g("Identified By"),
                        "Identified By Sub-Group": _g("Identified By Sub-Group"),
                        "ORE Owner Business Unit (L1, L2, L3)": _g("ORE Owner Business Unit (L1, L2, L3)"),
                        "ORE Root Cause": _g("ORE Root Cause"),
                        "Root Cause Description": _g("Root Cause Description"),
                        "Root Cause Level 1": _g("Root Cause Level 1"),
                        "Root Cause Level 2": _g("Root Cause Level 2"),
                        "Risk Level 2": _g("Risk Level 2"),
                        "Risk Level 4": _g("Risk Level 4"),
                        "Remediation ID": _g("Remediation ID"),
                        "Legacy Event ID": _g("Legacy Event ID"),
                        "L2 Source": _g("L2 Source"),
                    })
    return ore_irm_rows_js


def _filter_inventories(inventory_dfs: dict, legacy_df: pd.DataFrame,
                        inventory_cols: dict) -> dict:
    """Row-filter inventories to only IDs referenced by the legacy rows we have."""
    app_ids = _collect_inventory_ids(legacy_df, [inventory_cols["legacyPrimaryIT"], inventory_cols["legacySecondaryIT"]])
    tp_ids = _collect_inventory_ids(legacy_df, [inventory_cols["legacyPrimaryTP"], inventory_cols["legacySecondaryTP"]])
    policy_ids = _collect_inventory_ids(legacy_df, [inventory_cols["legacyPolicies"]])
    law_ids = _collect_inventory_ids(legacy_df, [inventory_cols["legacyLawsApplic"], inventory_cols["legacyLawsAdd"]])
    model_ids = _collect_model_ids(legacy_df, inventory_cols["legacyModels"])
    return {
        "applications": _filter_inventory(inventory_dfs["applications"], inventory_cols["appId"], app_ids, "Applications inventory"),
        "thirdparties": _filter_inventory(inventory_dfs["thirdparties"], inventory_cols["tpId"], tp_ids, "Third parties inventory"),
        "policies": _filter_inventory(inventory_dfs["policies"], inventory_cols["pspId"], policy_ids, "Policies inventory"),
        "laws": _filter_inventory(inventory_dfs["laws"], inventory_cols["manId"], law_ids, "Laws inventory"),
        "models": _filter_inventory(inventory_dfs["models"], inventory_cols["modelId"], model_ids, "Models inventory"),
    }


def _build_substitutions(*, excel_path: str,
                         audit_df: pd.DataFrame, detail_df: pd.DataFrame,
                         findings_df: pd.DataFrame, key_risks_df: pd.DataFrame,
                         ore_df: pd.DataFrame, ore_irm_df: pd.DataFrame,
                         prsa_df: pd.DataFrame, pg_gap_df: pd.DataFrame,
                         bma_df: pd.DataFrame, gra_raps_df: pd.DataFrame,
                         legacy_ratings_df: pd.DataFrame, legacy_df: pd.DataFrame,
                         inventory_dfs: dict, inventory_cols: dict, col_cfg: dict,
                         key_inventory_dict: dict, entity_meta: dict,
                         run_timestamp: str) -> tuple[dict, dict]:
    """Build the placeholder -> value substitution maps for the JS and HTML
    body templates.

    Returns (js_subs, body_subs); insertion order preserves the original
    .replace() chain order.
    """
    # Org filter values (pulled before audit_df is column-pruned)
    audit_leaders = sorted([str(x) for x in audit_df["Audit Leader"].dropna().unique() if str(x) != "nan"]) if "Audit Leader" in audit_df.columns else []
    pgas = sorted([str(x) for x in audit_df["PGA"].dropna().unique() if str(x) != "nan"]) if "PGA" in audit_df.columns else []
    core_teams = sorted([str(x) for x in audit_df["Core Audit Team"].dropna().unique() if str(x) != "nan"]) if "Core Audit Team" in audit_df.columns else []

    # Get unique values for filters
    entities = sorted(audit_df["Entity ID"].unique().tolist()) if "Entity ID" in audit_df.columns else []
    l2_risks = sorted(audit_df["New L2"].unique().tolist()) if "New L2" in audit_df.columns else []

    total_rows = len(audit_df)
    total_entities = audit_df["Entity ID"].nunique() if "Entity ID" in audit_df.columns else 0

    # Legacy column allowlist: static set + configured inventory columns
    legacy_cols = list(LEGACY_STATIC_COLS) + [
        inventory_cols["legacyPrimaryIT"], inventory_cols["legacySecondaryIT"],
        inventory_cols["legacyModels"],
        inventory_cols["legacyPrimaryTP"], inventory_cols["legacySecondaryTP"],
        inventory_cols["legacyPolicies"],
        inventory_cols["legacyLawsApplic"], inventory_cols["legacyLawsAdd"],
    ]

    # Embed data as JSON (pruned to columns the JS actually reads)
    audit_json = _safe_json(_project_cols(audit_df, AUDIT_COLS))
    detail_json = _safe_json(_project_cols(detail_df, DETAIL_COLS))
    findings_json = _safe_json(_project_cols(findings_df, FINDINGS_COLS))
    key_risks_json = _safe_json(_project_cols(key_risks_df, SUB_RISKS_COLS))
    # Build the combined ORE JS data array: IRM rows first (per Lu spec),
    # legacy ORE rows second.
    ore_irm_rows_js = _build_ore_irm_rows(ore_irm_df, legacy_df, col_cfg)
    ore_legacy_rows_js = json.loads(_safe_json(_project_cols(ore_df, ORE_COLS)))
    # IRM first, legacy second — matches the per-(entity, l2) drill-down ordering.
    ore_combined = ore_irm_rows_js + ore_legacy_rows_js
    ore_json = json.dumps(ore_combined, default=str)
    prsa_json = _safe_json(_project_cols(prsa_df, PRSA_COLS))
    pg_gap_json = _safe_json(_project_cols(pg_gap_df, PG_GAP_COLS))
    bma_json = _safe_json(_project_cols(bma_df, BMA_COLS))
    gra_raps_json = _safe_json(_project_cols(gra_raps_df, GRA_RAPS_COLS))
    legacy_ratings_json = _safe_json(_project_cols(legacy_ratings_df, LEGACY_RATINGS_COLS))
    legacy_json = _safe_json(_project_cols(legacy_df, legacy_cols))
    applications_inventory_json = _safe_json(inventory_dfs["applications"])
    policies_inventory_json = _safe_json(inventory_dfs["policies"])
    laws_inventory_json = _safe_json(inventory_dfs["laws"])
    thirdparties_inventory_json = _safe_json(inventory_dfs["thirdparties"])
    models_inventory_json = _safe_json(inventory_dfs["models"])

    entity_meta_json = json.dumps(entity_meta, default=str)

    js_subs = {
        "__AUDIT_JSON__": audit_json,
        "__DETAIL_JSON__": detail_json,
        "__FINDINGS_JSON__": findings_json,
        "__SUB_RISKS_JSON__": key_risks_json,
        "__ORE_JSON__": ore_json,
        "__PRSA_JSON__": prsa_json,
        "__PG_GAP_JSON__": pg_gap_json,
        "__BMA_JSON__": bma_json,
        "__GRA_RAPS_JSON__": gra_raps_json,
        "__LEGACY_RATINGS_JSON__": legacy_ratings_json,
        "__LEGACY_JSON__": legacy_json,
        "__APPS_INV_JSON__": applications_inventory_json,
        "__POLICIES_INV_JSON__": policies_inventory_json,
        "__LAWS_INV_JSON__": laws_inventory_json,
        "__TP_INV_JSON__": thirdparties_inventory_json,
        "__MODELS_INV_JSON__": models_inventory_json,
        "__INVENTORY_COLS_JSON__": json.dumps(inventory_cols),
        "__ENTITIES_JSON__": json.dumps(entities),
        "__L2_RISKS_JSON__": json.dumps(l2_risks),
        "__AUDIT_LEADERS_JSON__": json.dumps(audit_leaders),
        "__PGAS_JSON__": json.dumps(pgas),
        "__CORE_TEAMS_JSON__": json.dumps(core_teams),
        "__ENTITY_META_JSON__": entity_meta_json,
        "__KEY_INVENTORY_JSON__": json.dumps(key_inventory_dict),
        # LUminate Methodology view rows — sourced from methodology.yaml.
        "__METHODOLOGY_ROWS_JSON__": json.dumps(_load_methodology_rows()),
        # Static prose banners loaded from config/banners.yaml. JSON-encoded
        # so the rendered HTML (with embedded <strong>, quotes, em-dashes)
        # becomes a valid JS string literal when substituted.
        "__BANNER_IAG_JSON__":     json.dumps(_banner_html("iag")),
        "__BANNER_ORE_JSON__":     json.dumps(_banner_html("ore")),
        "__BANNER_PRSA_JSON__":    json.dumps(_banner_html("prsa")),
        "__BANNER_PG_GAP_JSON__":  json.dumps(_banner_html("pg_gap")),
        "__BANNER_GRA_RAP_JSON__": json.dumps(_banner_html("gra_rap")),
        "__BANNER_BMA_JSON__":     json.dumps(_banner_html("bma")),
        "__BANNER_ORE_IRM_ENTITY_JSON__": json.dumps(_banner_html("ore_irm_entity")),
        "__UNMAPPED_SUFFIX_JSON__": json.dumps(_banner_body("unmapped_suffix")),
    }

    body_subs = {
        "__RUN_TIMESTAMP__": str(run_timestamp),
        "__TOTAL_ENTITIES__": str(total_entities),
        "__TOTAL_ROWS__": str(total_rows),
        "__PROVENANCE_LINE__": _load_provenance_line(excel_path) or "unavailable",
    }
    return js_subs, body_subs


def _substitute(template: str, substitutions: dict) -> str:
    """Apply __PLACEHOLDER__ -> value replacements in insertion order.

    We use .replace() rather than f-strings so embedded CSS/JS (with their
    own { } braces) don't need to be doubly escaped.
    """
    for token, value in substitutions.items():
        template = template.replace(token, value)
    return template


def _assemble_html(js_subs: dict, body_subs: dict) -> str:
    """Assemble the final self-contained HTML document from the templates."""
    js_body = _substitute(_load_template("report.js"), js_subs)
    html_body = _substitute(_load_template("report_body.html"), body_subs)
    return (
        '<!DOCTYPE html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        '<title>LUminate</title>\n'
        '<link href="https://fonts.googleapis.com/css2?family=Source+Sans+Pro:wght@300;400;600;700&family=Source+Code+Pro:wght@400;600&display=swap" rel="stylesheet">\n'
        '<style>\n' + _load_template("report.css") + '\n</style>\n'
        '</head>\n'
        '<body>\n'
        + html_body +
        '\n<script>\n' + js_body + '\n</script>\n'
        '</body>\n'
        '</html>\n'
    )


def generate_html_report(excel_path: str, html_path: str):
    """Generate a self-contained HTML report from the transformer output Excel."""

    # Read sheets from the transformer workbook
    sheets = _read_workbook_sheets(excel_path)

    audit_df = sheets.get("Audit_Review", pd.DataFrame())
    detail_df = sheets.get("Side_by_Side", pd.DataFrame())
    audit_df = _lift_method_columns(audit_df, detail_df)

    # Support both old and new sheet names for findings/key risks
    findings_df = sheets.get("Source - Findings", sheets.get("Findings_Source", pd.DataFrame()))
    key_risks_df = sheets.get("Source - Key Risks", sheets.get("Sub_Risks_Source", pd.DataFrame()))
    ore_df = sheets.get("Source - OREs", pd.DataFrame())
    ore_irm_df = sheets.get("Source - ORE IRM", pd.DataFrame())
    prsa_df = sheets.get("Source - PRSA Issues", pd.DataFrame())
    pg_gap_df = sheets.get("Source - PG Gaps", pd.DataFrame())
    bma_df = sheets.get("Source - BM Activities", pd.DataFrame())
    gra_raps_df = sheets.get("Source - GRA RAPs", pd.DataFrame())
    legacy_ratings_df = sheets.get("Legacy Ratings Lookup", sheets.get("Legacy_Ratings_Lookup", pd.DataFrame()))
    legacy_df = sheets.get("Source - Legacy Data", pd.DataFrame())
    key_inventory_df = sheets.get("Key_Inventory", pd.DataFrame())

    key_inventory_dict = _prep_key_inventory(key_inventory_df)
    inventory_dfs, col_cfg = _load_inventories()
    run_timestamp = _parse_run_timestamp(excel_path)
    inventory_cols = _build_inventory_cols(col_cfg)
    entity_meta = _build_entity_meta(audit_df, legacy_df)
    inventory_dfs = _filter_inventories(inventory_dfs, legacy_df, inventory_cols)

    js_subs, body_subs = _build_substitutions(
        excel_path=excel_path,
        audit_df=audit_df, detail_df=detail_df,
        findings_df=findings_df, key_risks_df=key_risks_df,
        ore_df=ore_df, ore_irm_df=ore_irm_df,
        prsa_df=prsa_df, pg_gap_df=pg_gap_df,
        bma_df=bma_df, gra_raps_df=gra_raps_df,
        legacy_ratings_df=legacy_ratings_df, legacy_df=legacy_df,
        inventory_dfs=inventory_dfs, inventory_cols=inventory_cols,
        col_cfg=col_cfg,
        key_inventory_dict=key_inventory_dict, entity_meta=entity_meta,
        run_timestamp=run_timestamp,
    )

    html = _assemble_html(js_subs, body_subs)

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
        latest = latest_input(output_dir, ["transformed_risk_taxonomy_*.xlsx"],
                              log_label="transformer output")
        if latest is None:
            print("No transformer output found in data/output/")
            sys.exit(1)
        excel_path = str(latest)

    stem = Path(excel_path).stem
    ts = stem.replace("transformed_risk_taxonomy_", "")
    html_path = str(output_dir / f"risk_taxonomy_report_{ts}.html")

    generate_html_report(excel_path, html_path)
