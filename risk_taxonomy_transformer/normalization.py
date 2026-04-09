"""
L2 risk name normalization for the Risk Taxonomy Transformer.

Shared by findings ingestion, auxiliary risk flags, and any code that needs
to resolve a free-text L2 name to the canonical taxonomy name.
"""

from __future__ import annotations

import re

from risk_taxonomy_transformer.config import L2_TO_L1

# L1 prefix pattern to strip (e.g., "Operational - Data" -> "Data")
_L1_PREFIX_PATTERN = (
    r"^(?:Operational and Compliance|Operational|Strategic|Market|Credit|"
    r"Liquidity|Reputational)\s*[-\u2013]\s*"
)

# Known name variations -> canonical L2 name
_L2_ALIASES = {
    "earning": "Earnings",
    "earnings": "Earnings",
    "infosec": "Information and Cyber Security",
    "info security": "Information and Cyber Security",
    "information security": "Information and Cyber Security",
    "cyber security": "Information and Cyber Security",
    "cybersecurity": "Information and Cyber Security",
    "info and cyber security": "Information and Cyber Security",
    "prudential & bank admin compliance": "Prudential & bank administration compliance",
    "prudential and bank administration compliance": "Prudential & bank administration compliance",
    "prudential & bank admin": "Prudential & bank administration compliance",
    "customer / client protection": "Customer / client protection and product compliance",
    "customer/client protection and product compliance": "Customer / client protection and product compliance",
    "client protection": "Customer / client protection and product compliance",
    "fraud": "Fraud (External and Internal)",
    "external fraud": "Fraud (External and Internal)",
    "internal fraud": "Fraud (External and Internal)",
    "fraud (external & internal)": "Fraud (External and Internal)",
    "processing execution and change": "Processing, Execution and Change",
    "processing execution & change": "Processing, Execution and Change",
    "processing, execution & change": "Processing, Execution and Change",
    "processing, execution, and change": "Processing, Execution and Change",
    "fx & price": "FX and Price",
    "fx and price risk": "FX and Price",
    "interest rate risk": "Interest Rate",
    "consumer & small business": "Consumer and Small Business",
    "third-party": "Third Party",
    "information security / data protection": "Information and Cyber Security",
    "people (including conduct & culture": "Conduct",
    "people (including conduct & culture)": "Conduct",
    "physical security & internal fraud": "Fraud (External and Internal)",
    "physical security and internal fraud": "Fraud (External and Internal)",
}

# Values that are old L1 names or otherwise unmappable to a single L2
_UNMAPPABLE_L2S = {
    "nan", "Country", "Compliance", "Market", "Operational",
    "Strategic", "Credit", "Reputational", "Liquidity",
    "Fair Lending / Regulation B", "Operational - Legal",
}

# Build case-insensitive lookup (includes exact taxonomy names)
_L2_LOOKUP = {k.lower(): v for k, v in _L2_ALIASES.items()}
for _l2_name in L2_TO_L1:
    _L2_LOOKUP[_l2_name.lower()] = _l2_name

_UNMAPPABLE_LOWER = {v.lower() for v in _UNMAPPABLE_L2S}


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
