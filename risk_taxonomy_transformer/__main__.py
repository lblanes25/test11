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
    build_prsa_mapping_index,
    build_rap_mapping_index,
    build_key_inventory,
    build_key_risk_index,
    ingest_crosswalk,
    ingest_findings,
    ingest_legacy_data,
    ingest_ore_mappings,
    ingest_prsa_mappings,
    ingest_rap_mappings,
    ingest_bma,
    ingest_gra_raps,
    ingest_prsa,
    ingest_rco_overrides,
    ingest_key_risks,
    load_overrides,
)
from risk_taxonomy_transformer.pipeline import run_pipeline

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
    if findings_path is not None:
        findings_df, unmapped_findings = ingest_findings(findings_path, findings_cols)
        findings_index = build_findings_index(findings_df)

    # ORE mapping file (optional -- produced by ore_mapper.py into data/output/)
    ore_files = sorted(
        output_dir.glob("ore_mapping_*.xlsx"),
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
    else:
        logger.info("No ore_mapping_*.xlsx found \u2014 skipping ORE integration")

    # PRSA mapping file (optional -- produced by prsa_mapper.py into data/output/)
    prsa_mapping_files = sorted(
        output_dir.glob("prsa_mapping_*.xlsx"),
        key=lambda f: f.stat().st_mtime,
    )
    prsa_mapping_index = None
    prsa_mapping_df = None
    if prsa_mapping_files:
        prsa_mapping_path = str(prsa_mapping_files[-1])
        logger.info(f"Using PRSA mapping file: {prsa_mapping_path}")
        prsa_confidence = _CFG.get("prsa_confidence_filter", ["Suggested Match"])
        prsa_mapping_df, prsa_unmapped = ingest_prsa_mappings(prsa_mapping_path, confidence_filter=prsa_confidence)
        prsa_mapping_index = build_prsa_mapping_index(prsa_mapping_df)
        for eid, items in prsa_unmapped.items():
            unmapped_mapper_items.setdefault(eid, []).extend(items)
    else:
        logger.info("No prsa_mapping_*.xlsx found \u2014 skipping PRSA mapping integration")

    # RAP mapping file (optional -- produced by rap_mapper.py into data/output/)
    rap_mapping_files = sorted(
        output_dir.glob("rap_mapping_*.xlsx"),
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
        bma_df = ingest_bma(bma_path, bma_cols)
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
        ore_index=ore_index,
    )

    transformed_df = run_pipeline(legacy_df, entity_id_col, ctx)

    transformed_df = derive_inherent_risk_rating(transformed_df)
    transformed_df = derive_control_effectiveness(
        transformed_df, legacy_df, entity_id_col, _CFG,
        findings_index=findings_index,
        ore_index=ore_index,
        prsa_index=prsa_mapping_index,
        rap_index=rap_mapping_index,
    )
    transformed_df = flag_control_contradictions(transformed_df, findings_index)
    transformed_df = flag_application_applicability(transformed_df, legacy_df, entity_id_col)
    transformed_df = flag_auxiliary_risks(transformed_df, legacy_df, entity_id_col)
    transformed_df = flag_core_risks(transformed_df, legacy_df, entity_id_col)
    transformed_df = flag_cross_boundary_signals(
        transformed_df, legacy_df, pillar_columns, entity_id_col,
        key_risk_index=key_risk_index,
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
        pillar_columns=pillar_columns,
        prsa_df=prsa_df,
        prsa_cols=prsa_cols,
        bma_df=bma_df,
        bma_cols=bma_cols,
        gra_raps_df=gra_raps_df,
        gra_raps_cols=gra_raps_cols,
        unmapped_findings=unmapped_findings,
        unmapped_mapper_items=unmapped_mapper_items,
        key_inventory=key_inventory,
        l2_taxonomy_df=l2_taxonomy_df,
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
