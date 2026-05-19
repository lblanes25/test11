# LUminate — Validation

Merges the former Test Plan, Sample Reconciliation Procedure, and UAT &
Independent Review Sign-Off. These three feed Governance §Approval. Rules under
test: `Methodology.md` Part 4. Crosswalk under test: `Crosswalk_v1.0.md`.

**Status:** Parts 1–3 are unexecuted templates. Their presence is not evidence
the controls happened — execution + signatures are the gating governance items.
**A live pilot is running** — Part 4 converts it into the Part 2 + Part 3
evidence rather than running parallel to it.

---

# Part 1 — Test Plan

**Purpose:** Repeatable verification that the rules in `Methodology.md` Part 4
produce the expected status/method, including documented edge cases. Built from
the "Known edge cases" sections of `../config/methodology_reference.md`.
**Execution:** route to the `validation-qa` agent. Test-data generators in
`tests/`; `tests/test_prsa_provenance.py` is the only current assertion test.

## 1.1 Rule-path matrix

Each: stage minimal input, run `python -m risk_taxonomy_transformer`, assert
(status, method) on the target (entity, L2) row.

| TC | Input condition | Expected status | Expected method | Rule |
|---|---|---|---|---|
| T-01 | Direct pillar, numeric rating | Applicable | `direct` | A3 |
| T-02 | Direct pillar rated N/A | Not Applicable | `source_not_applicable` | A1 |
| T-03 | IT pillar, numeric rating | Applicable | `direct (no rationale column)` (Tech & Data) | A2 |
| T-04 | Multi pillar, ≥3 keyword hits one L2 | Applicable | `evidence_match (...)` conf=high | A4 |
| T-05 | Multi pillar, 1–2 hits | Applicable | `evidence_match (...)` conf=medium | A4 |
| T-06 | Multi pillar, sibling L2 hit, this L2 zero | Assumed N/A — Verify | `evaluated_no_evidence` | A4 |
| T-07 | Multi pillar, zero hits all candidates | Applicability Undetermined | `no_evidence_all_candidates` | A5 |
| T-08 | Open approved finding tagged to L2 | Applicable | `issue_confirmed` | A6 |
| T-09 | LLM override = not_applicable | Not Applicable | `llm_confirmed_na` | A7 |
| T-10 | LLM override = applicable but open finding exists | Applicable | finding wins (`issue_confirmed`) | A7 |
| T-11 | L2 with no pillar route | No Legacy Source | `true_gap_fill` | A8 |
| T-12 | Reputational / Country pillar present | no row for those | — | A9 |
| T-13 | Entity with all 23 L2 → row-count invariant | exactly 23 rows | — | invariant |

## 1.2 Edge cases

