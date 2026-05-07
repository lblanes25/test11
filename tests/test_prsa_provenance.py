"""Smoke test for Track B PRSA L2 provenance plumbing.

Loads the test-dummy Frankenstein and asserts that ingest_prsa stamps the
correct L2 Provenance value on each row, that an invalid Risk Level 2 logs
a WARNING and falls back to mapper provenance, and that the source-tagged
canonical L2 lands in `Risk Level 2 Normalized` for valid rows.

Run after regenerating fixtures:
    python tests/generate_prsa_source_test_data.py
    python build_prsa_frankenstein.py --test-dummy
    python tests/test_prsa_provenance.py
"""

from __future__ import annotations

import logging
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

import sys
sys.path.insert(0, str(_PROJECT_ROOT))

from risk_taxonomy_transformer.config import get_config
from risk_taxonomy_transformer.ingestion import ingest_prsa


def _expected_provenance() -> dict[str, str]:
    """Per ISSUES list in tests/generate_prsa_source_test_data.py."""
    return {
        "ISS-001": "source",   # "Financial Crimes" -> valid (alias -> 'Financial crimes')
        "ISS-002": "source",   # "Processing, Execution and Change" -> valid
        "ISS-003": "source",   # "Financial Crimes" -> valid
        "ISS-004": "source",   # "Information and Cyber Security" -> valid
        # ISS-005 is RCSA-only, dropped before reaching the Frankenstein
        "ISS-006": "mapper",   # blank -> fallback
        "ISS-007": "source",   # "Prudential & bank administration compliance" -> valid
        "ISS-008": "source",   # "Data" -> valid
        "ISS-009": "source",   # "Processing, Execution and Change" -> valid
        "ISS-010": "source",   # "Third Party" -> valid
        "ISS-011": "mapper",   # "Made Up Risk Category" -> invalid, WARNING + fallback
    }


def main() -> int:
    cfg = get_config()
    prsa_cols = cfg.get("columns", {}).get("prsa", {})

    # Use the BUILT Frankenstein (output of build_prsa_frankenstein.py
    # --test-dummy) when present, falling back to the golden fixture.
    candidates = [
        _PROJECT_ROOT / "data" / "input" / "prsa_report_test_dummy_BUILT.xlsx",
        _PROJECT_ROOT / "data" / "input" / "prsa_report_test_dummy.xlsx",
    ]
    path = next((p for p in candidates if p.exists()), None)
    if path is None:
        print(f"FAIL: no test-dummy PRSA report found in {candidates[0].parent}")
        return 1

    print(f"Loading: {path}")

    # Capture WARNINGs from the ingestion logger
    warning_records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if record.levelno >= logging.WARNING:
                warning_records.append(record)

    handler = _Capture(level=logging.WARNING)
    logging.getLogger("risk_taxonomy_transformer.ingestion").addHandler(handler)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    df = ingest_prsa(str(path), prsa_cols)

    failures: list[str] = []

    # Check provenance per issue
    expected = _expected_provenance()
    issue_id_col = prsa_cols.get("issue_id", "Issue ID")
    if issue_id_col not in df.columns:
        print(f"FAIL: missing column {issue_id_col!r}")
        return 1
    if "L2 Provenance" not in df.columns:
        print("FAIL: ingest_prsa did not add 'L2 Provenance' column")
        return 1
    if "Risk Level 2 Normalized" not in df.columns:
        print("FAIL: ingest_prsa did not add 'Risk Level 2 Normalized' column")
        return 1

    by_issue: dict[str, str] = {}
    norm_by_issue: dict[str, str] = {}
    for _, row in df.iterrows():
        iid = str(row[issue_id_col]).strip()
        prov = str(row["L2 Provenance"]).strip()
        norm = str(row["Risk Level 2 Normalized"]).strip()
        # Issue may repeat across controls -- all rows must agree
        if iid in by_issue and by_issue[iid] != prov:
            failures.append(f"  {iid}: provenance disagreement across controls "
                            f"({by_issue[iid]!r} vs {prov!r})")
        by_issue[iid] = prov
        norm_by_issue[iid] = norm

    for iid, want in expected.items():
        got = by_issue.get(iid)
        if got != want:
            failures.append(f"  {iid}: expected provenance {want!r}, got {got!r}")
        # Source rows must have Risk Level 2 Normalized populated
        if want == "source" and not norm_by_issue.get(iid):
            failures.append(f"  {iid}: provenance=source but 'Risk Level 2 Normalized' is blank")
        # Mapper rows must have Risk Level 2 Normalized blank
        if want == "mapper" and norm_by_issue.get(iid):
            failures.append(f"  {iid}: provenance=mapper but 'Risk Level 2 Normalized'='"
                            f"{norm_by_issue[iid]}' (should be blank)")

    # ISS-005 must NOT appear (RCSA-only, dropped before Frankenstein)
    if "ISS-005" in by_issue:
        failures.append("  ISS-005 should not be in PRSA report (RCSA-only)")

    # Verify a WARNING was logged for the invalid case (ISS-011)
    invalid_warnings = [
        r for r in warning_records
        if "ISS-011" in r.getMessage() and "Made Up Risk Category" in r.getMessage()
    ]
    if not invalid_warnings:
        failures.append("  Expected WARNING for invalid ISS-011 'Made Up Risk Category' not found")

    print()
    print("Provenance summary:")
    for iid in sorted(expected):
        prov = by_issue.get(iid, "<missing>")
        norm = norm_by_issue.get(iid, "")
        print(f"  {iid:<8s} provenance={prov:<7s} normalized_l2={norm!r}")

    print()
    if failures:
        print(f"FAIL: {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f)
        return 1

    print("PASS: all Track B provenance assertions hold "
          f"({len(expected)} issues, {len(invalid_warnings)} invalid-warning(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
