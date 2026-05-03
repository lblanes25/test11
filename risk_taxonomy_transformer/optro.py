"""
Optro override application.

Optro is the system audit teams use to perform L2 risk assessments. After
running the main pipeline, the team works through Optro to confirm
applicability + ratings per L2. Their export is treated as authoritative —
overrides flow into transformed_df, replacing tool-derived status/ratings.

All-or-nothing per entity: if an entity has *some* L2s submitted in Optro
but not all, that entity's overrides are NOT applied (avoids the
"half-decisions" confusion). A WARNING lists incompletely-covered entities
so the user can chase down the missing entries.

Conflict detection: when the team marks an L2 as Not Applicable in Optro
but tool signals (open evidence + applicability flags + cross-boundary
keywords) suggest the L2 may apply, the conflict surfaces in
Control Signals so the team can reconcile their own contradiction.
"""
from __future__ import annotations

import logging

import pandas as pd

from risk_taxonomy_transformer.config import L2_TO_L1
from risk_taxonomy_transformer.constants import Method, Status

logger = logging.getLogger(__name__)


# Map of "applicability flags that suggest this L2 should apply" — used by
# conflict detection. Each entry is (column_name, signal_label).
_APPLICABILITY_SIGNAL_COLUMNS = [
    ("app_flag", "IT applications listed for entity"),
    ("tp_flag", "Third-party engagements listed for entity"),
    ("model_flag", "Models listed for entity"),
    ("aux_flag", "Listed as auxiliary risk in legacy entity data"),
    ("core_flag", "Listed as core risk dimension in legacy entity data"),
    ("cross_boundary_flag", "Cross-boundary keyword signals from other pillars"),
]


def assess_optro_coverage(
    transformed_df: pd.DataFrame,
    optro_coverage: dict[str, set[str]],
) -> tuple[set[str], set[str]]:
    """Determine which entities have full Optro coverage and which are partial.

    Returns:
        (fully_covered_entities, partially_covered_entities)
    """
    if not optro_coverage:
        return set(), set()

    expected_l2s = set(L2_TO_L1.keys())
    fully_covered: set[str] = set()
    partially_covered: set[str] = set()

    for eid, submitted in optro_coverage.items():
        # Only require coverage of L2s that exist in this entity's transformed_df
        # (some L2s may be filtered earlier — e.g., true_gap_fill rows).
        entity_rows = transformed_df[transformed_df["entity_id"].astype(str) == eid]
        entity_l2s = set(entity_rows["new_l2"].dropna().astype(str).unique())
        # Intersect with the canonical set so noise doesn't force false-incomplete
        entity_l2s = entity_l2s & expected_l2s

        missing = entity_l2s - submitted
        if missing:
            partially_covered.add(eid)
            logger.warning(
                f"  Optro coverage incomplete for entity {eid}: "
                f"{len(missing)} of {len(entity_l2s)} L2s missing — "
                f"{sorted(missing)}"
            )
        else:
            fully_covered.add(eid)

    if fully_covered:
        logger.info(f"  Optro coverage complete for {len(fully_covered)} entities")
    if partially_covered:
        logger.warning(
            f"  Optro coverage incomplete for {len(partially_covered)} entities — "
            "their overrides will NOT be applied (avoids mixing tool + team "
            "decisions for the same entity)"
        )

    return fully_covered, partially_covered


