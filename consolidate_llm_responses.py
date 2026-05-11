"""
Consolidate LLM batch responses into a single llm_overrides_<timestamp>.csv.

Walks data/output/llm_prompts/batch_NNN/ folders, parses each
response.json, validates against the batch's manifest.json, reports
malformed or missing responses, and merges all valid rows into
data/input/llm_overrides_<ts>.csv where the main pipeline picks it up
on the next run.

Usage:
    python consolidate_llm_responses.py
    python consolidate_llm_responses.py --strict   # exit non-zero on any validation error
    python consolidate_llm_responses.py --dry-run  # validate only, don't write merged file
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_BATCHES_DIR = _ROOT / "data" / "output" / "llm_prompts"
_MERGED_DIR = _ROOT / "data" / "input"

EXPECTED_COLUMNS = [
    "entity_id",
    "source_legacy_pillar",
    "classified_l2",
    "determination",
    "reasoning",
]
VALID_DETERMINATIONS = {"applicable", "not_applicable"}


class BatchReport:
    def __init__(self, batch_dir: Path):
        self.batch_dir = batch_dir
        self.name = batch_dir.name
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.rows: list[dict] = []
        self.expected_count: int | None = None

    def ok(self) -> bool:
        return not self.errors


def _load_manifest(batch_dir: Path) -> dict | None:
    mfile = batch_dir / "manifest.json"
    if not mfile.exists():
        return None
    try:
        return json.loads(mfile.read_text(encoding="utf-8"))
    except Exception as e:
        return {"_load_error": str(e)}


def _try_parse_json_array(text: str):
    """Parse text as a JSON array, with best-effort recovery for common
    LLM formatting quirks: surrounding markdown code fence, trailing prose,
    or a single object instead of an array.
    """
    text = text.strip()
    if not text:
        return None, "response.json is empty (no LLM output pasted)"

    # Strip a single ```json ... ``` or ``` ... ``` code fence if present
    fence = re.match(r"^```(?:json)?\s*\n(.*)\n```\s*$", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        # Try slicing to the outer array if there's prose around it
        first = text.find("[")
        last = text.rfind("]")
        if first != -1 and last != -1 and last > first:
            try:
                data = json.loads(text[first:last + 1])
            except json.JSONDecodeError:
                return None, f"could not parse JSON: {e}"
        else:
            return None, f"could not parse JSON: {e}"

    if isinstance(data, dict):
        # LLM returned a single object instead of an array — wrap it
        data = [data]
    if not isinstance(data, list):
        return None, f"expected JSON array (or object), got {type(data).__name__}"
    return data, None


def _read_response(batch_dir: Path, report: BatchReport) -> None:
    rfile = batch_dir / "response.json"
    if not rfile.exists():
        report.errors.append("response.json missing")
        return

    try:
        text = rfile.read_text(encoding="utf-8")
    except Exception as e:
        report.errors.append(f"could not read response.json: {e}")
        return

    data, err = _try_parse_json_array(text)
    if err:
        report.errors.append(err)
        return

    if not data:
        report.warnings.append("response.json is an empty array (no LLM output pasted)")
        return

    for idx, item in enumerate(data):
        pos = f"item {idx}"
        if not isinstance(item, dict):
            report.errors.append(f"{pos}: expected object, got {type(item).__name__}")
            continue

        missing_keys = [k for k in EXPECTED_COLUMNS if k not in item]
        if missing_keys:
            report.errors.append(f"{pos}: missing required field(s) {missing_keys}: {item}")
            continue

        cleaned = {k: ("" if item[k] is None else str(item[k]).strip())
                   for k in EXPECTED_COLUMNS}
        det = cleaned["determination"].lower()
        if det not in VALID_DETERMINATIONS:
            report.errors.append(
                f"{pos}: invalid determination '{cleaned['determination']}' "
                f"(must be one of {sorted(VALID_DETERMINATIONS)})"
            )
            continue
        cleaned["determination"] = det

        empty_required = [k for k in ("entity_id", "source_legacy_pillar", "classified_l2")
                          if not cleaned[k]]
        if empty_required:
            report.errors.append(f"{pos}: empty required field(s) {empty_required}: {item}")
            continue

        report.rows.append(cleaned)


def _check_against_manifest(report: BatchReport, manifest: dict | None) -> None:
    if not manifest or "_load_error" in (manifest or {}):
        if manifest and "_load_error" in manifest:
            report.warnings.append(f"manifest.json failed to parse: {manifest['_load_error']}")
        else:
            report.warnings.append("manifest.json missing — skipping coverage check")
        return

    # --- Entity-level coverage ---
    expected_entities = set(manifest.get("entities", []))
    actual_entities = {r["entity_id"] for r in report.rows}
    missing_ent = expected_entities - actual_entities
    extra_ent = actual_entities - expected_entities
    if missing_ent:
        report.warnings.append(
            f"manifest expected {len(expected_entities)} entities, "
            f"response missing {len(missing_ent)}: {sorted(missing_ent)}"
        )
    if extra_ent:
        report.warnings.append(
            f"response contains {len(extra_ent)} entities not in manifest: {sorted(extra_ent)}"
        )

    # --- Total count sanity ---
    expected_items_count = manifest.get("item_count")
    report.expected_count = expected_items_count
    if expected_items_count is not None and len(report.rows) < expected_items_count:
        report.warnings.append(
            f"manifest expected {expected_items_count} items, response has {len(report.rows)}"
        )

    # --- Per-entity count check ---
    expected_per_entity = manifest.get("items_per_entity", {})
    if expected_per_entity:
        actual_per_entity = Counter(r["entity_id"] for r in report.rows)
        for eid, expected_n in expected_per_entity.items():
            actual_n = actual_per_entity.get(eid, 0)
            if actual_n < expected_n:
                report.warnings.append(
                    f"entity {eid}: manifest expected {expected_n} items, response has {actual_n}"
                )
            elif actual_n > expected_n:
                report.warnings.append(
                    f"entity {eid}: manifest expected {expected_n} items, response has {actual_n} "
                    f"(extras may indicate LLM generated rows for triples not in the prompt)"
                )

    # --- Exact triple coverage check ---
    # The manifest dumps every (entity_id, source_legacy_pillar, classified_l2)
    # triple the LLM was asked to determine. If a response has the right total
    # count but covers different triples than expected, this catches it.
    expected_triples_raw = manifest.get("expected_items", [])
    if expected_triples_raw:
        expected_triples = {
            (t["entity_id"], t["source_legacy_pillar"], t["classified_l2"])
            for t in expected_triples_raw
            if all(k in t for k in ("entity_id", "source_legacy_pillar", "classified_l2"))
        }
        actual_triples = {
            (r["entity_id"], r["source_legacy_pillar"], r["classified_l2"])
            for r in report.rows
        }
        missing_triples = expected_triples - actual_triples
        extra_triples = actual_triples - expected_triples
        if missing_triples:
            sample = sorted(missing_triples)[:5]
            more = f" (+{len(missing_triples) - 5} more)" if len(missing_triples) > 5 else ""
            report.warnings.append(
                f"missing {len(missing_triples)} expected (entity, pillar, L2) triples; "
                f"first {min(5, len(missing_triples))}: {sample}{more}"
            )
        if extra_triples:
            sample = sorted(extra_triples)[:5]
            more = f" (+{len(extra_triples) - 5} more)" if len(extra_triples) > 5 else ""
            report.warnings.append(
                f"response has {len(extra_triples)} (entity, pillar, L2) triples not in manifest; "
                f"first {min(5, len(extra_triples))}: {sample}{more}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Consolidate LLM batch responses into llm_overrides_<ts>.csv"
    )
    parser.add_argument("--strict", action="store_true",
                        help="Exit non-zero if any batch has errors")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate only; do not write merged file")
    ns = parser.parse_args()

    if not _BATCHES_DIR.exists():
        print(f"No batches directory at {_BATCHES_DIR}")
        return 1

    batch_dirs = sorted(d for d in _BATCHES_DIR.iterdir()
                        if d.is_dir() and d.name.startswith("batch_"))
    if not batch_dirs:
        print(f"No batch_NNN/ folders in {_BATCHES_DIR}")
        return 1

    print(f"Found {len(batch_dirs)} batch folders in {_BATCHES_DIR}")
    print()

    reports: list[BatchReport] = []
    for d in batch_dirs:
        report = BatchReport(d)
        manifest = _load_manifest(d)
        _read_response(d, report)
        _check_against_manifest(report, manifest)
        reports.append(report)

    # Summary
    total_rows = 0
    error_count = 0
    warning_count = 0
    for r in reports:
        status = "OK" if r.ok() else "ERROR"
        line = f"  {r.name}: {status} — {len(r.rows)} valid rows"
        if r.expected_count is not None:
            line += f" (manifest expected {r.expected_count})"
        print(line)
        for e in r.errors:
            print(f"    [error] {e}")
            error_count += 1
        for w in r.warnings:
            print(f"    [warn]  {w}")
            warning_count += 1
        total_rows += len(r.rows)

    print()
    print(f"Total valid rows across all batches: {total_rows}")
    print(f"Total errors: {error_count}")
    print(f"Total warnings: {warning_count}")

    if total_rows == 0:
        print()
        print("Nothing to merge — no valid rows in any batch.")
        return 1 if (ns.strict and error_count) else 0

    if ns.dry_run:
        print()
        print("--dry-run: skipping merged-file write.")
        return 1 if (ns.strict and error_count) else 0

    # Merge
    _MERGED_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%m%d%Y%I%M%p")
    merged_path = _MERGED_DIR / f"llm_overrides_{timestamp}.csv"
    with open(merged_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=EXPECTED_COLUMNS)
        writer.writeheader()
        for r in reports:
            for row in r.rows:
                writer.writerow(row)

    print()
    print(f"Merged file written: {merged_path}")
    print(f"Main pipeline will pick this up on next run (newest mtime in data/input/).")

    if ns.strict and error_count:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
