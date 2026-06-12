"""Tests for Track B PRSA L2 provenance plumbing.

Regenerates the PRSA source fixtures and the test-dummy Frankenstein via
subprocess (the established data/input pattern, matching
test_ore_irm_consolidate), then asserts that ingest_prsa stamps the correct
L2 Provenance value on each row, that an invalid Risk Level 2 logs a WARNING
and falls back to mapper provenance, and that the source-tagged canonical L2
lands in `Risk Level 2 Normalized` for valid rows.

Run:
    python -m pytest tests/test_prsa_provenance.py -q
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(_PROJECT_ROOT))

from risk_taxonomy_transformer.config import get_config
from risk_taxonomy_transformer.ingestion import ingest_prsa


# Per ISSUES list in tests/generate_prsa_source_test_data.py.
EXPECTED_PROVENANCE = {
    "ISS-001": "source",   # "Financial Crimes" -> valid (alias -> 'Financial crimes')
    "ISS-002": "source",   # "Processing, Execution and Change" -> valid
    "ISS-003": "source",   # "Financial Crimes" -> valid
    "ISS-004": "source",   # "Information and Cyber Security" -> valid
    # ISS-005 is RCSA-only (non-PG), dropped before reaching the Frankenstein
    "ISS-006": "mapper",   # blank -> fallback
    "ISS-007": "source",   # "Prudential & bank administration compliance" -> valid
    "ISS-008": "source",   # "Data" -> valid
    "ISS-009": "source",   # "Processing, Execution and Change" -> valid
    "ISS-010": "source",   # "Third Party" -> valid
    "ISS-011": "mapper",   # "Made Up Risk Category" -> invalid, WARNING + fallback
    # Track C: PG-flagged issues
    "ISS-012": "source",   # PG mapped, "Processing, Execution and Change" valid
    "ISS-013": "source",   # PG unmapped, "Processing, Execution and Change" valid
}


def _is_truthy(v) -> bool:
    s = str(v).strip().lower()
    return s in ("true", "yes", "1")


def _is_blank_cell(v) -> bool:
    # Excel reads back blank cells as NaN, so accept "nan" as blank.
    s = str(v).strip().lower()
    return s in ("", "nan")


@pytest.fixture(scope="module")
def prsa_ingest():
    """Regenerate fixtures, build the test-dummy Frankenstein, and ingest it.

    Returns (df, prsa_cols, warning_records).
    """
    for cmd in (
        [sys.executable, str(_PROJECT_ROOT / "tests" / "generate_prsa_source_test_data.py")],
        [sys.executable, str(_PROJECT_ROOT / "build_prsa_frankenstein.py"), "--test-dummy"],
    ):
        result = subprocess.run(cmd, cwd=str(_PROJECT_ROOT),
                                capture_output=True, text=True)
        assert result.returncode == 0, (
            f"fixture step failed ({' '.join(cmd)}):\n{result.stdout}\n{result.stderr}"
        )

    cfg = get_config()
    prsa_cols = cfg.get("columns", {}).get("prsa", {})

    # Use the BUILT Frankenstein (output of build_prsa_frankenstein.py
    # --test-dummy) when present, falling back to the golden fixture.
    candidates = [
        _PROJECT_ROOT / "data" / "input" / "prsa_report_test_dummy_BUILT.xlsx",
        _PROJECT_ROOT / "data" / "input" / "prsa_report_test_dummy.xlsx",
    ]
    path = next((p for p in candidates if p.exists()), None)
    assert path is not None, f"no test-dummy PRSA report found in {candidates[0].parent}"

    # Capture WARNINGs from the ingestion logger
    warning_records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if record.levelno >= logging.WARNING:
                warning_records.append(record)

    handler = _Capture(level=logging.WARNING)
    ingestion_logger = logging.getLogger("risk_taxonomy_transformer.ingestion")
    ingestion_logger.addHandler(handler)
    try:
        df = ingest_prsa(str(path), prsa_cols)
    finally:
        ingestion_logger.removeHandler(handler)

    return df, prsa_cols, warning_records


@pytest.fixture(scope="module")
def provenance_by_issue(prsa_ingest):
    """{issue_id: provenance} and {issue_id: normalized_l2}, with the
    cross-control consistency assertion from the original script."""
    df, prsa_cols, _ = prsa_ingest
    issue_id_col = prsa_cols.get("issue_id", "Issue ID")
    assert issue_id_col in df.columns, f"missing column {issue_id_col!r}"
    assert "L2 Provenance" in df.columns, "ingest_prsa did not add 'L2 Provenance' column"
    assert "Risk Level 2 Normalized" in df.columns, \
        "ingest_prsa did not add 'Risk Level 2 Normalized' column"

    by_issue: dict[str, str] = {}
    norm_by_issue: dict[str, str] = {}
    for _, row in df.iterrows():
        iid = str(row[issue_id_col]).strip()
        prov = str(row["L2 Provenance"]).strip()
        norm = str(row["Risk Level 2 Normalized"]).strip()
        # Issue may repeat across controls -- all rows must agree
        if iid in by_issue:
            assert by_issue[iid] == prov, (
                f"{iid}: provenance disagreement across controls "
                f"({by_issue[iid]!r} vs {prov!r})"
            )
        by_issue[iid] = prov
        norm_by_issue[iid] = norm
    return by_issue, norm_by_issue


@pytest.mark.parametrize("iid,want", sorted(EXPECTED_PROVENANCE.items()))
def test_provenance_per_issue(provenance_by_issue, iid, want):
    by_issue, norm_by_issue = provenance_by_issue
    got = by_issue.get(iid)
    assert got == want, f"{iid}: expected provenance {want!r}, got {got!r}"
    if want == "source":
        # Source rows must have Risk Level 2 Normalized populated
        assert norm_by_issue.get(iid), (
            f"{iid}: provenance=source but 'Risk Level 2 Normalized' is blank"
        )
    else:
        # Mapper rows must have Risk Level 2 Normalized blank
        assert not norm_by_issue.get(iid), (
            f"{iid}: provenance=mapper but 'Risk Level 2 Normalized'="
            f"{norm_by_issue[iid]!r} (should be blank)"
        )


def test_rcsa_only_issue_dropped(provenance_by_issue):
    """ISS-005 (RCSA-only, non-PG) must NOT appear."""
    by_issue, _ = provenance_by_issue
    assert "ISS-005" not in by_issue, \
        "ISS-005 should not be in PRSA report (RCSA-only, non-PG)"


def test_pg_unmapped_issue_present_with_pg_gap(prsa_ingest):
    """Track C: ISS-013 (PG-flagged unmapped) MUST appear with Is PG Gap truthy
    and blank AE / Control. ingest_prsa normalizes Is PG Gap to a Python
    boolean for downstream filtering, so accept True/Yes/etc. as truthy."""
    df, prsa_cols, _ = prsa_ingest
    issue_id_col = prsa_cols.get("issue_id", "Issue ID")
    assert "Is PG Gap" in df.columns, "'Is PG Gap' column missing from PRSA report"

    iss013_rows = df[df[issue_id_col].astype(str).str.strip() == "ISS-013"]
    assert not iss013_rows.empty, "ISS-013 (PG unmapped) missing from PRSA report"
    assert iss013_rows["Is PG Gap"].apply(_is_truthy).all(), (
        f"ISS-013: expected Is PG Gap truthy, got {iss013_rows['Is PG Gap'].tolist()}"
    )
    ae_id_col = prsa_cols.get("ae_id", "AE ID")
    if ae_id_col in iss013_rows.columns:
        assert iss013_rows[ae_id_col].apply(_is_blank_cell).all(), (
            f"ISS-013 (PG unmapped): expected blank AE ID, got "
            f"{iss013_rows[ae_id_col].tolist()}"
        )


def test_invalid_l2_logs_warning(prsa_ingest):
    """A WARNING must be logged for the invalid case (ISS-011)."""
    _, _, warning_records = prsa_ingest
    invalid_warnings = [
        r for r in warning_records
        if "ISS-011" in r.getMessage() and "Made Up Risk Category" in r.getMessage()
    ]
    assert invalid_warnings, \
        "Expected WARNING for invalid ISS-011 'Made Up Risk Category' not found"
