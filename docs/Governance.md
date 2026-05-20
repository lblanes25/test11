# LUminate — Governance

`^^` markers in Part 1 are the EUC owner's own "needs attention"
flags — left intact.

---

# Part 1 — EUC Inventory Record

| Field | Value |
|---|---|
| **EUC name** | LUminate (LUminate — A tool to transform Risk Taxonomy) |
^^| **EUC ID** | `[CONFIRM: assign per EUC register]` |
| **Package / repo** | `risk_taxonomy_transformer/` (Git-local Git-hub / Luminate) |
| **Type** | Non-model EUC. Deterministic Python pipeline with a bounded AI-assisted enrichment step (advisory only). |
| **Lifecycle** | Transitional — supports the one-time legacy→AERA taxonomy migration. Expected retirement once migration is complete. `[CONFIRM: target retirement date]` |
| **Owner** | `[Lurian Blanes — Sr Manager -SPPI]` |
^^| **Backup owner** | `[CONFIRM]` |
| **Escalation** | `[methodology/IAG escalation contact]` |
^^| **Risk tier** | `[CONFIRM: classify per EUC framework — see "Risk-tier inputs" below]` |
^^| **Governance approval** | See Part 3 — `[CONFIRM: status]` |

## 1.1 Purpose

Transforms current-state ("legacy") audit-entity risk assessments into the new
6-L1 / 23-L2 AERA taxonomy. For each (audit entity × L2) pair it produces a
**proposed applicability status** plus an evidence summary and decision basis,
giving audit teams an informed starting position rather than a blank slate.
LUminate **synthesizes and presents** upstream data; it does not create
attribution, generate quantitative risk estimates, or make final decisions.

## 1.2 Users

Internal Audit teams (audit leaders and core audit teams) reviewing entity risk
assessments under the new taxonomy; Risk Category Owners (keyword validation,
output review). Estimated population: IAG Department. Output is consumed by
humans only — no downstream automated consumer.

## 1.3 Data sources (inputs)

Pulled from ARCHER, related enterprise extracts, and provided by RCOs, staged in `data/input/`:

| Source | File pattern | Required |
|---|---|---|
| Legacy risk data | `legacy_risk_data_*.{xlsx,csv}` | Yes |
| Key risk descriptions | `key_risks_*` / `sub_risk_descriptions_*` | No |
| IAG findings | `findings_data_*` | No |
| ORE (legacy) | `ORE_*` → `ore_mapping_*` | No |
| ORE (IRM) | `ORE_IRM_*` → `ore_irm_mapping_*` | No |
| PRSA report (Frankenstein) | `prsa_report_*` → `prsa_mapping_*` | No |
| PG team inputs (Track C2 — FND_ID bridge for PG gaps) | `project_guardian_aera_inputs_*` | No |
| GRA RAPs | `gra_raps_*` → `rap_mapping_*` | No |
| BM Activities | `bm_activities_*` | No |
| LLM overrides | `llm_overrides*` | No |
| RCO overrides | `rco_overrides_*` | No |
| Optro export | `optro_export_*` | No |
| Inventories | applications / third parties / policies / laws / models | No |
| Taxonomy | `L2_Risk_Taxonomy.xlsx` | Yes |

Authoritative source list: `../luminate_disclaimers.md`, `../LUminate_Summary.md`.

## 1.4 Outputs

Point-in-time **Excel workbook** and **HTML report**, timestamped, published to
SharePoint. Frozen artifacts — do not auto-refresh; cite with run timestamp.
Final decisions are recorded in **Optro** (system of record), not in LUminate.

## 1.5 Hosting / environment

Locally-run Python script. No network calls, no subprocess, no environment
variables, no hosted infrastructure (`../AUDIT_INPUTS_DATAFLOW.md` §1.3, §1.9).
^^Reproducibility: direct dependencies pinned to
exact versions incl. the canonical `en_core_web_lg-3.8.0` model; tool commit +
model + library versions auto-stamped into every output. 
See `Methodology.md` §2.7.

## 1.6 Risk-tier inputs (for the classifier to weigh)

- **Raises tier:** output influences ~10,000 risk decisions across 450+
  entities that become the seed state of the new taxonomy; includes an
  AI-assisted step; feeds a regulated audit process.
- **Lowers tier:** advisory only; human decides every row; not a system of
  record; no downstream automation; transitional lifespan; deterministic core
  with full per-decision audit trail.

## 1.7 Review / recertification

Transitional tool — no annual recertification cycle. Crosswalk and keyword sets
are recertified by RCOs.

---

# Part 2 — Change Process

Two tracks, deliberately separate. The crosswalk and keyword sets carry
methodology authority and change the *decisions*; code changes the *tool*.
They do not share an approval path.

## 2.1 Track 1 — Crosswalk / keyword / rule changes (methodology)

Applies to: `config/taxonomy_config.yaml` (`crosswalk_config`, `keyword_map`,
`l2_aliases`, `l2_unmappable`, thresholds), `Crosswalk_*.md`, and
`Methodology.md` Part 4.

