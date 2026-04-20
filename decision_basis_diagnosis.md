# Decision Basis generation paths

All `Decision Basis` text in the `Audit_Review` sheet is produced by a single function,
`_derive_decision_basis(row)` in `risk_taxonomy_transformer/enrichment.py` (lines 239–330).
Three review-builder entry points call it:

| Entry point | File:line | Applied to |
| --- | --- | --- |
| `build_audit_review_df` | `review_builders.py:352` | Every row of the `Audit_Review` sheet |
| `build_review_queue_df` | `review_builders.py:584` | Rows flagged `no_evidence_all_candidates` or `evaluated_no_evidence` |
| `build_review_v2` (per-row dict) | `review_builders.py:748` | Rows in the V2 review sheet |

`_derive_decision_basis` branches on substring matches against `row["method"]`. The branch order
matters — specific methods (e.g. `llm_confirmed_na`) are checked before generic ones
(`direct`, `evidence_match`). Inputs flowing in:

- `method` — mapping method string from `mapping.py`. May carry a ` (dedup: kept higher)` suffix
  added in `_deduplicate_transformed_rows` (`mapping.py:249, 256`).
- `source_legacy_pillar` — pillar name; the ` (also: …)` dedup suffix is stripped with
  `.split(" (also")[0].strip()`.
- `sub_risk_evidence` — free-form evidence string. Built by `mapping.py` in several formats:
  - Keyword-match list: items joined with `"; "`, each item is either
    `rationale: kw1, kw2, …` **or**
    `sub-risk {RISK_ID} [{desc truncated to 80 chars}…]: kw1, kw2, …` (`mapping.py:136,148,461`).
  - Sibling list: `siblings_with_evidence: L2a; L2b; L2c` (`mapping.py:412,428`).
  - Finding list: `issue_id: issue_title (severity, status); …` (`mapping.py:54,64`).
  - LLM reasoning: literal `AI review: {reasoning}` (`mapping.py:105`).
  - **Fused (dedup)**: `{keyword-match list} | {finding list}` — branches 3/4 append with
    `" | "` delimiter (`mapping.py:231–240`). This produces rows where a `|` separates the
    evidence-match body from the finding record.
- `source_risk_rating_raw` — shown as the parenthesised `(rated …)`. Missing → `unknown`.
- `confidence`, `new_l2` — used only in specific branches.
- `dedup_note` — fixed sentence appended when `dedup` is in the method string:
  `" This L2 was also referenced by other legacy pillars; the higher rating was kept."`

### The ten possible templates

Each produces pure prose (no markdown, no newlines). `{pillar}`, `{rating}`, `{evidence}`,
`{confidence}`, `{reasoning}`, `{siblings}`, `{l2_name}`, `{dedup_note}` are interpolated.

1. **LLM_CONFIRMED_NA with reasoning** (`enrichment.py:265`) —
   `AI review confirmed this L2 is not applicable for the {pillar} pillar (rated {rating}). Basis: {reasoning}{dedup_note}`
2. **LLM_CONFIRMED_NA no reasoning** (`enrichment.py:267`) —
   `Proposed not applicable by AI review of the {pillar} pillar (rated {rating}) rationale and sub-risk descriptions.{dedup_note}`
3. **SOURCE_NOT_APPLICABLE** (`enrichment.py:270`) —
   `The legacy {pillar} pillar was rated Not Applicable for this entity, so this L2 risk is also marked as not applicable.{dedup_note}`
4. **EVALUATED_NO_EVIDENCE with siblings** (`enrichment.py:279`) —
   `The {pillar} pillar (rated {rating}) maps to multiple L2 risks. Other L2s from this pillar — {siblings} — had keyword matches in the rationale or sub-risk descriptions. This L2 ({l2_name}) did not. Assumed not applicable — override if your review of the rationale suggests this L2 is relevant to this entity.{dedup_note}`
5. **EVALUATED_NO_EVIDENCE no siblings** (`enrichment.py:284`) —
   `The {pillar} pillar (rated {rating}) rationale was reviewed for relevance to this L2 risk. No direct connection was found, so this L2 is marked as not applicable for this entity. If your review of the rationale suggests otherwise, this can be changed to applicable.{dedup_note}`
6. **NO_EVIDENCE_ALL_CANDIDATES** (`enrichment.py:289`) —
   `The {pillar} pillar (rated {rating}) covers multiple L2 risks. The rationale didn't clearly indicate which ones apply, so all candidates are shown with the original rating as a starting point. Review the rationale below and determine which of these L2s are relevant to this entity.{dedup_note}`
