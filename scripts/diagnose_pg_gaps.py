"""One-shot diagnostic: why does no PG gap attribute to an AE?

Throwaway. Reuses the pipeline's own ingestion functions so its counts equal a
real refresh run; it never re-implements gate logic.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root for package import

from risk_taxonomy_transformer.config import get_config
from risk_taxonomy_transformer.ingestion import (
    build_pg_gap_index,
    build_prsa_mapping_index,
    ingest_prsa,
    ingest_prsa_mappings,
)

NORM_L2_COL = "Risk Level 2 Normalized"  # derived literal, hardcoded at ingestion.py:1223
_PG_STRINGS = ("yes", "true", "1")
_BLANK_LOWER = {"nan", "none"}


def _is_blank(v) -> bool:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return True
    s = str(v).strip()
    return s == "" or s.lower() in _BLANK_LOWER


def _latest(paths) -> Path | None:
    paths = list(paths)
    if not paths:
        return None
    return sorted(paths, key=lambda f: f.stat().st_mtime)[-1]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Diagnose why no PG gap attributes to an AE (read-only).")
    ap.add_argument("--input-dir", default="data/input")
    ap.add_argument("--output-dir", default="data/output")
    args = ap.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    cfg = get_config()
    col_cfg = cfg.get("columns", {})
    prsa_cols = col_cfg.get("prsa", {})

    is_pg_col = prsa_cols.get("is_pg_gap", "Is PG Gap")
    ae_id_col = prsa_cols.get("ae_id", "AE ID")
    control_id_col = prsa_cols.get("control_id_prsa", "Control ID (PRSA)")
    issue_id_col = prsa_cols.get("issue_id", "Issue ID")

    prsa_report = _latest(
        [f for f in input_dir.glob("prsa_report_*.xlsx") if "_orphans" not in f.stem]
        + [f for f in input_dir.glob("prsa_report_*.csv") if "_orphans" not in f.stem]
    )
    prsa_mapping = _latest(
        f for f in output_dir.glob("prsa_mapping_*.xlsx")
        if "_orphans" not in f.stem
    )

    print("=" * 72)
    print("PG GAP ATTRIBUTION DIAGNOSTIC")
    print("=" * 72)

    # 1. Inputs
    print("\n1. INPUTS")
    if prsa_report is None:
        print(f"   prsa_report : NOT FOUND under {input_dir.resolve()}")
        print("   Cannot run without a PRSA report file. Exiting.")
        return 2
    print(f"   prsa_report : {prsa_report.resolve()}")
    print(f"   prsa_mapping: {prsa_mapping.resolve() if prsa_mapping else 'not found'}")
    print("   prsa_cols resolved headers:")
    print(f"     is_pg_gap        = {is_pg_col!r}")
    print(f"     ae_id            = {ae_id_col!r}")
    print(f"     control_id_prsa  = {control_id_col!r}")
    print(f"     issue_id         = {issue_id_col!r}")

    prsa_df = ingest_prsa(str(prsa_report), prsa_cols)

    # 2. Gate 0 — column presence
    print("\n2. GATE 0 — COLUMN PRESENCE")
    pg_col_present = is_pg_col in prsa_df.columns
    print(f"   prsa_df rows: {len(prsa_df)}")
    print(f"   {is_pg_col!r} in prsa_df.columns: {pg_col_present}")
    if not pg_col_present:
        print("   >> is_pg_gap header absent; build_pg_gap_index returns {} "
              "at ingestion.py:1225-1226")

    # 3. PG flag count, two interpretations
    print("\n3. PG FLAG COUNT — TWO INTERPRETATIONS")
    raw_bool_count = 0
    string_form_count = 0
    if pg_col_present:
        for _, row in prsa_df.iterrows():
            if bool(row.get(is_pg_col, False)):
                raw_bool_count += 1
            if str(row.get(is_pg_col, "")).strip().lower() in _PG_STRINGS:
                string_form_count += 1
    print(f"   raw_bool    (ingestion.py:1234)      : {raw_bool_count}")
    print(f"   string_form (prsa_mapper.py interp.) : {string_form_count}")
    truthiness_mismatch = raw_bool_count != string_form_count
    if truthiness_mismatch:
        print(">> FINDING: PG-flag truthiness mismatch "
              "(ingestion.py:1234 vs prsa_mapper.py)")

    # 4. Three-gate funnel over raw_bool PG rows
    print("\n4. THREE-GATE FUNNEL (over raw_bool PG-flagged rows)")
    pg_rows = (
        [r for _, r in prsa_df.iterrows() if bool(r.get(is_pg_col, False))]
        if pg_col_present else []
    )
    n_pg = len(pg_rows)
    n_pg_ae = sum(1 for r in pg_rows if not _is_blank(r.get(ae_id_col, "")))
    n_pg_ae_l2 = sum(
        1 for r in pg_rows
        if not _is_blank(r.get(ae_id_col, ""))
        and not _is_blank(r.get(NORM_L2_COL, ""))
    )
    n_pg_control = sum(
        1 for r in pg_rows if not _is_blank(r.get(control_id_col, ""))
    )
    print(f"   PG-flagged rows                         : {n_pg}")
    print(f"     + non-blank {ae_id_col!r:<22}: {n_pg_ae}")
    print(f"       + non-blank {NORM_L2_COL!r:<22}: {n_pg_ae_l2}")
    print(f"   (separately) non-blank {control_id_col!r:<22}: {n_pg_control}")

    # 5. Real result — the actual pipeline function
    print("\n5. REAL RESULT — build_pg_gap_index()")
    pg_index = build_pg_gap_index(prsa_df, prsa_cols)
    pg_entities = len(pg_index)
    pg_pills = sum(
        len(items) for by_l2 in pg_index.values() for items in by_l2.values()
    )
    print(f"   entities (mirrors 'PG gap index built: N entities'): {pg_entities}")
    print(f"   total PG gap pill entries                          : {pg_pills}")

    # 6. Discriminator — standard PRSA mapping path
    print("\n6. DISCRIMINATOR — standard PRSA mapping index")
    section6_ran = False
    std_entities = None
    if prsa_mapping is None:
        print("   prsa_mapping file not found — section skipped.")
    else:
        conf = cfg.get("prsa_confidence_filter", ["Suggested Match"])
        prsa_mapping_df, _unmapped = ingest_prsa_mappings(
            str(prsa_mapping), confidence_filter=conf)
        std_index = build_prsa_mapping_index(prsa_mapping_df)
        std_entities = len(std_index)
        std_items = sum(
            len(v) for by_l2 in std_index.values() for v in by_l2.values()
        )
        section6_ran = True
        print(f"   confidence_filter : {conf}")
        print(f"   entities          : {std_entities}")
        print(f"   total items       : {std_items}")

    # 7. Verdict — most-specific root cause wins.
    # Order: header-presence and truthiness defects first (either would also
    # zero the control count and falsely look "expected by design"); then the
    # zero-PG and expected-by-design checks; then the L2-blank defect; then the
    # shared-path defect; otherwise inconclusive.
    print("\n7. VERDICT")
    if not pg_col_present:
        verdict = "DEFECT: is_pg_gap header mismatch"
        action = ("align config/taxonomy_config.yaml:198 to the real header "
                  f"(resolved {is_pg_col!r}, not in prsa_df)")
    elif truthiness_mismatch:
        verdict = "DEFECT: PG-flag truthiness inconsistency"
        action = "reconcile ingestion.py:1234 / prsa_mapper.py"
    elif raw_bool_count == 0:
        verdict = "EXPECTED: no PG-flagged issues present"
        action = ("upstream Archer / case-sensitive #PG prefix review")
    elif n_pg_control == 0:
        verdict = ("EXPECTED BY DESIGN (methodology.yaml:82): no PG issue "
                   "carries a PRSA control")
        action = "add controls in IRM Archer; not a tool change"
    elif n_pg_ae > 0 and n_pg_ae_l2 == 0:
        verdict = 'DEFECT: normalized L2 blank on PG rows'
        action = "trace Frankenstein normalized-L2 for PG rows"
    elif section6_ran and std_entities == 0:
        verdict = "DEFECT (shared path): standard PRSA also maps zero"
        action = ('check prsa ae_id key / AE-ID format parity vs legacy '
                  '"Audit Entity ID"')
    elif pg_entities > 0:
        verdict = (f"WORKING: PG gaps DO attribute ({pg_entities} entities, "
                   f"{pg_pills} pills) — code path sound. Any real-data zero is "
                   "the expected-by-design case (no PG issue carries a control).")
        action = ("re-run against the real staged prsa_report_*.xlsx; the "
                  "decisive number is section 4's non-blank Control ID count")
    else:
        verdict = ("INCONCLUSIVE: PG rows reach build_pg_gap_index but index "
                   "is empty for another reason — inspect section 4/5 counts")
        action = "inspect section 4/5 counts"
    print(f"   {verdict}")
    print(f"   ACTION: {action}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
