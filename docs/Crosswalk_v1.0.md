# Legacy → AERA Crosswalk — v1.0

**Status:** For methodology-owner sign-off.
**Machine source of record:** `config/taxonomy_config.yaml` → `crosswalk_config`
(this document is generated from it; if they diverge, the YAML governs and this
doc must be regenerated).
**Generated:** 2026-05-15 from `taxonomy_config.yaml` → `crosswalk_config`;
updated 2026-05-17 — the per-edge `conditions:` keyword lists were removed:
conditional targets now gate purely on the target L2's `keyword_map` list.
There is one keyword list per L2, nothing separate.
**Config-fidelity verified:** 2026-05-17 — all 12 pillar routes
(relationships, `suppress_rating`) and 23-L2 coverage match the implemented
`crosswalk_config` route-by-route. Content-verified (not line-number-exact).
Re-verify on any Track-1 change.
**Proposed amendment in config, pending Matt:** Strategic & Business now
carries `suppress_rating: true` (Option C — §"Strategic & Business" below).
Implemented and behaviour-verified, but **not yet signed**; crosswalk stays
**v1.0** until the methodology owner approves, then → v1.1 + sign + CHANGELOG.

This is the standalone, reviewable statement of how each legacy pillar maps to
the new AERA taxonomy. It exists so the AERA methodology owner can review and
**sign the mapping itself**, separate from the code.

## New taxonomy scope

6 L1 / 23 evaluated L2 (Matt 2026-05-01). Earnings, Reputation, Country Risk
are in the broader 24-risk taxonomy as **"Not Assessed"** and intentionally
generate **no** Audit_Review rows.

## Relationship semantics

| Type | Behaviour |
|---|---|
| `direct` | Legacy pillar → exactly one L2. Legacy rating carried forward, **unless `suppress_rating: true`** (then applicability carries, rating blank — reviewer sets it). High confidence. |
| `multi · primary` | Candidate L2. For pillars with **no rationale column** (IT, InfoSec) every primary target is auto-applicable. |
| `multi · conditional` | Candidate L2 expected to surface only on a clear signal. |

For rationale-bearing pillars, `primary` and `conditional` are resolved
identically: scored against the target L2's own `keyword_map` (no separate
per-edge list); a row is created only on a keyword hit, else all candidates
are shown for review. The former `secondary` tier was collapsed into
`primary` 2026-05-17 — it had no distinct behavior.

When multiple legacy pillars map to the same (entity, L2), the higher (more
conservative) rating is kept and both sources logged.

## Direct mappings (1:1)

Rating carries forward on direct mappings **except** where noted
(`suppress_rating`).

| Legacy pillar | New L2 | Rating carryforward | Notes |
|---|---|---|---|
| Funding & Liquidity | Liquidity | Yes | Direct 1:1 |
| Strategic & Business | Capital | **No — suppressed (Option C, pending Matt)** | S&B split into Capital + Earnings (Earnings Not Assessed); rating was scoped to the broader pillar, so applicability carries but Capital is reviewer-rated. See §"Strategic & Business" below |
| Model | Model | Yes | Direct 1:1 |
| Third Party | Third Party | Yes | Direct 1:1 |
| Financial Reporting | Financial Reporting | Yes | Direct 1:1 |

## Multi-target mappings

| Legacy pillar | Target L2 | Relationship | Notes |
|---|---|---|---|
| **Credit** | Consumer and Small Business | primary | Both populate; team marks non-applicable one N/A |
| | Commercial | primary | |
| **Market** | Interest Rate | primary | Both populate; similarly assessed per VP |
| | FX and Price | primary | |
| **External Fraud** | External Fraud - First Party | primary | **Rating NOT carried forward** (Matt 2026-05-01). Applicability via First-Party vs Victim keyword disambiguation; generic-only fraud rationale → Applicability Undetermined |
| | External Fraud - Victim Fraud | primary | |
| **Information Technology** | Technology | primary | No rationale column → keyword scoring skipped; both always applicable |
| | Data | primary | |
| **Information Security** | Information and Cyber Security | primary | No rationale column → keyword scoring skipped; both always applicable |
| | Data | primary | |
| **Operational** | Processing, Execution and Change | primary | |
| | Business Disruption | primary | |
| | Human Capital | primary | |
| | Conduct | primary | |
| | Privacy | primary | |
| | Data | conditional | Fires only if Operational rationale / key risks hit the **Data** `keyword_map` list |
| | Internal Fraud | conditional | Fires only if Operational rationale / key risks hit the **Internal Fraud** `keyword_map` list |
| **Compliance** | Prudential & bank administration compliance | primary | |
| | Customer / client protection and product compliance | primary | |
| | Financial crimes | primary | |
| | Conduct | primary | |

## Pillars deliberately NOT in the crosswalk

**Reputational** and **Country** — set "Not Assessed" by Matt (2026-04-21).
They generate no L2 rows. Their rationale/key-risk text still feeds
cross-boundary keyword scanning only. Findings tagged "Reputation"/"Country"
surface in the Audit_Review "Unmapped Findings" column. Routing policy (e.g.
should Reputation findings be assigned to Conduct?) is an **open question**
routed to the AERA methodology owner — item 2 of the sign-off package
(`Governance.md` Part 3 / the Matt sign-off email).

## Strategic & Business → Capital — proposed Option C (pending Matt sign-off)

S&B decomposed into Capital **and** Earnings (Earnings = Not Assessed); an
earlier framing had Earnings primary, Capital secondary. Treating it as a
clean 1:1 with rating carryforward re-introduces the cross-taxonomy rating
assumption SVP 2026-04-07 closed for split pillars (legacy rating was scoped
to the broader pillar, not Capital).

**Decision (EUC owner): Option C — implemented, behaviour-verified, pending
AERA methodology-owner validation.** S&B keeps `mapping_type: direct` (Capital
applicability still carries — the Capital row is `Applicable` wherever S&B
applied) but `suppress_rating: true` (the same flag/mechanism External Fraud
uses): the legacy S&B rating does **not** populate Capital's Proposed Rating —
the reviewer assigns an L2-specific rating. Verified end state: Capital =
`Applicable`, Proposed Rating blank, Decision Basis = "Direct from Strategic &
Business. Rating not carried forward — review and assign an L2-specific
rating."

Options considered: (A) keep direct + rating carries; (B) reclassify
`multi → Capital`, no carryforward; **(C, chosen)** direct applicability +
`suppress_rating`. Matt sign-off package **item 1a** — he confirms C, or
directs A/B. Status: crosswalk stays **v1.0** until he signs; on approval →
**v1.1** + sign-off + CHANGELOG (Track-1).

## Coverage check

Every one of the 23 evaluated L2s is reached by at least one pillar route, so a
correctly-configured run produces zero `true_gap_fill` rows. A `true_gap_fill`
in output means the crosswalk was edited or a pillar was missing columns.

## Sign-off

| Role | Name | Statement | Signature | Date |
|---|---|---|---|---|
| AERA methodology owner | `[CONFIRM — Matt]` | "This crosswalk correctly represents the approved legacy→AERA mapping." | | |
| EUC owner | `[CONFIRM]` | "Implemented crosswalk matches this document." | | |

Any change to this mapping follows `Governance.md` Part 2 (Track 1) and
requires re-sign + a version bump (v1.1, …) recorded in `CHANGELOG.md`.
