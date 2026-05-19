"""
Build the PRSA Frankenstein report from three source extracts.

Replaces the manual workbook-stitching process Lu does today. Reads the
three Archer / Controls / legacy_risk_data source files, performs the
explode + join sequence, and writes a single-sheet Excel file matching
the schema declared in ``config/taxonomy_config.yaml`` under
``columns.prsa``.

Usage:
    # Production (latest of each input, timestamped output):
    python build_prsa_frankenstein.py

    # Test-dummy (uses *_test_dummy.xlsx; writes prsa_report_test_dummy_BUILT.xlsx):
    python build_prsa_frankenstein.py --test-dummy

    # Explicit overrides:
    python build_prsa_frankenstein.py --legacy <path> --archer <path> \\
        --controls <path> --output <path>

Inputs (production mode picks the most recently modified match):
    - data/input/legacy_risk_data_<datetime>.xlsx (must include ``PRSA``
      column, newline-delimited list of PRSA IDs per AE)
    - data/input/PRSA_IRM_Archer_<datetime>.xlsx (one row per Issue;
      ``Control ID (PRSA)`` may be newline-delimited)
    - data/input/PRSA_Controls_Map_<datetime>.xlsx (one row per control;
      ``Control ID`` joins to Archer; ``Process ID`` joins to legacy.PRSA)

Output:
    - data/input/prsa_report_<MMDDYYYYHHMMpm>.xlsx (production)
    - data/input/prsa_report_test_dummy_BUILT.xlsx (test-dummy)
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml


# Match `#PG` or `PG` at the start of an Issue Description, followed by a
# word boundary, whitespace, or end-of-string. Case-sensitive per Lu's spec —
# "Pgsql" or "Pgrade" must not flag. Common follow-ups in real text:
# "#PG Gap: ...", "PG - ...", "#PG.", "PG\n".
_PG_FLAG_RE = re.compile(r"^(#?PG)(\b|\s|$)")

_PROJECT_ROOT = Path(__file__).resolve().parent
_INPUT_DIR = _PROJECT_ROOT / "data" / "input"
_CONFIG_PATH = _PROJECT_ROOT / "config" / "taxonomy_config.yaml"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _resolve_columns(cfg: dict) -> dict:
    """Pull all column names we need out of the YAML.

    Returns a flat dict so the rest of the script doesn't have to think
    about the YAML structure.
    """
    cols = cfg.get("columns", {})
    prsa = cols.get("prsa", {})
    org = cols.get("org_metadata", {})
    findings = cols.get("findings", {})

    return {
        # Output (Frankenstein) column names
        "out_ae_id":               prsa.get("ae_id", "AE ID"),
        "out_ae_name":             prsa.get("ae_name", "AE Name"),
        "out_audit_leader":        prsa.get("audit_leader", "Audit Leader"),
        "out_core_audit_team":     prsa.get("core_audit_team", "Core Audit Team"),
        "out_audit_engagement_id": prsa.get("audit_engagement_id", "Audit Engagement ID"),
        "out_all_prsas_tagged":    prsa.get("all_prsas_tagged", "All PRSAs Tagged to AE"),
        "out_issue_id":            prsa.get("issue_id", "Issue ID"),
        "out_issue_rating":        prsa.get("issue_rating", "Issue Rating"),
        "out_issue_status":        prsa.get("issue_status", "Issue Status"),
        "out_issue_identifier":    prsa.get("issue_identifier", "Issue Identifier"),
        "out_issue_title":         prsa.get("issue_title", "Issue Title"),
        "out_issue_description":   prsa.get("issue_description", "Issue Description"),
        "out_issue_owner":         prsa.get("issue_owner", "Issue Owner"),
        "out_root_cause_desc":     prsa.get("root_cause_description", "Root Cause Description"),
        "out_root_cause_sub":      prsa.get("root_cause_sub_theme", "Root Cause Sub-Theme"),
        "out_root_cause_theme":    prsa.get("root_cause_theme", "Root Cause Theme"),
        "out_risk_level_2":        prsa.get("risk_level_2", "Risk Level 2"),
        "out_control_id_prsa":     prsa.get("control_id_prsa", "Control ID (PRSA)"),
        "out_prsa_id":             prsa.get("prsa_id", "PRSA ID"),
        "out_process_title":       prsa.get("process_title", "Process Title"),
        "out_control_title":       prsa.get("control_title", "Control Title"),
        "out_is_pg_gap":           prsa.get("is_pg_gap", "Is PG Gap"),

        # Legacy file column names (legacy_risk_data_*.xlsx)
        "legacy_entity_id":        findings.get("entity_id", "Audit Entity ID"),
        "legacy_entity_name":      org.get("entity_name", "Audit Entity Name"),
        "legacy_audit_leader":     org.get("audit_leader", "Audit Leader"),
        "legacy_core_audit_team":  org.get("core_audit_team", "Core Audit Team"),
        # Audit Engagement ID lives in the prsa output schema only; the
        # legacy file is expected to expose it under the same header.
        "legacy_audit_eng_id":     prsa.get("audit_engagement_id", "Audit Engagement ID"),
        "legacy_prsa":             "PRSA",
    }


# Output column order — match the YAML columns.prsa block exactly.
def _output_column_order(C: dict) -> list[str]:
    return [
        C["out_ae_id"],
        C["out_ae_name"],
        C["out_audit_leader"],
        C["out_core_audit_team"],
        C["out_audit_engagement_id"],
        C["out_all_prsas_tagged"],
        C["out_issue_id"],
        C["out_issue_rating"],
        C["out_issue_status"],
        C["out_issue_identifier"],
        C["out_issue_title"],
        C["out_issue_description"],
        C["out_issue_owner"],
        C["out_root_cause_desc"],
        C["out_root_cause_sub"],
        C["out_root_cause_theme"],
        C["out_risk_level_2"],
        C["out_control_id_prsa"],
        C["out_prsa_id"],
        C["out_process_title"],
        C["out_control_title"],
        C["out_is_pg_gap"],
    ]


# Required columns on each input
_ARCHER_REQUIRED = [
    "Issue ID", "Issue Title", "Issue Owner", "Issue Status",
    "Issue Status Rating", "Issue Impact Rating", "Issue Identifier",
    "Control ID (PRSA)", "Control ID (RCSA)", "Issue Description",
    "Root Cause Description", "Root Cause Sub-Theme",
    "Root Cause Theme", "Risk Level 2",
]
_CONTROLS_REQUIRED = ["Control ID", "Control Title", "Process ID", "Process Title"]


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def _latest(pattern: str, input_dir: Path) -> Path:
    matches = sorted(input_dir.glob(pattern), key=lambda f: f.stat().st_mtime)
    if not matches:
        raise FileNotFoundError(f"No file matching '{pattern}' in {input_dir}")
    return matches[-1]


def _latest_any_ext(stem_pattern: str, input_dir: Path) -> Path:
    """Find the most recent file matching the stem with .xlsx or .csv extension."""
    matches = (
        list(input_dir.glob(f"{stem_pattern}.xlsx"))
        + list(input_dir.glob(f"{stem_pattern}.csv"))
    )
    if not matches:
        raise FileNotFoundError(
            f"No file matching '{stem_pattern}.xlsx' or '{stem_pattern}.csv' in {input_dir}"
        )
    return max(matches, key=lambda f: f.stat().st_mtime)


def _resolve_input_paths(args: argparse.Namespace) -> dict:
    """Determine which legacy / Archer / Controls files to read."""
    if args.test_dummy:
        # Test fixtures: use *_test_dummy.xlsx for all three inputs. Prefer the
        # stable legacy_risk_data_test_dummy.xlsx fixture (written by
        # tests/generate_test_data.py); fall back to the latest production
        # legacy file with a loud warning so the run isn't silently coupled to
        # whatever timestamped file happens to be newest.
        if args.legacy:
            legacy = Path(args.legacy)
        else:
            test_dummy_legacy_xlsx = _INPUT_DIR / "legacy_risk_data_test_dummy.xlsx"
            test_dummy_legacy_csv = _INPUT_DIR / "legacy_risk_data_test_dummy.csv"
            if test_dummy_legacy_xlsx.exists():
                legacy = test_dummy_legacy_xlsx
            elif test_dummy_legacy_csv.exists():
                legacy = test_dummy_legacy_csv
            else:
                logger.warning(
                    "legacy_risk_data_test_dummy.{xlsx,csv} not found, falling back to "
                    "latest production legacy -- run generate_test_data.py to "
                    "create the fixture"
                )
                legacy = _latest_any_ext("legacy_risk_data_*", _INPUT_DIR)
        archer = Path(args.archer) if args.archer else _INPUT_DIR / "PRSA_IRM_Archer_test_dummy.xlsx"
        controls = Path(args.controls) if args.controls else _INPUT_DIR / "PRSA_Controls_Map_test_dummy.xlsx"
    else:
        legacy = Path(args.legacy) if args.legacy else _latest_any_ext("legacy_risk_data_*", _INPUT_DIR)
        archer = Path(args.archer) if args.archer else _latest("PRSA_IRM_Archer_*.xlsx", _INPUT_DIR)
        controls = Path(args.controls) if args.controls else _latest("PRSA_Controls_Map_*.xlsx", _INPUT_DIR)

    for label, p in (("legacy", legacy), ("archer", archer), ("controls", controls)):
        if not p.exists():
            raise FileNotFoundError(f"{label} file does not exist: {p}")

    return {"legacy": legacy, "archer": archer, "controls": controls}


def _resolve_output_path(args: argparse.Namespace) -> Path:
    if args.output:
        return Path(args.output)
    if args.test_dummy:
        # Use a distinct filename so we don't overwrite the golden file
        # produced by tests/generate_prsa_source_test_data.py.
        return _INPUT_DIR / "prsa_report_test_dummy_BUILT.xlsx"
    timestamp = datetime.now().strftime("%m%d%Y%I%M%p")
    return _INPUT_DIR / f"prsa_report_{timestamp}.xlsx"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_blank(val) -> bool:
    if val is None:
        return True
    s = str(val).strip()
    return s == "" or s.lower() == "nan"


def _explode_newline(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Split ``col`` on newline (CR/CRLF tolerant), strip, drop empty entries.

    Rows whose value is blank produce zero output rows.
    """
    if col not in df.columns:
        raise ValueError(f"Cannot explode column '{col}': not present in DataFrame")

    def _split(val):
        if _is_blank(val):
            return []
        raw = str(val).replace("\r\n", "\n").replace("\r", "\n")
        return [p.strip() for p in raw.split("\n") if p.strip()]

    df = df.copy()
    df[col] = df[col].map(_split)
    return df.explode(col, ignore_index=True).dropna(subset=[col]).reset_index(drop=True)


