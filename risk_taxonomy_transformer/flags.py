"""
Flag functions for the Risk Taxonomy Transformer.

Flags control contradictions, application applicability, auxiliary risks,
and cross-boundary signals on the transformed data.
"""

from __future__ import annotations

import logging

import pandas as pd

from risk_taxonomy_transformer.config import (
    CROSSWALK_CONFIG,
    KEYWORD_MAP,
    get_app_cols,
    get_aux_cols,
    get_config,
)
from risk_taxonomy_transformer.normalization import normalize_l2_name

logger = logging.getLogger(__name__)

# Which L2s are flagged by which application/engagement columns
_APP_L2_MAP = {
    "Technology": ("primary_it", "secondary_it"),
    "Data": ("primary_it", "secondary_it"),
    "Information and Cyber Security": ("primary_it", "secondary_it"),
    "Third Party": ("primary_tp", "secondary_tp"),
}

# Label lookup for app column keys (Phase 5: replaces 4 elif branches)
_APP_COL_LABELS = {
    "primary_it": "Primary application mapped to entity",
    "secondary_it": "Secondary application related to entity",
    "primary_tp": "Primary third party engagement mapped to entity",
    "secondary_tp": "Secondary third party engagement related to entity",
}


def _parse_control_level(baseline: str) -> int | None:
    """Extract a numeric control level from the control_effectiveness_baseline text.

    Returns 1 (Well Controlled) through 4 (Poorly Controlled), or None.
    """
    if not baseline or str(baseline).strip().lower() in ("", "nan", "none",
                                                          "no engagement rating available"):
        return None
    bl = str(baseline).lower()
    if bl.startswith("well controlled"):
        return 1
    if bl.startswith("moderately controlled"):
        return 2
    if bl.startswith("inadequately controlled"):
        return 3
    if bl.startswith("poorly controlled"):
        return 4
    return None


def flag_control_contradictions(transformed_df: pd.DataFrame, findings_index: dict) -> pd.DataFrame:
    """Flag rows where control rating contradicts open findings.

    Adds a 'control_flag' column with human-readable warnings.
    """
    if not findings_index:
        transformed_df["control_flag"] = ""
        return transformed_df

    flags = []
    for _, row in transformed_df.iterrows():
        eid = str(row.get("entity_id", ""))
        l2 = row.get("new_l2", "")
        control_eff = _parse_control_level(
            row.get("control_effectiveness_baseline", ""))

        entity_findings = findings_index.get(eid, {})
        l2_findings = entity_findings.get(l2, [])

        # Active findings -- exclude Closed, Cancelled, and Not Started
        open_findings = [
            f for f in l2_findings
            if str(f.get("status", "")).strip().lower()
            in ("open", "in validation", "in sustainability")
        ]

        if not open_findings or control_eff is None:
            flags.append("")
            continue

        # Determine which findings qualify for a flag
        control_labels = {1: "Well Controlled", 2: "Moderately Controlled",
                          3: "Inadequately Controlled", 4: "Poorly Controlled"}
        control_label = control_labels.get(control_eff, "")

        qualifying = []
        for f in open_findings:
            sev = f.get("severity", "")
            iid = f.get("issue_id", "")
            if control_eff == 1:
                qualifying.append((iid, sev))
            elif control_eff == 2 and str(sev).strip().lower() in ("high", "critical"):
                qualifying.append((iid, sev))

        if not qualifying:
            flags.append("")
            continue

        if len(qualifying) == 1:
            iid, sev = qualifying[0]
            title = next(
                (f.get("issue_title", "")[:80] for f in open_findings
                 if f.get("issue_id", "") == iid), ""
            )
            flag_str = (f"Open {sev} issue ({iid}: {title}) \u2014 "
                        f"review whether {control_label} rating reflects current state")
        else:
            shown = qualifying[:3]
            id_sev_parts = [f"{iid} {sev}" for iid, sev in shown]
            overflow = len(qualifying) - 3
            if overflow > 0:
                id_sev_parts.append(f"+{overflow} more")
            flag_str = (f"{len(qualifying)} open issues ({', '.join(id_sev_parts)}) \u2014 "
                        f"review whether {control_label} rating reflects current state")

        flags.append(flag_str)

    transformed_df["control_flag"] = flags
    return transformed_df


