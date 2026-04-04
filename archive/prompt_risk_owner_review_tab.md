# Prompt: Build a Risk Owner Review Tab

## Context

You are extending a Python tool called the Risk Taxonomy Transformer (`risk_taxonomy_transformer.py`). The tool transforms legacy 14-pillar risk assessments into a new 6 L1 / 23 L2 risk taxonomy for audit entities. It produces an Excel workbook with multiple tabs, the primary one being `Audit_Review` — a tab where every row is one entity + one L2 risk, with proposed statuses, ratings, evidence, and reviewer columns.

The `Audit_Review` tab is entity-centric: designed for audit leaders who own entities and review all 23 L2 risks for each of their entities. It is sorted by Audit Leader → Entity ID → within-entity priority.

There is a second persona: the **Risk Category Owner (RCO)**. An RCO owns a single L2 risk (e.g., Privacy, or Information and Cyber Security) across the entire audit portfolio — 200+ entities. They need to see their one L2 risk horizontally across every entity to catch errors, spot false negatives, validate ratings for consistency, and flag disagreements before audit leaders finalize assessments.

An RCO can filter `Audit_Review` to their L2 and get a usable starting point. But the filtered `Audit_Review` tab lacks several things they need:

1. **Cross-entity priority sorting** — the current sort is entity-first; an RCO needs rows sorted by "most likely to be wrong" across all entities for their L2
2. **Sibling L2 context** — whether other L2s under the same L1 are Applicable/High for an entity is a strong false-negative signal when this L2 is proposed N/A
3. **False negative flagging** — explicit flags when the tool proposes N/A but signals suggest the risk should apply
4. **Peer rating comparison** — how each entity's rating compares to peer entities in the same business line, to catch outliers
5. **RCO action columns** — separate from the audit leader's Reviewer columns, so both can work in parallel on separate copies

Additionally, RCOs work in silos. The Privacy RCO and the Data RCO may review simultaneously without seeing each other's overrides. Since sibling L2s under the same L1 are often owned by different people, the tool needs to support a **multi-pass workflow** where RCO overrides from round 1 propagate into sibling context for round 2.

## Your Task

Build two things:

### 1. A single `Risk_Owner_Review` tab

One tab. Every entity × L2 combination gets one row — same row count as `Audit_Review`, but with additional computed columns and a different sort order. RCOs filter this tab to their L2 using Excel's autofilter. The sort order is designed so that filtering to any single L2 produces a review-ready list sorted by priority.

This tab is **hidden** by default (same as Side_by_Side — unhide when needed).

### 2. A `Risk_Owner_Summary` tab

One **visible** tab. One row per L2 risk showing portfolio-wide counts, distribution, and alert counts. An RCO finds their L2 row, reads the headline numbers, and knows which issues to look for when they filter the detail tab.

### 3. RCO override ingestion (multi-pass support)

A new input file type — `rco_overrides` — that feeds RCO decisions back into the tool on subsequent runs. These overrides:
- Confirm or change applicability status for specific entity × L2 combinations
- Are reflected in sibling triangulation on the next run (so other RCOs see human-validated sibling context, not just tool proposals)
- Are labeled distinctly from tool proposals in the sibling context columns

## Data Available

The function receives:

- `transformed_df` (pd.DataFrame) — the full transformed dataset. Key columns:
  - `entity_id`, `new_l1`, `new_l2`, `composite_key`
  - `likelihood`, `impact_financial`, `impact_reputational`, `impact_consumer_harm`, `impact_regulatory`
  - `iag_control_effectiveness`, `aligned_assurance_rating`, `management_awareness_rating`
  - `source_legacy_pillar`, `source_risk_rating_raw`, `source_rationale`, `source_control_raw`, `source_control_rationale`
  - `mapping_type`, `confidence`, `method`
  - `dims_parsed_from_rationale`, `sub_risk_evidence`, `needs_review`
  - `inherent_risk_rating`, `inherent_risk_rating_label`, `overall_impact`
  - `control_flag`, `app_flag`, `aux_flag`, `cross_boundary_flag`
  - `overlay_flag`, `overlay_source`, `overlay_rating`, `overlay_rationale`

