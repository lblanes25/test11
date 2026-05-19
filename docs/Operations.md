# LUminate — Operations

Merges the former User Guide, Refresh SOP, and Runbook. Methodology/design:
`Methodology.md`. Validation: `Validation.md`. Governance/change control:
`Governance.md`.

---

# Part 1 — User Guide

**Audience:** Audit leaders and core audit teams. Detailed reviewer workflow:
`../config/risk_assessment_workflow.md`; guided walkthrough:
`../config/walkthrough_script.md`; e-learning transcript:
`../luminate_training_description.md`.

## 1.1 What LUminate is

A decision-support tool. Per (audit entity × L2 risk) it proposes an
applicability status with a Decision Basis and consolidated control-issue
evidence. **You decide.** Not a system of record — final assessments go in
**Optro**.

## 1.2 Getting the workbook

1. Download the latest workbook / HTML report from SharePoint
   `[CONFIRM: SharePoint URL]`.
2. Outputs are **point-in-time**, timestamped (e.g.
   `risk_taxonomy_report_<MMDDYYYYHHMM>.html`). Cite the timestamp; it does not
   auto-refresh.
3. Use the most recent timestamp unless told otherwise. The output's
   methodology banner shows the run provenance (tool commit, spaCy model +
   version) — confirm it before relying on an older artifact.

## 1.3 Workbook tabs

| Tab | Use |
|---|---|
| Dashboard | Portfolio summary: Tool Proposals breakdown, rows needing judgment, signal counts |
| Audit_Review | Main working tab — one row per (entity × L2): Status, Decision Basis, Additional Signals, Impact of Issues |
| Side_by_Side | Diagnostic columns (method/confidence) hidden from Audit_Review |
| Source - * | Raw evidence per source (Findings, OREs, PRSA, GRA RAPs, BMA, …) |
| Upstream Tagging Gaps | Items with no AE attribution upstream — chase the responsible team |
| Methodology / LUminate Methodology | Per-source scope, attribution, disclaimers, run provenance |

## 1.4 Statuses and what to do

| Status | Meaning | Your action |
|---|---|---|
| Applicable | Evidence supports it (finding / keyword / direct map) | Spot-check Decision Basis; confirm or override |
| Applicability Undetermined | Multiple candidates, rationale unclear | Read rationale; decide which L2s apply |
| Assumed N/A — Verify | Sibling L2 had evidence, this one didn't | Gut-check vs entity knowledge; confirm N/A or override |
| Not Applicable | Legacy was explicitly N/A | Confirm unless the entity's business changed |
| No Legacy Source | No legacy pillar maps here | Assess from scratch if applicable |

Detailed status→action + 5-step review sequence:
`../config/risk_assessment_workflow.md`.

## 1.5 Ratings

Legacy Risk Rating is populated **only** for pure 1:1 direct mappings; blank
for multi-target, dedup'd, Undetermined, and rating-suppressed pillars by
design (SVP 2026-04-07). Use judgment + RCO rating guidance when available.

## 1.6 Additional Signals

App/engagement, auxiliary risk, control contradiction, cross-boundary —
**attention suggestions only**, never set status. Use them to decide where to
look harder.

## 1.7 Unmapped findings

Some findings are tagged to legacy L1 categories, not a new L2. The workbook
flags these (banner + Audit_Review column) so you manually associate them.

## 1.8 Finishing

Transfer confirmed applicability, ratings, and control assessments into
**Optro**. The workbook is the map; Optro is the destination and the record.

## 1.9 Limitations & help

Read `../luminate_disclaimers.md` (canonical). Owner / escalation:
Governance §Inventory Record.

---

# Part 2 — Refresh SOP

**Owner:** `[CONFIRM]` · **Backup:** `[CONFIRM]` · **Cadence:** on demand for
the migration window (transitional tool — no fixed recurring schedule).

## 2.1 Preconditions

- Python env with pinned `requirements.txt` installed (includes pinned
  `en_core_web_lg-3.8.0` — canonical model). Model name+version, tool commit,
  library versions auto-logged and stamped into every output (no manual
  recording — `utils.get_run_provenance`).
- Latest ARCHER/enterprise extracts staged in `data/input/` using expected
  filename patterns (Governance §Inventory data-sources table).

## 2.2 Procedure

1. **Stage inputs.** Drop source files into `data/input/`. Most-recent-by-mtime
   wins per pattern — remove stale files to avoid picking the wrong one.
2. **Validate (mandatory gate).** `python validate_inputs.py`. Exit 0 = file
   manifest complete + column headers aligned. **Non-zero: stop** and fix the
   missing file / renamed column (defense against silent column-drop).
3. **Snapshot for traceability.** Record git commit, copy of `data/input/` +
   `config/taxonomy_config.yaml`, the spaCy model version, and the **as-of /
   extract date of each Archer source file** (mtime ≠ data as-of date). Store
   with the output. Required for Validation §Reconciliation and governance.
4. **Run.** `python refresh.py` (all mappers + main pipeline);
   `python refresh.py --consolidate-llm` if LLM batch responses are ready.
   Flags: `--only ore,prsa`, `--skip-mappers`, `--no-main`. Mapper failure →
   warning, continues. Main pipeline failure → non-zero exit (Part 3).
