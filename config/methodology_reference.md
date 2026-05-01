# Methodology Reference — Risk Taxonomy Transformer

Internal cheat sheet. One section per data source, end-to-end: what comes in, what gets kept, what gets dropped, what it becomes in the output. Every rule links to code so drift is easy to spot.

Status values produced by the pipeline (canonical, from `risk_taxonomy_transformer/constants.py:16-23`):

| Status | Literal |
|---|---|
| Applicable | `"Applicable"` |
| Not Applicable | `"Not Applicable"` |
| Assumed N/A — Verify | `"Assumed N/A — Verify"` |
| Applicability Undetermined | `"Applicability Undetermined"` |
| No Legacy Source | `"No Legacy Source"` |
| Needs Review (fallback only) | `"Needs Review"` |

Method constants live in `risk_taxonomy_transformer/constants.py:30-40`.

---

## 1. Legacy Risk Data — 14 pillars, entity metadata, handoffs, inventory tags

One wide-format row per entity containing ratings, rationale, and control assessments for each of the 14 legacy pillars, plus org metadata, audit engagement data, application/third-party tag columns, and auxiliary risk dimension columns.

- **Input file pattern:** `data/input/legacy_risk_data_*.xlsx` or `.csv` (most recent wins) — `risk_taxonomy_transformer/__main__.py:69-77`.
- **Entry point:** `ingest_legacy_data()` at `risk_taxonomy_transformer/ingestion.py:26-57`.
- **Expected column groups** (all configured under `columns:` in `config/taxonomy_config.yaml:65-243`):
  - Entity ID: `Audit Entity ID` (`:66`).
  - Org metadata: entity name/overview, audit leader, PGA/ASL, core audit team (`:68-73`).
  - Control effectiveness: `AXP - Audit Report Rating`, `Final Audit Report Date`, `Next Audit Start Date` (`:75-78`).
  - Per-pillar columns built as `{Pillar} {suffix}` where suffixes are `Inherent Risk`, `Inherent Risk Rationale`, `Control Assessment`, `Control Assessment Rationale` (`:179-183`).
  - Pillars **with** rationale (11): Credit, Market, Strategic & Business, Funding & Liquidity, Reputational, Model, Financial Reporting, External Fraud, Operational, Compliance, Country (`:185-196`).
  - Pillars **without** rationale (3): Information Technology, Information Security, Third Party (`:198-201`).
  - Applications tag columns (`:203-207`): `PRIMARY IT APPLICATIONS (MAPPED)`, `SECONDARY IT APPLICATIONS (RELATED OR RELIED ON)`, `PRIMARY TLM THIRD PARTY ENGAGEMENT`, `SECONDARY TLM THIRD PARTY ENGAGEMENTS (RELATED OR RELIED ON)`.
  - Policies/laws tag columns (`:209-212`).
  - Auxiliary dimension columns (`:241-243`): `AXP Auxiliary Risk Dimensions`, `AENB Auxiliary Risk Dimensions`.

### Keep rules

| Rule | Where |
|---|---|
| Strip whitespace from all column names | `ingestion.py:45` |
| Keep one row per entity — if `report_date_col` passed, keep most recent by that date; otherwise whatever pandas returns | `ingestion.py:48-54` |

### Drop / filter rules

| Rule | Reason | Code |
|---|---|---|
| Deduplicate multiple reports per entity, keep most recent | Historical audit reports would otherwise create duplicate entity rows | `ingestion.py:48-54` |

No hard filters here — all surviving entities go into the transformer.

### Warnings — none at ingest; handled downstream

### Statuses / methods produced (downstream, via `mapping.py:transform_entity`)

Per-pillar rating drives the method:

| Legacy rating | Pillar mapping_type | Method produced | Status |
|---|---|---|---|
| Blank / "N/A" / "Not Applicable" | `direct` or `multi` | `source_not_applicable` (on all candidate L2s) | Not Applicable |
| Numeric (Low/Med/High/Critical) | `direct` | `direct` | Applicable |
| Numeric, no rationale column (IT/InfoSec/Third Party) | `multi` | `direct (no rationale column)` on each primary target | Applicable |
| Numeric with keyword hits | `multi` | `evidence_match (primary|secondary|conditional)` | Applicable |
| Numeric, pillar has evidence elsewhere but not this L2 | `multi` | `evaluated_no_evidence` | Assumed N/A — Verify |
| Numeric, no evidence for any L2 in the pillar | `multi` | `no_evidence_all_candidates` | Applicability Undetermined |
| Numeric | `overlay` (Country only) | No row created; flag only | — |
| No legacy pillar maps to this L2 at all | — | `true_gap_fill` | No Legacy Source |

See `mapping.py:270-484` for the full branching and `enrichment.py:308-329` for the method → status mapping.

### Known edge cases

