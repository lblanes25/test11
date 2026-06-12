"""
Consolidate the denormalized IRM ORE Archer export to one row per ORE ID.

The raw IRM ORE export is "stacked": a single ORE fans out into multiple
rows because three independent one-to-many child sections (Cause, Risk,
Impact) are each emitted as their own row, with the other two sections'
columns blank. This is additive stacking, not a Cartesian product (no row
carries cause + risk + impact together). This pre-step collapses the stack
to one row per ORE before the ore_irm mapper and ingestion read it.

Column names come from ``config/taxonomy_config.yaml`` under
``columns.ore_irm_consolidate``.

Usage:
    # Production (latest IRM_ORE_raw_*, timestamped output):
    python consolidate_ore_irm.py

    # Test-dummy (reads IRM_ORE_raw_test_dummy.csv; writes
    # ORE_IRM_consolidated_test_dummy_BUILT.xlsx):
    python consolidate_ore_irm.py --test-dummy

    # Explicit overrides:
    python consolidate_ore_irm.py --raw <path> --output <path>

Output:
    - data/input/ORE_IRM_consolidated_<MMDDYYYYHHMMpm>.xlsx (production)
    - data/input/ORE_IRM_consolidated_test_dummy_BUILT.xlsx (test-dummy)
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

from risk_taxonomy_transformer.ingestion import _derive_irm_ore_status, _is_material_ore
from risk_taxonomy_transformer.utils import latest_input


_PROJECT_ROOT = Path(__file__).resolve().parent
_INPUT_DIR = _PROJECT_ROOT / "data" / "input"
_CONFIG_PATH = _PROJECT_ROOT / "config" / "taxonomy_config.yaml"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# Preservation columns (tool-added). Match these names downstream if you read
# the consolidated output.
COL_SOURCE_ROW_COUNT = "Source Row Count"
COL_CAUSE_ROW_COUNT = "Cause Row Count"
COL_RISK_ROW_COUNT = "Risk Row Count"
COL_IMPACT_ROW_COUNT = "Impact Assessment Row Count"
COL_IMPACT_STATUS_COUNTS = "Impact Assessment Status Counts"
COL_IMPACT_CLOSED = "Impact Assessment Closed"
COL_ORE_STATUS = "ORE Status"
COL_ORE_MATERIALITY = "ORE Materiality"


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _resolve_config(cfg: dict) -> dict:
    cols = cfg.get("columns", {})
    cc = cols.get("ore_irm_consolidate", {})
    return {
        "raw_file_pattern": cc.get("raw_file_pattern", "IRM_ORE_raw_*.csv"),
        "output_prefix": cc.get("output_prefix", "ORE_IRM_consolidated"),
        "ore_level_cols": list(cc.get("ore_level_cols", [])),
        "cause_cols": list(cc.get("cause_cols", [])),
        "risk_cols": list(cc.get("risk_cols", [])),
        "impact_id_col": cc.get("impact_id_col", "Impact ID"),
        "impact_status_col": cc.get("impact_status_col", "Impact Assessment Status"),
        "impact_open_statuses": list(cc.get("impact_open_statuses", ["In-Progress", ""])),
        # Inputs for the shared ORE Status deriver (reused from ingestion so the
        # mapper's skip and the displayed status are computed once, identically).
        "ore_irm_cols": cols.get("ore_irm", {}),
        "completed_values": {str(v).strip().lower()
                             for v in cfg.get("ore_phase_completed_values", ["completed", "complete"])},
        "material_categories": {str(v).strip().lower()
                                for v in cfg.get("ore_material_categories", ["Material ORE"])},
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_blank(val) -> bool:
    if val is None:
        return True
    s = str(val).strip()
    return s == "" or s.lower() in ("nan", "none", "nat")


def _norm(val) -> str:
    if _is_blank(val):
        return ""
    return str(val).strip()


def _distinct_join(values: list) -> str:
    """First-seen-ordered distinct non-blank values, newline-joined."""
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        s = _norm(v)
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def _latest_raw(pattern: str, input_dir: Path) -> Path:
    """Newest raw file matching the pattern's stem against .csv and .xlsx."""
    stem = pattern.rsplit(".", 1)[0]
    match = latest_input(
        input_dir, [f"{stem}.csv", f"{stem}.xlsx"], log_label="raw IRM ORE export",
    )
    if match is None:
        raise FileNotFoundError(
            f"No file matching '{stem}.csv' or '{stem}.xlsx' in {input_dir}"
        )
    return match


def _resolve_input_path(args: argparse.Namespace, C: dict) -> Path:
    if args.raw:
        p = Path(args.raw)
    elif args.test_dummy:
        p = _INPUT_DIR / "IRM_ORE_raw_test_dummy.csv"
    else:
        p = _latest_raw(C["raw_file_pattern"], _INPUT_DIR)
    if not p.exists():
        raise FileNotFoundError(f"raw IRM ORE file does not exist: {p}")
    return p


