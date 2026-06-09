"""
Data ingestion functions for the Risk Taxonomy Transformer.

Handles reading legacy data, key risk descriptions, LLM overrides, findings,
ORE mappings, enterprise findings, and RCO overrides from Excel/CSV files.
Also builds the nested lookup indexes used downstream.
"""

from __future__ import annotations

import logging
from collections import defaultdict

import pandas as pd

from risk_taxonomy_transformer.config import CROSSWALK_CONFIG, L2_TO_L1
from risk_taxonomy_transformer.normalization import normalize_l2_name
from risk_taxonomy_transformer.utils import split_id_list

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core ingestion
# ---------------------------------------------------------------------------

def ingest_legacy_data(filepath: str, entity_id_col: str = "Audit Entity ID",
                       report_date_col: str | None = None) -> pd.DataFrame:
    """Read the legacy entity-level risk data from Excel or CSV.

    Expects a wide-format file with columns for each legacy pillar's rating,
    rationale, control assessment, and control rationale.

    If the data contains multiple rows per entity (one per historical audit
    report), pass ``report_date_col`` to deduplicate — only the row with the
    most recent report date is kept for each entity.
    """
    logger.info(f"Reading legacy data from {filepath}")
    if filepath.endswith(".csv"):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)
    logger.info(f"  Loaded {len(df)} rows, {len(df.columns)} columns")

    # Normalize column names: strip whitespace
    df.columns = [str(c).strip() for c in df.columns]

    # Deduplicate to one row per entity using the most recent report date
    if report_date_col and report_date_col in df.columns:
        pre_dedup = len(df)
        df[report_date_col] = pd.to_datetime(df[report_date_col], errors="coerce")
        df = df.sort_values(report_date_col, ascending=False)
        df = df.drop_duplicates(subset=entity_id_col, keep="first")
        logger.info(f"  Deduplicated {pre_dedup} rows -> {len(df)} entities "
                     f"(kept most recent by '{report_date_col}')")

    logger.info(f"  {len(df)} audit entities after ingestion")
    return df


def ingest_crosswalk(filepath: str = None) -> dict:
    """Return the crosswalk config loaded from taxonomy_config.yaml.

    File-based crosswalk override is not yet implemented.
    Pass filepath=None to use the YAML-loaded CROSSWALK_CONFIG.
    """
    if filepath:
        raise NotImplementedError(
            f"File-based crosswalk parsing not yet implemented (got {filepath}). "
            "Use CROSSWALK_CONFIG or pass filepath=None."
        )
    return CROSSWALK_CONFIG


def ingest_key_risks(filepath: str, entity_id_col: str, legacy_l1_col: str,
                     risk_desc_col: str, risk_id_col: str = None,
                     rating_col: str = None,
                     key_apps_col: str = None,
                     key_tps_col: str = None,
                     kpa_id_col: str = None) -> pd.DataFrame:
    """Read key risk descriptions file.

    Expected columns (configure names in main()):
      - entity_id_col:  Audit Entity ID
      - risk_id_col:    Risk ID (optional, for traceability)
      - risk_desc_col:  Risk description text
      - legacy_l1_col:  Legacy L1 pillar(s), tab-separated if multiple
      - rating_col:     Inherent risk rating (optional, not used for scoring)
      - key_apps_col:   "KEY PRIMARY & SECONDARY IT APPLICATIONS" — per-key risk
                        list of app IDs flagged as key (optional; newline/sep.)
      - key_tps_col:    "KEY PRIMARY & SECONDARY THIRD PARTY ENGAGEMENT" —
                        per-key risk list of TP IDs flagged as key (optional).

    Returns DataFrame with one row per key risk, with legacy L1s exploded
    so each row maps to a single L1.
    """
    logger.info(f"Reading key risk descriptions from {filepath}")
    if filepath.endswith(".csv"):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)
    df.columns = [c.strip() for c in df.columns]
    logger.info(f"  Loaded {len(df)} key risk rows")

    # Rename to standard internal names
    col_map = {entity_id_col: "entity_id", risk_desc_col: "risk_description",
               legacy_l1_col: "legacy_l1_raw"}
    if risk_id_col:
        col_map[risk_id_col] = "risk_id"
    if rating_col:
        col_map[rating_col] = "key_risk_rating"
    if key_apps_col and key_apps_col in df.columns:
        col_map[key_apps_col] = "key_apps_raw"
    if key_tps_col and key_tps_col in df.columns:
        col_map[key_tps_col] = "key_tps_raw"
    if kpa_id_col and kpa_id_col in df.columns:
        col_map[kpa_id_col] = "kpa_id"
    df = df.rename(columns=col_map)

    # Ensure entity_id is string
    df["entity_id"] = df["entity_id"].astype(str).str.strip()

    # Explode multi-value L1 pillars so each row has one L1
    # Excel cells may use newlines, tabs, semicolons, or pipes as separators
    df["legacy_l1_list"] = df["legacy_l1_raw"].astype(str).str.split(r"\n|\t|;|\|")
    df = df.explode("legacy_l1_list")
    df["legacy_l1"] = df["legacy_l1_list"].str.strip()
    df = df[~df["legacy_l1"].isin(["", "nan"])]  # drop empty and NaN from splitting
    df = df.drop(columns=["legacy_l1_list"])

    # Clean up description text
    df["risk_description"] = df["risk_description"].astype(str).str.strip()

    logger.info(f"  After L1 explosion: {len(df)} key risk-to-L1 rows")
    logger.info(f"  Unique entities with key risks: {df['entity_id'].nunique()}")

    return df


# ---------------------------------------------------------------------------
# Index builders
# ---------------------------------------------------------------------------

def _build_nested_index(df: pd.DataFrame, key1_col: str, key2_col: str,
                        value_fn) -> dict:
    """Build a two-level nested index: {key1: {key2: [values]}}.

    value_fn receives each row and returns the value to append.
    """
    index = defaultdict(lambda: defaultdict(list))
    for _, row in df.iterrows():
        index[row[key1_col]][row[key2_col]].append(value_fn(row))
    # Convert back to plain dicts for consumers that check `key in index`
    return {k1: dict(v) for k1, v in index.items()}


def build_key_inventory(key_risks_df: pd.DataFrame, legacy_df: pd.DataFrame,
                        entity_id_col: str, app_cols: dict) -> dict:
    """Aggregate the "key" app/TP IDs per entity from key risk rows.

    Per procedure: an app or third party is "key" for an entity if it's listed
    in ANY of that entity's key risk KEY columns. Non-key items do not drive
    risk for the entity.

    Returns:
        {entity_id: {
            "key_apps": set[str],           # all IDs flagged key across key risks
            "key_tps":  set[str],
            "orphan_apps": set[str],        # key IDs not in entity inventory
            "orphan_tps":  set[str],
            "key_apps_kpa": dict[str, set], # {app_id: set of KPA IDs where key}
            "key_tps_kpa":  dict[str, set], # {tp_id: set of KPA IDs where key}
        }}
    """
    # Entity inventory (from legacy_df) — the denominator for orphan detection
    primary_it_col = app_cols.get("primary_it", "")
    secondary_it_col = app_cols.get("secondary_it", "")
    primary_tp_col = app_cols.get("primary_tp", "")
    secondary_tp_col = app_cols.get("secondary_tp", "")

    entity_inv = {}
    if legacy_df is not None and entity_id_col in legacy_df.columns:
        for _, row in legacy_df.iterrows():
            eid = str(row[entity_id_col]).strip()
            apps = set(split_id_list(row.get(primary_it_col, "")))
            apps.update(split_id_list(row.get(secondary_it_col, "")))
            tps = set(split_id_list(row.get(primary_tp_col, "")))
            tps.update(split_id_list(row.get(secondary_tp_col, "")))
            entity_inv[eid] = {"apps": apps, "tps": tps}

    # Aggregate key sets from key risks
    result = {}
    if key_risks_df is None or len(key_risks_df) == 0:
        return result

    has_key_apps = "key_apps_raw" in key_risks_df.columns
    has_key_tps = "key_tps_raw" in key_risks_df.columns
    if not (has_key_apps or has_key_tps):
        return result

    has_kpa = "kpa_id" in key_risks_df.columns

    for eid, group in key_risks_df.groupby("entity_id"):
        eid_str = str(eid).strip()
        key_apps = set()
        key_tps = set()
        key_apps_kpa = {}  # app_id -> set(kpa_ids)
        key_tps_kpa = {}
        # Deduplicate by risk_id so a key risk exploded across multiple legacy
        # L1s contributes its KPA only once.
        seen_risk_ids = set()
        for _, row in group.iterrows():
            rid = str(row.get("risk_id", "")).strip()
            if rid and rid in seen_risk_ids:
                continue
            if rid:
                seen_risk_ids.add(rid)
            kpa = str(row.get("kpa_id", "")).strip() if has_kpa else ""
            if kpa.lower() in ("", "nan", "none"):
                kpa = ""
            if has_key_apps:
                for app_id in split_id_list(row.get("key_apps_raw", "")):
                    key_apps.add(app_id)
                    if kpa:
                        key_apps_kpa.setdefault(app_id, set()).add(kpa)
            if has_key_tps:
                for tp_id in split_id_list(row.get("key_tps_raw", "")):
                    key_tps.add(tp_id)
                    if kpa:
                        key_tps_kpa.setdefault(tp_id, set()).add(kpa)

        inv = entity_inv.get(eid_str, {"apps": set(), "tps": set()})
        orphan_apps = key_apps - inv["apps"]
        orphan_tps = key_tps - inv["tps"]

        result[eid_str] = {
            "key_apps": key_apps,
            "key_tps": key_tps,
            "orphan_apps": orphan_apps,
            "orphan_tps": orphan_tps,
            "key_apps_kpa": key_apps_kpa,
            "key_tps_kpa": key_tps_kpa,
        }

    total_key_apps = sum(len(r["key_apps"]) for r in result.values())
    total_key_tps = sum(len(r["key_tps"]) for r in result.values())
    total_orphans = sum(len(r["orphan_apps"]) + len(r["orphan_tps"])
                         for r in result.values())
    logger.info(
        f"  Key inventory: {total_key_apps} key apps, {total_key_tps} key TPs "
        f"across {len(result)} entities ({total_orphans} orphan IDs not in entity inventory)"
    )
    return result