- **IT, InfoSec, Third Party have no rationale column.** Multi-mapping evidence scoring is bypassed — all primary targets populated directly with high confidence (`mapping.py:386-396`). Method becomes `"direct (no rationale column)"`, which still hits the `direct` substring check in `_derive_status`.
- **Pillar columns not present** → warning log, no rows created for that pillar (`mapping.py:299-302`). Entity still gets 23 L2 rows via gap-fill for missing L2s.
- **Country pillar is overlay.** Does not create L2 rows. Instead creates entries in `overlay_flags` that merge onto the four target L2s (Prudential, Financial Crimes, Consumer/SMB, Commercial) in `pipeline.py:85-118`. See Country overlay notes in Taxonomy Mapping below.
- **N/A ratings still produce rows.** Pillar rated N/A creates `source_not_applicable` rows on all candidate L2s (`mapping.py:316-340`). Not skipped silently.
- **Row count invariant:** every entity ends up with exactly 23 L2 rows in `transformed_df` after gap-fill (`mapping.py:474-482`).

---

## 2. Sub-Risk Descriptions

Granular "Key Risks" associated with each entity, each tagged to one or more legacy L1 pillars. Used as secondary evidence for keyword scoring during multi-mapping resolution.

- **Input file pattern:** `data/input/sub_risk_descriptions_*.xlsx` or `.csv` — `__main__.py:82-87`.
- **Entry point:** `ingest_sub_risks()` at `ingestion.py:74-123`.
- **Expected columns** (`taxonomy_config.yaml:80-85`):
  - `Audit Entity` → internal `entity_id`
  - `Key Risk ID` → `risk_id`
  - `Key Risk Description` → `risk_description`
  - `Level 1 Risk Category` → `legacy_l1_raw` (may hold multiple pillars separated by `\n`, `\t`, `;`, or `|`)
  - `Inherent Risk Rating` (optional, not used for scoring)

### Keep rules

| Rule | Where |
|---|---|
| Strip whitespace from column names | `ingestion.py:94` |
| Explode multi-value L1 cells on `\n`, `\t`, `;`, `|` | `ingestion.py:111-112` |
| Strip whitespace from each exploded L1 value | `ingestion.py:113` |
| Coerce `entity_id` to trimmed string | `ingestion.py:107` |

### Drop / filter rules

| Rule | Reason | Code |
|---|---|---|
| Drop rows where exploded L1 is `""` or `"nan"` | Exploding empty cells creates null L1s | `ingestion.py:114` |
| Sub-risks with L1 not in the crosswalk are silently ignored during scoring | Only diagnostic warning logged | `ingestion.py:156-168` |

### Warnings

- Sub-risk L1s not matching any crosswalk key are logged at WARNING but retained in the index (consumers just skip them). `ingestion.py:166`.

### Statuses / methods produced

Sub-risks never produce rows on their own. They only contribute keyword evidence to multi-mapping resolution via the sub-risk index. Evidence label format: `"sub-risk {risk_id} [{desc[:80]}]: kw1, kw2"` (`mapping.py:139-148`).

### Known edge cases

- **Sub-risk rating column is ingested but not used for scoring.** The sub-risk's own `Inherent Risk Rating` is captured and displayed in the source tab but does not contribute to the transformer decision.
- **Index keys are raw L1 strings.** Crosswalk keys are also raw L1 strings — if the sub-risk file uses a slightly different name (e.g. `"Strategic and Business"` vs `"Strategic & Business"`), sub-risks for that L1 are ignored without row-level warning. Watch the ingestion log for "Sub-risk L1s NOT in crosswalk".
- **Multi-L1 explosion duplicates keyword contributions.** A sub-risk tagged to 3 L1s gets scored 3 times — once per pillar during resolution. This is intended: the sub-risk genuinely informs each pillar's applicability.

---

## 3. IAG Findings (audit findings/issues)

Open audit findings. Used for two things: (a) confirming applicability of an L2 (creates `issue_confirmed` rows), (b) feeding the Impact of Issues column and the Control Contradiction flag.

- **Input file pattern:** `data/input/findings_data_*.xlsx` or `.csv` — `__main__.py:112-119`.
- **Entry point:** `ingest_findings()` at `ingestion.py:248-340`.
- **Expected columns** (`taxonomy_config.yaml:87-95`):

| Config key | Column | Required |
|---|---|---|
| `entity_id` | `Audit Entity ID` | Yes |
| `issue_id` | `Finding ID` | |
| `l2_risk` | `Risk Dimension Categories` | Yes |
| `severity` | `Final Reportable Finding Risk Rating` | |
| `status` | `Finding Status` | |
| `issue_title` | `Finding Name` | |
| `remediation_date` | `Actual Remediation Date` | |
| `approval_status` | `Finding Approval Status` | |

### Keep rules

| Rule | Where |
|---|---|
| Explode multi-value L2 cells (alt+enter → `\n` / `\r\n` / `\r`) | `ingestion.py:297-300` |
| Normalize L2 names via `normalize_l2_name()` (alias resolution, L1-prefix strip) | `ingestion.py:303-304` |
| Keep only L2s present in canonical taxonomy (`L2_TO_L1`) | `ingestion.py:329-333` |

### Drop / filter rules

