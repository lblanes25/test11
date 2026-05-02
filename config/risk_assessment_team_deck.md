# Risk Assessment Team Deck — Working in the New Taxonomy

**Audience:** Audit team members (audit leaders, PGAs, senior auditors) completing entity-level risk assessments under the new 6 L1 / 23 L2 taxonomy.
**Primary artifact:** The HTML Risk Taxonomy Report.
**Destination:** AERA (all final decisions go there — the report is the map, not the submission).

Each `##` heading below is one slide.

---

## Slide 1 — What You're Here to Do

For every audit entity, you answer three questions across 23 L2 risks:

1. **Applicability** — Does this risk apply to this entity?
2. **Rating** — If applicable, how severe is it (Low / Medium / High / Critical)?
3. **Control Assessment** — What's the state of controls for this risk, and what evidence exists of control issues?

The Risk Taxonomy Transformer gives you a starting position for all three. You review, override, and record your final answers in AERA.

**Key principle:** You aren't filling out the report. You're reading it and then making decisions in AERA. The report is structured to show you, row by row, what the tool thinks and why — so you react to an informed starting position rather than building from zero.

---

## Slide 2 — The View You Work From

Open the HTML report. Pick your entity from the sidebar. You land on the **Risk Profile** tab — one row per L2, sorted so the rows that need judgment are at the top (Undetermined → Needs Review → Assumed N/A → Applicable → Not Applicable → Not Assessed).

**The columns on the Risk Profile table:**

| Column | Source | What it tells you |
|---|---|---|
| `New L1` / `New L2` | Taxonomy | The risk being assessed |
| `Status` *(blue)* | Tool | The tool's applicability proposal |
| `Confidence` *(blue)* | Tool | How confident the tool is in its mapping |
| `Legacy Rating` | Legacy data | Pillar rating carried forward — a reference, not the answer |
| `Legacy Source` | Legacy data | Which legacy pillar this row came from |
| `Decision Basis` *(blue)* | Tool | Plain-English explanation of why the tool made this proposal |
| `Additional Signals` *(blue)* | Tool | Apps / 3Ps / cross-boundary flags — evidence the tool surfaced |

*Blue headers = tool-produced. Everything blue deserves a second look before you rely on it.*

**Four tabs you'll use in this order:**
1. **Risk Profile** — scan view (primary workspace)
2. **Drill-Down** — per-row deep-read for anything that gives you pause
3. **Legacy Profile** — the old pillar ratings for reference
4. **Source Data** — inventories + raw issues/events when you need details

---

## Slide 3 — Applicability, by Status

For each row, the tool has proposed a Status. Here's what you check for each.

### Applicable

**The claim:** Evidence supports this L2 applying to this entity.
**What you check:**
- Does the Decision Basis actually describe this L2?
- Does the Source Rationale (in drill-down) contain content that fits?
- If the keyword match is weak or generic, look harder before accepting.

**What you do:** Confirm in AERA, or override if evidence looks thin.

### Applicability Undetermined

**The claim:** The legacy pillar maps to multiple L2s and the rationale didn't clearly indicate which one(s). Proposed Rating is intentionally **blank** — we don't want you rubber-stamping a rating for an L2 the tool couldn't confirm.
**What you check:**
- Read the Source Rationale in drill-down.
- Check the "Other L2s from [pillar] that DID match" list — these are the siblings.
- Use your knowledge of the entity.

**What you do:** For each L2 in the ambiguous set, decide individually whether it applies. Apply a rating only to the ones you confirm.

### No Evidence Found — Verify N/A

**The claim:** Sibling L2s from the same pillar had evidence. This one didn't. Tool's best guess is N/A.
**What you check:**
- Gut check against your entity knowledge. Does this risk feel relevant despite no keyword match?
- The tool only looks for specific keywords. If the rationale uses different language (e.g., "resiliency" for Business Disruption), the tool misses it.

**What you do:** Usually confirm N/A. Override to Applicable when your judgment contradicts the keyword miss.

### Not Applicable

**The claim:** The legacy pillar was explicitly rated Not Applicable.
**What you check:** Has anything about the entity's business changed? New products, new lines, new geographies that make the risk relevant now?
**What you do:** Confirm unless something's changed.