| TC | Edge case | Expected |
|---|---|---|
| E-01 | External Fraud, generic-only fraud rationale | Applicability Undetermined; **no rating** (B2) |
| E-02 | Multi-L2 finding cell `"Data\nPrivacy"` | Two `issue_confirmed` rows |
| E-03 | Dedup: `issue_confirmed` vs rated direct, same (entity,L2) | Rated wins; finding detail appended; pillar "(also: Findings)" |
| E-04 | Dedup: two rated pillars, same (entity,L2) | Higher rating kept; `(dedup: kept higher)`; base status preserved |
| E-05 | Finding status `"OPEN "` trailing space | Treated active (strip+lower in comparison) |
| E-06 | Closed finding | In Source - Findings; NOT in Impact of Issues / control contradiction |
| E-07 | ORE with multiple mapped L2s | Row fan-out in Source - OREs (won't reconcile 1:1) — expected |
| E-08 | Key risk tagged to 3 L1s | Scored once per pillar (intended) |
| E-09 | Pillar columns absent | Warning logged; no rows for that pillar; entity still 23 via gap-fill |
| E-10 | Sub-risk L1 not in crosswalk | Silently skipped; WARNING "Sub-risk L1s NOT in crosswalk" |
| E-11 | Unmappable finding L2 ("Fair Lending / Regulation B") | Captured to Unmapped Findings; no applicability confirmed |

## 1.3 Failure-mode tests

| TC | Condition | Expected | Note |
|---|---|---|---|
| F-01 | Required `legacy_risk_data_*` missing | Run raises / non-zero exit | |
| F-02 | Renamed source column | Currently silent for inventories — `validate_inputs.py` must catch | Methodology §2.7 |
| F-03 | Inventory file malformed | HTML zero, no error | Assert `validate_inputs.py` flags it |
| F-04 | spaCy model `en_core_web_lg` not installed | Mapper fails; `refresh.py` warns, continues | Verify warning surfaces |
| F-05 | LLM prompt evidence completeness | Findings/sub-risk evidence reaches prompt — `export_llm_prompts.py:189-190` reads `Source - Findings`/`Source - Key Risks` | **Expected PASS** (stale-sheet defect fixed 2026-05-02). Regression guard vs `export.py` sheet renames. |

## 1.4 Pre-run gate

`python validate_inputs.py` exits 0 (manifest complete + column alignment).
Non-zero = do not run. See Operations §Refresh SOP.

## 1.5 Exit criteria

- All T-01..T-13 and E-01..E-11 pass.
- F-05 passes (regression guard).
- Results dated and attached to Part 3 below.

---

# Part 2 — Sample Reconciliation Procedure

**Why this matters most:** LUminate produces the migration decisions that seed
the permanent AERA state. This is the evidence its output was checked against a
human-derived baseline. Highest-priority open action. Must run under canonical
`en_core_web_lg` (the model that produced the decisions).

## 2.1 Scope

Pick **2 entities** that together exercise: ≥1 direct mapping, one multi-target
with keyword evidence, one Applicability Undetermined, one finding-confirmed
row, one N/A pillar, and (if available) one LLM-override row. Prefer entities
the reconciler knows well.

## 2.2 Procedure

1. **Freeze inputs.** Snapshot exact `data/input/` files + run timestamp + git
   commit + `taxonomy_config.yaml`. Record below.
2. **Run LUminate** (Operations §Refresh SOP). Record output filenames + the
   provenance block (must show `en_core_web_lg`).
3. **Manual derivation (blind).** Without looking at LUminate output, the
   reviewer derives, per the 23 L2 per entity: expected status, expected rating
   (if direct), rationale — using only legacy data, findings, the crosswalk
   (`Crosswalk_v1.0.md`) and rule set (`Methodology.md` Part 4). **Note the
   active S&B→Capital rule (Option C, pending Matt):** expect Capital =
   `Applicable` with **blank** Legacy Risk Rating, not the carried S&B rating —
   derive against this so a correct row isn't logged as a variance. If Matt
   directs A/B, re-derive.
4. **Compare** row by row; log every differing cell.
5. **Explain every variance** — categorize: (a) tool correct, manual wrong;
   (b) tool wrong (defect — log); (c) both defensible (judgment — expected);
   (d) documented edge case.
6. **Sign and attach** to Part 3 and the governance package.

## 2.3 Run metadata

| Field | Value |
|---|---|
| Run timestamp | `[ ]` |
| Git commit | `[ ]` |
| spaCy model + version (must be canonical `en_core_web_lg`; from output provenance) | `[ ]` |
| Source-system extract dates (as-of per Archer extract) | `[ ]` |
| Input snapshot location | `[ ]` |
| Output workbook | `[ ]` |
| Reconciler (not the tool author) | `[ ]` |

## 2.4 Reconciliation log

| Entity | L2 | Tool status | Tool rating | Manual status | Manual rating | Match? | Variance category | Explanation |
|---|---|---|---|---|---|---|---|---|
| | | | | | | | | |

## 2.5 Result summary

| Metric | Value |
|---|---|
| Rows compared | `[ ]` |
| Exact matches | `[ ]` |
| Variances — tool defect | `[ ]` (target 0; any → defect ticket) |
| Variances — manual error | `[ ]` |
| Variances — both defensible (judgment) | `[ ]` |
| Variances — documented edge case | `[ ]` |
| **All variances explained?** | `[Y/N]` |

## 2.6 Sign-off

| Role | Name | Statement | Signature | Date |
|---|---|---|---|---|
| Reconciler | `[CONFIRM — not the tool author]` | "Performed independent manual derivation; all variances explained." | | |
| EUC owner | `[CONFIRM]` | "Defects (if any) logged and dispositioned." | | |

---

# Part 3 — UAT & Independent Review Sign-Off

Covers the **whole tool**, not only the LLM step. The LLM-step peer review is
`../LLM_REVIEW_RESPONSES.md` (template `../LLM_REVIEW_TEMPLATE.md`) — attach it
but it is not the whole-tool UAT and is currently self-authored, needing an
independent signer.

## 3.1 Participants

| Role | Name | Independent of tool author? |
|---|---|---|
| Pilot audit leader (UAT) | `[CONFIRM]` | Yes — required |
| Independent reviewer (design/output) | `[CONFIRM]` | Yes — required |
| Tool author | `[CONFIRM — Lurian]` | n/a |

## 3.2 Pilot UAT (audit leader, real portfolio)

| # | Check | Result | Evidence |
|---|---|---|---|
| U-1 | Workbook opens, entity filter works, 23 L2 rows per entity | `[ ]` | |
| U-2 | Decision Basis explains *why* each row landed where it did | `[ ]` | |
| U-3 | Proposed statuses reasonable on a known portfolio | `[ ]` | |
| U-4 | Rating blank on non-direct mappings | `[ ]` | |
| U-5 | Impact of Issues shows expected findings/OREs/PRSA/RAP/BMA | `[ ]` | |
| U-6 | Signal flags informational, don't override status | `[ ]` | |
| U-7 | Disclaimer / methodology + provenance banner visible in output | `[ ]` | |
| U-8 | Operations §User Guide followable without the author | `[ ]` | |
| U-9 | Time per entity vs. manual process | `[ ]` qualitative |

## 3.3 Independent review

| # | Check | Result | Evidence |
|---|---|---|---|
| R-1 | Crosswalk (`Crosswalk_v1.0.md`) reviewed against methodology | `[ ]` | |
| R-2 | Sample of output independently spot-checked | `[ ]` | ref Part 2 |
| R-3 | Test plan (Part 1) executed; results reviewed | `[ ]` | |
| R-4 | Known limitations (Methodology §2.7, §Part 5) understood & accepted | `[ ]` | |
| R-5 | LLM-step review (`../LLM_REVIEW_RESPONSES.md`) independently countersigned | `[ ]` | |

## 3.4 Defects / follow-ups

| ID | Description | Severity | Disposition |
|---|---|---|---|
| | | | |

## 3.5 Sign-off

| Role | Name | Outcome (Pass / Pass w/ conditions / Fail) | Signature | Date |
|---|---|---|---|---|
| Pilot audit leader | `[CONFIRM]` | | | |
| Independent reviewer | `[CONFIRM]` | | | |
| EUC owner | `[CONFIRM]` | | | |

UAT is a **Yes/No gate before broader rollout** (`../PHASE2_SCOPE.md:82`).

---

# Part 4 — Pilot-as-Evidence Capture

A pilot is running now on canonical `en_core_web_lg` output. The pilot is
already generating the raw material for Parts 2 and 3 — this part captures it
in an inspectable form instead of letting it run parallel and uncaptured.

**Why this is needed:** pilot reviewers are *anchored to the proposal* — they
react to LUminate's suggestion, they don't derive the answer blind. So the
pilot alone does not evidence accuracy (it *is* the over-reliance failure mode
if a proposal is wrong-but-plausible — Methodology §Part 5). Capturing
overrides + one blind derivation closes that.

## 4.1 Override log (capture for the whole pilot)

Every time a pilot reviewer overrides a LUminate proposal, log it. Each
override is a reconciliation-grade data point — do not discard it.

| Entity | L2 | Tool proposal (status/rating) | Reviewer decision | Reviewer reason | Category: tool-wrong / judgment / edge-case | Reviewer | Date |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

Roll up into the Part 2.5 result summary. A material rate of **tool-wrong**
overrides is a defect signal — log in Part 3.4 and triage before broader
rollout; it does not get silently absorbed as "reviewer judgment."

## 4.2 Blind derivation (one pilot team — converts pilot → reconciliation)

One pilot team (or an independent reviewer) does Part 2's blind derivation on
**1–2 of their own entities, before looking at LUminate's output for those
entities**. Then run Part 2's compare/explain/sign. This is best done in the
in-person working session. Confirm the output provenance block shows
`en_core_web_lg` before comparing (Part 2.3).

- Pilot team selected: `[CONFIRM]`
- In-person session date: `[CONFIRM]`
- Entities chosen (cover ≥1 direct, 1 multi w/ keyword, 1 Undetermined, 1 finding-confirmed, 1 N/A pillar): `[CONFIRM]`

## 4.3 Sign-off hooks

- Blind-derivation reviewer signs **Part 2.6** (this is the sample reconciliation).
- Pilot leaders sign **Part 3.5** (U-1..U-9 in substance — record + sign).
- Independent reviewer countersigns **Part 3.3 R-5** (the `../LLM_REVIEW_RESPONSES.md` LLM-step review, currently self-authored).

## 4.4 Result summary (pilot evidence)

| Metric | Value |
|---|---|
| Pilot entities reviewed | `[ ]` |
| Total overrides logged | `[ ]` |
| Overrides categorized tool-wrong | `[ ]` (any → Part 3.4 defect triage) |
| Overrides categorized judgment / edge-case | `[ ]` |
| Blind-derivation entities reconciled (Part 2) | `[ ]` |
| All Part 2 variances explained? | `[Y/N]` |