def _resolve_output_path(args: argparse.Namespace, C: dict) -> Path:
    if args.output:
        return Path(args.output)
    if args.test_dummy:
        return _INPUT_DIR / "ORE_IRM_consolidated_test_dummy_BUILT.xlsx"
    timestamp = datetime.now().strftime("%m%d%Y%I%M%p")
    return _INPUT_DIR / f"{C['output_prefix']}_{timestamp}.xlsx"


# ---------------------------------------------------------------------------
# Load + validate
# ---------------------------------------------------------------------------

def _load_raw(filepath: Path) -> pd.DataFrame:
    logger.info(f"Reading raw IRM ORE export from {filepath}")
    if str(filepath).lower().endswith(".csv"):
        df = pd.read_csv(filepath, dtype=str, keep_default_na=False)
    else:
        df = pd.read_excel(filepath, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]
    logger.info(f"  Loaded {len(df)} raw rows, {len(df.columns)} columns")
    return df


def _required_columns(C: dict) -> list[str]:
    ore_id = C["ore_level_cols"][0] if C["ore_level_cols"] else "ORE ID"
    req = list(C["ore_level_cols"]) + list(C["cause_cols"]) + list(C["risk_cols"]) + [
        C["impact_id_col"], C["impact_status_col"],
    ]
    if ore_id not in req:
        req.insert(0, ore_id)
    seen: set[str] = set()
    ordered = []
    for c in req:
        if c not in seen:
            seen.add(c)
            ordered.append(c)
    return ordered


def _check_required(df: pd.DataFrame, required: list[str], filepath: Path) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"{filepath} missing required columns: {missing}. "
            f"Found: {list(df.columns)}"
        )


# ---------------------------------------------------------------------------
# Consolidation
# ---------------------------------------------------------------------------

def _impact_status_counts(statuses: list) -> str:
    """Human-readable count of raw impact statuses, e.g. 'Completed (53)'.

    Blanks are reported as '(blank) (n)' only when present. Ordered by
    descending count, then by name.
    """
    counts: dict[str, int] = {}
    for s in statuses:
        label = _norm(s) if not _is_blank(s) else "(blank)"
        counts[label] = counts.get(label, 0) + 1
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return ", ".join(f"{name} ({n})" for name, n in items)


def _impact_closed(statuses: list, open_statuses_norm: set[str]) -> str:
    """'Yes' iff >=1 impact row and no impact status is open; else 'No'.

    An ORE with zero impact rows => 'No' (blank impact == open).
    """
    if not statuses:
        return "No"
    for s in statuses:
        val = _norm(s).lower()
        if val in open_statuses_norm:
            return "No"
    return "Yes"


def _consolidate(df: pd.DataFrame, C: dict) -> pd.DataFrame:
    ore_id_col = C["ore_level_cols"][0]
    df = df.copy()
    df[ore_id_col] = df[ore_id_col].map(_norm)
    pre = len(df)
    df = df[df[ore_id_col] != ""].reset_index(drop=True)
    dropped = pre - len(df)
    if dropped:
        logger.warning(f"  Dropped {dropped} rows with blank ORE ID")

    cause_id_col = C["cause_cols"][0] if C["cause_cols"] else None
    risk_l2_col = C["risk_cols"][0] if C["risk_cols"] else None
    risk_l4_col = C["risk_cols"][1] if len(C["risk_cols"]) > 1 else None
    impact_id_col = C["impact_id_col"]
    impact_status_col = C["impact_status_col"]
    open_statuses_norm = {str(s).strip().lower() for s in C["impact_open_statuses"]}

    out_rows: list[dict] = []
    for ore_id, grp in df.groupby(ore_id_col, sort=False):
        row: dict = {}

        for col in C["ore_level_cols"]:
            first = ""
            for v in grp[col].tolist():
                if not _is_blank(v):
                    first = _norm(v)
                    break
            row[col] = first

        for col in C["cause_cols"]:
            row[col] = _distinct_join(grp[col].tolist())
        for col in C["risk_cols"]:
            row[col] = _distinct_join(grp[col].tolist())

        row[impact_id_col] = _distinct_join(grp[impact_id_col].tolist())
        row[impact_status_col] = _distinct_join(grp[impact_status_col].tolist())

        cause_mask = grp[cause_id_col].map(lambda v: not _is_blank(v)) if cause_id_col else pd.Series([False] * len(grp))
        risk_mask = pd.Series([False] * len(grp), index=grp.index)
        if risk_l2_col:
            risk_mask = risk_mask | grp[risk_l2_col].map(lambda v: not _is_blank(v))
        if risk_l4_col:
            risk_mask = risk_mask | grp[risk_l4_col].map(lambda v: not _is_blank(v))
        impact_mask = (
            grp[impact_id_col].map(lambda v: not _is_blank(v))
            | grp[impact_status_col].map(lambda v: not _is_blank(v))
        )

        impact_rows = grp[impact_mask]
        impact_status_values = impact_rows[impact_status_col].tolist()

        row[COL_SOURCE_ROW_COUNT] = len(grp)
        row[COL_CAUSE_ROW_COUNT] = int(cause_mask.sum())
        row[COL_RISK_ROW_COUNT] = int(risk_mask.sum())
        row[COL_IMPACT_ROW_COUNT] = int(impact_mask.sum())
        row[COL_IMPACT_STATUS_COUNTS] = _impact_status_counts(impact_status_values)
        row[COL_IMPACT_CLOSED] = _impact_closed(impact_status_values, open_statuses_norm)

        # Derive the Open/Closed status once here (four phases + cancelled
        # short-circuit) for display on the Source tab, plus a separate
        # Material/Non-Material flag. Reuses the ingestion derivers. The mapper
        # maps all IRM OREs regardless of either value.
        row[COL_ORE_STATUS] = _derive_irm_ore_status(
            row, C["ore_irm_cols"], C["completed_values"], C["material_categories"])
        row[COL_ORE_MATERIALITY] = (
            "Material" if _is_material_ore(row, C["ore_irm_cols"], C["material_categories"])
            else "Non-Material")

        out_rows.append(row)

    out = pd.DataFrame(out_rows)
    out = out[_output_column_order(C)]
    return out