def build_key_risk_index(key_risks_df: pd.DataFrame) -> dict:
    """Build lookup: {entity_id: {legacy_pillar: [list of risk descriptions]}}.

    This enables fast lookup during entity transformation.
    """
    index = _build_nested_index(
        key_risks_df, "entity_id", "legacy_l1",
        value_fn=lambda row: (
            str(row.get("risk_id", "")),
            row["risk_description"],
        ),
    )

    # Diagnostic: show which key risk L1 values match crosswalk keys
    all_l1s_in_subrisk = {l1 for eid_map in index.values() for l1 in eid_map
                          if isinstance(l1, str)}
    crosswalk_keys = set(CROSSWALK_CONFIG.keys())
    matched = all_l1s_in_subrisk & crosswalk_keys
    unmatched = all_l1s_in_subrisk - crosswalk_keys
    unused = crosswalk_keys - all_l1s_in_subrisk
    logger.info(f"  Sub-risk L1 values found: {sorted(all_l1s_in_subrisk)}")
    logger.info(f"  Matched to crosswalk keys: {sorted(matched)}")
    if unmatched:
        logger.warning(f"  Sub-risk L1s NOT in crosswalk (will be ignored): {sorted(unmatched)}")
    if unused:
        logger.info(f"  Crosswalk keys with NO key risks: {sorted(unused)}")

    return index


def load_overrides(filepath: str) -> dict:
    """Load LLM-classified overrides from Excel/CSV.

    Supports two formats:
      Legacy format (columns: entity_id, source_legacy_pillar, classified_l2, llm_confidence)
      New format (columns: entity_id, source_legacy_pillar, classified_l2, determination)

    Returns dict: {(entity_id, pillar, l2): {"determination": str, "confidence": str}}
    where determination is "applicable" or "not_applicable".
    """
    logger.info(f"Loading LLM overrides from {filepath}")

    if filepath.endswith(".csv"):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)

    df.columns = [str(c).strip() for c in df.columns]
    df["entity_id"] = df["entity_id"].astype(str).str.strip()
    df["source_legacy_pillar"] = df["source_legacy_pillar"].astype(str).str.strip()
    df["classified_l2"] = df["classified_l2"].astype(str).str.strip()

    has_determination = "determination" in df.columns
    has_reasoning = "reasoning" in df.columns

    overrides = {}
    accepted_count = 0
    applicable_count = 0
    na_count = 0
    skipped = 0

    for _, row in df.iterrows():
        l2 = row["classified_l2"]
        # Normalize L2 name
        normalized = normalize_l2_name(l2) if l2 not in L2_TO_L1 else l2
        if normalized is None or normalized not in L2_TO_L1:
            logger.warning(f"  Override skipped: '{l2}' not in taxonomy "
                        f"(entity={row['entity_id']}, pillar={row['source_legacy_pillar']})")
            skipped += 1
            continue

        key = (row["entity_id"], row["source_legacy_pillar"], normalized)

        if has_determination:
            determination = str(row.get("determination", "")).strip().lower()
            if determination not in ("applicable", "not_applicable"):
                logger.warning(f"  Override skipped: invalid determination "
                            f"'{determination}' (entity={row['entity_id']}, "
                            f"pillar={row['source_legacy_pillar']}, l2={normalized})")
                skipped += 1
                continue
            confidence = "high"
        else:
            # Legacy format -- treat as applicable
            determination = "applicable"
            confidence = str(row.get("llm_confidence", "high")).strip().lower()
            if confidence not in ("high", "medium", "low"):
                confidence = "high"

        # Read reasoning if column exists, default to empty string for backward compat
        reasoning = ""
        if has_reasoning:
            raw_reasoning = row.get("reasoning", "")
            if raw_reasoning is not None and not (isinstance(raw_reasoning, float) and pd.isna(raw_reasoning)):
                reasoning = str(raw_reasoning).strip()

        overrides[key] = {"determination": determination, "confidence": confidence,
                          "reasoning": reasoning}
        accepted_count += 1
        if determination == "applicable":
            applicable_count += 1
        else:
            na_count += 1

    logger.info(f"  Loaded {accepted_count} overrides ({applicable_count} applicable, "
                f"{na_count} not applicable), skipped {skipped} invalid")
    return overrides


def ingest_findings(filepath: str, column_name_map: dict) -> tuple[pd.DataFrame, dict, pd.DataFrame, str]:
    """Read findings/issues data.

    Expected columns (configure names via column_name_map):
      entity_id, issue_id, l2_risk, severity, status, issue_title, remediation_date

    Returns:
        (findings_df, unmapped_findings, blank_ae_orphans_df, source_filename) where:
        - unmapped_findings: {entity_id: [{"issue_id": ..., "severity": ..., "raw_l2": ...}, ...]}
        - blank_ae_orphans_df: DataFrame of approved findings whose entity_id is
          blank/missing — these can't be attached to an AE view, so they're
          captured for surfacing in the Upstream Tagging Gaps tab.
        - source_filename: basename of the input file, used to populate the
          Source File column on the orphans tab.
    """
    from pathlib import Path as _Path

    logger.info(f"Reading findings from {filepath}")
    if filepath.endswith(".csv"):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)
    df.columns = [c.strip() for c in df.columns]
    source_filename = _Path(filepath).name

    rename = {}
    for internal, actual in column_name_map.items():
        if actual and actual in df.columns:
            rename[actual] = internal
    df = df.rename(columns=rename)

    # Check required columns
    if "entity_id" not in df.columns:
        raise ValueError("Findings file missing required column: entity_id "
                         f"(mapped from '{column_name_map.get('entity_id', '?')}')")
    if "l2_risk" not in df.columns:
        raise ValueError("Findings file missing required column: l2_risk "
                         f"(mapped from '{column_name_map.get('l2_risk', '?')}')")

    df["entity_id"] = df["entity_id"].astype(str).str.strip()

    # Only include approved findings -- filter out drafts/in-review
    # The approval_status column name comes from config (defaults to "Finding Approval Status")
    approval_col = column_name_map.get("approval_status", "Finding Approval Status")
    if approval_col and approval_col in df.columns:
        pre_filter = len(df)
        df = df[df[approval_col].astype(str).str.strip() == "Approved"]
        logger.info(f"  Filtered to Approved findings: {len(df)} of {pre_filter}")

    # Capture approved findings with blank entity_id as orphans for the
    # Upstream Tagging Gaps tab. These can't be attached to a per-AE view.
    blank_ae_mask = df["entity_id"].isin(["", "nan", "None", "none"])
    blank_ae_orphans = df[blank_ae_mask].copy() if blank_ae_mask.any() else pd.DataFrame()
    if not blank_ae_orphans.empty:
        logger.info(f"  Captured {len(blank_ae_orphans)} findings with blank entity_id "
                    f"as orphans (Upstream Tagging Gaps)")
    df = df[~blank_ae_mask]

    # Exclude findings with blank severity -- likely incomplete, shouldn't confirm applicability
    if "severity" in df.columns:
        blank_sev = df["severity"].isna() | (df["severity"].astype(str).str.strip() == "")
        if blank_sev.any():
            logger.info(f"  Excluded {blank_sev.sum()} findings with blank severity")
            df = df[~blank_sev]

    # Explode multi-value L2 risk cells (alt+enter in Excel = newline separator)
    df["l2_risk"] = df["l2_risk"].astype(str).str.split(r"\n|\r\n|\r")
    df = df.explode("l2_risk")
    df["l2_risk"] = df["l2_risk"].str.strip()
    df = df[df["l2_risk"] != ""]

    # Normalize L2 names (strip L1 prefix, resolve aliases, drop unmappable)
    raw_l2 = df["l2_risk"].copy()
    df["l2_risk"] = df["l2_risk"].apply(normalize_l2_name)
    pre_norm = len(df)
    unmapped_mask = df["l2_risk"].isna()

    # Capture unmapped findings per entity before dropping them
    unmapped_findings: dict[str, list[dict]] = {}
    if unmapped_mask.any():
        unmapped_rows = df[unmapped_mask]
        for _, urow in unmapped_rows.iterrows():
            eid = str(urow["entity_id"]).strip()
            unmapped_findings.setdefault(eid, []).append({
                "issue_id": str(urow.get("issue_id", "")),
                "severity": str(urow.get("severity", "")),
                "raw_l2": str(raw_l2.loc[urow.name]),
            })

    df = df[~unmapped_mask]
    dropped = unmapped_mask.sum()
    if dropped > 0:
        dropped_values = raw_l2[unmapped_mask].value_counts()
        logger.info(f"  Dropped {dropped} findings with unmappable or blank L2 risk categories:")
        for val, count in dropped_values.items():
            logger.info(f"    '{val}': {count}")

    # Validate remaining L2 names match taxonomy. Anything that survived
    # normalization but isn't in L2_TO_L1 is a defensive drop — capture it
    # into unmapped_findings so it surfaces in the workbook + HTML banner
    # rather than being silently dropped.
    valid = df["l2_risk"].isin(L2_TO_L1)
    invalid_rows = df[~valid]
    if not invalid_rows.empty:
        invalid_l2s = invalid_rows["l2_risk"].unique()
        logger.warning(f"  Findings L2s NOT in taxonomy (captured as unmapped): {list(invalid_l2s)}")
        for _, urow in invalid_rows.iterrows():
            eid = str(urow["entity_id"]).strip()
            unmapped_findings.setdefault(eid, []).append({
                "issue_id": str(urow.get("issue_id", "")),
                "severity": str(urow.get("severity", "")),
                "raw_l2": str(urow["l2_risk"]),
            })
    df = df[valid]

    logger.info(f"  Loaded {len(df)} valid findings across {df['entity_id'].nunique()} entities")
    logger.info(f"  L2s covered by findings: {sorted(df['l2_risk'].unique())}")
    if unmapped_findings:
        total_unmapped = sum(len(v) for v in unmapped_findings.values())
        logger.info(f"  Unmapped findings captured: {total_unmapped} across {len(unmapped_findings)} entities")
    return df, unmapped_findings, blank_ae_orphans, source_filename