| Step | Action | Who |
|---|---|---|
| 1 | Propose change with rationale and the authority for it | Requester |
| 2 | Update YAML; regenerate `Crosswalk_vNEXT.md` from it | EUC owner |
| 3 | Run Validation §Test Plan (at least affected rule paths) | validation-qa |
| 4 | Spot-reconcile affected entities (Validation §Reconciliation, scoped) | Independent reviewer |
| 5 | **Methodology-owner sign-off** on the new crosswalk version | AERA methodology owner |
| 6 | Version bump + `../CHANGELOG.md` entry; re-sign `Crosswalk_vNEXT.md` | EUC owner |
| 7 | Re-stamp outputs with the new crosswalk version | EUC owner |

A Track 1 change to a tier-affecting rule triggers governance re-approval
(Part 3 re-approval triggers).

## 2.2 Track 2 — Code changes (tool)

Applies to: anything under `risk_taxonomy_transformer/` and root scripts that
does **not** alter crosswalk/keyword/rule *semantics*.

| Step | Action | Who |
|---|---|---|
| 1 | Change on a branch; keep config-driven behavior unchanged | Developer |
| 2 | Run Validation §Test Plan regression set | validation-qa |
| 3 | Review (`.claude/agents/` path — audit-leader / validation-qa) | Reviewer |
| 4 | Merge; `../CHANGELOG.md` entry; tool version bump if output-visible | Developer |

No methodology sign-off for pure code changes — but if a "code" change shifts
any decision (status/method/rating distribution), it is reclassified Track 1
and stops until methodology sign-off.

## 2.3 The test that decides the track

> Does this change alter what status/rating/evidence a row can get, for the
> same inputs? **Yes → Track 1. No → Track 2.** When unsure, treat as Track 1.

The BMA date cutoff is a Track-1 rule and is config-resident
(`taxonomy_config.yaml:209`), so it already follows Track 1. The only open
action is attributing the date value to a named approving authority
(`Methodology.md` §4.E) — not a code-to-config move.

---

# Part 3 — Governance Approval

To be completed by the approving authority.

## 3.1 Submission package

1. Part 1 (Inventory Record) — what it is, owner, data sources, risk-tier inputs
2. `Methodology.md` — requirements, design, method justification, rule set, limitations
3. `Crosswalk_v1.0.md` — the mapping rules (also requires methodology-owner sign)
4. `../luminate_disclaimers.md` — limitations register / out-of-scope
5. Reconciliation result (`Validation.md` Part 2, once executed)
6. UAT sign-off (`Validation.md` Part 3, once executed)

## 3.2 Risk-tier determination

| Field | Value |
|---|---|
| Proposed tier | `[CONFIRM]` |
| Determined by | `[name / role]` |
| Date | `[date]` |
| Rationale | `[1–2 sentences — weigh §1.6 risk-tier inputs]` |

## 3.3 Approval

| Question | Response |
|---|---|
| Is LUminate registered in the EUC inventory? | `[Y/N + ID]` |
| Is the intended use and out-of-scope use documented and acceptable? | `[Y/N]` |
| Has a sample reconciliation been performed and variances explained? | `[Y/N — attach]` |
| Has UAT been completed with sign-off? | `[Y/N — attach]` |
| Has the crosswalk been signed by the AERA methodology owner? | `[Y/N — see Crosswalk_v1.0.md]` |
| Are residual risks acknowledged: **over-reliance on the proposal** (highest-consequence — a confirmed wrong proposal becomes a permanent Optro decision), AI model variance, no full transitive-dependency lockfile, unattributed threshold authority? | `[Y/N]` |
| **Disclosure:** prior production outputs were generated with spaCy `en_core_web_lg` while config/docs incorrectly stated `en_core_web_md` (corrected 2026-05-16; `lg` confirmed canonical, now pinned). Mapper similarity scores/banding are model-dependent. Has the reconciliation been (re)run under canonical `lg`? | `[Y/N — confirm reconciliation used en_core_web_lg]` |
| Is the decision-level error-correction owner named (who finds/fixes a wrong confirmed decision in Optro post-migration — see Operations §Runbook 3.3)? | `[Y/N — name]` |
| Has a one-time aggregate output-distribution sanity review been done (status mix across all rows reasonable before freezing into Optro)? | `[Y/N — attach]` |
| **Approved for use in the AERA migration?** | `[Approved / Approved with conditions / Not approved]` |
| Conditions / scope limits | `[...]` |

| Role | Name | Signature | Date |
|---|---|---|---|
| EUC owner | `[CONFIRM]` | | |
| Approving authority (governance) | `[CONFIRM]` | | |
| AERA methodology owner | `[CONFIRM — likely Matt]` | | |

## 3.4 Re-approval triggers

Re-approval required if any of these change after approval: the crosswalk
(`Crosswalk_v1.0.md`), the AI step's evidence inputs, the risk-tier
determination, or the set of data sources consumed.