7. **TRUE_GAP_FILL** (`enrichment.py:294`) —
   `No legacy pillar maps to this L2 risk. This is a new risk category that will need to be assessed from scratch.`
   *(No dedup suffix possible.)*
8. **DIRECT** (`enrichment.py:297`) —
   `The legacy {pillar} pillar maps directly to this L2 risk. The original rating ({rating}) is carried forward as a starting point.{dedup_note}`
9. **ISSUE_CONFIRMED** (`enrichment.py:300`) —
   `Confirmed applicable based on an open finding tagged to this L2 risk. Finding detail: {evidence}{dedup_note}`
10. **EVIDENCE_MATCH** — three sub-shapes depending on target count / evidence presence:
    - **multi** (`enrichment.py:310`, triggered when the pillar has > 1 target and `evidence` is non-empty) —
      `The {pillar} pillar (rated {rating}) maps to {N} candidate L2 risks. This L2 was matched with {confidence} confidence based on references in the rationale and sub-risk descriptions. Matched references: {evidence}{dedup_note}`
    - **single with evidence** (`enrichment.py:315`) —
      `This L2 was mapped from the {pillar} pillar (rated {rating}) based on references found in the rationale and sub-risk descriptions. Matched references: {evidence}{dedup_note}`
    - **single no evidence** (`enrichment.py:318`) —
      `This L2 was mapped from the {pillar} pillar (rated {rating}) based on keyword evidence in the rationale text.{dedup_note}`
11. **LLM_OVERRIDE with reasoning** (`enrichment.py:326`) —
    `AI review of the {pillar} pillar proposed this L2 as applicable. Basis: {reasoning}{dedup_note}`
12. **LLM_OVERRIDE no reasoning** (`enrichment.py:328`) —
    `This L2 was classified based on an AI review of the {pillar} pillar rationale and sub-risk descriptions.{dedup_note}`

# Distinct output shapes

Classifying by the first sentence, here are the 12 possible shapes. Column "In data" records
the observed count in the latest xlsx. `uncertain` = fewer than 3 real-data examples.

| # | Shape | Template origin | Typical len | Structured markers | In data |
| --- | --- | --- | --- | --- | --- |
| S1 | LLM_CONFIRMED_NA + reasoning | Template 1 | short–medium | `Basis:` label | 0 (not seen) |
| S2 | LLM_CONFIRMED_NA no reasoning | Template 2 | short | — | 0 (not seen) |
| S3 | SOURCE_NOT_APPLICABLE | Template 3 | ~115–213 | optional dedup suffix | 55 |
| S4 | EVALUATED_NO_EVIDENCE + siblings | Template 4 | ~315–446 | em-dash delimited sibling list between `— … —`; `;` separates siblings | 17 |
| S5 | EVALUATED_NO_EVIDENCE no siblings | Template 5 | medium | — | 0 (not seen) |
| S6 | NO_EVIDENCE_ALL_CANDIDATES | Template 6 | ~275–361 | — | 16 |
| S7 | TRUE_GAP_FILL | Template 7 | short, fixed | — | 0 (not seen) |
| S8 | DIRECT | Template 8 | ~120–221 | `({rating})` parenthetical | 65 |
| S9 | ISSUE_CONFIRMED | Template 9 | ~130–145 | `Finding detail:` label; `; ` separates findings; each is `ID: title (severity, status)` | 2 (uncertain) |
| S10a | EVIDENCE_MATCH multi | Template 10 (multi) | ~200–575 | `Matched references:` label; `;` delimits match-groups; `rationale: kws` and `sub-risk ID [desc…]: kws` micro-structures; `[…]` brackets carry truncated sub-risk description; optional ` \| F-…` appends a finding record | 75 |
| S10b | EVIDENCE_MATCH single w/ evidence | Template 10 (single-with) | medium | same as S10a minus "maps to N candidate" prefix | 0 (not seen) |
| S10c | EVIDENCE_MATCH single no evidence | Template 10 (single-without) | short | — | 0 (not seen) |
| S11 | LLM_OVERRIDE + reasoning | Template 11 | medium | `Basis:` label | 0 (not seen) |
| S12 | LLM_OVERRIDE no reasoning | Template 12 | short | — | 0 (not seen) |

Notes:
- Shapes S1, S2, S5, S7, S10b, S10c, S11, S12 have 0 examples in the current data — their
  **patterns are uncertain** as rendered output but are defined in code.
- Any shape can end with the dedup suffix sentence; 20 rows in data have it.
- The `|` delimiter in S10a only appears when a findings-confirmed row was dedup-merged with
  an evidence-match row — it fuses two different sub_risk_evidence formats into one string
  (6 rows).

