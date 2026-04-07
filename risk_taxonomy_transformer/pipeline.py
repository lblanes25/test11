"""
Pipeline orchestration for the Risk Taxonomy Transformer.

Runs the full transformation across all entities and applies overlay flags.
"""

from __future__ import annotations

import logging

import pandas as pd

from risk_taxonomy_transformer.config import TransformContext
from risk_taxonomy_transformer.mapping import transform_entity

logger = logging.getLogger(__name__)


def _log_transformation_summary(transformed_df: pd.DataFrame, overlays_df: pd.DataFrame):
    """Log aggregate statistics about the transformation results."""
    total = len(transformed_df)
    if total == 0:
        logger.info("TRANSFORMATION COMPLETE \u2014 no rows produced")
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
    logger.info(f"  Assumed N/A \u2014 Verify: {method_counts.get('evaluated_no_evidence', 0)}")
    logger.info(f"  True gap fills (no legacy pillar maps): {method_counts.get('true_gap_fill', 0)}")
    evidence_total = evidence_mask.sum()
    evidence_high = (evidence_mask & (transformed_df["confidence"] == "high")).sum()
    evidence_med = (evidence_mask & (transformed_df["confidence"] == "medium")).sum()
    logger.info(f"  Evidence-based matches: {evidence_total} (high: {evidence_high}, medium: {evidence_med})")
    logger.info(f"  Issue-confirmed applicable: {method_counts.get('issue_confirmed', 0)}")
    logger.info(f"  No evidence \u2014 all candidates (flagged for review): {method_counts.get('no_evidence_all_candidates', 0)}")
    llm_applicable = method_contains('llm_override').sum()
    llm_na = method_contains('llm_confirmed_na').sum()
    logger.info(f"  Resolved via LLM: {llm_applicable + llm_na} ({llm_applicable} applicable, {llm_na} confirmed N/A)")
    logger.info(f"  Deduplicated (multiple sources -> same L2): {method_contains('dedup').sum()}")
    logger.info(f"  Dimensions parsed from rationale: {dims_parsed}")
    logger.info(f"  Overlay flags: {len(overlays_df)}")
    logger.info(f"  Applicability undetermined (team decision required): {needs_review}")
    logger.info("=" * 60)


def run_pipeline(
    legacy_df: pd.DataFrame,
    entity_id_col: str,
    ctx: TransformContext,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the full transformation pipeline across all entities."""
    all_transformed = []
    all_overlays = []

    for i, (_, row) in enumerate(legacy_df.iterrows(), start=1):
        entity_id = str(row[entity_id_col]).strip()
        logger.info(f"Processing entity {entity_id} ({i}/{len(legacy_df)})")
        transformed, overlays = transform_entity(entity_id, row, ctx)
        all_transformed.extend(transformed)
        all_overlays.extend(overlays)

    transformed_df = pd.DataFrame(all_transformed)
    overlays_df = pd.DataFrame(all_overlays) if all_overlays else pd.DataFrame()

    _log_transformation_summary(transformed_df, overlays_df)

    return transformed_df, overlays_df


def apply_overlay_flags(transformed_df: pd.DataFrame, overlays_df: pd.DataFrame) -> pd.DataFrame:
    """Join overlay flags onto the transformed data."""
    if overlays_df.empty:
        transformed_df["overlay_flag"] = False
        transformed_df["overlay_source"] = ""
        transformed_df["overlay_rating"] = None
        transformed_df["overlay_rationale"] = ""
        return transformed_df

    # Aggregate overlays per entity+L2
    overlay_agg = (
        overlays_df
        .groupby(["entity_id", "target_l2"])
        .agg({
            "overlay_source": lambda x: "; ".join(x),
            "overlay_rating": "max",
            "overlay_rationale": lambda x: " | ".join(x),
        })
        .reset_index()
    )

    merged = transformed_df.merge(
        overlay_agg,
        left_on=["entity_id", "new_l2"],
        right_on=["entity_id", "target_l2"],
        how="left",
        suffixes=("", "_overlay"),
    )
    merged["overlay_flag"] = merged["target_l2"].notna()
    merged.drop(columns=["target_l2"], errors="ignore", inplace=True)
    merged["overlay_source"] = merged["overlay_source"].fillna("")
    merged["overlay_rationale"] = merged["overlay_rationale"].fillna("")

    return merged
