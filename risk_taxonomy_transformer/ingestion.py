"""
Data ingestion functions for the Risk Taxonomy Transformer.

Handles reading legacy data, sub-risk descriptions, LLM overrides, findings,
ORE mappings, enterprise findings, and RCO overrides from Excel/CSV files.
Also builds the nested lookup indexes used downstream.
"""

from __future__ import annotations

import logging
from collections import defaultdict

import pandas as pd

from risk_taxonomy_transformer.config import CROSSWALK_CONFIG, L2_TO_L1
from risk_taxonomy_transformer.normalization import normalize_l2_name

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


def ingest_sub_risks(filepath: str, entity_id_col: str, legacy_l1_col: str,
                     risk_desc_col: str, risk_id_col: str = None,
                     rating_col: str = None) -> pd.DataFrame:
    """Read sub-risk descriptions file.

    Expected columns (configure names in main()):
      - entity_id_col:  Audit Entity ID
      - risk_id_col:    Risk ID (optional, for traceability)
      - risk_desc_col:  Risk description text
      - legacy_l1_col:  Legacy L1 pillar(s), tab-separated if multiple
      - rating_col:     Inherent risk rating (optional, not used for scoring)

    Returns DataFrame with one row per sub-risk, with legacy L1s exploded
    so each row maps to a single L1.
    """
    logger.info(f"Reading sub-risk descriptions from {filepath}")
    if filepath.endswith(".csv"):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)
    df.columns = [c.strip() for c in df.columns]
    logger.info(f"  Loaded {len(df)} sub-risk rows")

    # Rename to standard internal names
    col_map = {entity_id_col: "entity_id", risk_desc_col: "risk_description",
               legacy_l1_col: "legacy_l1_raw"}
    if risk_id_col:
        col_map[risk_id_col] = "risk_id"
    if rating_col:
        col_map[rating_col] = "sub_risk_rating"
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

    logger.info(f"  After L1 explosion: {len(df)} sub-risk-to-L1 rows")
    logger.info(f"  Unique entities with sub-risks: {df['entity_id'].nunique()}")

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


def build_sub_risk_index(sub_risks_df: pd.DataFrame) -> dict:
    """Build lookup: {entity_id: {legacy_pillar: [list of risk descriptions]}}.

    This enables fast lookup during entity transformation.
    """
    index = _build_nested_index(
        sub_risks_df, "entity_id", "legacy_l1",
        value_fn=lambda row: (
            str(row.get("risk_id", "")),
            row["risk_description"],
        ),
    )

    # Diagnostic: show which sub-risk L1 values match crosswalk keys
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
        logger.info(f"  Crosswalk keys with NO sub-risks: {sorted(unused)}")

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
            determination = str(row.get("determination", "applicable")).strip().lower()
            if determination not in ("applicable", "not_applicable"):
                determination = "applicable"
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


def ingest_findings(filepath: str, column_name_map: dict) -> pd.DataFrame:
    """Read findings/issues data.

    Expected columns (configure names via column_name_map):
      entity_id, issue_id, l2_risk, severity, status, issue_title, remediation_date
    """
    logger.info(f"Reading findings from {filepath}")
    if filepath.endswith(".csv"):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)
    df.columns = [c.strip() for c in df.columns]

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
    df = df[~unmapped_mask]
    dropped = unmapped_mask.sum()
    if dropped > 0:
        dropped_values = raw_l2[unmapped_mask].value_counts()
        logger.info(f"  Dropped {dropped} findings with unmappable or blank L2 risk categories:")
        for val, count in dropped_values.items():
            logger.info(f"    '{val}': {count}")

    # Validate remaining L2 names match taxonomy
    valid = df["l2_risk"].isin(L2_TO_L1)
    invalid_l2s = df[~valid]["l2_risk"].unique()
    if len(invalid_l2s) > 0:
        logger.warning(f"  Findings L2s NOT in taxonomy (will be ignored): {list(invalid_l2s)}")
    df = df[valid]

    logger.info(f"  Loaded {len(df)} valid findings across {df['entity_id'].nunique()} entities")
    logger.info(f"  L2s covered by findings: {sorted(df['l2_risk'].unique())}")
    return df


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


def ingest_ore_mappings(filepath: str, confidence_filter: list[str] | None = None) -> pd.DataFrame:
    """Read ORE mapper output and filter to mapped statuses.

    The ore_mapper now outputs a semicolon-separated 'Mapped L2s' column
    (one row per ORE). This function explodes that into one row per
    (entity_id, l2_risk) pair for downstream indexing.

    Returns DataFrame with columns: entity_id, l2_risk, event_id, event_title, event_description.
    """
    logger.info(f"Reading ORE mappings from {filepath}")
    df = pd.read_excel(filepath, sheet_name="All Mappings")
    df.columns = [c.strip() for c in df.columns]

    required = ["Event ID", "Audit Entity ID", "Status", "Mapped L2s"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"ORE mapping file missing columns: {missing}")

    # Filter to desired statuses
    if confidence_filter is None:
        confidence_filter = ["Mapped"]
    pre_filter = len(df)
    df = df[df["Status"].isin(confidence_filter)]
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
    df["l2_risk"] = df["l2_risk"].apply(normalize_l2_name)
    df = df[df["l2_risk"].notna()]

    logger.info(f"  Loaded {len(df)} ORE mappings across {df['entity_id'].nunique()} entities")
    return df