# Real data distribution

Latest file: `C:\Users\luria\pycharmprojects\Risk_Taxonomy_Transformer\data\output\transformed_risk_taxonomy_042020261005AM.xlsx`
(selected by mtime across all `transformed_risk_taxonomy_*.xlsx`; the AM/PM filename sort
cannot be trusted).

- Total `Audit_Review` rows: **230** (10 entities).
- Non-empty `Decision Basis` rows: **230** (100%).
- Length distribution (characters): min **115**, p25 **129**, median **211**, p75 **277**,
  p90 **365**, max **575**.
- Rows containing `"Matched references:"`: **75**.
- Rows containing `"rationale:"` as a field label: **75** (all inside S10a).
- Rows containing a `sub-risk {ID-NUM}` reference: **20**.
- Rows containing `[...]` (square-bracket truncated sub-risk description): **20**.
- Rows containing `;`: **44** (every S10a with ≥ 2 match-groups, plus every S4 with ≥ 2 siblings).

### Shape distribution

| Shape | Count | Min | Median | p90 | Max |
| --- | --- | --- | --- | --- | --- |
| S3 SOURCE_NOT_APPLICABLE | 55 | 115 | 121 | 130 | 213 |
| S4 EVALUATED_NO_EVIDENCE + siblings | 17 | 314 | 341 | 413 | 446 |
| S6 NO_EVIDENCE_ALL_CANDIDATES | 16 | 274 | 278 | 320 | 361 |
| S8 DIRECT | 65 | 120 | 134 | 217 | 221 |
| S9 ISSUE_CONFIRMED | 2 | 134 | 139 | 143 | 145 (*uncertain — n < 3*) |
| S10a EVIDENCE_MATCH multi | 75 | 204 | 250 | 442 | 575 |
| **All other shapes** | **0** | — | — | — | — |

### Verbatim median sample per observed shape

**S3 SOURCE_NOT_APPLICABLE (median = 121 chars):**
> The legacy Operational pillar was rated Not Applicable for this entity, so this L2 risk is also marked as not applicable.

**S4 EVALUATED_NO_EVIDENCE + siblings (median = 341 chars):**
> The Operational pillar (rated Low) maps to multiple L2 risks. Other L2s from this pillar — Processing, Execution and Change; Human Capital — had keyword matches in the rationale or sub-risk descriptions. This L2 (Privacy) did not. Assumed not applicable — override if your review of the rationale suggests this L2 is relevant to this entity.

**S6 NO_EVIDENCE_ALL_CANDIDATES (median = 278 chars):**
> The Operational pillar (rated High) covers multiple L2 risks. The rationale didn't clearly indicate which ones apply, so all candidates are shown with the original rating as a starting point. Review the rationale below and determine which of these L2s are relevant to this entity.

**S8 DIRECT (median = 134 chars):**
> The legacy Financial Reporting pillar maps directly to this L2 risk. The original rating (Low) is carried forward as a starting point.

**S9 ISSUE_CONFIRMED (median = 139 chars; n = 2, uncertain):**
> Confirmed applicable based on an open finding tagged to this L2 risk. Finding detail: F-5001: New market process errors (Medium, Open)

**S10a EVIDENCE_MATCH multi (median = 250 chars):**
> The Operational pillar (rated High) maps to 6 candidate L2 risks. This L2 was matched with high confidence based on references in the rationale and sub-risk descriptions. Matched references: rationale: retention, hiring, workforce, training, employee

### Longest S10a sample (575 chars — worst-case render)

> The Credit pillar (rated High) maps to 2 candidate L2 risks. This L2 was matched with high confidence based on references in the rationale and sub-risk descriptions. Matched references: rationale: consumer, small business, cardmember, retail, personal, individual, default; sub-risk CR-101 [Consumer credit card default risk from high-balance cardmember accounts in perso...]: consumer, cardmember, retail, personal, default; sub-risk CR-102 [Small business lending concentration in retail sector with individual cardmember...]: small business, cardmember, retail, individual

### Fused evidence+finding sample (S10a + `|` appendix, 6 rows total)

> The Compliance pillar (rated High) maps to 4 candidate L2 risks. This L2 was matched with high confidence based on references in the rationale and sub-risk descriptions. Matched references: rationale: financial crime, aml, sanctions, kyc; sub-risk CO-301 [AML monitoring gaps in cross-border transactions, suspicious activity detection ...]: financial crime, aml, suspicious activity | F-3003: AML monitoring gap (High, In Sustainability)

No multi-language or tenant variants present; all text is English.

