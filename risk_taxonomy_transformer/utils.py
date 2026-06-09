"""
Shared utility functions for the Risk Taxonomy Transformer.

Provides file I/O helpers and formatting functions used by multiple modules.
"""

from __future__ import annotations

import platform
import re
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd


# ---------------------------------------------------------------------------
# Shared parsing helpers
# ---------------------------------------------------------------------------

def split_id_list(raw) -> list[str]:
    """Split a multi-value ID cell (e.g. the legacy 'IRM ORE' or 'All PRSAs
    Tagged to AE' columns, or app/third-party ID lists) into individual IDs.
    Handles newline, semicolon, and comma separators (mixed ok); strips; drops
    blanks and nan/none. Do NOT use for category-name lists (L2/L1), whose
    names contain literal commas."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return []
    s = str(raw).strip()
    if not s or s.lower() in ("nan", "none"):
        return []
    out = []
    for part in re.split(r"[;\n\r,]+", s):
        p = part.strip()
        if p and p.lower() not in ("nan", "none"):
            out.append(p)
    return out


# ---------------------------------------------------------------------------
# Run provenance
# ---------------------------------------------------------------------------

def _git_commit_short() -> str:
    """Return the short HEAD commit hash, or 'unknown' if git is unavailable."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent,
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _package_version(name: str) -> str:
    """Return an installed package's version, or 'unknown' if not resolvable."""
    try:
        from importlib.metadata import version, PackageNotFoundError
        try:
            return version(name)
        except PackageNotFoundError:
            return "unknown"
    except ImportError:
        return "unknown"


def get_run_provenance(spacy_model: str | None = None) -> dict:
    """Return a run-provenance dict for logging and output stamping.

    Keys: tool_commit, run_timestamp, spacy_model, spacy_model_version,
    and versions for python/pandas/openpyxl/pyyaml/spacy. When spacy_model
    is given, its installed package version is resolved via spaCy.
    """
    spacy_model_version = "unknown"
    if spacy_model:
        try:
            import spacy
            spacy_model_version = spacy.util.get_package_version(spacy_model) or "unknown"
        except Exception:
            spacy_model_version = "unknown"

    return {
        "tool_commit": _git_commit_short(),
        "run_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "spacy_model": spacy_model or "n/a",
        "spacy_model_version": spacy_model_version,
        "python_version": platform.python_version(),
        "pandas_version": _package_version("pandas"),
        "openpyxl_version": _package_version("openpyxl"),
        "pyyaml_version": _package_version("PyYAML"),
        "spacy_version": _package_version("spacy"),
    }


def format_provenance_lines(prov: dict) -> list[str]:
    """Render a provenance dict as concise 'key: value' display lines."""
    return [
        f"Tool commit: {prov['tool_commit']}",
        f"Run timestamp: {prov['run_timestamp']}",
        f"spaCy model: {prov['spacy_model']} ({prov['spacy_model_version']})",
        f"Python {prov['python_version']} · pandas {prov['pandas_version']} · "
        f"openpyxl {prov['openpyxl_version']} · PyYAML {prov['pyyaml_version']} · "
        f"spaCy {prov['spacy_version']}",
    ]


def spacy_model_label(nlp) -> str:
    """Return 'name version' from a loaded spaCy model's meta block."""
    try:
        meta = nlp.meta
        return f"{meta.get('lang', '')}_{meta.get('name', '')} {meta.get('version', '')}".strip()
    except (AttributeError, KeyError):
        return "unknown"


def log_run_provenance(logger, spacy_model: str | None = None) -> dict:
    """Log the provenance block at run start and return the dict."""
    prov = get_run_provenance(spacy_model)
    logger.info("Run provenance:")
    for line in format_provenance_lines(prov):
        logger.info(f"  {line}")
    return prov


# ---------------------------------------------------------------------------
# Tabular file reader
# ---------------------------------------------------------------------------

def read_tabular_file(filepath: str, **kwargs) -> pd.DataFrame:
    """Read a CSV or Excel file into a DataFrame with normalised column names.

    Raises FileNotFoundError, PermissionError, or pd.errors.EmptyDataError
    with a clear message when the underlying read fails.
    """
    try:
        if str(filepath).endswith(".csv"):
            df = pd.read_csv(filepath, **kwargs)
        else:
            df = pd.read_excel(filepath, **kwargs)
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {filepath}")
    except PermissionError:
        raise PermissionError(f"Permission denied when reading: {filepath}")
    except pd.errors.EmptyDataError:
        raise pd.errors.EmptyDataError(f"File is empty or has no parseable data: {filepath}")

    # Normalise column names: strip leading/trailing whitespace
    df.columns = [str(c).strip() for c in df.columns]
    return df


# ---------------------------------------------------------------------------
# Date formatting
# ---------------------------------------------------------------------------

def _format_date_month_year(raw_date) -> str | None:
    """Parse a date value and return 'Month YYYY' string, or None if unparseable."""
    if not raw_date or str(raw_date).strip().lower() in ("", "nan", "none", "nat"):
        return None
    try:
        dt = pd.to_datetime(raw_date)
        if pd.isna(dt):
            return None
        return dt.strftime("%B %Y")
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Item listing formatter
# ---------------------------------------------------------------------------

