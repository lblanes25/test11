"""
Mapping engine for the Risk Taxonomy Transformer.

Resolves multi-target mappings via keyword evidence scoring, deduplicates
rows when multiple legacy pillars map to the same new L2, and transforms
individual audit entities from the legacy taxonomy to the new taxonomy.
"""

from __future__ import annotations

import logging

import pandas as pd

from risk_taxonomy_transformer.config import (
    CROSSWALK_CONFIG,
    HIGH_CONFIDENCE_THRESHOLD,
    KEYWORD_MAP,
    L2_TO_L1,
    NA_STRINGS,
    TransformContext,
)
from risk_taxonomy_transformer.constants import BLANK_METHODS, Method
from risk_taxonomy_transformer.rating import (
    _make_row,
    convert_control_rating,
    convert_risk_rating,
    parse_rationale_for_dimensions,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Findings pre-check helper (Phase 5 extraction)
# ---------------------------------------------------------------------------

def _create_findings_confirmed_rows(
    entity_id: str,
    findings_index: dict,
) -> list[dict]:
    """Create placeholder rows for L2s confirmed applicable by findings.

    If an entity has findings tagged to a new L2, that L2 is confirmed
    applicable.  These rows carry no ratings (ratings come from legacy
    pillar data) and may be overridden during dedup if the crosswalk also
    produces rated rows.
    """
    rows = []
    entity_findings = findings_index.get(entity_id, {})
    for l2, findings_list in entity_findings.items():
        if l2 in L2_TO_L1:
            issue_summaries = [
                f"{f['issue_id']}: {f['issue_title']} ({f['severity']}, {f['status']})"
                for f in findings_list[:5]
            ]
            l1 = L2_TO_L1[l2]
            rows.append(_make_row(
                entity_id, l1, l2,
                source_legacy_pillar="Findings",
                mapping_type="findings",
                confidence="high",
                method=Method.ISSUE_CONFIRMED,
                sub_risk_evidence="; ".join(issue_summaries),
            ))
            logger.info(f"  Entity {entity_id}: '{l2}' confirmed applicable by {len(findings_list)} finding(s)")
    return rows


# ---------------------------------------------------------------------------
# Multi-mapping resolution
# ---------------------------------------------------------------------------

def _resolve_multi_mapping(
    entity_id: str,
    legacy_pillar: str,
    pillar_config: dict,
    rationale: str,
    sub_risk_index: dict | None,
    overrides: dict | None,
) -> list[dict] | None:
    """Resolve a multi-target mapping by scoring evidence for each candidate L2.

    Returns list of target dicts [{l2, confidence, method, sub_risk_evidence}],
    or None if the mapping produced no targets and has no primary fallback.
    """
    targets_to_create = []

    # Prepare text sources separately so evidence can be labeled
    rationale_text = str(rationale).lower() if rationale else ""
    entity_subs = (sub_risk_index or {}).get(entity_id, {})
    sub_risk_entries = entity_subs.get(legacy_pillar, [])  # list of (risk_id, description)

    first_primary_l2 = None
    for target in pillar_config["targets"]:
        if target["relationship"] == "primary" and not first_primary_l2:
            first_primary_l2 = target["l2"]

        # Check LLM override for this entity+pillar+L2
        if overrides and entity_id:
            override_key = (entity_id, legacy_pillar, target["l2"])
            override_entry = overrides.get(override_key)
            if override_entry:
                reasoning = override_entry.get("reasoning", "")
                evidence = [f"AI review: {reasoning}"] if reasoning else []
                if override_entry["determination"] == "applicable":
                    targets_to_create.append({
                        "l2": target["l2"],
                        "confidence": override_entry["confidence"],
                        "method": Method.LLM_OVERRIDE,
                        "sub_risk_evidence": evidence,
                    })
                else:
                    # LLM confirmed not applicable -- add explicitly so it's tracked
                    targets_to_create.append({
                        "l2": target["l2"],
                        "confidence": "high",
                        "method": Method.LLM_CONFIRMED_NA,
                        "sub_risk_evidence": evidence,
                    })
                continue

        # Score this L2 against rationale and sub-risk descriptions separately
        l2_name = target["l2"]
        keywords = KEYWORD_MAP.get(l2_name, [])
        conditions = target.get("conditions", [])
        all_keywords = keywords + conditions

        labeled_evidence = []
        score = 0

        # Check rationale text
        rationale_hits = [kw for kw in all_keywords if kw in rationale_text]
        if rationale_hits:
            score += len(rationale_hits)
            labeled_evidence.append(f"rationale: {', '.join(rationale_hits)}")

        # Check each sub-risk description individually
        for risk_id, desc in sub_risk_entries:
            desc = str(desc) if desc is not None else ""
            if not desc or desc == "nan":
                continue
            desc_lower = desc.lower()
            desc_hits = [kw for kw in all_keywords if kw in desc_lower]
            if desc_hits:
                score += len(desc_hits)
                truncated = desc[:80] + "..." if len(desc) > 80 else desc
                labeled_evidence.append(f"sub-risk {risk_id}: {', '.join(desc_hits)}")

        relationship = target["relationship"]

        if score > 0:
            if score >= HIGH_CONFIDENCE_THRESHOLD:
                confidence = "high"
            else:
                confidence = "medium"
            method = f"{Method.EVIDENCE_MATCH} ({relationship})"
            targets_to_create.append({
                "l2": l2_name,
                "confidence": confidence,
                "method": method,
                "sub_risk_evidence": labeled_evidence[:8],
            })

    # If no L2s had evidence, populate ALL candidate L2s and flag for team review.
    # Don't pick one for them -- present the data and let them decide applicability.
    if not targets_to_create:
        candidate_l2s = [t["l2"] for t in pillar_config["targets"]]
        if candidate_l2s:
            for l2_name in candidate_l2s:
                targets_to_create.append({
                    "l2": l2_name,
                    "confidence": "low",
                    "method": Method.NO_EVIDENCE_ALL_CANDIDATES,
                    "sub_risk_evidence": [],
                })
            logger.info(
                f"  Entity {entity_id}: '{legacy_pillar}' -> no evidence for any L2, "
                f"populated all {len(candidate_l2s)} candidates \u2014 FLAGGED FOR REVIEW"
            )
        else:
            logger.warning(
                f"  Entity {entity_id}: '{legacy_pillar}' multi mapping "
                f"produced no targets and has no candidates"
            )
            return None

    return targets_to_create


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _deduplicate_transformed_rows(transformed: list[dict], entity_id: str) -> list[dict]:
    """Deduplicate when multiple legacy pillars map to the same new L2.

    6-branch dedup logic:
    -----------------------------------------------------------------------
    Branch 1: New row is issue_confirmed, existing is a blank-method placeholder
              -> replace existing with the findings-confirmed row.
    Branch 2: Existing is issue_confirmed, new is a blank-method placeholder
              -> keep existing (do nothing).
    Branch 3: Existing is issue_confirmed AND new row also has a positive rating
              -> keep new (rated) row but append findings evidence from existing.
    Branch 4: New is issue_confirmed AND existing already has a positive rating
              -> keep existing (rated) row but append findings evidence from new.
    Branch 5: Both have ratings, new is higher -> keep new (more conservative).
    Branch 6: Both have ratings, existing is equal or higher -> keep existing.
    -----------------------------------------------------------------------
    """
    seen = {}
    deduped = []
    for row in transformed:
        l2 = row["new_l2"]
        if l2 not in seen:
            seen[l2] = len(deduped)
            deduped.append(row)
        else:
            existing = deduped[seen[l2]]
            existing_rating = existing.get("likelihood") or 0
            new_rating = row.get("likelihood") or 0
            existing_method = existing.get("method", "")
            new_method = row.get("method", "")

            if new_method == Method.ISSUE_CONFIRMED and existing_method in BLANK_METHODS:
                deduped[seen[l2]] = row
            elif existing_method == Method.ISSUE_CONFIRMED and new_method in BLANK_METHODS:
                pass
            elif existing_method == Method.ISSUE_CONFIRMED and new_rating > 0:
                keyword_evidence = row.get("sub_risk_evidence", "")
                finding_evidence = existing.get("sub_risk_evidence", "")
                if finding_evidence.startswith("Finding detail:"):
                    finding_evidence = finding_evidence[len("Finding detail:"):].lstrip()
                if keyword_evidence and finding_evidence:
                    sub_risk_evidence = f"{keyword_evidence}\nFinding detail: {finding_evidence}"
                elif finding_evidence:
                    sub_risk_evidence = f"Finding detail: {finding_evidence}"
                else:
                    sub_risk_evidence = keyword_evidence
                row["sub_risk_evidence"] = sub_risk_evidence
                row["source_legacy_pillar"] = (
                    f"{row['source_legacy_pillar']} (also: Findings)"
                )
                deduped[seen[l2]] = row
            elif new_method == Method.ISSUE_CONFIRMED and existing_rating > 0:
                keyword_evidence = existing.get("sub_risk_evidence", "")
                finding_evidence = row.get("sub_risk_evidence", "")
                if finding_evidence.startswith("Finding detail:"):
                    finding_evidence = finding_evidence[len("Finding detail:"):].lstrip()
                if keyword_evidence and finding_evidence:
                    sub_risk_evidence = f"{keyword_evidence}\nFinding detail: {finding_evidence}"
                elif finding_evidence:
                    sub_risk_evidence = f"Finding detail: {finding_evidence}"
                else:
                    sub_risk_evidence = keyword_evidence
                existing["sub_risk_evidence"] = sub_risk_evidence
                existing["source_legacy_pillar"] = (
                    f"{existing['source_legacy_pillar']} (also: Findings)"
                )
            elif new_rating > existing_rating:
                row["source_legacy_pillar"] = (
                    f"{row['source_legacy_pillar']} (also: {existing['source_legacy_pillar']})"
                )
                row["method"] = f"{row['method']} (dedup: kept higher)"
                deduped[seen[l2]] = row
            else:
                existing["source_legacy_pillar"] = (
                    f"{existing['source_legacy_pillar']} (also: {row['source_legacy_pillar']})"
                )
                if "dedup" not in existing_method:
                    existing["method"] = f"{existing_method} (dedup: kept higher)"

            logger.info(
                f"  Entity {entity_id}: DEDUP '{l2}' \u2014 "
                f"'{row.get('source_legacy_pillar', '')}' [{new_method}] vs "
                f"existing [{existing_method}]"
            )
    return deduped


# ---------------------------------------------------------------------------
# Entity transformation
# ---------------------------------------------------------------------------

def transform_entity(
    entity_id: str,
    entity_row: pd.Series,
    ctx: TransformContext,
) -> list[dict]:
    """Transform one audit entity from legacy to new taxonomy."""
    crosswalk = ctx.crosswalk
    pillar_columns = ctx.pillar_columns
    sub_risk_index = ctx.sub_risk_index
    overrides = ctx.overrides
    findings_index = ctx.findings_index

    transformed = []
    mapped_l2s = set()

    # --- Pre-check: findings-confirmed L2s ---
    if findings_index:
        findings_rows = _create_findings_confirmed_rows(entity_id, findings_index)
        for row in findings_rows:
            mapped_l2s.add(row["new_l2"])
        transformed.extend(findings_rows)

    for legacy_pillar, pillar_config in crosswalk.items():
        # Get legacy data for this pillar
        cols = pillar_columns.get(legacy_pillar)
        if not cols:
            logger.warning(f"  Entity {entity_id}: No columns found for '{legacy_pillar}'")
            continue

        rating_raw = entity_row.get(cols.get("rating"))
        rationale = entity_row.get(cols.get("rationale"), "")
        control_raw = entity_row.get(cols.get("control"))
        control_rationale = entity_row.get(cols.get("control_rationale"), "")

        rating_numeric = convert_risk_rating(rating_raw)
        control_numeric = convert_control_rating(control_raw)

        # Skip N/A ratings -- flag all candidate L2s as not applicable
        raw_str = str(rating_raw).strip().lower() if rating_raw and not pd.isna(rating_raw) else ""
        is_na = (rating_numeric is None and raw_str in NA_STRINGS)

        if is_na:
            # Determine which L2s this pillar would have mapped to
            na_mapping_type = pillar_config.get("mapping_type", "")
            if na_mapping_type == "direct":
                na_l2s = [pillar_config["target_l2"]]
            elif na_mapping_type == "multi":
                na_l2s = [t["l2"] for t in pillar_config["targets"]]
            else:
                na_l2s = []

            for l2_name in na_l2s:
                l1 = L2_TO_L1.get(l2_name, "UNKNOWN")
                mapped_l2s.add(l2_name)
                transformed.append(_make_row(
                    entity_id, l1, l2_name,
                    source_legacy_pillar=legacy_pillar,
                    source_risk_rating_raw=rating_raw,
                    source_rationale=str(rationale) if rationale else "",
                    source_control_raw=control_raw,
                    mapping_type=pillar_config.get("mapping_type", ""),
                    confidence="high",
                    method=Method.SOURCE_NOT_APPLICABLE,
                ))
            logger.info(f"  Entity {entity_id}: '{legacy_pillar}' -> N/A, flagged {len(na_l2s)} L2s as not applicable")
            continue

        # Parse rationale for explicit dimension mentions
        parsed_dims = parse_rationale_for_dimensions(str(rationale))

        # Build the 5 risk dimension values
        likelihood = parsed_dims.get("likelihood", rating_numeric)
        impact_financial = parsed_dims.get("impact_financial", rating_numeric)
        impact_reputational = parsed_dims.get("impact_reputational", rating_numeric)
        impact_consumer_harm = parsed_dims.get("impact_consumer_harm", rating_numeric)
        impact_regulatory = parsed_dims.get("impact_regulatory", rating_numeric)
        # If generic "impact" was parsed, use it as default for all impact cols
        if "impact" in parsed_dims:
            generic_impact = parsed_dims["impact"]
            impact_financial = parsed_dims.get("impact_financial", generic_impact)
            impact_reputational = parsed_dims.get("impact_reputational", generic_impact)
            impact_consumer_harm = parsed_dims.get("impact_consumer_harm", generic_impact)
            impact_regulatory = parsed_dims.get("impact_regulatory", generic_impact)

        mapping_type = pillar_config["mapping_type"]

        # Build list of target L2s to create rows for
        if mapping_type == "direct":
            targets_to_create = [{
                "l2": pillar_config["target_l2"],
                "confidence": "high",
                "method": Method.DIRECT,
                "sub_risk_evidence": [],
            }]

        elif mapping_type == "multi":
            # If no rationale column exists for this pillar, skip keyword scoring --
            # populate all primary L2s directly with high confidence
            has_rationale = cols.get("rationale") is not None
            if not has_rationale:
                targets_to_create = [
                    {
                        "l2": t["l2"],
                        "confidence": "high",
                        "method": "direct (no rationale column)",
                        "sub_risk_evidence": [],
                    }
                    for t in pillar_config["targets"]
                    if t["relationship"] == "primary"
                ]
            else:
                targets_to_create = _resolve_multi_mapping(
                    entity_id, legacy_pillar, pillar_config, rationale,
                    sub_risk_index, overrides,
                )
            if targets_to_create is None:
                continue

            # Track candidate L2s that were evaluated but had no evidence
            matched_l2s_this_pillar = {t["l2"] for t in targets_to_create}
            # Siblings with evidence = matched L2s excluding confirmed-N/A
            siblings_with_evidence = [
                t["l2"] for t in targets_to_create
                if t["method"] not in (Method.LLM_CONFIRMED_NA, Method.NO_EVIDENCE_ALL_CANDIDATES)
            ]
            siblings_str = "siblings_with_evidence: " + "; ".join(siblings_with_evidence) if siblings_with_evidence else ""

            for target in pillar_config["targets"]:
                candidate_l2 = target["l2"]
                if candidate_l2 not in matched_l2s_this_pillar:
                    l1 = L2_TO_L1.get(candidate_l2, "UNKNOWN")
                    mapped_l2s.add(candidate_l2)
                    transformed.append(_make_row(
                        entity_id, l1, candidate_l2,
                        source_legacy_pillar=legacy_pillar,
                        source_risk_rating_raw=rating_raw,
                        source_rationale=str(rationale) if rationale else "",
                        source_control_raw=control_raw,
                        mapping_type=mapping_type,
                        confidence="none",
                        method=Method.EVALUATED_NO_EVIDENCE,
                        sub_risk_evidence=siblings_str,
                    ))

        else:
            logger.error(f"  Unknown mapping_type '{mapping_type}' for '{legacy_pillar}'")
            continue

        dims_were_parsed = bool(parsed_dims)
        suppress_rating = pillar_config.get("suppress_rating", False)

        for target_match in targets_to_create:
            selected_l2 = target_match["l2"]
            l1 = L2_TO_L1.get(selected_l2, "UNKNOWN")
            mapped_l2s.add(selected_l2)

            # LLM-confirmed N/A rows and suppress_rating pillars don't carry
            # forward ratings (the latter per Matt 2026-05-01 for External Fraud:
            # one legacy rating cannot be split between First Party / Victim).
            is_na_override = target_match["method"] == Method.LLM_CONFIRMED_NA
            clear_ratings = is_na_override or suppress_rating

            row = _make_row(
                entity_id, l1, selected_l2,
                likelihood=None if clear_ratings else likelihood,
                impact_financial=None if clear_ratings else impact_financial,
                impact_reputational=None if clear_ratings else impact_reputational,
                impact_consumer_harm=None if clear_ratings else impact_consumer_harm,
                impact_regulatory=None if clear_ratings else impact_regulatory,
                source_legacy_pillar=legacy_pillar,
                source_risk_rating_raw=rating_raw,
                source_rationale=str(rationale) if rationale else "",
                source_control_raw=control_raw,
                source_control_rationale=str(control_rationale) if control_rationale else "",
                mapping_type=mapping_type,
                confidence=target_match["confidence"],
                method=target_match["method"],
                dims_parsed_from_rationale=dims_were_parsed,
                sub_risk_evidence="; ".join(target_match["sub_risk_evidence"]) if target_match["sub_risk_evidence"] else "",
                needs_review=target_match["confidence"] == "low",
            )
            transformed.append(row)
            logger.info(
                f"  Entity {entity_id}: '{legacy_pillar}' -> {l1} / {selected_l2} "
                f"[{target_match['method']}, conf={target_match['confidence']}]"
            )

    transformed = _deduplicate_transformed_rows(transformed, entity_id)

    # Identify any new L2 risks with NO legacy mapping at all (true gaps)
    # With the current crosswalk this should be zero.
    for l2 in L2_TO_L1:
        if l2 not in mapped_l2s:
            l1 = L2_TO_L1[l2]
            transformed.append(_make_row(
                entity_id, l1, l2,
                mapping_type="no_legacy_source",
                confidence="none",
                method=Method.TRUE_GAP_FILL,
            ))

    return transformed