# Rendering pain points

Assumption for all estimates: 240px column, ~32 characters per line at the sheet's wrap
font size (≈ 7.5px per character average). Line counts are ceilings of
`chars / 32`. This is an approximation; narrow columns with wider prose words will wrap earlier.

### S3 SOURCE_NOT_APPLICABLE (n = 55)
1. Renders in **4–7 lines** (median 121 chars → 4 lines; worst 213 → 7 lines with the dedup
   suffix). Comfortable; pure prose.
2. No structure beyond the pillar name and optional dedup sentence.
3. Nothing to recover. Fine as-is.

### S4 EVALUATED_NO_EVIDENCE + siblings (n = 17)
1. Renders in **10–14 lines** (median 341 → 11 lines; worst 446 → 14). This is the second-
   heaviest shape.
2. Sibling list is buried between two em-dashes (`— L2a; L2b; L2c —`); semicolons delimit
   siblings; the current L2 is stated again in parentheses for emphasis.
3. Regex-recoverable: the sibling list is always framed as `Other L2s from this pillar — {…} —
   had keyword matches`. Splitting the inner `{…}` on `"; "` yields siblings reliably. `;` is
   unambiguous inside this frame.

### S6 NO_EVIDENCE_ALL_CANDIDATES (n = 16)
1. Renders in **9–12 lines** (median 278 → 9; worst 361 → 12). Mostly instruction/prose.
2. No embedded list — just a prompt to the reviewer. `{pillar}` and `({rating})` are the only
   structure.
3. Fine as-is — no structure to extract.

### S8 DIRECT (n = 65)
1. Renders in **4–7 lines** (median 134 → 5; worst 221 → 7). Small.
2. Two pieces of data only: pillar name, rating (in parentheses). Optional dedup sentence.
3. Semantically minimal; fine as-is. Candidate for condensation if the column is heavily
   truncated (see recs).

### S9 ISSUE_CONFIRMED (n = 2; pattern uncertain)
1. Renders in ~5 lines at observed lengths.
2. Structure: `Finding detail:` followed by `ID: title (severity, status)`. Multiple findings
   would be `"; "`-separated inside `evidence` (format comes from `mapping.py:54`).
3. Regex-recoverable using `r'([A-Z]+-\d+): (.+?) \(([^,]+), ([^)]+)\)'`. `; ` is the list
   delimiter in `evidence`; `;` does not appear inside individual titles in the current data
   but there is no guarantee — a finding title containing `";"` would confuse any splitter.

### S10a EVIDENCE_MATCH multi (n = 75)
1. Renders in **7–18 lines** (median 250 → 8; worst 575 → 18). This is the heaviest shape and
   the main rendering problem. Lots of commas + colons, bracketed truncations, and optional
   `|`-appended finding details inflate wrap count.
2. Heavy buried structure inside the single `Matched references: {evidence}` tail:
   - `;` delimits match-groups (rationale-level and per-sub-risk).
   - Each group is either `rationale: kw1, kw2, …` or `sub-risk {ID} [{truncated desc…}]:
     kw1, kw2, …`. The bracketed text is the **first 80 chars** of the sub-risk description
     with `"..."` appended when longer (`mapping.py:147`).
   - When a finding was merged in during dedup, the entire evidence string is further joined
     with `" | "` to a finding detail block (`mapping.py:231–240`). So a single cell can
     hold: prose prefix + `Matched references:` + keyword groups separated by `;` + ` | ` +
     `F-ID: title (severity, status)`.
3. Structure is regex-recoverable but ambiguous at the edges:
   - `;` is reliable as a match-group delimiter; it does not appear inside a truncated
     sub-risk description (those are hard-truncated at 80 chars and end with `"..."`).
   - Commas inside the keyword list are reliable *within* a group, but if a sub-risk
     description contains commas before the 80-char cut, they sit inside `[…]`. Brackets are
     a solid boundary — no nested brackets observed and none possible given the truncation
     rule.
   - `|` is only the fused-finding delimiter *when preceded by a space and followed by
     ` F-` / `{ID}-`*. It is not used anywhere else in the template. Still, a plain regex
     `" \| "` works because `|` has no other role in the current template library.
   - The bracketed sub-risk description is **truncated at 80 chars with `"..."`**, meaning
     the suffix inside `[…]` is never a complete sentence and often cut mid-word. This is
     information loss at generation time — the reviewer cannot see the full sub-risk text
     from the cell.

