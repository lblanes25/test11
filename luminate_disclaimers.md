# LUminate — Disclaimers, Filters, and Out-of-Scope Caveats

**Audience:** Leadership / governance.
**Purpose:** A single tracked place for "what LUminate is and isn't accountable for" — by data source. Useful in audit committee, SVP, RCO conversations, and methodology defenses.
**Framing principle:** LUminate **synthesizes and presents** what's already in upstream sources. It does **not** create attribution or fix data quality. When upstream data is missing, malformed, or unmapped, LUminate surfaces that fact rather than inventing a fill-in.
**Status:** Working artifact. Iterate as more disclaimers come up.

---

## Universal disclaimers (apply across all sources)

- **LUminate cannot fix upstream data.** If a finding, ORE, PRSA, RAP, or BMA case isn't tagged to an audit entity in its source system, LUminate cannot show it on that entity's view. Mapping is upstream's responsibility; LUminate displays what exists.
- **LUminate cannot create attribution that doesn't exist.** OREs, PRSAs, mandates, and inventory items reach an AE only if the source system already establishes the AE linkage. LUminate does not infer, guess, or invent the linkage.
- **Unmappable items are surfaced, not silently dropped.** Where an item has missing or invalid metadata (no L2, unmappable L2, blank AE), LUminate captures it per-entity and exposes it in the `Unmapped Findings` column on Audit_Review (the column name is broader than its label — it covers IAG findings, ORE mapper rows, PRSA mapper rows, and RAP mapper rows whose L2 doesn't normalize). Reviewers can see exactly which items got dropped from their AE's signal flow.
- **Items with no AE attribution upstream are captured separately.** When a source system item has no AE assigned, LUminate has nothing to attach it to in a per-AE view. These items now surface in the `Upstream Tagging Gaps` tab in the Excel workbook so reviewers can see what dropped out and follow up with the responsible team to fix the upstream tagging gap.
- **LUminate's outputs are point-in-time.** The HTML report and Excel workbook are frozen artifacts representing the inputs at the time the run executed. They do not auto-refresh and should be cited with the run timestamp.
- **LUminate is not a system of record.** Final risk assessment decisions must be entered and documented in Optro. LUminate's role is to surface signals and decision-support context for the audit team.
- **AI-assisted determinations are advisory.** Where LLM overrides or AI-proposed applicability appear, the audit team is the final decision-maker. AI outputs may shift between runs (model variance) and are documented as such.
- **All NLP mapper output is presented as "Needs Review" by design — LUminate does not assert a confident match.** The mappers (ORE legacy, ORE IRM, PRSA, GRA RAPs) score source items against the canonical L2 taxonomy text — including L3 and L4 definitions where present — and propose a candidate L2 the reviewer must confirm or correct. The tool deliberately makes no positive-confidence claim: NLP similarity can be wrong (generic wording, or L2 definitions that read similarly upstream), a risk reinforced by how textually similar the upstream L2 definitions are. Items below the similarity floor are excluded (No Match). LUminate cannot rewrite the taxonomy — the definitions are upstream artifacts owned by the enterprise taxonomy.

---

## legacy_risk_data

**What it is:** The current-state input from the audit team's prior assessments (legacy taxonomy). Includes ratings, control assessments, rationale, applications/TPs/models tagged to each AE, and supplementary risk dimensions.

- **Rating carryforward only on 1:1 direct mappings.** Where a legacy pillar maps to multiple new L2s (multi-mapping), no rating carries forward. Reviewers must actively rate. (Per SVP decision 2026-04-07: legacy ratings were scoped to a different taxonomy and shouldn't be assumed to apply.)
- **Applications, third parties, and models lists are surfaced verbatim.** Sentinels like "N/A", "Not Applicable", "—" are filtered out for chip rendering, but the underlying cell content is preserved in the workbook.
- **Auxiliary and core risk dimensions drive applicability suggestions, not determinations.** The "Additional Signals" column flags inventory presence as a *suggestion* that a risk may be applicable. Reviewers decide.
- **PRSA tagging on AEs is not validated by LUminate.** If a PRSA listed in the legacy `PRSA` column doesn't actually exist in PRSA Archer, LUminate has no way to detect that.

---

## PRSA Frankenstein build (`build_prsa_frankenstein.py` → `prsa_report_*.xlsx`)

**What it is:** An automation of the manual workbook-stitching process: joins three source files (legacy_risk_data + PRSA_IRM_Archer + PRSA_Controls_Map) into a single per-AE PRSA report.

- **Output is issue-driven, not PRSA-driven.** One row per (AE, Issue, Control). A PRSA tagged to an AE in legacy but with **no issues in Archer** does not generate a row. The full per-AE PRSA list is preserved in the `All PRSAs Tagged to AE` column on every row.
- **Non-PG, no-control issues are surfaced, not silently dropped.** Archer issues with blank `Control ID (PRSA)` and no PG flag are excluded from the per-AE PRSA view — including RCSA-only issues — and now surface in the `Upstream Tagging Gaps` tab with `Drop Reason="No PRSA control"` (previously INFO-log only).
- **PG-flagged unmapped issues are kept.** Archer issues with blank `Control ID (PRSA)` but flagged with `#PG` / `PG` prefix in Issue Description are retained as a special row type with blank AE / Control / PRSA fields, only the Issue block populated. These appear as PG Gap pills downstream.
- **Orphan Control IDs are dropped.** Archer Control IDs with no matching row in the Controls Map are excluded. Logged as orphan list.
- **Orphan Process IDs are dropped.** Process IDs in the Controls Map with no matching PRSA in legacy are excluded. Logged as orphan list.
- **Cross-AE PRSAs.** A PRSA tagged to multiple AEs in legacy generates rows under each AE — visible in the per-AE views as well as in the orphan log if applicable.

---

## PRSA report ingestion + L2 mapper

**What it is:** Consumption of the Frankenstein output (`prsa_report_*.xlsx`) plus the AI-driven L2 mapper output (`prsa_mapping_*.xlsx`) to drive the Impact of Issues column and the PG Gap pill type.

- **L2 attribution is mapper-driven by default; source-tagged L2 wins when valid (Track B).** If `Risk Level 2` is populated in the source row and normalizes to a current taxonomy L2, that wins; otherwise the mapper output is used. Provenance is surfaced via `L2 Source` column.
- **Mapper outputs are advisory, not authoritative.** The PRSA mapper uses similarity scoring on issue text; every mapped row surfaces as "Needs Review" for auditor judgment — no positive-confidence band is asserted.
- **PRSA closed-status filter applies in control-effectiveness rollup.** Configured via `prsa_closed_statuses` in YAML; closed PRSAs do not contribute to the live impact summary.
- **PRSA mapper rows with blank AE are skipped from per-AE pill listings.** PG-flagged unmapped issues surface separately via the `Source - PG Gaps` tab. Non-PG-flagged blank-AE rows are simply absent from per-AE views — they shouldn't have been mapper input without an AE in the first place.
- **PRSA mapper rows with unmappable L2 are surfaced.** Captured per-entity in the `Unmapped Findings` column on Audit_Review.
- **PRSAs not in the Frankenstein output never reach the mapper.** Per the Frankenstein disclaimers: PRSAs tagged to AEs but with no issues never produce rows in the report, so they have nothing for the L2 mapper to score against.
- **PG Gap pill is independent of mapper output.** Detected from the `#PG` / `PG` prefix on Issue Description (case-sensitive). Does not depend on the AI mapper.

---

## ORE legacy (`ore_mapping_*.xlsx`)

**What it is:** Operational Risk Events from the legacy ORE source, attributed to AEs and L2s via the ORE mapper.

- **Closed-status filter applies.** OREs with `Event Status` in the configured `ore_closed_statuses` set are filtered out of the control-effectiveness rollup. Configured in YAML; can opt out per call site.
- **Mapping is mapper-driven.** ORE attribution to L2 risks comes from the NLP mapper output, which surfaces uniformly as "Needs Review" in the workbook (no confidence band asserted — confirm the L2 attribution).
- **AE attribution comes from the ORE source's own AE field.** LUminate does not infer AE linkage — if an ORE isn't tagged to an AE upstream, it does not appear in any AE's view. Upstream tagging gap, not LUminate's call to make.
- **OREs whose mapper L2 doesn't normalize are surfaced, not dropped silently.** Captured per-entity and exposed in the `Unmapped Findings` column on Audit_Review (column name covers all unmapped mapper items — OREs, PRSAs, RAPs — not just IAG findings).

---

## ORE IRM (`ORE_IRM_*.xlsx` + `ore_irm_mapping_*.xlsx`)

**What it is:** OREs from the IRM Archer system. Bridged to AEs via the new `IRM ORE ID` column on legacy_risk_data.

- **No closed-status filter.** Per the ORE IRM banner: there is no reliable per-event status field on this source today, so all events are shown regardless of resolution. Reviewers must confirm open status before treating any IRM ORE as evidence in Impact of Issues.
- **AE attribution depends on the `IRM ORE ID` column on legacy_risk_data.** If an IRM ORE isn't listed in any AE's `IRM ORE ID` cell, LUminate cannot attribute it to that AE — even if other IRM evidence exists.
- **IRM OREs in the source file but missing from every AE's `IRM ORE ID` cell are invisible.** They exist in the input data but LUminate has no AE to attach them to. Upstream attribution gap; LUminate cannot infer.
- **IRM OREs whose mapper L2 doesn't normalize are surfaced.** Captured per-entity in the `Unmapped Findings` column on Audit_Review, same flow as legacy ORE / PRSA / RAP unmapped L2s.
- **L2 attribution: source-tagged wins, mapper fills gaps.** Same Track B logic as PRSA. Provenance shown in `L2 Source`.
- **Legacy Event ID is carried but not used.** The link between an IRM ORE and its corresponding legacy ORE (when one exists) is preserved as a column but does not affect the dedup or rollup logic. Cross-source dedup is out of scope today.

---

## Issues / Findings (IAG findings, `findings_data_*.xlsx`)

**What it is:** Open audit findings from the IAG system. Used both for confirming applicability (`issue_confirmed`) and for the Impact of Issues column.

- **Approved-only filter.** Only rows with `Finding Approval Status == "Approved"` are loaded. Drafts and in-review findings do not confirm applicability. Filter count logged at INFO level.
- **Blank-severity findings excluded.** Findings with blank severity are dropped — likely incomplete, shouldn't drive applicability.
- **L2 attribution comes from the finding's own `Risk Dimension Categories` field.** Newline-delimited multi-L2 cells are exploded; unmappable L2 names are dropped from the main applicability flow.
- **Findings without a mappable L2 are surfaced separately, not silently dropped.** Findings with no L2 listed, or with an L2 that doesn't normalize to the canonical taxonomy, are captured per-entity in the `Unmapped Findings` column on Audit_Review. They don't confirm applicability of any specific L2 (because there's no L2 to confirm), but reviewers can see exactly which findings got dropped on their AE so they can chase down the upstream tagging gap.
- **Findings without an AE are invisible.** A finding in the IAG system with no audit entity assigned never reaches LUminate's per-AE view at all. Upstream tagging gap, not a LUminate problem to fix.
- **Issue confirmation is a high-confidence signal but not a final determination.** An open finding tagged to an L2 confirms applicability; the audit team still owns the rating call.

---

## BMA — Business Monitoring Activities (`bm_activities_*.xlsx`)

**What it is:** Open BMA cases that may have AERA impact, displayed alongside IAG findings, OREs, and PRSA control problems.

- **Upstream Archer-report filter applies.** The source file is pre-filtered at the **Archer report level** to only include cases where the audit team has flagged: (a) the activity had an AERA-relevant impact, and (b) the recommended action is "Audit Entity Risk Assessment (AERA) Update". LUminate trusts the upstream filter and does not re-validate it.
- **Date cutoff applies.** Only cases with `Planned Completion Date >= cutoff` (default 2025-07-01, configurable) are included. Older cases are filtered out as out-of-scope for the current AERA cycle.
- **NaT (no completion date) cases are kept.** Defensive: cases without a planned date pass the filter rather than being silently dropped.
- **Blank entity IDs are kept with a warning.** BMA rows missing entity attribution are not silently dropped; they're logged at WARNING level so the audit team can chase them down. They surface in the `Upstream Tagging Gaps` tab.
- **No programmatic L2 attribution.** Per memory note (2026-05-02 cancellation): BMA cases are not programmatically mapped to L2 risks. The audit team makes that determination per their judgment. LUminate displays BMA cases as a separate signal alongside L2-attributed sources.

---

## GRA RAPs (`gra_raps_*.xlsx` + `rap_mapping_*.xlsx`)

**What it is:** Regulatory findings (RAPs from GRA), attributed to L2s via the RAP mapper.

- **Blank-RAP-ID rows dropped.** Entity-level rows with no RAP ID are excluded — these are placeholder rows, not actual findings.
- **Mapping is mapper-driven.** Same confidence-band logic as PRSA / ORE mappers.
- **RAP mapper rows with unmappable L2 are surfaced.** Captured per-entity in the `Unmapped Findings` column on Audit_Review (same flow as findings, OREs, PRSAs).
- **RAPs without an AE in the source are invisible.** Same upstream-attribution caveat as OREs and findings — LUminate cannot place a RAP under an AE if upstream didn't.
- **RAP Status field carried verbatim.** LUminate does not interpret RAP status; the field is displayed as-is for reviewer judgment.

---

## LLM overrides (`llm_overrides*.xlsx`)

**What it is:** AI-classified applicability determinations submitted as a separate file. Pre-empts keyword scoring on `(entity_id, source_legacy_pillar, classified_l2)` matches.

- **AI variance is real.** Outputs may shift between runs even on identical inputs. The override file is a snapshot; reviewers see the AI's call layered with keyword evidence in Decision Basis.
- **AI overrides do not trump open findings.** If an open finding tagged to the L2 exists, `issue_confirmed` wins.
- **Invalid L2 names skipped + logged.** Override rows with an L2 that doesn't normalize to the canonical taxonomy are skipped at ingestion with a WARNING.
- **Determination strictly `applicable` / `not_applicable`.** Other values rejected at ingestion.

---

## RCO overrides (`rco_overrides_*.xlsx`)

**What it is:** Per-row Risk Category Owner overrides on `(entity_id, l2_risk)` applicability and rating.

- **Narrow scope today.** Per `data_flow.md` §5.16: RCO overrides currently affect ONLY the `Risk_Owner_Review` tab (sibling-context overlay + peer-rating Counter). They do **not** change Audit_Review Status / Proposed Rating, do not appear in HTML, do not propagate to Side_by_Side, do not affect Impact of Issues.
- **Status values are strict.** Must be one of `Confirmed Applicable` / `Confirmed Not Applicable` / `Escalate`. Any other value → row skipped with WARNING.
- **`Escalate` has no workflow.** Today it surfaces as a status label only; no escalation queue or notification.
- **No Source tab.** The raw `rco_overrides_*.xlsx` does not get written to any sheet in the workbook. To audit what an RCO submitted, open the input file directly.
- **Rule-shaped directives not yet supported.** "Universe-wide" / "portfolio-concentrated" claims (e.g., "every AE applicable for HC") require manually expanding to per-row entries today. Designed enhancement captured in `rco_directive_override_design.md`.

---

## Optro export (`optro_export_*.xlsx`)

**What it is:** Audit team's confirmed L2 assessments exported from Optro, ingested as overrides.

- **Risk Rating doubles as applicability.** Low / Medium / High / Critical → applicable. N/A / blank → not applicable.
- **Coverage is per-entity.** Tracked separately so downstream consumers can enforce all-or-nothing per entity.
- **Treated as authoritative for the L2s it covers.** The audit team's confirmed assessment in Optro takes precedence over LUminate's keyword-scoring or AI proposals where present.
- **Scope of integration is still being verified.** Recently wired but full propagation behavior across Audit_Review / HTML needs review before relied upon for governance discussions. *(Action item: re-read Optro integration end-to-end.)*

---

## Inventory files

**What they are:** Standalone catalog files for applications, third parties, models, policies, and laws/mandates. Loaded primarily by the HTML report exporter.

- **Inventory is filtered to IDs referenced in legacy.** Apps / TPs / Models / Mandates not tagged to any AE in legacy_risk_data are not displayed (keeps the per-AE drill-downs focused).
- **Models have no key-inventory concept.** Apps and TPs distinguish "key" via the key risk file; models do not. Per memory, this is intentional pending a separate decision.
- **Inventory presence drives applicability *suggestions* only.** Apps in IT/Data/InfoSec/3P columns produce "consider this risk may be applicable" flags; they do not force an Applicable determination.
- **Inverse-direction not flagged today.** "AE has Technology applicable but no apps mapped" is a real disconnect that LUminate does not currently surface. (Phase 2 work — see LUminate vs Optro doc.)
- **Volume-by-rating disconnect not surfaced.** "AE has 27 mandates but Compliance rated Low" / "50 apps rated Critical for Availability but Technology rated Low" — these aggregate comparisons are not produced today.

---

## Mapping / applicability layer (general)

**What it is:** The core logic that produces a row per (AE, L2) with applicability status, method, evidence, rating, and decision basis.

- **Keyword lists were vetted by RCOs.** RCOs for each risk participated in vetting the keywords used by LUminate to score rationale text and key risk descriptions against L2 risks.
- **No-evidence fallback populates all candidates.** Where the keyword scoring finds no evidence for any L2 in a multi-mapping pillar, all candidate L2s are populated as low-confidence Undetermined. The team decides; LUminate does not pick one for them.
- **Source N/A → all candidates Not Applicable.** Where the legacy pillar is rated N/A, all candidate L2s in the multi-mapping receive `source_not_applicable`. Filer-driven, not LUminate's call.
- **Applicability suggestions vs. determinations.** Signal flags (app_flag, tp_flag, model_flag, aux_flag, mandate_flag, control_flag) surface considerations for review; they do not change the row's `Status`.
- **Multi-L1 explosion duplicates keyword contributions.** A key risk tagged to multiple L1s gets scored once per pillar. Intended behavior: the key risk genuinely informs each pillar's applicability.
- **External Fraud rating not carried forward.** Per memory (2026-05-01 Matt decision): rationale attached to both External Fraud L3 rows as reference; applicability driven by findings/mappers/AI.

---

## What LUminate explicitly does not do

- Does not assign final ratings under the new taxonomy (Pillar 2 — pending RCO rating guidance from May 15 templates).
- Does not enforce completeness of Optro Entity Risk Assessments (does the AE in Optro have all 24 L2s? — outside LUminate's scope today).
- Does not produce real-time data feeds; refreshes are manual.
- Does not produce cross-AE roll-up or matrix/heatmap views; per-AE drill-downs only.
- Does not detect inventory-vs-RC disconnects in the inverse direction or by aggregate volume.
- Does not validate upstream data quality (typos in AE IDs, missing PRSA tags, malformed multi-line cells beyond what defensive parsing catches).
- Does not propagate RCO overrides into Audit_Review / HTML today (§5.16 tabled item).
- Does not programmatically attribute BMA cases to L2 risks (audit team's call).
- Does not dedup OREs across legacy and IRM sources (cross-source overlap not detected).

---

## Tracking new disclaimers

When something comes up that's worth tracking — a filter rule, an exclusion, an "out of our control" caveat, a methodology limit — add it to this doc under the relevant data source. Format:

> **<short label>.** <one-paragraph plain-language statement. Cite the source code path or memory note in parentheses when relevant.>

Don't bury the disclaimer; lead with the rule, then explain. Leadership reads scannable bullets, not paragraphs.