def flag_application_applicability(
    transformed_df: pd.DataFrame,
    legacy_df: pd.DataFrame,
    entity_id_col: str,
) -> pd.DataFrame:
    """Flag L2 risks as potentially applicable when IT applications or
    third party engagements are tagged to the entity.

    Adds an 'app_flag' column with a recommendation message.
    """
    _APP_COLS = get_app_cols()

    # Check which app columns exist in the legacy data
    available_cols = {key: col for key, col in _APP_COLS.items() if col in legacy_df.columns}
    if not available_cols:
        transformed_df["app_flag"] = ""
        return transformed_df

    # Build lookup: {entity_id: {col_key: [list of IDs]}}
    entity_apps = {}
    for _, row in legacy_df.iterrows():
        eid = str(row[entity_id_col]).strip()
        entity_apps[eid] = {}
        for key, col in available_cols.items():
            raw = str(row.get(col, ""))
            if raw and raw not in ("", "nan", "None"):
                # Split on newlines (alt+enter in Excel) and semicolons
                ids = [v.strip() for v in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
                       if v.strip() and v.strip() != "nan"]
                entity_apps[eid][key] = ids
            else:
                entity_apps[eid][key] = []

    flags = []
    for _, row in transformed_df.iterrows():
        eid = str(row.get("entity_id", ""))
        l2 = row.get("new_l2", "")

        app_col_keys = _APP_L2_MAP.get(l2)
        if not app_col_keys:
            flags.append("")
            continue

        apps = entity_apps.get(eid, {})
        flag_parts = []

        for col_key in app_col_keys:
            ids = apps.get(col_key, [])
            if ids:
                id_list = ", ".join(ids[:5])
                if len(ids) > 5:
                    id_list += f" (+{len(ids) - 5} more)"

                # Use label dict lookup instead of elif chain
                label = _APP_COL_LABELS.get(col_key, col_key)
                flag_parts.append(
                    f"{label} ({id_list}) \u2014 "
                    f"consider this risk may be applicable"
                )

        flags.append(" | ".join(flag_parts))

    transformed_df["app_flag"] = flags

    flagged = sum(1 for f in flags if f)
    # Extract set of flagged entity IDs into a named variable
    entities_with_apps = {
        eid for eid, app_data in entity_apps.items() if any(app_data.values())
    }
    flagged_entity_ids = {
        str(row.get("entity_id"))
        for _, row in transformed_df.iterrows()
        if str(row.get("entity_id")) in entities_with_apps
    }
    logger.info(f"  Application/engagement flags: {flagged} rows flagged across "
                f"{len(flagged_entity_ids)} entities")

    return transformed_df


def flag_auxiliary_risks(
    transformed_df: pd.DataFrame,
    legacy_df: pd.DataFrame,
    entity_id_col: str,
) -> pd.DataFrame:
    """Flag L2 risks as potentially applicable when they appear in the entity's
    auxiliary risk dimensions columns.

    Adds an 'aux_flag' column with a recommendation message.
    """
    _AUX_COLS = get_aux_cols()

    # Check which aux columns exist
    available_cols = [c for c in _AUX_COLS if c in legacy_df.columns]
    if not available_cols:
        transformed_df["aux_flag"] = ""
        return transformed_df

    # Build lookup: {entity_id: set of normalized L2 names from auxiliary columns}
    entity_aux = {}
    for _, row in legacy_df.iterrows():
        eid = str(row[entity_id_col]).strip()
        aux_l2s = {}  # {l2_name: source_column}
        for col in available_cols:
            raw = str(row.get(col, ""))
            if raw and raw not in ("", "nan", "None"):
                # Split on newlines and commas
                entries = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
                for entry in entries:
                    entry = entry.strip()
                    if not entry:
                        continue
                    normalized = normalize_l2_name(entry)
                    if normalized and normalized not in aux_l2s:
                        aux_l2s[normalized] = col
        entity_aux[eid] = aux_l2s

    flags = []
    for _, row in transformed_df.iterrows():
        eid = str(row.get("entity_id", ""))
        l2 = row.get("new_l2", "")

        aux = entity_aux.get(eid, {})
        if l2 in aux:
            source = aux[l2]
            short_source = "AXP" if "AXP" in source else "AENB"
            flags.append(
                f"Listed as auxiliary risk in legacy entity data ({short_source}) \u2014 "
                f"consider this risk may be applicable"
            )
        else:
            flags.append("")

    transformed_df["aux_flag"] = flags

    flagged = sum(1 for f in flags if f)
    entities_flagged = len({eid for eid, aux in entity_aux.items() if aux})
    logger.info(f"  Auxiliary risk flags: {flagged} rows flagged across {entities_flagged} entities")

    return transformed_df


