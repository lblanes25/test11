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

from risk_taxonomy_transformer.config import get_config, TransformContext
from risk_taxonomy_transformer.enrichment import derive_control_effectiveness, derive_inherent_risk_rating
from risk_taxonomy_transformer.export import export_results
from risk_taxonomy_transformer.flags import (
    flag_application_applicability,
    flag_auxiliary_risks,
    flag_control_contradictions,
    flag_cross_boundary_signals,
)
from risk_taxonomy_transformer.ingestion import (
    build_enterprise_findings_index,
    build_findings_index,
    build_ore_index,
    build_sub_risk_index,
    ingest_crosswalk,
    ingest_enterprise_findings,
    ingest_findings,
    ingest_legacy_data,
    ingest_ore_mappings,
    ingest_prsa,
    ingest_rco_overrides,
    ingest_sub_risks,
    load_overrides,
)
from risk_taxonomy_transformer.pipeline import apply_overlay_flags, run_pipeline

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

    Returns a dict with keys: legacy_data_path, sub_risk_path, override_path,
    findings_path, sub_risk_cols, findings_cols, pillar_columns, entity_id_col.
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

    # Sub-risk descriptions file (optional but recommended for accuracy)
    sub_risk_files = sorted(
        list(input_dir.glob("sub_risk_descriptions_*.xlsx")) +
        list(input_dir.glob("sub_risk_descriptions_*.csv")),
        key=lambda f: f.stat().st_mtime,
    )
    sub_risk_path = str(sub_risk_files[-1]) if sub_risk_files else None
    if sub_risk_path:
        logger.info(f"Using sub-risk file: {sub_risk_path}")
    else:
        logger.info("No sub_risk_descriptions_*.xlsx or .csv found \u2014 skipping sub-risk lookup")
    _sr_cfg = col_cfg.get("sub_risks", {})
    sub_risk_cols = {
        "entity_id": _sr_cfg.get("entity_id", "Audit Entity ID"),
        "risk_id": _sr_cfg.get("risk_id", "Key Risk ID"),
        "risk_desc": _sr_cfg.get("risk_description", "Key Risk Description"),
        "legacy_l1": _sr_cfg.get("legacy_l1", "Level 1 Risk Category"),
        "rating": _sr_cfg.get("rating", "Inherent Risk Rating"),
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
        "sub_risk_path": sub_risk_path,
        "override_path": override_path,
        "findings_path": findings_path,
        "sub_risk_cols": sub_risk_cols,
        "findings_cols": findings_cols,
        "pillar_columns": pillar_columns,
        "entity_id_col": entity_id_col,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    """Configure paths, load data, run pipeline, and export results."""
    _CFG = get_config()

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

    legacy_data_path = paths["legacy_data_path"]
    sub_risk_path = paths["sub_risk_path"]
    override_path = paths["override_path"]
    findings_path = paths["findings_path"]
    sub_risk_cols = paths["sub_risk_cols"]
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

    # Load sub-risk descriptions if configured
    sub_risk_index = None
    sub_risks_df = None
    if sub_risk_path:
        sub_risks_df = ingest_sub_risks(
            sub_risk_path,
            entity_id_col=sub_risk_cols["entity_id"],
            legacy_l1_col=sub_risk_cols["legacy_l1"],
            risk_desc_col=sub_risk_cols["risk_desc"],
            risk_id_col=sub_risk_cols.get("risk_id"),
            rating_col=sub_risk_cols.get("rating"),
        )
        sub_risk_index = build_sub_risk_index(sub_risks_df)
        logger.info(f"  Sub-risk index built: {len(sub_risk_index)} entities with sub-risks")

    # Load LLM overrides if configured
    overrides = None
    if override_path is not None:
        overrides = load_overrides(override_path)
        logger.info(f"  Override index built: {len(overrides)} entity-pillar overrides")

    # Load findings if configured
    findings_index = None
    findings_df = None
    if findings_path is not None:
        findings_df = ingest_findings(findings_path, findings_cols)
        findings_index = build_findings_index(findings_df)

    # ORE mapping file (optional -- produced by ore_mapper.py into data/output/)
    ore_files = sorted(
        list(input_dir.glob("ore_mapping_*.xlsx")) +
        list(output_dir.glob("ore_mapping_*.xlsx")),
        key=lambda f: f.stat().st_mtime,
    )
    ore_index = None
    ore_df = None
    if ore_files:
        ore_path = str(ore_files[-1])
        logger.info(f"Using ORE mapping file: {ore_path}")
        ore_confidence = _CFG.get("ore_confidence_filter", ["Mapped"])
        ore_df = ingest_ore_mappings(ore_path, confidence_filter=ore_confidence)
        ore_index = build_ore_index(ore_df)
    else:
        logger.info("No ore_mapping_*.xlsx found \u2014 skipping ORE integration")

    # Enterprise findings file (optional)
    ent_findings_files = sorted(
        list(input_dir.glob("enterprise_findings_*.xlsx")) +
        list(input_dir.glob("enterprise_findings_*.csv")),
        key=lambda f: f.stat().st_mtime,
    )
    enterprise_findings_index = None
    if ent_findings_files:
        ent_path = str(ent_findings_files[-1])
        logger.info(f"Using enterprise findings file: {ent_path}")
        ent_df = ingest_enterprise_findings(ent_path)
        enterprise_findings_index = build_enterprise_findings_index(ent_df)
    else:
        logger.info("No enterprise_findings_*.xlsx or .csv found \u2014 skipping enterprise findings")

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

    # PRSA report file (optional — Frankenstein report with AE/Issues/PRSA controls)
    prsa_files = sorted(
        list(input_dir.glob("prsa_report_*.xlsx")) +
        list(input_dir.glob("prsa_report_*.csv")),
        key=lambda f: f.stat().st_mtime,
    )
    prsa_df = None
    prsa_cols = col_cfg.get("prsa", {})
    if prsa_files:
        prsa_path = str(prsa_files[-1])
        logger.info(f"Using PRSA report file: {prsa_path}")
        prsa_df = ingest_prsa(prsa_path, prsa_cols)
    else:
        logger.info("No prsa_report_*.xlsx or .csv found — skipping PRSA integration")

    ctx = TransformContext(
        crosswalk=crosswalk,
        pillar_columns=pillar_columns,
        sub_risk_index=sub_risk_index,
        overrides=overrides,
        findings_index=findings_index,
        ore_index=ore_index,
        enterprise_findings_index=enterprise_findings_index,
    )

    transformed_df, overlays_df = run_pipeline(legacy_df, entity_id_col, ctx)

    transformed_df = apply_overlay_flags(transformed_df, overlays_df)
    transformed_df = derive_inherent_risk_rating(transformed_df)
    transformed_df = derive_control_effectiveness(
        transformed_df, legacy_df, entity_id_col, _CFG,
        findings_index=findings_index,
        ore_index=ore_index,
        enterprise_findings_index=enterprise_findings_index,
    )
    transformed_df = flag_control_contradictions(transformed_df, findings_index)
    transformed_df = flag_application_applicability(transformed_df, legacy_df, entity_id_col)
    transformed_df = flag_auxiliary_risks(transformed_df, legacy_df, entity_id_col)
    transformed_df = flag_cross_boundary_signals(
        transformed_df, legacy_df, pillar_columns, entity_id_col,
        sub_risk_index=sub_risk_index,
    )

    export_results(
        transformed_df, overlays_df, legacy_df, output_path,
        findings_df=findings_df,
        sub_risks_df=sub_risks_df,
        findings_path=findings_path,
        findings_cols=findings_cols,
        entity_id_col=entity_id_col,
        findings_index=findings_index,
        rco_overrides=rco_overrides,
        ore_df=ore_df,
        pillar_columns=pillar_columns,
        prsa_df=prsa_df,
        prsa_cols=prsa_cols,
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