- `legacy_df` (pd.DataFrame) — original entity data with metadata:
  - Entity ID column (name passed as `entity_id_col`)
  - `Audit Entity Name`, `Audit Entity Overview`, `Audit Leader`, `PGA/ASL`, `Core Audit Team`

- `entity_id_col` (str) — column name for entity ID in `legacy_df`

- `findings_index` (dict or None) — `{entity_id: {l2_risk: [finding dicts]}}` where each finding dict has `issue_id`, `severity`, `status`, `issue_title`, `remediation_date`

- `rco_overrides` (dict or None) — `{(entity_id, l2): {"status": str, "rating": str, "source": "rco_override"}}` loaded from the RCO override file. See Section on RCO Override Ingestion below.

You also have access to:
- `L2_TO_L1` (dict) — maps each L2 name to its parent L1
- `NEW_TAXONOMY` (dict) — maps each L1 to its list of L2s
- `_derive_status(method)` — maps method strings to human-readable statuses
- `_derive_decision_basis(row)` — produces plain-language explanation

## Function Signatures

```python
def build_risk_owner_review_df(
    transformed_df: pd.DataFrame,
    legacy_df: pd.DataFrame,
    entity_id_col: str,
    findings_index: dict | None = None,
    rco_overrides: dict | None = None,
) -> pd.DataFrame:
    """Build the Risk Owner Review dataframe with all entity x L2 rows,
    enriched with sibling context, false-negative flags, and peer comparison."""

def build_ro_summary_df(
    ro_review_df: pd.DataFrame,
    findings_index: dict | None = None,
) -> pd.DataFrame:
    """Build the Risk Owner Summary dataframe with one row per L2."""
```

## Column Specification for Risk_Owner_Review Tab

Produce these columns in this order. One row per entity × L2 combination.

### Entity Context Block

| Column Name | Source | Notes |
|---|---|---|
| Entity ID | `entity_id` | |
| Entity Name | `Audit Entity Name` from `legacy_df` join | |
| Entity Overview | `Audit Entity Overview` from `legacy_df` join | First 300 characters |
| Audit Leader | `Audit Leader` from `legacy_df` join | |
| Business Line | `PGA/ASL` from `legacy_df` join | |

### Risk Identity Block

| Column Name | Source | Notes |
|---|---|---|
| L1 | `new_l1` | Included so the RCO can verify their L2's parent L1 and so the tab is self-describing when filtered |
| L2 | `new_l2` | The primary filter column. RCO filters this to their risk |
| Review Priority | Computed (see Sort Order section) | Integer score. Positioned here so it's visible early when scrolling right |

### Tool Proposal Block

| Column Name | Source | Notes |
|---|---|---|
| Proposed Status | `_derive_status(method)` | |
| Proposed Rating | `inherent_risk_rating_label` | |
| Confidence | `confidence` | |
| Legacy Source | `source_legacy_pillar` | |
| Legacy Pillar Rating | `source_risk_rating_raw` | |
| Method | `method` | Raw method string. RCOs who use the tool regularly scan method codes faster than prose |
| Decision Basis | `_derive_decision_basis(row)` | Prose explanation, for reference |

### Evidence Block

| Column Name | Source | Computation |
|---|---|---|
| Keyword Hits | Parsed from `sub_risk_evidence` | Extract keyword portions only. From entries like `"rationale: data, privacy"` and `"sub-risk KR-123 [desc...]: encryption, pii"`, extract: `"data, privacy, encryption, pii"`. If `sub_risk_evidence` is empty or starts with `"siblings_with_evidence:"`, leave blank. If method is `"issue_confirmed"`, leave blank (finding info goes in Finding Reference) |
| Sub-Risk IDs | Parsed from `sub_risk_evidence` | Extract sub-risk ID portions only (e.g., `"KR-123, KR-456"`). These appear after `"sub-risk "` and before `" ["` in the evidence string |
| Finding Reference | From `findings_index` for this entity + L2 | Format: `"FND-001 (High, Open); FND-002 (Medium, In Validation)"`. Up to 3 findings. Blank if none |
| Source Rationale Excerpt | `source_rationale` | First 300 characters |

