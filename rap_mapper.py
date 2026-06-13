"""
GRA RAP-to-L2 Risk Mapper
=========================
Maps GRA RAPs (Regulatory Action Plans) to new L2 risk categories using
spaCy semantic similarity (en_core_web_lg word vectors). Each RAP's text
(RAP Header + RAP Details) is compared against each L2 definition.

Each RAP can map to multiple L2s when the text legitimately spans more than
one risk category. Raw scores are replaced with plain-language mapping
statuses. Every item that passes the similarity floor is presented as
Needs Review (the tool does not assert a positive-confidence band); items
below the floor are No Match (excluded). Scores are retained in the hidden
Raw Scores sheet for traceability.

Usage:
    python rap_mapper.py

Input:
    - data/input/L2_Risk_Taxonomy.xlsx (L2 definitions)
    - data/input/gra_raps_*.xlsx (Audit Entity ID, RAP ID, RAP Header,
      RAP Details)

Output:
    - data/output/rap_mapping_{timestamp}.xlsx
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
        logging.FileHandler(_PROJECT_ROOT / "logs" / "rap_mapping_log.txt", mode="w"),
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

_rap_cfg = _cfg.get("columns", {}).get("rap_mapper", {})

# spaCy model — large model has 300-dimensional word vectors
SPACY_MODEL = _rap_cfg.get("spacy_model", "en_core_web_lg")

AMBIGUITY_MARGIN_THRESHOLD = None
MIN_SIMILARITY_SCORE = _rap_cfg.get("min_similarity_score", 0.50)
HIGH_SIMILARITY_SCORE = _rap_cfg.get("high_similarity_score", 0.75)

RAP_FILE_PATTERN = _rap_cfg.get("rap_file_pattern", "gra_raps_*.xlsx")

RAP_ID_COL = _rap_cfg.get("rap_id", "RAP ID")
RAP_ENTITY_COL = _rap_cfg.get("entity_id", "Audit Entity ID")
RAP_HEADER_COL = _rap_cfg.get("rap_header", "RAP Header")
RAP_DETAILS_COL = _rap_cfg.get("rap_details", "RAP Details")
RAP_RELATED_COL = _rap_cfg.get("related_exams_and_findings", "Related Exams and Findings")
RAP_STATUS_COL = _rap_cfg.get("rap_status", "RAP Status")

L2_TAXONOMY_FILE = _rap_cfg.get("l2_taxonomy_file", "L2_Risk_Taxonomy.xlsx")


# =============================================================================
# SOURCE LOADING
# =============================================================================

def load_rap_data(input_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Load GRA RAP data from the most recent matching file.

    Returns (df, orphans_df, source_filename) where orphans_df captures rows
    dropped for blank Audit Entity ID.
    """
    filepath = latest_input(input_dir, [RAP_FILE_PATTERN], log_label="GRA RAPs")
    if filepath is None:
        raise FileNotFoundError(
            f"No files matching '{RAP_FILE_PATTERN}' found in {input_dir}")
    source_filename = filepath.name
    logger.info(f"Loading RAP data from {filepath}")
    df = pd.read_excel(filepath)
    df.columns = [c.strip() for c in df.columns]

    required = [RAP_ID_COL]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"RAP file missing required columns: {missing}. "
                         f"Found: {list(df.columns)}")

    pre_count = len(df)

    # Clean text columns
    for col in [RAP_ID_COL, RAP_HEADER_COL, RAP_DETAILS_COL, RAP_RELATED_COL]:
        if col in df.columns:
            df[col] = df[col].astype(str).fillna("").str.strip()
    if RAP_STATUS_COL in df.columns:
        df[RAP_STATUS_COL] = df[RAP_STATUS_COL].astype(str).fillna("").str.strip()

    # Drop rows with blank RAP ID
    df = df[~df[RAP_ID_COL].isin(["", "nan"])]

    # Drop rows with blank entity — can't place without an entity
    orphans = pd.DataFrame()
    if RAP_ENTITY_COL in df.columns:
        df[RAP_ENTITY_COL] = df[RAP_ENTITY_COL].astype(str).str.strip()
        no_entity = df[RAP_ENTITY_COL].isin(["", "nan"])
        if no_entity.any():
            orphans = df[no_entity].copy()
            logger.info(f"  Dropped {no_entity.sum()} RAP rows with blank Audit Entity ID "
                        f"(captured to orphans sidecar)")
            df = df[~no_entity]
    else:
        logger.warning(f"  Column '{RAP_ENTITY_COL}' not found — cannot filter by entity")

    # Build combined text: header + details
    def _combine(row):
        parts = []
        for col in [RAP_HEADER_COL, RAP_DETAILS_COL]:
            if col in df.columns:
                val = str(row.get(col, "")).strip()
                if val and val.lower() not in ("", "nan", "none"):
                    parts.append(val)
        return ". ".join(parts)

    df["_combined_text"] = df.apply(_combine, axis=1)
    blank_text = df["_combined_text"].str.strip() == ""
    if blank_text.any():
        logger.info(f"  Dropped {blank_text.sum()} RAP rows with no text content")
        df = df[~blank_text]

    logger.info(f"  Loaded {len(df)} RAPs with text content (of {pre_count} total rows)")
    return df, orphans, source_filename


# =============================================================================
# SOURCE-SPECIFIC MAPPING HOOKS
# =============================================================================

def _rap_text(rap_row: pd.Series) -> str:
    """Text to vectorize: the precomputed header+details concat."""
    return str(rap_row["_combined_text"])