def _check_required(df: pd.DataFrame, required: list[str], filepath: Path) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"{filepath} missing required columns: {missing}. "
            f"Available: {list(df.columns)}"
        )


# ---------------------------------------------------------------------------
# Build steps
# ---------------------------------------------------------------------------

def _load_legacy(filepath: Path, C: dict) -> pd.DataFrame:
    logger.info(f"Reading legacy data from {filepath}")
    if str(filepath).lower().endswith(".csv"):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)
    df.columns = [str(c).strip() for c in df.columns]
    legacy_required_hard = [
        C["legacy_entity_id"],
        C["legacy_entity_name"],
        C["legacy_audit_leader"],
        C["legacy_core_audit_team"],
        C["legacy_prsa"],
    ]
    _check_required(df, legacy_required_hard, filepath)

    # Audit Engagement ID is soft-required: if absent, emit blanks and warn.
    # Production legacy extracts include it; some test fixtures don't yet.
    eng_col = C["legacy_audit_eng_id"]
    if eng_col not in df.columns:
        logger.warning(f"  Legacy file missing '{eng_col}' column -- emitting blanks")
        df = df.copy()
        df[eng_col] = ""

    logger.info(f"  Loaded {len(df)} legacy rows")
    df = df[legacy_required_hard + [eng_col]].copy()

    pre = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    removed = pre - len(df)
    if removed:
        logger.warning(f"  Legacy file had {removed} bit-for-bit duplicate rows; kept {len(df)}")
    ae_dupes = df.duplicated(subset=[C["legacy_entity_id"]]).sum()
    if ae_dupes:
        logger.warning(
            f"  Legacy still has {ae_dupes} rows with non-unique AE IDs after dedup — "
            f"upstream extract is likely multi-period. Downstream joins may multiply."
        )

    return df