### Signal Block

| Column Name | Source |
|---|---|
| Application Flag | `app_flag` for this row |
| Auxiliary Risk Flag | `aux_flag` for this row |
| Cross-Boundary Flag | `cross_boundary_flag` for this row |
| Control Flag | `control_flag` for this row |

### Sibling Context Block (new — not present on Audit_Review)

These columns are the core value-add of the RCO view. They require cross-referencing other L2 rows for the same entity.

**Pre-computation step:** Before building these columns, create a lookup structure:

```python
# {entity_id: {l2: {"status": str, "rating": str, "source": "tool" | "rco_override"}}}
entity_l2_status = {}
```

Populate from `transformed_df` (all rows get source="tool"). Then overlay `rco_overrides` on top — any entity × L2 key in `rco_overrides` replaces the tool's status/rating and gets source="rco_override". This means sibling triangulation reflects RCO overrides from prior runs.

| Column Name | Computation |
|---|---|
| Sibling L2 Summary | Look up this row's L2 parent L1 via `L2_TO_L1`. Find all other L2s under that L1 via `NEW_TAXONOMY`. For each sibling, get its status and rating from `entity_l2_status` for this entity. Format each as `"{L2}: {Status}-{Rating}"` and append `"(RCO)"` if source is `"rco_override"`. Example: `"Data: Applicable-High (RCO) | Processing: Applicable-Medium | Fraud: N/A"`. Only include siblings that are Applicable or have a populated status — skip true gap fills to reduce noise. If no siblings have meaningful status, show `"No sibling L2s applicable"` |
| Sibling Alert | If any sibling L2 (same L1) is Applicable at High or Critical for this entity, AND this row's Proposed Status is N/A-adjacent (`"Not Applicable"`, `"No Evidence Found — Verify N/A"`, `"Not Assessed"`), set to: `"⚠ {Sibling L2 Name} is {Rating}{' (RCO-validated)' if source is rco_override else ''} but this L2 is {Status}"`. Show the single highest-rated sibling that triggers the alert. If multiple siblings trigger, pick the one with the highest rating (Critical > High). Otherwise blank |
| Peer Group Rating | Among entities in the same `PGA/ASL` business line, for this L2, count those with Proposed Status = "Applicable" and compute the modal Proposed Rating. Format: `"Peer modal: Medium (14 of 18 peers)"`. If this entity's rating differs from the mode, append `" — this entity is {Rating}"`. If fewer than 3 applicable peers, show `"Insufficient peers"`. If `PGA/ASL` column is not available, show `"Business line not available"` |

### RCO Action Columns

| Column Name | Default | Notes |
|---|---|---|
| RCO Agrees | Blank | Risk owner fills: Yes / No / Needs Discussion |
| RCO Recommended Status | Blank | Risk owner fills: Confirmed Applicable / Confirmed Not Applicable / Escalate |
| RCO Recommended Rating | Blank | Risk owner fills: Low / Medium / High / Critical |
| RCO Comment | Blank | Free text. This is the reasoning communicated to the audit leader |

## Sort Order

The sort must work well both for the full tab (all L2s) and when filtered to any single L2. Primary sort is by L2 (so filtering preserves within-L2 ordering), then by priority score descending within each L2.

### Priority scoring (computed per row):

```
100 — Proposed Status is N/A-adjacent AND any signal flag is populated
       (app_flag, aux_flag, cross_boundary_flag, control_flag, or Sibling Alert)
       These are the most likely false negatives.

 95 — Sibling Alert is populated (sibling High/Critical, this L2 is N/A-adjacent)
       Note: a row can score both 100 and 95; use the max (100).

 90 — Proposed Status is "Applicability Undetermined"
       Tool couldn't decide. RCO should weigh in.

 80 — Proposed Status is "Applicable" AND Confidence is "medium" or "low"
       Potential false positive — low-confidence match needs validation.

 70 — Proposed Status is "No Evidence Found — Verify N/A" AND no signal flags populated
       No contradicting signals, but still unverified.

 60 — Proposed Status is "Not Assessed"
       Structural gap, needs first-time assessment.

 50 — Proposed Status is "Applicable" AND Proposed Rating is "High" or "Critical"
       Likely correct, but rating consistency matters.

 40 — Proposed Status is "Applicable" AND Proposed Rating is "Low" or "Medium"
       Lowest urgency among applicable rows.

 20 — Proposed Status is "Not Applicable" AND no signal flags populated
       Legacy N/A carried forward, no contradicting evidence.

 10 — Default / fallback
```