| Rule | Reason | Code |
|---|---|---|
| Only rows where `Finding Approval Status == "Approved"` | Draft/in-review findings shouldn't confirm applicability | `ingestion.py:283-287` |
| Drop rows with blank severity | Incomplete — can't reliably anchor a control contradiction | `ingestion.py:290-294` |
| Drop L2 values that don't normalize (e.g. "Fair Lending / Regulation B") | Not in canonical 23-L2 taxonomy | `ingestion.py:300, 306-326` |
| Drop L2 values that normalize to something still not in `L2_TO_L1` | Defensive — shouldn't happen | `ingestion.py:328-333` |
| Enterprise findings with unmappable L2s dropped silently (diagnostic only) | Same reason | `ingestion.py:482-492` |

### Warnings

Unmappable L2 values are captured into `unmapped_findings` dict (`ingestion.py:309-318`), available for audit/diagnostic but not merged back into rows. The file reports counts per unmapped value.

### Statuses / methods produced

| Trigger | Method | Status | Notes |
|---|---|---|---|
| Entity has ≥1 valid finding for an L2 | `issue_confirmed` | Applicable | `mapping.py:38-67`; no rating carried (findings confirm applicability, not ratings). |
| `issue_confirmed` loses dedup vs. a rated direct/evidence_match row | Base method + `(dedup: kept higher)` | Same as winner | Findings evidence appended to winner's `sub_risk_evidence`. `mapping.py:230-244`. |

Active findings for the Impact of Issues column are those with status in `{"open", "in validation", "in sustainability"}` — case-insensitive (`enrichment.py:149-153`). Other statuses (closed, cancelled, not started) contribute to the Source tab but not to the impact summary or control contradiction flag.

### Known edge cases

- **Finding status check is lowercase.** `"Open"` and `"open"` both match, but `"OPEN "` with trailing whitespace does not in the control contradiction filter (`flags.py:82-86`) — the stripping happens inside the comparison (`str(f.get("status", "")).strip().lower()`), so trailing space is OK.
- **Multi-L2 explosion duplicates findings.** A single finding tagged to `"Data\nPrivacy"` creates two index entries, and both L2s get a matching `issue_confirmed` row.
- **Unmapped findings per entity** are available for reporting but never re-enter the pipeline. Rework needed if a new L2 alias emerges.
- **Closed findings not excluded at ingest.** They survive ingest but are filtered out where it matters (active findings list in `enrichment.py:149-153` and `flags.py:82-86`). They still appear in the Source - Findings tab of the workbook.

---

## 4. Operational Risk Events (OREs)

Operational loss/near-miss events from the ORE system. Runs as a separate preprocessing pipeline (`ore_mapper.py`) which produces a reviewer-facing workbook. The transformer ingests Sheet 1 of that workbook.

### 4a. `ore_mapper.py` — preprocessing pipeline

Takes raw ORE events, computes spaCy semantic similarity against the 23 L2 definitions, classifies each event as Suggested Match / Needs Review / No Match.

- **Input files:** `data/input/ORE_*.xlsx` (most recent by mtime) and `data/input/L2_Risk_Taxonomy.xlsx` — `ore_mapper.py:98-107`, `:82`.
- **Expected ORE columns** (`taxonomy_config.yaml:168-177`):

| Config key | Column |
|---|---|
| `event_id` | `Event ID` |
| `event_title` | `Event Title` |
| `event_description` | `Event Description / Summary` |
| `entity_id` | `Audit Entity (Operational Risk Events)` |
| `event_classification` | `Final Event Classification` |
| `event_status` | `Event Status` |

### Filter stack (order matters — `ore_mapper.py:load_ore_data`)

| Order | Rule | Reason | Code |
|---|---|---|---|
| 1 | Required columns present: Event ID, Event Title, Event Description / Summary | Cannot compute similarity without text | `ore_mapper.py:112-116` |
| 2 | Strip and coerce text columns | | `ore_mapper.py:121-127` |
| 3 | Drop rows where `Event Status` is closed — `{closed, canceled, draft canceled, draft expired, draft, pending cancelation by event admin}` (case-insensitive) | No need to map inactive events | `ore_mapper.py:129-138` |
| 4 | Drop rows where both Event Title and Event Description are empty/`"nan"` | No text → no similarity computable | `ore_mapper.py:140-142` |
| 5 | Drop rows where Event ID is empty/`"nan"` | No handle for traceability | `ore_mapper.py:143` |
| 6 | Drop rows with blank `Audit Entity (Operational Risk Events)` | Can't attribute event to an entity's evidence brief | `ore_mapper.py:146-151` |

### Classification logic (`ore_mapper.py:classify_mappings`, `:308-390`)

- **No Match:** Top-1 similarity score < `MIN_SIMILARITY_SCORE` (0.50). Weak confidence. `Mapped L2s` is blank. Excluded from downstream pipeline.
- **Needs Review:** Top-1 score ≥ 0.50 but margin to Top-2 < `AMBIGUITY_MARGIN_THRESHOLD` (auto-computed from data: P25 of margins, clamped to [0.01, 0.05]). All candidates above 0.50 listed in `Mapped L2s`. Confidence band: `Review Required`.
- **Suggested Match:** Top-1 score ≥ 0.50 and margin to Top-2 ≥ threshold. Additional candidates (Match 2/3) added to `Mapped L2s` only if score ≥ 0.50 and `(top_score - their_score) < threshold * 2`. Confidence band: `Strong` if top ≥ 0.75 else `Moderate`.

### 4b. Transformer ingestion — `ingest_ore_mappings()` at `ingestion.py:365-413`

