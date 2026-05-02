"""
Risk Taxonomy Transformer
=========================
Transforms legacy 14-pillar risk taxonomy into new 6 L1 / 23 L2 taxonomy.
Handles: LLM override file, key risk description lookup, deterministic mapping,
1:many keyword resolution, and rating decomposition.

Resolution order for multi mappings:
  Override -- LLM-classified overrides from Review Queue (highest priority)
  Evidence -- Keyword matching on rationale text + key risk descriptions
  Default  -- First primary L2, flagged for review

Workflow:
  1. Run script without overrides -> produces Review Queue
  2. Batch Review Queue through LLM prompt -> produces override file
  3. Re-run script with override file -> overrides replace low-confidence mappings

SETUP:
1. Edit taxonomy_config.yaml with your mappings, keywords, and taxonomy
2. Set file paths in main() (Section 5), including SUB_RISK_PATH
3. Run: python -m risk_taxonomy_transformer
4. (Optional) Batch Review Queue through LLM, save as overrides, re-run
"""

# Public API re-exports.
# NOTE: Do NOT import from __main__ here — it causes circular import issues
# when running with `python -m risk_taxonomy_transformer`.
# Users who need main() should import it directly:
#   from risk_taxonomy_transformer.__main__ import main
from risk_taxonomy_transformer.pipeline import run_pipeline
from risk_taxonomy_transformer.review_builders import (
    build_audit_review_df,
    build_review_queue_df,
    build_risk_owner_review_df,
    build_ro_summary_df,
)
from risk_taxonomy_transformer.export import export_results
from risk_taxonomy_transformer.config import TransformContext

__all__ = [
    "run_pipeline",
    "build_audit_review_df",
    "build_review_queue_df",
    "build_risk_owner_review_df",
    "build_ro_summary_df",
    "export_results",
    "TransformContext",
]
