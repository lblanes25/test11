"""
ORE-to-L2 Risk Mapper
=====================
Maps Operational Risk Events (OREs) to new L2 risk categories using
spaCy semantic similarity (en_core_web_lg word vectors).

Each ORE can map to multiple L2s when the event legitimately spans more
than one risk category. Raw scores are replaced with plain-language
mapping statuses. Every item that passes the similarity floor is presented
as Needs Review (the tool does not assert a positive-confidence band);
items below the floor are No Match (excluded). Scores are retained in the
hidden Raw Scores sheet for traceability.

Usage:
    python ore_mapper.py

Input:
    - data/input/L2_Risk_Taxonomy.xlsx (L2 definitions)
    - data/input/ORE_*.xlsx (Event ID, Event Title, Event Description / Summary)

Output:
    - data/output/ore_mapping_{timestamp}.xlsx
      Sheet 1: All Mappings (one row per ORE, reviewer-friendly)
      Sheet 2: Needs Review (side-by-side comparison for ambiguous OREs)
      Sheet 3: Summary (counts + plain-language explanation)
      Sheet 4: L2 Distribution (ORE counts per L2, multi-L2 exploded)
      Sheet 5: Raw Scores (hidden — development/threshold tuning only)
"""

import argparse
import pandas as pd
import logging
from pathlib import Path
import spacy
import yaml

from risk_taxonomy_transformer.mapper_common import (
    MapperSpec,
    build_reference_vectors,
    classify_mappings,
    compute_mappings,
    determine_ambiguity_threshold,
    export_results,
    load_l2_definitions,
    write_orphans_sidecar,
)
from risk_taxonomy_transformer.utils import _pick_latest, log_run_provenance, spacy_model_label

_PROJECT_ROOT = Path(__file__).parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(_PROJECT_ROOT / "logs" / "ore_mapping_log.txt", mode="w"),
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

# Margin threshold: if the score gap between 1st and 2nd match is below this,
# the ORE is flagged as ambiguous. Set to None to auto-detect from data.
AMBIGUITY_MARGIN_THRESHOLD = None

# Minimum similarity score for a match to be considered valid
MIN_SIMILARITY_SCORE = 0.50

# Retained for Raw Scores traceability only — no longer drives a user-facing
# confidence band (all floor-passing items are uniformly Needs Review).
HIGH_SIMILARITY_SCORE = 0.75

# Source-specific config — populated by set_active_source() at startup.
SPACY_MODEL = "en_core_web_lg"
# Resolved "name version" of the actually-loaded model; set in main() after
# spacy.load. Falls back to the configured name until the model loads.
RESOLVED_SPACY_MODEL = SPACY_MODEL
SOURCE_NAME = "ore"
ORE_FILE_PATTERN = ""
ORE_ID_COL = ""
ORE_TITLE_COL = ""
ORE_DESC_COL = ""
ORE_ENTITY_COL = ""
ORE_CLASS_COL = ""
ORE_STATUS_COL = ""
ORE_RISK_L2_COL = ""        # only ore_irm — empty for ore
ORE_LEGACY_EVENT_ID_COL = ""  # only ore_irm
L2_TAXONOMY_FILE = ""
OUTPUT_FILENAME_PREFIX = "ore_mapping"