def build_findings_index(findings_df: pd.DataFrame) -> dict:
    """Build lookup: {entity_id: {l2_risk: [list of finding dicts]}}.

    Each finding dict: {issue_id, severity, status, issue_title, remediation_date}
    """
    def _finding_from_row(row):
        return {
            "issue_id": str(row.get("issue_id", "")),
            "severity": str(row.get("severity", "")),
            "status": str(row.get("status", "")),
            "issue_title": str(row.get("issue_title", "")),
            "remediation_date": str(row.get("remediation_date", "")),
        }

    index = _build_nested_index(findings_df, "entity_id", "l2_risk",
                                value_fn=_finding_from_row)

    total_findings = sum(len(fs) for eid_map in index.values() for fs in eid_map.values())
    logger.info(f"  Findings index built: {len(index)} entities, {total_findings} total findings")
    return index


def ingest_ore_mappings(filepath: str, confidence_filter: list[str] | None = None) -> tuple[pd.DataFrame, dict]:
    """Read ORE mapper output and filter to mapped statuses.

    The ore_mapper outputs a semicolon-separated 'Mapped L2s' column
    (one row per ORE). This function explodes that into one row per
    (entity_id, l2_risk) pair for downstream indexing.

    Returns:
        (ore_df, unmapped_dict). unmapped_dict is
        {entity_id: [{"source": "ore", "item_id": ..., "raw_l2": ...}, ...]}
        for ORE rows whose L2 name didn't normalize.
    """
    logger.info(f"Reading ORE mappings from {filepath}")
    df = pd.read_excel(filepath, sheet_name="All Mappings")
    df.columns = [c.strip() for c in df.columns]

    required = ["Event ID", "Audit Entity ID", "Mapping Status", "Mapped L2s"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"ORE mapping file missing columns: {missing}")

    # Filter to desired statuses
    if confidence_filter is None:
        confidence_filter = ["Suggested Match"]
    pre_filter = len(df)
    df = df[df["Mapping Status"].isin(confidence_filter)]
    logger.info(f"  Filtered to {len(df)} of {pre_filter} OREs (statuses: {confidence_filter})")

    # Explode semicolon-separated Mapped L2s into individual rows
    df["l2_risk"] = df["Mapped L2s"].str.split("; ")
    df = df.explode("l2_risk")
    df["l2_risk"] = df["l2_risk"].str.strip()
    df = df[df["l2_risk"] != ""]

    df = df.rename(columns={
        "Audit Entity ID": "entity_id",
        "Event ID": "event_id",
    })
    df["entity_id"] = df["entity_id"].astype(str).str.strip()
    raw_l2 = df["l2_risk"].copy()
    df["l2_risk"] = df["l2_risk"].apply(normalize_l2_name)
    unmapped_mask = df["l2_risk"].isna()

    # Capture unmapped rows so reviewers see what the mapper produced that
    # didn't reconcile to canonical L2s (alias drift, stale config, etc.).
    unmapped: dict[str, list[dict]] = {}
    if unmapped_mask.any():
        for _, urow in df[unmapped_mask].iterrows():
            eid = str(urow["entity_id"]).strip()
            unmapped.setdefault(eid, []).append({
                "source": "ore",
                "item_id": str(urow.get("event_id", "")),
                "raw_l2": str(raw_l2.loc[urow.name]),
            })
        dropped_values = raw_l2[unmapped_mask].value_counts()
        logger.info(f"  Dropped {unmapped_mask.sum()} ORE-L2 pairs with unmappable L2 names (captured as unmapped):")
        for val, count in dropped_values.items():
            logger.info(f"    '{val}': {count}")
    df = df[~unmapped_mask]

    logger.info(f"  Loaded {len(df)} ORE mappings across {df['entity_id'].nunique()} entities")
    return df, unmapped


def build_ore_index(ore_df: pd.DataFrame) -> dict:
    """Build lookup: {entity_id: {l2_risk: [list of ORE dicts]}}.

    Each ORE dict: {event_id, event_title, event_description, event_status,
    mapping_status}.
    """
    def _ore_from_row(row):
        d = {
            "event_id": str(row.get("event_id", "")),
            "event_title": str(row.get("Event Title", ""))[:200],
            "event_description": str(row.get("Event Description", ""))[:200],
        }
        # Optional: ORE classification (Class A/B/C) — may not be present in older files
        cls_val = row.get("Final Event Classification", "")
        cls_str = str(cls_val).strip() if pd.notna(cls_val) else ""
        if cls_str and cls_str.lower() not in ("", "nan", "none"):
            d["event_classification"] = cls_str
        # Optional: Event Status (lifecycle status) — may not be present in older files
        status_val = row.get("Event Status", "")
        status_str = str(status_val).strip() if pd.notna(status_val) else ""
        if status_str and status_str.lower() not in ("", "nan", "none"):
            d["event_status"] = status_str
        # Mapping confidence band — preserved so the per-row display can
        # annotate Needs Review items inline.
        mstatus = str(row.get("Mapping Status", "")).strip()
        if mstatus and mstatus.lower() not in ("", "nan", "none"):
            d["mapping_status"] = mstatus
        return d

    index = _build_nested_index(ore_df, "entity_id", "l2_risk",
                                value_fn=_ore_from_row)
    total = sum(len(fs) for eid_map in index.values() for fs in eid_map.values())
    logger.info(f"  ORE index built: {len(index)} entities, {total} total OREs")
    return index


def _derive_irm_ore_status(row, cols: dict, completed_values: set[str],
                           material_categories: set[str] | None = None) -> str:
    """Derive ORE Status for a single consolidated IRM ORE row.

    Returns "Closed" or "Open". A cancelled/canceled Capture Status
    short-circuits to "Closed" regardless of impacts. Otherwise an ORE is
    Closed only when all four phases (Capture, RCA, Stop ongoing impact, and
    the impact phase) are done. The impact phase honors a non-blank "Impact
    Assessment Closed" column when present (the consolidated pre-step
    pre-computes it); otherwise it falls back to the flat
    impact_assessment_status completed-values check. Materiality is a separate
    concern (see _is_material_ore) and does not affect status.
    """
    capture_col = cols.get("capture_status", "Capture Status")
    rca_col = cols.get("rca_status", "RCA Status")
    stop_col = cols.get("stop_ongoing_impact_status", "Stop ongoing impact Status")
    ia_col = cols.get("impact_assessment_status", "Impact Assessment Status")
    impact_closed_col = "Impact Assessment Closed"

    def _norm(v):
        return str(v).strip().lower()

    def _blank(v):
        return _norm(v) in ("", "nan", "none")

    def _done(v):
        return _norm(v) in completed_values

    capture_done = _done(row.get(capture_col, ""))
    rca_done = _done(row.get(rca_col, ""))
    stop_done = _done(row.get(stop_col, ""))

    # Cancelled capture short-circuits to Closed regardless of impacts.
    if _norm(row.get(capture_col, "")) in ("cancelled", "canceled"):
        return "Closed"

    impact_closed_val = row.get(impact_closed_col, "")
    if not _blank(impact_closed_val):
        ia_done = _norm(impact_closed_val) == "yes"
    else:
        ia_done = _done(row.get(ia_col, ""))

    return "Closed" if (capture_done and rca_done and ia_done and stop_done) else "Open"


def _is_material_ore(row, cols: dict, material_categories: set[str] | None = None) -> bool:
    """Materiality flag, separate from Open/Closed. Blank category => Material
    out of caution. Gates Impact of Issues only, not status."""
    cat_col = cols.get("ore_category", "ORE Category")
    material_cats = material_categories or {"material ore"}
    category = str(row.get(cat_col, "")).strip().lower()
    if category in ("", "nan", "none"):
        return True
    return category in material_cats


def _derive_irm_ore_statuses(df: pd.DataFrame, cols: dict, completed_values: set[str],
                             material_categories: set[str] | None = None) -> dict:
    """Roll up ORE Status across all Impact Assessment rows for each ORE ID.

    Returns {ore_id: status} where status is "Closed" or "Open".
    Each ORE's stacked rows are collapsed to a single representative row
    (first non-blank per column) and routed through _derive_irm_ore_status.
    """
    ore_id_col = cols.get("ore_id", "ORE ID")
    ia_col = cols.get("impact_assessment_status", "Impact Assessment Status")
    impact_id_col = cols.get("impact_id", "Impact ID")
    impact_closed_col = "Impact Assessment Closed"

    def _norm(v):
        return str(v).strip().lower()

    def _blank(v):
        return _norm(v) in ("", "nan", "none")

    def _done(v):
        return _norm(v) in completed_values

    status_by_ore: dict = {}
    if ore_id_col not in df.columns:
        return status_by_ore
    for oid, g in df.groupby(ore_id_col, sort=False):
        def first_nonblank(col):
            if col not in g.columns:
                return ""
            for v in g[col]:
                if not _blank(v):
                    return v
            return ""

        rep = {col: first_nonblank(col) for col in g.columns}

        # When no consolidated "Impact Assessment Closed" flag is present, the
        # impact phase is judged across every impact-bearing stacked row (a
        # single unfinished impact keeps the ORE Open). Pre-compute it here and
        # hand the per-row deriver a settled flag.
        if impact_closed_col not in g.columns or _blank(rep.get(impact_closed_col, "")):
            if impact_id_col in g.columns:
                impact_rows = g[g[impact_id_col].map(lambda v: not _blank(v))]
                if len(impact_rows) > 0 and ia_col in g.columns:
                    ia_done = all(_done(v) for v in impact_rows[ia_col])
                else:
                    ia_done = False
            else:
                ia_done = _done(first_nonblank(ia_col)) if ia_col in g.columns else False
            rep[impact_closed_col] = "Yes" if ia_done else "No"

        status_by_ore[oid] = _derive_irm_ore_status(rep, cols, completed_values, material_categories)
    return status_by_ore