Reads Sheet 1 "All Mappings" from the ORE mapper output. Explodes the semicolon-separated `Mapped L2s` column into one row per (entity, L2).

- **Filter to mapping statuses listed in** `ore_confidence_filter` config — defaults to `["Suggested Match", "Needs Review"]` (`taxonomy_config.yaml:58-60`). "No Match" rows are excluded from the pipeline. `ingestion.py:383-387`.
- **Required columns** on the mapping file: `Event ID`, `Audit Entity ID`, `Mapping Status`, `Mapped L2s` (`ingestion.py:378-381`).
- **Drop ORE-L2 pairs where L2 name fails `normalize_l2_name()`** — diagnostic log of dropped values. `ingestion.py:402-410`.

### Statuses / methods produced

OREs **do not** produce rows in the transformed_df. They feed only into the Impact of Issues column (`enrichment.py:160-174`).

Open/closed classification for Impact of Issues (`enrichment.py:162-168`) uses the same `_CLOSED_STATUSES` set as the mapper; unknown status treated as open (so it appears in the summary line).

### Known edge cases

- **Row fan-out: "Source - OREs" has more rows than the raw ORE input.** Each ORE with multiple mapped L2s becomes N rows after explosion. This is intentional — per-L2 indexing — but means row counts between raw and source tab won't reconcile directly.
- **`ore_confidence_filter` default includes "Needs Review".** Set in `taxonomy_config.yaml:58-60`. "Needs Review" OREs propagate into the Impact of Issues column for every candidate L2 they could fit. If this feels noisy, narrow the filter.
- **Old ORE files may be missing `Event Status` or `Final Event Classification`** — ingestion handles absence defensively (`ingestion.py:428-436`; `ore_mapper.py:124-127`).
- **Event titles/descriptions truncated to 200 chars** for the Impact of Issues output (`ingestion.py:424-425`). Full descriptions live in the ORE mapper workbook, not the transformer output.
- **Closed OREs are dropped at the mapper stage**, so they never reach the transformer. If a historical event is needed for context, pull from the raw ORE file, not the mapper output.

---

## 5. PRSA Issues

Combined AE + Issues + PRSA controls report ("Frankenstein" format). Each row is one issue-control combination within an AE. Used for cross-AE visibility and operational control inference.

- **Input file pattern:** `data/input/prsa_report_*.xlsx` or `.csv` — `__main__.py:303-309`.
- **Entry point:** `ingest_prsa()` at `ingestion.py:518-585`.
- **Expected columns** (`taxonomy_config.yaml:116-137`): AE ID, AE Name, Audit Leader, Core Audit Team, Audit Engagement ID, All PRSAs Tagged to AE, Issue ID, Issue Rating, Issue Status, Issue Identified By Group, Issue Identifier, Issue Breakdown Type, Issue Owning Business Unit, Issue Title, Issue Description, Issue Owner, Control ID (PRSA), PRSA ID, Process Title, Process Owner, Control Title.

### Keep rules

| Rule | Where |
|---|---|
| Strip whitespace from column names | `ingestion.py:532` |
| Trim AE ID and PRSA ID | `ingestion.py:544-545` |
| Compute cross-AE "Other AEs With This PRSA" column from `All PRSAs Tagged to AE` | `ingestion.py:547-571` |

### Drop / filter rules

**None.** All rows pass through. The PRSA source is displayed in the Source - PRSA Issues tab for analyst reference but has no pipeline effect on L2 status or rating (as of Phase 1).

### Drop / filter rules (required columns)

| Rule | Reason | Code |
|---|---|---|
| Required columns present: AE ID, PRSA ID, Issue ID | File format validation | `ingestion.py:539-542` |

### Warnings — none

### Statuses / methods produced

**None.** PRSA is view-only in Phase 1. Phase 2 plan: map PRSA control failures via issues to infer AE control effectiveness (per user memory `project_prsa_input.md`).

### Known edge cases

- **PRSAs tagged to multiple AEs create visibility cross-links.** The `Other AEs With This PRSA` column is derived from `All PRSAs Tagged to AE` parsed on `\n` / `\r\n` / `\r` (`ingestion.py:559-561`).
- **Row count does not equal issue count or PRSA count.** Each row is an issue-control pair. Grouping required for most analyses.

---

## 6. GRA RAPs (regulatory findings)

Regulatory Action Plans (RAPs) from GRA — typically tied to regulatory exam findings. View-only in Phase 1.

- **Input file pattern:** `data/input/gra_raps_*.xlsx` or `.csv` — `__main__.py:333-339`.
- **Entry point:** `ingest_gra_raps()` at `ingestion.py:640-683`.
- **Expected columns** (`taxonomy_config.yaml:152-166`): Audit Entity ID, Audit Entity Name, Audit Entity Status, Core Audit Team, Audit Leader, PGA/ASL, GRA RAPS, Audit Entity (GRA RAPs), RAP ID, RAP Header, RAP Details, BU Corrective Action Due Date, RAP Status, Related Exams and Findings.

### Keep rules

| Rule | Where |
|---|---|
| Strip whitespace from column names | `ingestion.py:653` |

### Drop / filter rules

