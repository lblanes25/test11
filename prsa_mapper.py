"""
PRSA-to-L2 Risk Mapper
======================
Maps PRSA (Process Risk Self Assessment) issues to new L2 risk categories
using spaCy semantic similarity (en_core_web_lg word vectors). Each issue's
text (Issue Description + Control Title + Process Title) is compared against
each L2 definition.

Each issue can map to multiple L2s when the text legitimately spans more
than one risk category. Raw scores are replaced with plain-language
mapping statuses. Every item that passes the similarity floor is presented
as Needs Review (the tool does not assert a positive-confidence band);
items below the floor are No Match (excluded). Scores are retained in the
hidden Raw Scores sheet for traceability.

Usage:
    python prsa_mapper.py

Input:
    - data/input/L2_Risk_Taxonomy.xlsx (L2 definitions)
    - data/input/prsa_report_*.xlsx (AE ID, Issue ID, Issue Description,
      Control Title, Process Title)

Output:
    - data/output/prsa_mapping_{timestamp}.xlsx
"""

import pandas as pd
import logging
from pathlib import Path
import spacy
import yaml

from risk_taxonomy_transformer.mapper_common import (
    MapperSpec,
    build_basic_summary_df,
    build_reference_vectors,
    classify_mappings,
    compute_mappings,
    determine_ambiguity_threshold,
    export_results,
    load_l2_definitions,
    write_orphans_sidecar,
)
from risk_taxonomy_transformer.utils import latest_input, log_run_provenance, spacy_model_label

