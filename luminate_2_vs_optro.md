# LUminate 2.0 vs. Optro Dashboard Suite — Pros/Cons

**Audience:** SVP / leadership (assumed familiar with both tools)
**Framing:** Neutral comparison, no recommendation
**Status:** First-discussion draft
**Date:** 2026-05-08

---

## Context

Two paths are on the table for surfacing audit-entity risk-rating analytics:

- **LUminate 2.0** — extend the existing audit-built tool to consume Optro's L2 risk-assessment results as an input, so the AE rating logic (signals, decision basis, control effectiveness, impact of issues) can be cross-referenced against Optro's L2 results inside one report.
- **Optro dashboard suite** — build a series of dashboards inside Optro itself. Owned and built by the data migration team.

The two are not strict substitutes. LUminate is a **synthesis** product (combines PRSA, ORE legacy + IRM, audit issues, BMA, app/TP/model inventories, key flags, severity-weighted decision basis into one AE-centric view). Optro dashboards are **exposure** products (surface results from one source). The decision is whether the synthesis layer is worth the maintenance cost it imposes.

---

## LUminate 2.0

### Pros

- **One-stop shop.** Single AE-centric report; users don't context-switch between dashboards to assemble the picture.
- **Decision-basis transparency.** Carries the *reasoning* behind a rating (control-effectiveness chips, signal flags, key-inventory markers, severity-weighted impact-of-issues) — not just the result. Auditors have to defend the rating, not just display it.
- **Point-in-time evidence.** Produces a timestamped HTML report that can be attached to workpapers and cited in issued audit reports. Real-time dashboards drift; a live dashboard cannot be referenced in a frozen audit conclusion.
- **Cross-source integration already paid for.** Frankenstein automation, source-vs-mapper L2, PG Gap, ORE IRM, BMA wiring — that synthesis cost is sunk. Replicating it in Optro is greenfield data-engineering work.
- **Methodology embedded inline.** Banner/disclosure language ships next to the data via `methodology.yaml`. Dashboards typically separate docs from numbers.
- **AE-centric mental model.** Built around the audit entity as unit of analysis. Optro is L2-risk-centric; the AE-to-L2 translation lives only inside LUminate today.
- **Highly customizable.** Audit-specific signals (PG Gap pills, key chips, severity coloring) are first-class.
- **Intuitive for the audit user base.** No platform login; HTML report is portable and emailable.
- **Iteration speed.** Changes ship at the maintainer's pace, not the platform team's backlog cadence.

### Cons

- **Manual refresh today.** Cumbersome data refresh process; cadence is dictated by manual file pulls. Auditors viewing LUminate after a quarter-end may see stale rating inputs.
- **AI workload risk.** A 2.0 with AI assistance could require 50-100 batched prompts to refresh when guidance pivots (RCO changes, AE retirements, reorgs). Bursty cost — heavy when triggered, near-zero in steady state. Mitigable via diff-based reprompting (only reprompt entities whose inputs actually changed) but not free.
- **Bus factor.** Single maintainer. If maintainer rotates off audit, the tool calcifies. Optro has platform-team support by default.
- **Resource-allocation imbalance.** Building LUminate 2.0 keeps the build workload on a single audit lead. Building Optro dashboards moves that workload to the data migration team — which is staffed for it. Capacity here is asymmetric.
- **Customization burden.** Every new requirement (new source, new field, new signal) is bespoke work for the maintainer. Currently borne by one person.
- **AI determinism / reviewability.** LLM outputs can shift between runs even on identical inputs (model drift, temperature). Dashboards are deterministic by SQL — easier to defend in QA.
- **Multi-user concurrency.** Static HTML report has no shared state. Optro scales naturally to many concurrent users.
- **Governance / IT approval.** Internal-built tool may face risk/IT review hurdles a vendored platform sails through.
- **Onboarding tax.** Each new audit lead has to learn LUminate's mental model.

---

## Optro Dashboard Suite

### Pros

- **Real-time data feeds.** Dashboards reflect the latest Optro state without a manual refresh step.
- **Vendor / platform-supported.** Maintenance burden sits with platform team, not with the audit team.
- **Multi-user, multi-team.** Scales to many concurrent users without bottlenecking on a single maintainer.
- **Standard tooling.** Auditors already use Optro for L2 results; lower onboarding cost.
- **IT-governed.** Easier compliance/risk approval path than internally-built tools.
- **Resource fit.** Data migration team is staffed and ready; building these dashboards solves an existing resource problem on their side.
- **Deterministic by SQL.** No LLM variance; outputs reproducible across runs.

### Cons

- **No synthesis layer.** Doesn't combine PRSA, ORE (legacy + IRM), audit issues, BMA, inventories, key flags into one view. Either users assemble the picture across dashboards, or Optro takes on multi-source integration work it doesn't currently do.
- **No decision-basis layer by default.** Optro shows the rating; audit needs the reasoning behind the rating. Adding signal/chip-level transparency means custom dashboards on top, which become their own maintenance burden — just routed to a different team.
- **Dashboard fragmentation.** "A series of dashboards" means users navigate between several to assemble what LUminate gives in one place.
- **Limited custom rendering.** Audit-specific concepts (PG Gap pills, key chips, severity coloring, methodology disclosures inline) are likely thin in Optro's native dashboard capabilities.
- **No frozen-evidence artifact.** Live dashboards drift; cannot be cited as point-in-time evidence in an issued report. Audit defensibility relies on frozen attachable artifacts.
- **Stakeholder queue.** Each dashboard change waits behind the platform team's backlog; iteration speed ≠ audit-team's pace.
- **AE translation gap.** Optro is L2-risk-centric; AE-centric views require explicit modeling work that doesn't exist today.

---

## Cross-cutting considerations

- **The two are not strict substitutes.** Optro dashboards expose one source; LUminate synthesizes across many. A **hybrid** is plausible: LUminate consumes Optro as a feed (eliminates the manual refresh pain), Optro hosts a lightweight L2-only view for users who don't need synthesis. This collapses much of the dichotomy.
- **Resource asymmetry is a real factor.** "Optro dashboards solve a problem for the data migration team" is a legitimate input — but only if scoped to dashboards they're already resourced and motivated to build. It is not, on its own, a reason to absorb the equivalent workload onto a single audit lead.
- **AI workload concern is mitigable but not eliminable.** Diff-based reprompting (only reprompt entities whose inputs changed since last refresh) keeps the steady-state cost low. Worst-case bursts (RCO pivot, mass AE reorganization) remain heavy.
- **Customization is bottleneck-shaped, not absent.** LUminate customization bottlenecks on one audit lead. Optro customization bottlenecks on the platform team. Neither tool eliminates the bottleneck; they relocate it.

---

## Known gaps for a fuller decision

- **Specific Optro dashboards in scope.** Knowing the dashboard list would let us check, per dashboard, whether the functionality is replaceable by LUminate, complementary to it, or unrelated. Without it, the comparison stays at a structural level.
- **Optro feed feasibility for LUminate.** Whether Optro can export L2 risk-assessment results in a format LUminate can ingest reliably — the foundation of the hybrid path.
- **AI cost model.** Concrete dollar and latency numbers per refresh batch, with and without diff-based reprompting.
- **Bus-factor mitigation options.** Whether a second audit team member, contractor, or automation-team partner could share the LUminate maintenance load. If yes, the bus-factor con softens.