| Rule | Reason | Code |
|---|---|---|
| Required columns present: RAP ID, RAP Header | File format validation | `ingestion.py:660-663` |
| Drop rows with blank RAP ID (`""`, `"nan"`, `"none"`, NaN) | Entity-level rows with no actual RAP | `ingestion.py:666-670` |

### Warnings

- Rows with blank entity IDs logged at WARNING but kept (`ingestion.py:672-679`).

### Statuses / methods produced

**None.** GRA RAPs are view-only in Phase 1 and displayed in the Source - GRA RAPs tab.

### Known edge cases

- **Entity-level vs RAP-level rows.** The source file mixes "entity has N RAPs" summary rows and individual RAP rows. The blank-RAP-ID filter (step above) removes the summaries. If the file format changes to stop mixing row types, this filter becomes a no-op.

---

## 7. BM Activities (Business Monitoring Activities)

BMA instances — scheduled business monitoring deliverables. Each row is one activity instance with planned completion date and result/impact info.

- **Input file pattern:** `data/input/bm_activities_*.xlsx` or `.csv` — `__main__.py:318-324`.
- **Entry point:** `ingest_bma()` at `ingestion.py:588-637`.
- **Expected columns** (`taxonomy_config.yaml:139-150`): Related Audit Entity, Activity Instance ID, Related BM Activity ID, Related BM Activity Title, Planned Instance Completion Date, Did this activity occur?, Business Monitoring Cases, Did this activity result in an impact to one or more of the following items?, If yes, select one or more of the following actions needed, Summary of Results, If yes, please describe impact.

### Keep rules

| Rule | Where |
|---|---|
| Strip whitespace from column names | `ingestion.py:602` |
| Keep rows with NaT (unparseable) completion dates | Don't silently drop blank dates | `ingestion.py:632` |
| Keep rows with blank entity IDs (warning logged) | Completeness | `ingestion.py:616-621` |

### Drop / filter rules

| Rule | Reason | Code |
|---|---|---|
| Required columns present: Activity Instance ID, Planned Instance Completion Date | File format validation | `ingestion.py:609-613` |
| Drop rows where Planned Instance Completion Date parses and is `< 2025-07-01` | Focus on current/forward-looking activities | `ingestion.py:624-632` |

### Warnings

- Blank entity IDs: logged at WARNING with count, but rows kept (`ingestion.py:616-621`). Downstream any per-entity filter by entity ID will skip them, but they remain in the Source - BM Activities tab.

### Statuses / methods produced

**None.** BMA is view-only in Phase 1.

### Known edge cases

- **July 2025 cutoff is hardcoded.** `cutoff = pd.Timestamp("2025-07-01")` in `ingestion.py:626` — not in the YAML config. Update here when the cutoff changes.
- **"Did this activity occur?" column is not used for filtering.** Ingested and displayed, but not used to narrow the set. If you want to hide not-yet-occurred activities, post-filter at the consumer level.
- **BMA impact → AERA impact linkage is planned but not implemented** (per user memory `project_bma_input.md`). Currently no pipeline effect on transformed_df.

---

## 8. Applications Inventory

Application-level metadata (ARA IDs, names, risk ratings). Loaded only by the HTML report exporter — not by the core transformer pipeline.

- **Input file pattern:** `data/input/all_applications_*.xlsx` (most recent by mtime) — `export_html_report.py:83-98`.
- **Entry point:** `_load_inventory()` at `export_html_report.py:35-44`.
- **Expected columns** (`taxonomy_config.yaml:214-219`):

| Config key | Column |
|---|---|
| `id` | `ARA ID` |
| `name` | `Application Name` |
| `confidence` | `Confidentiality Risk` |
| `availability` | `Availability Risk` |
| `integrity` | `Integrity Risk` |

### Keep rules — all rows loaded as-is.

### Drop / filter rules

| Rule | Reason | Code |
|---|---|---|
| If no matching file found, return empty DataFrame | Inventory is optional | `export_html_report.py:37-39` |
| If `pd.read_excel` raises, return empty DataFrame (silent) | Ibid | `export_html_report.py:41-44` |

### Warnings — none logged at ingest.

### Statuses / methods produced — none. Inventories are display-only.

### Known edge cases

- **Read failure is silent.** A malformed file returns an empty DataFrame with no error message — the HTML report will simply show zero apps. Watch the log; there's nothing to see there. If the inventory should be present but isn't showing, check the filename pattern matches.
- **Not loaded by the core transformer.** The transformer uses tag-based columns on the legacy data file (PRIMARY IT APPLICATIONS, etc.) for flag emission; the inventory file contributes names and risk ratings only to the HTML report view.

---

## 9. Third Parties Inventory

Third-party engagement metadata. Loaded only by the HTML report exporter.

- **Input file pattern:** `data/input/all_thirdparties_*.xlsx` — `export_html_report.py:86`.
- **Entry point:** `_load_inventory()` at `export_html_report.py:35-44`.
- **Expected columns** (`taxonomy_config.yaml:231-234`):

| Config key | Column |
|---|---|
| `id` | `TLM ID` |
| `name` | `Third Party Name (L3)` |
| `overall_risk` | `Overall Risk` |