def apply_optro_overrides(
    transformed_df: pd.DataFrame,
    optro_overrides: dict[tuple[str, str], dict],
    fully_covered_entities: set[str],
) -> pd.DataFrame:
    """Apply Optro overrides to transformed_df rows for fully-covered entities.

    Replaces method, ratings (if applicable), and applicability marker on each
    row. Adds an `optro_override` column flagging which rows came from Optro.

    Rationale text is preserved separately on the row for downstream Decision
    Basis prose.
    """
    if "optro_override" not in transformed_df.columns:
        transformed_df["optro_override"] = ""
    if "optro_rationale" not in transformed_df.columns:
        transformed_df["optro_rationale"] = ""

    if not optro_overrides or not fully_covered_entities:
        return transformed_df

    applied = 0
    for idx, row in transformed_df.iterrows():
        eid = str(row.get("entity_id", "")).strip()
        l2 = row.get("new_l2", "")
        if eid not in fully_covered_entities:
            continue
        entry = optro_overrides.get((eid, l2))
        if not entry:
            continue

        if entry["applicability"] == "applicable":
            transformed_df.at[idx, "method"] = Method.OPTRO_CONFIRMED
            transformed_df.at[idx, "confidence"] = "high"
            transformed_df.at[idx, "needs_review"] = False
            transformed_df.at[idx, "likelihood"] = entry.get("likelihood")
            transformed_df.at[idx, "impact_financial"] = entry.get("impact_financial")
            transformed_df.at[idx, "impact_reputational"] = entry.get("impact_reputational")
            transformed_df.at[idx, "impact_consumer_harm"] = entry.get("impact_consumer_harm")
            transformed_df.at[idx, "impact_regulatory"] = entry.get("impact_regulatory")
            # Override the composite rating directly with the team's call.
            # The dimensions remain on the row for traceability but the team's
            # risk_rating is authoritative — don't recompute via the matrix.
            if entry.get("risk_rating"):
                transformed_df.at[idx, "inherent_risk_rating_label"] = entry["risk_rating"]
            transformed_df.at[idx, "optro_override"] = (
                f"Confirmed Applicable ({entry['risk_rating']})"
                if entry.get("risk_rating") else "Confirmed Applicable"
            )
        else:  # not_applicable
            transformed_df.at[idx, "method"] = Method.OPTRO_CONFIRMED_NA
            transformed_df.at[idx, "confidence"] = "high"
            transformed_df.at[idx, "needs_review"] = False
            transformed_df.at[idx, "likelihood"] = None
            transformed_df.at[idx, "impact_financial"] = None
            transformed_df.at[idx, "impact_reputational"] = None
            transformed_df.at[idx, "impact_consumer_harm"] = None
            transformed_df.at[idx, "impact_regulatory"] = None
            transformed_df.at[idx, "inherent_risk_rating_label"] = ""
            transformed_df.at[idx, "optro_override"] = "Confirmed Not Applicable"

        rationale = entry.get("team_rationale", "")
        if rationale and rationale.lower() not in ("nan", "none"):
            transformed_df.at[idx, "optro_rationale"] = rationale
        applied += 1

    if applied:
        logger.info(f"  Applied Optro overrides to {applied} rows")
    return transformed_df


def detect_optro_conflicts(transformed_df: pd.DataFrame) -> pd.DataFrame:
    """For each row marked Not Applicable in Optro, scan the row's own
    signals for evidence the L2 might actually apply. If any signal fires,
    append a conflict message to a new `optro_conflict` column.

    Signals checked:
      - Impact of Issues — open evidence (IAG findings, OREs, PRSA, RAPs)
      - app_flag, tp_flag, model_flag — entity has IT/TP/models listed
      - aux_flag, core_flag — L2 listed as auxiliary or core dimension
      - cross_boundary_flag — keywords for L2 in other pillars' rationale

    The conflict text is appended to Control Signals downstream so it's loud
    in the audit leader's view.
    """
    if "optro_conflict" not in transformed_df.columns:
        transformed_df["optro_conflict"] = ""

    if "optro_override" not in transformed_df.columns:
        return transformed_df

    fired = 0
    for idx, row in transformed_df.iterrows():
        if row.get("optro_override") != "Confirmed Not Applicable":
            continue
        signals = []

        # Open evidence (impact_of_issues has "Open items:" prefix when items exist)
        ioi = str(row.get("impact_of_issues", "") or "")
        if ioi and ioi.strip().lower() not in ("", "no open items", "nan", "none"):
            # Extract the summary line for compact conflict messaging
            first_line = ioi.split("\n", 1)[0].strip()
            signals.append(first_line)

        # Flag-based signals
        for col, label in _APPLICABILITY_SIGNAL_COLUMNS:
            val = row.get(col)
            if val and str(val).strip().lower() not in ("", "false", "nan", "none"):
                # The flag columns hold either booleans or text; treat any
                # non-empty truthy value as "fired"
                if isinstance(val, bool):
                    if val:
                        signals.append(label)
                else:
                    signals.append(label)

        if signals:
            l2 = row.get("new_l2", "this L2")
            conflict = (
                f"⚠ Conflict: Audit team marked {l2} as Not Applicable in Optro, "
                f"but the following signals suggest it may apply:\n"
                + "\n".join(f"  • {s}" for s in signals)
            )
            transformed_df.at[idx, "optro_conflict"] = conflict
            fired += 1

    if fired:
        logger.info(f"  Optro conflicts detected on {fired} rows")
    return transformed_df
