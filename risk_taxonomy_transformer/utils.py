"""
Shared utility functions for the Risk Taxonomy Transformer.

Provides file I/O helpers and formatting functions used by multiple modules.
"""

from __future__ import annotations

import pandas as pd


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