def ingest_ore_irm_source(filepath: str, column_name_map: dict,
                          completed_values: set[str] | None = None,
                          material_categories: set[str] | None = None) -> pd.DataFrame:
    """Read the IRM ORE source file (pre-mapper).

    Returns one row per IRM ORE with source metadata, plus tool-added
    'Risk Level 2 Normalized' and 'L2 Provenance' columns (Track B convention,
    matches ingest_prsa).
    """
    logger.info(f"Reading IRM ORE source from {filepath}")
    if filepath.endswith(".csv"):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)
    df.columns = [c.strip() for c in df.columns]

    ore_id_col = column_name_map.get("ore_id", "ORE ID")
    risk_l2_col = column_name_map.get("risk_level_2", "Risk Level 2")

    if ore_id_col not in df.columns:
        raise ValueError(
            f"IRM ORE source missing required column '{ore_id_col}'. "
            f"Available: {list(df.columns)}"
        )

    df[ore_id_col] = df[ore_id_col].astype(str).str.strip()
    df = df[~df[ore_id_col].isin(["", "nan", "none"])].copy()

    # Track B: filer-tagged Risk Level 2 (when valid) overrides mapper output downstream.
    normalized_l2: list[str] = []
    provenance: list[str] = []
    invalid_count = valid_count = blank_count = 0
    if risk_l2_col in df.columns:
        for _, row in df.iterrows():
            raw_val = row.get(risk_l2_col, "")
            text = "" if raw_val is None else str(raw_val).strip()
            if not text or text.lower() in ("nan", "none"):
                normalized_l2.append("")
                provenance.append("mapper")
                blank_count += 1
                continue
            canonical = normalize_l2_name(text)
            if canonical is None:
                ore_id = str(row.get(ore_id_col, "")).strip()
                logger.warning(
                    f"  Invalid '{risk_l2_col}' for ORE {ore_id}: '{text}' "
                    f"(does not normalize to a taxonomy L2; falling back to mapper)"
                )
                normalized_l2.append("")
                provenance.append("mapper")
                invalid_count += 1
            else:
                normalized_l2.append(canonical)
                provenance.append("source")
                valid_count += 1
    else:
        normalized_l2 = ["" for _ in range(len(df))]
        provenance = ["mapper" for _ in range(len(df))]
        blank_count = len(df)
        logger.info(f"  Column '{risk_l2_col}' not found — all rows use mapper provenance")

    df["Risk Level 2 Normalized"] = normalized_l2
    df["L2 Provenance"] = provenance

    # Prefer the ORE Status precomputed by the consolidation pre-step so the
    # mapper's Closed-skip and this displayed status are guaranteed identical.
    # Fall back to deriving here for non-consolidated inputs (e.g. flat fixture).
    if "ORE Status" in df.columns:
        df["ORE Status"] = df["ORE Status"].fillna("").astype(str).str.strip()
    else:
        cv = completed_values or {"completed", "complete"}
        mc = material_categories or {"material ore"}
        status_by_ore = _derive_irm_ore_statuses(df, column_name_map, cv, mc)
        df["ORE Status"] = df[ore_id_col].map(lambda oid: status_by_ore.get(oid, ""))

    if "ORE Materiality" in df.columns:
        df["ORE Materiality"] = df["ORE Materiality"].fillna("").astype(str).str.strip()
    else:
        mc = material_categories or {"material ore"}
        df["ORE Materiality"] = df.apply(
            lambda r: "Material" if _is_material_ore(r, column_name_map, mc) else "Non-Material",
            axis=1,
        )

    open_n = int((df["ORE Status"] == "Open").sum())
    closed_n = int((df["ORE Status"] == "Closed").sum())
    material_n = int((df["ORE Materiality"] == "Material").sum())
    nonmaterial_n = int((df["ORE Materiality"] == "Non-Material").sum())

    logger.info(
        f"  Loaded {len(df)} IRM OREs. Provenance: {valid_count} source / "
        f"{blank_count} blank-fallback / {invalid_count} invalid-fallback"
    )
    logger.info(
        f"  Derived ORE Status: {open_n} Open / {closed_n} Closed. "
        f"Materiality: {material_n} Material / {nonmaterial_n} Non-Material"
    )
    return df


def ingest_ore_irm_mappings(filepath: str, confidence_filter: list[str] | None = None) -> tuple[pd.DataFrame, dict]:
    """Read IRM ORE mapper output and filter to mapped statuses.

    Mirrors ingest_ore_mappings but does not require an Audit Entity ID
    column — IRM AE attribution happens at index-build time via the legacy
    'IRM ORE ID' bridge column.

    Returns:
        (ore_irm_df, unmapped_dict). ore_irm_df has internal 'event_id' and
        'l2_risk' columns. unmapped_dict captures rows whose mapper L2 didn't
        normalize, keyed off ORE ID (no AE attribution at this point).
    """
    logger.info(f"Reading IRM ORE mappings from {filepath}")
    df = pd.read_excel(filepath, sheet_name="All Mappings")
    df.columns = [c.strip() for c in df.columns]

    required = ["Event ID", "Mapping Status", "Mapped L2s"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"IRM ORE mapping file missing columns: {missing}")

    if confidence_filter is None:
        confidence_filter = ["Suggested Match"]
    pre_filter = len(df)
    df = df[df["Mapping Status"].isin(confidence_filter)]
    logger.info(f"  Filtered to {len(df)} of {pre_filter} IRM OREs (statuses: {confidence_filter})")

    # Explode semicolon-separated Mapped L2s into individual rows
    df["l2_risk"] = df["Mapped L2s"].astype(str).str.split("; ")
    df = df.explode("l2_risk")
    df["l2_risk"] = df["l2_risk"].str.strip()
    df = df[df["l2_risk"] != ""]

    df = df.rename(columns={"Event ID": "event_id"})
    df["event_id"] = df["event_id"].astype(str).str.strip()
    raw_l2 = df["l2_risk"].copy()
    df["l2_risk"] = df["l2_risk"].apply(normalize_l2_name)
    unmapped_mask = df["l2_risk"].isna()

    # Capture unmapped rows so reviewers see what the mapper produced that
    # didn't reconcile to canonical L2s. Keyed under "" because there's no AE
    # at this point — the unmapped surface lives at ORE granularity.
    unmapped: dict[str, list[dict]] = {}
    if unmapped_mask.any():
        for _, urow in df[unmapped_mask].iterrows():
            unmapped.setdefault("", []).append({
                "source": "ore_irm",
                "item_id": str(urow.get("event_id", "")),
                "raw_l2": str(raw_l2.loc[urow.name]),
            })
        dropped_values = raw_l2[unmapped_mask].value_counts()
        logger.info(f"  Dropped {unmapped_mask.sum()} IRM ORE-L2 pairs with unmappable L2 names:")
        for val, count in dropped_values.items():
            logger.info(f"    '{val}': {count}")
    df = df[~unmapped_mask]

    logger.info(f"  Loaded {len(df)} IRM ORE mappings")
    return df, unmapped


def build_ore_irm_mapping_index(
    legacy_df: pd.DataFrame,
    ore_irm_source_df: pd.DataFrame,
    ore_irm_mapping_df: pd.DataFrame | None,
    legacy_irm_ore_col: str,
    entity_id_col: str,
    ore_irm_cols: dict | None = None,
) -> dict:
    """Build {entity_id: {l2_risk: [ore_irm_dicts]}} by joining mapper output
    onto legacy_df's IRM ORE ID newline-delimited column.

    Each ore_irm_dict mirrors the shape produced by build_ore_index so it
    drops into the combined ORE index transparently. Carries an
    `ore_source: "IRM"` discriminator so downstream filters (e.g., the
    closed-status filter in derive_control_effectiveness) can opt out
    per Lu's spec.
    """
    if ore_irm_source_df is None or ore_irm_source_df.empty:
        return {}
    if legacy_irm_ore_col not in legacy_df.columns:
        logger.warning(
            f"  legacy_df has no '{legacy_irm_ore_col}' column — no AE attribution "
            f"is possible, so IRM OREs will NOT appear in the dashboard (skipping "
            f"IRM index build). Reviewers should consult the 'Source - ORE IRM' and "
            f"'Upstream Tagging Gaps' tabs in the Excel workbook."
        )
        return {}

    ore_irm_cols = ore_irm_cols or {}
    ore_id_col = ore_irm_cols.get("ore_id", "ORE ID")

    # Step 1: explode legacy IRM ORE ID column → list of (entity_id, ore_id) pairs.
    pairs: list[tuple[str, str]] = []
    for _, row in legacy_df.iterrows():
        eid = str(row.get(entity_id_col, "")).strip()
        if not eid or eid.lower() in ("nan", "none"):
            continue
        for ore_id in split_id_list(row.get(legacy_irm_ore_col, "")):
            pairs.append((eid, ore_id))

    if not pairs:
        logger.info(f"  No (AE, ORE-IRM) pairs found in legacy '{legacy_irm_ore_col}' column")
        return {}

    # Step 2: per-ORE metadata + provenance lookup.
    src_idx: dict[str, dict] = {}
    for _, row in ore_irm_source_df.iterrows():
        oid = str(row.get(ore_id_col, "")).strip()
        if not oid:
            continue
        src_idx[oid] = row.to_dict()

    # Step 3: mapper L2 lookup. mapper_df has been exploded already (see
    # ingest_ore_irm_mappings), so each row is one (ore_id, l2) pair.
    mapper_l2s: dict[str, list[tuple[str, str]]] = defaultdict(list)
    if ore_irm_mapping_df is not None and not ore_irm_mapping_df.empty:
        for _, row in ore_irm_mapping_df.iterrows():
            oid = str(row.get("event_id", "")).strip()
            l2 = str(row.get("l2_risk", "")).strip()
            mstatus = str(row.get("Mapping Status", "")).strip()
            if oid and l2:
                mapper_l2s[oid].append((l2, mstatus))

    # Step 4: build the index.
    index: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    seen_keys: set[tuple[str, str, str]] = set()  # (entity_id, l2, ore_id) dedup
    for entity_id, ore_id in pairs:
        meta = src_idx.get(ore_id)
        if meta is None:
            logger.warning(
                f"  IRM ORE {ore_id} referenced by entity {entity_id} but not "
                f"found in IRM source file — skipping"
            )
            continue
        provenance = str(meta.get("L2 Provenance", "mapper")).strip().lower()
        if provenance == "source":
            l2_pairs = [(str(meta.get("Risk Level 2 Normalized", "")).strip(), "Source-Tagged")]
        else:
            l2_pairs = mapper_l2s.get(ore_id, [])
        for l2, mstatus in l2_pairs:
            if not l2:
                continue
            key = (entity_id, l2, ore_id)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            item = {
                "event_id": ore_id,
                "event_title": str(meta.get(ore_irm_cols.get("ore_title", "ORE Title"), ""))[:200],
                "event_description": str(meta.get(ore_irm_cols.get("ore_description", "ORE Description"), ""))[:200],
                "ore_source": "IRM",
                "l2_provenance": provenance,
            }
            cap_status = str(meta.get(ore_irm_cols.get("capture_status", "Capture Status"), "")).strip()
            if cap_status and cap_status.lower() not in ("", "nan", "none"):
                item["event_status"] = cap_status
            ore_status = str(meta.get("ORE Status", "")).strip()
            if ore_status:
                item["ore_status"] = ore_status
            materiality = str(meta.get("ORE Materiality", "")).strip()
            if materiality:
                item["ore_material"] = materiality
            legacy_event_id = str(meta.get(ore_irm_cols.get("legacy_event_id", "Legacy Event ID"), "")).strip()
            if legacy_event_id and legacy_event_id.lower() not in ("", "nan", "none"):
                item["legacy_event_id"] = legacy_event_id
            if mstatus and mstatus.lower() not in ("", "nan", "none"):
                item["mapping_status"] = mstatus
            index[entity_id][l2].append(item)

    plain = {k1: dict(v) for k1, v in index.items()}
    total = sum(len(items) for by_l2 in plain.values() for items in by_l2.values())
    logger.info(f"  IRM ORE index built: {len(plain)} entities, {total} total IRM ORE × L2 entries")
    return plain


