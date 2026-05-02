"""
Configuration loading and accessor functions for the Risk Taxonomy Transformer.

Loads the YAML config eagerly at import time (matching original behavior) and
exposes all derived lookups (L2_TO_L1, NEW_TAXONOMY, KEYWORD_MAP, etc.) as
plain module-level variables that static analyzers can see.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

_CONFIG_PATH = _PROJECT_ROOT / "config" / "taxonomy_config.yaml"


# =============================================================================
# Config loading
# =============================================================================

def _load_config(config_path: Path = _CONFIG_PATH) -> dict:
    """Load and validate taxonomy configuration from YAML."""
    logger.info(f"Loading config from {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    required_keys = ["risk_rating_map", "control_rating_map", "new_taxonomy",
                     "crosswalk_config", "keyword_map", "l2_aliases", "l2_unmappable"]
    missing = [k for k in required_keys if k not in cfg]
    if missing:
        raise ValueError(f"taxonomy_config.yaml missing required keys: {missing}")

    # Pre-lowercase all keyword lists so inner loops don't repeat .lower()
    for l2_key in cfg["keyword_map"]:
        cfg["keyword_map"][l2_key] = [kw.lower() for kw in cfg["keyword_map"][l2_key]]

    # Pre-lowercase condition lists in crosswalk targets
    for pillar_cfg in cfg["crosswalk_config"].values():
        for target in pillar_cfg.get("targets", []):
            if "conditions" in target:
                target["conditions"] = [c.lower() for c in target["conditions"]]

    # Validate l2_aliases: every value must be a canonical L2 in new_taxonomy.
    canonical_l2s = {l2 for l2_list in cfg["new_taxonomy"].values() for l2 in l2_list}
    bad_alias_values = {k: v for k, v in cfg["l2_aliases"].items()
                        if v not in canonical_l2s}
    if bad_alias_values:
        raise ValueError(
            f"taxonomy_config.yaml l2_aliases values not in new_taxonomy: "
            f"{bad_alias_values}"
        )

    # Validate l2_aliases: keys must be unique case-insensitively (YAML already
    # rejects exact duplicates; this catches "Foo" vs "foo" collisions).
    lower_keys = [str(k).lower() for k in cfg["l2_aliases"]]
    if len(lower_keys) != len(set(lower_keys)):
        from collections import Counter
        dups = [k for k, c in Counter(lower_keys).items() if c > 1]
        raise ValueError(
            f"taxonomy_config.yaml l2_aliases has case-insensitive duplicate keys: {dups}"
        )

    # Backward compatibility: if 'columns' key is missing, log a warning
    if "columns" not in cfg:
        logger.warning("Config missing 'columns' section \u2014 using hardcoded defaults. "
                       "Update taxonomy_config.yaml to centralize column names.")

    return cfg


def get_config() -> dict:
    """Return the parsed config dict (cached after first load)."""
    return _CFG


# =============================================================================
# Load config eagerly at import time — matches original single-file behavior.
# All downstream module-level names are plain assignments so static analyzers
# (PyCharm, mypy, pyright) can resolve them.
# =============================================================================

_CFG: dict = _load_config()

HIGH_CONFIDENCE_THRESHOLD: int = _CFG.get("high_confidence_threshold", 3)
NA_STRINGS: tuple = tuple(_CFG.get("na_strings", ("not applicable", "n/a", "na", "")))
RATING_WORDS: str = "low|medium|high|critical"  # regex fragment for rationale parsing
RISK_RATING_MAP: dict = _CFG["risk_rating_map"]
CONTROL_RATING_MAP: dict = _CFG["control_rating_map"]
NEW_TAXONOMY: dict = _CFG["new_taxonomy"]
CROSSWALK_CONFIG: dict = _CFG["crosswalk_config"]
KEYWORD_MAP: dict = _CFG["keyword_map"]
L2_ALIASES: dict = _CFG["l2_aliases"]
L2_UNMAPPABLE: set = set(_CFG["l2_unmappable"])

# Flatten taxonomy for validation and lookup
L2_TO_L1: dict[str, str] = {}
for _l1, _l2_list in NEW_TAXONOMY.items():
    for _l2 in _l2_list:
        L2_TO_L1[_l2] = _l1


# =============================================================================
# Column config — application and auxiliary columns
# =============================================================================

# Application/engagement columns in the legacy data (defaults)
_APP_COLS: dict = {
    "primary_it": "PRIMARY IT APPLICATIONS (MAPPED)",
    "secondary_it": "SECONDARY IT APPLICATIONS (RELATED OR RELIED ON)",
    "primary_tp": "PRIMARY TLM THIRD PARTY ENGAGEMENT",
    "secondary_tp": "SECONDARY TLM THIRD PARTY ENGAGEMENTS (RELATED OR RELIED ON)",
    "models": "Models (View Only)",
}

# Auxiliary risk dimension columns (defaults)
_AUX_COLS: list = [
    "AXP Auxiliary Risk Dimensions",
    "AENB Auxiliary Risk Dimensions",
]

# Core risk dimension columns (defaults) — same structure as aux, separate
# column pair in legacy data naming the entity's primary L2 risks.
_CORE_COLS: list = [
    "AXP Core Risk Dimensions",
    "AENB Core Risk Dimensions",
]

# Override from config if present
_col_cfg = _CFG.get("columns", {})
if "applications" in _col_cfg:
    _APP_COLS = _col_cfg["applications"]
if "auxiliary_risk_dimensions" in _col_cfg:
    _AUX_COLS = _col_cfg["auxiliary_risk_dimensions"]
if "core_risk_dimensions" in _col_cfg:
    _CORE_COLS = _col_cfg["core_risk_dimensions"]


def get_app_cols() -> dict:
    """Return the application/engagement column mapping."""
    return _APP_COLS


def get_aux_cols() -> list:
    """Return the auxiliary risk dimension column names."""
    return _AUX_COLS


def get_core_cols() -> list:
    """Return the core risk dimension column names."""
    return _CORE_COLS


# =============================================================================
# TransformContext dataclass
# =============================================================================

@dataclass
class TransformContext:
    """Bundles shared lookup data passed through the transformation pipeline."""
    crosswalk: dict
    pillar_columns: dict
    sub_risk_index: dict | None = None
    overrides: dict | None = None
    findings_index: dict | None = None
    ore_index: dict | None = None
    enterprise_findings_index: dict | None = None
