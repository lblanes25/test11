"""
Value-level diff of two transformer output workbooks.

Compares every sheet present in both files cell-by-cell (raw grid, header=None,
so banner rows and headers are included). Reports per sheet: shape mismatches
and differing cells grouped by column, with samples. Exit 0 when identical,
1 when any difference is found.

Usage:
    python scripts/diff_workbooks.py BASELINE.xlsx CANDIDATE.xlsx [--max-samples N]
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd


def _norm(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)) or pd.isna(v):
        return ""
    return str(v)


def diff_sheet(name: str, a: pd.DataFrame, b: pd.DataFrame, max_samples: int) -> int:
    if a.shape != b.shape:
        print(f"  [{name}] SHAPE {a.shape} -> {b.shape}")
    rows = min(a.shape[0], b.shape[0])
    cols = min(a.shape[1], b.shape[1])
    by_col: dict[int, list[tuple[int, str, str]]] = {}
    total = 0
    for c in range(cols):
        av = a.iloc[:rows, c].map(_norm)
        bv = b.iloc[:rows, c].map(_norm)
        mask = av != bv
        n = int(mask.sum())
        if n:
            total += n
            idx = list(av.index[mask][:max_samples])
            by_col[c] = [(i, av.loc[i], bv.loc[i]) for i in idx]
    extra = abs(a.shape[0] - b.shape[0]) * cols + abs(a.shape[1] - b.shape[1]) * rows
    if not total and a.shape == b.shape:
        return 0
    # Column header label = row-0 value of that column (header row in most sheets)
    for c, samples in by_col.items():
        label = _norm(a.iloc[0, c]) or f"col{c}"
        n = sum(1 for _ in samples)
        print(f"  [{name}] column '{label}' (#{c}): "
              f"{len(samples)} sample(s) of differing cells")
        for i, va, vb in samples:
            print(f"      row {i}: {va[:90]!r} -> {vb[:90]!r}")
    print(f"  [{name}] total differing cells: {total}"
          + (f" (+{extra} cells in non-overlapping area)" if extra else ""))
    return total + extra


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("baseline")
    ap.add_argument("candidate")
    ap.add_argument("--max-samples", type=int, default=3)
    ns = ap.parse_args()

    a_book = pd.read_excel(ns.baseline, sheet_name=None, header=None)
    b_book = pd.read_excel(ns.candidate, sheet_name=None, header=None)

    a_only = set(a_book) - set(b_book)
    b_only = set(b_book) - set(a_book)
    if a_only:
        print(f"Sheets only in baseline: {sorted(a_only)}")
    if b_only:
        print(f"Sheets only in candidate: {sorted(b_only)}")

    grand = 0
    for name in [s for s in a_book if s in b_book]:
        n = diff_sheet(name, a_book[name], b_book[name], ns.max_samples)
        if n == 0:
            print(f"  [{name}] identical")
        grand += n

    print()
    if grand or a_only or b_only:
        print(f"DIFFERENT: {grand} differing cells across common sheets")
        return 1
    print("IDENTICAL")
    return 0


if __name__ == "__main__":
    sys.exit(main())