def _format_cross_boundary_flags(pillar_signals: dict) -> str:
    """Format cross-boundary signal data for a single (entity, L2) pair into a flag string.

    Args:
        pillar_signals: {pillar: {"rationale_hits": [...], "sub_risk_hits": [...]}}

    Returns:
        Formatted flag string or empty string.
    """
    parts = []
    for pillar, data in pillar_signals.items():
        rat_hits = data["rationale_hits"]
        sub_hits = data["sub_risk_hits"]

        if rat_hits and sub_hits:
            # Combined rationale + sub-risk hit
            rat_kws = "'" + "', '".join(sorted(set(rat_hits))) + "'"
            sub_parts = []
            for rid, desc, hits in sub_hits:
                sub_kws = "'" + "', '".join(sorted(set(hits))) + "'"
                sub_parts.append(f"sub-risk {rid} ({sub_kws})")
            sub_str = " and ".join(sub_parts)
            parts.append(
                f"Referenced in {pillar} pillar rationale ({rat_kws}) and "
                f"{sub_str} \u2014 outside normal mapping. "
                f"Consider whether this L2 applies to this entity."
            )
        elif rat_hits:
            rat_kws = "'" + "', '".join(sorted(set(rat_hits))) + "'"
            parts.append(
                f"Referenced in {pillar} pillar rationale ({rat_kws}) \u2014 "
                f"outside normal mapping. Consider whether this L2 applies to this entity."
            )
        elif sub_hits:
            for rid, desc, hits in sub_hits:
                sub_kws = "'" + "', '".join(sorted(set(hits))) + "'"
                parts.append(
                    f"Referenced in {pillar} sub-risk {rid} ({sub_kws}) \u2014 "
                    f"outside normal mapping. Consider whether this L2 applies to this entity."
                )

    return " | ".join(parts) if parts else ""