def ingest_prsa_mappings(filepath: str, confidence_filter: list[str] | None = None) -> tuple[pd.DataFrame, dict]:
    """Read PRSA mapper output and filter to mapped statuses.

    Explodes the semicolon-separated 'Mapped L2s' column into one row per
    (entity_id, l2_risk) pair for downstream indexing.

    Returns:
        (prsa_df, unmapped_dict). unmapped_dict captures PRSA mapper rows
        whose L2 name didn't normalize.
    """
    logger.info(f"Reading PRSA mappings from {filepath}")
    df = pd.read_excel(filepath, sheet_name="All Mappings")
    df.columns = [c.strip() for c in df.columns]

    required = ["Issue ID", "AE ID", "Mapping Status", "Mapped L2s"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"PRSA mapping file missing columns: {missing}")

    if confidence_filter is None:
        confidence_filter = ["Suggested Match"]
    pre_filter = len(df)
    df = df[df["Mapping Status"].isin(confidence_filter)]
    logger.info(f"  Filtered to {len(df)} of {pre_filter} PRSA issues "
                f"(statuses: {confidence_filter})")

    # Explode semicolon-separated Mapped L2s
    df["l2_risk"] = df["Mapped L2s"].astype(str).str.split("; ")
    df = df.explode("l2_risk")
    df["l2_risk"] = df["l2_risk"].str.strip()
    df = df[df["l2_risk"] != ""]

    df = df.rename(columns={
        "AE ID": "entity_id",
        "Issue ID": "issue_id",
    })
    df["entity_id"] = df["entity_id"].astype(str).str.strip()
    raw_l2 = df["l2_risk"].copy()
    df["l2_risk"] = df["l2_risk"].apply(normalize_l2_name)
    unmapped_mask = df["l2_risk"].isna()

    unmapped: dict[str, list[dict]] = {}
    if unmapped_mask.any():
        for _, urow in df[unmapped_mask].iterrows():
            eid = str(urow["entity_id"]).strip()
            unmapped.setdefault(eid, []).append({
                "source": "prsa",
                "item_id": str(urow.get("issue_id", "")),
                "raw_l2": str(raw_l2.loc[urow.name]),
            })
        dropped_values = raw_l2[unmapped_mask].value_counts()
        logger.info(f"  Dropped {unmapped_mask.sum()} PRSA-L2 pairs with unmappable L2 names (captured as unmapped):")
        for val, count in dropped_values.items():
            logger.info(f"    '{val}': {count}")
    df = df[~unmapped_mask]

    logger.info(f"  Loaded {len(df)} PRSA mappings across {df['entity_id'].nunique()} entities")
    return df, unmapped


def build_prsa_mapping_index(prsa_mapping_df: pd.DataFrame) -> dict:
    """Build lookup: {entity_id: {l2_risk: [list of PRSA issue dicts]}}.

    Each PRSA dict: {issue_id, issue_title, issue_description, issue_rating,
    issue_status, mapping_status}.

    Track C: rows with blank entity_id (e.g., synthesized rows for PG-flagged
    Archer issues that lack a PRSA control mapping) are explicitly skipped so
    they never enter the per-AE PRSA pill listings. Those PG gaps surface via
    the Source - PG Gaps Excel tab and the banner count instead.
    """
    def _prsa_from_row(row):
        d = {
            "issue_id": str(row.get("issue_id", "")),
            "issue_title": str(row.get("Issue Title", ""))[:200],
            "issue_description": str(row.get("Issue Description", ""))[:200],
        }
        rating = str(row.get("Issue Rating", "")).strip()
        if rating and rating.lower() not in ("", "nan", "none"):
            d["issue_rating"] = rating
        status = str(row.get("Issue Status", "")).strip()
        if status and status.lower() not in ("", "nan", "none"):
            d["issue_status"] = status
        mstatus = str(row.get("Mapping Status", "")).strip()
        if mstatus and mstatus.lower() not in ("", "nan", "none"):
            d["mapping_status"] = mstatus
        return d

    if prsa_mapping_df is None or prsa_mapping_df.empty:
        return {}
    blank_eid = prsa_mapping_df["entity_id"].astype(str).str.strip().isin(["", "nan", "none"])
    blank_count = int(blank_eid.sum())
    if blank_count:
        logger.info(f"  PRSA mapping index: skipping {blank_count} row(s) with blank entity_id "
                    f"(unmapped PG gaps — surfaced via Source - PG Gaps tab instead)")
    filtered = prsa_mapping_df.loc[~blank_eid]

    index = _build_nested_index(filtered, "entity_id", "l2_risk",
                                value_fn=_prsa_from_row)
    total = sum(len(fs) for eid_map in index.values() for fs in eid_map.values())
    logger.info(f"  PRSA mapping index built: {len(index)} entities, {total} total items")
    return index


def ingest_rap_mappings(filepath: str, confidence_filter: list[str] | None = None) -> tuple[pd.DataFrame, dict]:
    """Read RAP mapper output and filter to mapped statuses.

    Returns:
        (rap_df, unmapped_dict). unmapped_dict captures RAP mapper rows
        whose L2 name didn't normalize.
    """
    logger.info(f"Reading RAP mappings from {filepath}")
    df = pd.read_excel(filepath, sheet_name="All Mappings")
    df.columns = [c.strip() for c in df.columns]

    required = ["RAP ID", "Audit Entity ID", "Mapping Status", "Mapped L2s"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"RAP mapping file missing columns: {missing}")

    if confidence_filter is None:
        confidence_filter = ["Suggested Match"]
    pre_filter = len(df)
    df = df[df["Mapping Status"].isin(confidence_filter)]
    logger.info(f"  Filtered to {len(df)} of {pre_filter} RAPs "
                f"(statuses: {confidence_filter})")

    df["l2_risk"] = df["Mapped L2s"].astype(str).str.split("; ")
    df = df.explode("l2_risk")
    df["l2_risk"] = df["l2_risk"].str.strip()
    df = df[df["l2_risk"] != ""]

    df = df.rename(columns={
        "Audit Entity ID": "entity_id",
        "RAP ID": "rap_id",
    })
    df["entity_id"] = df["entity_id"].astype(str).str.strip()
    raw_l2 = df["l2_risk"].copy()
    df["l2_risk"] = df["l2_risk"].apply(normalize_l2_name)
    unmapped_mask = df["l2_risk"].isna()

    unmapped: dict[str, list[dict]] = {}
    if unmapped_mask.any():
        for _, urow in df[unmapped_mask].iterrows():
            eid = str(urow["entity_id"]).strip()
            unmapped.setdefault(eid, []).append({
                "source": "rap",
                "item_id": str(urow.get("rap_id", "")),
                "raw_l2": str(raw_l2.loc[urow.name]),
            })
        dropped_values = raw_l2[unmapped_mask].value_counts()
        logger.info(f"  Dropped {unmapped_mask.sum()} RAP-L2 pairs with unmappable L2 names (captured as unmapped):")
        for val, count in dropped_values.items():
            logger.info(f"    '{val}': {count}")
    df = df[~unmapped_mask]

    logger.info(f"  Loaded {len(df)} RAP mappings across {df['entity_id'].nunique()} entities")
    return df, unmapped


def build_rap_mapping_index(rap_mapping_df: pd.DataFrame) -> dict:
    """Build lookup: {entity_id: {l2_risk: [list of RAP dicts]}}.

    Each RAP dict: {rap_id, rap_header, rap_details, rap_status,
    related_exams_and_findings, mapping_status}.
    """
    def _rap_from_row(row):
        d = {
            "rap_id": str(row.get("rap_id", "")),
            "rap_header": str(row.get("RAP Header", ""))[:200],
            "rap_details": str(row.get("RAP Details", ""))[:200],
        }
        status = str(row.get("RAP Status", "")).strip()
        if status and status.lower() not in ("", "nan", "none"):
            d["rap_status"] = status
        related = str(row.get("Related Exams and Findings", "")).strip()
        if related and related.lower() not in ("", "nan", "none"):
            d["related_exams_and_findings"] = related
        mstatus = str(row.get("Mapping Status", "")).strip()
        if mstatus and mstatus.lower() not in ("", "nan", "none"):
            d["mapping_status"] = mstatus
        return d

    index = _build_nested_index(rap_mapping_df, "entity_id", "l2_risk",
                                value_fn=_rap_from_row)
    total = sum(len(fs) for eid_map in index.values() for fs in eid_map.values())
    logger.info(f"  RAP mapping index built: {len(index)} entities, {total} total items")
    return index