### Keep / drop rules — same as Applications Inventory.
### Statuses / methods — none.

### Known edge cases — same silent-load behavior as Applications Inventory.

---

## 10. Policies Inventory

Policies / Standards / Procedures catalog. Loaded only by the HTML report exporter.

- **Input file pattern:** `data/input/policystandardprocedure_*.xlsx` — `export_html_report.py:84`.
- **Entry point:** `_load_inventory()` at `export_html_report.py:35-44`.
- **Expected columns** (`taxonomy_config.yaml:221-223`):

| Config key | Column |
|---|---|
| `id` | `PSP ID` |
| `name` | `Policy/Standard/Procedure Name` |

### Keep / drop rules — same as Applications Inventory.
### Statuses / methods — none.

---

## 11. Laws & Regulations Mandates

Mandate catalog with per-entity applicability. Loaded only by the HTML report exporter.

- **Input file pattern:** `data/input/lawsandapplicability_*.xlsx` — `export_html_report.py:85`.
- **Entry point:** `_load_inventory()` at `export_html_report.py:35-44`.
- **Expected columns** (`taxonomy_config.yaml:226-228`):

| Config key | Column |
|---|---|
| `id` | `Applicable Mandates ID` |
| `title` | `Mandate Title` |
| `applicability` | `Applicability to Audit Entity` |

### Keep / drop rules — same as Applications Inventory.
### Statuses / methods — none.

---

## 12. Taxonomy Mapping — the crosswalk

This is where legacy pillars become new-taxonomy L2 rows. All rules live in `config/taxonomy_config.yaml:crosswalk_config` (lines 294-418) and are executed by `risk_taxonomy_transformer/mapping.py:transform_entity()`.

### 12.1 Crosswalk types

Three `mapping_type` values (`taxonomy_config.yaml:281-289`):

| Type | What it means | Code path |
|---|---|---|
| `direct` | Legacy pillar maps 1:1 to one L2. Rating carried forward, high confidence. | `mapping.py:374-381` |
| `multi` | Legacy pillar maps to multiple candidate L2s. Each target has a `relationship`: `primary` (always populated), `secondary` (always populated, flagged for review), `conditional` (only if keyword evidence hits). | `mapping.py:383-433` |
| `overlay` | Country pillar only. Does not create rows — records entries in `overlay_flags` that later merge onto target L2 rows via `pipeline.apply_overlay_flags()`. | `mapping.py:361-371`, `pipeline.py:85-118` |

Direct mappings (`taxonomy_config.yaml:322-350`):
- Funding & Liquidity → Liquidity
- Reputational → Reputation
- Model → Model
- Third Party → Third Party
- Financial Reporting → Financial Reporting
- (External Fraud — pillar no longer carries forward; rationale attached to both External Fraud L3 rows as reference, applicability driven by findings/mappers/AI per Matt 2026-05-01)

Multi mappings:
- Credit → {Consumer and Small Business, Commercial} (both primary)
- Market → {Interest Rate, FX and Price} (both primary)
- Strategic & Business → {Earnings (primary), Capital (secondary)}
- Information Technology → {Technology, Data} (both primary, **no rationale column** → keyword scoring skipped)
- Information Security → {Information and Cyber Security, Data} (both primary, no rationale column)
- Operational → 6 targets (3 primary, 2 secondary, 1 conditional on data keywords)
- Compliance → 4 targets (3 primary, 1 secondary)

Overlay:
- Country → [Prudential, Financial Crimes, Consumer/SMB, Commercial]

### 12.2 Multi-target resolution — evidence scoring

For a multi-mapping pillar with a rationale column (`mapping.py:397-401` → `_resolve_multi_mapping` at `mapping.py:74-188`):

1. For each candidate target L2:
   - Build keyword list: `KEYWORD_MAP[l2_name] + target.conditions` (`mapping.py:125-127`).
   - Scan rationale text (lowercased) for substring hits. Substring match, case-insensitive: `if keyword in text.lower()` (`mapping.py:133`).
   - Scan each sub-risk description tagged to this (entity, pillar) the same way (`mapping.py:139-148`).
   - Sum hit count. 
2. Decision per L2:
   - `score ≥ HIGH_CONFIDENCE_THRESHOLD` (3 by default, `taxonomy_config.yaml:17`) → confidence `high`, method `evidence_match ({relationship})`.
   - `0 < score < 3` → confidence `medium`, method `evidence_match ({relationship})`.
   - `score == 0` → target is **not added** to `targets_to_create`. Later loop (`mapping.py:414-429`) creates an `evaluated_no_evidence` placeholder row for it.
3. If **all** candidate L2s for the pillar scored zero → populate all candidates with `no_evidence_all_candidates` (confidence `low`), leave for team review (`mapping.py:167-186`).

LLM override takes precedence: if an override exists for (entity, pillar, L2), the keyword scoring for that L2 is skipped and the override determines applicability (`mapping.py:100-121`). See §12.5.

### 12.3 Dedup branches — `_deduplicate_transformed_rows` at `mapping.py:195-263`

When multiple legacy pillars map to the same (entity, L2), one row survives. `BLANK_METHODS` is `(evaluated_no_evidence, gap_fill, true_gap_fill, no_evidence_all_candidates)` — `constants.py:45-50`.

