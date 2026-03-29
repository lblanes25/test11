# Project Decisions & Open Questions

## Questions for Leadership

### Information Technology, Information Security, and Third Party — Process Change
These three legacy pillars were previously auto-populated based on IT applications
and third party engagements tagged to the audit entity. Under the new taxonomy,
they map to multiple L2s (Technology, Data, Information and Cyber Security, Third Party).

**Current approach**: Both primary L2s are auto-populated for IT and InfoSec
(e.g., Technology + Data always apply). Third Party is a direct 1:1 mapping.

**Questions**:
- Should teams continue to treat these as automatically applicable based on
  tagged applications/engagements, or should they now make a subjective
  applicability determination per L2?
- If subjective, what criteria should teams use to decide whether Data applies
  separately from Technology, or whether Information and Cyber Security applies
  separately from Data?
- Who is responsible for the applicability decision — the audit team, the risk
  owner, or the entity owner?

### Evaluated No Evidence — Expected Team Action
When a legacy pillar maps to multiple L2s and keyword matching finds evidence for
some but not others, the unmatched L2s are marked "Not Applicable — evaluated,
no evidence found."

**Question**: Should teams actively review these and confirm Not Applicable, or
accept the automated determination unless they have reason to override?

### Control Assessment Columns
The new taxonomy has three control-related columns (IAG Control Effectiveness,
Aligned Assurance Rating, Management Awareness Rating). Currently all three
are populated with the same legacy control assessment value.

**Questions**:
- Will these three columns have distinct definitions and assessment criteria?
- If so, when will those definitions be available?
- Should the transformer leave two of the three blank until criteria are defined,
  or continue populating all three identically as a starting point?

### Confidence Thresholds
The transformer assigns confidence based on keyword match count:
- **High**: 3+ keyword matches (configurable in taxonomy_config.yaml)
- **Medium**: 1-2 keyword matches
- **Low**: 0 matches, defaulted to first primary L2, flagged for review

**Question**: Is the threshold of 3 appropriate, or should it be adjusted?
A lower threshold means fewer items flagged for review but more false positives.
A higher threshold means more items flagged but higher accuracy on the confident ones.

### Country Risk Overlay
Country risk is treated as an amplifier — it flags target L2s (Prudential,
Financial crimes, Consumer and Small Business, Commercial) but does not modify
their ratings.

**Question**: Should a High or Critical country risk rating influence the target
L2 ratings (e.g., bump them up), or should the overlay remain informational only?

---

## Decisions Made

### Source N/A = High Confidence
When a legacy pillar is rated "Not Applicable", the corresponding L2s are marked
as Not Applicable with **high** confidence. The source explicitly stated N/A, so
we are confident in the mapping. The status and decision basis communicate that
the rating came from the legacy source.

### IT/InfoSec: Both Primary L2s Always Applicable
Information Technology maps to both Technology and Data as primary. Information
Security maps to both Information and Cyber Security and Data as primary. These
always populate — no conditional keyword check. Decision rationale: these pillars
have no rationale columns, and Data risk is inherently present wherever Technology
or InfoSec risk exists.

### Findings Filters
- Only **Approved** findings are included (filters out In Progress, Pending Review)
- Findings with **blank severity** are excluded (likely incomplete)
- Only **active** finding statuses confirm applicability: Open, In Validation,
  In Sustainability
- Closed, Cancelled, and Not Started findings are excluded

---

## Future Enhancements

### Planned

#### IT Application / Third Party Applicability Detection
When an entity has IT applications or third party engagements tagged (via the four
legacy columns), auto-flag the relevant L2s as recommended-applicable even if the
legacy pillar was rated Not Applicable. The output should clearly distinguish:
- **Source rating**: Not Applicable (from legacy pillar)
- **Recommendation**: Recommend Applicable — entity has [App-100, App-200] mapped

Relevant legacy columns (values are IDs, alt+enter/newline-separated if multiple):
- `PRIMARY IT APPLICATIONS (MAPPED)` -> flag Technology, Data as recommended
- `SECONDARY IT APPLICATIONS (RELATED OR RELIED ON)` -> same, lower confidence
- `PRIMARY TLM THIRD PARTY ENGAGEMENT` -> flag Third Party as recommended
- `SECONDARY TLM THIRD PARTY ENGAGEMENTS (RELATED OR RELIED ON)` -> same, lower confidence

#### Additional Evidence Sources — Control and Process Area Descriptions
Add control descriptions and key process area descriptions as supplementary
evidence sources for keyword matching, alongside the existing sub-risk descriptions
and rationale text. These should be:
- Scored separately and labeled in the evidence trail (e.g., "control [Daily
  data quality monitoring]: data quality")
- Used to reinforce matches or break ties, not as primary applicability signals
- Audit entity overview is intentionally excluded — overviews are too broad and
  would produce false positives across most L2s

Requires: ingestion of control and process area description files, column mapping
configuration, and integration into `_resolve_multi_mapping` evidence scoring.

#### Cross-Pillar Keyword Leakage Detection
Legacy rationale text sometimes references risks that belong to a different pillar
(e.g., "Operational" rationale mentioning "outsourcing" which is really Third Party).
Detect and log when keywords from one L2 appear in a different pillar's rationale
as an informational flag for reviewers.

#### Differentiated Control Columns
The three control columns (`iag_control_effectiveness`, `aligned_assurance_rating`,
`management_awareness_rating`) currently all receive the same legacy control rating.
When the new taxonomy defines distinct assessment criteria for each, implement
differentiated logic. The column structure may also change (may not be 3 columns).

#### Rationale Dimension Parsing - Fuzzy Matching
Legacy rationale text may contain misspellings of rating words (e.g., "medum",
"hgih"). Consider adding fuzzy matching for dimension extraction to capture
these cases. Evaluate whether the noise-to-signal ratio justifies the complexity.

### Considered but Deferred

#### Default Non-Applicability by Entity Type
No entity types have default non-applicable L2s — all 23 L2s are potentially
applicable to any entity. Revisit if the taxonomy team defines entity-type-based
defaults.

#### Country Overlay Rating Influence
Country overlay currently flags target L2s without modifying their ratings.
Could optionally bump target L2 ratings when country risk is higher, but
stakeholders prefer manual review over automatic adjustment.
