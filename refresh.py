"""
One-button refresh: runs all three mapper scripts then the main pipeline.

Usage:
    python refresh.py              # run everything
    python refresh.py --skip-mappers   # skip mappers, just run main pipeline
    python refresh.py --only ore       # run only ORE mapper, then main pipeline
    python refresh.py --only ore,prsa  # run only ORE+PRSA mappers, then main pipeline
    python refresh.py --no-main        # run mappers, skip main pipeline

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
    ("ore", "ore_mapper.py", "ORE Mapper"),
    ("prsa", "prsa_mapper.py", "PRSA Mapper"),
    ("rap", "rap_mapper.py", "RAP Mapper"),
]


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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run all mappers then the main risk taxonomy transformer pipeline."
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
        help="Comma-separated list of mappers to run (ore,prsa,rap). Others are skipped.",
    )
    parser.add_argument(
        "--no-main",
        action="store_true",
        help="Run mappers but skip the main pipeline.",
    )
    ns = parser.parse_args()

    if ns.only:
        only = {m.strip().lower() for m in ns.only.split(",") if m.strip()}
        unknown = only - {"ore", "prsa", "rap"}
        if unknown:
            print(f"ERROR: unknown mapper(s) in --only: {sorted(unknown)}")
            return 2
    else:
        only = None

    mapper_failures: list[str] = []
    if not ns.skip_mappers:
        for key, script, label in _MAPPERS:
            if only is not None and key not in only:
                print(f"\n[skip] {label} (not in --only)")
                continue
            _banner(f"Running {label}: {script}")
            rc = _run([sys.executable, script], label)
            if rc != 0:
                mapper_failures.append(label)
                print(f"WARNING: {label} failed; continuing.")

    if ns.no_main:
        _banner("Skipping main pipeline (--no-main)")
        if mapper_failures:
            print(f"Mappers that failed: {', '.join(mapper_failures)}")
        return 1 if mapper_failures else 0

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