### Not Assessed

**The claim:** No legacy pillar maps to this L2. Structural gap — this L2 is new under the taxonomy.
**What you check:** Is the risk relevant to this entity? Fresh assessment, no legacy anchor.
**What you do:** Assess from scratch. Rate if applicable; confirm N/A otherwise.

---

## Slide 4 — Evidence Beyond Keywords

When the tool says Assumed N/A or Undetermined, these are the signals that may push you to "applicable" despite no direct keyword hit.

### Inventories (Source Data → Scope → Inventories)

- **Applications** with Confidentiality / Availability / Integrity ratings. A Critical-rated app is direct evidence for Information Security / Data / Privacy applicability.
- **Third parties (primary + secondary)**. Presence of 3Ps makes Third Party L2 applicable almost by definition.
- **Models tagged to the entity**. Makes Model Risk applicable.
- **Policies / Laws / Mandates**. Applicable laws anchor Compliance L2s (e.g., Reg Z → Consumer protection; BSA → Financial crimes).

### Handoffs (Risk Profile tab, entity context block)

- **FROM other AEs** → the entity inherits upstream risk. E.g., receiving customer data makes Data / Privacy applicable even if your own assessment didn't mention it.
- **TO other AEs** → check whether the handoff itself introduces Processing / Execution / Compliance risk.

### Additional Signals column

- `[App]` chip → app or 3P tagged to entity. Soft signal.
- `[Aux]` chip → legacy entity data tagged this L2 as an auxiliary risk dimension.
- `[Cross-boundary]` chip → keywords for this L2 appeared in a *different* pillar's rationale. The risk was discussed but filed elsewhere.

### Control Signals (amber ⚠ warning in drill-down)

Triggers when the control rating is `Well Controlled` AND there's an open Critical or High IAG issue on this L2. Applicable by construction — there's an active audit issue.

---

## Slide 5 — Rating (Severity)

**The tool does NOT tell you the right rating.** Legacy Rating is a starting reference only — it was computed against a differently-scoped legacy pillar and may not translate cleanly to the new L2.

### What you work with today

| Input | What it means |
|---|---|
| Legacy Rating (direct mappings only) | Old pillar rating carried forward. Starting reference. |
| Parsed likelihood / impact dimensions | If the legacy rationale contained explicit language (e.g., "Likelihood: Medium, Impact: High"), it's extracted into dimensions. |
| Your professional judgment | The final answer. |

### What's coming (RCO deliverable, due May 15)

- **Per-L2 rating guidance** — what Low / Medium / High / Critical look like for this specific L2.
- Once available, the tool surfaces guidance alongside each applicable row.
- Cross-entity consistency improves because everyone's rating against the same criteria.

### Until then

- Use Legacy Rating as a reference point, not the answer.
- Calibrate within your team before submitting — don't let similar entities end up with wildly different ratings because different reviewers interpreted "High" differently.
- When you override Legacy Rating, leave a one-line note explaining why. The RCO review catches outliers, but a note gives them context.

---

## Slide 6 — Control Assessment

For each applicable L2, the drill-down shows a **Control Assessment** block. It has two parts:

### Rating + audit context (one line)

Example: `[Well Controlled]  Last audit Satisfactory · September 2025 · next planned March 2027`

- The pill is the last independent audit's effectiveness rating.
- The context line tells you *when* and *what* the last assessment was.
- If the entity hasn't had a recent engagement, this line may show fewer segments or "No engagement rating available."

### Amber warning (when it applies)

Fires when the rating is `Well Controlled` AND there's at least one open Critical or High IAG issue on this L2.

> ⚠ Open High issue below — review whether this rating reflects current state

**What it means:** The rating and the evidence disagree. Your control rating for this L2 probably shouldn't stay "Well Controlled."

### The evidence channels

Below the drill-down body, two mini-tables:

- **IAG Issues** — one row per open audit finding tagged to this L2 (ID, Title, Severity pill, Status pill). Header shows the severity mix.
- **Operational Risk Events** — one row per ORE mapped to this L2 via TF-IDF (ID, Title, Class pill, Status pill). Header shows the class mix.