def _load_archer(filepath: Path) -> pd.DataFrame:
    logger.info(f"Reading Archer issues from {filepath}")
    df = pd.read_excel(filepath)
    _check_required(df, _ARCHER_REQUIRED, filepath)
    logger.info(f"  Loaded {len(df)} Archer issue rows")

    pre = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    removed = pre - len(df)
    if removed:
        logger.warning(f"  Archer file had {removed} bit-for-bit duplicate rows; kept {len(df)}")
    issue_dupes = df.duplicated(subset=["Issue ID"]).sum()
    if issue_dupes:
        logger.warning(
            f"  Archer still has {issue_dupes} rows with non-unique Issue IDs after dedup — "
            f"downstream joins may multiply."
        )

    return df


def _detect_pg_flag(desc) -> bool:
    """True if Issue Description starts with `#PG` or `PG` (boundary-checked).

    Case-sensitive. Returns False for blank/None/NaN.
    """
    if _is_blank(desc):
        return False
    return _PG_FLAG_RE.match(str(desc).lstrip()) is not None


def _load_controls(filepath: Path) -> pd.DataFrame:
    logger.info(f"Reading Controls Map from {filepath}")
    df = pd.read_excel(filepath)
    _check_required(df, _CONTROLS_REQUIRED, filepath)
    logger.info(f"  Loaded {len(df)} controls map rows")
    return df


