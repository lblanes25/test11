"""
Main entrypoint for the Risk Taxonomy Transformer.

Configures file paths, loads all data sources, runs the transformation
pipeline, and exports the multi-sheet Excel output.

Usage:
    python -m risk_taxonomy_transformer
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from risk_taxonomy_transformer.config import get_config, TransformContext
from risk_taxonomy_transformer.enrichment import derive_control_effectiveness, derive_inherent_risk_rating
from risk_taxonomy_transformer.export import export_results
from risk_taxonomy_transformer.flags import (
    flag_application_applicability,
    flag_auxiliary_risks,
    flag_control_contradictions,
    flag_core_risks,
    flag_cross_boundary_signals,
)
from risk_taxonomy_transformer.ingestion import (
    build_findings_index,
    build_ore_index,
    build_ore_irm_mapping_index,
    build_pg_gap_index,
    build_pg_gap_index_from_pg_team,
    build_prsa_mapping_index,
    build_rap_mapping_index,
    build_key_inventory,
    build_key_risk_index,
    ingest_crosswalk,
    ingest_findings,
    ingest_legacy_data,
    ingest_ore_mappings,
    ingest_ore_irm_source,
    ingest_ore_irm_mappings,
    ingest_pg_team_inputs,
    ingest_prsa_mappings,
    ingest_rap_mappings,
    ingest_bma,
    ingest_gra_raps,
    ingest_prsa,
    ingest_rco_overrides,
    ingest_optro_overrides,
    ingest_key_risks,
    load_overrides,
    merge_pg_gap_indexes,
)
from risk_taxonomy_transformer.optro import (
    assess_optro_coverage,
    apply_optro_overrides,
    detect_optro_conflicts,
)
from risk_taxonomy_transformer.pipeline import run_pipeline
from risk_taxonomy_transformer.utils import log_run_provenance

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(_PROJECT_ROOT / "logs" / "transform_log.txt", mode="w"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# File discovery helper (Phase 5 extraction)
# ---------------------------------------------------------------------------

def _resolve_input_paths(input_dir: Path, output_dir: Path, col_cfg: dict) -> dict:
    """Discover and resolve all input file paths from the input directory.

    Returns a dict with keys: legacy_data_path, key_risk_path, override_path,
    findings_path, key_risk_cols, findings_cols, pillar_columns, entity_id_col.
    """
    # Find the most recent legacy data file (filename includes variable datetime)
    legacy_files = sorted(
        list(input_dir.glob("legacy_risk_data_*.xlsx")) +
        list(input_dir.glob("legacy_risk_data_*.csv")),
        key=lambda f: f.stat().st_mtime,
    )
    if not legacy_files:
        raise FileNotFoundError(f"No legacy_risk_data_*.xlsx or .csv found in {input_dir}")
    legacy_data_path = str(legacy_files[-1])  # most recent
    logger.info(f"Using legacy data file: {legacy_data_path}")

    entity_id_col = col_cfg.get("entity_id", "Audit Entity ID")

    # Key risk file (optional but recommended for accuracy).
    # Accepts both new "key_risks_*" filenames and legacy "sub_risk_descriptions_*"
    # filenames so existing inputs keep working after the 2026-05-02 rename.
    key_risk_files = sorted(
        list(input_dir.glob("key_risks_*.xlsx")) +
        list(input_dir.glob("key_risks_*.csv")) +
        list(input_dir.glob("sub_risk_descriptions_*.xlsx")) +
        list(input_dir.glob("sub_risk_descriptions_*.csv")),
        key=lambda f: f.stat().st_mtime,
    )
    key_risk_path = str(key_risk_files[-1]) if key_risk_files else None
    if key_risk_path:
        logger.info(f"Using key risk file: {key_risk_path}")
    else:
        logger.info("No key_risks_*.xlsx or .csv found \u2014 skipping key risk lookup")
    _sr_cfg = col_cfg.get("key_risks", {})
    key_risk_cols = {
        "entity_id": _sr_cfg.get("entity_id", "Audit Entity ID"),
        "risk_id": _sr_cfg.get("risk_id", "Key Risk ID"),
        "risk_desc": _sr_cfg.get("risk_description", "Key Risk Description"),
        "legacy_l1": _sr_cfg.get("legacy_l1", "Level 1 Risk Category"),
        "rating": _sr_cfg.get("rating", "Inherent Risk Rating"),
        "key_applications": _sr_cfg.get("key_applications", "KEY PRIMARY & SECONDARY IT APPLICATIONS"),
        "key_thirdparties": _sr_cfg.get("key_thirdparties", "KEY PRIMARY & SECONDARY THIRD PARTY ENGAGEMENT"),
        "kpa_id": _sr_cfg.get("kpa_id", "KPA ID"),
    }

    # LLM Override file -- auto-detect if present in input folder
    override_files = sorted(
        list(input_dir.glob("llm_overrides*.xlsx")) +
        list(input_dir.glob("llm_overrides*.csv")),
        key=lambda f: f.stat().st_mtime,
    )
    override_path = str(override_files[-1]) if override_files else None
    if override_path:
        logger.info(f"Using override file: {override_path}")

    # Findings/Issues file
    findings_files = sorted(
        list(input_dir.glob("findings_data_*.xlsx")) +
        list(input_dir.glob("findings_data_*.csv")),
        key=lambda f: f.stat().st_mtime,
    )
    findings_path = str(findings_files[-1]) if findings_files else None
    if findings_path:
        logger.info(f"Using findings file: {findings_path}")
    else:
        logger.info("No findings_data_*.xlsx or .csv found \u2014 skipping findings integration")
    _f_cfg = col_cfg.get("findings", {})
    findings_cols = {
        "entity_id": _f_cfg.get("entity_id", "Audit Entity ID"),
        "issue_id": _f_cfg.get("issue_id", "Finding ID"),
        "l2_risk": _f_cfg.get("l2_risk", "Risk Dimension Categories"),
        "severity": _f_cfg.get("severity", "Final Reportable Finding Risk Rating"),
        "status": _f_cfg.get("status", "Finding Status"),
        "issue_title": _f_cfg.get("issue_title", "Finding Name"),
        "remediation_date": _f_cfg.get("remediation_date", "Actual Remediation Date"),
        "approval_status": _f_cfg.get("approval_status", "Finding Approval Status"),
    }

    # PG team inputs file (optional — second AE-attribution route via FND_ID bridge).
    pg_team_cols = col_cfg.get("pg_team_inputs", {})
    pg_pattern = pg_team_cols.get("file_pattern", "project_guardian_aera_inputs_*.xlsx")
    pg_team_files = sorted(
        list(input_dir.glob(pg_pattern)),
        key=lambda f: f.stat().st_mtime,
    )
    pg_team_path = str(pg_team_files[-1]) if pg_team_files else None
    if pg_team_path:
        logger.info(f"Using PG team inputs file: {pg_team_path}")
    else:
        logger.info(f"No {pg_pattern} found — skipping PG team integration")

    # Legacy pillar column names -- built dynamically from config
    _suf = col_cfg.get("pillar_suffixes", {
        "rating": "Inherent Risk",
        "rationale": "Inherent Risk Rationale",
        "control": "Control Assessment",
        "control_rationale": "Control Assessment Rationale",
    })

    def _pillar(name):
        return {
            "rating":            f"{name} {_suf['rating']}",
            "rationale":         f"{name} {_suf['rationale']}",
            "control":           f"{name} {_suf['control']}",
            "control_rationale": f"{name} {_suf['control_rationale']}",
        }

    def _pillar_no_rationale(name):
        return {
            "rating":            f"{name} {_suf['rating']}",
            "rationale":         None,
            "control":           f"{name} {_suf['control']}",
            "control_rationale": None,
        }

    _pillars_with = col_cfg.get("pillars_with_rationale", [
        "Credit", "Market", "Strategic & Business", "Funding & Liquidity",
        "Reputational", "Model", "Financial Reporting", "External Fraud",
        "Operational", "Compliance", "Country",
    ])
    _pillars_without = col_cfg.get("pillars_without_rationale", [
        "Information Technology", "Information Security", "Third Party",
    ])
    pillar_columns = {}
    for name in _pillars_with:
        pillar_columns[name] = _pillar(name)
    for name in _pillars_without:
        pillar_columns[name] = _pillar_no_rationale(name)

    return {
        "legacy_data_path": legacy_data_path,
        "key_risk_path": key_risk_path,
        "override_path": override_path,
        "findings_path": findings_path,
        "key_risk_cols": key_risk_cols,
        "findings_cols": findings_cols,
        "pillar_columns": pillar_columns,
        "entity_id_col": entity_id_col,
        "pg_team_path": pg_team_path,
        "pg_team_cols": pg_team_cols,
    }


# ---------------------------------------------------------------------------
# Upstream Tagging Gaps — orphan capture helpers
# ---------------------------------------------------------------------------

# Schema for every orphan row written to the Upstream Tagging Gaps tab.
# Mappers and ingestion paths each emit DataFrames matching this exact column
# order so the main pipeline can concat without column drift.
_ORPHAN_COLUMNS = ["Source", "Item ID", "Title", "Status", "Drop Reason", "Source File"]


def _series_or_blank(df: pd.DataFrame, col: str) -> list[str]:
    """Return df[col] as a list of strings, or a list of empty strings if col absent.

    Use a plain list so the DataFrame constructor doesn't realign on a
    surviving non-default index (which would inflate the row count by
    pairing the indexed Series with the scalar Source/Drop Reason fields).
    """
    if not col or col not in df.columns:
        return [""] * len(df)
    return df[col].astype(str).tolist()


def _orphans_from_findings(
    blank_ae_findings: pd.DataFrame,
    findings_cols: dict,
    source_filename: str,
) -> pd.DataFrame:
    """Build orphan rows for findings dropped due to blank Audit Entity ID."""
    issue_id_col = findings_cols.get("issue_id", "Finding ID")
    title_col = findings_cols.get("issue_title", "Finding Title")
    status_col = findings_cols.get("status", "Finding Status")
    n = len(blank_ae_findings)
    return pd.DataFrame({
        "Source": ["Findings"] * n,
        "Item ID": _series_or_blank(blank_ae_findings, issue_id_col),
        "Title": _series_or_blank(blank_ae_findings, title_col),
        "Status": _series_or_blank(blank_ae_findings, status_col),
        "Drop Reason": ["Blank AE upstream"] * n,
        "Source File": [source_filename] * n,
    })[_ORPHAN_COLUMNS]


def _orphans_from_bma(
    blank_ae_bma: pd.DataFrame,
    bma_cols: dict,
    source_filename: str,
) -> pd.DataFrame:
    """Build orphan rows for BMA cases with blank entity IDs.

    Drop Reason is "Kept with warning (no AE)" — BMA does not drop these
    rows; they remain in bma_df. The orphan tab surfaces them so reviewers
    can chase the upstream tagging gap.
    """
    instance_col = bma_cols.get("instance_id", "Activity Instance ID")
    title_col = bma_cols.get("activity_title", "BM Activity Title")
    status_col = bma_cols.get("status", "")
    n = len(blank_ae_bma)
    return pd.DataFrame({
        "Source": ["BMA"] * n,
        "Item ID": _series_or_blank(blank_ae_bma, instance_col),
        "Title": _series_or_blank(blank_ae_bma, title_col),
        "Status": _series_or_blank(blank_ae_bma, status_col),
        "Drop Reason": ["Kept with warning (no AE)"] * n,
        "Source File": [source_filename] * n,
    })[_ORPHAN_COLUMNS]


def _orphans_from_pg_prsa(prsa_df, prsa_cols, src_name):
    """Build orphan rows for PG-flagged PRSA issues with a blank AE."""
    is_pg = prsa_cols.get("is_pg_gap", "Is PG Gap")
    ae = prsa_cols.get("ae_id", "AE ID")
    iid = prsa_cols.get("issue_id", "Issue ID")
    title = prsa_cols.get("issue_title", "Issue Title")
    status = prsa_cols.get("issue_status", "Issue Status")
    if prsa_df is None or prsa_df.empty or is_pg not in prsa_df.columns:
        return pd.DataFrame(columns=_ORPHAN_COLUMNS)
    blank_ae = prsa_df[ae].astype(str).str.strip().str.lower().isin(["", "nan", "none"]) if ae in prsa_df.columns else True
    mask = prsa_df[is_pg].astype(bool) & blank_ae
    rows = prsa_df[mask]
    if iid in rows.columns:
        rows = rows.drop_duplicates(subset=[iid])
    if rows.empty:
        return pd.DataFrame(columns=_ORPHAN_COLUMNS)
    n = len(rows)
    return pd.DataFrame({
        "Source": ["PG Gap"] * n,
        "Item ID": _series_or_blank(rows, iid),
        "Title": _series_or_blank(rows, title),
        "Status": _series_or_blank(rows, status),
        "Drop Reason": ["PG gap — no AE (no PRSA control tagged in IRM)"] * n,
        "Source File": [src_name] * n,
    })[_ORPHAN_COLUMNS]


def _read_orphans_sidecar(mapping_path: str) -> pd.DataFrame | None:
    """Read the `*_orphans.xlsx` sidecar next to a mapper output, if it exists.

    Returns a DataFrame matching ``_ORPHAN_COLUMNS`` schema, or None if no
    sidecar is found. Mappers write the sidecar in the same directory as
    the main mapping file, with `_orphans` inserted before the extension.
    """
    p = Path(mapping_path)
    sidecar = p.with_name(p.stem + "_orphans" + p.suffix)
    if not sidecar.exists():
        return None
    try:
        df = pd.read_excel(sidecar)
    except Exception as exc:
        logger.warning(f"  Could not read orphans sidecar {sidecar.name}: {exc}")
        return None
    # Defensive — if a mapper ever writes a different schema, project to ours.
    out_cols = {c: df[c] if c in df.columns else "" for c in _ORPHAN_COLUMNS}
    logger.info(f"  Read orphans sidecar: {sidecar.name} ({len(df)} rows)")
    return pd.DataFrame(out_cols)[_ORPHAN_COLUMNS]


def _compute_irm_ore_orphans(
    ore_irm_source_df: pd.DataFrame,
    legacy_df: pd.DataFrame,
    legacy_irm_ore_col: str,
    ore_irm_cols: dict,
    source_filename: str,
) -> pd.DataFrame:
    """Find IRM OREs in the source file but not bridged to any AE.

    The IRM source has no AE column; AE attribution flows through the
    `IRM ORE ID` column on legacy_risk_data — a per-AE newline-delimited
    list. An IRM ORE not listed in any AE's cell is invisible to the report.
    """
    ore_id_col = ore_irm_cols.get("ore_id", "ORE ID")
    title_col = ore_irm_cols.get("ore_title", "ORE Title")
    status_col = ore_irm_cols.get("capture_status", "Capture Status")

    if ore_id_col not in ore_irm_source_df.columns:
        return pd.DataFrame(columns=_ORPHAN_COLUMNS)

    bridged: set[str] = set()
    if legacy_irm_ore_col in legacy_df.columns:
        for raw in legacy_df[legacy_irm_ore_col].dropna().tolist():
            s = str(raw).strip()
            if not s or s.lower() in ("nan", "none"):
                continue
            for part in s.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
                part = part.strip()
                if part:
                    bridged.add(part)

    src_ids = ore_irm_source_df[ore_id_col].astype(str).str.strip()
    orphan_mask = (~src_ids.isin(bridged)) & (src_ids != "") & (src_ids.str.lower() != "nan")
    orphan_rows = ore_irm_source_df[orphan_mask]
    if orphan_rows.empty:
        return pd.DataFrame(columns=_ORPHAN_COLUMNS)

    logger.info(f"  IRM ORE bridge gaps: {len(orphan_rows)} OREs in source not "
                f"listed in any AE's '{legacy_irm_ore_col}' cell")
    n = len(orphan_rows)
    return pd.DataFrame({
        "Source": ["ORE IRM"] * n,
        "Item ID": _series_or_blank(orphan_rows, ore_id_col),
        "Title": _series_or_blank(orphan_rows, title_col),
        "Status": _series_or_blank(orphan_rows, status_col),
        "Drop Reason": ["Not in IRM ORE ID bridge"] * n,
        "Source File": [source_filename] * n,
    })[_ORPHAN_COLUMNS]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    """Configure paths, load data, run pipeline, and export results."""
    _CFG = get_config()

    provenance = log_run_provenance(logger)

    # -------------------------------------------------------------------------
    # CONFIGURE THESE PATHS AND COLUMN NAMES
    # -------------------------------------------------------------------------
    input_dir = _PROJECT_ROOT / "data" / "input"
    output_dir = _PROJECT_ROOT / "data" / "output"

    crosswalk_path = None  # Set path or None to use YAML config
    timestamp = datetime.now().strftime("%m%d%Y%I%M%p")
    output_path = str(output_dir / f"transformed_risk_taxonomy_{timestamp}.xlsx")
    col_cfg = _CFG.get("columns", {})

    paths = _resolve_input_paths(input_dir, output_dir, col_cfg)

    # Validate alignment between YAML new_taxonomy and L2_Risk_Taxonomy.xlsx.
    # If the file is present, every L2 in new_taxonomy should have a matching
    # row (via L2 column or L3 column for Fraud-at-L3-grain). Drift between
    # YAML and the taxonomy file is silent today — mappers build vectors for
    # whatever's in the file; main pipeline filters via normalize_l2_name.
    # Surfacing the drift at startup lets the user reconcile before a run.
    l2_taxonomy_file = input_dir / "L2_Risk_Taxonomy.xlsx"
    l2_taxonomy_df = None
    if l2_taxonomy_file.exists():
        try:
            import pandas as _pd
            l2_taxonomy_df = _pd.read_excel(l2_taxonomy_file)
            ffill_cols = [c for c in ("L1", "L2", "L3") if c in l2_taxonomy_df.columns]
            if ffill_cols:
                l2_taxonomy_df[ffill_cols] = l2_taxonomy_df[ffill_cols].ffill()
            from risk_taxonomy_transformer.config import L2_TO_L1 as _L2_TO_L1
            taxonomy_l2s = set()
            if "L2" in l2_taxonomy_df.columns:
                taxonomy_l2s.update(
                    str(v).strip() for v in l2_taxonomy_df["L2"].dropna()
                    if str(v).strip()
                )
            if "L3" in l2_taxonomy_df.columns:
                taxonomy_l2s.update(
                    str(v).strip() for v in l2_taxonomy_df["L3"].dropna()
                    if str(v).strip()
                )
            yaml_l2s = set(_L2_TO_L1.keys())
            missing_in_file = yaml_l2s - taxonomy_l2s
            if missing_in_file:
                logger.warning(
                    f"  Taxonomy alignment: {len(missing_in_file)} YAML L2(s) not "
                    f"found in L2_Risk_Taxonomy.xlsx (L2 or L3 columns): "
                    f"{sorted(missing_in_file)}"
                )
        except Exception as e:
            logger.warning(f"  Could not validate taxonomy file alignment: {e}")
            l2_taxonomy_df = None

    legacy_data_path = paths["legacy_data_path"]
    key_risk_path = paths["key_risk_path"]
    override_path = paths["override_path"]
    findings_path = paths["findings_path"]
    key_risk_cols = paths["key_risk_cols"]
    findings_cols = paths["findings_cols"]
    pillar_columns = paths["pillar_columns"]
    entity_id_col = paths["entity_id_col"]

    # -------------------------------------------------------------------------
    # RUN
    # -------------------------------------------------------------------------
    crosswalk = ingest_crosswalk(crosswalk_path)
    ce_cfg = col_cfg.get("control_effectiveness", {})
    legacy_df = ingest_legacy_data(
        legacy_data_path,
        entity_id_col=entity_id_col,
        report_date_col=ce_cfg.get("last_audit_completion_date"),
    )

    # Load key risk descriptions if configured
    key_risk_index = None
    key_risks_df = None
    if key_risk_path:
        key_risks_df = ingest_key_risks(
            key_risk_path,
            entity_id_col=key_risk_cols["entity_id"],
            legacy_l1_col=key_risk_cols["legacy_l1"],
            risk_desc_col=key_risk_cols["risk_desc"],
            risk_id_col=key_risk_cols.get("risk_id"),
            rating_col=key_risk_cols.get("rating"),
            key_apps_col=key_risk_cols.get("key_applications"),
            key_tps_col=key_risk_cols.get("key_thirdparties"),
            kpa_id_col=key_risk_cols.get("kpa_id"),
        )
        key_risk_index = build_key_risk_index(key_risks_df)
        logger.info(f"  Sub-risk index built: {len(key_risk_index)} entities with key risks")

        # Validate that every legacy_l1 in the key-risk file matches a configured
        # pillar. Unrecognized L1s are silently ignored by mapping/cross-boundary
        # scoring, so surface them here so the user can fix the file or the YAML.
        configured_pillars = set(pillar_columns.keys())
        key_risk_l1s = set(key_risks_df["legacy_l1"].dropna().astype(str).str.strip().unique())
        unrecognized = key_risk_l1s - configured_pillars
        if unrecognized:
            logger.warning(
                f"  Key-risk file references {len(unrecognized)} legacy L1 pillar(s) "
                f"not in pillars_with_rationale + pillars_without_rationale; rows under "
                f"these L1s will be silently ignored by mapping and cross-boundary scoring: "
                f"{sorted(unrecognized)}"
            )

    # Build per-entity key inventory (aggregate "key" app/TP IDs across key risks).
    # Non-key items do not drive risk per procedure; this set drives the drill-down
    # and Source Data "key" markers.
    from risk_taxonomy_transformer.config import get_app_cols
    key_inventory = build_key_inventory(
        key_risks_df, legacy_df, entity_id_col, get_app_cols()
    ) if key_risks_df is not None else {}

    # Load LLM overrides if configured
    overrides = None
    if override_path is not None:
        overrides = load_overrides(override_path)
        logger.info(f"  Override index built: {len(overrides)} entity-pillar overrides")

    # Load findings if configured
    findings_index = None
    findings_df = None
    unmapped_findings = {}
    upstream_orphans: list[pd.DataFrame] = []
    if findings_path is not None:
        findings_df, unmapped_findings, findings_orphans, findings_src_name = \
            ingest_findings(findings_path, findings_cols)
        findings_index = build_findings_index(findings_df)
        if not findings_orphans.empty:
            upstream_orphans.append(_orphans_from_findings(
                findings_orphans, findings_cols, findings_src_name
            ))

    # ORE mapping file (optional -- produced by ore_mapper.py into data/output/)
    # Exclude `*_orphans.xlsx` sidecars so they aren't picked up as the
    # latest mapping file (the orphans sidecar has its own schema).
    ore_files = sorted(
        [f for f in output_dir.glob("ore_mapping_*.xlsx") if "_orphans" not in f.stem],
        key=lambda f: f.stat().st_mtime,
    )
    ore_index = None
    ore_df = None
    unmapped_mapper_items: dict = {}
    if ore_files:
        ore_path = str(ore_files[-1])
        logger.info(f"Using ORE mapping file: {ore_path}")
        ore_confidence = _CFG.get("ore_confidence_filter", ["Suggested Match"])
        ore_df, ore_unmapped = ingest_ore_mappings(ore_path, confidence_filter=ore_confidence)
        ore_index = build_ore_index(ore_df)
        for eid, items in ore_unmapped.items():
            unmapped_mapper_items.setdefault(eid, []).extend(items)
        sidecar = _read_orphans_sidecar(ore_path)
        if sidecar is not None:
            upstream_orphans.append(sidecar)
    else:
        logger.info("No ore_mapping_*.xlsx found \u2014 skipping ORE integration")

    # ORE IRM source file (optional \u2014 read raw IRM file for source-tagged L2)
    ore_irm_source_files = sorted(
        list(input_dir.glob("ORE_IRM_*.xlsx")) +
        list(input_dir.glob("ORE_IRM_*.csv")),
        key=lambda f: f.stat().st_mtime,
    )
    ore_irm_source_df = None
    ore_irm_index = None
    if ore_irm_source_files:
        ore_irm_path = str(ore_irm_source_files[-1])
        logger.info(f"Using IRM ORE source file: {ore_irm_path}")
        ore_irm_cols = col_cfg.get("ore_irm", {})
        ore_phase_done = {str(v).strip().lower() for v in _CFG.get("ore_phase_completed_values", ["completed", "complete"])}
        ore_irm_source_df = ingest_ore_irm_source(ore_irm_path, ore_irm_cols, completed_values=ore_phase_done)

        # ORE IRM mapping file (produced by `python ore_mapper.py --source ore_irm`)
        ore_irm_mapping_files = sorted(
            [f for f in output_dir.glob("ore_irm_mapping_*.xlsx") if "_orphans" not in f.stem],
            key=lambda f: f.stat().st_mtime,
        )
        ore_irm_mapping_df = None
        if ore_irm_mapping_files:
            ore_irm_mapping_path = str(ore_irm_mapping_files[-1])
            logger.info(f"Using IRM ORE mapping file: {ore_irm_mapping_path}")
            ore_confidence_irm = _CFG.get("ore_confidence_filter", ["Suggested Match"])
            ore_irm_mapping_df, ore_irm_unmapped = ingest_ore_irm_mappings(
                ore_irm_mapping_path, confidence_filter=ore_confidence_irm
            )
            for eid, items in ore_irm_unmapped.items():
                unmapped_mapper_items.setdefault(eid, []).extend(items)
        else:
            logger.info("No ore_irm_mapping_*.xlsx found \u2014 IRM OREs with blank "
                        "or invalid Risk Level 2 will not be attributed to L2s")

        legacy_irm_ore_col = col_cfg.get("legacy_extras", {}).get("irm_ore_id", "IRM ORE ID")
        ore_irm_index = build_ore_irm_mapping_index(
            legacy_df, ore_irm_source_df, ore_irm_mapping_df,
            legacy_irm_ore_col, entity_id_col,
            ore_irm_cols=ore_irm_cols,
        )

        # IRM ORE orphans: items present in the source file but not listed in
        # any AE's IRM ORE ID cell on legacy. The bridge is the entire AE
        # attribution path; these items are invisible to the report otherwise.
        irm_orphans = _compute_irm_ore_orphans(
            ore_irm_source_df, legacy_df, legacy_irm_ore_col,
            ore_irm_cols, Path(ore_irm_path).name,
        )
        if not irm_orphans.empty:
            upstream_orphans.append(irm_orphans)
    else:
        logger.info("No ORE_IRM_*.xlsx or .csv found \u2014 skipping IRM ORE integration")

    # Combined ORE index for control effectiveness \u2014 IRM rows first within each
    # (entity, l2) cell, then legacy EV rows. Lu-confirmed ordering: IRM first
    # because they're newer and more granular.
    combined_ore_index: dict | None = None
    if ore_index or ore_irm_index:
        combined_ore_index = {}
        all_eids = set((ore_index or {}).keys()) | set((ore_irm_index or {}).keys())
        for eid in all_eids:
            merged_l2: dict[str, list] = {}
            irm_by_l2 = (ore_irm_index or {}).get(eid, {})
            legacy_by_l2 = (ore_index or {}).get(eid, {})
            all_l2s = set(irm_by_l2.keys()) | set(legacy_by_l2.keys())
            for l2 in all_l2s:
                # IRM first, legacy second (intentional ordering \u2014 Lu spec)
                merged_l2[l2] = list(irm_by_l2.get(l2, [])) + list(legacy_by_l2.get(l2, []))
            combined_ore_index[eid] = merged_l2

    # PRSA mapping file (optional -- produced by prsa_mapper.py into data/output/)
    # NOTE: build_prsa_mapping_index is deferred to AFTER ingest_prsa runs, so
    # we can apply the Track B source-tagged L2 substitution (filer-tagged L2
    # from `Risk Level 2` overrides the mapper output) before indexing.
    prsa_mapping_files = sorted(
        [f for f in output_dir.glob("prsa_mapping_*.xlsx") if "_orphans" not in f.stem],
        key=lambda f: f.stat().st_mtime,
    )
    prsa_mapping_index = None
    prsa_mapping_df = None
    if prsa_mapping_files:
        prsa_mapping_path = str(prsa_mapping_files[-1])
        logger.info(f"Using PRSA mapping file: {prsa_mapping_path}")
        prsa_confidence = _CFG.get("prsa_confidence_filter", ["Suggested Match"])
        prsa_mapping_df, prsa_unmapped = ingest_prsa_mappings(prsa_mapping_path, confidence_filter=prsa_confidence)
        for eid, items in prsa_unmapped.items():
            unmapped_mapper_items.setdefault(eid, []).extend(items)
        sidecar = _read_orphans_sidecar(prsa_mapping_path)
        if sidecar is not None:
            upstream_orphans.append(sidecar)
    else:
        logger.info("No prsa_mapping_*.xlsx found \u2014 skipping PRSA mapping integration")

    # RAP mapping file (optional -- produced by rap_mapper.py into data/output/)
    rap_mapping_files = sorted(
        [f for f in output_dir.glob("rap_mapping_*.xlsx") if "_orphans" not in f.stem],
        key=lambda f: f.stat().st_mtime,
    )
    rap_mapping_index = None
    rap_mapping_df = None
    if rap_mapping_files:
        rap_mapping_path = str(rap_mapping_files[-1])
        logger.info(f"Using RAP mapping file: {rap_mapping_path}")
        rap_confidence = _CFG.get("rap_confidence_filter", ["Suggested Match"])
        rap_mapping_df, rap_unmapped = ingest_rap_mappings(rap_mapping_path, confidence_filter=rap_confidence)
        rap_mapping_index = build_rap_mapping_index(rap_mapping_df)
        for eid, items in rap_unmapped.items():
            unmapped_mapper_items.setdefault(eid, []).extend(items)
        sidecar = _read_orphans_sidecar(rap_mapping_path)
        if sidecar is not None:
            upstream_orphans.append(sidecar)
    else:
        logger.info("No rap_mapping_*.xlsx found \u2014 skipping RAP mapping integration")

    # RCO Override file (optional -- produced by RCOs after reviewing Risk_Owner_Review tab)
    rco_override_files = sorted(
        list(input_dir.glob("rco_overrides_*.xlsx")) +
        list(input_dir.glob("rco_overrides_*.csv")),
        key=lambda f: f.stat().st_mtime,
    )
    rco_override_path = str(rco_override_files[-1]) if rco_override_files else None
    rco_overrides = None
    if rco_override_path:
        logger.info(f"Using RCO override file: {rco_override_path}")
        rco_overrides = ingest_rco_overrides(rco_override_path)

    # Optro export file (optional — audit team's confirmed L2 assessments)
    optro_files = sorted(
        list(input_dir.glob("optro_export_*.xlsx")) +
        list(input_dir.glob("optro_export_*.csv")),
        key=lambda f: f.stat().st_mtime,
    )
    optro_overrides: dict = {}
    optro_coverage: dict = {}
    if optro_files:
        optro_path = str(optro_files[-1])
        logger.info(f"Using Optro export file: {optro_path}")
        optro_cols = col_cfg.get("optro", {})
        optro_overrides, optro_coverage = ingest_optro_overrides(optro_path, optro_cols)
    else:
        logger.info("No optro_export_*.xlsx or .csv found — skipping Optro override integration")

    # PRSA report file (optional — Frankenstein report with AE/Issues/PRSA controls)
    prsa_files = sorted(
        [f for f in input_dir.glob("prsa_report_*.xlsx") if "_orphans" not in f.stem] +
        [f for f in input_dir.glob("prsa_report_*.csv") if "_orphans" not in f.stem],
        key=lambda f: f.stat().st_mtime,
    )
    prsa_df = None
    prsa_cols = col_cfg.get("prsa", {})
    pg_gap_index: dict | None = None
    if prsa_files:
        prsa_path = str(prsa_files[-1])
        logger.info(f"Using PRSA report file: {prsa_path}")
        prsa_df = ingest_prsa(prsa_path, prsa_cols)
        sidecar = _read_orphans_sidecar(prsa_path)
        if sidecar is not None:
            upstream_orphans.append(sidecar)
        # Track C: build the PG gap pill index alongside (independent of the
        # PRSA mapper output, which is keyed off issue text similarity rather
        # than the PG flag).
        pg_gap_index = build_pg_gap_index(prsa_df, prsa_cols)
        pg_prsa_orphans = _orphans_from_pg_prsa(prsa_df, prsa_cols, Path(prsa_path).name)
        if not pg_prsa_orphans.empty:
            upstream_orphans.append(pg_prsa_orphans)
    else:
        logger.info("No prsa_report_*.xlsx or .csv found — skipping PRSA integration")

    # Track C2: PG team inputs file — second AE-attribution route via FND_ID
    # bridge through findings_df. Unions with the PRSA-route pg_gap_index above.
    pg_team_path = paths.get("pg_team_path")
    pg_team_cols = paths.get("pg_team_cols", {})
    pg_team_df = None
    pg_team_diagnostics: dict = {}
    if pg_team_path and findings_df is not None and prsa_df is not None:
        pg_team_df = ingest_pg_team_inputs(pg_team_path, pg_team_cols)
        pg_team_route_index, pg_team_diagnostics = build_pg_gap_index_from_pg_team(
            pg_team_df, findings_df, prsa_df, pg_team_cols, prsa_cols,
        )
        pg_gap_index = merge_pg_gap_indexes(pg_gap_index or {}, pg_team_route_index)
        _pg_team_orphans = pg_team_diagnostics.get("orphans")
        if _pg_team_orphans is not None and not _pg_team_orphans.empty:
            if "Source File" in _pg_team_orphans.columns:
                _pg_team_orphans["Source File"] = Path(pg_team_path).name
            upstream_orphans.append(_pg_team_orphans.reindex(columns=_ORPHAN_COLUMNS))
    elif pg_team_path and (findings_df is None or prsa_df is None):
        logger.warning("PG team inputs file present but findings/PRSA missing — "
                       "skipping FND_ID bridge")

    # Track B: apply filer-tagged L2 substitution to PRSA mapper output, then
    # build the index. For each issue where prsa_df has L2 Provenance == 'source',
    # we replace the mapper's per-row l2_risk with the source-tagged canonical L2.
    # The mapper still ran on every issue; its output is just overridden when the
    # source wins. Issues with provenance == 'mapper' keep the mapper's L2.
    if prsa_mapping_df is not None:
        if prsa_df is not None and "L2 Provenance" in prsa_df.columns:
            issue_id_col = prsa_cols.get("issue_id", "Issue ID")
            ae_id_col_prsa = prsa_cols.get("ae_id", "AE ID")
            issue_title_col = prsa_cols.get("issue_title", "Issue Title")
            issue_desc_col = prsa_cols.get("issue_description", "Issue Description")
            issue_rating_col = prsa_cols.get("issue_rating", "Issue Rating")
            issue_status_col = prsa_cols.get("issue_status", "Issue Status")
            # Build source-L2 lookup: {issue_id: (canonical_l2, ae_id, metadata)}.
            # When an issue has multiple rows in prsa_df (one per control) the
            # L2 is identical by construction, so any row's value is fine.
            source_l2_by_issue: dict[str, dict] = {}
            if issue_id_col in prsa_df.columns:
                for _, prow in prsa_df.iterrows():
                    if str(prow.get("L2 Provenance", "")).strip() != "source":
                        continue
                    iid = str(prow.get(issue_id_col, "")).strip()
                    src_l2 = str(prow.get("Risk Level 2 Normalized", "")).strip()
                    if iid and src_l2 and iid not in source_l2_by_issue:
                        source_l2_by_issue[iid] = {
                            "l2": src_l2,
                            "entity_id": str(prow.get(ae_id_col_prsa, "")).strip(),
                            "Issue Title": str(prow.get(issue_title_col, ""))[:200],
                            "Issue Description": str(prow.get(issue_desc_col, ""))[:200],
                            "Issue Rating": str(prow.get(issue_rating_col, "")).strip(),
                            "Issue Status": str(prow.get(issue_status_col, "")).strip(),
                        }
            if source_l2_by_issue:
                # Substitute on the exploded prsa_mapping_df: drop existing
                # mapper-emitted rows for substituted issues, then append rows
                # carrying the source L2. Issues that were filtered out by the
                # mapper (e.g., status != Suggested Match) get a synthesized
                # row so the source-tagged L2 still propagates downstream.
                sub_ids = set(source_l2_by_issue.keys())
                sub_mask = prsa_mapping_df["issue_id"].astype(str).str.strip().isin(sub_ids)
                replaced_in_mapper = sub_mask.sum()
                # Issues already present in mapper output: keep one row, swap L2
                present_issues = set(
                    prsa_mapping_df.loc[sub_mask, "issue_id"].astype(str).str.strip()
                )
                keepers = (
                    prsa_mapping_df[sub_mask]
                    .drop_duplicates(subset=["issue_id"], keep="first")
                    .copy()
                )
                if not keepers.empty:
                    keepers["l2_risk"] = keepers["issue_id"].astype(str).str.strip().map(
                        lambda i: source_l2_by_issue[i]["l2"]
                    )
                    if "Mapped L2s" in keepers.columns:
                        keepers["Mapped L2s"] = keepers["l2_risk"]
                # Issues missing from mapper output (filtered out): synthesize
                missing_issues = sub_ids - present_issues
                synthesized_rows = []
                for iid in sorted(missing_issues):
                    meta = source_l2_by_issue[iid]
                    synthesized_rows.append({
                        "entity_id": meta["entity_id"],
                        "issue_id": iid,
                        "l2_risk": meta["l2"],
                        "Issue Title": meta["Issue Title"],
                        "Issue Description": meta["Issue Description"],
                        "Issue Rating": meta["Issue Rating"],
                        "Issue Status": meta["Issue Status"],
                        "Mapping Status": "Source-Tagged",
                        "Mapped L2s": meta["l2"],
                    })
                synth_df = pd.DataFrame(synthesized_rows) if synthesized_rows else None
                pieces = [prsa_mapping_df[~sub_mask]]
                if not keepers.empty:
                    pieces.append(keepers)
                if synth_df is not None and not synth_df.empty:
                    pieces.append(synth_df)
                prsa_mapping_df = pd.concat(pieces, ignore_index=True)
                logger.info(
                    f"  Track B: substituted source-tagged L2 for "
                    f"{len(source_l2_by_issue)} issue(s) "
                    f"({replaced_in_mapper} mapper row(s) replaced, "
                    f"{len(missing_issues)} synthesized for filtered-out issues)"
                )
        prsa_mapping_index = build_prsa_mapping_index(prsa_mapping_df)

    # BM Activities file (optional — Business Monitoring Activities instances)
    bma_files = sorted(
        list(input_dir.glob("bm_activities_*.xlsx")) +
        list(input_dir.glob("bm_activities_*.csv")),
        key=lambda f: f.stat().st_mtime,
    )
    bma_df = None
    bma_cols = col_cfg.get("bma", {})
    if bma_files:
        bma_path = str(bma_files[-1])
        logger.info(f"Using BM Activities file: {bma_path}")
        bma_df, bma_orphans, bma_src_name = ingest_bma(bma_path, bma_cols)
        if not bma_orphans.empty:
            upstream_orphans.append(_orphans_from_bma(
                bma_orphans, bma_cols, bma_src_name
            ))
    else:
        logger.info("No bm_activities_*.xlsx or .csv found — skipping BMA integration")

    # GRA RAPs file (optional — regulatory action plans)
    gra_raps_files = sorted(
        list(input_dir.glob("gra_raps_*.xlsx")) +
        list(input_dir.glob("gra_raps_*.csv")),
        key=lambda f: f.stat().st_mtime,
    )
    gra_raps_df = None
    gra_raps_cols = col_cfg.get("gra_raps", {})
    if gra_raps_files:
        gra_raps_path = str(gra_raps_files[-1])
        logger.info(f"Using GRA RAPs file: {gra_raps_path}")
        gra_raps_df = ingest_gra_raps(gra_raps_path, gra_raps_cols)
    else:
        logger.info("No gra_raps_*.xlsx or .csv found — skipping GRA RAPs integration")

    # Enrich PRSA/GRA RAPs source DataFrames with mapping status so the HTML
    # report's source tabs and drill-down filters can use them. The mapper
    # output is one row per item with Mapped L2s semicolon-joined; we merge
    # those two columns onto the raw source records by ID.
    if prsa_df is not None and prsa_mapping_files:
        try:
            _prsa_raw = pd.read_excel(prsa_mapping_files[-1], sheet_name="All Mappings")
            _prsa_raw.columns = [c.strip() for c in _prsa_raw.columns]
            _prsa_map_cols = _prsa_raw[["Issue ID", "Mapped L2s", "Mapping Status"]].drop_duplicates(subset=["Issue ID"])
            issue_id_col = prsa_cols.get("issue_id", "Issue ID")
            if issue_id_col in prsa_df.columns:
                prsa_df = prsa_df.merge(
                    _prsa_map_cols.rename(columns={"Issue ID": issue_id_col}),
                    on=issue_id_col, how="left",
                )
                logger.info(f"  Enriched PRSA source with mapping status from {prsa_mapping_files[-1].name}")
        except Exception as e:
            logger.warning(f"  Could not enrich PRSA source with mapping: {e}")

    if gra_raps_df is not None and rap_mapping_files:
        try:
            _rap_raw = pd.read_excel(rap_mapping_files[-1], sheet_name="All Mappings")
            _rap_raw.columns = [c.strip() for c in _rap_raw.columns]
            _rap_map_cols = _rap_raw[["RAP ID", "Mapped L2s", "Mapping Status"]].drop_duplicates(subset=["RAP ID"])
            rap_id_col = gra_raps_cols.get("rap_id", "RAP ID")
            if rap_id_col in gra_raps_df.columns:
                gra_raps_df = gra_raps_df.merge(
                    _rap_map_cols.rename(columns={"RAP ID": rap_id_col}),
                    on=rap_id_col, how="left",
                )
                logger.info(f"  Enriched GRA RAPs source with mapping status from {rap_mapping_files[-1].name}")
        except Exception as e:
            logger.warning(f"  Could not enrich GRA RAPs source with mapping: {e}")

    ctx = TransformContext(
        crosswalk=crosswalk,
        pillar_columns=pillar_columns,
        key_risk_index=key_risk_index,
        overrides=overrides,
        findings_index=findings_index,
        ore_index=combined_ore_index if combined_ore_index is not None else ore_index,
    )

    transformed_df = run_pipeline(legacy_df, entity_id_col, ctx)

    transformed_df = derive_inherent_risk_rating(transformed_df)
    transformed_df = derive_control_effectiveness(
        transformed_df, legacy_df, entity_id_col, _CFG,
        findings_index=findings_index,
        ore_index=combined_ore_index if combined_ore_index is not None else ore_index,
        prsa_index=prsa_mapping_index,
        rap_index=rap_mapping_index,
        pg_gap_index=pg_gap_index,
    )
    transformed_df = flag_control_contradictions(transformed_df, findings_index)
    transformed_df = flag_application_applicability(
        transformed_df, legacy_df, entity_id_col,
        key_inventory=key_inventory,
    )
    transformed_df = flag_auxiliary_risks(transformed_df, legacy_df, entity_id_col)
    transformed_df = flag_core_risks(transformed_df, legacy_df, entity_id_col)
    transformed_df = flag_cross_boundary_signals(
        transformed_df, legacy_df, pillar_columns, entity_id_col,
        key_risk_index=key_risk_index,
    )

    # Apply Optro overrides AFTER all flag functions so conflict detection
    # can read the row's own signals. All-or-nothing per entity — partial
    # coverage entities are warned about but not applied.
    if optro_overrides:
        fully_covered, _partial = assess_optro_coverage(transformed_df, optro_coverage)
        transformed_df = apply_optro_overrides(transformed_df, optro_overrides, fully_covered)
        transformed_df = detect_optro_conflicts(transformed_df)

    # Concatenate all upstream orphan DataFrames into a single tab. Empty
    # DataFrame is OK — export skips writing the tab if no rows.
    if upstream_orphans:
        upstream_orphans_df = pd.concat(upstream_orphans, ignore_index=True)
        upstream_orphans_df = upstream_orphans_df.reindex(columns=_ORPHAN_COLUMNS)
    else:
        upstream_orphans_df = pd.DataFrame(columns=_ORPHAN_COLUMNS)
    logger.info(
        f"  Upstream Tagging Gaps: {len(upstream_orphans_df)} orphan rows across "
        f"{upstream_orphans_df['Source'].nunique() if not upstream_orphans_df.empty else 0} sources"
    )

    export_results(
        transformed_df, legacy_df, output_path,
        findings_df=findings_df,
        key_risks_df=key_risks_df,
        findings_path=findings_path,
        findings_cols=findings_cols,
        entity_id_col=entity_id_col,
        findings_index=findings_index,
        rco_overrides=rco_overrides,
        ore_df=ore_df,
        ore_irm_source_df=ore_irm_source_df,
        ore_irm_index=ore_irm_index,
        pillar_columns=pillar_columns,
        prsa_df=prsa_df,
        prsa_cols=prsa_cols,
        pg_team_df=pg_team_df,
        pg_team_cols=pg_team_cols,
        pg_team_diagnostics=pg_team_diagnostics,
        bma_df=bma_df,
        bma_cols=bma_cols,
        gra_raps_df=gra_raps_df,
        gra_raps_cols=gra_raps_cols,
        unmapped_findings=unmapped_findings,
        unmapped_mapper_items=unmapped_mapper_items,
        key_inventory=key_inventory,
        l2_taxonomy_df=l2_taxonomy_df,
        upstream_orphans_df=upstream_orphans_df,
        provenance=provenance,
    )

    # Generate HTML report
    try:
        from export_html_report import generate_html_report
        html_path = str(output_dir / f"risk_taxonomy_report_{timestamp}.html")
        generate_html_report(output_path, html_path)
    except ImportError:
        logger.info("  export_html_report not available \u2014 skipping HTML report")

    print(f"\nDone! Output: {output_path}")
    print(f"Applicability undetermined: {transformed_df['needs_review'].sum()} items require team decision")


if __name__ == "__main__":
    main()
