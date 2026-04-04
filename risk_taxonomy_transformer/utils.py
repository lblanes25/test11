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
    max_items: int = 5,
) -> str:
    """Format individual item listings with IDs for traceability.

    Returns e.g. 'Finding F-2024-089: Dual-control bypass (High, Open) \u00b7 Finding F-2023-412: ...'
    or 'No audit findings'.
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
        if detail_parts:
            label = f"{label} ({', '.join(detail_parts)})"

        parts.append(label)

    remaining = len(items) - max_items
    if remaining > 0:
        parts.append(f"(+{remaining} more)")

    return " \u00b7 ".join(parts)