def _format_item_listings(
    items: list[dict],
    source_name: str,
    id_key: str = "issue_id",
    title_key: str = "issue_title",
    severity_key: str | None = "severity",
    status_key: str | None = "status",
    band_key: str | None = None,
    max_items: int = 5,
) -> str:
    """Format individual item listings with IDs for traceability.

    Returns e.g. 'Finding F-2024-089: Dual-control bypass (High, Open) \u00b7 Finding F-2023-412: ...'
    or 'No audit findings'.

    band_key: dict key for the mapper confidence band (e.g., "mapping_status").
        When set, the band is appended to the detail parens ONLY when the value
        is "Needs Review" \u2014 Suggested Match is the default-confidence case and
        not labeled to reduce noise.
    """
    if not items:
        return f"No {source_name}"

    parts = []
    for item in items[:max_items]:
        item_id = str(item.get(id_key, "")).strip()
        title_raw = str(item.get(title_key, "")).strip()
        title = title_raw[:80] + ("..." if len(title_raw) > 80 else "") if title_raw and title_raw.lower() not in ("nan", "none", "") else ""

        # Build the label: "ID: Title (Severity, Status)"
        label = item_id
        if title:
            label = f"{item_id}: {title}"

        # Add severity/status in parentheses if available
        detail_parts = []
        if severity_key:
            sev = str(item.get(severity_key, "")).strip()
            if sev and sev.lower() not in ("", "nan", "none"):
                detail_parts.append(sev)
        if status_key:
            status = str(item.get(status_key, "")).strip()
            if status and status.lower() not in ("", "nan", "none"):
                detail_parts.append(status)
        if band_key:
            band = str(item.get(band_key, "")).strip()
            if band.lower() == "needs review":
                detail_parts.append("Needs Review")
        if detail_parts:
            label = f"{label} ({', '.join(detail_parts)})"

        parts.append(label)

    remaining = len(items) - max_items
    if remaining > 0:
        parts.append(f"(+{remaining} more)")

    return " \u00b7 ".join(parts)


# ---------------------------------------------------------------------------
# Impact-of-issues summary line
# ---------------------------------------------------------------------------

# Severity ordering for display (most severe first)
_SEVERITY_ORDER = ["critical", "high", "medium", "low"]
_ORE_CLASS_ORDER = ["class a", "class b", "class c"]

# Source type display names and ordering
_SOURCE_DISPLAY = {
    "audit findings": "IAG issues",
    "OREs": "OREs",
    "enterprise findings": "regulatory findings",
    "regulatory findings": "regulatory findings",
    "PRSA issues": "PRSA issues",
    "BMA cases": "BMA cases",
}

# Singular forms for count == 1
_SOURCE_SINGULAR = {
    "IAG issues": "IAG issue",
    "OREs": "ORE",
    "regulatory findings": "regulatory finding",
    "PRSA issues": "PRSA issue",
    "BMA cases": "BMA case",
}


def _build_impact_summary(
    source_items: list[tuple[str, list[dict], str | None]],
) -> str | None:
    """Build a one-line summary of open items grouped by source type.

    Args:
        source_items: list of (source_name, items, severity_key) tuples.
            source_name matches the names used in _format_item_listings
            (e.g. "audit findings", "OREs", "enterprise findings").
            severity_key is the dict key for severity/classification.

    Returns:
        Summary string like "Open items: 3 IAG issues (1 Critical, 2 High) · 1 Class B ORE"
        or None if there are no items at all.
    """
    segments = []

    for source_name, items, severity_key in source_items:
        if not items:
            continue

        display_name = _SOURCE_DISPLAY.get(source_name, source_name)
        singular_name = _SOURCE_SINGULAR.get(display_name, display_name)
        total = len(items)
        is_ore = source_name == "OREs"

        # Count by severity/classification
        counts: dict[str, int] = {}
        if severity_key:
            for item in items:
                sev = str(item.get(severity_key, "")).strip()
                if sev and sev.lower() not in ("", "nan", "none"):
                    counts[sev] = counts.get(sev, 0) + 1

        # Determine ordering for display
        order = _ORE_CLASS_ORDER if is_ore else _SEVERITY_ORDER

        # Sort severities by defined order (unknown severities go last)
        sorted_sevs = sorted(
            counts.keys(),
            key=lambda s: order.index(s.lower()) if s.lower() in order else len(order),
        )

        distinct_sevs = len(sorted_sevs)
        name = singular_name if total == 1 else display_name

        if distinct_sevs == 0:
            # No severity info available — just show count
            segments.append(f"{total} {name}")
        elif distinct_sevs == 1:
            # Single severity — flat format: "2 High IAG issues"
            sev_label = sorted_sevs[0]
            segments.append(f"{total} {sev_label} {name}")
        else:
            # Multiple severities — breakdown: "3 IAG issues (1 Critical, 2 High)"
            breakdown = ", ".join(
                f"{counts[s]} {s}" for s in sorted_sevs
            )
            segments.append(f"{total} {name} ({breakdown})")

    if not segments:
        return None

    return "Open items: " + " \u00b7 ".join(segments)
