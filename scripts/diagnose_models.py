"""Diagnose why model inventory isn't matching in the HTML export.

Mirrors the exact pipeline used by export_html_report.generate_html_report():
  1. Load model_inventory_*.xlsx
  2. Load latest legacy_risk_data_*
  3. Extract referenced model IDs from legacy
  4. Filter inventory
  5. Report what survives + spot-check the lookup

Run:  python scripts/diagnose_models.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import yaml

_ROOT = Path(__file__).resolve().parent.parent
_INPUT = _ROOT / "data" / "input"

sys.path.insert(0, str(_ROOT))
from export_html_report import (  # noqa: E402
    _collect_model_ids,
    _filter_inventory,
    _load_inventory,
    _norm_id_series,
)


def _latest(pattern: str) -> Path | None:
    matches = sorted(_INPUT.glob(pattern))
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def main() -> int:
    cfg = yaml.safe_load((_ROOT / "config" / "taxonomy_config.yaml").read_text(encoding="utf-8"))
    col_cfg = cfg.get("columns", {})
    inv_pattern = col_cfg.get("inventory_files", {}).get("models", "model_inventory_*.xlsx")
    legacy_models_col = col_cfg.get("applications", {}).get("models", "Models")
    model_id_col = col_cfg.get("model_inventory", {}).get("id", "Model ID")
    model_name_col = col_cfg.get("model_inventory", {}).get("name", "Model Name")

    print("=" * 72)
    print("MODEL INVENTORY DIAGNOSTIC")
    print("=" * 72)
    print(f"Pattern:           {inv_pattern}")
    print(f"Legacy column:     {legacy_models_col!r}")
    print(f"Inventory ID col:  {model_id_col!r}")
    print(f"Inventory name col:{model_name_col!r}")
    print()

    # 1. Inventory file
    inv_file = _latest(inv_pattern)
    if inv_file is None:
        print(f"[FAIL] No file matches pattern {inv_pattern!r} in {_INPUT}")
        return 1
    print(f"Inventory file:    {inv_file.name}")
    inv_df = _load_inventory(_INPUT, inv_pattern)
    print(f"Inventory rows:    {len(inv_df)}")
    print(f"Inventory columns: {list(inv_df.columns)}")
    if model_id_col not in inv_df.columns:
        print(f"[FAIL] Configured id column {model_id_col!r} NOT in inventory headers.")
        print(f"       Closest header tokens: "
              f"{[c for c in inv_df.columns if 'id' in c.lower() or 'model' in c.lower()]}")
        return 1
    print(f"Inventory ID dtype:    {inv_df[model_id_col].dtype}")
    print(f"Inventory ID raw head: {inv_df[model_id_col].head(8).tolist()}")
    print(f"Inventory ID normalized head: "
          f"{_norm_id_series(inv_df[model_id_col]).head(8).tolist()}")
    print()

    # 2. Legacy file
    legacy_file = _latest("legacy_risk_data_*.xlsx") or _latest("legacy_risk_data_*.csv")
    if legacy_file is None:
        print("[FAIL] No legacy_risk_data_*.xlsx file found.")
        return 1
    print(f"Legacy file:       {legacy_file.name}")
    if str(legacy_file).endswith(".csv"):
        legacy_df = pd.read_csv(legacy_file)
    else:
        legacy_df = pd.read_excel(legacy_file)
    legacy_df.columns = [str(c).strip() for c in legacy_df.columns]
    if legacy_models_col not in legacy_df.columns:
        print(f"[FAIL] Legacy column {legacy_models_col!r} NOT in legacy headers.")
        candidates = [c for c in legacy_df.columns if "model" in c.lower()]
        print(f"       Possible Models columns: {candidates}")
        return 1
    print(f"Legacy rows:       {len(legacy_df)}")
    non_blank = legacy_df[legacy_models_col].dropna()
    non_blank = non_blank[non_blank.astype(str).str.strip() != ""]
    print(f"Rows with non-blank {legacy_models_col!r}: {len(non_blank)}")
    if not non_blank.empty:
        print(f"Sample chunks (first 3):")
        for v in non_blank.head(3).tolist():
            print(f"   {v!r}")
    print()

    # 3. Collect referenced IDs
    model_ids = _collect_model_ids(legacy_df, legacy_models_col)
    print(f"Referenced model IDs (count): {len(model_ids)}")
    print(f"Referenced sample: {sorted(model_ids)[:10]}")
    print()

    # 4. Filter
    filtered = _filter_inventory(inv_df, model_id_col, model_ids, "Models inventory")
    print(f"Filtered inventory rows: {len(filtered)} (of {len(inv_df)})")
    if not filtered.empty:
        print(f"Surviving Model IDs: "
              f"{_norm_id_series(filtered[model_id_col]).tolist()[:10]}")
    print()

    # 5. Spot-check lookup: for each referenced ID, did it survive?
    surviving = set(_norm_id_series(filtered[model_id_col]).tolist()) if not filtered.empty else set()
    matched = sorted(model_ids & surviving)
    unmatched = sorted(model_ids - surviving)
    print(f"Referenced IDs that matched inventory:   {len(matched)}  e.g. {matched[:10]}")
    print(f"Referenced IDs that DID NOT match:       {len(unmatched)}  e.g. {unmatched[:10]}")
    print()
    if unmatched:
        # For each unmatched, check if it appears anywhere in the inventory
        # via substring (catches "M-1178" / "1178-US" / "01178" type prefixes).
        inv_strs = inv_df[model_id_col].astype(str).str.strip().tolist()
        for uid in unmatched[:5]:
            hits = [s for s in inv_strs if uid in s]
            if hits:
                print(f"  ID {uid!r} appears as a substring in inventory: {hits[:3]}")
            else:
                print(f"  ID {uid!r} not anywhere in inventory")
    return 0


if __name__ == "__main__":
    sys.exit(main())
