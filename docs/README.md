# LUminate — EUC Documentation Set

Governance documentation of record for **LUminate**, the legacy→AERA risk
taxonomy transformer EUC. Assembled 2026-05-15; consolidated 2026-05-17 from 13
documents into 5 to enforce **one home per fact** (the prior set threaded the
same facts through many files, creating a maintenance hazard for a
single-owner transitional tool).

**Framing:** LUminate is a *transitional* tool. The tool is disposable; the
migration decisions it produces are permanent (they seed the new AERA taxonomy
in Optro). Documentation is calibrated accordingly — heaviest on artifacts that
protect the *decisions and their traceability*.

## The 5 documents

| Doc | Contains (formerly separate docs) |
|---|---|
| `Methodology.md` | Purpose & Requirements (BRD) · Architecture & Technical Design · Method Justification · Rule Set · Limitations. **Single source for what/why/rules + residual-risk table.** |
| `Operations.md` | User Guide · Refresh SOP · Runbook. **How to read output, run it, handle failures.** |
| `Validation.md` | Test Plan · Sample Reconciliation Procedure · UAT & Independent Review Sign-Off. **Unexecuted templates — execution + signatures are the gating items.** |
| `Governance.md` | EUC Inventory Record · Change Process · Governance Approval. |
| `Crosswalk_v1.0.md` | The signable legacy→AERA mapping. Standalone (needs its own methodology-owner signature) — not merged. |

Plus `../CHANGELOG.md` (root) — version/change log.

`reference/data_flow.md` — **non-governed developer reference** (relocated from
`config/` and re-verified 2026-06-12): per-source code-level plumbing (where
each input is read, what's filtered, where it lands). Where it diverges from
the 5 governed docs, the governed docs win. Its former companions
(`methodology_reference.md`, `decision_tree.md`, the dev prompts, and the May-2
training/walkthrough docs) were stale and retired to
`../archive/superseded_docs/` on 2026-06-12.

`Meeting_Prep.md` also exists but is **transient working notes, NOT
governance-of-record** — meeting scripts for the Technology/Director/Matt
conversations, deletable after those meetings. It points back to the 5 docs;
it is not part of the controlled set.

Reviewers asking for a named artifact (e.g. "the Test Plan") are pointed to the
titled section:

| Old artifact | Now at |
|---|---|
| BRD | `Methodology.md` Part 1 |
| Technical Design (+ residual risks §7) | `Methodology.md` Part 2 (§2.7) |
| Method Justification | `Methodology.md` Part 3 |
| Rule Set | `Methodology.md` Part 4 |
| Limitations Register | `Methodology.md` Part 5 (canonical remains `../luminate_disclaimers.md`) |
| User Guide | `Operations.md` Part 1 |
| Refresh SOP | `Operations.md` Part 2 |
| Runbook | `Operations.md` Part 3 |
| Test Plan | `Validation.md` Part 1 |
| Reconciliation Procedure | `Validation.md` Part 2 |
| UAT / Independent Review | `Validation.md` Part 3 |
| EUC Inventory Record | `Governance.md` Part 1 |
| Change Process | `Governance.md` Part 2 |
| Governance Approval | `Governance.md` Part 3 |

Already-met items kept in their existing locations (not duplicated here):
per-decision audit trail (Decision Basis columns + `methodology.yaml`), stated
intended use (`../luminate_disclaimers.md`), output disclaimer
(`../risk_taxonomy_transformer/methodology.yaml` + `../config/banners.yaml`).

## Close-out checklist (canonical — require a run or other people)

**Evidence (gates approval):**
1. **Pilot override log** — start capturing now (`Validation.md` Part 4.1).
2. **Sample reconciliation** — one pilot team does the blind derivation on 1–2
   entities under canonical `en_core_web_lg` (`Validation.md` Part 4.2 → Part
   2). Highest priority.
3. **UAT + independent review sign-off** — pilot leaders sign Part 3.5;
   independent reviewer countersigns the LLM review (Part 3.3 R-5).
4. **Crosswalk sign-off** — diff all 23 routes vs `taxonomy_config.yaml`, then
   AERA methodology owner signs `Crosswalk_v1.0.md`.

**Decisions / authority (needed before governance approval):**
5. Threshold authority: NLP band **closed by design** (2026-05-17, all
   Needs Review). Still open — keyword confidence = 3 (decision-bearing;
   rationale drafted for Matt to accept), BMA cutoff 2025-07-01 owner, RCO
   keyword-validation status (`Methodology.md` §4.E).
6. One-time aggregate output-distribution sanity review (`Governance.md` 3.3).
7. Resolve all `[CONFIRM]` fields — EUC ID, retirement date, backup owner,
   escalation, risk tier (+ who/why), SharePoint URL, decision-error-correction
   owner, Refresh-SOP roles.

**Then:**
8. **Governance approval** — route the package per `Governance.md` Part 3.

Optional: correct the stale ~4,600/200+ figure in `../PHASE2_SCOPE.md`
(historical doc; owner's call).

## Verification note

Re-verified against current `HEAD` after an audit-leader review. Findings
inherited from the earlier point-in-time `../EUC documentation checklist.md` /
`AUDIT_INPUTS_DATAFLOW.md` (the latter retired to `../archive/superseded_docs/`
2026-06-12) that were **stale and have been corrected**:

- **LLM prompt sheet-name bug: RESOLVED, not open.**
  `export_llm_prompts.py:189-190` reads `"Source - Findings"` /
  `"Source - Key Risks"` (the sheets `export.py:542,547` write). Fixed
  2026-05-02. Findings/sub-risk evidence **does** reach the LLM prompt.
- **BMA date cutoff is in YAML** (`taxonomy_config.yaml:209`
  `min_completion_date`), not hardcoded. Open item is the unattributed
  approving authority for the value.
- **Canonical spaCy model is `en_core_web_lg`**, not `md` (corrected
  2026-05-16; pinned; provenance now stamped into every output).

Every `file:line` citation should be re-confirmed against current `HEAD`
before governance sign-off — the codebase moves under point-in-time docs.