| Branch | Existing method | New method | Winner | Annotations | Code |
|---|---|---|---|---|---|
| 1 | In `BLANK_METHODS` | `issue_confirmed` | New (findings) | — | `mapping.py:226-227` |
| 2 | `issue_confirmed` | In `BLANK_METHODS` | Existing (findings) | — | `mapping.py:228-229` |
| 3 | `issue_confirmed` (no rating) | New has `likelihood > 0` | New (rated) | Winner's `sub_risk_evidence` prepended with existing's finding detail; `source_legacy_pillar` annotated `" (also: Findings)"` | `mapping.py:230-237` |
| 4 | Has `likelihood > 0` | `issue_confirmed` (no rating) | Existing (rated) | Existing's `sub_risk_evidence` appended with new's finding detail; `source_legacy_pillar` annotated `" (also: Findings)"` | `mapping.py:238-244` |
| 5 | Has rating | Has higher rating | New | Pillar annotated `" (also: {existing pillar})"`; method gets `(dedup: kept higher)` suffix | `mapping.py:245-250` |
| 6 | Has rating ≥ new's rating | Has rating | Existing | Pillar annotated `" (also: {new pillar})"`; existing method gets `(dedup: kept higher)` suffix if not already present | `mapping.py:251-257` |

Rating comparison uses `likelihood or 0` (`mapping.py:221-222`) — None likelihood is treated as 0.

### 12.4 Status derivation — `_derive_status()` at `enrichment.py:308-329`

Substring check order matters. Checked top-down:

| Method substring (first match wins) | Status |
|---|---|
| `llm_confirmed_na` | Not Applicable |
| `source_not_applicable` | Not Applicable |
| `evaluated_no_evidence` | Assumed N/A — Verify |
| `no_evidence_all_candidates` | Applicability Undetermined |
| `true_gap_fill` or `gap_fill` | No Legacy Source |
| `direct` or `evidence_match` or `llm_override` or `issue_confirmed` or contains `dedup` | Applicable |
| (no match) | Needs Review (fallback — should not occur in production) |

**Important:** The `_dedup` suffix rides along on whatever base method won. `evaluated_no_evidence (dedup: kept higher)` → still "Assumed N/A — Verify" because `evaluated_no_evidence` is checked first. `direct (dedup: kept higher)` → "Applicable".

Full method-to-status table (every method string the pipeline can emit):

| Method string | Produced by | Status | Needs Review? | Confidence |
|---|---|---|---|---|
| `direct` | `mapping.py:378` (direct mapping) | Applicable | False | high |
| `direct (no rationale column)` | `mapping.py:392` (IT/InfoSec/Third Party primary targets) | Applicable | False | high |
| `evidence_match (primary)` | `mapping.py:157` | Applicable | False | high if score ≥3 else medium |
| `evidence_match (secondary)` | `mapping.py:157` | Applicable | False | high/medium |
| `evidence_match (conditional)` | `mapping.py:157` | Applicable | False | high/medium |
| `source_not_applicable` | `mapping.py:337` | Not Applicable | False | high |
| `evaluated_no_evidence` | `mapping.py:427` | Assumed N/A — Verify | False | none |
| `no_evidence_all_candidates` | `mapping.py:174` | Applicability Undetermined | True (row.confidence == "low") | low |
| `true_gap_fill` | `mapping.py:481` | No Legacy Source | False | none |
| `issue_confirmed` | `mapping.py:63` | Applicable | False | high |
| `llm_override` | `mapping.py:110` | Applicable | False | from override row |
| `llm_confirmed_na` | `mapping.py:118` | Not Applicable | False | high |
| `{base} (dedup: kept higher)` | `mapping.py:249, 256` | Same as base | Same as base | Same as base |

### 12.5 LLM override workflow

**Generate prompts:** `python export_llm_prompts.py [path/to/output.xlsx]` → `data/output/llm_prompts/`.

- Reads Audit_Review sheet from the transformer output (`export_llm_prompts.py:92-98`).
- Filters to rows with status in `{"Applicability Undetermined", "Assumed N/A — Verify"}` (`:104`).
- Groups by entity, emits structured prompt files containing entity overview, L2 definition, source rationale, sub-risks, findings, apps, cross-boundary signals (`:122+`).
- System prompt instructs the LLM to respond with CSV rows (no header): `entity_id,source_legacy_pillar,classified_l2,determination,reasoning` (`:25-51`).

**Apply overrides:** save the LLM's CSV response as `data/input/llm_overrides.csv` (or `.xlsx`).

- Loaded by `load_overrides()` at `ingestion.py:173-245`.
- Keyed by `(entity_id, source_legacy_pillar, classified_l2)`. L2 name normalized via `normalize_l2_name()` (`:207-212`).
- `determination` must be `applicable` or `not_applicable` (anything else coerced to `applicable`, `:218-219`).
- Overrides bypass keyword scoring in `_resolve_multi_mapping()`. For each target L2 processed for this (entity, pillar), the code checks `overrides[(entity_id, pillar, l2)]` and, if present, emits one of two methods and `continue`s — no keyword scan runs (`mapping.py:99-121`):
  - `determination == "applicable"` → method `llm_override`, confidence from row.
  - `determination == "not_applicable"` → method `llm_confirmed_na`, confidence `high`.

