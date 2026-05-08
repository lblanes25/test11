"""
Validate input files for the LUminate pipeline. Two checks:

1. **Input File Manifest** — lists every expected file pattern, marks
   each found / missing, and flags whether any required file is absent.
   Catches the case where a refresh forgets a source file.

2. **Column-name alignment** — verifies YAML-configured column headers
   match the actual columns in each input file. Catches silent column
   drops (the kind that made key_thirdparties miss because the real
   header was plural).

Usage:
    python validate_inputs.py

Exit code 0 if everything is fine, 1 if any required file is missing
or any required column doesn't match.
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

# ---------------------------------------------------------------------------
# Input file manifest
# ---------------------------------------------------------------------------
# Every file pattern the pipeline (or HTML report exporter) looks for, grouped
# by category. `where` is "input" (data/input/) or "output" (data/output/, for
# mapper-produced files). `required=True` means a missing file fails the run;
# everything else is optional and logged-but-skipped at runtime.

EXPECTED_FILES: list[dict] = [
    # ---- Source files (raw inputs) ----
    {"label": "Legacy risk data", "patterns": ["legacy_risk_data_*.xlsx", "legacy_risk_data_*.csv"],
     "category": "Source", "required": True, "where": "input"},
    {"label": "Key risks", "patterns": ["key_risks_*.xlsx", "key_risks_*.csv",
                                          "sub_risk_descriptions_*.xlsx", "sub_risk_descriptions_*.csv"],
     "category": "Source", "required": False, "where": "input"},
    {"label": "Findings / Issues", "patterns": ["findings_data_*.xlsx", "findings_data_*.csv"],
     "category": "Source", "required": False, "where": "input"},
    {"label": "ORE IRM raw", "patterns": ["ORE_IRM_*.xlsx", "ORE_IRM_*.csv"],
     "category": "Source", "required": False, "where": "input"},
    {"label": "PRSA report (Frankenstein)", "patterns": ["prsa_report_*.xlsx", "prsa_report_*.csv"],
     "category": "Source", "required": False, "where": "input"},
    {"label": "BM Activities", "patterns": ["bm_activities_*.xlsx", "bm_activities_*.csv"],
     "category": "Source", "required": False, "where": "input"},
    {"label": "GRA RAPs", "patterns": ["gra_raps_*.xlsx", "gra_raps_*.csv"],
     "category": "Source", "required": False, "where": "input"},
    {"label": "L2 taxonomy reference", "patterns": ["L2_Risk_Taxonomy.xlsx"],
     "category": "Source", "required": False, "where": "input"},

    # ---- Mapper outputs (produced by ore_mapper / prsa_mapper / rap_mapper) ----
    {"label": "ORE mapping (legacy)", "patterns": ["ore_mapping_*.xlsx"],
     "category": "Mapper output", "required": False, "where": "output"},
    {"label": "ORE IRM mapping", "patterns": ["ore_irm_mapping_*.xlsx"],
     "category": "Mapper output", "required": False, "where": "output"},
    {"label": "PRSA mapping", "patterns": ["prsa_mapping_*.xlsx"],
     "category": "Mapper output", "required": False, "where": "output"},
    {"label": "RAP mapping", "patterns": ["rap_mapping_*.xlsx"],
     "category": "Mapper output", "required": False, "where": "output"},

    # ---- Overrides ----
    {"label": "LLM overrides", "patterns": ["llm_overrides*.xlsx", "llm_overrides*.csv"],
     "category": "Overrides", "required": False, "where": "input"},
    {"label": "RCO overrides", "patterns": ["rco_overrides_*.xlsx", "rco_overrides_*.csv"],
     "category": "Overrides", "required": False, "where": "input"},
    {"label": "Optro export", "patterns": ["optro_export_*.xlsx", "optro_export_*.csv"],
     "category": "Overrides", "required": False, "where": "input"},

    # ---- Inventory (HTML report only) ----
    {"label": "Applications inventory", "patterns": ["all_applications_*.xlsx"],
     "category": "Inventory", "required": False, "where": "input"},
    {"label": "Policies inventory", "patterns": ["policystandardprocedure_*.xlsx"],
     "category": "Inventory", "required": False, "where": "input"},
    {"label": "Laws / mandates inventory", "patterns": ["lawsandapplicability_*.xlsx"],
     "category": "Inventory", "required": False, "where": "input"},
    {"label": "Third parties inventory", "patterns": ["all_thirdparties_*.xlsx"],
     "category": "Inventory", "required": False, "where": "input"},
    {"label": "Models inventory", "patterns": ["model_inventory_*.xlsx"],
     "category": "Inventory", "required": False, "where": "input"},
]


def _latest(patterns: list[str], where: Path = _INPUT_DIR) -> Path | None:
    matches: list[Path] = []
    for p in patterns:
        matches.extend(where.glob(p))
    if not matches:
        return None
    return max(matches, key=lambda f: f.stat().st_mtime)


def _print_manifest() -> int:
    """Print the input file manifest. Returns # of REQUIRED files missing."""
    print("=" * 72)
    print("INPUT FILE MANIFEST")
    print("=" * 72)

    found_count = 0
    required_missing = 0
    optional_missing = 0

    by_category: dict[str, list[dict]] = {}
    for entry in EXPECTED_FILES:
        by_category.setdefault(entry["category"], []).append(entry)

    for category, entries in by_category.items():
        print(f"\n{category}:")
        for entry in entries:
            where = _INPUT_DIR if entry["where"] == "input" else _OUTPUT_DIR
            latest = _latest(entry["patterns"], where=where)
            label = entry["label"]
            req_marker = " (required)" if entry["required"] else ""
            patterns_display = " | ".join(entry["patterns"])

            if latest is not None:
                found_count += 1
                print(f"  [ FOUND   ]  {label:32s}  {latest.name}{req_marker}")
            elif entry["required"]:
                required_missing += 1
                print(f"  [ MISSING ]  {label:32s}  {patterns_display}  (REQUIRED)")
            else:
                optional_missing += 1
                print(f"  [ missing ]  {label:32s}  {patterns_display}")

    total = len(EXPECTED_FILES)
    print()
    print("-" * 72)
    print(f"Summary: {found_count}/{total} expected files present  "
          f"|  required missing: {required_missing}  "
          f"|  optional missing: {optional_missing}")
    print("-" * 72)

    if required_missing > 0:
        print(f"\n[!] {required_missing} REQUIRED file(s) missing - pipeline will fail at runtime.")
    elif optional_missing > 0:
        print(f"\n    {optional_missing} optional file(s) missing - pipeline will skip those integrations.")
    else:
        print("\n    All expected files present.")

    return required_missing


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

    # File-presence manifest first; required-missing count rolls into total_misses
    # so a missing legacy file fails the validator before column-alignment runs.
    total_misses = _print_manifest()
    print("\n" + "=" * 72)
    print("COLUMN-NAME ALIGNMENT")
    print("=" * 72)

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
    print("=" * 72)
    if total_misses == 0:
        print("All checks passed: every required file present, every column aligned.")
        return 0
    else:
        print(f"Found {total_misses} issue(s). Fix missing required file(s) and/or "
              f"update YAML or input headers to resolve column mismatch(es).")
        return 1


if __name__ == "__main__":
    sys.exit(main())
