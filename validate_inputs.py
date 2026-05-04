"""
Validate that every YAML-configured column header matches the actual
columns in each input file. Catches silent column-name drops (the kind
that made key_thirdparties miss because the real header was plural).

Usage:
    python validate_inputs.py

Reports OK/MISS per input source. Run after any data refresh or after
editing YAML column mappings.

Exit code 0 if everything matches, 1 if any MISS.
"""
from __future__ import annotations

import glob
import sys
from pathlib import Path

import pandas as pd
import yaml

_ROOT = Path(__file__).resolve().parent
_INPUT_DIR = _ROOT / "data" / "input"
_OUTPUT_DIR = _ROOT / "data" / "output"


def _latest(patterns: list[str], where: Path = _INPUT_DIR) -> Path | None:
    matches: list[Path] = []
    for p in patterns:
        matches.extend(where.glob(p))
    if not matches:
        return None
    return max(matches, key=lambda f: f.stat().st_mtime)


def _read_columns(filepath: Path) -> list[str] | None:
    try:
        if str(filepath).endswith(".csv"):
            df = pd.read_csv(filepath, nrows=0)
        else:
            df = pd.read_excel(filepath, nrows=0)
        return [str(c).strip() for c in df.columns]
    except Exception as e:
        print(f"  ERROR reading {filepath.name}: {e}")
        return None


def _check(label: str, filepath: Path | None, expected: dict[str, str],
           optional_keys: set[str] | None = None) -> int:
    """expected: {internal_name: actual_header_text}. Returns # of REQUIRED misses.

    Optional keys (in `optional_keys`) are reported as [opt-MISS] and don't
    count toward the failure total.
    """
    print(f"\n=== {label} ===")
    if filepath is None:
        print("  (no file found — skipped)")
        return 0
    print(f"  file: {filepath.name}")
    cols = _read_columns(filepath)
    if cols is None:
        return 1
    cols_set = set(cols)
    optional_keys = optional_keys or set()

    misses = 0
    for internal, actual in expected.items():
        if not actual:
            continue
        is_optional = internal in optional_keys or "(optional)" in internal
        if actual in cols_set:
            print(f"  [ OK ]      {internal:30s} -> {actual!r}")
        else:
            tokens = [t for t in str(actual).upper().split() if len(t) > 3]
            hints = [c for c in cols if any(t in c.upper() for t in tokens)]
            hint_str = f"  HINT: {hints}" if hints else ""
            if is_optional:
                print(f"  [opt-MISS]  {internal:30s} -> {actual!r}{hint_str}")
            else:
                misses += 1
                print(f"  [MISS]      {internal:30s} -> {actual!r}{hint_str}")
    return misses


