# Prompt: Update ORE Mapper — Multi-L2 Mapping with Reviewer-Friendly Output

## Context

I have a working Python script (`ore_mapper.py`) that maps Operational Risk Events (OREs) to new L2 risk categories using spaCy semantic similarity. It currently outputs raw similarity scores (e.g., 0.87) and classifications. The full script is attached.

The output is reviewed by audit teams who don't know what a cosine similarity score means and shouldn't have to. I need to restructure the output so:

1. OREs can map to multiple L2s when the event legitimately spans more than one risk category (e.g., "unauthorized payment due to system access control failure" maps to both External Fraud - First Party and Info & Cyber Security)
2. Raw scores are replaced with three plain-language statuses that each drive a different reviewer action
3. L2 definitions are shown alongside each match so the reviewer can judge the mapping by reading the ORE description next to the L2 definition — a side-by-side comparison
4. Raw scores and technical details are preserved in a hidden sheet for development and threshold tuning

## Changes Required

### 1. Multi-L2 Mapping and Classification

The current design forces each ORE to a single primary L2 with an optional supplementary. OREs frequently span multiple risk categories legitimately. Restructure the classification to support this.

**Classification logic — still three buckets, but Mapped can carry multiple L2s:**

| Status | Logic | What flows downstream |
|---|---|---|
| Mapped | At least one match above MIN_SIMILARITY_SCORE with margin above threshold. Additional L2s are included if they are also above MIN_SIMILARITY_SCORE and within 2x the ambiguity threshold of the top score. | All matched L2s flow into the control effectiveness pipeline for this entity. |
| Needs Review | Multiple matches above MIN_SIMILARITY_SCORE but the margin between them is below the ambiguity threshold — the tool can't confidently rank them. | Reviewer sees the side-by-side comparison and checks all L2s that apply. |
| No Match | No match scored above MIN_SIMILARITY_SCORE. | Excluded from pipeline. Reviewer can manually assign if needed. |

**Key distinction between Mapped (multiple) and Needs Review:** Mapped (multiple) means the tool is confident the ORE relates to more than one L2 — the scores are all strong and reasonably close. Needs Review means the tool can't tell which L2(s) are correct because the scores are too tightly clustered at a lower confidence level.

More concretely, for the top 3 matches (Match 1, Match 2, Match 3):
- Match 1 must be above MIN_SIMILARITY_SCORE or the ORE is No Match
- If Match 1 is valid and the margin between Match 1 and Match 2 is ABOVE the ambiguity threshold: Match 1 is a confident primary. Then check if Match 2 is also above MIN_SIMILARITY_SCORE AND within 2x the threshold of Match 1's score — if yes, include Match 2 as an additional mapped L2. Apply the same check to Match 3 relative to Match 1.
- If Match 1 is valid but the margin between Match 1 and Match 2 is BELOW the ambiguity threshold: Needs Review — the tool can't confidently separate them.

The result for each ORE is a list of mapped L2s (could be 1, 2, or 3) plus a status.

Update `classify_mappings()` to produce:
- A `Status` column (Mapped / Needs Review / No Match)
- A `Mapped L2s` column containing a semicolon-separated list of all L2s that qualified (e.g., "External Fraud - First Party; Info & Cyber Security")
- A `Mapped L2 Count` column (integer — how many L2s this ORE maps to)

Update `compute_mappings()` or add a post-processing step so that the output DataFrame has one row per ORE (not one row per ORE-L2 pair). The multi-L2 information is in the list column. Downstream consumers (the control effectiveness pipeline in the main transformer) will explode this into per-L2 rows when building their indexes.

### 2. Restructure Output Sheets

**Sheet 1: "All Mappings" (visible)**

One row per ORE. Columns in this order:
- Event ID
- Audit Entity ID
- Event Title
- Event Description (current 200-char truncation is fine)
- Status (Mapped / Needs Review / No Match)
- Mapped L2s (semicolon-separated list of all L2s this ORE maps to, e.g., "External Fraud - First Party; Info & Cyber Security". For Needs Review rows, show the candidates that need resolution. Blank for No Match.)
- Mapped L2 Count (integer — 1, 2, or 3 for Mapped rows; count of candidates for Needs Review; 0 for No Match)
- Mapped L2 Definitions (semicolon-separated L2 definitions matching the L2s listed, in the same order — so the reviewer can read each L2 name and its definition together)

Do NOT include raw scores, margins, or any numeric similarity values on this sheet.

**Sheet 2: "Needs Review" (visible)**

This is the side-by-side comparison workspace. Only rows where Status = "Needs Review". The tool found multiple L2 definitions that fit the ORE almost equally well but couldn't confidently determine which ones actually apply. The reviewer reads the ORE description alongside the candidate L2 definitions and checks all that apply.

Columns:
- Event ID
- Audit Entity ID
- Event Title
- Event Description (FULL text here, not truncated — reviewers need the complete description to make the call)
- Candidate 1 L2
- Candidate 1 Definition
- Candidate 1 Applies (blank column — reviewer enters Yes/No)
- Candidate 2 L2
- Candidate 2 Definition
- Candidate 2 Applies (blank column — reviewer enters Yes/No)
- Candidate 3 L2 (the current Match 3)
- Candidate 3 Definition
- Candidate 3 Applies (blank column — reviewer enters Yes/No)
- Reviewer Notes (blank column)

**Sheet 3: "Summary" (visible)**

Update the summary statistics to use the new status names:
- Total OREs
- Mapped: [count] ([%])
  - Mapped to single L2: [count]
  - Mapped to multiple L2s: [count]
- Needs Review: [count] ([%])
- No Match: [count] ([%])