**Which methods the override replaces:** the override replaces whatever the keyword scan would have produced for that L2 — typically `evidence_match`, `evaluated_no_evidence`, or `no_evidence_all_candidates`. Overrides do **not** apply to `direct` mappings (only multi) because `_resolve_multi_mapping` is only called for multi-type pillars (`mapping.py:397-401`).

### 12.6 Overlay flags (Country pillar)

- During `transform_entity`, overlay pillars produce entries in the `overlays` list (`mapping.py:361-371`) rather than rows.
- After all entities are transformed, `apply_overlay_flags()` groups overlays by (entity_id, target_l2) and merges four columns onto matching transformed rows: `overlay_flag` (bool), `overlay_source`, `overlay_rating`, `overlay_rationale` (`pipeline.py:85-118`).
- Overlay flags never change `Proposed Status` or `Proposed Rating` — they're informational signals shown in the Additional Signals column and Side_by_Side.

### 12.7 True gap fills

After all pillar mappings and dedup, any L2 in `L2_TO_L1` (all 23) that wasn't mapped for this entity gets a placeholder row with method `true_gap_fill`, confidence `none` (`mapping.py:472-482`). With the current crosswalk there should be zero true gaps — every L2 has at least one pillar routing to it. If a true gap appears in output, either the crosswalk was edited or a pillar was missing columns and silently skipped.

### 12.8 Flag emission (not part of mapping, but adjacent)

Four flag functions in `risk_taxonomy_transformer/flags.py` run after mapping and enrichment:

| Function | Output column | Fires when | Code |
|---|---|---|---|
| `flag_control_contradictions` | `control_flag` | Control baseline = Well Controlled + any active finding on this L2; or Moderately Controlled + active finding with severity High/Critical. Active = status in {open, in validation, in sustainability}. | `flags.py:62-130` |
| `flag_application_applicability` | `app_flag` | Entity has non-empty primary/secondary IT or TP columns **and** L2 in `_APP_L2_MAP` (Technology, Data, InfoSec, Third Party). | `flags.py:133-210` |
| `flag_auxiliary_risks` | `aux_flag` | L2 appears in the entity's AXP/AENB Auxiliary Risk Dimensions (after `normalize_l2_name`). | `flags.py:213-272` |
| `flag_cross_boundary_signals` | `cross_boundary_flag` | Keyword from L2 X appears in a pillar that does **not** map to L2 X, with `total_hits >= min_hits_per_pillar` (default 2, from config). Config key `cross_boundary_scanning` at `taxonomy_config.yaml:10-14`. | `flags.py:319-460` |

All four are informational only — they never change Proposed Status or Proposed Rating.

---

## Quick lookups

### "Why doesn't this BMA show up?"

1. Is it in a file matching `bm_activities_*.xlsx` or `.csv` in `data/input/`? → `__main__.py:318-324`.
2. Does it have an Activity Instance ID and a Planned Instance Completion Date? → Required columns, `ingestion.py:610-613`.
3. Is the Planned Instance Completion Date ≥ 2025-07-01 or blank? Earlier dates are dropped. → `ingestion.py:624-632`.
4. Is the entity ID blank? It's kept but only visible in the source tab, won't link to any entity view. → `ingestion.py:616-621`.

### "Why is this finding missing from Impact of Issues?"

1. Finding Approval Status = "Approved"? → `ingestion.py:283-287`.
2. Severity populated? → `ingestion.py:290-294`.
3. L2 Risk column normalizes to a canonical L2? Unmappable values dropped. → `ingestion.py:303-333`.
4. Finding Status in {open, in validation, in sustainability}? Closed/cancelled findings appear in Source - Findings but not Impact of Issues. → `enrichment.py:149-153`.

### "Why does this ORE not appear in the pipeline?"

1. Is the ORE's Event Status closed? Dropped at the mapper stage. → `ore_mapper.py:129-138`.
2. Does it have Event ID + (Title or Description)? → `ore_mapper.py:140-143`.
3. Does it have Audit Entity ID? → `ore_mapper.py:146-151`.
4. Is its Mapping Status "Suggested Match" or "Needs Review"? "No Match" is excluded. Filter lives in `taxonomy_config.yaml:ore_confidence_filter` and `ingestion.py:383-387`.

### "What statuses can this source produce?"

| Source | Produces status? |
|---|---|
| Legacy Risk Data | Yes — all 5 statuses possible depending on rating + mapping_type + keyword evidence |
| Sub-Risk Descriptions | No — evidence only |
| IAG Findings | Yes — `issue_confirmed` → Applicable |
| OREs | No — contributes to Impact of Issues only |
| PRSA Issues | No — view-only |
| GRA RAPs | No — view-only |
| BM Activities | No — view-only |
| Applications / Third Parties / Policies / Laws Inventories | No — view-only (HTML report) |
| LLM overrides | Yes — `llm_override` (Applicable) or `llm_confirmed_na` (Not Applicable) |
| RCO overrides | Yes — applied at Risk Owner Review stage, not transformed_df (not covered here; see `review_builders.py`) |