For PRSA issues, GRA RAPs, and BMA cases — see the Source Data tab. These are currently shown at the entity level (not yet mapped to individual L2s).

### What you do

1. Start from the audit baseline rating.
2. Adjust based on severity and volume of open findings + OREs.
3. If the amber warning fires, your control rating almost certainly shouldn't remain Well Controlled.
4. Enter your final control effectiveness assessment in AERA.

---

## Slide 7 — Working Through an Entity, End-to-End

The sequence for one entity:

1. **Open the report** → select entity from the sidebar.
2. **Scan the Risk Profile tab.** Rows at the top need the most attention (Undetermined / Needs Review / Assumed N/A).
3. **For each row you pause on, expand its Drill-Down:**
   - Read Decision Basis (the "why").
   - Read Key Risks (what the legacy pillar covered).
   - Read Source Rationale (the original text).
   - Check Additional Signals and Control Assessment.
   - Scan the IAG Issues + OREs tables for concrete evidence.
4. **If you need raw data** (full finding description, ORE narrative, policy text, mandate title, 3P name): go to the Source Data tab. Everything's there — you shouldn't need to open Archer.
5. **Decide three things per applicable L2:** applicability (Y/N), inherent rating, control effectiveness.
6. **Record in AERA.** The HTML report is not a submission. AERA is the system of record.

**What makes this efficient:**
- The report is sorted so the first rows are the ones that need judgment. Confirmable rows fall through quickly.
- The Source Data tab replaces 80% of Archer round-trips. Stay in the report.
- If you get stuck on a row, flag it for SME input and move on — don't let one ambiguous L2 hold up the other 22.

---

## Slide 8 — What Your Audit Leader Sees of Your Work

Your leader opens the same report, filtered to their portfolio. Here's what they're spot-checking:

- **Undetermined rows you closed** — did your rationale make sense? Could another reviewer follow your reasoning from your notes?
- **Rating overrides** — rows where you departed from Legacy Rating. Did you explain why?
- **High-severity L2s with thin control evidence** — Critical / High inherent rating but no obvious open findings. Is the rating justified, or is it legacy residue?
- **Amber warnings you triggered** — did you adjust the control rating to match the open issues, or leave it Well Controlled?
- **Inventories that should have flipped applicability** — e.g., an entity with 5 critical apps but Information Security marked N/A.

**What to do for them:**
- Write short notes when you override, even one line. *"Entity exited retail lending in 2024 — no longer applicable"* beats silence.
- Escalate anything you're genuinely unsure about. Flagging a row is better than making a silent judgment call you can't defend.
- Finish entities you start. Half-reviewed entities are the hardest thing for a leader to review.

---

## Slide 9 — What Change Directors See

Directors don't look at row-level decisions. They watch portfolio-level progress:

- **Entity coverage** — how many entities have completed their Phase 2 assessment.
- **Undetermined backlog** — count of Undetermined rows across the portfolio. Rising count is a blocker signal.
- **RCO dependencies** — entities blocked waiting on RCO rating guidance (due May 15) vs. entities closeable today.
- **Escalation counts** — rows flagged for SME input.

**What they need from you:**
- Predictable cadence. Finish the entities you start.
- Keep "escalated" rows moving — they become bottlenecks if they sit.
- Raise RCO-gap rows early, not at the deadline. The more the RCOs see what's stuck on their guidance, the faster the guidance gets written.

---

## Slide 10 — The Tool Is the Map, AERA Is the Destination

One more time, because it's the thing teams get wrong most:

- The HTML report shows you what the tool thinks and why, with every piece of evidence you'd normally look up in Archer surfaced alongside the row.
- You don't fill anything in on the report. It's read-only by design.
- All final decisions — applicability, rating, control effectiveness — go into AERA.
- The workbook is preserved as the evidence trail for your decisions. If a reviewer asks "why did you confirm X applicable?", the answer is in the Decision Basis + Source Rationale + Signals that were visible when you made the call.

**Three questions in, three answers out, recorded in AERA. That's the whole job.**

---

## Appendix A — What the Tool Pulls In

The new taxonomy has 23 L2 risk categories. For every audit entity, the tool consolidates data spread across many different sources into one view per row.