Remove the raw score distribution stats (mean, median, min, max) from this sheet — they move to the hidden sheet.

Add a "How This Works" section to the Summary sheet with plain-language explanation:

```
HOW THIS WORKS

The tool reads each ORE description and compares it against all 23 L2 risk
definitions to find which ones fit. Think of it like a search engine — it finds
the L2 definitions that talk about the most similar things as the ORE.

A single ORE can map to more than one L2. For example, "unauthorized payment
processed due to system access control failure" relates to both External
Fraud - First Party and Info & Cyber Security. When the tool detects this, it
maps the ORE to all L2s that fit.

Mapped — The tool found one or more L2 definitions that clearly fit this ORE.
These flow into the control effectiveness pipeline automatically. You'll see
them in context when reviewing each entity. If the tool mapped the ORE to
multiple L2s, all of them are listed.

Needs Review — The tool found multiple L2 definitions that fit the ORE almost
equally well but couldn't confidently determine which ones actually apply, like
a search returning several equally relevant results. Open the Needs Review tab
and check all L2s that apply for each ORE.

No Match — Nothing fit well enough, like a search that returns results but none
of them are really what you were looking for. These are excluded from the
pipeline. A reviewer can manually assign an L2 if needed.
```

**Sheet 4: "L2 Distribution" (visible)**

Count of OREs mapped to each L2, including multi-L2 mappings (an ORE mapped to 2 L2s counts once for each). Only includes Mapped rows. Columns:
- L2 Risk
- ORE Count (Mapped)

**Sheet 5: "Raw Scores" (HIDDEN)**

This is for development and threshold tuning only. Reviewers should never need this sheet. Contains all the technical data:
- Event ID
- Audit Entity ID
- Event Title
- Event Description (full text)
- Match 1 - L2, Match 1 - Score
- Match 2 - L2, Match 2 - Score
- Match 3 - L2, Match 3 - Score
- Margin 1-2, Margin 2-3
- Status (the three-bucket label)
- Match 1 Valid (boolean)

Also include score distribution stats that were removed from the Summary sheet:
- Mean, median, min, max of Match 1 scores for valid matches
- Margin distribution: P25, P50 (median), P75
- Ambiguity threshold used
- Min similarity score setting
- spaCy model name

Hide this sheet using openpyxl `sheet_state = "hidden"` after writing, same pattern used in the main transformer.

### 3. Carry L2 Definitions Through the Pipeline

`build_reference_vectors()` currently returns `(vectors, l2_names)`. Update it to also return the L2 definitions list so they're available at output time. Either:
- Return `(vectors, l2_names, l2_definitions)` and pass `l2_definitions` through to `compute_mappings()` and `export_results()`
- Or build a `l2_name_to_def` dict from the L2 DataFrame and use it during export

The L2 definitions come from the `L2 Definition` column in `L2_Risk_Taxonomy.xlsx` which is already loaded in `load_l2_definitions()`.

### 4. Needs Review Sheet — Full Event Description

Currently `compute_mappings()` truncates Event Description to 200 chars. Keep this truncation for the All Mappings sheet, but for the Needs Review sheet, use the full description. This means either:
- Storing the full description in the mappings DataFrame (as a separate column like `Event Description Full`) and truncating only at export time for All Mappings
- Or joining back to the source ORE data when building the Needs Review sheet

### 5. Formatting

Apply basic openpyxl formatting to the visible sheets:
- Header styling: bold, dark blue background, white text (same pattern as the main transformer's `style_header()`)
- Column widths: Event Description and L2 Definition columns at 60, Event Title at 30, others auto-fit capped at 25
- Text wrap on Event Description and Definition columns
- Color-code the Status column cells: Mapped = green fill, Needs Review = yellow fill, No Match = gray fill
- Freeze panes on All Mappings: freeze header row + first 2 columns (Event ID, Audit Entity ID)
- Freeze panes on Needs Review: freeze header row only, set row height to 60 for readability since descriptions are full-length
- Needs Review: highlight the Candidate X Applies and Reviewer Notes column headers with a green fill to indicate these are input columns (same pattern as the RCO action columns in the main transformer)

### 6. What NOT to Change

- Do not modify the spaCy model, vectorization approach, or similarity computation
- Do not change the ambiguity threshold logic (`determine_ambiguity_threshold`)
- Do not change the minimum similarity score
- Do not change how ORE data is loaded or cleaned
- Keep the same file naming convention and timestamp format

Note: The current "Supplementary L2" concept is replaced by the multi-L2 mapping logic. The 2x threshold check that previously identified supplementary L2s now determines whether additional L2s are included as full mapped L2s.

### 7. Downstream Consumption Note

The control effectiveness pipeline in the main transformer will consume this output by exploding the semicolon-separated `Mapped L2s` column into individual rows per (entity_id, l2) pair. This is the same pattern used for findings where multi-value L2 cells are split on newlines. Include a brief comment in the code noting this expected downstream usage so future developers understand why the All Mappings sheet uses a semicolon-separated list rather than one row per L2.

## Existing Code Reference

The full `ore_mapper.py` is attached. Key functions to modify:
- `build_reference_vectors()` — needs to return L2 definitions alongside names
- `compute_mappings()` — needs to store full description and include L2 definitions in results
- `classify_mappings()` — major rework: needs to produce the three status labels AND determine which L2s qualify as mapped (single or multiple) based on the margin/threshold logic described above
- `export_results()` — major restructure of sheet content, layout, and formatting; L2 Distribution needs to explode multi-L2 mappings so each L2 is counted separately

## Output

Give me:
1. Updated functions with full code
2. Any new helper functions needed
3. Changes called out as diffs where possible (show old vs new)