def ingest_prsa(filepath: str, column_name_map: dict) -> pd.DataFrame:
    """Read a PRSA Frankenstein report (AE + Issues + PRSA controls in one file).

    Returns the raw DataFrame with these added columns:
      - 'Other AEs With This PRSA': cross-AE visibility for each PRSA.
      - 'Risk Level 2 Normalized': filer-tagged L2 from source, normalized to
        the canonical taxonomy name. Empty if blank or unmappable.
      - 'L2 Provenance': 'source' when 'Risk Level 2 Normalized' is populated,
        otherwise 'mapper' (downstream PRSA mapper output is the fallback).

    Column names are read from ``column_name_map`` (sourced from
    ``taxonomy_config.yaml`` → ``columns.prsa``).
    """
    logger.info(f"Reading PRSA report from {filepath}")
    if filepath.endswith(".csv"):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)
    df.columns = [c.strip() for c in df.columns]

    ae_id_col = column_name_map.get("ae_id", "AE ID")
    prsa_id_col = column_name_map.get("prsa_id", "PRSA ID")
    issue_id_col = column_name_map.get("issue_id", "Issue ID")
    tagged_col = column_name_map.get("all_prsas_tagged", "All PRSAs Tagged to AE")
    risk_l2_col = column_name_map.get("risk_level_2", "Risk Level 2")

    required = [ae_id_col, prsa_id_col, issue_id_col]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"PRSA report missing required columns: {missing}")

    # Track C: blank cells become NaN through pandas' Excel reader; NaN.astype
    # gives the literal string "nan" which then masquerades as a populated AE.
    # Normalize "nan" to empty so blank-AE filters work consistently.
    def _clean_id_str(s: pd.Series) -> pd.Series:
        return s.astype(str).str.strip().mask(
            lambda x: x.str.lower().isin(["nan", "none"]), ""
        )

    df[ae_id_col] = _clean_id_str(df[ae_id_col])
    df[prsa_id_col] = _clean_id_str(df[prsa_id_col])

    # Build PRSA → AE mapping from the multi-value tagged column
    prsa_to_aes: dict[str, set[str]] = defaultdict(set)
    if tagged_col in df.columns:
        # Collect from all rows (each AE may repeat, but the tag list is the same)
        seen_aes = set()
        for _, row in df.iterrows():
            ae_id = str(row[ae_id_col]).strip()
            if ae_id in seen_aes:
                continue
            seen_aes.add(ae_id)
            for prsa_id in split_id_list(row.get(tagged_col, "")):
                prsa_to_aes[prsa_id].add(ae_id)

    # Add cross-AE column: for each row's PRSA ID, list other AEs that share it
    other_aes = []
    for _, row in df.iterrows():
        ae_id = str(row[ae_id_col]).strip()
        prsa_id = str(row[prsa_id_col]).strip()
        shared = sorted(prsa_to_aes.get(prsa_id, set()) - {ae_id})
        other_aes.append(", ".join(shared) if shared else "")
    df["Other AEs With This PRSA"] = other_aes

    # Resolve filer-tagged L2 (Track B): when source is populated and normalizes
    # to a valid taxonomy L2, it overrides the PRSA mapper output downstream.
    # Invalid source values fall back to mapper with a WARNING.
    normalized_l2: list[str] = []
    provenance: list[str] = []
    invalid_count = 0
    valid_count = 0
    blank_count = 0
    if risk_l2_col in df.columns:
        for _, row in df.iterrows():
            raw_val = row.get(risk_l2_col, "")
            text = "" if raw_val is None else str(raw_val).strip()
            if not text or text.lower() in ("nan", "none"):
                normalized_l2.append("")
                provenance.append("mapper")
                blank_count += 1
                continue
            canonical = normalize_l2_name(text)
            if canonical is None:
                issue_id = str(row.get(issue_id_col, "")).strip()
                logger.warning(
                    f"  Invalid '{risk_l2_col}' for issue {issue_id}: '{text}' "
                    f"(does not normalize to a taxonomy L2; falling back to mapper)"
                )
                normalized_l2.append("")
                provenance.append("mapper")
                invalid_count += 1
            else:
                normalized_l2.append(canonical)
                provenance.append("source")
                valid_count += 1
    else:
        # Column not present at all — every row falls back to mapper.
        normalized_l2 = ["" for _ in range(len(df))]
        provenance = ["mapper" for _ in range(len(df))]
        blank_count = len(df)
        logger.info(f"  Column '{risk_l2_col}' not found — all rows use mapper provenance")

    df["Risk Level 2 Normalized"] = normalized_l2
    df["L2 Provenance"] = provenance

    # Track C: normalize Is PG Gap to a boolean column for downstream filters.
    # The Frankenstein writes "Yes"/"No" strings; older builds may not have
    # the column at all (treat as all-False then).
    is_pg_col = column_name_map.get("is_pg_gap", "Is PG Gap")
    if is_pg_col in df.columns:
        df[is_pg_col] = df[is_pg_col].map(
            lambda v: str(v).strip().lower() in ("yes", "true", "1")
        )
        pg_count = int(df[is_pg_col].sum())
        pg_unmapped_count = int(
            (df[is_pg_col] & (df[ae_id_col].astype(str).str.strip() == "")).sum()
        )
        logger.info(f"  PG gaps: {pg_count} total ({pg_unmapped_count} unmapped without AE)")
    else:
        df[is_pg_col] = False
        logger.info(f"  Column '{is_pg_col}' not found — no PG gaps in this report")

    logger.info(f"  Loaded {len(df)} PRSA issue-control rows across "
                f"{df[ae_id_col].nunique()} entities")
    logger.info(f"  Unique PRSAs: {df[prsa_id_col].nunique()}, "
                f"Unique issues: {df[issue_id_col].nunique()}")
    logger.info(f"  L2 provenance: {valid_count} source / "
                f"{blank_count} blank-fallback / {invalid_count} invalid-fallback")

    # Log cross-AE shared PRSAs
    shared_prsas = {p: aes for p, aes in prsa_to_aes.items() if len(aes) > 1}
    if shared_prsas:
        logger.info(f"  PRSAs shared across AEs: {len(shared_prsas)}")
        for prsa_id, aes in sorted(shared_prsas.items()):
            logger.info(f"    {prsa_id}: {sorted(aes)}")

    return df


def build_pg_gap_index(prsa_df: pd.DataFrame, column_name_map: dict | None = None) -> dict:
    """Build {entity_id: {l2_risk: [pg_gap_dicts]}} from prsa_df.

    Filters to PG-flagged rows that have BOTH an AE ID and a normalized L2.
    PG gaps without an AE (unmapped — the team hasn't entered a PRSA control
    in IRM Archer yet) are excluded here so they don't try to render as
    per-AE pills. They surface via the Source - PG Gaps Excel tab + the
    pg_gap banner count.

    Each item dict mirrors the PRSA mapping index shape so the HTML pill
    renderer can reuse the same column-resolution logic where it makes sense.
    """
    if prsa_df is None or prsa_df.empty:
        return {}

    column_name_map = column_name_map or {}
    ae_id_col = column_name_map.get("ae_id", "AE ID")
    issue_id_col = column_name_map.get("issue_id", "Issue ID")
    issue_title_col = column_name_map.get("issue_title", "Issue Title")
    issue_desc_col = column_name_map.get("issue_description", "Issue Description")
    issue_rating_col = column_name_map.get("issue_rating", "Issue Rating")
    issue_status_col = column_name_map.get("issue_status", "Issue Status")
    is_pg_col = column_name_map.get("is_pg_gap", "Is PG Gap")
    norm_l2_col = "Risk Level 2 Normalized"

    if is_pg_col not in prsa_df.columns:
        return {}

    # Per-issue dedup: same issue may appear on multiple controls (Frankenstein
    # grain is AE × Issue × Control). For pill purposes one entry per
    # (entity, l2, issue) is correct.
    index: dict[str, dict[str, list[dict]]] = {}
    seen_keys: set[tuple[str, str, str]] = set()
    for _, row in prsa_df.iterrows():
        if not bool(row.get(is_pg_col, False)):
            continue
        eid = str(row.get(ae_id_col, "")).strip()
        if not eid or eid.lower() in ("nan", "none"):
            continue
        l2 = str(row.get(norm_l2_col, "")).strip()
        if not l2:
            # PG gap without a normalized L2 has nowhere to render as a per-L2
            # pill. The Excel source tab still surfaces it.
            continue
        iid = str(row.get(issue_id_col, "")).strip()
        key = (eid, l2, iid)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        item: dict = {
            "issue_id": iid,
            "issue_title": str(row.get(issue_title_col, ""))[:200],
            "issue_description": str(row.get(issue_desc_col, ""))[:200],
        }
        rating = str(row.get(issue_rating_col, "")).strip()
        if rating and rating.lower() not in ("", "nan", "none"):
            item["issue_rating"] = rating
        status = str(row.get(issue_status_col, "")).strip()
        if status and status.lower() not in ("", "nan", "none"):
            item["issue_status"] = status
        index.setdefault(eid, {}).setdefault(l2, []).append(item)

    total = sum(len(items) for by_l2 in index.values() for items in by_l2.values())
    logger.info(f"  PG gap index built: {len(index)} entities, {total} total PG gap pill entries")
    return index


def ingest_pg_team_inputs(filepath: str, column_name_map: dict) -> pd.DataFrame:
    """Read a Project Guardian team inputs file (per-Gap-ID severity + Archer bridges).

    Expected source columns (resolved via ``column_name_map`` sourced from
    ``taxonomy_config.yaml`` → ``columns.pg_team_inputs``):
      - ``gap_id``: PG team's Gap ID.
      - ``impact_rating``: PG team's severity rating for the gap.
      - ``issue_id``: Archer IRM Issue ID — joins to prsa_df issue_id.
      - ``finding_id``: Archer eGRC Finding ID — joins to findings_df issue_id.

    Returns the raw DataFrame with whitespace-stripped column headers and the
    four resolved columns retained under their source names. ``issue_id`` and
    ``finding_id`` are cleaned so blank/NaN become "" (matching the ingest_prsa
    convention).
    """
    logger.info(f"Reading PG team inputs from {filepath}")
    sheet_name = column_name_map.get("sheet_name", 0)
    if filepath.endswith(".csv"):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath, sheet_name=sheet_name)
    df.columns = [c.strip() for c in df.columns]

    gap_id_col = column_name_map.get("gap_id", "Gap ID")
    issue_id_col = column_name_map.get("issue_id", "Issue ID (Archer IRM)")
    finding_id_col = column_name_map.get("finding_id", "Archer eGRC FND ID")

    required = [gap_id_col, issue_id_col, finding_id_col]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"PG team inputs file missing required columns: {missing}. "
            f"Available: {list(df.columns)}"
        )

    def _clean_id_str(s: pd.Series) -> pd.Series:
        return s.astype(str).str.strip().mask(
            lambda x: x.str.lower().isin(["nan", "none"]), ""
        )

    df[issue_id_col] = _clean_id_str(df[issue_id_col])
    df[finding_id_col] = _clean_id_str(df[finding_id_col])

    total = len(df)
    has_issue = (df[issue_id_col] != "").sum()
    has_fnd = (df[finding_id_col] != "").sum()
    has_both = ((df[issue_id_col] != "") & (df[finding_id_col] != "")).sum()
    has_neither = ((df[issue_id_col] == "") & (df[finding_id_col] == "")).sum()
    logger.info(f"  Loaded {total} PG team gap rows")
    logger.info(f"  Rows with Issue ID: {has_issue}, with Finding ID: {has_fnd}, "
                f"with both: {has_both}, with neither: {has_neither}")
    return df


