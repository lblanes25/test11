"""
ORE-to-L2 Risk Mapper
=====================
Maps Operational Risk Events (OREs) to new L2 risk categories using
spaCy semantic similarity (en_core_web_md word vectors).

For each ORE, produces top 3 L2 matches with scores and margins.
Flags ambiguous cases (tight margin between 1st and 2nd) for manual review.

Usage:
    python ore_mapper.py

Input:
    - data/input/L2_Risk_Taxonomy.xlsx (L2 definitions)
    - data/input/ORE_*.xlsx (Event ID, Event Title, Event Description / Summary)

Output:
    - data/output/ore_mapping_{timestamp}.xlsx
      Sheet 1: All mappings (one row per ORE with top 3 matches)
      Sheet 2: Ambiguous cases (tight margins, need manual review)
      Sheet 3: Summary statistics
      Sheet 4: L2 distribution
"""

import pandas as pd
import numpy as np
import logging
from datetime import datetime
from pathlib import Path
import spacy

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
# CONFIGURATION
# =============================================================================

# spaCy model — medium model has 300-dimensional word vectors
SPACY_MODEL = "en_core_web_md"

# Margin threshold: if the score gap between 1st and 2nd match is below this,
# the ORE is flagged as ambiguous. Set to None to auto-detect from data.
AMBIGUITY_MARGIN_THRESHOLD = None

# Minimum similarity score for a match to be considered valid
MIN_SIMILARITY_SCORE = 0.50

# ORE file pattern
ORE_FILE_PATTERN = "ORE_*.xlsx"

# ORE column names
ORE_ID_COL = "Event ID"
ORE_TITLE_COL = "Event Title"
ORE_DESC_COL = "Event Description / Summary"
ORE_ENTITY_COL = "Audit Entity ID"

# L2 taxonomy file
L2_TAXONOMY_FILE = "L2_Risk_Taxonomy.xlsx"


# =============================================================================
# CORE FUNCTIONS
# =============================================================================

def load_l2_definitions(input_dir: Path) -> pd.DataFrame:
    """Load L2 risk definitions from taxonomy file."""
    filepath = input_dir / L2_TAXONOMY_FILE
    logger.info(f"Loading L2 definitions from {filepath}")
    df = pd.read_excel(filepath)
    logger.info(f"  Loaded {len(df)} L2 definitions")
    return df


def load_ore_data(input_dir: Path) -> pd.DataFrame:
    """Load ORE data from the most recent matching file."""
    ore_files = sorted(input_dir.glob(ORE_FILE_PATTERN),
                       key=lambda f: f.stat().st_mtime)
    if not ore_files:
        raise FileNotFoundError(
            f"No files matching '{ORE_FILE_PATTERN}' found in {input_dir}")

    filepath = ore_files[-1]
    logger.info(f"Loading ORE data from {filepath}")
    df = pd.read_excel(filepath)
    df.columns = [c.strip() for c in df.columns]

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

    # Drop rows with no meaningful text
    df = df[~((df[ORE_TITLE_COL].isin(["", "nan"])) &
              (df[ORE_DESC_COL].isin(["", "nan"])))]
    df = df[~df[ORE_ID_COL].isin(["", "nan"])]

    # Drop OREs with no Audit Entity ID — can't place in entity evidence briefs
    if ORE_ENTITY_COL in df.columns:
        df[ORE_ENTITY_COL] = df[ORE_ENTITY_COL].astype(str).str.strip()
        no_entity = df[ORE_ENTITY_COL].isin(["", "nan"])
        if no_entity.any():
            logger.info(f"  Dropped {no_entity.sum()} OREs with blank Audit Entity ID")
            df = df[~no_entity]
    else:
        logger.warning(f"  Column '{ORE_ENTITY_COL}' not found — cannot filter by entity")

    logger.info(f"  Loaded {len(df)} OREs with text content (of {pre_count} total rows)")
    return df


