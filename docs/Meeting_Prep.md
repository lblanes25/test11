# Meeting Prep — LUminate close-out (TRANSIENT working notes)

> **Status: transient working prep — NOT governance-of-record.** Delete after
> the meetings. The durable decisions live in `Governance.md`,
> `Crosswalk_v1.0.md`, `Methodology.md`, and the close-out list in `README.md`;
> this file just scripts the conversations and points back to those.
> Prepared 2026-05-17.

## Sequencing (do them in roughly this order)

1. **Technology team first** (or know their answer early). They decide whether
   this is an "application" or a simple end-user tool — that sets which
   rulebook applies. If "application," the lighter EUC documentation may not be
   enough and the Director/Matt asks change. Don't treat anything as final
   until this is answered.
2. **Matt before reconciliation locks.** His item **1a** (Strategic & Business
   → Capital, Option C) must be answered before the pilot reconciliation is
   locked — the reconciler derives Capital under Option C; if he picks A/B it
   must be re-derived.
3. **Director blesses the path last** but needs the scope clarified up front.
   Her approval is conditional on the Technology answer.

## Say this consistently in every room (the honesty anchor)

> "The documentation is complete and honest about what's done versus pending.
> Three things are still open by design — the application determination,
> Matt's methodology sign-offs, and the pilot-run reconciliation — and the
> package is built so those close cleanly rather than being papered over."

---

# 1. Technology team — application determination

**Goal:** a written classification — **EUC/tool vs. application**. This is the
fork that sets which control regime everything else lives under.

**Decisions to extract:**
- Their actual *criteria* for "application" vs. EUC (get the definition — don't
  argue the conclusion).
- The classification itself.
- If borderline: does transitional lifespan + no infrastructure keep it EUC?
- Does the **ChatGPT paste step** (data to an external LLM, even
  operator-mediated) or **SharePoint publication** change the classification,
  or trigger a separate data-handling review?

**Bring (only this):** the technical facts — local Python script, no
server/DB/network/auth, single local user, output is files to SharePoint,
transitional; the LLM step is bounded, operator-mediated, no automated egress,
schema-validated, human-confirmed. Source: `Methodology.md` Part 2 +
`../AUDIT_INPUTS_DATAFLOW.md` §1.3/§1.9. **Not** the governance pack.