def main() -> int:
    cfg_path = _ROOT / "config" / "taxonomy_config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    col_cfg = cfg.get("columns", {})

    total_misses = 0

    # --- Legacy risk data ---
    # Columns are dynamic: per-pillar × suffix + entity metadata + applications + aux/core
    legacy_file = _latest(["legacy_risk_data_*.xlsx", "legacy_risk_data_*.csv"])
    if legacy_file:
        suffixes = col_cfg.get("pillar_suffixes", {
            "rating": "Inherent Risk",
            "rationale": "Inherent Risk Rationale",
            "control": "Control Assessment",
            "control_rationale": "Control Assessment Rationale",
        })
        pillars_with = col_cfg.get("pillars_with_rationale", [])
        pillars_without = col_cfg.get("pillars_without_rationale", [])

        legacy_expected: dict[str, str] = {}
        # Entity ID / metadata
        legacy_expected["entity_id"] = col_cfg.get("entity_id", "Audit Entity ID")
        for k, v in col_cfg.get("org_metadata", {}).items():
            legacy_expected[f"org.{k}"] = v
        # Control effectiveness
        for k, v in col_cfg.get("control_effectiveness", {}).items():
            legacy_expected[f"ce.{k}"] = v
        # Applications
        for k, v in col_cfg.get("applications", {}).items():
            legacy_expected[f"apps.{k}"] = v
        # Aux + core
        for v in col_cfg.get("auxiliary_risk_dimensions", []):
            legacy_expected[f"aux.{v}"] = v
        for v in col_cfg.get("core_risk_dimensions", []):
            legacy_expected[f"core.{v}"] = v
        # Per-pillar columns
        for p in pillars_with:
            for kind, suf in suffixes.items():
                legacy_expected[f"{p}.{kind}"] = f"{p} {suf}"
        for p in pillars_without:
            legacy_expected[f"{p}.rating"] = f"{p} {suffixes['rating']}"
            legacy_expected[f"{p}.control"] = f"{p} {suffixes['control']}"
        total_misses += _check("Legacy risk data", legacy_file, legacy_expected)
    else:
        print("\n=== Legacy risk data ===")
        print("  (no legacy_risk_data_*.xlsx file found)")

    # --- Key risks ---
    kr_file = _latest(["key_risks_*.xlsx", "key_risks_*.csv",
                       "sub_risk_descriptions_*.xlsx", "sub_risk_descriptions_*.csv"])
    total_misses += _check("Key risks", kr_file, col_cfg.get("key_risks", {}))

    # --- Findings ---
    f_file = _latest(["findings_data_*.xlsx", "findings_data_*.csv"])
    total_misses += _check("Findings", f_file, col_cfg.get("findings", {}))

    # --- PRSA report (raw) ---
    prsa_file = _latest(["prsa_report_*.xlsx", "prsa_report_*.csv"])
    total_misses += _check("PRSA report (raw)", prsa_file, col_cfg.get("prsa", {}))

    # --- BMA ---
    bma_cfg = {k: v for k, v in col_cfg.get("bma", {}).items()
               if k != "min_completion_date"}  # not a column header
    bma_file = _latest(["bm_activities_*.xlsx", "bm_activities_*.csv"])
    total_misses += _check("BM Activities", bma_file, bma_cfg)

    # --- GRA RAPs (raw) ---
    rap_file = _latest(["gra_raps_*.xlsx", "gra_raps_*.csv"])
    total_misses += _check("GRA RAPs (raw)", rap_file, col_cfg.get("gra_raps", {}))

    # --- Optro export ---
    optro_file = _latest(["optro_export_*.xlsx", "optro_export_*.csv"])
    total_misses += _check("Optro export", optro_file, col_cfg.get("optro", {}))

    # --- L2 Taxonomy ---
    l2_file = _INPUT_DIR / "L2_Risk_Taxonomy.xlsx"
    if l2_file.exists():
        l2_expected = {
            "L1 (required)": "L1",
            "L2 (required)": "L2",
            "L2 Definition (required)": "L2 Definition",
            "L1 Definition (optional)": "L1 Definition",
            "L3 (optional)": "L3",
            "L3 Definition (optional)": "L3 Definition",
            "L4 (optional)": "L4",
            "L4 Definition (optional)": "L4 Definition",
        }
        # We don't fail the run on optionals — only the required L1/L2/L2 Definition.
        # For the report, let's still surface every miss so the user sees it.
        total_misses += _check("L2 Taxonomy reference", l2_file, l2_expected)
    else:
        print("\n=== L2 Taxonomy reference ===")
        print("  (no L2_Risk_Taxonomy.xlsx file found)")

    # --- Mapper outputs (validate sheet + required columns, not column-by-column) ---
    print("\n=== Mapper outputs (sheet + required-column check) ===")
    for prefix, label, required_cols in [
        ("ore_mapping", "ORE mapping", ["Event ID", "Audit Entity ID", "Mapping Status", "Mapped L2s"]),
        ("prsa_mapping", "PRSA mapping", ["Issue ID", "AE ID", "Mapping Status", "Mapped L2s"]),
        ("rap_mapping", "RAP mapping", ["RAP ID", "Audit Entity ID", "Mapping Status", "Mapped L2s"]),
    ]:
        files = sorted((_OUTPUT_DIR).glob(f"{prefix}_*.xlsx"),
                       key=lambda f: f.stat().st_mtime)
        if not files:
            print(f"  {label}: (no file found — skip)")
            continue
        latest = files[-1]
        try:
            xls = pd.ExcelFile(latest)
            if "All Mappings" not in xls.sheet_names:
                print(f"  {label}: [MISS] 'All Mappings' sheet missing in {latest.name}")
                total_misses += 1
                continue
            df = pd.read_excel(latest, sheet_name="All Mappings", nrows=0)
            cols_set = {str(c).strip() for c in df.columns}
            for rc in required_cols:
                if rc in cols_set:
                    print(f"  {label}: [ OK ] {rc!r}")
                else:
                    print(f"  {label}: [MISS] {rc!r}")
                    total_misses += 1
        except Exception as e:
            print(f"  {label}: ERROR — {e}")
            total_misses += 1

    print()
    print("=" * 60)
    if total_misses == 0:
        print("All input columns aligned with YAML configuration.")
        return 0
    else:
        print(f"Found {total_misses} column-name mismatch(es). Update YAML or "
              f"input file headers to fix.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
