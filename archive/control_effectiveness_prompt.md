# Prompt: Add Control Effectiveness Assessment to Risk Taxonomy Transformer

## Context

I have a working Python script (`risk_taxonomy_transformer.py`) that transforms legacy 14-pillar risk assessments into a new 6 L1 / 23 L2 risk taxonomy. The script currently handles the **applicability** and **inherent risk** sides well. It produces an Excel workbook with Audit Review, Risk Owner Review, Dashboard, and other tabs.

The three control columns (`iag_control_effectiveness`, `aligned_assurance_rating`, `management_awareness_rating`) are currently all set to the same legacy control assessment value as a placeholder. I want to replace them with a proper control effectiveness assessment.

## What I Want Built

Replace the three identical control columns with two new columns:

1. **Control Effectiveness Baseline** — derived from the last audit engagement rating for the entity
2. **Impact of Issues** — a structured text summary of all open items (findings, OREs, enterprise findings, and eventually regulatory items) tagged to this entity-L2 combination, plus a staleness indicator for the baseline

The tool should **not** compute a final suggested control rating. It assembles the inputs and presents them so the reviewer can make the determination. The output is informational, not prescriptive.

## Data Sources

### Already integrated in the script:
- **Audit findings** — ingested via `ingest_findings()` and indexed via `build_findings_index()`. Keyed on `(entity_id, l2)`. Each finding has: issue_id, severity, status, issue_title, remediation_date.

### New data sources to integrate:

- **Last audit rating** — available in the legacy risk data file (or a joinable source).
  - Column name: [FILL IN YOUR COLUMN NAME]
  - Values: Satisfactory, Requires Attention, Needs Improvement, Unsatisfactory
  - Baseline mapping to add in `taxonomy_config.yaml`:
    ```yaml
    audit_rating_baseline_map:
      satisfactory: "Well Controlled"
      requires attention: "Moderately Controlled"
      needs improvement: "Inadequately Controlled"
      unsatisfactory: "Poorly Controlled"
    ```

- **Last audit completion date** — available in the legacy risk data file.
  - Column name: [FILL IN YOUR COLUMN NAME]
  - Used to compute staleness: months since completion, with labels:
    - 0-6 months: "Current"
    - 7-12 months: "Aging"
    - 13-18 months: "Stale"
    - 18+ months: "Outdated"

- **ORE mappings** — produced by `ore_mapper.py` (separate script, already built).
  - File pattern: `data/input/ore_mapping_*.xlsx` (copy from output to input, or adjust path)
  - Sheet: `All_Mappings`
  - Key columns: `Event ID`, `Audit Entity ID`, `Match 1 - L2`, `Match 1 - Score`, `Classification`
  - Only use OREs where Classification = "Confident"
  - ORE severity/status columns (if present): [FILL IN COLUMN NAMES OR NOTE IF ABSENT]

- **Enterprise findings** — produced by [YOUR ENTERPRISE FINDINGS MAPPER SCRIPT].
  - File pattern: [FILL IN]
  - Key columns: [FILL IN — entity_id, l2, severity, status, or equivalent]

- **Regulatory findings / RAPs** — [FILL IN IF AVAILABLE, OTHERWISE NOTE "not yet available — build the pipeline to accept this later as an additional data source with the same pattern"]

## Implementation Requirements

### 1. New ingestion functions

Create ingestion functions following the existing patterns (`ingest_findings` is the template):

- `ingest_ore_mappings(filepath, ...)` → reads ORE mapper output, filters to Confident classifications, returns DataFrame with standardized columns
- `ingest_enterprise_findings(filepath, ...)` → reads enterprise findings, normalizes L2 names via existing `normalize_l2_name()`, returns DataFrame
- Build index functions for each: `build_ore_index()`, `build_enterprise_findings_index()` → same shape as `build_findings_index()`: `{entity_id: {l2: [list of item dicts]}}`

### 2. Control effectiveness computation

Create a new function `derive_control_effectiveness()` that runs after `derive_inherent_risk_rating()` in the pipeline. It should:

- Look up the entity's last audit rating and map it to the baseline using the config
- Look up the entity's last audit completion date and compute staleness
- For each entity-L2 row, gather all open items from all indexes (findings, OREs, enterprise findings)
- Build the two new columns:

**Control Effectiveness Baseline** format:
```
Well Controlled (Last audit: Satisfactory, March 2024, Current)
```
or
```
Moderately Controlled (Last audit: Requires Attention, September 2022, Stale)
```

**Impact of Issues** format:
```
2 audit findings (1 High open, 1 Medium in validation) · 3 OREs (2 Medium, 1 Low) · No enterprise findings
```
or if nothing:
```
No open items
```

### 3. Integration points

- Add the new data source ingestion to `main()`, following the existing pattern of auto-detecting files by glob pattern
- Pass the new indexes through `TransformContext` (add fields to the dataclass)
- The `_make_row()` function currently has `iag_control_effectiveness`, `aligned_assurance_rating`, `management_awareness_rating` — replace these three with `control_effectiveness_baseline` and `impact_of_issues`
- Update `build_audit_review_df()` to include the two new columns in place of the old three
- Update `build_risk_owner_review_df()` similarly
- Update `export_results()` column lists and formatting

### 4. What NOT to change

- Do not modify the applicability determination logic (`_resolve_multi_mapping`, `transform_entity`, keyword matching, evidence scoring)
- Do not modify the inherent risk rating derivation
- Do not change the existing findings integration for applicability (findings confirming L2 applicability is separate from findings impacting control effectiveness — the same finding serves both purposes)
- Do not remove the existing `flag_control_contradictions()` function yet — it can coexist until the new approach is validated, then be removed later
- Keep all existing tabs and their content intact; just update the column structure within them

### 5. Config additions

Add to `taxonomy_config.yaml`:

```yaml
# Control Effectiveness Assessment
audit_rating_baseline_map:
  satisfactory: "Well Controlled"
  requires attention: "Moderately Controlled"
  needs improvement: "Inadequately Controlled"
  unsatisfactory: "Poorly Controlled"

staleness_thresholds_months:
  current: 6
  aging: 12
  stale: 18
  # anything beyond stale threshold = "Outdated"

# Which ORE classifications to include in control impact
ore_confidence_filter:
  - "Confident"
```

### 6. Methodology tab updates

Add a new section to the methodology data explaining:
- What Control Effectiveness Baseline means and where it comes from
- What Impact of Issues contains and which data sources feed it
- That the tool does not compute a final control rating — the reviewer determines that
- Staleness labels and what they mean

## Existing Code Reference

The full `risk_taxonomy_transformer.py` is attached. Key functions to study before modifying:

- `ingest_findings()` and `build_findings_index()` — pattern for new ingestion functions
- `TransformContext` dataclass — where to add new indexes
- `_make_row()` — where output row columns are defined
- `transform_entity()` — where control values are currently assigned per row
- `derive_inherent_risk_rating()` — runs just before where `derive_control_effectiveness()` should go
- `build_audit_review_df()` — where output columns are selected and renamed
- `export_results()` — where everything comes together

## Output

Give me the implementation as:
1. New/modified functions with full code
2. Changes to existing functions called out as diffs (show the old code and new code)
3. Additions to `taxonomy_config.yaml`
4. Updated methodology content