_PROJECT_ROOT = Path(__file__).parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(_PROJECT_ROOT / "logs" / "prsa_mapping_log.txt", mode="w"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION (loaded from taxonomy_config.yaml)
# =============================================================================

_CONFIG_PATH = _PROJECT_ROOT / "config" / "taxonomy_config.yaml"
with open(_CONFIG_PATH, "r", encoding="utf-8") as _f:
    _cfg = yaml.safe_load(_f)

_prsa_cfg = _cfg.get("columns", {}).get("prsa_mapper", {})

# spaCy model — large model has 300-dimensional word vectors
SPACY_MODEL = _prsa_cfg.get("spacy_model", "en_core_web_lg")

# Margin threshold between top matches; None = auto-detect from data
AMBIGUITY_MARGIN_THRESHOLD = None

# Minimum similarity score for a match to be considered valid
MIN_SIMILARITY_SCORE = _prsa_cfg.get("min_similarity_score", 0.50)

# Retained for Raw Scores traceability only — no longer drives a user-facing
# confidence band (all floor-passing items are uniformly Needs Review).
HIGH_SIMILARITY_SCORE = _prsa_cfg.get("high_similarity_score", 0.75)

# PRSA file pattern
PRSA_FILE_PATTERN = _prsa_cfg.get("prsa_file_pattern", "prsa_report_*.xlsx")

# PRSA column names
PRSA_ID_COL = _prsa_cfg.get("issue_id", "Issue ID")
PRSA_ENTITY_COL = _prsa_cfg.get("ae_id", "AE ID")
PRSA_TITLE_COL = _prsa_cfg.get("issue_title", "Issue Title")
PRSA_DESC_COL = _prsa_cfg.get("issue_description", "Issue Description")
PRSA_CONTROL_COL = _prsa_cfg.get("control_title", "Control Title")
PRSA_PROCESS_COL = _prsa_cfg.get("process_title", "Process Title")
PRSA_RATING_COL = _prsa_cfg.get("issue_rating", "Issue Rating")
PRSA_STATUS_COL = _prsa_cfg.get("issue_status", "Issue Status")

# L2 taxonomy file
L2_TAXONOMY_FILE = _prsa_cfg.get("l2_taxonomy_file", "L2_Risk_Taxonomy.xlsx")


# =============================================================================
# SOURCE LOADING
# =============================================================================

def load_prsa_data(input_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Load PRSA data from the most recent matching file.

    Returns (df, orphans_df, source_filename) where orphans_df captures
    non-PG-flagged rows dropped for blank AE ID. PG-flagged blank-AE rows
    are NOT orphans — they're routed downstream to the PG Gaps tab.
    """
    filepath = latest_input(input_dir, [PRSA_FILE_PATTERN], log_label="PRSA report")
    if filepath is None:
        raise FileNotFoundError(
            f"No files matching '{PRSA_FILE_PATTERN}' found in {input_dir}")
    source_filename = filepath.name
    logger.info(f"Loading PRSA data from {filepath}")
    df = pd.read_excel(filepath)
    df.columns = [c.strip() for c in df.columns]

    required = [PRSA_ID_COL, PRSA_DESC_COL]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"PRSA file missing required columns: {missing}. "
                         f"Found: {list(df.columns)}")

    pre_count = len(df)

    # Clean text columns
    for col in [PRSA_ID_COL, PRSA_TITLE_COL, PRSA_DESC_COL,
                PRSA_CONTROL_COL, PRSA_PROCESS_COL]:
        if col in df.columns:
            df[col] = df[col].astype(str).fillna("").str.strip()
    if PRSA_STATUS_COL in df.columns:
        df[PRSA_STATUS_COL] = df[PRSA_STATUS_COL].astype(str).fillna("").str.strip()
    if PRSA_RATING_COL in df.columns:
        df[PRSA_RATING_COL] = df[PRSA_RATING_COL].astype(str).fillna("").str.strip()

    # Exclude closed issues — no need to map issues no longer actionable
    _CLOSED_STATUSES = {"closed", "canceled", "cancelled"}
    if PRSA_STATUS_COL in df.columns:
        closed_mask = df[PRSA_STATUS_COL].str.lower().isin(_CLOSED_STATUSES)
        if closed_mask.any():
            logger.info(f"  Excluded {closed_mask.sum()} closed PRSA issues")
            df = df[~closed_mask]

    # Drop rows with blank Issue ID
    df = df[~df[PRSA_ID_COL].isin(["", "nan"])]

    # Drop rows with blank entity — can't place without an AE
    # Per Lu's spec: PG-flagged blank-AE rows are NOT orphans (they're routed
    # to the PG Gaps tab). Only non-PG blank-AE rows count as orphans.
    orphans = pd.DataFrame()
    if PRSA_ENTITY_COL in df.columns:
        df[PRSA_ENTITY_COL] = df[PRSA_ENTITY_COL].astype(str).str.strip()
        no_entity = df[PRSA_ENTITY_COL].isin(["", "nan"])
        if no_entity.any():
            if "Is PG Gap" in df.columns:
                pg_flag = df["Is PG Gap"].map(
                    lambda v: bool(v) if isinstance(v, bool)
                    else str(v).strip().lower() in ("yes", "true", "1")
                )
            else:
                pg_flag = pd.Series([False] * len(df), index=df.index)
            orphan_mask = no_entity & ~pg_flag
            if orphan_mask.any():
                orphans = df[orphan_mask].copy()
            logger.info(f"  Dropped {no_entity.sum()} PRSA rows with blank AE ID "
                        f"({orphan_mask.sum()} non-PG orphans captured to sidecar)")
            df = df[~no_entity]
    else:
        logger.warning(f"  Column '{PRSA_ENTITY_COL}' not found — cannot filter by entity")

    # Build combined text: description + control title + process title
    def _combine(row):
        parts = []
        for col in [PRSA_DESC_COL, PRSA_CONTROL_COL, PRSA_PROCESS_COL]:
            if col in df.columns:
                val = str(row.get(col, "")).strip()
                if val and val.lower() not in ("", "nan", "none"):
                    parts.append(val)
        return ". ".join(parts)

    df["_combined_text"] = df.apply(_combine, axis=1)
    # Drop rows whose combined text is empty after concat
    blank_text = df["_combined_text"].str.strip() == ""
    if blank_text.any():
        logger.info(f"  Dropped {blank_text.sum()} PRSA rows with no text content")
        df = df[~blank_text]

    # Deduplicate by (AE, Issue ID) so we don't double-map the same issue
    # when a PRSA report lists one issue under multiple PRSA controls
    pre_dedup = len(df)
    df = df.drop_duplicates(subset=[PRSA_ENTITY_COL, PRSA_ID_COL], keep="first")
    if len(df) < pre_dedup:
        logger.info(f"  Deduplicated {pre_dedup} -> {len(df)} issue rows "
                    f"(one per AE+Issue ID)")

    logger.info(f"  Loaded {len(df)} PRSA issues with text content "
                f"(of {pre_count} total rows)")
    return df, orphans, source_filename


# =============================================================================
# SOURCE-SPECIFIC MAPPING HOOKS
# =============================================================================

def _prsa_text(issue_row: pd.Series) -> str:
    """Text to vectorize: the precomputed description+control+process concat."""
    return str(issue_row["_combined_text"])


def _prsa_record(issue_row: pd.Series) -> dict:
    """Build the PRSA-specific leading fields for a mapping record."""
    full_desc = str(issue_row.get(PRSA_DESC_COL, ""))
    full_desc = "" if full_desc == "nan" else full_desc

    rating = str(issue_row.get(PRSA_RATING_COL, "")) if PRSA_RATING_COL in issue_row.index else ""
    rating = "" if rating in ("", "nan", "none") else rating

    status = str(issue_row.get(PRSA_STATUS_COL, "")) if PRSA_STATUS_COL in issue_row.index else ""
    status = "" if status in ("", "nan", "none") else status

    return {
        "Issue ID": issue_row[PRSA_ID_COL],
        "AE ID": issue_row.get(PRSA_ENTITY_COL, ""),
        "Issue Title": issue_row.get(PRSA_TITLE_COL, ""),
        "Issue Description": full_desc[:200],
        "Issue Description Full": full_desc,
        "Issue Rating": rating,
        "Issue Status": status,
    }


_SPEC = MapperSpec(
    item_label="PRSA issues",
    output_prefix="prsa_mapping",
    min_similarity_score=MIN_SIMILARITY_SCORE,
    all_cols=[
        "Issue ID", "AE ID", "Issue Title", "Issue Description",
        "Issue Rating", "Issue Status",
        "Mapping Status", "Match Confidence", "Mapped L2s", "Mapped L2 Count",
        "Mapped L2 Definitions",
    ],
    review_fields=[
        ("Issue ID", "Issue ID"),
        ("AE ID", "AE ID"),
        ("Issue Title", "Issue Title"),
        ("Issue Description", "Issue Description Full"),
    ],
    review_columns=None,
    raw_cols=[
        "Issue ID", "AE ID", "Issue Title", "Issue Description Full",
        "Match 1 - L2", "Match 1 - Score",
        "Match 2 - L2", "Match 2 - Score",
        "Match 3 - L2", "Match 3 - Score",
        "Margin 1-2", "Margin 2-3",
        "Mapping Status", "Match Confidence", "Match 1 Valid",
    ],
    raw_rename={"Issue Description Full": "Issue Description"},
    all_width_overrides={
        "Issue Description": 60, "Issue Title": 30,
        "Mapped L2s": 50, "Mapped L2 Definitions": 60,
    },
    all_wrap_cols=["Issue Description", "Mapped L2s", "Mapped L2 Definitions"],
    review_width_overrides={
        "Issue Description": 60, "Issue Title": 30,
        "Candidate 1 Definition": 60, "Candidate 2 Definition": 60,
        "Candidate 3 Definition": 60,
        "Reviewer Notes": 30,
    },
    review_wrap_cols=[
        "Issue Description",
        "Candidate 1 Definition", "Candidate 2 Definition", "Candidate 3 Definition",
    ],
    raw_width_overrides={"Issue Description": 60, "Issue Title": 30},
    raw_wrap_cols=["Issue Description"],
)


# =============================================================================
# MAIN
# =============================================================================

def main():
    global AMBIGUITY_MARGIN_THRESHOLD

    input_dir = _PROJECT_ROOT / "data" / "input"
    output_dir = _PROJECT_ROOT / "data" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    (_PROJECT_ROOT / "logs").mkdir(parents=True, exist_ok=True)

    l2_df = load_l2_definitions(input_dir, L2_TAXONOMY_FILE)
    prsa_df, orphans_df, source_filename = load_prsa_data(input_dir)

    logger.info(f"Loading spaCy model: {SPACY_MODEL}")
    nlp = spacy.load(SPACY_MODEL)
    logger.info(f"  Model loaded: {spacy_model_label(nlp)} "
                f"({len(nlp.vocab.vectors)} vectors, "
                f"{nlp.vocab.vectors.shape[1]} dimensions)")
    log_run_provenance(logger, SPACY_MODEL)

    ref_vectors, l2_names, l2_definitions = build_reference_vectors(nlp, l2_df)

    mapping_df = compute_mappings(
        nlp, prsa_df, ref_vectors, l2_names, l2_definitions,
        text_fn=_prsa_text, record_fn=_prsa_record,
        item_label="PRSA issues", min_similarity_score=MIN_SIMILARITY_SCORE,
    )

    if AMBIGUITY_MARGIN_THRESHOLD is None:
        AMBIGUITY_MARGIN_THRESHOLD = determine_ambiguity_threshold(mapping_df)

    mapping_df = classify_mappings(mapping_df, AMBIGUITY_MARGIN_THRESHOLD,
                                   min_similarity_score=MIN_SIMILARITY_SCORE)

    total = len(mapping_df)
    needs_review = (mapping_df["Mapping Status"] == "Needs Review").sum()
    no_match = (mapping_df["Mapping Status"] == "No Match").sum()

    logger.info("=" * 60)
    logger.info("PRSA MAPPING COMPLETE")
    logger.info(f"  Total PRSA issues: {total}")
    if total:
        logger.info(f"  Needs Review: {needs_review} ({needs_review/total*100:.1f}%)")
        logger.info(f"  No Match: {no_match} ({no_match/total*100:.1f}%)")
    logger.info(f"  Ambiguity threshold: {AMBIGUITY_MARGIN_THRESHOLD:.4f}")
    logger.info("=" * 60)

    summary_df = build_basic_summary_df(
        mapping_df, AMBIGUITY_MARGIN_THRESHOLD, MIN_SIMILARITY_SCORE,
        total_label="Total PRSA Issues", item_word="issue",
    )
    output_path = export_results(
        mapping_df, AMBIGUITY_MARGIN_THRESHOLD, output_dir,
        spec=_SPEC, summary_df=summary_df,
    )

    if not orphans_df.empty:
        sidecar_path = write_orphans_sidecar(
            orphans_df, output_path, source_filename,
            id_col=PRSA_ID_COL, title_col=PRSA_TITLE_COL,
            status_col=PRSA_STATUS_COL, source_label="PRSA",
        )
        logger.info(f"  Orphans sidecar saved: {sidecar_path} ({len(orphans_df)} rows)")

    print(f"\nDone! Output: {output_path}")
    print(f"  Needs Review: {needs_review} | No Match: {no_match}")


if __name__ == "__main__":
    main()
