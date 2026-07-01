"""
Consolidate RCO Rating Responses
=================================
Reads ChatGPT response.json files from rco_rating_prompts/<l2>/ batch folders,
validates each response, merges with LUminate suggested status, and writes a
single Excel summary sorted by rating severity.

Output: data/output/rco_ratings_<l2_slug>_<timestamp>.xlsx

One sheet — "Ratings" — with:
  Entity ID | Entity Name | Proposed Rating | Rating Rationale | LUminate Status

Rating column is color-coded (Critical=red, High=orange, Medium=yellow, Low=green).
A summary block at the top shows counts by rating.

Usage:
    python consolidate_rco_ratings.py --l2 Conduct
    python consolidate_rco_ratings.py --l2 "Internal Fraud"
    python consolidate_rco_ratings.py --l2 Conduct --dry-run   # validate only
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

from risk_taxonomy_transformer.utils import latest_input

_PROJECT_ROOT = Path(__file__).parent
_PROMPTS_ROOT = _PROJECT_ROOT / "data" / "output" / "rco_rating_prompts"
_OUT_DIR = _PROJECT_ROOT / "data" / "output"

VALID_RATINGS = ["Critical", "High", "Medium", "Low"]
RATING_ORDER = {r: i for i, r in enumerate(VALID_RATINGS)}

# openpyxl fill colors per rating
_FILLS = {
    "Critical": PatternFill("solid", fgColor="FF4C4C"),  # red
    "High":     PatternFill("solid", fgColor="FF944C"),  # orange
    "Medium":   PatternFill("solid", fgColor="FFD966"),  # yellow
    "Low":      PatternFill("solid", fgColor="92D050"),  # green
}
_HEADER_FILL = PatternFill("solid", fgColor="1F4E79")    # dark blue
_SUMMARY_FILL = PatternFill("solid", fgColor="D6E4F0")   # light blue
_THIN = Border(
    left=Side(style="thin"), right=Side(style="thin"),
    top=Side(style="thin"), bottom=Side(style="thin"),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slug(l2_name: str) -> str:
    return l2_name.lower().replace(" ", "_").replace("/", "_")


def _try_parse(text: str) -> tuple[list | None, str | None]:
    text = text.strip()
    if not text:
        return None, "response.json is empty"
    fence = re.match(r"^```(?:json)?\s*\n(.*)\n```\s*$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        first, last = text.find("["), text.rfind("]")
        if first != -1 and last > first:
            try:
                data = json.loads(text[first:last + 1])
            except json.JSONDecodeError:
                return None, f"JSON parse error: {e}"
        else:
            return None, f"JSON parse error: {e}"
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return None, f"expected JSON array, got {type(data).__name__}"
    return data, None


def _load_luminate_status(l2_name: str) -> dict[str, str]:
    """Return {entity_id: suggested_status} for the given L2 from latest output."""
    latest = latest_input(
        _PROJECT_ROOT / "data" / "output",
        ["transformed_risk_taxonomy_*.xlsx"],
        log_label="transformer output",
    )
    if latest is None:
        return {}
    try:
        df = pd.read_excel(latest, sheet_name="Audit_Review")
        subset = df[df["New L2"] == l2_name][["Entity ID", "Suggested Status"]].copy()
        return dict(zip(subset["Entity ID"].astype(str), subset["Suggested Status"].astype(str)))
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Core consolidation
# ---------------------------------------------------------------------------

def consolidate(l2_name: str, dry_run: bool = False) -> int:
    """Consolidate responses for one L2. Returns exit code (0 = ok, 1 = errors)."""
    slug = _slug(l2_name)
    prompt_dir = _PROMPTS_ROOT / slug

    if not prompt_dir.exists():
        print(f'  No prompt folder found at {prompt_dir}')
        print(f'  Run: python export_rco_rating_prompts.py --l2 "{l2_name}" first.')
        return 1

    batch_dirs = sorted(d for d in prompt_dir.iterdir()
                        if d.is_dir() and d.name.startswith("batch_"))
    if not batch_dirs:
        print(f"  No batch_NNN/ folders in {prompt_dir}")
        return 1

    print(f'  Found {len(batch_dirs)} batch folder(s)')

    all_rows: list[dict] = []
    errors: list[str] = []
    warnings: list[str] = []

    for batch_dir in batch_dirs:
        rfile = batch_dir / "response.json"
        mfile = batch_dir / "manifest.json"

        # Load manifest for entity list
        expected_entities: list[str] = []
        if mfile.exists():
            try:
                manifest = json.loads(mfile.read_text(encoding="utf-8"))
                expected_entities = manifest.get("entities", [])
            except Exception as e:
                warnings.append(f"{batch_dir.name}: manifest load error — {e}")

        # Load response
        if not rfile.exists():
            errors.append(f"{batch_dir.name}: response.json missing")
            continue

        text = rfile.read_text(encoding="utf-8")
        data, err = _try_parse(text)
        if err:
            errors.append(f"{batch_dir.name}: {err}")
            continue
        if not data:
            warnings.append(f"{batch_dir.name}: response.json is empty — no output pasted yet")
            continue

        # Validate rows
        batch_entity_ids: list[str] = []
        for idx, item in enumerate(data):
            if not isinstance(item, dict):
                errors.append(f"{batch_dir.name} item {idx}: expected object")
                continue
            missing = [k for k in ("entity_id", "entity_name", "proposed_rating", "rating_rationale")
                       if k not in item]
            if missing:
                errors.append(f"{batch_dir.name} item {idx}: missing fields {missing}")
                continue
            rating = str(item["proposed_rating"]).strip()
            if rating not in VALID_RATINGS:
                errors.append(
                    f"{batch_dir.name} item {idx} ({item.get('entity_id', '?')}): "
                    f"invalid rating '{rating}' — must be one of {VALID_RATINGS}"
                )
                continue
            row = {
                "entity_id":       str(item["entity_id"]).strip(),
                "entity_name":     str(item["entity_name"]).strip(),
                "proposed_rating": rating,
                "rating_rationale": str(item["rating_rationale"]).strip(),
            }
            all_rows.append(row)
            batch_entity_ids.append(row["entity_id"])

        # Coverage check
        if expected_entities:
            responded = set(batch_entity_ids)
            missing_ae = set(expected_entities) - responded
            if missing_ae:
                warnings.append(
                    f"{batch_dir.name}: response missing {len(missing_ae)} "
                    f"expected entity ID(s): {sorted(missing_ae)}"
                )

        print(f"    {batch_dir.name}: {len(batch_entity_ids)} valid row(s)")

    # Summary
    print()
    if errors:
        for e in errors:
            print(f"  [error] {e}")
    if warnings:
        for w in warnings:
            print(f"  [warn]  {w}")

    if not all_rows:
        print("  No valid rows to consolidate.")
        return 1 if errors else 0

    # Deduplicate — last response wins if an entity appears in multiple batches
    seen: dict[str, dict] = {}
    for row in all_rows:
        seen[row["entity_id"]] = row
    rows = list(seen.values())

    # Sort by rating severity
    rows.sort(key=lambda r: RATING_ORDER.get(r["proposed_rating"], 99))

    # Attach LUminate status
    luminate_status = _load_luminate_status(l2_name)
    for row in rows:
        row["luminate_status"] = luminate_status.get(row["entity_id"], "—")

    print(f"  Total valid entities: {len(rows)}")
    counts = {r: sum(1 for row in rows if row["proposed_rating"] == r) for r in VALID_RATINGS}
    for rating in VALID_RATINGS:
        if counts[rating]:
            print(f"    {rating}: {counts[rating]}")

    if dry_run:
        print()
        print("  --dry-run: no file written.")
        return 1 if errors else 0

    # Write Excel
    ts = datetime.now().strftime("%m%d%Y%I%M%p")
    out_path = _OUT_DIR / f"rco_ratings_{slug}_{ts}.xlsx"
    _write_excel(out_path, l2_name, rows, counts)
    print()
    print(f"  Written: {out_path.name}")
    return 1 if errors else 0


def _write_excel(path: Path, l2_name: str, rows: list[dict], counts: dict[str, int]):
    wb = Workbook()
    ws = wb.active
    ws.title = "Ratings"

    # Column widths
    col_widths = [12, 30, 16, 80, 28]
    for i, w in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    row_num = 1

    # Title row
    ws.merge_cells(f"A{row_num}:E{row_num}")
    title_cell = ws.cell(row_num, 1,
                         value=f"{l2_name} — RCO Proposed Ratings  |  "
                               f"Generated {datetime.now().strftime('%Y-%m-%d')}")
    title_cell.font = Font(bold=True, color="FFFFFF", size=12)
    title_cell.fill = _HEADER_FILL
    title_cell.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[row_num].height = 22
    row_num += 1

    # Summary row
    ws.merge_cells(f"A{row_num}:E{row_num}")
    summary_parts = [f"{r}: {counts[r]}" for r in VALID_RATINGS if counts[r]]
    summary_cell = ws.cell(row_num, 1,
                           value="  |  ".join(summary_parts) +
                                 f"  |  Total: {sum(counts.values())}")
    summary_cell.font = Font(bold=True, size=10)
    summary_cell.fill = _SUMMARY_FILL
    summary_cell.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[row_num].height = 18
    row_num += 1

    # Blank separator
    row_num += 1

    # Header row
    headers = ["Entity ID", "Entity Name", "Proposed Rating", "Rating Rationale", "LUminate Status"]
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row_num, col, value=header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _THIN
    ws.row_dimensions[row_num].height = 20
    row_num += 1

    # Data rows
    for row in rows:
        rating = row["proposed_rating"]
        fill = _FILLS.get(rating, PatternFill())
        values = [
            row["entity_id"],
            row["entity_name"],
            rating,
            row["rating_rationale"],
            row["luminate_status"],
        ]
        for col, val in enumerate(values, start=1):
            cell = ws.cell(row_num, col, value=val)
            cell.border = _THIN
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if col == 3:  # Rating column only gets color
                cell.fill = fill
                cell.font = Font(bold=True)
                cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[row_num].height = 40
        row_num += 1

    # Freeze panes below header
    ws.freeze_panes = f"A{5}"  # row 4 is header, freeze below it

    wb.save(path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Consolidate RCO rating responses into a single Excel summary"
    )
    parser.add_argument(
        "--l2",
        required=True,
        help='L2 name, e.g. "Conduct" or "Internal Fraud"',
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Validate responses and print summary without writing the Excel file",
    )
    ns = parser.parse_args()

    print(f'Consolidating RCO ratings for "{ns.l2}"...')
    rc = consolidate(ns.l2, dry_run=ns.dry_run)
    sys.exit(rc)