def set_active_source(name: str):
    """Bind module-level mapper config to the named source (ore | ore_irm).

    Loads the corresponding YAML block from columns.{ore_mapper, ore_irm_mapper}
    and sets ORE_*_COL, file pattern, output filename prefix.
    """
    global SOURCE_NAME, ORE_FILE_PATTERN, ORE_ID_COL, ORE_TITLE_COL
    global ORE_DESC_COL, ORE_ENTITY_COL, ORE_CLASS_COL, ORE_STATUS_COL
    global ORE_RISK_L2_COL, ORE_LEGACY_EVENT_ID_COL
    global L2_TAXONOMY_FILE, SPACY_MODEL, OUTPUT_FILENAME_PREFIX

    SOURCE_NAME = name
    if name == "ore":
        cfg = _cfg.get("columns", {}).get("ore_mapper", {})
        ORE_FILE_PATTERN = cfg.get("ore_file_pattern", "ORE_*.xlsx")
        ORE_ID_COL = cfg.get("event_id", "Event ID")
        ORE_TITLE_COL = cfg.get("event_title", "Event Title")
        ORE_DESC_COL = cfg.get("event_description", "Event Description / Summary")
        ORE_ENTITY_COL = cfg.get("entity_id", "Audit Entity (Operational Risk Events)")
        ORE_CLASS_COL = cfg.get("event_classification", "Final Event Classification")
        ORE_STATUS_COL = cfg.get("event_status", "Event Status")
        ORE_RISK_L2_COL = ""
        ORE_LEGACY_EVENT_ID_COL = ""
        OUTPUT_FILENAME_PREFIX = "ore_mapping"
    elif name == "ore_irm":
        cfg = _cfg.get("columns", {}).get("ore_irm_mapper", {})
        ORE_FILE_PATTERN = cfg.get("ore_irm_file_pattern", "ORE_IRM_*.xlsx")
        ORE_ID_COL = cfg.get("ore_id", "ORE ID")
        ORE_TITLE_COL = cfg.get("ore_title", "ORE Title")
        ORE_DESC_COL = cfg.get("ore_description", "ORE Description")
        ORE_ENTITY_COL = ""  # no AE column — AE join happens at ingestion time
        ORE_CLASS_COL = ""    # IRM has Capture Status (display-only) — no severity class
        ORE_STATUS_COL = cfg.get("capture_status", "Capture Status")
        ORE_RISK_L2_COL = cfg.get("risk_level_2", "Risk Level 2")
        ORE_LEGACY_EVENT_ID_COL = cfg.get("legacy_event_id", "Legacy Event ID")
        OUTPUT_FILENAME_PREFIX = "ore_irm_mapping"
    else:
        raise ValueError(f"Unknown source: {name!r}; expected 'ore' or 'ore_irm'")

    SPACY_MODEL = cfg.get("spacy_model", "en_core_web_lg")
    L2_TAXONOMY_FILE = cfg.get("l2_taxonomy_file", "L2_Risk_Taxonomy.xlsx")


# Default to legacy ORE source so that imports of this module before main()
# runs (e.g., tests that import constants) still see populated globals.
set_active_source("ore")


# =============================================================================
# SOURCE LOADING
# =============================================================================