5. **Verify output.** New timestamped Excel + HTML in `data/output/`. Open the
   HTML: methodology/disclaimer + provenance banner renders; row counts sane
   (not silently zero — Part 3, F-03).
6. **Record the run.** Append to `../CHANGELOG.md` if crosswalk/keywords/rules
   changed (Governance §Change Process). Note run timestamp + commit + input
   snapshot location.
7. **Publish.** Upload to SharePoint `[CONFIRM]`. Communicate the run
   timestamp (outputs are point-in-time).

## 2.3 LLM step (only if AI overrides in scope)

1. `python export_llm_prompts.py` → `data/output/llm_prompts/batch_NNN/`.
2. Paste each `prompt.md` into ChatGPT once; paste JSON back into
   `response.json`.
3. `python consolidate_llm_responses.py` (or `refresh.py --consolidate-llm`) —
   enforces closed schema. Produces `llm_overrides_<ts>.csv`.
4. The historic "prompt omits findings/sub-risk evidence" concern is
   **resolved** — current code reads the correct sheets
   (`export_llm_prompts.py:189-190`). Remaining residual: model variance
   (advisory), not an evidence gap.

## 2.4 Roles

| Step | Who |
|---|---|
| Stage + validate + run | `[CONFIRM: owner]` |
| LLM paste round-trip | `[CONFIRM]` |
| Publish + communicate | `[CONFIRM]` |
| Sign reconciliation (when required) | independent reviewer |

---

# Part 3 — Runbook (failure modes)

Keyed to known failure modes (`../AUDIT_INPUTS_DATAFLOW.md` §1.5/§1.10,
Methodology §2.7, `../config/methodology_reference.md` quick lookups).

## 3.1 Triage order

1. Did `validate_inputs.py` pass? If skipped, run it first — most "wrong
   output" issues are a missing file or renamed column.
2. Check `logs/transform_log.txt` (**truncated each run** — copy it aside
   before re-running). The provenance block at the top confirms which model +
   commit produced the run.
3. Identify the stage from the symptom table.

## 3.2 Symptom → cause → action

| Symptom | Likely cause | Action |
|---|---|---|
| Run aborts immediately, non-zero | Required `legacy_risk_data_*` missing | Stage the file; re-run |
| `validate_inputs.py` non-zero | Missing required file OR renamed source column | Fix file/column — do **not** run the pipeline until green |
| HTML shows **zero** apps / TPs / policies | Inventory file malformed → silently swallowed (`export_html_report.py:42-45`) | Check filename matches pattern; open the file; nothing will be in the log |
| A mapper failed but run continued | spaCy model missing, or bad mapper input | Install `en_core_web_lg` (pinned wheel in `requirements.txt`); check input; `refresh.py --only <mapper>` |
| Main pipeline non-zero exit | Schema/logic error mid-pipeline | Read `logs/transform_log.txt`; reproduce with `python -m risk_taxonomy_transformer` |
| Expected finding/ORE/PRSA absent for an entity | Source filter (Methodology §4.C) or upstream tagging gap | Walk `methodology_reference.md` "Why doesn't X show up"; check Upstream Tagging Gaps tab |
| `true_gap_fill` rows appear | Crosswalk edited or a pillar missing columns | Diff `taxonomy_config.yaml` vs `Crosswalk_v1.0.md`; check pillar-column warnings |
| AI overrides look thin / miss obvious evidence | Prompt missing expected evidence. (Stale-sheet defect is **fixed** — `export_llm_prompts.py:189-190`.) Likely the source workbook lacks those sheets, or rows filtered upstream. | Confirm workbook has `Source - Findings`/`Source - Key Risks`; check `:189-190` still matches `export.py` sheet names |
| Output can't be reproduced from an old timestamp | Pre-2026-05-16 outputs predate pinning/provenance | Read the provenance block if present; otherwise treat as the accepted residual (Methodology §2.7) |
| Importing `build_presentation` wrote a .pptx | No `__main__` guard — runs at import | Don't import it from tooling/tests; run as a script only |
| Raw vs Source-tab row counts don't reconcile | Multi-L2 explosion (intended fan-out) | Expected — group by item ID before comparing |

## 3.3 Recovery

- **Bad run published:** outputs immutable; do not edit. Re-run cleanly,
  publish a new timestamp, communicate which is authoritative, supersede.
- **Partial mapper failure:** mapper outputs persist in `data/output/`;
  `refresh.py --only <mapper>` then `refresh.py --skip-mappers`.
- **Suspected logic defect:** log in Validation §Test Plan defects table; do
  **not** patch the crosswalk to "fix" output — follow Governance §Change
  Process.
- **Wrong *decision* discovered post-migration** (LUminate proposed a status, a
  leader confirmed it into Optro, it was wrong): an Optro/process correction,
  not a LUminate re-run. Outputs are immutable point-in-time artifacts.
  Accountability for finding/fixing a wrong confirmed decision sits with
  `[CONFIRM: AERA migration / methodology process owner]`; correction is made
  in Optro; the original LUminate proposal + Decision Basis remains the audit
  trail. LUminate has no role beyond evidencing the proposal.

## 3.4 Escalation

Owner → backup → `[CONFIRM: methodology/IAG escalation]` (Governance §Inventory).