**Framing/risk:** the LLM step is the thing most likely to push it toward
"application" or extra review — have the bounded design ready. This
determination can invalidate the *calibration* of the whole EUC package
(it's all sized for a transitional EUC), so treat it as gating.

**Not for them:** methodology, sign-offs, risk tier.

---

# 2. Director — "protect ourselves" (governance path & risk posture)

**First two minutes — clarify scope.** "Configuration documentation" is
ambiguous. Ask whether she means: (a) the full EUC governance pack, (b) the
**AI-step configuration specifically** (system prompt, knowledge sources — the
CREATE-framework review), or (c) just the EUC register entry. This changes what
you walk her through. Don't assume (a).

Each item below: plain meaning · why it's her call · the literal ask.

### 2.1 EUC register entry, risk-tier owner, approving authority
- *Plain:* "EUC" = the category your tool is in (business-built, not an IT
  system). Orgs keep an official list of these. Open: does this need to be on
  that list and who logs it; who officially rates how risky it is (that rating
  sets how much oversight); whose signature actually clears it for use.
- *Why her:* you can't self-assign these — governance roles she owns or routes.
- *Ask:* "Does this need a formal EUC register entry, and who owns that? Who
  officially decides its risk rating? And whose sign-off clears it for use?"

### 2.2 Pilot-derived reconciliation as the accuracy evidence
- *Plain:* the biggest open item is *proving the tool's answers are right*.
  Plan: use the pilot — one team works an entity by hand, blind, and compares —
  instead of a separate standalone test project.
- *Why her:* she's the one exposed if a regulator asks "how do you know it was
  right?"
- *Ask:* "My plan to prove accuracy is to use the pilot — one team derives an
  entity by hand and we compare — rather than a separate formal test. Are you
  comfortable with that as the evidence?"

### 2.3 Accept the documented residuals + mitigation she wants
- *Plain:* "residuals" = known weaknesses deliberately not fully fixed, written
  down. Two: (a) main software versions pinned but not every sub-dependency, so
  an old run can't be recreated byte-for-byte; (b) you're the only owner and
  not a developer — no one else owns it if you're out.
- *Why her:* "we accept a known weakness" is a management risk-acceptance call.
- *Ask:* "Two known gaps I deliberately didn't fully close because the tool's
  temporary — sub-dependency versions aren't all locked, and I'm the only owner
  and not a developer. OK to accept those for the migration, and do you want
  anything done to reduce them (e.g., brief a backup)?"

### 2.4 Decision-error-correction owner
- *Plain:* tool suggests → human confirms → answer goes into Optro
  permanently. If a confirmed answer is later found wrong, who catches and
  fixes it in Optro? Currently nobody is named (a blank in the Runbook). Not
  the tool's job — a process-ownership gap.
- *Why her:* it's an accountability assignment above the tool.
- *Ask:* "If we later find a confirmed decision saved into Optro was wrong, who
  owns finding and correcting it? Nobody's named — it's a process role."

### 2.5 Timeline + Technology determination gates the regime
- *Plain:* (a) when she needs this done / approval target; (b) Technology's
  pending call ("application" vs end-user tool) decides which rulebook applies
  — if "application," requirements get heavier and this lighter documentation
  may not suffice. Her approval can't be final until Technology rules.
- *Why her:* she shouldn't sign off thinking it's closed when Technology could
  reopen it.
- *Ask:* "What's your target date? And heads-up: Technology is deciding whether
  this is an 'application' or a simple end-user tool — if it's an application
  the requirements get heavier, so this approval is conditional on their
  answer."

### 2.6 Walk the banners and disclaimers together
- *Plain:* "Banners" = notices users actually see on the Excel tabs / HTML
  report (the "starting point only, NLP can be wrong, confirm the L2" caveat;
  per-source methodology notes; the run-provenance line). "Disclaimers" =
  `../luminate_disclaimers.md`, the written "what LUminate is and isn't
  accountable for." Together they're the literal text your protection rests on.
- *Why her:* if anyone later says "the tool told me to do X," the defense *is*
  this wording — a management call, not just yours. Walking it also forces the
  honest point: this is *cover* (bounds accountability), **not** proof the tool
  is right.
- *Do:* open a **freshly generated** HTML report + Excel workbook and show the
  banners in place (don't just describe). Then walk the disclaimers doc —
  highest-severity: advisory/AI may vary between runs; not a system of record
  (Optro is); point-in-time; over-reliance on the proposal; the spaCy-`lg`
  correction disclosure.
- *Get from her:* (a) wording is what she'll stand behind; (b) anything to
  strengthen/soften/add; (c) it's visible **at the point of use** (working tab,
  not a hidden methodology tab).
- *Gotcha to say up front:* old reports in the output folder predate the model
  correction and the all-"Needs Review" change — their banners are stale.
  Generate a current run and check its provenance line so she reviews live
  wording, not last month's.

**One-line framing for the whole Director meeting:** *you're not asking her to
bless the engineering — you're asking her to own the governance decisions only
she can own (who approves, what risk level, what gaps are acceptable, who fixes
mistakes later, what the protection wording says) and to acknowledge it's
conditional on the Technology call.*

**Bring:** the 5-doc `docs/` set + `README.md` old→new map + the close-out
checklist + the corrected `../EUC documentation checklist.md`. Lead with the
honest posture and the disclosures (spaCy `lg` correction; NLP now all
"Needs Review"; Option C pending Matt; reconciliation/UAT not yet executed).

---

# 3. VP Matt — methodology confirm/approve

**Goal:** the sign-offs below. Make each a pick-one so it can close without a
meeting. **Item 1a must be answered before the reconciliation is locked.**

**Bring:** the email below + `Crosswalk_v1.0.md` (config-verified 2026-05-17).

### Email draft (ready to send)

> **Subject: LUminate — AERA methodology sign-offs needed for EUC governance**
>
> Matt,
>
> LUminate is going through EUC governance close-out. As AERA methodology owner
> you're the named authority on the items below. I've made each a yes/no or
> pick-one so this doesn't need a meeting unless you want one. Crosswalk
> document attached.
>
> **1. Crosswalk sign-off (the main one).** `Crosswalk_v1.0.md` — the full
> legacy-pillar → new-L2 mapping, verified against the implemented config.
> Please confirm it represents the approved AERA mapping and sign the sign-off
> block. This also covers your prior decisions already baked in (Fraud
> evaluated at L3 grain; External Fraud rating not carried forward; 23
> evaluated L2 of the 24-risk taxonomy).
>
> **1a. Strategic & Business → Capital — confirm the treatment.** S&B split
> into Capital + Earnings (Earnings Not Assessed). Leaving it a clean 1:1 would
> carry the legacy S&B rating onto Capital — but that rating was scoped to the
> broader pillar, the same situation the SVP 2026-04-07 decision addressed for
> split pillars. **We've implemented Option C:** Capital still applies wherever
> S&B applied (applicability carries), but the rating is **not** carried — it's
> blank for the reviewer to set, using the same mechanism already approved for
> External Fraud. Implemented and verified but **not locked pending your
> confirmation**. Please confirm Option C, or direct otherwise (A: keep rating
> carryforward; B: reclassify as multi). On confirm, the crosswalk goes to v1.1
> with your sign-off.
>
> **2. Reputational & Country — routing decision.** Per your 2026-04-21 call
> these are "Not Assessed" and generate no L2 rows. Open: findings tagged to
> Reputation/Country currently surface in the "Unmapped Findings" column for
> manual handling — not auto-routed to any L2. Options: (a) leave as-is
> (surface, manual); (b) route Reputation → Conduct (and Country → [your
> call]); (c) other. Recommended: (a) for the migration, revisit later.
>
> **3. Keyword confidence threshold = 3 — accept or replace.** A multi-target
> L2 is high-confidence at ≥3 RCO-vetted keyword hits; 1–2 = medium; 0 = not
> asserted and routed to human review. 3 biases deliberately toward review.
> Because every non-direct proposal is human-confirmed and 0-hit L2s already
> route to review, the value tunes review-queue volume, not the auditor's final
> call. Recommended: accept 3; revisit only if pilot review volume proves
> impractical.
>
> **4. BMA scope cutoff (2025-07-01) — confirm owner.** Cases before this date
> are out of scope for the current AERA cycle. Needs a named approving
> authority. Is that you, or the AERA-cycle owner? If yours, confirm the date.
>
> **5. RCO keyword validation — status, not a sign-off.** Governance will ask
> when keyword validation is complete for all 23 L2 (in progress). Do you have
> a target, or who owns the remaining RCOs?
>
> Happy to walk through any of these live. Otherwise a reply with your answers
> (e.g. "1 signed, 1a C, 2(a), 3 accept, 4 mine—confirmed, 5 …") closes them
> out.
>
> Thanks,
> Lurian

**Not for him:** EUC governance mechanics, the application determination.

---

## Where the durable versions live (this file is just the script)

- Matt's decisions / sign-off block: `Governance.md` Part 3, `Crosswalk_v1.0.md`
- Option C detail + status: `Crosswalk_v1.0.md`, `Methodology.md` §4.B5/§4.E,
  `../CHANGELOG.md`
- Close-out checklist: `README.md`
- Disclaimers (canonical): `../luminate_disclaimers.md`
- Banners content: `../config/banners.yaml`, `../risk_taxonomy_transformer/methodology.yaml`