def build_ore_index(ore_df: pd.DataFrame) -> dict:
    """Build lookup: {entity_id: {l2_risk: [list of ORE dicts]}}.

    Each ORE dict: {event_id, event_title, event_description}
    """
    def _ore_from_row(row):
        return {
            "event_id": str(row.get("event_id", "")),
            "event_title": str(row.get("Event Title", ""))[:200],
            "event_description": str(row.get("Event Description", ""))[:200],
        }

    index = _build_nested_index(ore_df, "entity_id", "l2_risk",
                                value_fn=_ore_from_row)
    total = sum(len(fs) for eid_map in index.values() for fs in eid_map.values())
    logger.info(f"  ORE index built: {len(index)} entities, {total} total OREs")
    return index


def ingest_enterprise_findings(filepath: str) -> pd.DataFrame:
    """Read enterprise findings and normalize L2 names.

    Expected columns: entity_id, l2_risk, finding_id, severity, status, finding_title.
    """
    logger.info(f"Reading enterprise findings from {filepath}")
    if filepath.endswith(".csv"):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)
    df.columns = [c.strip() for c in df.columns]

    # Support flexible column naming
    col_map = {
        "Audit Entity ID": "entity_id",
        "Entity ID": "entity_id",
        "L2 Risk": "l2_risk",
        "L2": "l2_risk",
        "Finding ID": "finding_id",
        "Issue ID": "finding_id",
        "Severity": "severity",
        "Status": "status",
        "Finding Title": "finding_title",
        "Issue Title": "finding_title",
    }
    rename = {}
    for actual, internal in col_map.items():
        if actual in df.columns and internal not in df.columns:
            rename[actual] = internal
    df = df.rename(columns=rename)

    required = ["entity_id", "l2_risk"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Enterprise findings file missing columns: {missing}")

    df["entity_id"] = df["entity_id"].astype(str).str.strip()
    df["l2_risk"] = df["l2_risk"].apply(normalize_l2_name)
    df = df[df["l2_risk"].notna()]

    logger.info(f"  Loaded {len(df)} enterprise findings across {df['entity_id'].nunique()} entities")
    return df


def build_enterprise_findings_index(ent_df: pd.DataFrame) -> dict:
    """Build lookup: {entity_id: {l2_risk: [list of finding dicts]}}.

    Each finding dict: {finding_id, severity, status, finding_title}
    """
    def _ent_finding_from_row(row):
        return {
            "finding_id": str(row.get("finding_id", "")),
            "severity": str(row.get("severity", "")),
            "status": str(row.get("status", "")),
            "finding_title": str(row.get("finding_title", "")),
        }

    index = _build_nested_index(ent_df, "entity_id", "l2_risk",
                                value_fn=_ent_finding_from_row)
    total = sum(len(fs) for eid_map in index.values() for fs in eid_map.values())
    logger.info(f"  Enterprise findings index built: {len(index)} entities, {total} total findings")
    return index


def ingest_prsa(filepath: str) -> pd.DataFrame:
    """Read a PRSA Frankenstein report (AE + Issues + PRSA controls in one file).

    Returns the raw DataFrame with an added 'Other AEs With This PRSA' column
    showing cross-AE visibility for each PRSA.

    Expected columns:
      AE ID, AE Name, All PRSAs Tagged to AE (multi-value, newline-separated),
      Issue ID, Issue Rating, Issue Status, Issue Breakdown Type,
      Control ID (PRSA), PRSA ID, Process Title, Control Title, ...
    """
    logger.info(f"Reading PRSA report from {filepath}")
    if filepath.endswith(".csv"):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)
    df.columns = [c.strip() for c in df.columns]

    required = ["AE ID", "PRSA ID", "Issue ID"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"PRSA report missing required columns: {missing}")

    df["AE ID"] = df["AE ID"].astype(str).str.strip()
    df["PRSA ID"] = df["PRSA ID"].astype(str).str.strip()

    # Build PRSA → AE mapping from the multi-value "All PRSAs Tagged to AE" column
    prsa_to_aes: dict[str, set[str]] = defaultdict(set)
    tagged_col = "All PRSAs Tagged to AE"
    if tagged_col in df.columns:
        # Collect from all rows (each AE may repeat, but the tag list is the same)
        seen_aes = set()
        for _, row in df.iterrows():
            ae_id = str(row["AE ID"]).strip()
            if ae_id in seen_aes:
                continue
            seen_aes.add(ae_id)
            raw = str(row[tagged_col])
            if raw and raw != "nan":
                for prsa_id in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
                    prsa_id = prsa_id.strip()
                    if prsa_id:
                        prsa_to_aes[prsa_id].add(ae_id)

    # Add cross-AE column: for each row's PRSA ID, list other AEs that share it
    other_aes = []
    for _, row in df.iterrows():
        ae_id = str(row["AE ID"]).strip()
        prsa_id = str(row["PRSA ID"]).strip()
        shared = sorted(prsa_to_aes.get(prsa_id, set()) - {ae_id})
        other_aes.append(", ".join(shared) if shared else "")
    df["Other AEs With This PRSA"] = other_aes

    logger.info(f"  Loaded {len(df)} PRSA issue-control rows across "
                f"{df['AE ID'].nunique()} entities")
    logger.info(f"  Unique PRSAs: {df['PRSA ID'].nunique()}, "
                f"Unique issues: {df['Issue ID'].nunique()}")

    # Log cross-AE shared PRSAs
    shared_prsas = {p: aes for p, aes in prsa_to_aes.items() if len(aes) > 1}
    if shared_prsas:
        logger.info(f"  PRSAs shared across AEs: {len(shared_prsas)}")
        for prsa_id, aes in sorted(shared_prsas.items()):
            logger.info(f"    {prsa_id}: {sorted(aes)}")

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