Final sort: `L2 ascending → Review Priority descending → Business Line ascending → Entity Name ascending`

The `Review Priority` column (integer) is included in the output so RCOs can re-sort if preferred.

**N/A-adjacent statuses** (referenced in scoring): `"Not Applicable"`, `"No Evidence Found — Verify N/A"`, `"Not Assessed"`.

**Internal helper columns** used for scoring (`has_any_signal`, `signal_contradicts_na`) should be used for computation but **dropped before final output**. However, apply any conditional row formatting (see Formatting section) before dropping them.

## Risk_Owner_Summary Tab Specification

One row per L2 risk. Sorted by L1 then L2.

| Column | Computation |
|---|---|
| L1 | Parent L1 name |
| L2 | L2 risk name |
| Total Entities | Count of unique entities in the portfolio |
| Applicable | Count where Proposed Status = "Applicable" |
| Applicable % | Applicable / Total Entities |
| Not Applicable | Count where Proposed Status = "Not Applicable" |
| No Evidence — Verify | Count where Proposed Status starts with "No Evidence Found" |
| Undetermined | Count where Proposed Status = "Applicability Undetermined" |
| Not Assessed | Count where Proposed Status = "Not Assessed" |
| High/Critical | Count where Proposed Rating is "High" or "Critical" |
| Contradicted N/A | Count where Proposed Status is N/A-adjacent AND any signal flag is populated (the priority-100 rows) |
| Sibling Alerts | Count where Sibling Alert column is populated |
| Open Findings | Count of entities with ≥1 finding for this L2 in `findings_index` |
| RCO Reviews Done | Count where RCO Agrees is not blank (will be 0 on initial generation; updates when the file is re-read) |

Format `Applicable %` as percentage. Bold the `Contradicted N/A` and `Sibling Alerts` cells if their value is > 0.

## RCO Override Ingestion (Multi-Pass Support)

### Purpose

RCOs work in silos. The Privacy RCO and the Data RCO review simultaneously without seeing each other's overrides. Since sibling L2s under the same L1 are often owned by different people, a Privacy RCO's override to Applicable-High should appear as validated sibling context for the Data RCO on the next run. Without this, sibling triangulation only reflects tool proposals — never human-validated judgments.

### Override File Format

File: `rco_overrides_*.xlsx` or `rco_overrides_*.csv` in the input directory. Auto-detected like other input files.

| Column | Required | Description |
|---|---|---|
| entity_id | Yes | Audit Entity ID |
| l2_risk | Yes | Canonical L2 risk name |
| rco_status | Yes | `"Confirmed Applicable"` or `"Confirmed Not Applicable"` or `"Escalate"` |
| rco_rating | No | `"Low"`, `"Medium"`, `"High"`, or `"Critical"`. Required if status is Confirmed Applicable |
| rco_name | No | Name of the RCO who made the determination |
| rco_comment | No | Reasoning |

### Ingestion Function

```python
def ingest_rco_overrides(filepath: str) -> dict:
    """Load RCO overrides from Excel/CSV.

    Returns dict: {(entity_id, l2): {
        "status": str,
        "rating": str or None,
        "source": "rco_override",
        "rco_name": str or "",
        "comment": str or "",
    }}
    """
```

Normalize L2 names using the existing `normalize_l2_name()` function. Skip rows with unrecognized L2 names (log a warning). Skip rows with invalid status values.

### How Overrides Affect the Output