def flag_cross_boundary_signals(
    transformed_df: pd.DataFrame,
    legacy_df: pd.DataFrame,
    pillar_columns: dict,
    entity_id_col: str,
    sub_risk_index: dict | None = None,
) -> pd.DataFrame:
    """Scan every pillar's rationale and sub-risks against every L2's keywords,
    flagging hits that fall outside the crosswalk-defined mappings.

    These are informational signals -- they don't change Status, ratings, or confidence.
    """
    _CFG = get_config()

    # Check config
    cb_config = _CFG.get("cross_boundary_scanning", {})
    if not cb_config.get("enabled", True):
        transformed_df["cross_boundary_flag"] = ""
        logger.info("  Cross-boundary scanning disabled in config")
        return transformed_df

    scan_rationale = cb_config.get("scan_rationale", True)
    scan_sub_risks = cb_config.get("scan_sub_risks", True)
    min_hits = cb_config.get("min_hits_per_pillar", 2)

    # Build the set of expected (pillar, L2) pairs from the crosswalk
    expected_pairs = set()
    for pillar, config in CROSSWALK_CONFIG.items():
        mt = config.get("mapping_type", "")
        if mt == "direct":
            expected_pairs.add((pillar, config["target_l2"]))
        elif mt == "multi":
            for target in config["targets"]:
                expected_pairs.add((pillar, target["l2"]))
        elif mt == "overlay":
            for l2 in config.get("target_l2s", []):
                expected_pairs.add((pillar, l2))

    # Build signals: {(entity_id, l2): {pillar: {"rationale_hits": [], "sub_risk_hits": []}}}
    signals = {}

    for _, legacy_row in legacy_df.iterrows():
        eid = str(legacy_row[entity_id_col]).strip()

        for pillar, cols in pillar_columns.items():
            # --- Scan rationale text ---
            if scan_rationale and cols.get("rationale"):
                rationale = legacy_row.get(cols["rationale"], "")
                if not rationale or pd.isna(rationale):
                    continue
                rationale_lower = str(rationale).lower()
                if rationale_lower in ("", "nan", "n/a", "not applicable"):
                    continue

                for l2_name, keywords in KEYWORD_MAP.items():
                    if (pillar, l2_name) in expected_pairs:
                        continue  # expected mapping, not cross-boundary
                    hits = [kw for kw in keywords if kw in rationale_lower]
                    if hits:
                        key = (eid, l2_name)
                        if key not in signals:
                            signals[key] = {}
                        # Group by pillar
                        if pillar not in signals[key]:
                            signals[key][pillar] = {"rationale_hits": [], "sub_risk_hits": []}
                        signals[key][pillar]["rationale_hits"].extend(hits)

            # --- Scan sub-risk descriptions ---
            if scan_sub_risks and sub_risk_index:
                entity_subs = sub_risk_index.get(eid, {})
                sub_entries = entity_subs.get(pillar, [])

                for risk_id, desc in sub_entries:
                    desc = str(desc) if desc is not None else ""
                    if not desc or desc == "nan":
                        continue
                    desc_lower = desc.lower()

                    for l2_name, keywords in KEYWORD_MAP.items():
                        if (pillar, l2_name) in expected_pairs:
                            continue
                        hits = [kw for kw in keywords if kw in desc_lower]
                        if hits:
                            key = (eid, l2_name)
                            if key not in signals:
                                signals[key] = {}
                            if pillar not in signals[key]:
                                signals[key][pillar] = {"rationale_hits": [], "sub_risk_hits": []}
                            truncated = desc[:80] + "..." if len(desc) > 80 else desc
                            signals[key][pillar]["sub_risk_hits"].append(
                                (risk_id, truncated, hits)
                            )

    # Format signals into plain-language flags per entity+L2
    formatted = {}  # {(eid, l2): flag_string}
    for (eid, l2), pillar_signals in signals.items():
        # Apply minimum threshold per pillar -- filter out pillars below threshold
        filtered_signals = {}
        for pillar, data in pillar_signals.items():
            rat_hits = data["rationale_hits"]
            sub_hits = data["sub_risk_hits"]
            total_hits = len(rat_hits) + sum(len(h) for _, _, h in sub_hits)
            if total_hits >= min_hits:
                filtered_signals[pillar] = data

        if filtered_signals:
            flag_str = _format_cross_boundary_flags(filtered_signals)
            if flag_str:
                formatted[(eid, l2)] = flag_str

    # Attach to transformed_df
    flag_col = []
    for _, row in transformed_df.iterrows():
        eid = str(row.get("entity_id", ""))
        l2 = row.get("new_l2", "")
        flag_col.append(formatted.get((eid, l2), ""))
    transformed_df["cross_boundary_flag"] = flag_col

    # Logging summary
    total_flags = sum(1 for f in flag_col if f)
    entities_with_flags = len({eid for (eid, _) in formatted})
    logger.info(f"  Cross-boundary flags: {total_flags} rows flagged across {entities_with_flags} entities")

    if formatted:
        # Top flagged L2s
        l2_counts = {}
        pillar_counts = {}
        for (eid, l2), pillar_signals in signals.items():
            l2_counts[l2] = l2_counts.get(l2, set())
            l2_counts[l2].add(eid)
            for pillar in pillar_signals:
                pillar_counts[pillar] = pillar_counts.get(pillar, 0) + 1

        top_l2s = sorted(l2_counts.items(), key=lambda x: len(x[1]), reverse=True)[:5]
        logger.info("  Top cross-boundary L2s: " +
                     ", ".join(f"{l2}: {len(eids)} entities" for l2, eids in top_l2s))

        top_pillars = sorted(pillar_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        logger.info("  Top source pillars: " +
                     ", ".join(f"{p}: {c} flags" for p, c in top_pillars))

    return transformed_df