### Legacy assessment
- 14 legacy risk pillars per entity: rating + rationale + control assessment + control rationale
- Sub-risk descriptions per pillar
- Last engagement rating, last audit date, next planned audit date

### Evidence of control issues
- **IAG Issues** — open audit findings from Internal Audit engagements
- **Operational Risk Events (OREs)** — loss events and near-misses, with severity classification
- **PRSA Issues** — Process Risk Self-Assessment control problems from first-line owners
- **GRA RAPs** — regulatory findings and enterprise-level exam results
- **Business Monitoring Activities** — open cases with AERA impact

### Entity composition
- IT applications (primary + secondary) with Confidentiality / Availability / Integrity ratings
- Third-party engagements (primary + secondary)
- Models tagged to the entity
- Policies, standards, procedures
- Applicable laws + additional regulatory mandates

### Entity relationships
- Handoffs from and to other audit entities
- Auxiliary risk dimensions tagged in AXP + AENB

### External validation (from Risk Category Owners)
- Validated keyword maps per L2 (reduces false positives)
- Known AE lists per L2 (entities that always carry this risk)
- Rating guidance per L2 (due May 15 — critical path)

**Doing this manually means opening roughly 10 different systems or tabs per entity, every assessment cycle. The tool pulls it all in once, joins it to the new taxonomy, and puts the context you need on the same row as the decision you're making.**

---

## Appendix B — How the Tool Decides

The tool uses three main techniques to match inputs to the new taxonomy. No single technique does the whole job — they stack.

### Structural mapping (the easy cases)
Some legacy pillars map 1:1 to a new L2 — legacy Model pillar → Model L2, legacy Third Party → Third Party, legacy Reputational → Reputation, etc. The tool carries the assessment forward as-is. No inference needed.

### Keyword matching (the evidence cases)
For legacy pillars that map to *multiple* L2s (e.g., the Operational pillar splits across nine different new L2s), the tool reads the legacy rationale and key risk descriptions and searches for keywords defined for each candidate L2. If keywords for a specific L2 show up, it proposes that row Applicable and records which keywords hit. If none of the sibling L2s match, it flags as "No Evidence Found — Verify N/A."

### Text similarity (for Operational Risk Events)
OREs are free-text descriptions of actual loss events. They don't map through a legacy pillar. The tool compares each ORE description against the definition of each L2 using a text-similarity technique (TF-IDF — a standard way of measuring how closely two pieces of text overlap in meaningful terms) and assigns the ORE to the L2(s) whose definition matches most closely.

### AI review (for the ambiguous ones)
Some legacy assessments explicitly rate a pillar "not applicable" with brief rationale. The tool asks an AI reviewer to read the rationale and either confirm the N/A or flag it for human review if the reasoning is unclear.

### Contradiction flagging
When the control rating for an L2 is "Well Controlled" but there's an open Critical or High audit finding on the same L2, the tool flags the rating-vs-evidence mismatch so you can decide whether the rating still holds.

**The principle across all of this:** every proposal comes with its evidence. Decision Basis explains *why*, Source Rationale shows the original text, Signals flag what else the tool noticed. You can always see the reasoning — if you disagree, override with confidence.

---

## Appendix C — What the Tool Does Not Do

Being honest about the limits matters more than listing the features.

### It does not tell you the right rating
Legacy Rating is a starting reference. What Low / Medium / High / Critical *mean* under the new L2 definition comes from RCO rating guidance (due May 15). Until that lands, rating is professional judgment — the tool does not produce authoritative new-L2 ratings.

### It does not know your entity
Keyword matching finds evidence in the legacy text. It doesn't know that your entity exited a business line in 2024, acquired a new third-party processor last quarter, or has an active remediation that the rationale doesn't mention. Your entity knowledge is the final filter.

### It can miss risks the legacy rationale didn't describe
If a risk is real but wasn't discussed in the legacy text — or was discussed using different words than the keyword map anticipated — the tool won't surface it. "No Evidence Found" is a starting hypothesis, not a conclusion. This is exactly why RCO keyword validation matters: every refinement reduces the chance the tool misses something the language just didn't catch.

### It does not submit to AERA
The report is a working canvas. Everything stays there until you enter your decisions in AERA. The tool is the map; AERA is the system of record.