def build_reference_vectors(
    nlp: spacy.language.Language,
    l2_df: pd.DataFrame,
) -> tuple[np.ndarray, list[str]]:
    """Build document vectors for L2 risk definitions.

    Uses L2 name + definition for richer semantic representation.
    Returns (vectors array, l2_names list).
    """
    l2_names = l2_df["L2"].tolist()
    l2_texts = [
        f"{row['L2']}. {row['L2 Definition']}"
        for _, row in l2_df.iterrows()
    ]

    logger.info(f"Computing vectors for {len(l2_texts)} L2 definitions...")
    vectors = []
    for text in l2_texts:
        doc = nlp(text)
        vectors.append(doc.vector)
    vectors = np.array(vectors)

    # Normalize to unit vectors for cosine similarity via dot product
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1  # avoid division by zero
    vectors = vectors / norms

    logger.info(f"  Reference vectors shape: {vectors.shape}")
    return vectors, l2_names


def compute_mappings(
    nlp: spacy.language.Language,
    ore_df: pd.DataFrame,
    ref_vectors: np.ndarray,
    l2_names: list[str],
) -> pd.DataFrame:
    """Compute semantic similarity and produce top-3 mappings per ORE."""

    total = len(ore_df)
    logger.info(f"Computing vectors for {total} OREs...")

    results = []
    log_interval = max(1, total // 10)

    for i, (_, ore_row) in enumerate(ore_df.iterrows()):
        if i > 0 and i % log_interval == 0:
            logger.info(f"  Processed {i}/{total} OREs ({i/total*100:.0f}%)")

        # Build ORE text: title + description
        title = str(ore_row[ORE_TITLE_COL])
        desc = str(ore_row[ORE_DESC_COL])
        title = "" if title == "nan" else title
        desc = "" if desc == "nan" else desc
        combined = f"{title}. {desc}" if desc else title

        # Get document vector
        doc = nlp(combined)
        ore_vector = doc.vector

        # Normalize
        norm = np.linalg.norm(ore_vector)
        if norm > 0:
            ore_vector = ore_vector / norm

        # Cosine similarity via dot product (both vectors are unit-normalized)
        scores = ref_vectors @ ore_vector

        # Top 3
        top_indices = np.argsort(scores)[::-1][:3]

        top1_idx = top_indices[0]
        top2_idx = top_indices[1]
        top3_idx = top_indices[2]

        top1_score = float(scores[top1_idx])
        top2_score = float(scores[top2_idx])
        top3_score = float(scores[top3_idx])

        margin_1_2 = top1_score - top2_score
        margin_2_3 = top2_score - top3_score

        results.append({
            "Event ID": ore_row[ORE_ID_COL],
            "Audit Entity ID": ore_row.get(ORE_ENTITY_COL, ""),
            "Event Title": ore_row[ORE_TITLE_COL],
            "Event Description": str(ore_row[ORE_DESC_COL])[:200],
            "Match 1 - L2": l2_names[top1_idx],
            "Match 1 - Score": round(top1_score, 4),
            "Match 2 - L2": l2_names[top2_idx],
            "Match 2 - Score": round(top2_score, 4),
            "Match 3 - L2": l2_names[top3_idx],
            "Match 3 - Score": round(top3_score, 4),
            "Margin 1-2": round(margin_1_2, 4),
            "Margin 2-3": round(margin_2_3, 4),
            "Match 1 Valid": top1_score >= MIN_SIMILARITY_SCORE,
        })

    logger.info(f"  Computed mappings for {len(results)} OREs")
    return pd.DataFrame(results)


def determine_ambiguity_threshold(mapping_df: pd.DataFrame) -> float:
    """Determine the margin threshold from data distribution.

    Uses the 25th percentile of margins for valid matches,
    floored at 0.01 and capped at 0.05.
    """
    valid = mapping_df[mapping_df["Match 1 Valid"]]
    margins = valid["Margin 1-2"]
    margins = margins[margins > 0]

    if len(margins) == 0:
        return 0.02  # fallback

    p25 = margins.quantile(0.25)
    median = margins.quantile(0.50)

    # SpaCy scores are more compressed than TF-IDF, so tighter thresholds
    threshold = max(0.01, min(p25, 0.05))

    logger.info(f"  Margin distribution (valid matches) — P25: {p25:.4f}, median: {median:.4f}")
    logger.info(f"  Ambiguity threshold set to: {threshold:.4f}")
    return threshold


def classify_mappings(mapping_df: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """Add classification columns based on scores and margins."""
    df = mapping_df.copy()

    def classify(row):
        if not row["Match 1 Valid"]:
            return "No Valid Match"
        if row["Margin 1-2"] < threshold:
            return "Ambiguous — Manual Review"
        return "Confident"

    df["Classification"] = df.apply(classify, axis=1)

    # For confident matches, flag supplementary L2 if 2nd match is also valid
    # and within 2x the ambiguity threshold
    df["Supplementary L2"] = df.apply(
        lambda r: r["Match 2 - L2"] if (
            r["Classification"] == "Confident"
            and r["Match 2 - Score"] >= MIN_SIMILARITY_SCORE
            and r["Margin 1-2"] < threshold * 2
        ) else "",
        axis=1
    )

    return df


def export_results(
    mapping_df: pd.DataFrame,
    threshold: float,
    output_dir: Path,
) -> Path:
    """Write results to multi-sheet Excel."""
    timestamp = datetime.now().strftime("%m%d%Y%I%M%p")
    output_path = output_dir / f"ore_mapping_{timestamp}.xlsx"

    # Sheet 1: All mappings
    all_mappings = mapping_df[[
        "Event ID", "Audit Entity ID", "Event Title", "Event Description",
        "Match 1 - L2", "Match 1 - Score",
        "Match 2 - L2", "Match 2 - Score",
        "Match 3 - L2", "Match 3 - Score",
        "Margin 1-2", "Margin 2-3",
        "Classification", "Supplementary L2",
    ]]

    # Sheet 2: Ambiguous cases
    ambiguous = mapping_df[mapping_df["Classification"] == "Ambiguous — Manual Review"][[
        "Event ID", "Audit Entity ID", "Event Title", "Event Description",
        "Match 1 - L2", "Match 1 - Score",
        "Match 2 - L2", "Match 2 - Score",
        "Match 3 - L2", "Match 3 - Score",
        "Margin 1-2",
    ]]

    # Sheet 3: Summary
    total = len(mapping_df)
    valid = mapping_df["Match 1 Valid"].sum()
    confident = (mapping_df["Classification"] == "Confident").sum()
    ambiguous_count = (mapping_df["Classification"] == "Ambiguous — Manual Review").sum()
    no_match = (mapping_df["Classification"] == "No Valid Match").sum()
    supplementary = (mapping_df["Supplementary L2"] != "").sum()

    # Score distribution stats
    valid_scores = mapping_df[mapping_df["Match 1 Valid"]]["Match 1 - Score"]

    summary_data = {
        "Metric": [
            "Total OREs",
            "Valid matches (above min score)",
            "Confident (clear primary match)",
            "Ambiguous (manual review needed)",
            "No Valid Match (below min score)",
            "With Supplementary L2",
            "",
            "Ambiguity Threshold Used",
            "Min Similarity Score",
            "spaCy Model",
            "",
            "Score Distribution (valid matches)",
            "  Mean",
            "  Median",
            "  Min",
            "  Max",
        ],
        "Value": [
            total,
            f"{valid} ({valid/total*100:.1f}%)" if total > 0 else 0,
            f"{confident} ({confident/total*100:.1f}%)" if total > 0 else 0,
            f"{ambiguous_count} ({ambiguous_count/total*100:.1f}%)" if total > 0 else 0,
            f"{no_match} ({no_match/total*100:.1f}%)" if total > 0 else 0,
            supplementary,
            "",
            f"{threshold:.4f}",
            MIN_SIMILARITY_SCORE,
            SPACY_MODEL,
            "",
            "",
            f"{valid_scores.mean():.4f}" if len(valid_scores) > 0 else "N/A",
            f"{valid_scores.median():.4f}" if len(valid_scores) > 0 else "N/A",
            f"{valid_scores.min():.4f}" if len(valid_scores) > 0 else "N/A",
            f"{valid_scores.max():.4f}" if len(valid_scores) > 0 else "N/A",
        ],
    }
    summary_df = pd.DataFrame(summary_data)

    # Sheet 4: L2 distribution for confident matches
    l2_dist = (mapping_df[mapping_df["Classification"] == "Confident"]["Match 1 - L2"]
               .value_counts().reset_index())
    l2_dist.columns = ["L2 Risk", "ORE Count (Confident)"]

    logger.info(f"Writing output to {output_path}")
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        all_mappings.to_excel(writer, sheet_name="All_Mappings", index=False)
        ambiguous.to_excel(writer, sheet_name="Ambiguous_Review", index=False)
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        l2_dist.to_excel(writer, sheet_name="L2_Distribution", index=False)

    logger.info(f"  Output saved: {output_path}")
    return output_path


# =============================================================================
# MAIN
# =============================================================================

def main():
    global AMBIGUITY_MARGIN_THRESHOLD

    input_dir = _PROJECT_ROOT / "data" / "input"
    output_dir = _PROJECT_ROOT / "data" / "output"

    # Load data
    l2_df = load_l2_definitions(input_dir)
    ore_df = load_ore_data(input_dir)

    # Load spaCy model
    logger.info(f"Loading spaCy model: {SPACY_MODEL}")
    nlp = spacy.load(SPACY_MODEL)
    logger.info(f"  Model loaded ({len(nlp.vocab.vectors)} vectors, "
                f"{nlp.vocab.vectors.shape[1]} dimensions)")

    # Build reference vectors from L2 definitions
    ref_vectors, l2_names = build_reference_vectors(nlp, l2_df)

    # Compute similarity and get top-3 mappings
    mapping_df = compute_mappings(nlp, ore_df, ref_vectors, l2_names)

    # Determine ambiguity threshold from data
    if AMBIGUITY_MARGIN_THRESHOLD is None:
        AMBIGUITY_MARGIN_THRESHOLD = determine_ambiguity_threshold(mapping_df)

    # Classify mappings
    mapping_df = classify_mappings(mapping_df, AMBIGUITY_MARGIN_THRESHOLD)

    # Summary stats
    total = len(mapping_df)
    confident = (mapping_df["Classification"] == "Confident").sum()
    ambiguous = (mapping_df["Classification"] == "Ambiguous — Manual Review").sum()
    no_match = (mapping_df["Classification"] == "No Valid Match").sum()

    logger.info("=" * 60)
    logger.info("ORE MAPPING COMPLETE")
    logger.info(f"  Total OREs: {total}")
    logger.info(f"  Confident: {confident} ({confident/total*100:.1f}%)")
    logger.info(f"  Ambiguous (manual review): {ambiguous} ({ambiguous/total*100:.1f}%)")
    logger.info(f"  No valid match: {no_match} ({no_match/total*100:.1f}%)")
    logger.info(f"  Ambiguity threshold: {AMBIGUITY_MARGIN_THRESHOLD:.4f}")
    logger.info("=" * 60)

    # Export
    output_path = export_results(mapping_df, AMBIGUITY_MARGIN_THRESHOLD, output_dir)

    print(f"\nDone! Output: {output_path}")
    print(f"  Confident: {confident} | Ambiguous: {ambiguous} | No match: {no_match}")


if __name__ == "__main__":
    main()