def load_ore_data(input_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Load ORE data from the most recent matching file.

    Returns (df, orphans_df, source_filename) where orphans_df captures rows
    dropped for blank Audit Entity ID. Empty orphans_df for ore_irm (IRM has
    no AE column at all; AE attribution happens at ingestion time via the
    legacy_risk_data 'IRM ORE ID' bridge).
    """
    # Match the configured pattern regardless of extension — IRM exports may
    # arrive as .csv or .xlsx. Glob the pattern's stem against both suffixes.
    stem = ORE_FILE_PATTERN.rsplit(".", 1)[0]
    ore_files = sorted(
        set(input_dir.glob(f"{stem}.xlsx")) | set(input_dir.glob(f"{stem}.csv")))
    # The legacy ORE pattern (ORE_*) also matches ORE_IRM_* — filter those out
    # when running the legacy source so the IRM file doesn't shadow the legacy
    # file. The IRM mapper has its own dedicated pattern.
    if SOURCE_NAME == "ore":
        ore_files = [f for f in ore_files if not f.name.upper().startswith("ORE_IRM_")]
    filepath = _pick_latest(ore_files, log_label=f"{SOURCE_NAME} source data")
    if filepath is None:
        raise FileNotFoundError(
            f"No files matching '{stem}.xlsx' or '{stem}.csv' found in {input_dir}")
    source_filename = filepath.name
    logger.info(f"Loading ORE data from {filepath}")
    df = (pd.read_csv(filepath) if filepath.suffix.lower() == ".csv"
          else pd.read_excel(filepath))
    # Strip whitespace and any leading "*" prefix some ORE exports use on
    # Event Title / Event Description / Summary headers.
    df.columns = [str(c).strip().lstrip("*").strip() for c in df.columns]

    # Validate required columns
    required = [ORE_ID_COL, ORE_TITLE_COL, ORE_DESC_COL]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"ORE file missing required columns: {missing}. "
                         f"Found: {list(df.columns)}")

    pre_count = len(df)

    # Clean data
    df[ORE_ID_COL] = df[ORE_ID_COL].astype(str).str.strip()
    df[ORE_TITLE_COL] = df[ORE_TITLE_COL].astype(str).fillna("").str.strip()
    df[ORE_DESC_COL] = df[ORE_DESC_COL].astype(str).fillna("").str.strip()
    if ORE_CLASS_COL in df.columns:
        df[ORE_CLASS_COL] = df[ORE_CLASS_COL].astype(str).fillna("").str.strip()
    if ORE_STATUS_COL in df.columns:
        df[ORE_STATUS_COL] = df[ORE_STATUS_COL].astype(str).fillna("").str.strip()

    # Exclude closed OREs — no need to map events that are no longer active.
    _CLOSED_STATUSES = {"closed", "canceled", "draft canceled", "draft expired",
                        "draft", "pending cancelation by event admin"}
    if SOURCE_NAME != "ore_irm" and ORE_STATUS_COL in df.columns:
        closed_mask = df[ORE_STATUS_COL].str.lower().isin(_CLOSED_STATUSES)
        if closed_mask.any():
            logger.info(f"  Excluded {closed_mask.sum()} closed OREs (statuses: "
                        f"{df.loc[closed_mask, ORE_STATUS_COL].unique().tolist()})")
            df = df[~closed_mask]

    # Drop rows with no meaningful text
    df = df[~((df[ORE_TITLE_COL].isin(["", "nan"])) &
              (df[ORE_DESC_COL].isin(["", "nan"])))]
    df = df[~df[ORE_ID_COL].isin(["", "nan"])]

    # Drop OREs with no Audit Entity ID — can't place in entity evidence briefs.
    # IRM source has no AE column at all; AE attribution is established at
    # ingestion time via the legacy_risk_data 'IRM ORE ID' bridge.
    orphans = pd.DataFrame()
    if SOURCE_NAME != "ore_irm":
        if ORE_ENTITY_COL in df.columns:
            df[ORE_ENTITY_COL] = df[ORE_ENTITY_COL].astype(str).str.strip()
            no_entity = df[ORE_ENTITY_COL].isin(["", "nan"])
            if no_entity.any():
                orphans = df[no_entity].copy()
                logger.info(f"  Dropped {no_entity.sum()} OREs with blank Audit Entity ID "
                            f"(captured to orphans sidecar)")
                df = df[~no_entity]
        else:
            logger.warning(f"  Column '{ORE_ENTITY_COL}' not found — cannot filter by entity")

    logger.info(f"  Loaded {len(df)} OREs with text content (of {pre_count} total rows)")
    return df, orphans, source_filename


# =============================================================================
# SOURCE-SPECIFIC MAPPING HOOKS
# =============================================================================

def _ore_text(ore_row: pd.Series) -> str:
    """Build ORE text to vectorize: title + description."""
    title = str(ore_row[ORE_TITLE_COL])
    desc = str(ore_row[ORE_DESC_COL])
    title = "" if title == "nan" else title
    desc = "" if desc == "nan" else desc
    return f"{title}. {desc}" if desc else title


def _ore_record(ore_row: pd.Series) -> dict:
    """Build the ORE-specific leading fields for a mapping record.

    Stores both truncated (200-char) and full event descriptions.
    """
    full_desc = str(ore_row[ORE_DESC_COL])
    full_desc = "" if full_desc == "nan" else full_desc

    # Classification is optional — may not exist in older ORE files
    cls_raw = str(ore_row.get(ORE_CLASS_COL, "")) if ORE_CLASS_COL in ore_row.index else ""
    cls_val = "" if cls_raw in ("", "nan", "none") else cls_raw

    # Event Status is optional — may not exist in older ORE files
    status_raw = str(ore_row.get(ORE_STATUS_COL, "")) if ORE_STATUS_COL in ore_row.index else ""
    status_val = "" if status_raw in ("", "nan", "none") else status_raw

    return {
        "Event ID": ore_row[ORE_ID_COL],
        "Audit Entity ID": (ore_row.get(ORE_ENTITY_COL, "") if ORE_ENTITY_COL else ""),
        "Event Title": ore_row[ORE_TITLE_COL],
        "Event Description": full_desc[:200],
        "Event Description Full": full_desc,
        "Final Event Classification": cls_val,
        "Event Status": status_val,
    }


def _build_spec() -> MapperSpec:
    """Build the export spec from the currently bound source config."""
    return MapperSpec(
        item_label="OREs",
        output_prefix=OUTPUT_FILENAME_PREFIX,
        min_similarity_score=MIN_SIMILARITY_SCORE,
        all_cols=[
            "Event ID", "Audit Entity ID", "Event Title", "Event Description",
            "Final Event Classification", "Event Status",
            "Mapping Status", "Match Confidence", "Mapped L2s", "Mapped L2 Count",
            "Mapped L2 Definitions",
        ],
        review_fields=[
            ("Event ID", "Event ID"),
            ("Audit Entity ID", "Audit Entity ID"),
            ("Event Title", "Event Title"),
            ("Event Description", "Event Description Full"),
        ],
        review_columns=[
            "Event ID", "Audit Entity ID", "Event Title", "Event Description",
            "Match Confidence",
            "Candidate 1 L2", "Candidate 1 Definition", "Candidate 1 Applies",
            "Candidate 2 L2", "Candidate 2 Definition", "Candidate 2 Applies",
            "Candidate 3 L2", "Candidate 3 Definition", "Candidate 3 Applies",
            "Reviewer Notes",
        ],
        raw_cols=[
            "Event ID", "Audit Entity ID", "Event Title", "Event Description Full",
            "Match 1 - L2", "Match 1 - Score",
            "Match 2 - L2", "Match 2 - Score",
            "Match 3 - L2", "Match 3 - Score",
            "Margin 1-2", "Margin 2-3",
            "Mapping Status", "Match Confidence", "Match 1 Valid",
        ],
        raw_rename={"Event Description Full": "Event Description"},
        all_width_overrides={
            "Event Description": 60,
            "Event Title": 30,
            "Mapped L2s": 50,
            "Mapped L2 Definitions": 60,
        },
        all_wrap_cols=["Event Description", "Mapped L2s", "Mapped L2 Definitions"],
        review_width_overrides={
            "Event Description": 60,
            "Event Title": 30,
            "Candidate 1 Definition": 60,
            "Candidate 2 Definition": 60,
            "Candidate 3 Definition": 60,
            "Candidate 1 L2": 25,
            "Candidate 2 L2": 25,
            "Candidate 3 L2": 25,
            "Candidate 1 Applies": 15,
            "Candidate 2 Applies": 15,
            "Candidate 3 Applies": 15,
            "Reviewer Notes": 30,
        },
        review_wrap_cols=[
            "Event Description",
            "Candidate 1 Definition", "Candidate 2 Definition", "Candidate 3 Definition",
        ],
        raw_width_overrides={"Event Description": 60, "Event Title": 30},
        raw_wrap_cols=["Event Description"],
        summary_a_width=80,
        summary_wrap=True,
        review_row_height=60,
        reviewer_input_cols=[
            "Candidate 1 Applies", "Candidate 2 Applies", "Candidate 3 Applies",
            "Reviewer Notes",
        ],
    )


def _build_summary_df(mapping_df: pd.DataFrame) -> pd.DataFrame:
    """Build the ORE long-form Summary sheet (counts + how-this-works prose)."""
    total = len(mapping_df)
    needs_review_count = (mapping_df["Mapping Status"] == "Needs Review").sum()
    no_match_count = (mapping_df["Mapping Status"] == "No Match").sum()

    def pct(n):
        return f"{n} ({n/total*100:.1f}%)" if total > 0 else "0"

    nr_single = ((mapping_df["Mapping Status"] == "Needs Review") & (mapping_df["Mapped L2 Count"] == 1)).sum()
    nr_multi = ((mapping_df["Mapping Status"] == "Needs Review") & (mapping_df["Mapped L2 Count"] > 1)).sum()

    summary_data = {
        "Metric": [
            "Total OREs",
            "",
            "Needs Review",
            "  Mapped to single L2",
            "  Mapped to multiple L2s",
            "No Match",
            "",
            "",
            "HOW THIS WORKS",
            "",
            (f"This tool uses NLP word-vector similarity (spaCy {RESOLVED_SPACY_MODEL}) to suggest\n"
             "which L2 risk categories each ORE relates to. This is classical NLP — not\n"
             "generative AI / LLMs. Each ORE description is compared against the 23 L2\n"
             "definitions; matches are based on word-vector cosine similarity. These are\n"
             "starting points, not confirmed lookups, and must be reviewer-validated."),
            "",
            ("A single ORE can be suggested for more than one L2. For example, \"unauthorized\n"
             "payment processed due to system access control failure\" relates to both Fraud\n"
             "and Information and Cyber Security. When the tool detects this, it lists\n"
             "all L2s that fit."),
            "",
            ("Needs Review — Every ORE that passes the minimum similarity floor is marked\n"
             "Needs Review by design. NLP text similarity can be wrong (generic wording,\n"
             "L2 definitions that read similarly), so the tool does not assert a positive-\n"
             "confidence band. Open the Needs Review tab and confirm the L2 attribution\n"
             "for each ORE before relying on it. Similarity scores remain in the hidden\n"
             "Raw Scores tab for traceability."),
            "",
            ("No Match — Nothing fit well enough. The similarity scores were all below the\n"
             "minimum threshold. These are excluded from the pipeline. A reviewer can\n"
             "manually assign an L2 if needed."),
        ],
        "Value": [
            total,
            "",
            pct(needs_review_count),
            nr_single,
            nr_multi,
            pct(no_match_count),
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        ],
    }
    return pd.DataFrame(summary_data)


def _build_raw_stats_df(mapping_df: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """Build the score/margin distribution stats written below Raw Scores."""
    valid_scores = mapping_df[mapping_df["Match 1 Valid"]]["Match 1 - Score"]
    valid_margins = mapping_df[mapping_df["Match 1 Valid"]]["Margin 1-2"]
    valid_margins = valid_margins[valid_margins > 0]

    raw_stats = {
        "Metric": [
            "Score Distribution (valid Match 1)",
            "  Mean",
            "  Median",
            "  Min",
            "  Max",
            "",
            "Margin Distribution (valid, non-zero)",
            "  P25",
            "  P50 (Median)",
            "  P75",
            "",
            "Settings",
            "  Ambiguity Threshold",
            "  Min Similarity Score",
            "  spaCy Model",
        ],
        "Value": [
            "",
            f"{valid_scores.mean():.4f}" if len(valid_scores) > 0 else "N/A",
            f"{valid_scores.median():.4f}" if len(valid_scores) > 0 else "N/A",
            f"{valid_scores.min():.4f}" if len(valid_scores) > 0 else "N/A",
            f"{valid_scores.max():.4f}" if len(valid_scores) > 0 else "N/A",
            "",
            "",
            f"{valid_margins.quantile(0.25):.4f}" if len(valid_margins) > 0 else "N/A",
            f"{valid_margins.quantile(0.50):.4f}" if len(valid_margins) > 0 else "N/A",
            f"{valid_margins.quantile(0.75):.4f}" if len(valid_margins) > 0 else "N/A",
            "",
            "",
            f"{threshold:.4f}",
            MIN_SIMILARITY_SCORE,
            RESOLVED_SPACY_MODEL,
        ],
    }
    return pd.DataFrame(raw_stats)


# =============================================================================
# MAIN
# =============================================================================

def main():
    global AMBIGUITY_MARGIN_THRESHOLD

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", choices=["ore", "ore_irm"], default="ore",
        help="Source dataset to map (ore = legacy ORE_*.xlsx; ore_irm = ORE_IRM_*.xlsx)",
    )
    args = parser.parse_args()
    set_active_source(args.source)
    logger.info(f"ORE mapper running with source: {SOURCE_NAME}")

    input_dir = _PROJECT_ROOT / "data" / "input"
    output_dir = _PROJECT_ROOT / "data" / "output"

    # Load data
    l2_df = load_l2_definitions(input_dir, L2_TAXONOMY_FILE)
    ore_df, orphans_df, source_filename = load_ore_data(input_dir)

    # Load spaCy model
    global RESOLVED_SPACY_MODEL
    logger.info(f"Loading spaCy model: {SPACY_MODEL}")
    nlp = spacy.load(SPACY_MODEL)
    RESOLVED_SPACY_MODEL = spacy_model_label(nlp)
    logger.info(f"  Model loaded: {RESOLVED_SPACY_MODEL} "
                f"({len(nlp.vocab.vectors)} vectors, "
                f"{nlp.vocab.vectors.shape[1]} dimensions)")
    log_run_provenance(logger, SPACY_MODEL)

    # Build reference vectors from L2 definitions
    ref_vectors, l2_names, l2_definitions = build_reference_vectors(nlp, l2_df)

    # Compute similarity and get top-3 mappings
    mapping_df = compute_mappings(
        nlp, ore_df, ref_vectors, l2_names, l2_definitions,
        text_fn=_ore_text, record_fn=_ore_record,
        item_label="OREs", min_similarity_score=MIN_SIMILARITY_SCORE,
    )

    # Determine ambiguity threshold from data
    if AMBIGUITY_MARGIN_THRESHOLD is None:
        AMBIGUITY_MARGIN_THRESHOLD = determine_ambiguity_threshold(mapping_df)

    # Classify mappings
    mapping_df = classify_mappings(mapping_df, AMBIGUITY_MARGIN_THRESHOLD,
                                   min_similarity_score=MIN_SIMILARITY_SCORE)

    # Summary stats
    total = len(mapping_df)
    needs_review = (mapping_df["Mapping Status"] == "Needs Review").sum()
    nr_single = ((mapping_df["Mapping Status"] == "Needs Review") & (mapping_df["Mapped L2 Count"] == 1)).sum()
    nr_multi = ((mapping_df["Mapping Status"] == "Needs Review") & (mapping_df["Mapped L2 Count"] > 1)).sum()
    no_match = (mapping_df["Mapping Status"] == "No Match").sum()

    logger.info("=" * 60)
    logger.info("ORE MAPPING COMPLETE")
    logger.info(f"  Total OREs: {total}")
    logger.info(f"  Needs Review: {needs_review} ({needs_review/total*100:.1f}%) — single: {nr_single}, multi: {nr_multi}")
    logger.info(f"  No Match: {no_match} ({no_match/total*100:.1f}%)")
    logger.info(f"  Ambiguity threshold: {AMBIGUITY_MARGIN_THRESHOLD:.4f}")
    logger.info("=" * 60)

    # Export
    output_path = export_results(
        mapping_df, AMBIGUITY_MARGIN_THRESHOLD, output_dir,
        spec=_build_spec(),
        summary_df=_build_summary_df(mapping_df),
        raw_stats_df=_build_raw_stats_df(mapping_df, AMBIGUITY_MARGIN_THRESHOLD),
    )

    # Write orphans sidecar — same timestamp as the mapping file. Picked up by
    # the main pipeline and surfaced in the Upstream Tagging Gaps tab.
    if not orphans_df.empty:
        sidecar_path = write_orphans_sidecar(
            orphans_df, output_path, source_filename,
            id_col=ORE_ID_COL, title_col=ORE_TITLE_COL,
            status_col=ORE_STATUS_COL,
            source_label="OREs (legacy)" if SOURCE_NAME == "ore" else "ORE IRM",
        )
        logger.info(f"  Orphans sidecar saved: {sidecar_path} ({len(orphans_df)} rows)")

    print(f"\nDone! Output: {output_path}")
    print(f"  Needs Review: {needs_review} (single: {nr_single}, multi: {nr_multi}) | No Match: {no_match}")


if __name__ == "__main__":
    main()
