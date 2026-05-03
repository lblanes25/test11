# Data Flow Reference — Risk Taxonomy Transformer

How each input file flows through the pipeline. For every column or data type: where it's read, what transformations apply, where it ultimately lands, and what gets filtered or ignored.

Companion to `methodology_reference.md` (which covers the *rules*). This file covers the *plumbing*.

---

## File: `legacy_risk_data_*.xlsx`

The primary input. Wide-format, one row per entity (after dedup). Drives the row count of the final workbook — every L2 row in `Audit_Review` originates from an entity in this file.

### Where it gets loaded

`__main__.py:84` finds the most recent file by mtime in `data/input/`. Ingested at `ingestion.py:26-57` via `ingest_legacy_data()`.

Processing:
1. Read Excel or CSV.
2. Strip whitespace from column names.
3. Optional dedup by report date (lines 48-54): `pd.to_datetime(..., errors="coerce")` → sort desc → keep first per entity.

Result: one DataFrame, one row per entity, all columns preserved.

The DataFrame is then passed to multiple consumers in parallel. There is no single linear path.

### Per-pillar **Risk Rating** (e.g., `Credit Inherent Risk`)

**Read at:** `mapping.py:315` via `entity_row.get(cols.get("rating"))` for each pillar in `crosswalk_config`.

**Conversion:** `rating.py:convert_risk_rating()` strips, lowercases, looks up in `RISK_RATING_MAP` from YAML (`low: 1, medium: 2, high: 3, critical: 4`). Returns int or None.

**Branches:**
- **N/A** (`raw_str in NA_STRINGS` after `convert_risk_rating` returned None): emits a `source_not_applicable` row for every candidate L2 in that pillar's mapping. `likelihood=None`, no rating numbers. Status downstream: "Not Applicable."
- **Numeric** (Low–Critical): the rating is fanned out to **all five risk dimensions** (`likelihood, impact_financial, impact_reputational, impact_consumer_harm, impact_regulatory`) as the default value at `mapping.py:357-361`. Rationale parsing can override individual dimensions.
- **Anything else** (numeric like "3", typos, blank): silently treated as `None`.

**Final fate:**
- Stored on the transformed row as `source_risk_rating_raw` (original string, audit trail) and as the five dimension columns (numeric).
- Numeric likelihood × max(impact) flows through `enrichment.py:derive_inherent_risk_rating` (line 31) into the composite `Inherent Risk Rating` shown in Audit_Review.
- **For multi-mapping pillars, `review_builders.py:528-541` clears the `Proposed Rating` column** in Audit_Review for any non-pure-direct row. The legacy rating is moved to a `Source Rating` column for reference. Only pure 1:1 direct mappings carry the rating into the displayed `Proposed Rating`. HTML inherits this clearing because it reads from Audit_Review.
- The full inherited rating IS still visible in `Side_by_Side` (debug tab) for traceability.

**Filtered / ignored:**
- Whitespace and case differences ignored.
- Numeric values in the cell ("3") not in the map → silently None.
- "N/A" recognized via the `na_strings:` config list (`not applicable`, `n/a`, `na`, ``).

### Per-pillar **Rationale** (e.g., `Credit Inherent Risk Rationale`)

**Read at:** `mapping.py:316` via `entity_row.get(cols.get("rationale"), "")`. Only pillars in `pillars_with_rationale` (YAML) have these columns; for `pillars_without_rationale` (IT, InfoSec, Third Party), the rationale field is absent and treated as empty.

The rationale text is used in **three independent ways**:

#### Use 1: Dimension extraction (`rating.py:parse_rationale_for_dimensions`)

Regex-scans the lowered rationale for explicit dimension mentions. Three patterns per "likelihood" / "impact":
- `likelihood: high`, `likelihood is rated medium`, `likelihood = critical` (separator-based)
- `the likelihood of X is high` (5-word window before "is/of")
- `high likelihood` (rating before dimension)

Plus abbreviations: `L: High`, `I: Medium`. Plus per-impact-type splits: `financial impact: high`, `regulatory impact - medium`, `impact (consumer): low`.

If matched, that dimension on the row is overridden from the default rating numeric.

#### Use 2: Multi-mapping keyword scoring (`mapping.py:_resolve_multi_mapping`)

For every `multi`-type pillar, for every candidate L2 in that pillar's targets, the rationale is scanned for keywords from `KEYWORD_MAP[l2_name]` plus any `conditions` defined on that target. Every keyword hit adds 1 to the L2's score.

Score → confidence band:
- ≥3 hits: `high`
- 1–2 hits: `medium`
- 0 hits across all candidates: every candidate L2 gets a row with `Method.NO_EVIDENCE_ALL_CANDIDATES`, status = "Applicability Undetermined"

#### Use 3: Cross-boundary signal scanning (`flags.py:flag_cross_boundary_signals`)

After all transformation, the rationale is re-scanned — but this time looking for keywords from L2s the pillar does *not* map to. Hits with `total_hits >= min_hits_per_pillar` (default 2) become `cross_boundary_flag` on the relevant L2 row, surfacing as the "Also — referenced in:" block in Decision Basis.

Threshold of 2 catches sustained references and ignores stray mentions ("we considered fraud but it doesn't apply"). Trade-off: single specific mentions like "GDPR" or "OFAC" are missed. Documented in YAML and Methodology tab.

**Stored on row:** Full rationale text saved as `source_rationale` for audit trail.

**Filtered / ignored:**
- Empty/NaN rationale → empty parser dict, defaults stand.
- "n/a" / "not applicable" / "nan" rationales skip the cross-boundary scan (`flags.py:441`).
- Pillars without rationale (IT/InfoSec/Third Party): no rationale column at all. All primary targets get rows with default rating, high confidence (the "no rationale column" path at `mapping.py:386-396`).

### Per-pillar **Control Assessment** + **Control Rationale**

**Read at:** `mapping.py:317-318`. Stored on transformed row as `source_control_raw` and `source_control_rationale`.

**Used for:** Currently passive storage. The per-pillar control assessment is captured for the row but does **not** feed the Control Effectiveness Baseline today. The baseline string in Audit_Review comes from the entity-level `Last Engagement Rating`, not the per-pillar control rating. The per-pillar fields appear in `Source - Legacy Data` and `Side_by_Side` for traceability.

**Filtered / ignored:** Same conversion as risk rating (low/medium/high/critical → 1-4 via `CONTROL_RATING_MAP`). Anything else → None. Not re-checked downstream.

### **Last Engagement Rating, Last Audit Completion Date, Next Planned Audit Date**

**Read at:** `enrichment.py:derive_control_effectiveness` (lines 122-130). Builds `entity_audit_info[eid] = {rating, date, next_date}`.

**Used for:** `_format_baseline()` produces the `control_effectiveness_baseline` string for every row of that entity:

> `Well Controlled (Last audit: Satisfactory, June 2024 · Next planned: June 2026)`

The lookup `audit_rating_baseline_map:` in YAML translates legacy rating values (satisfactory → Well Controlled, needs improvement → Partially Effective, unsatisfactory → Ineffective).