### Unseen shapes (S1, S2, S5, S7, S10b, S10c, S11, S12)
The current entity set (10 entities) has no LLM overrides, no single-target evidence-match
mappings, no true gap fills, and no "no siblings" evaluated-no-evidence rows. If the pipeline
ingests real LLM review output, expect S1/S11 to appear with free-form `Basis: {reasoning}`
tails whose shape is unconstrained.

# Recommendations

### Transformer-level changes (high leverage)
1. **Split S10a evidence groups onto their own lines at generation time.** The single longest
   source of rendering pain is the `Matched references: …; …; …` tail. Owner:
   `enrichment.py:_derive_decision_basis` (the `EVIDENCE_MATCH` branch, lines 309–319).
   - Before: `Matched references: rationale: kw1, kw2; sub-risk CR-101 [desc…]: kw1, kw2; sub-risk CR-102 [desc…]: kw1`
   - After: join `evidence.split("; ")` with `\n  - ` instead. The cell then renders as a
     scannable bullet list; existing wrap-enabled columns in `formatting.py` already accept
     newlines.
2. **Stop appending the finding-detail block with ` | `.** Owner: `mapping.py:231–240`
   (dedup branches 3 and 4). Fusing two formats into one string in `sub_risk_evidence` forces
   downstream code to handle a mixed delimiter set. Options (pick one):
   - Keep the keyword-match list in `sub_risk_evidence` and move the finding detail to a new
     column (e.g. `merged_findings`). The audit review already surfaces findings via
     `impact_of_issues`, so this may even be redundant.
   - At minimum, change the fuse delimiter from ` | ` to a distinct token like `\nFinding
     detail: ` so the rendered output matches the S9 shape.
3. **Stop truncating the bracketed sub-risk description at 80 chars** *or* remove it from
   `Decision Basis` entirely. Owner: `mapping.py:147`. The `[desc…]` fragment adds bulk (≈ 80
   chars per sub-risk) but is always cut mid-word and provides no actionable detail that the
   sub-risk ID alone couldn't fetch. Either emit just `sub-risk {ID}: kw1, kw2` or keep the
   full description. Current behaviour is the worst of both.

### Report-level parsing (no code change needed yet, just flags)
4. **S4's sibling list is a clean regex target.** If the HTML report wants to render sibling
   L2s as chips, the pattern `Other L2s from this pillar — (.+?) — had keyword matches` is
   safe, and the inner capture group can be split on `"; "`.
5. **S10a is parseable *after* rec #1 lands.** Parsing `; `-joined groups today works but is
   more fragile (e.g., if a keyword ever contained `; ` it would break; none do now). Moving
   the split to generation time removes the ambiguity.

### Fine as-is
- S3 SOURCE_NOT_APPLICABLE — short, pure prose, no extractable structure.
- S6 NO_EVIDENCE_ALL_CANDIDATES — reviewer instruction; no list to render.
- S8 DIRECT — short; pillar + rating are the only data points.
- S7 TRUE_GAP_FILL (unseen but hard-coded short) — fixed string, no parameters worth
  structuring.

### Generation-logic smells worth flagging to the user
- **S10a double-mentions the pillar name** in the `({rating})` parenthetical when it was just
  named, e.g., `The Credit pillar (rated High) maps to 2 candidate L2 risks.` — no bug, but
  two of the first eight words repeat between S10a and S4. Tolerable.
- **S10a repeats the same boilerplate for every multi-target L2 in the same entity.** A
  Credit pillar with two candidate L2s produces two rows whose first two sentences are
  identical (just the keyword tail differs). Fine for Excel, but a 240px HTML cell will
  render that boilerplate twice per entity. Consider moving the "maps to N candidate" framing
  into a tooltip or a hidden column.
- **Ambiguous dedup suffix placement.** The dedup sentence always sits *after* the
  body, even when the body itself reasons about multiple candidates (e.g., S6). Readers may
  interpret "also referenced by other legacy pillars" as a second, separate list of siblings.
  Consider moving the dedup note into a dedicated column (`Dedup Note`) — this also makes it
  filterable.
- **Sub-risk description truncation is silent.** Cut at 80 chars mid-word with `...`. If the
  audit team is meant to verify the evidence, that truncation is either noise (drop it) or a
  gap (keep full text).
- **ISSUE_CONFIRMED has n = 2** in current data — keep an eye on its delimiter behaviour
  once more findings land; if a finding title contains `"; "` or `" | "` the template will
  break parsing.
- **Several defined branches produce zero rows** in the current 10-entity test set (S1, S2,
  S5, S7, S10b, S10c, S11, S12). Don't design the renderer around shapes you haven't actually
  seen — revisit once real LLM-override / gap-fill / single-target data lands.
