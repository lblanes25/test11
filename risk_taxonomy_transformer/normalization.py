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
    r"^(?:Operational and Compliance|Operational|Compliance|Strategic|Market|Credit|"
    r"Liquidity|Reputational|Reputation)\s*[-\u2013]\s*"
)

# Known name variations -> canonical L2 name.
# Includes aliases for the pre-2026-04-21 L2 names so legacy free-text inputs
# (e.g., IAG findings, PRSA issues) still normalize to the renamed taxonomy.
_L2_ALIASES = {
    # Info & Cyber Security (renamed from "Information and Cyber Security")
    "infosec": "Info & Cyber Security",
    "info security": "Info & Cyber Security",
    "information security": "Info & Cyber Security",
    "cyber security": "Info & Cyber Security",
    "cybersecurity": "Info & Cyber Security",
    "info and cyber security": "Info & Cyber Security",
    "information and cyber security": "Info & Cyber Security",
    "information security / data protection": "Info & Cyber Security",
    # Prudential Compliance (renamed from long-form)
    "prudential & bank admin compliance": "Prudential Compliance",
    "prudential and bank administration compliance": "Prudential Compliance",
    "prudential & bank admin": "Prudential Compliance",
    "prudential & bank administration compliance": "Prudential Compliance",
    # Consumer Compliance (renamed from customer/client protection)
    "customer / client protection": "Consumer Compliance",
    "customer/client protection and product compliance": "Consumer Compliance",
    "customer / client protection and product compliance": "Consumer Compliance",
    "client protection": "Consumer Compliance",
    # Financial Crimes (case normalization)
    "financial crimes": "Financial Crimes",
    "financial crime": "Financial Crimes",
    # Fraud at L3 grain (Matt 2026-05-01). The two External Fraud L3 sub-
    # types and Internal Fraud are evaluated as L2-grain entries in the new
    # taxonomy; dashed names from the enterprise L2_Risk_Taxonomy file and
    # ORE/PRSA/RAP mapper outputs alias to their canonical L3 names. The
    # legacy umbrella "Fraud" / "Fraud (External and Internal)" / bare
    # "External Fraud" tokens are intentionally unmapped (return None) —
    # too ambiguous to assign to one specific L3 without other evidence.
    "external fraud - first party": "External Fraud - First Party",
    "external fraud - first party fraud": "External Fraud - First Party",
    "external fraud - victim fraud": "External Fraud - Victim Fraud",
    "external fraud - victim third party": "External Fraud - Victim Fraud",
    "external fraud - victim / third party": "External Fraud - Victim Fraud",
    "external fraud - third party": "External Fraud - Victim Fraud",
    "internal fraud": "Internal Fraud",
    "physical security & internal fraud": "Internal Fraud",
    "physical security and internal fraud": "Internal Fraud",
    # Other
    "processing execution and change": "Processing, Execution and Change",
    "processing execution & change": "Processing, Execution and Change",
    "processing, execution & change": "Processing, Execution and Change",
    "processing, execution, and change": "Processing, Execution and Change",
    "fx & price": "FX and Price",
    "fx and price risk": "FX and Price",
    "interest rate risk": "Interest Rate",
    "consumer & small business": "Consumer and Small Business",
    "third-party": "Third Party",
    "people (including conduct & culture": "Conduct",
    "people (including conduct & culture)": "Conduct",
}

# Values that are old L1 names or otherwise unmappable to a single L2.
# Earnings, Reputation, and Country are in the 24-risk taxonomy as
# "Not Assessed" (2026-04-21 Matt update) — no L2 rows produced, so free-text
# inputs naming them normalize to None rather than creating orphan rows.
_UNMAPPABLE_L2S = {
    "nan", "Country", "Compliance", "Market", "Operational",
    "Strategic", "Credit", "Reputational", "Reputation", "Liquidity",
    "Earnings",
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
