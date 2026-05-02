"""
Pipeline orchestration for the Risk Taxonomy Transformer.

Runs the full transformation across all entities.
"""

from __future__ import annotations

import logging

import pandas as pd

from risk_taxonomy_transformer.config import TransformContext
from risk_taxonomy_transformer.mapping import transform_entity

logger = logging.getLogger(__name__)


def _log_transformation_summary(transformed_df: pd.DataFrame):
    """Log aggregate statistics about the transformation results."""
    total = len(transformed_df)
    if total == 0:
        logger.info("TRANSFORMATION COMPLETE — no rows produced")
        return

    # Compute all counts from a single pass over the method column
    method_counts = transformed_df["method"].value_counts()
    def method_contains(substr):
        return transformed_df["method"].str.contains(substr, na=False)

    conf_counts = transformed_df["confidence"].value_counts()
    needs_review = transformed_df["needs_review"].sum()
    evidence_mask = method_contains("evidence_match")
    dims_parsed = transformed_df["dims_parsed_from_rationale"].sum()

    logger.info("=" * 60)
    logger.info("TRANSFORMATION COMPLETE")
    logger.info(f"  Total rows: {total}")
    logger.info(f"  High confidence: {conf_counts.get('high', 0)} ({conf_counts.get('high', 0)/total*100:.1f}%)")
    logger.info(f"  Medium confidence: {conf_counts.get('medium', 0)} ({conf_counts.get('medium', 0)/total*100:.1f}%)")
    logger.info(f"  Low confidence / needs review: {conf_counts.get('low', 0)} ({conf_counts.get('low', 0)/total*100:.1f}%)")
    logger.info(f"  Source N/A (skipped): {method_counts.get('source_not_applicable', 0)}")
    logger.info(f"  Assumed N/A — Verify: {method_counts.get('evaluated_no_evidence', 0)}")
    logger.info(f"  True gap fills (no legacy pillar maps): {method_counts.get('true_gap_fill', 0)}")
    evidence_total = evidence_mask.sum()
    evidence_high = (evidence_mask & (transformed_df["confidence"] == "high")).sum()
    evidence_med = (evidence_mask & (transformed_df["confidence"] == "medium")).sum()
    logger.info(f"  Evidence-based matches: {evidence_total} (high: {evidence_high}, medium: {evidence_med})")
    logger.info(f"  Issue-confirmed applicable: {method_counts.get('issue_confirmed', 0)}")
    logger.info(f"  No evidence — all candidates (flagged for review): {method_counts.get('no_evidence_all_candidates', 0)}")
    llm_applicable = method_contains('llm_override').sum()
    llm_na = method_contains('llm_confirmed_na').sum()
    logger.info(f"  Resolved via LLM: {llm_applicable + llm_na} ({llm_applicable} applicable, {llm_na} confirmed N/A)")
    logger.info(f"  Deduplicated (multiple sources -> same L2): {method_contains('dedup').sum()}")
    logger.info(f"  Dimensions parsed from rationale: {dims_parsed}")
    logger.info(f"  Applicability undetermined (team decision required): {needs_review}")
    logger.info("=" * 60)


def run_pipeline(
    legacy_df: pd.DataFrame,
    entity_id_col: str,
    ctx: TransformContext,
) -> pd.DataFrame:
    """Run the full transformation pipeline across all entities."""
    all_transformed = []

    for i, (_, row) in enumerate(legacy_df.iterrows(), start=1):
        entity_id = str(row[entity_id_col]).strip()
        logger.info(f"Processing entity {entity_id} ({i}/{len(legacy_df)})")
        transformed = transform_entity(entity_id, row, ctx)
        all_transformed.extend(transformed)

    transformed_df = pd.DataFrame(all_transformed)

    _log_transformation_summary(transformed_df)

    return transformed_df