def _build_legacy_explode(legacy_df: pd.DataFrame, C: dict) -> pd.DataFrame:
    """Explode legacy on PRSA -> one row per (AE, PRSA ID).

    Returns a DataFrame with the original AE metadata columns plus a single
    PRSA ID per row (header still ``C["legacy_prsa"]`` at this stage).
    """
    exploded = _explode_newline(legacy_df, C["legacy_prsa"])
    logger.info(f"  Legacy exploded: {len(exploded)} (AE, PRSA) pairs across "
                f"{exploded[C['legacy_entity_id']].nunique()} entities")
    return exploded


def _build_all_prsas_per_ae(legacy_df: pd.DataFrame, C: dict) -> dict:
    """Map AE ID -> list of unique PRSA IDs (sorted for determinism)."""
    out: dict[str, list[str]] = {}
    for _, row in legacy_df.iterrows():
        ae_id = str(row[C["legacy_entity_id"]]).strip()
        if not ae_id or ae_id.lower() == "nan":
            continue
        raw = row[C["legacy_prsa"]]
        if _is_blank(raw):
            out.setdefault(ae_id, [])
            continue
        prsa_ids = [p.strip() for p in str(raw).replace("\r\n", "\n").replace("\r", "\n").split("\n") if p.strip()]
        # Preserve order in legacy file (no sort) so the output lists read the
        # same way Lu sees them in source.
        seen = set()
        ordered = []
        for p in prsa_ids:
            if p not in seen:
                seen.add(p)
                ordered.append(p)
        out[ae_id] = ordered
    return out


def _filter_archer(archer_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, int, int, pd.DataFrame]:
    """Split Archer rows into mapped (with PRSA control) and PG-flagged unmapped.

    Returns:
        (mapped_df, pg_unmapped_df, dropped_count, pg_retained_count, dropped_df)
        - mapped_df: rows with non-blank Control ID (PRSA). Continue through the
          explode/join pipeline as before.
        - pg_unmapped_df: rows with blank Control ID (PRSA) but Is PG Gap == True.
          Bypass the controls/legacy joins and join the final output with blank
          AE / Control / PRSA fields populated only for the issue block.
        - dropped_count: rows with blank Control ID (PRSA) AND not PG-flagged
          (current behavior — RCSA-only or pure unmapped issues stay dropped).
        - pg_retained_count: PG-flagged unmapped rows preserved (NEW).
        - dropped_df: the dropped non-PG, no-control Archer rows (surfaced via
          the orphan sidecar).
    """
    blank_ctrl = archer_df["Control ID (PRSA)"].map(_is_blank)
    is_pg = archer_df["Is PG Gap"] if "Is PG Gap" in archer_df.columns else (
        archer_df["Issue Description"].map(_detect_pg_flag)
    )

    mapped = archer_df.loc[~blank_ctrl].reset_index(drop=True)
    pg_unmapped = archer_df.loc[blank_ctrl & is_pg].reset_index(drop=True)
    dropped_mask = blank_ctrl & ~is_pg
    dropped = int(dropped_mask.sum())
    pg_retained = int(len(pg_unmapped))
    dropped_df = archer_df.loc[dropped_mask].reset_index(drop=True)

    if dropped:
        rcsa_only = archer_df.loc[dropped_mask & ~archer_df["Control ID (RCSA)"].map(_is_blank)]
        logger.info(f"  Dropped {dropped} Archer rows with blank Control ID (PRSA) and no PG flag "
                    f"({len(rcsa_only)} of which had RCSA-only mapping)")
    if pg_retained:
        logger.info(f"  PG-flagged Archer rows retained without controls: {pg_retained}")
    return mapped, pg_unmapped, dropped, pg_retained, dropped_df