def build_pg_gap_index_from_pg_team(
    pg_team_df: pd.DataFrame,
    findings_df: pd.DataFrame,
    prsa_df: pd.DataFrame,
    column_name_map_pg: dict,
    column_name_map_prsa: dict,
) -> tuple[dict, dict]:
    """Build a second PG gap pill index via the FND_ID -> findings -> (AE, L2) bridge.

    Each row in ``pg_team_df`` with a non-blank Finding ID is looked up in
    ``findings_df`` (already exploded one row per (entity_id, l2_risk) by
    ``ingest_findings``). A single Finding ID may produce multiple (AE, L2)
    pairs — all become independent pill entries. Each resolved pill is then
    enriched from ``prsa_df`` by Issue ID when the Issue ID is present in PRSA;
    when absent (PG-team-only gap), the pill carries the PG team's Impact
    Rating and a synthetic title.

    Pill dicts mirror the schema built in ``build_pg_gap_index`` so the HTML
    renderer can consume both indexes transparently. Each pill is tagged with
    ``pg_team_route: True`` for diagnostic provenance.

    Returns ``(index, diagnostics)`` where:
      - ``index`` is ``{entity_id: {l2_risk: [pill_dicts]}}``
      - ``diagnostics`` carries ``pg_team_rows_total``, ``resolved_via_fnd``,
        ``unresolved_no_fnd_match``, ``pg_team_only_issues``.
    """
    diagnostics: dict = {
        "pg_team_rows_total": 0,
        "resolved_via_fnd": 0,
        "unresolved_no_fnd_match": 0,
        "pg_team_only_issues": [],
    }
    index: dict[str, dict[str, list[dict]]] = {}

    if pg_team_df is None or pg_team_df.empty:
        return index, diagnostics
    if findings_df is None or findings_df.empty:
        logger.info("  PG team FND bridge: findings_df is empty — no resolutions possible")
        return index, diagnostics

    impact_rating_col = column_name_map_pg.get("impact_rating", "Impact Rating")
    pg_issue_id_col = column_name_map_pg.get("issue_id", "Issue ID (Archer IRM)")
    pg_finding_id_col = column_name_map_pg.get("finding_id", "Archer eGRC FND ID")
    pg_gap_id_col = column_name_map_pg.get("gap_id", "Gap ID")

    prsa_issue_id_col = column_name_map_prsa.get("issue_id", "Issue ID")
    prsa_issue_title_col = column_name_map_prsa.get("issue_title", "Issue Title")
    prsa_issue_desc_col = column_name_map_prsa.get("issue_description", "Issue Description")
    prsa_issue_rating_col = column_name_map_prsa.get("issue_rating", "Issue Rating")
    prsa_issue_status_col = column_name_map_prsa.get("issue_status", "Issue Status")

    # Findings are pre-exploded by ingest_findings: one row per (entity_id, l2_risk).
    # Group by issue_id so a single FND_ID resolves to all its (AE, L2) attributions.
    findings_by_fnd: dict[str, list[tuple[str, str]]] = defaultdict(list)
    if "issue_id" in findings_df.columns:
        for _, frow in findings_df.iterrows():
            fid = str(frow.get("issue_id", "")).strip()
            if not fid or fid.lower() in ("nan", "none"):
                continue
            eid = str(frow.get("entity_id", "")).strip()
            l2 = str(frow.get("l2_risk", "")).strip()
            if not eid or not l2:
                continue
            findings_by_fnd[fid].append((eid, l2))

    # PRSA lookup: one entry per Issue ID (drop duplicate rows, Frankenstein
    # grain is AE x Issue x Control but the metadata is identical per issue).
    prsa_by_issue: dict[str, dict] = {}
    if prsa_df is not None and not prsa_df.empty and prsa_issue_id_col in prsa_df.columns:
        for _, prow in prsa_df.iterrows():
            iid = str(prow.get(prsa_issue_id_col, "")).strip()
            if not iid or iid in prsa_by_issue:
                continue
            prsa_by_issue[iid] = {
                "issue_title": str(prow.get(prsa_issue_title_col, ""))[:200],
                "issue_description": str(prow.get(prsa_issue_desc_col, ""))[:200],
                "issue_rating": str(prow.get(prsa_issue_rating_col, "")).strip(),
                "issue_status": str(prow.get(prsa_issue_status_col, "")).strip(),
            }

    seen_keys: set[tuple[str, str, str]] = set()
    pg_team_only_issues: set[str] = set()
    unresolved_orphan_rows: list[dict] = []
    for _, row in pg_team_df.iterrows():
        diagnostics["pg_team_rows_total"] += 1
        fid = str(row.get(pg_finding_id_col, "")).strip()
        iid = str(row.get(pg_issue_id_col, "")).strip()
        pg_rating = str(row.get(impact_rating_col, "")).strip()
        gap_id = str(row.get(pg_gap_id_col, "")).strip()
        if not fid:
            diagnostics["unresolved_no_fnd_match"] += 1
            unresolved_orphan_rows.append({"gap_id": gap_id, "issue_id": iid})
            continue
        matches = findings_by_fnd.get(fid, [])
        if not matches:
            diagnostics["unresolved_no_fnd_match"] += 1
            unresolved_orphan_rows.append({"gap_id": gap_id, "issue_id": iid})
            continue
        diagnostics["resolved_via_fnd"] += 1
        prsa_meta = prsa_by_issue.get(iid)
        if iid and prsa_meta is None:
            pg_team_only_issues.add(iid)
        for eid, l2 in matches:
            key = (eid, l2, iid)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            if prsa_meta is not None:
                item: dict = {
                    "issue_id": iid,
                    "issue_title": prsa_meta["issue_title"],
                    "issue_description": prsa_meta["issue_description"],
                    "pg_team_route": True,
                }
                # PRSA Issue Rating wins over PG team's Impact Rating; fall back
                # to PG rating only when PRSA's is blank.
                rating = prsa_meta["issue_rating"]
                if not rating or rating.lower() in ("", "nan", "none"):
                    rating = pg_rating
                if rating and rating.lower() not in ("", "nan", "none"):
                    item["issue_rating"] = rating
                status = prsa_meta["issue_status"]
                if status and status.lower() not in ("", "nan", "none"):
                    item["issue_status"] = status
            else:
                item = {
                    "issue_id": iid,
                    "issue_title": "(PG team gap — no PRSA record)",
                    "issue_description": "",
                    "pg_team_route": True,
                }
                if pg_rating and pg_rating.lower() not in ("", "nan", "none"):
                    item["issue_rating"] = pg_rating
            index.setdefault(eid, {}).setdefault(l2, []).append(item)

    diagnostics["pg_team_only_issues"] = sorted(pg_team_only_issues)
    diagnostics["orphans"] = pd.DataFrame({
        "Source": ["PG Gap (PG team)"] * len(unresolved_orphan_rows),
        "Item ID": [r["gap_id"] for r in unresolved_orphan_rows],
        "Title": [r["issue_id"] for r in unresolved_orphan_rows],
        "Status": ["Unresolved"] * len(unresolved_orphan_rows),
        "Drop Reason": ["PG gap — Archer eGRC FND ID not matched to a finding"] * len(unresolved_orphan_rows),
        "Source File": [""] * len(unresolved_orphan_rows),
    }) if unresolved_orphan_rows else pd.DataFrame()
    total = sum(len(items) for by_l2 in index.values() for items in by_l2.values())
    logger.info(
        f"  PG team FND bridge: {diagnostics['pg_team_rows_total']} total rows, "
        f"{diagnostics['resolved_via_fnd']} resolved via FND_ID, "
        f"{diagnostics['unresolved_no_fnd_match']} unresolved, "
        f"{len(pg_team_only_issues)} PG-team-only issue(s)"
    )
    logger.info(f"  PG team FND index built: {len(index)} entities, {total} pill entries")
    return index, diagnostics


def merge_pg_gap_indexes(prsa_route: dict, pg_team_route: dict) -> dict:
    """Union two PG gap pill indexes, deduping on (entity_id, l2, issue_id).

    The dedup key matches ``build_pg_gap_index`` (the PRSA-route builder) so a
    gap that resolves identically under both routes produces a single pill.
    When the PRSA route already has a pill for a key, the PG-team-route pill
    is dropped (PRSA wins on metadata — Issue Rating, Status, Title).
    Same Issue ID at different entities or under different L2s produces
    independent pills, which is the union behaviour the user requested.
    """
    prsa_route = prsa_route or {}
    pg_team_route = pg_team_route or {}
    merged: dict[str, dict[str, list[dict]]] = {}
    seen_keys: set[tuple[str, str, str]] = set()

    for eid, by_l2 in prsa_route.items():
        for l2, items in by_l2.items():
            for item in items:
                iid = str(item.get("issue_id", "")).strip()
                key = (eid, l2, iid)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                merged.setdefault(eid, {}).setdefault(l2, []).append(item)

    added = 0
    for eid, by_l2 in pg_team_route.items():
        for l2, items in by_l2.items():
            for item in items:
                iid = str(item.get("issue_id", "")).strip()
                key = (eid, l2, iid)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                merged.setdefault(eid, {}).setdefault(l2, []).append(item)
                added += 1

    total = sum(len(items) for by_l2 in merged.values() for items in by_l2.values())
    logger.info(
        f"  PG gap indexes merged: {len(merged)} entities, {total} total pills "
        f"({added} added by PG team FND route)"
    )
    return merged


