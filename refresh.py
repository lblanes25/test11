"""
One-button refresh: runs the complete pipeline end-to-end.

Phases (in order):
    1. Validate (gate)   -> python validate_inputs.py   (non-zero exit HALTS)
    2. Build PRSA report -> python build_prsa_frankenstein.py (HARD prerequisite
       for the PRSA mapper + main ingest; HALTS on failure or missing inputs)
    3. Consolidate IRM ORE -> python consolidate_ore_irm.py (only when a raw
       IRM_ORE_raw_* export is present; warn-and-continue. Runs before the
       ore_irm mapper so it reads the collapsed one-row-per-ORE file.)
    4. Mappers           -> ore, ore_irm, prsa, rap (warn-and-continue)
    5. consolidate-llm   -> optional, before main pipeline
    6. Main pipeline     -> python -m risk_taxonomy_transformer

Usage:
    python refresh.py                            # run everything
    python refresh.py --skip-validate            # skip the input-validation gate
    python refresh.py --skip-build               # reuse existing prsa_report_*.xlsx
    python refresh.py --skip-consolidate-ore-irm # reuse existing ORE_IRM_consolidated_*.xlsx
    python refresh.py --skip-mappers             # skip mappers (still validates + builds)
    python refresh.py --only ore                 # run only legacy ORE mapper
    python refresh.py --only ore_irm             # run only IRM ORE mapper
    python refresh.py --only ore,ore_irm,prsa    # run a subset
    python refresh.py --no-main                  # run earlier phases, skip main pipeline
    python refresh.py --consolidate-llm          # consolidate LLM batch responses BEFORE main pipeline

--only implies a targeted mapper re-run: it auto-skips validate + build + IRM
ORE consolidation so a single mapper can be re-run without forcing a
Frankenstein rebuild, a re-consolidation, or a validation halt. Explicit
--skip-validate / --skip-build / --skip-consolidate-ore-irm are still honored.

Mapper keys: ore, ore_irm, prsa, rap.
Mapper failures emit a warning but do not block subsequent mappers or the
main pipeline. Main pipeline failure causes a non-zero exit code.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent

_MAPPERS = [
    ("ore", "ore_mapper.py", [], "ORE Mapper (legacy)"),
    ("ore_irm", "ore_mapper.py", ["--source", "ore_irm"], "IRM ORE Mapper"),
    ("prsa", "prsa_mapper.py", [], "PRSA Mapper"),
    ("rap", "rap_mapper.py", [], "RAP Mapper"),
]
_MAPPER_KEYS = {key for key, *_ in _MAPPERS}

_INPUT_DIR = _ROOT / "data" / "input"

# build_prsa_frankenstein.py is the source of truth for its inputs; these
# mirror the patterns from its docstring for a fast pre-flight check.
_BUILD_INPUT_PATTERNS = {
    "legacy_risk_data_*": ["legacy_risk_data_*.xlsx", "legacy_risk_data_*.csv"],
    "PRSA_IRM_Archer_*": ["PRSA_IRM_Archer_*.xlsx", "PRSA_IRM_Archer_*.csv"],
    "PRSA_Controls_Map_*": ["PRSA_Controls_Map_*.xlsx", "PRSA_Controls_Map_*.csv"],
}

# Raw stacked IRM ORE export — when present, consolidate to one row per ORE ID
# before the ore_irm mapper runs.
_IRM_ORE_RAW_PATTERNS = ["IRM_ORE_raw_*.csv", "IRM_ORE_raw_*.xlsx"]


def _banner(text: str) -> None:
    print()
    print("=" * 70)
    print(text)
    print("=" * 70, flush=True)


def _run(args: list[str], label: str) -> int:
    start = time.monotonic()
    result = subprocess.run(args, cwd=str(_ROOT))
    elapsed = time.monotonic() - start
    print(f"\n{label} finished in {elapsed:.1f}s (exit code {result.returncode})", flush=True)
    return result.returncode


def _has_match(patterns):
    return any(next(_INPUT_DIR.glob(p), None) is not None for p in patterns)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the complete pipeline: validate, build PRSA report, "
                    "mappers, then the main risk taxonomy transformer pipeline."
    )
    parser.add_argument(
        "--skip-validate",
        action="store_true",
        help="Skip the input-validation gate (validate_inputs.py).",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip building the PRSA Frankenstein report; reuse the existing "
             "prsa_report_*.xlsx in data/input/.",
    )
    parser.add_argument(
        "--skip-consolidate-ore-irm",
        action="store_true",
        help="Skip the IRM ORE consolidation pre-step; reuse the existing "
             "ORE_IRM_consolidated_*.xlsx in data/input/.",
    )
    parser.add_argument(
        "--skip-mappers",
        action="store_true",
        help="Skip all mappers; run only the main pipeline.",
    )
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help="Comma-separated list of mappers to run (ore, ore_irm, prsa, rap). Others are skipped.",
    )
    parser.add_argument(
        "--no-main",
        action="store_true",
        help="Run mappers but skip the main pipeline.",
    )
    parser.add_argument(
        "--consolidate-llm",
        action="store_true",
        help="Run consolidate_llm_responses.py before the main pipeline so the "
             "freshly merged llm_overrides_<ts>.csv is picked up.",
    )
    ns = parser.parse_args()

    if ns.only:
        only = {m.strip().lower() for m in ns.only.split(",") if m.strip()}
        unknown = only - _MAPPER_KEYS
        if unknown:
            print(f"ERROR: unknown mapper(s) in --only: {sorted(unknown)}")
            return 2
    else:
        only = None

    targeted = ns.only is not None
    skip_validate = ns.skip_validate or targeted
    skip_build = ns.skip_build or targeted
    skip_consolidate_ore_irm = ns.skip_consolidate_ore_irm or targeted

    if skip_validate:
        reason = "--skip-validate" if ns.skip_validate else "--only targeted run"
        _banner(f"Skipping input-validation gate ({reason})")
    else:
        _banner("Validating inputs (gate): python validate_inputs.py")
        validate_rc = _run([sys.executable, "validate_inputs.py"], "Input validation")
        if validate_rc != 0:
            print(
                f"HALT: input validation FAILED (exit code {validate_rc}). "
                "Fix the reported inputs and re-run."
            )
            return validate_rc

    if skip_build:
        reason = "--skip-build" if ns.skip_build else "--only targeted run"
        _banner(f"Skipping PRSA Frankenstein build ({reason}); reusing existing prsa_report_*.xlsx")
    else:
        missing = [name for name, patterns in _BUILD_INPUT_PATTERNS.items()
                   if not _has_match(patterns)]
        if missing:
            _banner("PREREQUISITE INPUTS MISSING")
            print(f"Missing input group(s) for the PRSA Frankenstein build: {missing}")
            print(
                "The Frankenstein build is a prerequisite for the PRSA mapper and "
                "the main pipeline's PRSA ingest. Stage the missing inputs, or pass "
                "--skip-build to reuse the existing prsa_report_*.xlsx."
            )
            return 2
        _banner("Building PRSA Frankenstein report: python build_prsa_frankenstein.py")
        build_rc = _run([sys.executable, "build_prsa_frankenstein.py"], "PRSA Frankenstein build")
        if build_rc != 0:
            print(
                f"HALT: PRSA Frankenstein build FAILED (exit code {build_rc}). "
                "The PRSA mapper and main ingest would read stale input; aborting."
            )
            return build_rc

    ore_irm_in_scope = not ns.skip_mappers and (only is None or "ore_irm" in only)
    if ore_irm_in_scope and skip_consolidate_ore_irm:
        reason = "--skip-consolidate-ore-irm" if ns.skip_consolidate_ore_irm else "--only targeted run"
        _banner(f"Skipping IRM ORE consolidation ({reason}); reusing existing ORE_IRM_consolidated_*.xlsx")
    elif ore_irm_in_scope and _has_match(_IRM_ORE_RAW_PATTERNS):
        _banner("Consolidating raw IRM ORE export: python consolidate_ore_irm.py")
        consolidate_rc = _run([sys.executable, "consolidate_ore_irm.py"], "IRM ORE consolidation")
        if consolidate_rc != 0:
            print(f"WARNING: IRM ORE consolidation exit code {consolidate_rc}; "
                  "continuing (ore_irm mapper reads existing ORE_IRM_*).")

    mapper_failures: list[str] = []
    if not ns.skip_mappers:
        for key, script, extra_args, label in _MAPPERS:
            if only is not None and key not in only:
                print(f"\n[skip] {label} (not in --only)")
                continue
            cmd_display = " ".join([script, *extra_args]) if extra_args else script
            _banner(f"Running {label}: {cmd_display}")
            rc = _run([sys.executable, script, *extra_args], label)
            if rc != 0:
                mapper_failures.append(label)
                print(f"WARNING: {label} failed; continuing.")

    if ns.no_main:
        _banner("Skipping main pipeline (--no-main)")
        if mapper_failures:
            print(f"Mappers that failed: {', '.join(mapper_failures)}")
        return 1 if mapper_failures else 0

    if ns.consolidate_llm:
        _banner("Consolidating LLM batch responses: consolidate_llm_responses.py")
        consolidate_rc = _run(
            [sys.executable, "consolidate_llm_responses.py"],
            "LLM consolidator",
        )
        if consolidate_rc != 0:
            print(f"WARNING: LLM consolidator exit code {consolidate_rc}; continuing.")

    _banner("Running main pipeline: python -m risk_taxonomy_transformer")
    rc = _run([sys.executable, "-m", "risk_taxonomy_transformer"], "Main pipeline")

    print()
    if mapper_failures:
        print(f"Mappers that failed earlier: {', '.join(mapper_failures)}")
    if rc != 0:
        print(f"Main pipeline FAILED (exit code {rc}).")
    else:
        print("Refresh complete.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