def _rap_record(rap_row: pd.Series) -> dict:
    """Build the RAP-specific leading fields for a mapping record."""
    details_full = str(rap_row.get(RAP_DETAILS_COL, ""))
    details_full = "" if details_full == "nan" else details_full

    status = str(rap_row.get(RAP_STATUS_COL, "")) if RAP_STATUS_COL in rap_row.index else ""
    status = "" if status in ("", "nan", "none") else status

    related = str(rap_row.get(RAP_RELATED_COL, "")) if RAP_RELATED_COL in rap_row.index else ""
    related = "" if related in ("", "nan", "none") else related

    return {
        "RAP ID": rap_row[RAP_ID_COL],
        "Audit Entity ID": rap_row.get(RAP_ENTITY_COL, ""),
        "RAP Header": rap_row.get(RAP_HEADER_COL, ""),
        "RAP Details": details_full[:200],
        "RAP Details Full": details_full,
        "Related Exams and Findings": related,
        "RAP Status": status,
    }


_SPEC = MapperSpec(
    item_label="RAPs",
    output_prefix="rap_mapping",
    min_similarity_score=MIN_SIMILARITY_SCORE,
    all_cols=[
        "RAP ID", "Audit Entity ID", "RAP Header", "RAP Details",
        "Related Exams and Findings", "RAP Status",
        "Mapping Status", "Match Confidence", "Mapped L2s", "Mapped L2 Count",
        "Mapped L2 Definitions",
    ],
    review_fields=[
        ("RAP ID", "RAP ID"),
        ("Audit Entity ID", "Audit Entity ID"),
        ("RAP Header", "RAP Header"),
        ("RAP Details", "RAP Details Full"),
    ],
    review_columns=None,
    raw_cols=[
        "RAP ID", "Audit Entity ID", "RAP Header", "RAP Details Full",
        "Match 1 - L2", "Match 1 - Score",
        "Match 2 - L2", "Match 2 - Score",
        "Match 3 - L2", "Match 3 - Score",
        "Margin 1-2", "Margin 2-3",
        "Mapping Status", "Match Confidence", "Match 1 Valid",
    ],
    raw_rename={"RAP Details Full": "RAP Details"},
    all_width_overrides={
        "RAP Details": 60, "RAP Header": 30,
        "Mapped L2s": 50, "Mapped L2 Definitions": 60,
        "Related Exams and Findings": 40,
    },
    all_wrap_cols=["RAP Details", "Mapped L2s", "Mapped L2 Definitions",
                   "Related Exams and Findings"],
    review_width_overrides={
        "RAP Details": 60, "RAP Header": 30,
        "Candidate 1 Definition": 60, "Candidate 2 Definition": 60,
        "Candidate 3 Definition": 60,
        "Reviewer Notes": 30,
    },
    review_wrap_cols=[
        "RAP Details",
        "Candidate 1 Definition", "Candidate 2 Definition", "Candidate 3 Definition",
    ],
    raw_width_overrides={"RAP Details": 60, "RAP Header": 30},
    raw_wrap_cols=["RAP Details"],
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
    rap_df, orphans_df, source_filename = load_rap_data(input_dir)

    logger.info(f"Loading spaCy model: {SPACY_MODEL}")
    nlp = spacy.load(SPACY_MODEL)
    logger.info(f"  Model loaded: {spacy_model_label(nlp)} "
                f"({len(nlp.vocab.vectors)} vectors, "
                f"{nlp.vocab.vectors.shape[1]} dimensions)")
    log_run_provenance(logger, SPACY_MODEL)

    ref_vectors, l2_names, l2_definitions = build_reference_vectors(nlp, l2_df)

    mapping_df = compute_mappings(
        nlp, rap_df, ref_vectors, l2_names, l2_definitions,
        text_fn=_rap_text, record_fn=_rap_record,
        item_label="RAPs", min_similarity_score=MIN_SIMILARITY_SCORE,
    )

    if AMBIGUITY_MARGIN_THRESHOLD is None:
        AMBIGUITY_MARGIN_THRESHOLD = determine_ambiguity_threshold(mapping_df)

    mapping_df = classify_mappings(mapping_df, AMBIGUITY_MARGIN_THRESHOLD,
                                   min_similarity_score=MIN_SIMILARITY_SCORE)

    total = len(mapping_df)
    needs_review = (mapping_df["Mapping Status"] == "Needs Review").sum()
    no_match = (mapping_df["Mapping Status"] == "No Match").sum()

    logger.info("=" * 60)
    logger.info("RAP MAPPING COMPLETE")
    logger.info(f"  Total RAPs: {total}")
    if total:
        logger.info(f"  Needs Review: {needs_review} ({needs_review/total*100:.1f}%)")
        logger.info(f"  No Match: {no_match} ({no_match/total*100:.1f}%)")
    logger.info(f"  Ambiguity threshold: {AMBIGUITY_MARGIN_THRESHOLD:.4f}")
    logger.info("=" * 60)

    summary_df = build_basic_summary_df(
        mapping_df, AMBIGUITY_MARGIN_THRESHOLD, MIN_SIMILARITY_SCORE,
        total_label="Total RAPs", item_word="RAP",
    )
    output_path = export_results(
        mapping_df, AMBIGUITY_MARGIN_THRESHOLD, output_dir,
        spec=_SPEC, summary_df=summary_df,
    )

    if not orphans_df.empty:
        sidecar_path = write_orphans_sidecar(
            orphans_df, output_path, source_filename,
            id_col=RAP_ID_COL, title_col=RAP_HEADER_COL,
            status_col=RAP_STATUS_COL, source_label="GRA RAPs",
        )
        logger.info(f"  Orphans sidecar saved: {sidecar_path} ({len(orphans_df)} rows)")

    print(f"\nDone! Output: {output_path}")
    print(f"  Needs Review: {needs_review} | No Match: {no_match}")


if __name__ == "__main__":
    main()