RCO overrides affect **only** the sibling context columns on the `Risk_Owner_Review` tab. They do NOT:
- Change the Proposed Status or Proposed Rating columns (those always reflect the tool's determination)
- Modify any data on the `Audit_Review` tab
- Alter any other tab

The effect is specifically:
1. In the `entity_l2_status` lookup used for sibling triangulation, RCO overrides replace the tool's status/rating for that entity × L2 combination
2. In the `Sibling L2 Summary` column, overridden siblings get an `"(RCO)"` tag so the reader knows the sibling signal is human-validated, not a tool guess
3. In the `Sibling Alert` column, RCO-validated siblings get `"(RCO-validated)"` in the alert text, which carries more weight than a tool proposal

### Multi-Pass Workflow

The intended workflow:
1. **Run 1:** Tool runs with no RCO overrides. Produces output with sibling context based on tool proposals only.
2. **RCO Round 1:** Each RCO reviews their L2, fills in RCO action columns, exports their overrides.
3. **Run 2:** Tool reruns with `rco_overrides` file containing round-1 decisions from all RCOs who have completed review. Sibling context now reflects validated judgments. RCOs who haven't reviewed yet (or are doing a second pass) see enriched sibling signals.
4. **Iterate** as needed. Each run incorporates the latest RCO override file.

### Integration into main()

Add to `main()` alongside other optional input file detection:

```python
# RCO Override file (optional — produced by RCOs after reviewing Risk_Owner_Review tab)
rco_override_files = sorted(
    list(input_dir.glob("rco_overrides_*.xlsx")) +
    list(input_dir.glob("rco_overrides_*.csv")),
    key=lambda f: f.stat().st_mtime,
)
rco_override_path = str(rco_override_files[-1]) if rco_override_files else None
if rco_override_path:
    logger.info(f"Using RCO override file: {rco_override_path}")

# ... later, after pipeline runs:
rco_overrides = None
if rco_override_path:
    rco_overrides = ingest_rco_overrides(rco_override_path)
```

Pass `rco_overrides` to `build_risk_owner_review_df()`.

## Integration into export_results()

In the existing `export_results()` function, after writing all current tabs and before formatting:

```python
# --- Risk Owner Review tab ---
ro_review_df = build_risk_owner_review_df(
    transformed_df, legacy_df, entity_id_col,
    findings_index=findings_index,
    rco_overrides=rco_overrides,
)
ro_review_df.to_excel(writer, sheet_name="Risk_Owner_Review", index=False)

# --- Risk Owner Summary tab ---
ro_summary_df = build_ro_summary_df(ro_review_df, findings_index=findings_index)
ro_summary_df.to_excel(writer, sheet_name="Risk_Owner_Summary", index=False)
```

Add `rco_overrides` as a parameter to `export_results()`.

## Formatting

Apply during the openpyxl formatting pass:

### Risk_Owner_Review tab:
- **Header styling:** Same as other tabs — use existing `style_header()` function
- **Freeze panes:** `C2` (freeze Entity ID and Entity Name columns + header row)
- **Auto-filter:** On all columns, full data range
- **Column widths:** Entity Overview: 40, Decision Basis: 50, Source Rationale Excerpt: 50, Sibling L2 Summary: 45, Sibling Alert: 30, RCO Comment: 40. All others: auto-fit capped at 25
- **Text wrap** (using `Alignment(wrap_text=True, vertical="top")`): Entity Overview, Decision Basis, Source Rationale Excerpt, Sibling L2 Summary, Sibling Alert, Peer Group Rating, RCO Comment
- **Row height:** 45 for all data rows
- **Proposed Status cell coloring:** Same status fills used on Audit_Review — green for Applicable, gray for Not Applicable, yellow for Undetermined, orange for No Evidence Found, blue for Not Assessed
- **Sibling Alert cell coloring:** Orange fill (`PatternFill("solid", fgColor="FCE4D6")`) on Sibling Alert cells when populated
- **Contradicted N/A row coloring:** Light red fill (`PatternFill("solid", fgColor="FFC7CE")`) on the entire row for any row where priority score is 100 (N/A-adjacent with contradicting signals). Apply this fill to all cells in the row BEFORE dropping the internal helper columns
- **RCO action column headers:** Green fill (`PatternFill("solid", fgColor="E2EFDA")`) to visually distinguish them as input columns
- **Column grouping:** Group and collapse (hidden, outlineLevel=1) the rating detail columns from Likelihood through Management Awareness Rating, same as Audit_Review does. Also group Decision Basis and Source Rationale Excerpt (these are reference columns the RCO expands when needed)

### Risk_Owner_Summary tab:
- **Header styling:** Same `style_header()` function
- **Column widths:** L2: 35, all count columns: 15, Applicable %: 12
- **Conditional bold:** Bold cell values in Contradicted N/A and Sibling Alerts columns where value > 0
- **Applicable % formatting:** Percentage format `'0.0%'`
- **Freeze panes:** `C2`

### Tab visibility and ordering:
- `Risk_Owner_Summary` — **visible**, positioned after Dashboard and before Audit_Review
- `Risk_Owner_Review` — **hidden** (RCOs unhide it; keeps the workbook clean for audit leaders who don't need it)
- All other tabs: unchanged

Updated desired tab order:
```python
desired_order = [
    "Dashboard", "Risk_Owner_Summary", "Audit_Review", "Methodology",
    # Hidden tabs
    "Risk_Owner_Review", "Review_Queue", "Side_by_Side",
    "Source - Legacy Data", "Source - Findings", "Source - Sub-Risks",
    "Overlay_Flags",
]
```

## Performance

The portfolio is 200+ entities × 23 L2s = 4,600+ rows on Risk_Owner_Review. The sibling computation cross-references rows for the same entity across different L2s. Do NOT iterate the full DataFrame per row. Instead:

1. **Pre-build an entity-L2 lookup** before iterating:
```python
# {entity_id: {l2: {"status": str, "rating": str, "source": str}}}
entity_l2_lookup = defaultdict(dict)
for _, row in transformed_df.iterrows():
    eid = str(row["entity_id"])
    l2 = row["new_l2"]
    entity_l2_lookup[eid][l2] = {
        "status": _derive_status(row["method"]),
        "rating": str(row.get("inherent_risk_rating_label", "") or ""),
        "source": "tool",
    }
# Overlay RCO overrides
if rco_overrides:
    for (eid, l2), override in rco_overrides.items():
        entity_l2_lookup[eid][l2] = {
            "status": override["status"],
            "rating": override.get("rating", ""),
            "source": "rco_override",
        }
```

2. **Pre-build peer group data** before iterating:
```python
# {(business_line, l2): Counter of ratings among Applicable entities}
from collections import Counter
peer_ratings = defaultdict(Counter)
# ... populate from transformed_df rows where status is Applicable
```

3. **Pre-build entity metadata lookup** from legacy_df once.

4. Then iterate `transformed_df` once to build all columns.

## Edge Cases

- If `findings_index` is None: leave Finding Reference blank, show 0 for Open Findings in summary.
- If `legacy_df` doesn't have `PGA/ASL`: skip Peer Group Rating (show `"Business line not available"`), omit Business Line column.
- If `rco_overrides` is None: all sibling context reflects tool proposals only. No `"(RCO)"` tags appear. This is the expected state on the first run.
- If an L2 has zero Applicable entities: it still appears in the summary with all zeros. RCO needs to see that.
- `sub_risk_evidence` parsing:
  - `"rationale: data, privacy, encryption"` → keywords: `"data, privacy, encryption"`
  - `"sub-risk KR-123 [Risk of data breach...]: data breach, encryption"` → sub-risk ID: `"KR-123"`, keywords: `"data breach, encryption"`
  - `"siblings_with_evidence: Data; Privacy"` → NOT keyword evidence; skip
  - Evidence from `issue_confirmed` method (finding summaries) → skip for Keyword Hits column; use Finding Reference column instead
- Sibling computation: an L2's siblings are all other L2s under the same L1, NOT including itself. If an L1 has only one L2, Sibling L2 Summary should show `"Only L2 under this L1"`.

## Constraints

- Do not modify any existing tabs or their content. The new tabs are additive.
- Do not add dependencies beyond what the tool already imports (pandas, openpyxl, re, logging, collections, dataclasses, datetime, pathlib, yaml).
- Follow the existing code style: type hints, docstrings, `logger.info` for key steps, underscore-prefixed internal helpers.
- The `rco_overrides` parameter should be optional throughout — the tool must produce valid output with or without it, and all existing behavior must be unchanged when it's absent.