def ingest_bma(filepath: str, column_name_map: dict) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Read a Business Monitoring Activities file.

    Returns ``(df, blank_ae_orphans_df, source_filename)``. ``df`` is filtered
    to rows with planned completion date >= cutoff (default 2025-07-01); rows
    with blank entity IDs remain in ``df`` (BMA does not drop them) but are
    additionally captured into ``blank_ae_orphans_df`` so they surface in the
    Upstream Tagging Gaps tab.

    Column names are read from ``column_name_map`` (sourced from
    ``taxonomy_config.yaml`` → ``columns.bma``).
    """
    from pathlib import Path as _Path

    logger.info(f"Reading BM Activities from {filepath}")
    if filepath.endswith(".csv"):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)
    df.columns = [c.strip() for c in df.columns]
    source_filename = _Path(filepath).name

    entity_col = column_name_map.get("entity_id", "Related Audit Entity")
    date_col = column_name_map.get("planned_completion_date",
                                   "Planned Instance Completion Date")
    instance_col = column_name_map.get("instance_id", "Activity Instance ID")

    # Validate required columns
    required = [instance_col, date_col]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"BMA file missing required columns: {missing}")

    # Warn about blank entity IDs
    blank_ae_orphans = pd.DataFrame()
    if entity_col in df.columns:
        blank_mask = df[entity_col].isna() | (df[entity_col].astype(str).str.strip() == "")
        blank_count = blank_mask.sum()
        if blank_count:
            logger.warning(f"  {blank_count} BMA row(s) have blank entity IDs "
                           f"(will be kept for completeness; captured to "
                           f"Upstream Tagging Gaps)")
            blank_ae_orphans = df[blank_mask].copy()

    # Filter by planned completion date >= cutoff
    pre_filter = len(df)
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    cutoff_str = column_name_map.get("min_completion_date", "2025-07-01")
    cutoff = pd.Timestamp(cutoff_str)
    date_valid = df[date_col].notna()
    date_pass = df[date_col] >= cutoff
    filtered_out = date_valid & ~date_pass
    logger.info(f"  Filtered out {filtered_out.sum()} row(s) with planned date "
                f"before {cutoff.date()}")
    df = df[~date_valid | date_pass]  # keep NaT dates + dates >= cutoff

    logger.info(f"  Loaded {len(df)} BMA instance rows (from {pre_filter} total) "
                f"across {df[entity_col].nunique() if entity_col in df.columns else '?'} entities")

    # Re-filter the orphans DataFrame by the same date cutoff so we don't
    # surface ancient blank-AE rows that are out of cycle anyway.
    if not blank_ae_orphans.empty and date_col in blank_ae_orphans.columns:
        blank_ae_orphans[date_col] = pd.to_datetime(blank_ae_orphans[date_col], errors="coerce")
        keep = blank_ae_orphans[date_col].isna() | (blank_ae_orphans[date_col] >= cutoff)
        blank_ae_orphans = blank_ae_orphans[keep]

    return df, blank_ae_orphans, source_filename


def ingest_gra_raps(filepath: str, column_name_map: dict) -> pd.DataFrame:
    """Read a GRA RAPs (regulatory findings) file.

    Returns the raw DataFrame with basic validation.

    Column names are read from ``column_name_map`` (sourced from
    ``taxonomy_config.yaml`` → ``columns.gra_raps``).
    """
    logger.info(f"Reading GRA RAPs from {filepath}")
    if filepath.endswith(".csv"):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)
    df.columns = [c.strip() for c in df.columns]

    entity_col = column_name_map.get("entity_id", "Audit Entity ID")
    rap_id_col = column_name_map.get("rap_id", "RAP ID")
    rap_header_col = column_name_map.get("rap_header", "RAP Header")

    # Validate required columns
    required = [rap_id_col, rap_header_col]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"GRA RAPs file missing required columns: {missing}")

    # Filter out rows with blank RAP ID — these are entity-level rows with no RAP
    blank_rap_mask = df[rap_id_col].isna() | (df[rap_id_col].astype(str).str.strip().str.lower().isin(["", "nan", "none"]))
    blank_rap_count = blank_rap_mask.sum()
    if blank_rap_count:
        logger.info(f"  Filtered out {blank_rap_count} row(s) with blank RAP ID")
        df = df[~blank_rap_mask]

    # Warn about blank entity IDs
    if entity_col in df.columns:
        blank_mask = df[entity_col].isna() | (df[entity_col].astype(str).str.strip() == "")
        blank_count = blank_mask.sum()
        if blank_count:
            logger.warning(f"  {blank_count} GRA RAPs row(s) have blank entity IDs "
                           f"(will be kept for completeness)")

    logger.info(f"  Loaded {len(df)} GRA RAPs rows "
                f"across {df[entity_col].nunique() if entity_col in df.columns else '?'} entities")

    return df


def ingest_rco_overrides(filepath: str) -> dict:
    """Load RCO overrides from Excel/CSV.

    Returns dict: {(entity_id, l2): {
        "status": str, "rating": str or None,
    }}
    """
    logger.info(f"Loading RCO overrides from {filepath}")
    if filepath.endswith(".csv"):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)
    df.columns = [str(c).strip() for c in df.columns]

    df["entity_id"] = df["entity_id"].astype(str).str.strip()

    valid_statuses = {"Confirmed Applicable", "Confirmed Not Applicable", "Escalate"}
    overrides = {}
    skipped = 0

    for _, row in df.iterrows():
        raw_l2 = str(row.get("l2_risk", "")).strip()
        normalized = normalize_l2_name(raw_l2) if raw_l2 not in L2_TO_L1 else raw_l2
        if normalized is None or normalized not in L2_TO_L1:
            logger.warning(f"  RCO override skipped: unrecognized L2 '{raw_l2}' "
                           f"(entity={row['entity_id']})")
            skipped += 1
            continue

        status = str(row.get("rco_status", "")).strip()
        if status not in valid_statuses:
            logger.warning(f"  RCO override skipped: invalid status '{status}' "
                           f"(entity={row['entity_id']}, l2={normalized})")
            skipped += 1
            continue

        key = (str(row["entity_id"]), normalized)
        overrides[key] = {
            "status": status,
            "rating": str(row.get("rco_rating", "")).strip() or None,
            "source": "rco_override",
            "rco_name": str(row.get("rco_name", "")).strip(),
            "comment": str(row.get("rco_comment", "")).strip(),
        }

    logger.info(f"  Loaded {len(overrides)} RCO overrides ({skipped} skipped)")
    return overrides


def ingest_optro_overrides(filepath: str, column_name_map: dict) -> tuple[dict, dict]:
    """Read Optro export — audit team's confirmed L2 assessments.

    Risk Rating doubles as applicability:
        Low/Medium/High/Critical → applicable
        N/A / blank              → not_applicable

    Returns:
        (overrides, coverage)
        overrides: {(entity_id, l2_risk): {
            "applicability": "applicable" | "not_applicable",
            "risk_rating": str | None,
            "likelihood": int | None,
            "impact_financial": int | None,
            "impact_reputational": int | None,
            "impact_consumer_harm": int | None,
            "impact_regulatory": int | None,
            "team_rationale": str,
        }}
        coverage: {entity_id: set of L2 names submitted by the team}
            Used downstream to enforce all-or-nothing per entity.
    """
    logger.info(f"Loading Optro overrides from {filepath}")
    if filepath.endswith(".csv"):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)
    df.columns = [str(c).strip() for c in df.columns]

    eid_col = column_name_map.get("entity_id", "Audit Entity ID")
    l2_col = column_name_map.get("l2_risk", "Risk Category")
    rating_col = column_name_map.get("risk_rating", "Inherent Risk Rating")

    required = [eid_col, l2_col, rating_col]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"Optro export missing required columns: {missing}. Update YAML "
            f"columns.optro to match actual export header text."
        )

    # Optional columns — read if present, blank otherwise
    likelihood_col = column_name_map.get("likelihood", "Likelihood")
    if_col = column_name_map.get("impact_financial", "Financial Impact")
    ir_col = column_name_map.get("impact_reputational", "Reputational Impact")
    ic_col = column_name_map.get("impact_consumer_harm", "Consumer Harm Impact")
    irg_col = column_name_map.get("impact_regulatory", "Regulatory Impact")
    rationale_col = column_name_map.get("team_rationale", "Rationale")

    df[eid_col] = df[eid_col].astype(str).str.strip()
    raw_l2 = df[l2_col].copy()
    df[l2_col] = df[l2_col].apply(normalize_l2_name)

    # Drop rows whose L2 didn't normalize (warn so the user can fix the export)
    unmapped_mask = df[l2_col].isna()
    if unmapped_mask.any():
        dropped_values = raw_l2[unmapped_mask].value_counts()
        logger.warning(f"  Dropped {unmapped_mask.sum()} Optro rows with unmappable L2 names:")
        for val, count in dropped_values.items():
            logger.warning(f"    '{val}': {count}")
        df = df[~unmapped_mask]

    overrides: dict[tuple[str, str], dict] = {}
    coverage: dict[str, set[str]] = {}

    rating_to_int = {"low": 1, "medium": 2, "high": 3, "critical": 4}

    def _to_int_rating(val) -> int | None:
        s = str(val).strip().lower()
        if not s or s in ("nan", "none", "n/a", "na", ""):
            return None
        return rating_to_int.get(s)

    for _, row in df.iterrows():
        eid = str(row[eid_col]).strip()
        l2 = row[l2_col]
        if not eid or eid.lower() in ("nan", "none", ""):
            continue

        raw_rating = str(row.get(rating_col, "")).strip()
        rating_lower = raw_rating.lower()
        # Applicability derived from rating presence
        if rating_lower in ("", "nan", "none", "n/a", "na", "not applicable"):
            applicability = "not_applicable"
            risk_rating = None
        else:
            applicability = "applicable"
            risk_rating = raw_rating  # preserve original casing for display

        entry: dict = {
            "applicability": applicability,
            "risk_rating": risk_rating,
            "likelihood": _to_int_rating(row.get(likelihood_col)),
            "impact_financial": _to_int_rating(row.get(if_col)),
            "impact_reputational": _to_int_rating(row.get(ir_col)),
            "impact_consumer_harm": _to_int_rating(row.get(ic_col)),
            "impact_regulatory": _to_int_rating(row.get(irg_col)),
            "team_rationale": str(row.get(rationale_col, "")).strip(),
        }
        overrides[(eid, l2)] = entry
        coverage.setdefault(eid, set()).add(l2)

    n_applicable = sum(1 for v in overrides.values() if v["applicability"] == "applicable")
    n_na = len(overrides) - n_applicable
    logger.info(
        f"  Loaded {len(overrides)} Optro overrides across {len(coverage)} entities "
        f"({n_applicable} applicable, {n_na} not applicable)"
    )
    return overrides, coverage
