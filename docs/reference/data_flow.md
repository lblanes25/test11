# Data Flow Reference — Risk Taxonomy Transformer

How each input file flows through the pipeline. For every column or data type: where it's read, what transformations apply, where it ultimately lands, and what gets filtered or ignored.

> **Precedence (2026-05-17):** detail-of-record for code-level tracing. Where this diverges from `Methodology.md` (governance source of truth), **Methodology.md governs.** NLP mapper banding changed 2026-05-17 (Family A — all above-floor items now "Needs Review"; Strong/Suggested Match/Weak no longer emitted); references to those bands below are historical. Re-verify `file:line` cites against `HEAD` — newer sections cite function names instead of line numbers for exactly this reason.

> **Last full verification: 2026-06-12.** Relocated from `config/` to `docs/reference/` (non-governed developer reference). Sections added in this pass: IRM OREs (raw export + consolidation + bridge), PG team inputs (FND_ID route), Optro export overrides, Upstream Tagging Gaps / orphan sidecars, inventory files. The former companion `methodology_reference.md` was retired to `archive/superseded_docs/` (never referenced in practice); reviewer-facing per-source rules live in `risk_taxonomy_transformer/methodology.yaml`, which renders into the workbook and HTML on every run.

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
- **N/A** (`raw_str in NA_STRINGS` after `convert_risk_rating` returned None): emits a `source_not_applicable` row for every candidate L2 in that pillar's mapping. `likelihood=None`, no rating numbers. Status downstream: "Not Applicable." **Updated 2026-05-08 (commit `1f4c31c`):** The N/A path now also runs keyword scoring against the pillar's rationale and key risk descriptions per candidate L2 and captures `key_risk_evidence` on the `source_not_applicable` row. Method stays `source_not_applicable` (filer's call respected); evidence is captured so contradictions surface visibly. See "N/A pillar conflict surfacing" subsection below.
- **Numeric** (Low–Critical): the rating is fanned out to **all five risk dimensions** (`likelihood, impact_financial, impact_reputational, impact_consumer_harm, impact_regulatory`) as the default value at `mapping.py:357-361`. Rationale parsing can override individual dimensions.
- **Anything else** (numeric like "3", typos, blank): silently treated as `None`.

#### N/A pillar conflict surfacing (post-2026-05-08)

Three coordinated changes close the gap where a legacy N/A pillar buried contradicting evidence:

1. **Keyword evidence captured on N/A pillars** (`mapping.py:338-396`). The N/A branch in `transform_entity` now runs the same keyword + condition scoring against rationale and key risk descriptions as `_resolve_multi_mapping`, but only as data capture — `method` stays `source_not_applicable`, status stays `Not Applicable`. Evidence stored in `key_risk_evidence` column on the row.

2. **Review note prepended to Decision Basis** (`enrichment.py:344-388`). When a `source_not_applicable` row has any signal flag (`app_flag`, `tp_flag`, `model_flag`, `aux_flag`, `core_flag`) OR `key_risk_evidence` populated, the Decision Basis prose leads with: *"Review note: the legacy filer rated this Not Applicable, but contradicting evidence exists for this L2 — [specific signals]. Reconsider before confirming N/A. See Additional Signals for the specific items."* Then the existing "legacy was N/A" sentence follows. Rows with no contradicting signals stay single-sentence.

3. **AI conflict-review routing** (`export_llm_prompts.py`). The LLM prompt-export filter now also pulls `Not Applicable` rows where `Additional Signals` is non-empty OR Decision Basis starts with `Review note:`. Each conflict row's prompt block carries a `[CONFLICT REVIEW]` tag. AI's reasoning template requires "Originally marked N/A but auditor should reconsider because..." (when proposing Applicable) or "Confirming N/A despite signals because..." (when keeping N/A).

**What this changes for reviewers:** an N/A pillar that has contradicting inventory tags or keyword matches in its rationale now produces a row with the conflict explicitly named in the Decision Basis prose, and gets routed through the AI override pipeline for validation. Status pill remains Not Applicable so the filer's call is preserved as the default; AI override or audit-team review can flip it.

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

### **IRM ORE ID** (bridge column — added with the IRM ORE integration)

**Read at:** `ingestion.build_ore_irm_mapping_index()` (and `__main__._compute_irm_ore_orphans` for the orphan surface). Column name configurable at YAML `columns.legacy_extras.irm_ore_id` (default `IRM ORE ID`).

Each AE's cell is a delimited list of IRM ORE IDs the audit team tagged to that entity. **This column is the entire AE-attribution path for IRM OREs** — the IRM source file has no AE column. Cells are split via `utils.split_id_list()` on semicolons, commas, *and* newlines (unified post-`df8a4d8`; earlier code split on newline only and silently dropped `;`/`,`-separated tails).

**Filtered / ignored:**
- An IRM ORE in the source file but absent from every AE's cell is invisible to the per-AE report — it surfaces only in `Upstream Tagging Gaps` (Drop Reason "Not in IRM ORE ID bridge").
- An ORE ID listed in a cell but missing from the IRM source file is skipped with a WARNING.

See the dedicated "IRM OREs" section below for the full flow.

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
| Per-pillar Inherent Risk | `mapping.py:315` | 5 dimension columns + `source_risk_rating_raw` | Non-Low/Med/High/Critical → None; N/A → SOURCE_NOT_APPLICABLE row + keyword evidence captured on row (since 2026-05-08) |
| Per-pillar Inherent Risk Rationale | `mapping.py:316` | (1) parsed dimensions, (2) keyword scoring evidence, (3) cross-boundary signals; full text stored as `source_rationale` | "n/a" / blank → skipped; case-insensitive substring; no fuzzy match |
| Per-pillar Control Assessment | `mapping.py:317` | `source_control_raw` (passive storage) | Currently unused for derivation |
| Per-pillar Control Rationale | `mapping.py:318` | `source_control_rationale` (passive storage) | Not parsed |
| Last Engagement Rating + dates | `enrichment.py:122-130` | `control_effectiveness_baseline` string per row | Empty rating → "No engagement rating available"; bad dates → "date unknown" |
| Application columns (5) | `flags.py:flag_application_applicability` | `app_flag`, `tp_flag`, `model_flag` | Only fires for L2s in `_APP_L2_MAP`; emptiness/non-emptiness only; key designation ignored |
| AXP/AENB Auxiliary Risk Dimensions | `flags.py:flag_auxiliary_risks` | `aux_flag` + Additional Signal | Names not normalizing to canonical L2 silently dropped |
| AXP/AENB Core Risk Dimensions | `flags.py:flag_core_risks` | `core_flag` + Additional Signal | Same as auxiliary |
| IRM ORE ID (bridge) | `ingestion.build_ore_irm_mapping_index` | (AE, ORE) pairs — the only AE attribution for IRM OREs | Split on `;` `,` newline via `split_id_list`; unbridged source OREs → Upstream Tagging Gaps |
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

## File: `prsa_report_*.xlsx` (Frankenstein report — Track B source-tagged L2)

The PRSA report. Contains AE × Issue × Control rows. Now carries a filer-tagged `Risk Level 2` column from IRM Archer that, when populated, drives L2 attribution directly (Track B); when blank or invalid, the per-issue PRSA mapper output (Tier 3) is the fallback.

> ℹ️ **About this file:** The Frankenstein report is now produced by `build_prsa_frankenstein.py` from three Archer extracts (`legacy_risk_data` + `PRSA_IRM_Archer` + `PRSA_Controls_Map`). Manual stitching is no longer needed. The main pipeline ingests the script's output via the same `prsa_report_*` file pattern.

### Where it gets loaded

`__main__.py:422-435` finds the most recent file by mtime in `data/input/`. Ingested at `ingestion.py:784-899` via `ingest_prsa()`.

### Expected columns (configured in YAML `columns.prsa:`, lines 173-194)

Required: `ae_id`, `prsa_id`, `issue_id` (lines 810-813 — `ValueError` if missing).

Optional pass-through (20 columns): `ae_name`, `audit_leader`, `core_audit_team`, `audit_engagement_id`, `all_prsas_tagged`, `issue_rating`, `issue_status`, `issue_identifier`, `issue_title`, `issue_description`, `issue_owner`, `root_cause_description`, `root_cause_sub_theme`, `root_cause_theme`, `risk_level_2`, `control_id_prsa`, `process_title`, `control_title`.

`risk_level_2` is the IRM Archer self-tagged L2; `root_cause_*` columns capture the filer's RCA narrative.

### Processing pipeline

1. Read file (line 798-801).
2. Strip column whitespace.
3. Stringify `ae_id` and `prsa_id` (lines 815-816).
4. **Build PRSA → AE cross-reference** (lines 819-833): walks the `All PRSAs Tagged to AE` column, builds `{prsa_id: set(ae_ids)}`. The `Other AEs With This PRSA` column (line 842) lists every other AE that shares this PRSA — surfacing cross-AE control-failure visibility for the reviewer.
5. **Resolve filer-tagged L2 (Track B)** (lines 844-883): for each row, normalize the `Risk Level 2` cell via `normalize_l2_name()`. If it resolves to a canonical taxonomy L2, store it in a new `Risk Level 2 Normalized` column and tag `L2 Provenance = "source"`. If the cell is blank, tag `L2 Provenance = "mapper"` (silent fallback). If the cell is populated but does not normalize, log a WARNING and tag `L2 Provenance = "mapper"`. If the column is absent entirely, every row falls back to mapper provenance with a single INFO log.
6. Log per-batch L2 provenance counts and shared-across-AEs PRSAs (lines 885-897).

### How PRSA gets used (3 consumers)

#### Use 1: Track B L2 substitution into `prsa_mapping_df` (`__main__.py:437-522`)

Before `build_prsa_mapping_index` runs, the pipeline walks `prsa_df` for any row where `L2 Provenance == "source"`. For each such issue, it:

1. Drops the mapper's emitted rows for that issue from `prsa_mapping_df`.
2. Re-inserts a single row carrying the source-tagged canonical L2.
3. If the issue was filtered out by the mapper entirely (e.g., status != Suggested Match), synthesizes a new row with `Mapping Status = "Source-Tagged"` so the source-tagged L2 still propagates downstream.

`build_prsa_mapping_index` then runs against the substituted DataFrame, producing the per-(entity, L2) index that `enrichment.derive_control_effectiveness` consumes for Impact of Issues. **PRSA now contributes to Impact of Issues** for the resolved L2 (whether IRM Archer-tagged or mapper-inferred). Mappings still don't confirm L2 applicability — that determination remains auditor-driven via the legacy crosswalk + findings + LLM overrides — but they DO drive the Impact of Issues display.

#### Use 2: `Source - PRSA Issues` tab (`export.py:360-381`)

Written to the workbook with the added `Other AEs With This PRSA` column. The internal `L2 Provenance` column is renamed to `L2 Source` for the workbook, with values recased from `source` / `mapper` to user-facing **`IRM Archer`** / **`Inferred`** (blank stays blank). Repositioned next to `Mapped L2s` when present. Visible since 2026-05-02. Reviewers can browse the full PRSA report and see which L2 attribution path each issue took.

The dual-source banner copy in the HTML report's Source - PRSA Issues tab is sourced from `config/banners.yaml` (`source_banners.prsa`) — that's why the banner mentions IRM Archer.

#### Use 3: PG gap pill index (Track C) — `ingestion.build_pg_gap_index`

The Frankenstein build flags issues whose description starts with `#PG` / `PG` as `Is PG Gap` (the Excel header displays as `PG Gap`; the HTML reader renames it back on read). `build_pg_gap_index` filters `prsa_df` to PG-flagged rows that have **both** an AE ID and a normalized L2, dedupes per (entity, L2, issue), and builds the `{entity: {l2: [pill dicts]}}` index that renders as per-AE PG Gap pills in the HTML report.

- PG-flagged issues **without an AE** (no PRSA control entered in IRM Archer yet) are excluded from pills and captured as orphans (`__main__._orphans_from_pg_prsa`) into `Upstream Tagging Gaps` with Drop Reason "PG gap — no AE".
- PG-flagged issues without a normalized L2 render nowhere per-L2; the `Source - PG Gaps` Excel tab still surfaces them.
- This index is later **unioned** with the PG-team-route index (see "PG team inputs" section below) via `merge_pg_gap_indexes` — PRSA-route pills win on metadata for duplicate (entity, L2, issue) keys.

### Filtered / ignored

- No row-level filtering at ingestion (all PRSA control rows kept regardless of status).
- Source-tagged `Risk Level 2` values that don't normalize: row kept, provenance set to `mapper`, WARNING logged.
- No status / severity / approval filters.

### Things worth flagging

1. **L2 Provenance has only two values:** `source` (IRM Archer wins) or `mapper` (PRSA mapper output is used). The internal column is the sentinel form; the Excel export renames it to `L2 Source` with values `IRM Archer` / `Inferred` for the user.
2. **The `Other AEs With This PRSA` column is tool-computed**, not from source data. Documented in the Methodology tab as of commit `7d2d083`.
3. **No deduplication if the file has multiple rows per (PRSA, AE).** PRSA reports often repeat AEs across rows because each issue/control gets its own row. The cross-AE logic correctly dedupes by `seen_aes` (line 822), but the output DataFrame retains all rows.
4. **Source-tagged L2 substitution is per-issue, not per-row.** When an issue has multiple PRSA control rows in `prsa_df`, every row carries the same source-tagged L2 by construction — the substitution loop dedups on `issue_id` (line 460).
5. **The Frankenstein build is a separate script.** `build_prsa_frankenstein.py` produces the `prsa_report_*.xlsx` from three Archer extracts. The main pipeline only consumes the output file, not the upstream extracts.

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

## Files: `IRM_ORE_raw_*` → `ORE_IRM_consolidated_*.xlsx` → `ORE_IRM_*` (IRM OREs, added 2026-05/06)

Operational risk events from the IRM Archer system. Unlike legacy OREs (whose mapper output carries its own AE column), **the IRM source has no AE column** — AE attribution flows entirely through the `IRM ORE ID` bridge column on `legacy_risk_data` (see the legacy section above). The flow has up to three files:

### Stage 0 (optional): consolidation pre-step — `consolidate_ore_irm.py`

The raw IRM export (`IRM_ORE_raw_*.{csv,xlsx}`) is *stacked*: one ORE spans multiple rows (source row, then Cause / Risk / Impact rows). When a raw file is present, `refresh.py` runs `consolidate_ore_irm.py` before the ore_irm mapper. It collapses to **one row per ORE ID**:

- ORE-level columns carry the first non-blank value down the stack.
- Cause / Risk text columns roll up distinct values newline-joined.
- Pre-computes three derived columns the rest of the pipeline trusts:
  - **`Impact Assessment Closed`** (Yes/No): No if any impact-bearing row is still open; an ORE with zero impact rows is **No** (no evidence of closure = open, conservative by design).
  - **`ORE Status`** (Open/Closed): Closed only when all four phases (Capture, RCA, Stop ongoing impact, impact phase) are done. A cancelled Capture Status **short-circuits to Closed** regardless of impacts.
  - **`ORE Materiality`** (Material/Non-Material) from `ORE Category`; **blank category → Material out of caution**. Materiality gates Impact of Issues only — it never changes ORE Status.

Output: `data/input/ORE_IRM_consolidated_<timestamp>.xlsx`. Covered by `tests/test_ore_irm_consolidate.py` (the best-tested corner of the pipeline).

### Stage 1: source ingest — `ingestion.ingest_ore_irm_source()`

`__main__` finds the most recent `ORE_IRM_*.{xlsx,csv}` (the consolidated file matches this pattern). Column names configurable at YAML `columns.ore_irm`. Processing:

1. Require the ORE ID column (`ValueError` if missing); drop blank-ID rows.
2. **Track B provenance** (same convention as PRSA): normalize the filer-tagged `Risk Level 2` per row → `Risk Level 2 Normalized` + `L2 Provenance` = `source` (valid), or `mapper` (blank or invalid; invalid logs a WARNING per ORE).
3. **Trust pre-computed `ORE Status` / `ORE Materiality` when present** (consolidated input); otherwise derive in-pipeline via `_derive_irm_ore_statuses` (roll-up across stacked rows — a single unfinished impact keeps the ORE Open) — the fallback path for flat fixtures.

### Stage 2: mapper output — `ore_irm_mapping_*.xlsx`

Produced by `python ore_mapper.py --source ore_irm` (same script as the legacy ORE mapper; `set_active_source()` rebinds its column globals from YAML `columns.ore_irm_mapper`). Ingested by `ingestion.ingest_ore_irm_mappings()`: same shape as the other mappers (All Mappings sheet, status filter, `"; "` explosion, `normalize_l2_name`, unmapped capture) **except no AE column is required** — unmapped items are keyed under `""` since AE attribution hasn't happened yet.

### Stage 3: bridge index — `ingestion.build_ore_irm_mapping_index()`

Joins everything: explodes each AE's `IRM ORE ID` cell into (AE, ORE) pairs via `split_id_list`, then per pair resolves the L2:

- `L2 Provenance == "source"` → the filer-tagged L2 wins, mapping status `Source-Tagged` (mapper output ignored for that ORE).
- Otherwise → the mapper's exploded (ORE, L2) pairs.

Each index item carries `ore_source: "IRM"` (so downstream closed-status filtering can treat IRM and legacy EV rows differently), `ore_status`, `ore_material`, `l2_provenance`, capture status, and `Legacy Event ID` when present.

**Combined ORE index:** `__main__` merges the IRM index with the legacy ORE index per (entity, L2) cell — **IRM rows first, legacy EV rows second** (deliberate ordering: IRM events are newer and more granular). The combined index is what `derive_control_effectiveness` and the flag functions consume.

### Where it lands

- **Impact of Issues**: only OREs with `ORE Status == "Open"` **and** Material (materiality gate per `13307b5`).
- **`Source - ORE IRM` tab + HTML dashboard**: full ORE population for traceability, including `ORE Rating` and `ORE Owner Business Unit (L1, L2, L3)` surfaced per `e7a7c03`/`295c598`. The HTML `Source - OREs` view mixes legacy and IRM grains — the JS dedupes by Event ID (Title|Desc fallback) and **never** resolves columns on the mixed-schema rows (the `oreRowEid` convention).
- **Upstream Tagging Gaps**: source OREs not bridged to any AE (`__main__._compute_irm_ore_orphans`).

### Filtered / ignored

| Condition | Result |
|---|---|
| Blank/`nan` ORE ID in source | Row dropped at ingest |
| Filer L2 invalid (doesn't normalize) | WARNING per ORE; falls back to mapper provenance |
| Mapper L2 unmappable | Captured to `unmapped_mapper_items` (keyed `""` — no AE yet) |
| ORE in source but in no AE's bridge cell | Invisible per-AE; surfaces in Upstream Tagging Gaps |
| ORE in a bridge cell but not in source | Skipped with WARNING |
| Closed or Non-Material ORE | On `Source - ORE IRM` tab, **not** in Impact of Issues |

### Things worth flagging

1. **The bridge column is a single point of failure.** No `IRM ORE ID` column on legacy → the entire IRM index build is skipped with a WARNING (items live only on the source + gaps tabs).
2. **Two open methodology questions** (tracked): how open status gets confirmed upstream, and who owns the AE-level IRM ORE ID tagging.
3. **Cancelled ⇒ Closed** is a deliberate rule, not a bug.

---

## File: `project_guardian_aera_inputs_*.xlsx` (PG team inputs — Track C2, second PG-gap route)

Per-Gap-ID severity ratings plus Archer bridge IDs from the Project Guardian team. Provides a **second AE-attribution route** for PG gaps, independent of the PRSA route (Use 3 in the PRSA section): the PRSA route requires a PRSA control to exist in IRM Archer; this route bridges through **findings** instead, so it can attribute gaps the PRSA route can't.

File pattern is YAML-configurable (`columns.pg_team_inputs.file_pattern`). Skipped with a WARNING if findings or PRSA aren't also loaded (the bridge needs both).

### Expected columns (configured in YAML `columns.pg_team_inputs:`)

Required: `gap_id`, `issue_id` (Archer IRM Issue ID — joins to prsa_df), `finding_id` (Archer eGRC FND ID — joins to findings_df). Optional: `impact_rating` (PG team's severity).

### Processing pipeline — `ingest_pg_team_inputs` + `build_pg_gap_index_from_pg_team`

1. Read (sheet name configurable), strip headers, clean the two bridge-ID columns (blank/NaN → "").
2. **FND_ID bridge:** each row's `finding_id` is looked up in `findings_df` (already exploded one row per (entity, L2) by `ingest_findings`). One FND ID can resolve to multiple (AE, L2) pairs — all become independent pill entries.
3. **Metadata enrichment:** if the row's `issue_id` exists in `prsa_df`, the pill carries PRSA metadata; **PRSA Issue Rating wins over the PG team's Impact Rating** (PG rating used only when PRSA's is blank). Issues absent from PRSA entirely get a synthetic title "(PG team gap — no PRSA record)" + the PG rating, and are counted as `pg_team_only_issues`.
4. **Union with the PRSA route** via `merge_pg_gap_indexes`, deduping on (entity, L2, issue) — PRSA-route pills win on metadata.

### Filtered / ignored

- Rows with no `finding_id`, or whose FND ID matches no ingested finding → counted `unresolved_no_fnd_match` and written to `Upstream Tagging Gaps` (Drop Reason "Archer eGRC FND ID not matched to a finding"). Note the findings file's own filters (Approved-only, blank severity) apply upstream — a gap pointing at a non-Approved finding is unresolvable by construction.
- Every pill from this route is tagged `pg_team_route: True` for diagnostic provenance; `scripts/compare_pg_mappings.py` diffs the two routes per Gap ID.

---

---

## Tier 3: Mapper Outputs (`ore_mapping`, `ore_irm_mapping`, `prsa_mapping`, `rap_mapping`)

The four mapper outputs share a near-identical shape: each is produced by a spaCy-based mapper script (`ore_mapper.py` — which also produces `ore_irm_mapping_*` when run with `--source ore_irm` — `prsa_mapper.py`, `rap_mapper.py`), reads the same "All Mappings" sheet structure, and feeds Impact of Issues per L2 row. The ore_irm variant differs in one structural way (no AE column — see the IRM OREs section above for its bridge-based attribution); this section covers the shared shape.

### How these files are produced

These are **derived artifacts**, not raw inputs. Each mapper script:
1. Loads its raw input (OREs / PRSA issues / RAPs) and `data/input/L2_Risk_Taxonomy.xlsx`.
2. Builds reference vectors per L2 from the L2 description text using spaCy `en_core_web_lg` (300-dim word vectors). **L3/L4 columns from the taxonomy file, when present, are folded into the per-L2 reference text** — the L3-based bucketing also gives Fraud-at-L3-grain L2s their own vectors. Code: `ore_mapper.py:166-249`, `prsa_mapper.py:182-...`, `rap_mapper.py:150-...`.
3. Computes cosine similarity between each item's text and each L2 vector.
4. Bands the scores: **Needs Review** (every item ≥ 0.50 floor) or **No Match** (below floor, excluded). *(2026-05-17: the former Strong / Suggested Match / Weak bands were removed — `docs/Methodology.md` §4.C5–C6 governs.)*
5. Writes a 5-sheet workbook (`All Mappings`, `Needs Review`, `Summary`, `L2 Distribution`, `Raw Scores`) into `data/output/`.

The mappers are **run separately** before the main transformer pipeline. The user runs them manually (or via `python refresh.py`), reviews the `Needs Review` sheet, updates the `Mapping Status` column where needed, and the main pipeline ingests the most-recent mapper output. The main pipeline reads only from `data/output/` (per commit `30c7f11`).

### Shared shape: ingestion pipeline

For all three (`ingest_ore_mappings`, `ingest_prsa_mappings`, `ingest_rap_mappings`):

1. Read sheet `"All Mappings"`.
2. Strip column whitespace.
3. Required-column check — raises `ValueError` if source-specific required columns are missing.
4. **🚫 FILTER: Mapping Status** — keeps rows whose band is in the configured filter (default still lists `["Suggested Match", "Needs Review"]` for backward-compat with older workbooks; current mappers emit only **"Needs Review"**, so effectively all above-floor rows pass). No Match is excluded; `Source-Tagged` (PRSA Track B) bypasses the filter.
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
| Mapping Status not in confidence_filter | ingestion | No Match always dropped (below floor). Mappers now emit only "Needs Review", so above-floor rows pass; `Source-Tagged` bypasses the filter. |
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

6. **Band ratio looks lopsided on real data — by design.** Real-data runs with `en_core_web_lg` produce ~99% Needs Review / ~1% Suggested Match across all three mappers. Score percentiles are p25=0.93, median=0.95, p75=0.97 (very compressed at the high end), and margins between Match 1 and Match 2 are ~0.002 median. Both margin-based and absolute-score bands collapse on this distribution because spaCy embeddings (any size) saturate at high similarity for enterprise-risk text — the L2 categories share too much vocabulary at the L1 theme level for a general-purpose embedding to cleanly separate.

   **Percentile-based bands were considered and rejected (2026-05-04 decision):** they would have split ~75% of items into Suggested Match (top-1 candidate shown only) and ~25% into Needs Review (top-3 candidates shown). The current 99% Needs Review actually produces a *better* reviewer experience because top-3 candidates are surfaced for nearly every item — more information per decision, no false-confidence "Suggested" labels on items where the model is genuinely uncertain. Reviewers don't engage with band terminology in practice; they look at the candidates and pick. The band ratio is engineer-aesthetic noise, not a reviewer-pain signal.

   **The real fix is a better embedding** — sentence-transformers fine-tuned on risk text or OpenAI text-embedding-3-large (API access required). Until that's available, leave the band logic alone. Tracked as a Phase 2 item in `project_open_items.md`.

---

---

## Tier 4: Override Files (`llm_overrides`, `rco_overrides`, `optro_export`)

Three override files with very different roles. All feed decisions back into the pipeline from external review work. **All are optional** — pipeline runs without any of them.

| File | Source of decisions | What it overrides | Where it's consumed |
|---|---|---|---|
| `llm_overrides_*.{xlsx,csv}` | LLM (e.g., ChatGPT) responses to prompts generated by `export_llm_prompts.py` | Per-row keyword-scoring decisions for `multi`-type pillars | `mapping.py:_resolve_multi_mapping` — replaces keyword evidence with LLM determination |
| `rco_overrides_*.{xlsx,csv}` | Risk Category Owners reviewing the `Risk_Owner_Review` tab | Per-row applicability status + rating | **`review_builders.py:build_risk_owner_review_df` ONLY** — sibling-context overlay. Does NOT reach `Audit_Review` or HTML (§5.16) |
| `optro_export_*.{xlsx,csv}` | Audit team's confirmed L2 assessments entered in Optro (the system of record) | Whole rows — status, method, ratings — for **fully-covered entities only** | `optro.apply_optro_overrides` on `transformed_df`, applied **after** all flag functions |

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

## File: `optro_export_*.{xlsx,csv}` (Optro overrides — team decisions of record)

The audit team's confirmed L2 assessments, exported from Optro (the system of record AERA results are entered into). Treated as **authoritative**: where applied, the team's decision replaces the tool's status and ratings on `transformed_df` itself — unlike RCO overrides, these DO reach `Audit_Review` and the HTML report.

### Expected columns (configured in YAML `columns.optro:`)

Required: `entity_id` (`Audit Entity ID`), `l2_risk` (`Risk Category`), `risk_rating` (`Inherent Risk Rating`) — `ValueError` if missing. Optional: per-dimension `Likelihood` / four impact columns (Low–Critical → 1–4; anything else → None) and `team_rationale` (`Rationale`).

### Processing pipeline — `ingestion.ingest_optro_overrides`

1. Read, strip headers, normalize L2 via `normalize_l2_name()` — unmappable L2 rows dropped with WARNING listing the offending values.
2. **Risk Rating doubles as applicability:** Low/Medium/High/Critical → `applicable` (original casing preserved for display); `N/A` / blank → `not_applicable`.
3. Returns `(overrides, coverage)`: `{(entity, l2): {...}}` plus `{entity: set of submitted L2s}`.

### How it gets applied — `optro.py`, AFTER all flag functions

Ordering matters: overrides apply after `flag_*` runs so conflict detection can read the row's own signals.

1. **`assess_optro_coverage`** — **all-or-nothing per entity.** An entity's overrides apply only if the team submitted every canonical L2 that exists on that entity's rows; partially-covered entities get a WARNING (listing missing L2s) and **no overrides at all** — avoids mixing tool + team decisions for the same entity.
2. **`apply_optro_overrides`** — for fully-covered entities, replaces method/ratings/applicability per row; flags rows via an `optro_override` column; team rationale stored for Decision Basis prose.
3. **`detect_optro_conflicts`** — when the team marked an L2 Not Applicable but the row's own signals (`app_flag`, `tp_flag`, `model_flag`, `aux_flag`, `core_flag`, `cross_boundary_flag`) suggest it applies, the conflict surfaces in Control Signals so the team can reconcile their own contradiction.

### Filtered / ignored

| Condition | Result |
|---|---|
| L2 doesn't normalize | Row dropped + WARNING |
| Blank/`nan` entity ID | Row skipped |
| Entity partially covered | **Entire entity's overrides unapplied** + WARNING |
| Invalid dimension value | That dimension → None, row kept |

### Things worth flagging

1. **The signal-column list for conflict detection is hardcoded** in `optro.py` (`_APPLICABILITY_SIGNAL_COLUMNS`) — renaming a flag column elsewhere silently weakens conflict detection. Flagged in IMPROVEMENT_PLAN.md 1.4.
2. **Applicability is inferred from the rating column**, not a dedicated status column — a team that leaves the rating blank on an applicable risk reads as `not_applicable`.

---

## Summary table for Tier 4

| File | Required columns | Filters | Consumer | Effect on Audit_Review? |
|---|---|---|---|---|
| `llm_overrides_*.{xlsx,csv}` | entity_id, source_legacy_pillar, classified_l2 (+ determination OR llm_confidence) | L2 normalization; determination validation; consolidator pre-validates per-entity counts and exact triple coverage | `mapping.py:_resolve_multi_mapping` (pre-empts keyword scoring; layers AI reasoning + keyword evidence) | **Yes** — produces `LLM_OVERRIDE` or `LLM_CONFIRMED_NA` rows that flow into Audit_Review with combined reasoning + keyword evidence |
| `rco_overrides_*.{xlsx,csv}` | entity_id, l2_risk, rco_status | L2 normalization; status validation | `review_builders.py:build_risk_owner_review_df` ONLY (sibling context + peer ratings) | **No** — visible only in Risk_Owner_Review tab. §5.16 tabled item. |
| `optro_export_*.{xlsx,csv}` | Audit Entity ID, Risk Category, Inherent Risk Rating | L2 normalization; all-or-nothing entity coverage gate | `optro.apply_optro_overrides` on transformed_df (post-flags) + `detect_optro_conflicts` | **Yes** — replaces status/method/ratings for fully-covered entities; N/A-vs-signals conflicts surface in Control Signals |

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

## Cross-cutting: Upstream Tagging Gaps (orphan capture)

Every path that drops or fails to attribute an item routes it into the **`Upstream Tagging Gaps`** workbook tab, on a fixed six-column schema (`Source, Item ID, Title, Status, Drop Reason, Source File` — `__main__._ORPHAN_COLUMNS`). Two delivery mechanisms:

1. **Sidecar files:** mappers and the Frankenstein build write `<output>_orphans.xlsx` next to their main output; `__main__._read_orphans_sidecar` picks them up. (This is why every "latest file" glob excludes `*_orphans*` stems.)
2. **In-pipeline capture:** findings with blank AE; BMA blank-AE rows ("Kept with warning (no AE)" — BMA keeps the rows, the tab just surfaces them); PG-flagged PRSA issues with no AE; IRM OREs not in any bridge cell; PG team gaps whose FND ID didn't match a finding.

The principle: the pipeline never infers linkage the source system didn't establish, but it also never *silently* loses an item — everything dropped is visible with a reason, so the upstream tagging gap can be chased with the responsible team.

## Cross-cutting: Inventory files (HTML report only)

`export_html_report.py` loads five inventory files directly from `data/input/` (patterns YAML-configurable at `columns.inventory_files:`): `all_applications_*`, `all_thirdparties_*`, `policystandardprocedure_*`, `lawsandapplicability_*`, `model_inventory_*`. Display-only: they populate the HTML drill-down inventory views (filtered to IDs tagged to the selected entity, with "key" markers from `Key_Inventory`). They never touch `transformed_df` or the Excel decision tabs. A missing file logs a warning and renders an empty view; a *corrupt* file is currently swallowed silently (IMPROVEMENT_PLAN.md 1.5).

---

## Tier completion status

- [x] **Tier 1**: legacy_risk_data (incl. IRM ORE ID bridge column), key_risks (formerly sub_risk_descriptions), findings_data
- [x] **Tier 2**: prsa_report (incl. PG gap route), bm_activities, gra_raps, IRM OREs (raw → consolidated → source), pg team inputs (enterprise_findings removed — never used)
- [x] **Tier 3**: ore_mapping, ore_irm_mapping, prsa_mapping, rap_mapping (mapper outputs)
- [x] **Tier 4**: llm_overrides (with batch-folder workflow + 3-layer consolidator validation), rco_overrides, optro_export
- [x] **Tier 5**: L2_Risk_Taxonomy.xlsx (ffill fix in mappers, L1 enrichment, YAML alignment validator, source tab)
- [x] **Cross-cutting**: Upstream Tagging Gaps / orphan sidecars, HTML-only inventory files

**All tiers complete. Last verified against HEAD: 2026-06-12.**