def _explode_archer(archer_df: pd.DataFrame) -> pd.DataFrame:
    exploded = _explode_newline(archer_df, "Control ID (PRSA)")
    logger.info(f"  Archer exploded: {len(exploded)} (Issue, Control) pairs")
    return exploded


def _join_controls(archer_exploded: pd.DataFrame, controls_df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Inner-join Archer.Control ID (PRSA) <-> controls_map.Control ID.

    Returns (joined_df, orphan_control_ids).
    """
    archer_ctrl_ids = set(archer_exploded["Control ID (PRSA)"].astype(str).str.strip().unique())
    map_ctrl_ids = set(controls_df["Control ID"].astype(str).str.strip().unique())
    orphans = sorted(archer_ctrl_ids - map_ctrl_ids)

    joined = archer_exploded.merge(
        controls_df,
        how="inner",
        left_on="Control ID (PRSA)",
        right_on="Control ID",
    )
    logger.info(f"  After controls join: {len(joined)} rows")
    if orphans:
        logger.warning(f"  {len(orphans)} Archer Control IDs had no match in Controls Map "
                       f"(rows dropped): {orphans}")
    return joined, orphans


def _join_legacy(joined_df: pd.DataFrame, legacy_explode: pd.DataFrame, C: dict) -> tuple[pd.DataFrame, list[str]]:
    """Inner-join Process ID <-> legacy.PRSA -> one row per (AE, Issue, Control).

    Returns (final_df, orphan_prsas).
    """
    legacy_prsa_ids = set(legacy_explode[C["legacy_prsa"]].astype(str).str.strip().unique())
    joined_prsa_ids = set(joined_df["Process ID"].astype(str).str.strip().unique())
    orphans = sorted(joined_prsa_ids - legacy_prsa_ids)

    merged = joined_df.merge(
        legacy_explode,
        how="inner",
        left_on="Process ID",
        right_on=C["legacy_prsa"],
    )
    logger.info(f"  After legacy join: {len(merged)} rows")
    if orphans:
        logger.warning(f"  {len(orphans)} Process IDs from controls map had no AE in legacy "
                       f"(rows dropped): {orphans}")
    return merged, orphans


def _attach_all_prsas(merged: pd.DataFrame, all_prsas_per_ae: dict, C: dict) -> pd.DataFrame:
    merged = merged.copy()
    merged[C["out_all_prsas_tagged"]] = merged[C["legacy_entity_id"]].map(
        lambda eid: "\n".join(all_prsas_per_ae.get(str(eid).strip(), []))
    )
    return merged


def _select_and_rename(merged: pd.DataFrame, C: dict) -> pd.DataFrame:
    """Project to the output schema (column order matches YAML columns.prsa)."""
    pg_yes_no = merged["Is PG Gap"].map(lambda v: "Yes" if bool(v) else "No") \
        if "Is PG Gap" in merged.columns else "No"
    out = pd.DataFrame({
        C["out_ae_id"]:               merged[C["legacy_entity_id"]].astype(str).str.strip(),
        C["out_ae_name"]:             merged[C["legacy_entity_name"]],
        C["out_audit_leader"]:        merged[C["legacy_audit_leader"]],
        C["out_core_audit_team"]:     merged[C["legacy_core_audit_team"]],
        C["out_audit_engagement_id"]: merged[C["legacy_audit_eng_id"]],
        C["out_all_prsas_tagged"]:    merged[C["out_all_prsas_tagged"]],
        C["out_issue_id"]:            merged["Issue ID"],
        C["out_issue_rating"]:        merged["Issue Impact Rating"],
        C["out_issue_status"]:        merged["Issue Status"],
        C["out_issue_identifier"]:    merged["Issue Identifier"],
        C["out_issue_title"]:         merged["Issue Title"],
        C["out_issue_description"]:   merged["Issue Description"],
        C["out_issue_owner"]:         merged["Issue Owner"],
        C["out_root_cause_desc"]:     merged["Root Cause Description"],
        C["out_root_cause_sub"]:      merged["Root Cause Sub-Theme"],
        C["out_root_cause_theme"]:    merged["Root Cause Theme"],
        C["out_risk_level_2"]:        merged["Risk Level 2"],
        C["out_control_id_prsa"]:     merged["Control ID (PRSA)"],
        C["out_prsa_id"]:             merged["Process ID"],
        C["out_process_title"]:       merged["Process Title"],
        C["out_control_title"]:       merged["Control Title"],
        C["out_is_pg_gap"]:           pg_yes_no,
    })
    return out[_output_column_order(C)]


def _select_and_rename_pg_unmapped(pg_unmapped: pd.DataFrame, C: dict) -> pd.DataFrame:
    """Project PG-flagged Archer rows that lack a PRSA control to the output schema.

    AE / Control / PRSA fields are blank — only the Issue block is populated.
    Used to surface PG gaps that should be entered against a PRSA control in
    IRM Archer but aren't yet, so the responsible team can see what's missing.
    """
    if pg_unmapped is None or pg_unmapped.empty:
        return pd.DataFrame(columns=_output_column_order(C))
    n = len(pg_unmapped)
    blank_series = pd.Series([""] * n, index=pg_unmapped.index)
    out = pd.DataFrame({
        C["out_ae_id"]:               blank_series,
        C["out_ae_name"]:             blank_series,
        C["out_audit_leader"]:        blank_series,
        C["out_core_audit_team"]:     blank_series,
        C["out_audit_engagement_id"]: blank_series,
        C["out_all_prsas_tagged"]:    blank_series,
        C["out_issue_id"]:            pg_unmapped["Issue ID"],
        C["out_issue_rating"]:        pg_unmapped["Issue Impact Rating"],
        C["out_issue_status"]:        pg_unmapped["Issue Status"],
        C["out_issue_identifier"]:    pg_unmapped["Issue Identifier"],
        C["out_issue_title"]:         pg_unmapped["Issue Title"],
        C["out_issue_description"]:   pg_unmapped["Issue Description"],
        C["out_issue_owner"]:         pg_unmapped["Issue Owner"],
        C["out_root_cause_desc"]:     pg_unmapped["Root Cause Description"],
        C["out_root_cause_sub"]:      pg_unmapped["Root Cause Sub-Theme"],
        C["out_root_cause_theme"]:    pg_unmapped["Root Cause Theme"],
        C["out_risk_level_2"]:        pg_unmapped["Risk Level 2"],
        C["out_control_id_prsa"]:     blank_series,
        C["out_prsa_id"]:             blank_series,
        C["out_process_title"]:       blank_series,
        C["out_control_title"]:       blank_series,
        C["out_is_pg_gap"]:           pd.Series(["Yes"] * n, index=pg_unmapped.index),
    })
    return out[_output_column_order(C)]


def _flag_natural_dupes(df: pd.DataFrame, C: dict) -> None:
    """Log if any (AE, Issue, Control) tuples appear more than once.

    PG-unmapped rows (blank AE+Control) are excluded — they intentionally
    share the same blank grain values and aren't true duplicates.
    """
    grain = [C["out_ae_id"], C["out_issue_id"], C["out_control_id_prsa"]]
    mapped_only = df[df[C["out_ae_id"]].astype(str).str.strip() != ""]
    dupes = mapped_only[mapped_only.duplicated(subset=grain, keep=False)]
    if not dupes.empty:
        logger.warning(f"  Found {len(dupes)} rows with duplicate "
                       f"(AE, Issue, Control) keys -- source data quality issue:")
        for _, row in dupes.iterrows():
            logger.warning(f"    {row[C['out_ae_id']]} / {row[C['out_issue_id']]} / "
                           f"{row[C['out_control_id_prsa']]}")


def _log_cross_ae_summary(all_prsas_per_ae: dict) -> None:
    """Log PRSAs tagged to more than one AE (informational)."""
    prsa_to_aes: dict[str, list[str]] = {}
    for ae_id, prsas in all_prsas_per_ae.items():
        for p in prsas:
            prsa_to_aes.setdefault(p, []).append(ae_id)
    shared = {p: aes for p, aes in prsa_to_aes.items() if len(aes) > 1}
    if not shared:
        logger.info("  No cross-AE PRSAs (every PRSA tags exactly one AE)")
        return
    logger.info(f"  Cross-AE PRSAs (tagged to >1 AE): {len(shared)}")
    for prsa_id, aes in sorted(shared.items())[:5]:
        logger.info(f"    {prsa_id}: {sorted(aes)}")
    if len(shared) > 5:
        logger.info(f"    ... and {len(shared) - 5} more")


def _write_dropped_sidecar(dropped_df: pd.DataFrame, report_out_path: Path, source_filename: str) -> Path:
    """Sidecar of non-PG, no-control Archer rows for the Upstream Tagging Gaps tab."""
    report_out_path = Path(report_out_path)
    sidecar_path = report_out_path.parent / (report_out_path.stem + "_orphans" + report_out_path.suffix)
    n = len(dropped_df)

    def _col(df, col):
        if not col or col not in df.columns:
            return [""] * n
        return df[col].astype(str).tolist()

    out = pd.DataFrame({
        "Source": ["PRSA"] * n,
        "Item ID": _col(dropped_df, "Issue ID"),
        "Title": _col(dropped_df, "Issue Title"),
        "Status": _col(dropped_df, "Issue Status"),
        "Drop Reason": ["No PRSA control"] * n,
        "Source File": [source_filename] * n,
    })[["Source", "Item ID", "Title", "Status", "Drop Reason", "Source File"]]
    out.to_excel(sidecar_path, index=False)
    return sidecar_path


# ---------------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------------

def build(args: argparse.Namespace) -> Path:
    cfg = _load_config()
    C = _resolve_columns(cfg)

    paths = _resolve_input_paths(args)
    out_path = _resolve_output_path(args)

    logger.info("=" * 60)
    logger.info("PRSA Frankenstein build")
    logger.info("=" * 60)
    logger.info(f"  legacy:   {paths['legacy']}")
    logger.info(f"  archer:   {paths['archer']}")
    logger.info(f"  controls: {paths['controls']}")
    logger.info(f"  output:   {out_path}")

    # 1. Load
    legacy_df = _load_legacy(paths["legacy"], C)
    archer_df = _load_archer(paths["archer"])
    controls_df = _load_controls(paths["controls"])

    # 1a. Detect PG flag per Archer issue. The flag is per-issue (driven by
    # Issue Description prefix) and propagates through the explode-on-controls
    # step. Boolean column `Is PG Gap` is added in-place so downstream stages
    # can read it without recomputing.
    archer_df = archer_df.copy()
    archer_df["Is PG Gap"] = archer_df["Issue Description"].map(_detect_pg_flag)
    pg_total_in_source = int(archer_df["Is PG Gap"].sum())
    logger.info(f"  PG flag detected on {pg_total_in_source} of {len(archer_df)} Archer issues")

    # 2. Build the per-AE all-PRSAs lookup (BEFORE any filtering)
    all_prsas_per_ae = _build_all_prsas_per_ae(legacy_df, C)

    # 3. Explode legacy on PRSA
    legacy_explode = _build_legacy_explode(legacy_df, C)

    # 4. Filter Archer: split into mapped (with control) and PG-flagged unmapped
    archer_mapped, pg_unmapped, archer_dropped, pg_retained, archer_dropped_df = _filter_archer(archer_df)
    archer_exploded = _explode_archer(archer_mapped)

    # 5. Inner-join controls map (Control ID (PRSA) <-> Control ID)
    after_controls, orphan_controls = _join_controls(archer_exploded, controls_df)

    # 6. Inner-join legacy (Process ID <-> legacy.PRSA)
    merged, orphan_prsas = _join_legacy(after_controls, legacy_explode, C)

    # 7. Attach All PRSAs Tagged to AE column
    merged = _attach_all_prsas(merged, all_prsas_per_ae, C)

    # 8. Select + rename to output schema. Mapped rows + PG-flagged unmapped
    # rows (blank AE/Control block, only Issue block populated) are concatenated.
    mapped_out = _select_and_rename(merged, C)
    pg_unmapped_out = _select_and_rename_pg_unmapped(pg_unmapped, C)
    if pg_unmapped_out.empty:
        out_df = mapped_out
    else:
        out_df = pd.concat([mapped_out, pg_unmapped_out], ignore_index=True)

    # 9. Quality checks (informational)
    _flag_natural_dupes(out_df, C)
    _log_cross_ae_summary(all_prsas_per_ae)

    # 10. Write
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        out_df.to_excel(writer, index=False)

    if not archer_dropped_df.empty:
        sidecar = _write_dropped_sidecar(archer_dropped_df, out_path, Path(paths["archer"]).name)
        logger.info(f"  Dropped-issues sidecar saved: {sidecar} ({len(archer_dropped_df)} rows)")

    logger.info("=" * 60)
    logger.info("Build summary")
    logger.info("=" * 60)
    logger.info(f"  Final rows:                     {len(out_df)}")
    logger.info(f"  Unique AEs in output:           {out_df[C['out_ae_id']].nunique()}")
    logger.info(f"  Unique Issues in output:        {out_df[C['out_issue_id']].nunique()}")
    logger.info(f"  Unique PRSAs in output:         {out_df[C['out_prsa_id']].nunique()}")
    logger.info(f"  Unique Controls in output:      {out_df[C['out_control_id_prsa']].nunique()}")
    logger.info(f"  Archer rows dropped (blank):    {archer_dropped}")
    logger.info(f"  PG-unmapped rows retained:      {pg_retained}")
    pg_yes_in_output = int((out_df[C["out_is_pg_gap"]] == "Yes").sum())
    logger.info(f"  PG gaps in final output:        {pg_yes_in_output}")
    logger.info(f"  Orphan Control IDs (no map):    {len(orphan_controls)}")
    logger.info(f"  Orphan PRSAs (no AE in legacy): {len(orphan_prsas)}")
    logger.info(f"  Output:                         {out_path}")

    if len(out_df) == 0:
        logger.warning("=" * 60)
        logger.warning("Output has 0 rows. Likely causes:")
        logger.warning("  - All Archer rows had blank Control ID (PRSA) (RCSA-only issues)")
        logger.warning("  - legacy_risk_data PRSA column is empty for all AEs")
        logger.warning("  - No matching Process IDs between legacy and controls map")
        logger.warning("Output file written but is empty. Review input files before "
                       "using downstream.")
        logger.warning("=" * 60)

    return out_path


# ---------------------------------------------------------------------------
# Test-dummy verification
# ---------------------------------------------------------------------------

def _verify_test_dummy(built_path: Path) -> None:
    """When run with --test-dummy, sanity-check shape and column set against
    the golden file generated by tests/generate_prsa_source_test_data.py.
    """
    golden_path = _INPUT_DIR / "prsa_report_test_dummy.xlsx"
    if not golden_path.exists():
        logger.warning(f"  Golden file not found at {golden_path}; skipping sanity check")
        return

    built = pd.read_excel(built_path)
    golden = pd.read_excel(golden_path)

    logger.info("=" * 60)
    logger.info("Test-dummy sanity check (vs golden)")
    logger.info("=" * 60)
    logger.info(f"  Built  rows: {len(built)},  cols: {len(built.columns)}")
    logger.info(f"  Golden rows: {len(golden)}, cols: {len(golden.columns)}")

    if len(built) != len(golden):
        logger.error(f"  ROW COUNT MISMATCH: built={len(built)}, golden={len(golden)}")
        return

    built_cols = set(built.columns)
    golden_cols = set(golden.columns)
    if built_cols != golden_cols:
        only_built = sorted(built_cols - golden_cols)
        only_golden = sorted(golden_cols - built_cols)
        logger.error(f"  COLUMN SET MISMATCH:")
        if only_built:
            logger.error(f"    Only in built:  {only_built}")
        if only_golden:
            logger.error(f"    Only in golden: {only_golden}")
        return

    if list(built.columns) != list(golden.columns):
        logger.warning("  Column SET matches but column ORDER differs from golden "
                       "(spec says 'match YAML exactly' -- golden file may need refresh)")
        logger.info(f"    Built  order: {list(built.columns)}")
        logger.info(f"    Golden order: {list(golden.columns)}")
    else:
        logger.info("  Column order matches golden")

    logger.info("  Shape and column-set match golden; cell-level diff is validation-qa's job")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build the PRSA Frankenstein report from three source extracts.",
    )
    p.add_argument(
        "--test-dummy",
        action="store_true",
        help="Use *_test_dummy.xlsx fixtures and write to "
             "data/input/prsa_report_test_dummy_BUILT.xlsx (does not overwrite the "
             "golden prsa_report_test_dummy.xlsx).",
    )
    p.add_argument("--legacy", help="Path to legacy_risk_data_*.xlsx")
    p.add_argument("--archer", help="Path to PRSA_IRM_Archer_*.xlsx")
    p.add_argument("--controls", help="Path to PRSA_Controls_Map_*.xlsx")
    p.add_argument("--output", help="Explicit output path (Excel)")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    out_path = build(args)
    if args.test_dummy:
        _verify_test_dummy(out_path)


if __name__ == "__main__":
    main()