**Filtered / ignored:**
- Empty/nan rating → "No engagement rating available".
- Bad date → "date unknown" / "not scheduled".
- Per-row: same baseline repeated for every L2 of that entity (it's an entity-level fact).

### **Application columns** (IT, Third Party, Models)

Five columns in YAML `columns.applications:`. Read at `flags.py:flag_application_applicability`.

**Used for:**
- Any IT app column non-empty + L2 ∈ {Technology, Data, Information and Cyber Security} → `app_flag=True` → "Additional Signals: [App] Listed in entity's IT applications"
- TP columns non-empty + L2 == Third Party → `tp_flag=True`
- Models column non-empty + L2 == Model → `model_flag=True`

**Filtered / ignored:**
- L2s outside `_APP_L2_MAP` get no flag regardless of column content.
- The actual app/TP/model IDs aren't currently parsed to a list — just emptiness/non-emptiness drives the flag. Inventory enrichment parses them separately.
- **Key designation is not currently considered.** Per RCO methodology, "key" apps/TPs should drive applicability differently than non-key. Tracked in `project_open_items.md` for May 15 RCO template review.

### **AXP / AENB Auxiliary Risk Dimensions**

**Read at:** `flags.py:flag_auxiliary_risks`. Each cell is a list of L2 names separated by commas/semicolons/newlines.

**Processing:**
1. Split on separators
2. Each token passed to `normalize_l2_name()` — strips L1 prefix, resolves aliases, returns canonical name or None
3. For each canonical L2: find the entity+L2 row, set `aux_flag = True`

**Used for:** "Additional Signals: [Aux] Listed as auxiliary risk in legacy entity data (AENB)" in Decision Basis. Doesn't change Status or Rating — informational only.

**Filtered / ignored:**
- Names that don't normalize → silently dropped, no warning per row.
- Empty cells: skipped.

### **AXP / AENB Core Risk Dimensions**

Same processing as Auxiliary, separate function: `flags.py:flag_core_risks`. Adds `core_flag` instead of `aux_flag`. Drives a different signal label and a different priority sort in Audit_Review (Core dimensions sort higher than Auxiliary).

### **Entity metadata** (Audit Entity ID, Audit Entity, Audit Leader, PGA, Entity Overview)

- **Audit Entity ID** is the join key throughout the pipeline. Stripped of whitespace at every consumer.
- **Audit Entity** (name), **Audit Leader**, **PGA**, **Entity Overview**: read by `review_builders.py:build_audit_review_df` and `export_html_report.py` for header rows and HTML drill-downs. Pure pass-through.

### **The legacy DataFrame as a whole**

After all consumers run, the entire unmodified `legacy_df` is written verbatim to the `Source - Legacy Data` sheet at `export.py`. Every column preserved, regardless of whether it's read by the pipeline. Visible by default since the 2026-05-02 visibility change.

### Things worth flagging

1. **Per-pillar Control Assessment is captured but unused for derivation.** The Control Effectiveness Baseline comes from `Last Engagement Rating`, not from the per-pillar control columns.
2. **Reputational and Country pillars are read for cross-boundary scanning only.** They have rationale columns that get scanned by `flag_cross_boundary_signals`, but their ratings aren't transformed (no crosswalk_config entries — Matt 2026-04-21 "Not Assessed" decision).
3. **Multi-mapping rating fanout is hidden in Audit_Review/HTML but still in Side_by_Side.** Reviewers don't see it on the primary tabs (`review_builders.py:528-541` clears `Proposed Rating` for non-pure-direct rows). Side_by_Side intentionally retains the value for debugging.

### Summary table

| Column type | Read where | Becomes | Filters / ignored |
|---|---|---|---|
| Per-pillar Inherent Risk | `mapping.py:315` | 5 dimension columns + `source_risk_rating_raw` | Non-Low/Med/High/Critical → None; N/A → SOURCE_NOT_APPLICABLE row |
| Per-pillar Inherent Risk Rationale | `mapping.py:316` | (1) parsed dimensions, (2) keyword scoring evidence, (3) cross-boundary signals; full text stored as `source_rationale` | "n/a" / blank → skipped; case-insensitive substring; no fuzzy match |
| Per-pillar Control Assessment | `mapping.py:317` | `source_control_raw` (passive storage) | Currently unused for derivation |
| Per-pillar Control Rationale | `mapping.py:318` | `source_control_rationale` (passive storage) | Not parsed |
| Last Engagement Rating + dates | `enrichment.py:122-130` | `control_effectiveness_baseline` string per row | Empty rating → "No engagement rating available"; bad dates → "date unknown" |
| Application columns (5) | `flags.py:flag_application_applicability` | `app_flag`, `tp_flag`, `model_flag` | Only fires for L2s in `_APP_L2_MAP`; emptiness/non-emptiness only; key designation ignored |
| AXP/AENB Auxiliary Risk Dimensions | `flags.py:flag_auxiliary_risks` | `aux_flag` + Additional Signal | Names not normalizing to canonical L2 silently dropped |
| AXP/AENB Core Risk Dimensions | `flags.py:flag_core_risks` | `core_flag` + Additional Signal | Same as auxiliary |
| Entity metadata | `review_builders.py`, HTML report | Pass-through into output | None |
| Whole DataFrame | `export.py` | `Source - Legacy Data` sheet (visible) | None — verbatim copy |

---

## File: `key_risks_*.xlsx` (formerly `sub_risk_descriptions_*.xlsx`)

Granular risks tagged to each audit entity, each linked to one or more legacy L1 pillars. Drives keyword scoring during multi-mapping resolution, feeds cross-boundary signals, and aggregates "key" app/TP IDs per entity.

The codebase calls these "key risks" since the 2026-05-02 rename — same terminology audit teams use in Archer. Old "sub-risk" naming was internal-only and confused leaders cross-referencing back to the source. The file glob accepts both new (`key_risks_*`) and legacy (`sub_risk_descriptions_*`) filenames for backward compat.

### Where it gets loaded

`__main__.py:90-100` finds the most recent file by mtime in `data/input/`, accepting either glob pattern. Ingested at `ingestion.py:74-136` via `ingest_key_risks()`.

### Expected columns (configurable in YAML `columns.key_risks:`)

| Internal name | Default header | Required? |
|---|---|---|
| `entity_id` | `Audit Entity ID` | **yes** |
| `risk_description` | `Key Risk Description` | **yes** |
| `legacy_l1_raw` | `Level 1 Risk Category` | **yes** (legacy pillar(s)) |
| `risk_id` | `Key Risk ID` | optional (traceability only) |
| `key_risk_rating` | `Inherent Risk Rating` | optional (read but **not used for scoring**) |
| `key_apps_raw` | `KEY PRIMARY & SECONDARY IT APPLICATIONS` | optional |
| `key_tps_raw` | `KEY PRIMARY & SECONDARY THIRD PARTY ENGAGEMENT` | optional |
| `kpa_id` | (KPA / Key Process Area ID) | optional |

### Processing pipeline

1. Read file (line 97-100). Excel or CSV.
2. Strip whitespace from column names.
3. **Rename to internal canonical names** (col_map at lines 105-117). The YAML lets you configure the actual column header in your file (e.g., `Key Risk Description`); the code renames it internally to `risk_description` so downstream code is decoupled from your specific header text.
4. Stringify entity_id.
5. **Multi-value L1 explosion** (line 122-128). Key risks tagged to multiple legacy L1 pillars in one cell are exploded so each row maps to a single L1. Separators: newline, tab, semicolon, pipe.
6. Drop empty/NaN L1 rows after explosion.
7. Strip risk_description text.

Result: one row per (key risk, legacy-L1) pair. A key risk listed under both Operational and Compliance becomes 2 rows.

### Validation (post-ingestion)

`__main__.py:253-264` checks every `legacy_l1` value against the configured pillar list (`pillars_with_rationale + pillars_without_rationale`). Any L1 in the file but not in the YAML is logged as a WARNING listing the offending names — those rows would otherwise be silently ignored by mapping and cross-boundary scoring. (Added 2026-05-02 in commit `1d8bab6`.)

### How key risks get used (5 distinct consumers)

#### Use 1: Multi-mapping keyword scoring (`mapping.py:_resolve_multi_mapping`)

Key risks for an entity, indexed by legacy pillar, are scanned for L2 keywords during multi-mapping resolution. Each keyword hit adds 1 to the L2's score (same as rationale text scanning, but per key risk).

Score thresholds for confidence (across rationale + key risks combined): ≥3 = high, 1-2 = medium, 0 = `Method.NO_EVIDENCE_ALL_CANDIDATES`.

#### Use 2: Cross-boundary signal scanning (`flags.py:flag_cross_boundary_signals`)

Key risk descriptions are also scanned for keywords from L2s the pillar does *not* map to. A key risk under Operational mentioning "GDPR" twice fires a cross-boundary flag on Privacy / Customer Protection L2.

Same `min_hits_per_pillar: 2` threshold as rationale scanning.

#### Use 3: Key inventory aggregation (`ingestion.py:build_key_inventory`)

If `key_apps_col` and `key_tps_col` are configured:
- Splits each cell on newlines/semicolons/commas
- Aggregates **all key app/TP IDs across an entity's key risks** into a per-entity set
- Builds `{app_id: set(KPA IDs where this app is key)}` mapping
- Detects "orphan" key apps (key in a key risk but not in the entity's legacy IT app inventory)

Lands in the `Key_Inventory` sheet (visible since 2026-05-02; formerly hidden) and feeds the HTML report's drill-down view (apps marked "key" get a star/highlight). **Currently NOT used to drive the `app_flag` / `tp_flag` logic** — known gap pending RCO May 15 template.

The Key_Inventory sheet stores per-entity sets as JSON-serialized cells, designed primarily for the HTML report to consume programmatically. A user-friendly per-row display alongside Audit_Review L2 rows is a Phase 2 enhancement.

#### Use 4: `Source - Key Risks` workbook tab (`export.py`)

Written to the workbook with one row per key-risk-to-L1 pair, enriched with which L2s it contributed keywords to. Visible since 2026-05-02 (formerly hidden); reviewers can use it for traceability.

#### Use 5: LLM prompt evidence (`export_llm_prompts.py:253-274`)

For items needing review (Applicability Undetermined / Assumed N/A — Verify), the prompt builder reads the `Source - Key Risks` tab and includes matching key risk descriptions per pillar.

### Filtered / ignored

- L1 names not in `pillar_columns`: kept in the index but no consumer uses it. **Surfaced via startup WARNING since 2026-05-02** so the user can fix the file or YAML.
- `key_risk_rating` column: read but never consumed today. Pass-through to `Source - Key Risks` for reviewer reference.
- Empty/nan `risk_description`: skipped in keyword scanning (`mapping.py:141`, `flags.py:464`).
- Key risks for entities not in the legacy file: still in `key_risks_df` but no `transformed_df` rows exist for those entities, so no consumer reads them.
- No L2 normalization on key risk content — key risks tag to *legacy L1*, not new L2. The mapping happens via keyword scoring against the new L2's keyword list.

### Things worth flagging

1. **`key_risk_rating` is captured but unused.** A Phase 2 evaluation pattern — once individual key risks have actual ratings (post-Optro) and become 1:1 to L2 risks (post-RCO methodology), build a flag when the *aggregate of key risk ratings* outweighs the *L2 inherent risk rating*. Tracked in `project_open_items.md`.
2. **Key risks under Reputational / Country L1** still get scanned for cross-boundary signals — same as their pillar rationale.
3. **Key designation is captured but unused for flag logic.** Tracked in `project_open_items.md` for May 15 RCO template review.
4. **Models tagged to key risks:** the pipeline currently looks for `key_apps` and `key_tps` per key risk but not `key_models`. If your file has a "KEY MODELS" column, it's silently ignored. (Open question — user todo.)

---

## File: `findings_data_*.xlsx`

The IAG findings file. Drives applicability confirmation, control effectiveness display, and control contradiction signals.

### Where it gets loaded

`__main__.py:123-131` finds the most recent file by mtime in `data/input/`. Ingested at `ingestion.py:380-472` via `ingest_findings()`.

### Expected columns (configurable in YAML `columns.findings:`)

| Internal name | Typical header | Required? |
|---|---|---|
| `entity_id` | `Audit Entity ID` | **yes** |
| `l2_risk` | `Risk Dimension Categories` | **yes** |
| `issue_id` | `Issue ID` / `Finding ID` | optional (display) |
| `severity` | `Final Reportable Finding Risk Rating` | optional |
| `status` | `Issue Status` / `Finding Status` | optional |
| `issue_title` | `Finding Name` | optional |
| `remediation_date` | (target close date) | optional |
| `approval_status` | `Finding Approval Status` | optional (filter) |

### Processing pipeline (in order)

1. Read file (line 391-394).
2. Strip column whitespace (line 395).
3. **Rename via column_name_map** (line 397-401). Same pattern as key risks — YAML maps your file's actual column header (e.g., `Finding ID`, `Risk Dimension Categories`) to internal canonical names (`issue_id`, `l2_risk`). Required columns checked at lines 404-409 — raises `ValueError` at startup if your file doesn't contain the columns the YAML points to.
4. Stringify entity_id (line 411).
5. **🚫 FILTER: Approved-only** (line 415-419). Findings with `Finding Approval Status != "Approved"` are dropped.
6. **🚫 FILTER: Blank severity** (line 421-426). Logged as "likely incomplete, shouldn't confirm applicability."
7. **Multi-value L2 explosion** (line 428-432). A finding tagged to multiple L2s in one cell (Excel alt+enter) is exploded into multiple rows.
8. **L2 normalization** (line 434-436) via `normalize_l2_name()`: strips L1 prefix, resolves aliases (from YAML `l2_aliases`), drops names in `l2_unmappable`.
9. **🚨 CAPTURE unmapped findings BEFORE drop** (line 440-450). Findings whose L2 didn't normalize are saved into `unmapped_findings` dict per entity, keeping the raw L2 string.
10. **🚫 FILTER: Drop unmapped from main df** (line 452). Logged with the dropped count and offending raw values.
11. **🚫 FILTER: L2 not in taxonomy** (line 460-475). Defensive — anything that survived normalization but isn't in `L2_TO_L1` is **also captured into `unmapped_findings`** before drop (added 2026-05-02 in commit `1d8bab6`). Both unmappable and defensive-drop findings now surface in the same `Unmapped Findings` column and HTML banner.

Returns `(findings_df, unmapped_findings)` — both consumed downstream.

### How findings get used (6 distinct consumers)

#### Use 1: Confirm applicability — `_create_findings_confirmed_rows` (`mapping.py:38-67`)

For every (entity, L2) with at least one finding in the index, an `ISSUE_CONFIRMED` row is created **before** the crosswalk loop runs. This row:
- Has `confidence: high`
- No rating values (likelihood/impact = None)
- `source_legacy_pillar = "Findings"`, `mapping_type = "findings"`
- Lists up to 5 finding summaries in `key_risk_evidence`

**This is status-agnostic.** Closed findings still produce ISSUE_CONFIRMED rows — a finding existing means the L2 was applicable at some point.

The dedup logic merges ISSUE_CONFIRMED with crosswalk-derived rated rows: rated row keeps the rating, finding evidence appended to `key_risk_evidence`, source becomes `"<pillar> (also: Findings)"`.

#### Use 2: Impact of Issues — `derive_control_effectiveness` (`enrichment.py:150-160`)

For each (entity, L2) row, looks up findings in the index. **Active-status filter applies here** — only `open / in validation / in sustainability` findings appear in the per-row "Audit findings" listing. Closed findings do NOT appear in `Impact of Issues`.

This creates an intentional asymmetry: closed findings confirm applicability (Use 1) but don't appear as current control issues (Use 2). Reviewer sees "Applicable" with "No open items" — both correct.

#### Use 3: Control contradiction flag — `flag_control_contradictions` (`flags.py:77-130`)

For each row, looks up findings on that L2 for that entity. **Active-status filter** (line 97-101). Triggers based on the entity's audit `Last Engagement Rating`:
- **Satisfactory** + any active finding → contradiction flag on every active finding
- **Partially Effective** + active finding with severity **High** or **Critical** → contradiction flag
- **Ineffective** → no flag (already acknowledged weak)

The flag becomes the `control_flag` column → "Control Signals" in Audit_Review.

#### Use 4: `Source - Findings` workbook tab (`export.py:332-337`)

In normal pipeline runs, `_enrich_findings_source()` re-reads the file and adds disposition columns per L2 (showing how each finding mapped, what it confirmed). The enriched DataFrame is written to the `Source - Findings` sheet. Visible since 2026-05-02 (formerly hidden).

A defensive fallback at `export.py:336-337` writes the raw findings_df if `findings_path` is unset; this branch never fires in normal runs.

#### Use 5: LLM prompt evidence (`export_llm_prompts.py:277-296`)

For each (entity, L2) needing review, reads `Source - Findings` and matches by entity + L2 substring. Lists `id, title, severity, status` per matched finding.

#### Use 6: Unmapped findings surface — `Audit_Review` column + HTML banner

The `unmapped_findings` dict is passed to `build_audit_review_df` → produces the `Unmapped Findings` column on every row of that entity. HTML report renders a banner per entity if any unmapped findings exist.

A finding tagged "Reputation" (Not Assessed in the 24-risk taxonomy) still surfaces — just with no L2 row attached. Same now applies to defensive-drop findings (post-`1d8bab6`).

### Filtered / ignored — full list

| Filter | What's dropped | Where | Recovery |
|---|---|---|---|
| `Finding Approval Status ≠ "Approved"` | Drafts, in-review | line 418 | Lost; only `Approved` flows downstream |
| Blank `severity` | Findings with no severity | line 422-426 | Lost; assumes incomplete data |
| Multi-value L2 cell | Exploded, not dropped | line 428-432 | Each L2 becomes its own row |
| Unmappable L2 (per `l2_unmappable` YAML) | Reputation, Compliance, etc. | line 438 | **Preserved** in `unmapped_findings` → workbook + HTML |
| L2 not in `L2_TO_L1` after normalization | Defensive — should never fire | line 460-475 | **Now also preserved** in `unmapped_findings` (post-`1d8bab6`) |
| Status filter for Impact of Issues | Closed/cancelled findings | enrichment.py:151-155 | Still applicable via Use 1; absent from active items |
| Status filter for control contradiction | Closed/cancelled findings | flags.py:97-101 | Same — not flagged as contradiction |

### Things worth flagging

1. **Approval filter is binary.** Statuses other than `"Approved"` (e.g., `"In Review"`, `"Pending Approval"`) are excluded entirely.
2. **The active-status set is hardcoded** in two places: `enrichment.py:153-154` and `flags.py:97-101`. New statuses won't be recognized as active until both are updated. Candidate for promotion to YAML.
3. **Severity filter requires non-blank but doesn't validate against a known list.** A typo like `"Hgih"` survives ingestion and contributes a `ISSUE_CONFIRMED` row without participating correctly in the contradiction flag's High/Critical check (case-insensitive substring on `"high"`).
4. **`remediation_date` is captured but currently used only for display.** Not used for staleness detection or any logic.
5. **`unmapped_findings` is the safety net** — it's why the pipeline can be aggressive about normalization without silently losing data. As of `1d8bab6`, both the unmappable-L2 branch and the defensive L2-not-in-taxonomy branch route through the same surface.

---

## File: `prsa_report_*.xlsx` (display-only raw report)

The PRSA report. Contains AE × Issue × Control rows, used purely as a reference tab — **not** a per-L2 evidence source. L2 attribution for PRSA control problems comes from the separate `prsa_mapping_*.xlsx` mapper output (Tier 3).

> ℹ️ **About this file:** Today the file is a "Frankenstein" stitched manually by Bui from 3 separate Archer reports. A Python script to recreate this report directly from the 3 Archer extracts is on the Phase 2 backlog (`project_open_items.md`). Until then, the tool ingests the pre-built file and adds one tool-computed column.

### Where it gets loaded

`__main__.py:355-365` finds the most recent file by mtime in `data/input/`. Ingested at `ingestion.py:819-886` via `ingest_prsa()`.

### Expected columns (configured in YAML `columns.prsa:`)

Required: `ae_id`, `prsa_id`, `issue_id` (line 840-843 — `ValueError` if missing).

Optional pass-through (~17 columns): `audit_leader`, `core_audit_team`, `audit_engagement_id`, `all_prsas_tagged`, `issue_rating`, `issue_status`, `issue_identified_by`, `issue_identifier`, `issue_breakdown_type`, `issue_owning_bu`, `issue_title`, `issue_description`, `issue_owner`, `control_id_prsa`, `process_title`, `process_owner`, `control_title`.

### Processing pipeline

1. Read file (line 829-832).
2. Strip column whitespace.
3. Stringify `ae_id` and `prsa_id` (lines 845-846).
4. **Build PRSA → AE cross-reference** (lines 848-863): walks the `All PRSAs Tagged to AE` column, builds `{prsa_id: set(ae_ids)}`. The `Other AEs With This PRSA` column added at line 872 lists every other AE that shares this PRSA — surfacing cross-AE control-failure visibility for the reviewer.
5. Log shared-across-AEs PRSAs at INFO (lines 880-884).

### How PRSA raw gets used (1 consumer)

#### Use 1: `Source - PRSA Issues` tab (`export.py:353-354`)

Written verbatim to the workbook with the added `Other AEs With This PRSA` column. Visible since 2026-05-02. Reviewers can browse the full PRSA report and see cross-AE links.

**That's the only use.** The L2 attribution for PRSA control problems comes from the separate `prsa_mapping_*.xlsx` mapper output (Tier 3). Why: the auditor hasn't completed an explicit per-L2 mapping for these issues, so the tool will not flag PRSA items as Applicable or include them in Impact of Issues based on the mapper's automated suggestions alone. The mapper's output is an intermediate artifact reviewed and refined separately.

### Filtered / ignored

- No L2 normalization (no L2 column in PRSA reports).
- No status / severity / approval filters at ingestion.
- All PRSA control rows kept regardless of status.

### Things worth flagging

1. **The `Other AEs With This PRSA` column is tool-computed**, not from source data. Documented in the Methodology tab as of commit `7d2d083` so reviewers know it was added during ingestion.
2. **No deduplication if the file has multiple rows per (PRSA, AE).** PRSA reports often repeat AEs across rows because each issue/control gets its own row. The cross-AE logic correctly dedupes by `seen_aes` (line 852), but the output DataFrame retains all rows.
3. **The raw PRSA file has many columns** — all preserved in the source tab. Intentional; user wants full visibility.

---

## File: `bm_activities_*.xlsx` (display-only with date filter)

Business Monitoring Activities. Display-only reference tab — no L2 attribution.

### Where it gets loaded

`__main__.py:370-380` finds the most recent file by mtime in `data/input/`. Ingested at `ingestion.py:889-939` via `ingest_bma()`.

### Expected columns (configured in YAML `columns.bma:`)

Required: `instance_id`, `planned_completion_date` (line 911-914).

Optional pass-through: `entity_id`, `activity_id`, `activity_title`, `activity_occurred`, `monitoring_cases`, `impact_result`, `action_needed`, `summary_of_results`, `impact_description`.

### Processing pipeline

1. Read file (line 899-902).
2. Strip column whitespace.
3. **Warn about blank entity IDs** (lines 916-922) — kept for completeness but flagged. Blank entity IDs are a known department-wide data-quality issue, so the warning is the right level — surfacing without excluding.
4. **🚫 FILTER: Date cutoff** (lines 924-934). Rows with `Planned Instance Completion Date` before the configured cutoff (`columns.bma.min_completion_date` in YAML, default `2025-07-01`) are dropped. Rows with NaT/missing dates are kept.

### How BMA gets used (1 consumer)

#### Use 1: `Source - BM Activities` tab (`export.py:355-356`)

Written verbatim to the workbook. Visible since 2026-05-02.

**That's the only use today, and that's the final state.** Earlier roadmap planned a Phase B BMA mapper to attribute BMA cases to L2 risks. **CANCELLED 2026-05-02** per user: there's no reliable signal in BMA cases to programmatically determine which L2 they should map to; the audit team will handle that judgment manually. So BMA cases will not feed `Impact of Issues` at the L2 level — they remain a reviewer-visible reference only.

### Filtered / ignored

- No L2 normalization (no L2 column).
- Pre-cutoff BMA activities silently dropped.
- Blank entity ID rows kept with WARNING.
- No status / activity-occurred filters.

### Things worth flagging

1. **The `2025-07-01` cutoff is YAML-configurable** at `columns.bma.min_completion_date`. Roll forward by editing YAML — no code change needed.
2. **Blank entity-ID BMA rows are a department-wide problem.** Tool surfaces them via WARNING but does not drop. Right call — preserves data fidelity for the reviewer to investigate.
3. **No L2 attribution by design.** Don't expect to see BMA cases in Impact of Issues per L2 row.

---

## File: `gra_raps_*.xlsx` (display-only with light validation)

Regulatory Action Plans (regulatory findings). Same display-only pattern as PRSA — L2 attribution comes from the Tier 3 mapper output.

### Where it gets loaded

`__main__.py:385-395` finds the most recent file by mtime in `data/input/`. Ingested at `ingestion.py:942-985` via `ingest_gra_raps()`.

### Expected columns (configured in YAML `columns.gra_raps:`)

Required: `rap_id`, `rap_header` (line 962-965).

Optional pass-through: `entity_id`, `entity_name`, `entity_status`, `core_audit_team`, `audit_leader`, `pga`, `gra_raps`, `audit_entity_gra_raps`, `rap_details`, `bu_corrective_action_due_date`, `rap_status`, `related_exams_and_findings`.

### Processing pipeline

1. Read file (line 950-954).
2. Strip column whitespace.
3. **🚫 FILTER: Drop rows with blank `rap_id`** (lines 967-972). These are entity-level header rows with no actual RAP — filtered out. Logged as INFO with count.
4. **Warn about blank entity IDs** (lines 974-980) — kept for completeness but flagged.

### How GRA RAPs gets used (1 consumer)

#### Use 1: `Source - GRA RAPs` tab (`export.py:357-358`)

Written verbatim to the workbook. Visible since 2026-05-02.

**That's the only use.** L2 attribution for RAPs comes from the separate `rap_mapping_*.xlsx` mapper output (Tier 3) — the auditor reviews/refines those mappings before they feed Impact of Issues.

### Filtered / ignored

- No L2 normalization (no L2 column in raw RAPs).
- Rows with blank `rap_id` dropped (entity-level header rows).
- Blank entity ID rows kept with WARNING.
- No status / due-date filters.
- The "Audit Entity Status" column (`Inactive` / `Active`) is captured but **not filtered on** — inactive entities' RAPs still flow through.

### Things worth flagging

1. **Inactive entities in GRA RAPs** are not currently filtered. Tracked in `project_open_items.md` for methodology follow-up — should inactive entities' RAPs be excluded?
2. **Same display-only pattern as PRSA.** The raw file just provides a reference tab; the L2 attribution lives in the mapper output, which the auditor reviews separately.

---

## Why PRSA / BMA / GRA RAPs are display-only

Each of these has a different reason, but the underlying principle is the same: **the tool will not programmatically attribute these items to L2s without an auditor-reviewed mapping.** The user's explicit guidance (2026-05-02):

> "The mappers I have for each of these suggest L2s but that doesn't mean (1) it is correct, (2) that auditors agree with this. Because of (1) and (2) I don't think it's appropriate to flag something as applicable or list it as part of impact of issues."

Concretely:
- **PRSA & GRA RAPs:** mappers exist (Tier 3) and produce automated L2 attributions. Those attributions feed Impact of Issues only after the auditor reviews and refines them. The raw report file has no L2 attribution at all — it's a reviewer reference, not an evidence source.
- **BMA:** no mapper exists or will be built (cancelled 2026-05-02). BMA cases stay in their source tab for reviewer reference only.

This is why the Tier 1 vs Tier 2 split matters: IAG findings are *already* L2-attributed at source (they have a `Risk Dimension Categories` column), so they can flow directly into per-L2 Impact of Issues. The Tier 2 raw reports have no source-side L2 column.

## Removed: `enterprise_findings_*.xlsx`

The pipeline previously had an `ingest_enterprise_findings` code path that read a separate `enterprise_findings_*.xlsx` file pattern and routed those items into `Impact of Issues` per L2. **Removed in commit `7d2d083`** per user direction: "I don't currently use these. Originally I thought they existed but they're really just the PRSA. There's also nothing really called enterprise findings."

Net 102 lines deleted across `ingestion.py`, `__main__.py`, `enrichment.py`, `config.py`, and `taxonomy_config.yaml`. No behavior change in the workbook — the code path was dormant in practice.

---

---

## Tier 3: Mapper Outputs (`ore_mapping`, `prsa_mapping`, `rap_mapping`)

The three mapper outputs share a near-identical shape: each is produced by a separate spaCy-based mapper script (`ore_mapper.py`, `prsa_mapper.py`, `rap_mapper.py`), reads the same "All Mappings" sheet structure, and feeds Impact of Issues per L2 row.

### How these files are produced

These are **derived artifacts**, not raw inputs. Each mapper script:
1. Loads its raw input (OREs / PRSA issues / RAPs) and `data/input/L2_Risk_Taxonomy.xlsx`.
2. Builds reference vectors per L2 from the L2 description text using spaCy `en_core_web_md` (300-dim word vectors). **L3/L4 columns from the taxonomy file, when present, are folded into the per-L2 reference text** — the L3-based bucketing also gives Fraud-at-L3-grain L2s their own vectors. Code: `ore_mapper.py:166-249`, `prsa_mapper.py:182-...`, `rap_mapper.py:150-...`.
3. Computes cosine similarity between each item's text and each L2 vector.
4. Bands the scores: **Strong / Suggested Match / Needs Review / Weak / No Match**.
5. Writes a 5-sheet workbook (`All Mappings`, `Needs Review`, `Summary`, `L2 Distribution`, `Raw Scores`) into `data/output/`.

The mappers are **run separately** before the main transformer pipeline. The user runs them manually (or via `python refresh.py`), reviews the `Needs Review` sheet, updates the `Mapping Status` column where needed, and the main pipeline ingests the most-recent mapper output. The main pipeline reads only from `data/output/` (per commit `30c7f11`).

### Shared shape: ingestion pipeline

For all three (`ingest_ore_mappings`, `ingest_prsa_mappings`, `ingest_rap_mappings`):

1. Read sheet `"All Mappings"`.
2. Strip column whitespace.
3. Required-column check — raises `ValueError` if source-specific required columns are missing.
4. **🚫 FILTER: Mapping Status** — keeps rows whose band is in the configured filter (default `["Suggested Match", "Needs Review"]` per YAML `ore_confidence_filter` / `prsa_confidence_filter` / `rap_confidence_filter`). Strong / Weak / No Match are filtered out.
5. **Multi-value L2 explosion** — splits `Mapped L2s` on `"; "`, explodes one row per L2.
6. Strip whitespace, drop empties.
7. Rename to internal canonical names (`entity_id`, item ID).
8. **L2 normalization** via `normalize_l2_name()`. Unmappable L2 names are **captured into `unmapped_mapper_items` BEFORE drop** (per commit `db4dbcb`) so they surface in the Audit_Review `Unmapped Findings` column alongside unmapped IAG findings.
9. **Index build** — `{entity_id: {l2_risk: [list of item dicts]}}`.
10. Returns `(df, unmapped_dict)` tuple. `__main__.py` merges the three unmapped dicts into a single `unmapped_mapper_items` dict for export.

The index is consumed downstream by `derive_control_effectiveness` (`enrichment.py`). Each (entity, L2) row in `transformed_df` looks up its index, formats the matching items with confidence-band annotations, and appends them to `Impact of Issues`.

### Per-source detail

#### `ore_mapping_*.xlsx` — Operational Risk Events

**Required columns:** `Event ID`, `Audit Entity ID`, `Mapping Status`, `Mapped L2s`.

**Per-row payload** (`build_ore_index:_ore_from_row`):
- `Event Title`, `Event Description` (truncated to 200 chars; full text on truncation-test backlog)
- `Final Event Classification` (Class A/B/C) — optional, only included if present
- `Event Status` (lifecycle: Open, Closed, Canceled, etc.) — optional
- `Mapping Status` — preserved as `mapping_status` (per `db4dbcb`) so the per-row display can annotate `(Needs Review)` inline.

**Closed events filtered out of Impact of Issues** entirely (per `db4dbcb`) — they still appear in `Source - OREs` for full traceability. Closed-status set is YAML-configurable at `ore_closed_statuses`.

#### `prsa_mapping_*.xlsx` — PRSA control problems

**Required columns:** `Issue ID`, `AE ID`, `Mapping Status`, `Mapped L2s`.

**Per-row payload** (`build_prsa_mapping_index:_prsa_from_row`):
- `Issue Title`, `Issue Description` (truncated to 200 chars; backlog item)
- `Issue Rating`, `Issue Status` — optional, only included if non-empty
- `Mapping Status` — preserved as `mapping_status`.

**Closed PRSA issues filtered out of Impact of Issues** via `prsa_closed_statuses` YAML list. Active-status definition is also YAML-configurable.

#### `rap_mapping_*.xlsx` — Regulatory Action Plans (GRA RAPs)

**Required columns:** `RAP ID`, `Audit Entity ID`, `Mapping Status`, `Mapped L2s`.

**Per-row payload** (`build_rap_mapping_index:_rap_from_row`):
- `RAP Header`, `RAP Details` (truncated to 200 chars)
- `RAP Status`, `Related Exams and Findings` — optional
- `Mapping Status` — preserved as `mapping_status`.

**No closed-status filter today.** RAPs may not have an equivalent "closed" lifecycle worth filtering on — tracked in `project_open_items.md` for confirmation against real data.

### Source tab content

All three Source tabs show the items + mapping attribution columns. Different mechanisms, same outcome:

- **Source - OREs** — written from the ingested `ore_df` directly. The mapper output already carries event context (Event Title, Description, Classification, Status) plus mapping columns (Mapping Status, Match Confidence, Mapped L2s, Mapped L2 Count, Mapped L2 Definitions). The exploded per-row normalized L2 is shown as a `Canonical L2` column (renamed from `l2_risk` per commit `3707c03`) to avoid colliding with the original ;-joined `Mapped L2s`.
- **Source - PRSA Issues** — raw report is the source structure (richer context than the mapper output: Process Title, Control Title, Issue Owner, etc.). `__main__.py:408-421` reads the mapper's `All Mappings` sheet, slims to `[Issue ID, Mapped L2s, Mapping Status]`, dedups by Issue ID, merges onto `prsa_df`. Plus the tool-computed `Other AEs With This PRSA` column.
- **Source - GRA RAPs** — same merge pattern as PRSA at `__main__.py:423-436`, keyed on RAP ID.

### Filtered / ignored

| Filter | Where | What's dropped |
|---|---|---|
| Mapping Status not in confidence_filter | ingestion | Rows with bands other than configured (default Suggested Match + Needs Review). Strong, Weak, No Match always dropped. |
| Empty L2 cell after explosion | ingestion | Rows where `Mapped L2s` was blank or whitespace |
| Unmappable L2 name | ingestion | **Captured to `unmapped_mapper_items`** — surfaces in workbook + HTML alongside unmapped findings |
| Closed PRSA issues | enrichment.py | Excluded from Impact of Issues; YAML-configurable via `prsa_closed_statuses` |
| Closed OREs | enrichment.py | Excluded from Impact of Issues; YAML-configurable via `ore_closed_statuses` |

### Things worth flagging

1. **Mapper outputs are produced manually.** Running the main pipeline doesn't run the mappers. Use `python refresh.py` to refresh everything in one shot.
2. **L3/L4 enrichment is implemented** but only fires when the L2 taxonomy file has those columns (the dummy fixture doesn't). Validate against real data by checking the mapper log line `Computing vectors for {N} unique L2s (aggregated from {M} rows)...` — `M > N` confirms aggregation.
3. **`Needs Review` items now flow through** to Impact of Issues with `(Needs Review)` annotation inline. Reviewer adjudicates uncertainty without having to open the mapper output workbook.
4. **`mapping_status` is preserved on all three index dicts** as of `db4dbcb`. ORE was the laggard before that.
5. **Multi-L2 explosion uses `"; "` separator only.** No validation enforces it; if a mapper run produces a different separator, the explosion silently fails.

---

---

## Tier 4: Override Files (`llm_overrides`, `rco_overrides`)

Two override files with very different roles. Both feed applicability decisions back into the pipeline from external review work. **Both are optional** — pipeline runs without either.

| File | Source of decisions | What it overrides | Where it's consumed |
|---|---|---|---|
| `llm_overrides_*.{xlsx,csv}` | LLM (e.g., ChatGPT) responses to prompts generated by `export_llm_prompts.py` | Per-row keyword-scoring decisions for `multi`-type pillars | `mapping.py:_resolve_multi_mapping` — replaces keyword evidence with LLM determination |
| `rco_overrides_*.{xlsx,csv}` | Risk Category Owners reviewing the `Risk_Owner_Review` tab | Per-row applicability status + rating | **`review_builders.py:build_risk_owner_review_df` ONLY** — sibling-context overlay. Does NOT reach `Audit_Review` or HTML (§5.16) |

---

## File: `llm_overrides_*.{xlsx,csv}`

The LLM-feedback loop closer. The transformer's review queue (entities + L2s the keyword scoring couldn't decide on) gets exported as prompts via `export_llm_prompts.py`. The user pastes these prompts into ChatGPT, saves the LLM's CSV response, and the next pipeline run picks up `llm_overrides_*.xlsx` from `data/input/` and applies the decisions.

### The structured workflow (post-`ab1a4a3`)

Output of `export_llm_prompts.py` is now organized per batch:

```
data/output/llm_prompts/
  batch_001/
    manifest.json   ← entities, items_per_entity, expected_items triples
    prompt.txt      ← the LLM prompt to paste into ChatGPT
    response.csv    ← header-only template; user pastes ChatGPT's CSV here
  batch_002/
    ...
```

**`manifest.json`** captures everything the LLM is being asked to decide:
- `batch_number`, `generated_at`, `source_workbook`
- `entities` (list of audit entity IDs in this batch)
- `items_per_entity` (e.g., `{"AE-3": 9, "AE-4": 5}`) for per-entity count validation
- `expected_items` (list of `{entity_id, source_legacy_pillar, classified_l2}` triples) for exact coverage validation
- `expected_response_columns` and `valid_determination_values` for schema declaration

**`response.csv`** starts as a header-only template. User pastes ChatGPT's output below the header.

**`consolidate_llm_responses.py`** is run after responses are pasted in. It:
1. Walks `batch_NNN/` folders
2. Validates each `response.csv`:
   - Header matches expected columns
   - Each data row has correct column count
   - `determination` is in `{applicable, not_applicable}`
   - Required fields are non-empty
3. Cross-checks against the manifest:
   - Entity-level: missing or extra entities vs manifest
   - Per-entity counts: each entity's row count vs `items_per_entity`
   - Exact triples: missing or extra `(entity, pillar, L2)` triples vs `expected_items`
4. Reports failures with line numbers and triple samples
5. Merges all valid rows into `data/input/llm_overrides_<timestamp>.csv`

The merged file is the input to the next pipeline run. Flags: `--strict` (exit non-zero on any error), `--dry-run` (validate only, don't write merged file).

`refresh.py --consolidate-llm` runs the consolidator before the main pipeline.

### Where it gets loaded

`__main__.py:113-122` finds the most recent `llm_overrides*.{xlsx,csv}` by mtime in `data/input/`. Ingested at `ingestion.py:301-377` via `load_overrides()`.

### Expected columns (consolidator output schema)

| Column | Required? | Purpose |
|---|---|---|
| `entity_id` | yes | Audit entity ID |
| `source_legacy_pillar` | yes | The legacy pillar that triggered the row in the review queue (base name; the prompt strips `(also: ...)` annotations before showing the LLM) |
| `classified_l2` | yes | The L2 the LLM is making a determination about |
| `determination` | yes | `applicable` or `not_applicable` (case-insensitive; anything else → row skipped per `04f53b3`) |
| `reasoning` | optional | LLM's explanation; surfaced in Decision Basis prose |

Legacy two-column format (`entity_id, source_legacy_pillar, classified_l2, llm_confidence`) still supported — treated as `applicable` with the given confidence.

### Processing pipeline (ingestion)

1. Read file (line 313-316).
2. Strip column whitespace, stringify identifiers (lines 318-321).
3. Detect format via column presence: `has_determination`, `has_reasoning`.
4. Per row:
   - **L2 normalization** (line 335). Unmappable L2 → row skipped + WARNING.
   - **Determination validation** (lines 344-351). Anything other than `applicable` / `not_applicable` → row skipped + WARNING.
   - **Confidence handling**: new format always `high`; legacy reads `llm_confidence`, coerces invalid values to `high`.
   - **Reasoning capture** (lines 360-365).
5. Build dict: `{(entity_id, source_legacy_pillar, normalized_l2): {determination, confidence, reasoning}}`.

Returns dict, not DataFrame.

### How LLM overrides get used (1 consumer)

#### `mapping.py:_resolve_multi_mapping` (post-`ab1a4a3`)

Inside the multi-target resolution loop, the order is:
1. **Keyword scanning runs first** — captures `labeled_evidence` (rationale + key risk hits) for this candidate L2. This now happens regardless of whether an override fires.
2. **Override check** — `(entity_id, legacy_pillar, target["l2"])` lookup against the overrides dict.
3. **If override fires:**
   - Build evidence list: `["AI review: <reasoning>"]` + `labeled_evidence[:8]`
   - Method: `LLM_OVERRIDE` (applicable) or `LLM_CONFIRMED_NA` (not_applicable)
   - For `LLM_CONFIRMED_NA`: `clear_ratings=True` at `mapping.py:446` — likelihood and impacts blanked
   - `continue` — skip the keyword-scoring confidence band logic
4. **If no override:** keyword score determines confidence band (`high`/`medium`/`low`).

This means **LLM_OVERRIDE rows now carry both AI reasoning AND keyword evidence** — useful especially when LLM disagrees with keywords (the keyword hits are still visible alongside the AI's contrary determination).

### Filtered / ignored

| Condition | Result |
|---|---|
| L2 doesn't normalize to canonical taxonomy | Row skipped + WARNING |
| `determination` not in `{applicable, not_applicable}` | Row skipped + WARNING (post-`04f53b3`) |
| `llm_confidence` invalid (legacy format) | Coerced to `high`, row kept |
| Pillar not in crosswalk | Override loaded but never matched (loop doesn't iterate); silent dead-letter |
| Override key matches a `direct`-type pillar | Loaded but unused — `_resolve_multi_mapping` only handles `multi` |
| Override key matches a `multi` pillar but the L2 isn't a target of that pillar | Loaded but unused — pillar's targets list doesn't include this L2 |

### Things worth flagging

1. **Override keys that don't match a real (pillar, L2) pair are silent dead-letters.** If you submit an override for `AE-2 / Compliance / Privacy` but Compliance doesn't map to Privacy in the crosswalk, the override is loaded with no error and never fires. Counter at run end (`Loaded N overrides`) doesn't distinguish between "loaded and used" vs "loaded and never matched." A future cleanup could log dead-letters at end of pipeline.
2. **Dedup can drop LLM_OVERRIDE evidence.** If an LLM_OVERRIDE row for `(Operational, Conduct)` collides with an EVIDENCE_MATCH row for `(Compliance, Conduct)` and the EVIDENCE_MATCH wins on rating, the LLM_OVERRIDE's evidence list is replaced wholesale by the EVIDENCE_MATCH's. The dedup is rating-driven, not authority-driven. Worth considering whether LLM_OVERRIDE should always win in dedup.
3. **CSV is the response format today.** Manual paste from ChatGPT web UI → CSV is more forgiving than JSON. Migration to JSON saved to memory; triggered when API access lands.
4. **Reasoning is layered with keyword evidence in Decision Basis.** Per `ab1a4a3`, the `sub_risk_evidence` list on an LLM_OVERRIDE row contains both `"AI review: <reasoning>"` and `"rationale: <kws>"` / `"key risk <id>: <kws>"` when both signals are present. Reviewers see the LLM's call AND the keyword backing.

---

## File: `rco_overrides_*.{xlsx,csv}`

Risk Category Owner overrides. RCOs review the `Risk_Owner_Review` tab (a per-RCO view of all entities × L2s within their categories) and submit overrides for entities they have stronger views on.

### Where it gets loaded

`__main__.py:347-355` finds the most recent file by mtime. Pattern: `rco_overrides_*.{xlsx,csv}`. Ingested at `ingestion.py:953-999` via `ingest_rco_overrides()`.

### Expected columns

| Column | Required? | Purpose |
|---|---|---|
| `entity_id` | yes | Audit entity |
| `l2_risk` | yes | The L2 being overridden |
| `rco_status` | yes | One of `Confirmed Applicable`, `Confirmed Not Applicable`, `Escalate` (anything else → row skipped) |
| `rco_rating` | optional | RCO's rating override (only meaningful for `Confirmed Applicable`) |
| `rco_name` | optional | Who submitted (audit trail) |
| `rco_comment` | optional | Justification |

### Processing pipeline (ingestion)

1. Read file. Strip column whitespace. Stringify entity_id.
2. Per row:
   - **L2 normalization**. Unmappable → WARNING + skip.
   - **Status validation**. Must be one of the three valid values; else WARNING + skip.
   - Build entry: `{status, rating, source: "rco_override", rco_name, comment}`.
3. Build dict: `{(entity_id, normalized_l2): {...}}`.

Returns dict.

### How RCO overrides get used (1 consumer, narrow scope)

#### `review_builders.py:build_risk_owner_review_df`

Two places (lines 829-836 and 854-860):

1. **Entity × L2 lookup overlay** (lines 829-836). The Risk Owner Review's `entity_l2_lookup` dict is built from `transformed_df`, then RCO overrides clobber any matching entries. Drives sibling context shown next to each row in the Risk Owner Review.

2. **Peer-rating Counter overlay** (lines 854-860). Used for the within-business-line rating distribution. Only `Confirmed Applicable` overrides contribute to peer ratings.

**That's the entire scope.** RCO overrides do NOT:
- Change the row's `Status` or `Proposed Rating` in `Audit_Review`
- Appear in the HTML report
- Propagate to `Side_by_Side`
- Affect `Impact of Issues`

Per §5.16 (tabled audit item from 2026-05-01), this asymmetry is intentional today since RCOs aren't actively producing override files. If they start, the propagation policy needs revisiting.

### Filtered / ignored

| Condition | Result |
|---|---|
| L2 doesn't normalize | Row skipped + WARNING |
| `rco_status` not in `{Confirmed Applicable, Confirmed Not Applicable, Escalate}` | Row skipped + WARNING |
| Empty `rco_rating` | Stored as `None` |
| Empty `rco_name` / `rco_comment` | Stored as empty string |

### Things worth flagging

1. **Effects only land in Risk_Owner_Review.** A non-trivial limitation. If an RCO submits "Confirmed Not Applicable" for an entity × L2, the Audit_Review tab still shows that L2 as Applicable per the tool's keyword scoring. Audit teams reading Audit_Review wouldn't know the RCO has spoken.
2. **No "Escalate" handling beyond status display.** When `rco_status == "Escalate"`, the row appears in Risk_Owner_Review with that label; no escalation workflow / notification / queue is generated.
3. **No source tab.** The raw `rco_overrides_*.xlsx` doesn't get written anywhere in the workbook. To audit what the RCO submitted, open the input file directly.
4. **Phase 2: rule-based RCO layer.** The current per-row override is one shape. The May 15 RCO template is expected to capture rule-shaped applicability ("all entities in BU 'Card Services' → Conduct is Applicable"). Rule infrastructure would build on the per-row dict; saved to `project_open_items.md` for post-template work.

---

## Summary table for Tier 4

| File | Required columns | Filters | Consumer | Effect on Audit_Review? |
|---|---|---|---|---|
| `llm_overrides_*.{xlsx,csv}` | entity_id, source_legacy_pillar, classified_l2 (+ determination OR llm_confidence) | L2 normalization; determination validation; consolidator pre-validates per-entity counts and exact triple coverage | `mapping.py:_resolve_multi_mapping` (pre-empts keyword scoring; layers AI reasoning + keyword evidence) | **Yes** — produces `LLM_OVERRIDE` or `LLM_CONFIRMED_NA` rows that flow into Audit_Review with combined reasoning + keyword evidence |
| `rco_overrides_*.{xlsx,csv}` | entity_id, l2_risk, rco_status | L2 normalization; status validation | `review_builders.py:build_risk_owner_review_df` ONLY (sibling context + peer ratings) | **No** — visible only in Risk_Owner_Review tab. §5.16 tabled item. |

---

---

## Tier 5: `L2_Risk_Taxonomy.xlsx`

The canonical source-of-truth for L2 names + definitions, plus L1/L3/L4 nesting context. **Read by four consumers** — three mapper scripts and the LLM prompt builder. NOT consumed by the main pipeline directly; the main pipeline uses `taxonomy_config.yaml` for L2 names + L1 mappings (and the YAML should match this file).

### Where it gets loaded

| Consumer | Function | Purpose |
|---|---|---|
| `ore_mapper.py:94-110` | `load_l2_definitions()` | Build reference vectors for spaCy similarity |
| `prsa_mapper.py:91-...` | `load_l2_definitions()` | Same |
| `rap_mapper.py:80-...` | `load_l2_definitions()` | Same |
| `export_llm_prompts.py:65-114` | `load_l2_definitions()` | Populate `Definition:` line per L2 in LLM prompts |
| `__main__.py:218-256` (NEW per `55e251d`) | inline alignment validator + source tab passthrough | Validate YAML alignment + write `Source - L2 Taxonomy` tab |

### Expected columns

Required by all consumers:
- **L2** — canonical L2 name
- **L2 Definition** — text definition

Folded into the per-L2 reference vector when present (children only — see below for why):
- **L3**, **L3 Definition** — sub-category
- **L4**, **L4 Definition** — even more granular

Read by other consumers but NOT folded into reference vectors:
- **L1**, **L1 Definition** — parent category. Excluded from reference vector text intentionally — folding the parent's broader concepts in would dilute the L2's vector rather than sharpen it. Children (L3/L4) narrow the L2's scope; the parent (L1) widens it.

The dummy fixture in this repo has only L1, L2, L2 Definition. Real enterprise file has all eight (L1/L1 Definition through L4/L4 Definition).

### Merged cells — handled by ffill (post-`55e251d`)

Real enterprise files commonly merge L1/L2/L3 cells across multiple rows (one L2 cell merged across all its L3 rows). Pandas reads continuation rows as NaN. **Previously** the four consumers split:
- `export_llm_prompts.py` did `ffill()` (correct)
- The three mappers did NOT (continuation rows were skipped, dropping their L3/L4 definitions)

**As of `55e251d`, all four consumers ffill L1/L2/L3** in `load_l2_definitions()`. The bucketing loop in `build_reference_vectors` now sees populated values on every row and folds L3/L4 definitions correctly.

### How it gets used (two distinct consumption patterns)

#### Pattern 1: Mapper reference vector construction

`ore_mapper.py:166-256`, `prsa_mapper.py:182-...`, `rap_mapper.py:150-...` all share the same logic:

1. **Read with ffill** (post-`55e251d`).
2. **Iterate rows.** For each row:
   - Read L2 name and L3 name.
   - **L3-based bucketing** — if L3 normalizes to an evaluated L2 (e.g., `Internal Fraud`), L3 wins as the bucket; otherwise falls back to L2. Fraud-at-L3-grain L2s get their own vectors.
   - Initialize bucket text with bucket name + L2 Definition.
   - Fold CHILD-level text via `sub_cols`:
     ```python
     sub_cols = [c for c in ["L3", "L3 Definition", "L4", "L4 Definition"]
                 if c in l2_df.columns]
     ```
     L1 and L1 Definition are NOT included — L1 is the parent and would dilute the L2's vector with broader/more-generic concepts. L3 and L4 are narrower than L2 and sharpen the match.
3. **Compute vectors** — concatenated text per bucket → `nlp(text).vector`.

The result: each bucket's reference vector is the spaCy embedding of (bucket name + L2 Definition + L3 + L3 Definition + L4 + L4 Definition) for every row that matches.

#### Pattern 2: LLM prompt definition lookup

`export_llm_prompts.py:65-114` builds `{l2_name: {"l1": ..., "definition": ...}}` keyed by the L2 name as it appears in `Audit_Review.New L2`. For Fraud L3 sub-types, it pulls the L3 Definition instead of the L2 Definition. Used to write the `Definition:` line in each prompt block.

### YAML alignment validator (post-`55e251d`)

`__main__.py:218-256` runs at pipeline start (only if the file is present). It:
1. Reads `L2_Risk_Taxonomy.xlsx` with `ffill()` on L1/L2/L3.
2. Collects every L2 name from the L2 column AND every L3 name from the L3 column (since L3-grain L2s use L3 as their canonical name).
3. Compares against `L2_TO_L1.keys()` (the YAML `new_taxonomy:` definition).
4. Logs a WARNING if any YAML L2 is missing from the file.

Soft warning, not hard fail — if the file is absent (e.g., dummy data run), validation is skipped silently. If the file is present but malformed (read error), warns and continues without the validator running.

### `Source - L2 Taxonomy` tab (post-`55e251d`)

The taxonomy DataFrame (post-ffill) is now written to a visible workbook tab. Reviewers can read L1/L2/L3/L4 definitions directly from inside the workbook without opening the input file separately.

### Filtered / ignored

| Condition | Mappers | Prompt builder | Source tab |
|---|---|---|---|
| L2 cell blank/NaN (post-ffill) | Row skipped | Row skipped silently | Written verbatim (post-ffill, so no NaN unless full row blank) |
| L3 normalizes to evaluated L2 | L3 wins as bucket | Captured under L3 name | Written verbatim |
| L4 / L4 Definition columns absent | sub_cols list excludes them | Not looked up | Written verbatim if present |
| File absent | Mapper run fails (mappers require it) | `l2_defs` falls back to YAML names with empty definitions | Source tab not written |

### Things worth flagging

1. **YAML validator won't catch all drift.** It checks that YAML L2s appear in the file. It does NOT check the reverse (file L2s not in YAML — could be intentional non-evaluated rows) or definition text drift (YAML doesn't have definitions). Reasonable scope today; expand if drift becomes a real problem.

2. **No validation of L1 alignment.** L1 names in `new_taxonomy` should match L1 names in the file. Not currently checked.

3. **Real file structure assumption.** The mapper bucketing logic assumes: one L2 per merged-cell block, multiple L3 rows per L2 (with L4 sometimes nested below L3). Other structures (e.g., flat one-row-per-L2-no-L3-merging) work too — the ffill is a no-op when there's nothing to fill.

4. **Source - L2 Taxonomy is verbose for real data.** May have hundreds of rows post-ffill. Visible by default since 2026-05-02 visibility change; user may want to hide if it's noisy.

---

## Summary table for Tier 5

| Consumer | Reads | Uses for | Handles merged cells? |
|---|---|---|---|
| `ore_mapper.py` | L2/L2 Definition (bucket); L3/L3 Definition + L4/L4 Definition (folded into vector). L1/L1 Definition NOT folded. | spaCy reference vector per L2 bucket | **Yes** (post-`55e251d`) — `ffill()` on L1/L2/L3 |
| `prsa_mapper.py` | Same | Same | Same — `ffill()` |
| `rap_mapper.py` | Same | Same | Same — `ffill()` |
| `export_llm_prompts.py` | L1, L2, L3, L2 Definition, L3 Definition | `Definition:` line per L2 in prompts | Always did `ffill()` |
| `__main__.py` (alignment validator) | L2 column + L3 column | WARN if any YAML L2 missing | **Yes** — `ffill()` |
| `Source - L2 Taxonomy` tab | All columns | Reviewer reference | Written post-ffill |

---

## Tier completion status

- [x] **Tier 1**: legacy_risk_data, key_risks (formerly sub_risk_descriptions), findings_data
- [x] **Tier 2**: prsa_report, bm_activities, gra_raps (enterprise_findings removed — never used)
- [x] **Tier 3**: ore_mapping, prsa_mapping, rap_mapping (mapper outputs)
- [x] **Tier 4**: llm_overrides (with batch-folder workflow + 3-layer consolidator validation), rco_overrides
- [x] **Tier 5**: L2_Risk_Taxonomy.xlsx (ffill fix in mappers, L1 enrichment, YAML alignment validator, source tab)

**All tiers complete.**
