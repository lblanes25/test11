"""
L2 risk name normalization for the Risk Taxonomy Transformer.

Shared by findings ingestion, auxiliary risk flags, and any code that needs
to resolve a free-text L2 name to the canonical taxonomy name.
"""

from __future__ import annotations

import re

from risk_taxonomy_transformer.config import L2_TO_L1, L2_ALIASES, L2_UNMAPPABLE

# L1 prefix pattern to strip (e.g., "Operational - Data" -> "Data")
_L1_PREFIX_PATTERN = (
    r"^(?:Operational and Compliance|Operational|Compliance|Strategic|Market|Credit|"
    r"Liquidity|Reputational|Reputation)\s*[-–]\s*"
)

# Aliases and unmappable-set are defined in config/taxonomy_config.yaml
# (l2_aliases / l2_unmappable). Validated at config-load time.

# Build case-insensitive lookup (aliases first, exact taxonomy names override).
_L2_LOOKUP = {str(k).lower(): v for k, v in L2_ALIASES.items()}
for _l2_name in L2_TO_L1:
    _L2_LOOKUP[_l2_name.lower()] = _l2_name

_UNMAPPABLE_LOWER = {str(v).lower() for v in L2_UNMAPPABLE}


def normalize_l2_name(raw: str) -> str | None:
    """Normalize a raw L2 risk name to the canonical taxonomy name.

    Strips L1 prefixes, resolves aliases, and returns None for unmappable values.
    """
    text = str(raw).strip()
    if not text or text.lower() in ("", "nan"):
        return None

    # Strip L1 prefix
    text = re.sub(_L1_PREFIX_PATTERN, "", text).strip()

    # Check unmappable
    if text.lower() in _UNMAPPABLE_LOWER:
        return None

    # Resolve alias or exact match
    return _L2_LOOKUP.get(text.lower())