def _output_column_order(C: dict) -> list[str]:
    return (
        list(C["ore_level_cols"])
        + list(C["cause_cols"])
        + list(C["risk_cols"])
        + [C["impact_id_col"], C["impact_status_col"]]
        + [
            COL_SOURCE_ROW_COUNT,
            COL_CAUSE_ROW_COUNT,
            COL_RISK_ROW_COUNT,
            COL_IMPACT_ROW_COUNT,
            COL_IMPACT_STATUS_COUNTS,
            COL_IMPACT_CLOSED,
            COL_ORE_STATUS,
            COL_ORE_MATERIALITY,
        ]
    )


# ---------------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------------

def build(args: argparse.Namespace) -> Path:
    cfg = _load_config()
    C = _resolve_config(cfg)

    raw_path = _resolve_input_path(args, C)
    out_path = _resolve_output_path(args, C)

    logger.info("=" * 60)
    logger.info("IRM ORE consolidation")
    logger.info("=" * 60)
    logger.info(f"  raw:    {raw_path}")
    logger.info(f"  output: {out_path}")

    df = _load_raw(raw_path)
    _check_required(df, _required_columns(C), raw_path)

    raw_rows = len(df)
    out_df = _consolidate(df, C)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        out_df.to_excel(writer, index=False)

    closed_yes = int((out_df[COL_IMPACT_CLOSED] == "Yes").sum())
    closed_no = int((out_df[COL_IMPACT_CLOSED] == "No").sum())
    status_open = int((out_df[COL_ORE_STATUS] == "Open").sum())
    status_closed = int((out_df[COL_ORE_STATUS] == "Closed").sum())
    material_n = int((out_df[COL_ORE_MATERIALITY] == "Material").sum())
    nonmaterial_n = int((out_df[COL_ORE_MATERIALITY] == "Non-Material").sum())

    logger.info("=" * 60)
    logger.info("Consolidation summary")
    logger.info("=" * 60)
    logger.info(f"  Raw rows in:                 {raw_rows}")
    logger.info(f"  Unique OREs out:             {len(out_df)}")
    logger.info(f"  Impact Assessment Closed=Yes: {closed_yes}")
    logger.info(f"  Impact Assessment Closed=No:  {closed_no}")
    logger.info(f"  ORE Status: {status_open} Open / {status_closed} Closed "
                f"— derived for display; mapper maps all")
    logger.info(f"  ORE Materiality: {material_n} Material / {nonmaterial_n} Non-Material "
                f"— separate flag gating Impact of Issues only")
    logger.info(f"  Output:                      {out_path}")

    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Collapse the stacked IRM ORE Archer export to one row per ORE ID.",
    )
    p.add_argument(
        "--test-dummy",
        action="store_true",
        help="Read data/input/IRM_ORE_raw_test_dummy.csv and write "
             "data/input/ORE_IRM_consolidated_test_dummy_BUILT.xlsx (does not "
             "overwrite the golden ORE_IRM_consolidated_test_dummy.xlsx).",
    )
    p.add_argument("--raw", help="Path to the raw IRM_ORE_raw_*.csv/.xlsx export")
    p.add_argument("--output", help="Explicit output path (Excel)")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    build(args)


if __name__ == "__main__":
    main()
