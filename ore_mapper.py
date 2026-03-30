"""
ORE-to-L2 Risk Mapper
=====================
Maps Operational Risk Events (OREs) to new L2 risk categories using
TF-IDF vectorization with cosine similarity.

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
import re
from datetime import datetime
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

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

# Margin threshold: if the score gap between 1st and 2nd match is below this,
# the ORE is flagged as ambiguous. Set to None to auto-detect from data.
AMBIGUITY_MARGIN_THRESHOLD = None

# Minimum similarity score for a match to be considered valid
MIN_SIMILARITY_SCORE = 0.05

# TF-IDF settings
TFIDF_MAX_FEATURES = 15000
TFIDF_NGRAM_RANGE = (1, 2)  # unigrams and bigrams

# Domain-specific stopwords to exclude from TF-IDF (too common to be useful)
DOMAIN_STOPWORDS = [
    "risk", "company", "financial", "control", "controls", "process",
    "processes", "management", "business", "operations", "operational",
    "activity", "activities", "event", "impact", "issue", "issues",
    "related", "due", "result", "resulting", "including", "include",
    "includes", "also", "may", "could", "would", "within", "across",
    "ensure", "ensuring", "maintain", "maintained", "adequate",
    "inadequate", "failure", "failed", "adverse", "current", "projected",
]

# ORE file pattern
ORE_FILE_PATTERN = "ORE_*.xlsx"

# ORE column names
ORE_ID_COL = "Event ID"
ORE_TITLE_COL = "Event Title"
ORE_DESC_COL = "Event Description / Summary"

# L2 taxonomy file
L2_TAXONOMY_FILE = "L2_Risk_Taxonomy.xlsx"


# =============================================================================
# TEXT PREPROCESSING
# =============================================================================

def preprocess_text(text: str) -> str:
    """Clean and normalize text for TF-IDF vectorization."""
    if not text or text == "nan":
        return ""
    text = text.lower()
    # Remove special characters but keep hyphens and slashes (useful in risk terms)
    text = re.sub(r"[^a-z0-9\s\-/]", " ", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


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

    # Clean data
    df[ORE_ID_COL] = df[ORE_ID_COL].astype(str).str.strip()
    df[ORE_TITLE_COL] = df[ORE_TITLE_COL].astype(str).fillna("").str.strip()
    df[ORE_DESC_COL] = df[ORE_DESC_COL].astype(str).fillna("").str.strip()

    # Drop rows with no meaningful text
    df = df[~((df[ORE_TITLE_COL].isin(["", "nan"])) &
              (df[ORE_DESC_COL].isin(["", "nan"])))]
    df = df[~df[ORE_ID_COL].isin(["", "nan"])]

    logger.info(f"  Loaded {len(df)} OREs with text content")
    return df


def build_texts(l2_df: pd.DataFrame, ore_df: pd.DataFrame) -> tuple[list[str], list[str], list[str]]:
    """Build preprocessed text lists for L2 definitions and OREs.

    Returns (l2_texts, l2_names, ore_texts).
    """
    # L2 reference texts: name + definition combined for richer representation
    l2_names = l2_df["L2"].tolist()
    l2_texts = [
        preprocess_text(f"{row['L2']}. {row['L2 Definition']}")
        for _, row in l2_df.iterrows()
    ]

    # ORE texts: title + description combined, title weighted by repetition
    ore_texts = []
    for _, row in ore_df.iterrows():
        title = str(row[ORE_TITLE_COL]) if str(row[ORE_TITLE_COL]) != "nan" else ""
        desc = str(row[ORE_DESC_COL]) if str(row[ORE_DESC_COL]) != "nan" else ""
        # Repeat title to give it more weight in TF-IDF
        combined = preprocess_text(f"{title}. {title}. {desc}")
        ore_texts.append(combined)

    return l2_texts, l2_names, ore_texts


def compute_mappings(
    l2_texts: list[str],
    l2_names: list[str],
    ore_texts: list[str],
    ore_df: pd.DataFrame,
) -> pd.DataFrame:
    """Compute TF-IDF similarity and produce top-3 mappings per ORE."""

    # Fit TF-IDF on all texts together so they share the same vocabulary
    all_texts = l2_texts + ore_texts
    logger.info(f"Fitting TF-IDF on {len(all_texts)} documents "
                f"(max_features={TFIDF_MAX_FEATURES}, ngrams={TFIDF_NGRAM_RANGE})...")

    vectorizer = TfidfVectorizer(
        max_features=TFIDF_MAX_FEATURES,
        ngram_range=TFIDF_NGRAM_RANGE,
        stop_words="english",
        sublinear_tf=True,  # dampens term frequency (log scaling)
    )

    # Add domain stopwords
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
    custom_stop = list(ENGLISH_STOP_WORDS) + DOMAIN_STOPWORDS
    vectorizer.stop_words = custom_stop

    tfidf_matrix = vectorizer.fit_transform(all_texts)

    # Split back into L2 and ORE matrices
    l2_matrix = tfidf_matrix[:len(l2_texts)]
    ore_matrix = tfidf_matrix[len(l2_texts):]

    logger.info(f"  Vocabulary size: {len(vectorizer.vocabulary_)}")
    logger.info(f"  L2 matrix: {l2_matrix.shape}, ORE matrix: {ore_matrix.shape}")

    # Compute cosine similarity: (num_ores, num_l2s)
    logger.info("Computing cosine similarities...")
    similarities = cosine_similarity(ore_matrix, l2_matrix)

    results = []
    for i, (_, ore_row) in enumerate(ore_df.iterrows()):
        scores = similarities[i]
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

    result_df = pd.DataFrame(results)
    logger.info(f"  Computed mappings for {len(result_df)} OREs")
    return result_df


def determine_ambiguity_threshold(mapping_df: pd.DataFrame) -> float:
    """Determine the margin threshold from data distribution.

    Uses the 25th percentile of non-zero margins as the threshold,
    floored at 0.02 and capped at 0.08.
    """
    margins = mapping_df["Margin 1-2"]
    margins = margins[margins > 0]

    if len(margins) == 0:
        return 0.03  # fallback

    p25 = margins.quantile(0.25)
    median = margins.quantile(0.50)

    threshold = max(0.02, min(p25, 0.08))

    logger.info(f"  Margin distribution — P25: {p25:.4f}, median: {median:.4f}")
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

    # For confident matches, flag supplementary L2 if 2nd match is close enough
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
        "Event ID", "Event Title", "Event Description",
        "Match 1 - L2", "Match 1 - Score",
        "Match 2 - L2", "Match 2 - Score",
        "Match 3 - L2", "Match 3 - Score",
        "Margin 1-2", "Margin 2-3",
        "Classification", "Supplementary L2",
    ]]

    # Sheet 2: Ambiguous cases
    ambiguous = mapping_df[mapping_df["Classification"] == "Ambiguous — Manual Review"][[
        "Event ID", "Event Title", "Event Description",
        "Match 1 - L2", "Match 1 - Score",
        "Match 2 - L2", "Match 2 - Score",
        "Match 3 - L2", "Match 3 - Score",
        "Margin 1-2",
    ]]

    # Sheet 3: Summary
    total = len(mapping_df)
    confident = (mapping_df["Classification"] == "Confident").sum()
    ambiguous_count = (mapping_df["Classification"] == "Ambiguous — Manual Review").sum()
    no_match = (mapping_df["Classification"] == "No Valid Match").sum()
    supplementary = (mapping_df["Supplementary L2"] != "").sum()

    summary_data = {
        "Metric": [
            "Total OREs",
            "Confident (clear primary match)",
            "Ambiguous (manual review needed)",
            "No Valid Match",
            "With Supplementary L2",
            "Ambiguity Threshold Used",
            "Min Similarity Score",
            "TF-IDF Max Features",
            "TF-IDF N-gram Range",
        ],
        "Value": [
            total,
            f"{confident} ({confident/total*100:.1f}%)" if total > 0 else 0,
            f"{ambiguous_count} ({ambiguous_count/total*100:.1f}%)" if total > 0 else 0,
            f"{no_match} ({no_match/total*100:.1f}%)" if total > 0 else 0,
            supplementary,
            f"{threshold:.4f}",
            MIN_SIMILARITY_SCORE,
            TFIDF_MAX_FEATURES,
            str(TFIDF_NGRAM_RANGE),
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

    # Build text representations
    l2_texts, l2_names, ore_texts = build_texts(l2_df, ore_df)

    # Compute similarity and get top-3 mappings
    mapping_df = compute_mappings(l2_texts, l2_names, ore_texts, ore_df)

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
