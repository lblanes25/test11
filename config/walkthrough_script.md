# Risk Taxonomy Transformer — Proof-Entity Walkthrough Script

**Duration:** 15 minutes
**Audience:** Audit leaders seeing the tool output for the first time
**Goal:** Build trust by showing exactly how the tool works, including a case where it's arguably wrong

---

## Setup

Open the output workbook. Navigate to the **Dashboard** tab to show the portfolio summary.

> "Before we dive into a specific entity, let me show you the overall picture. The Dashboard gives you a Tool Proposals breakdown — how many rows are Applicable, Undetermined, Assumed N/A, Not Applicable, and so on. It also shows how many rows need your judgment and how many have control or additional signals."

Point out the key categories: Applicable (evidence found), AI-Resolved, Applicability Undetermined, Assumed N/A, Not Applicable, and No Legacy Source. Note that the percentage column shows each category's share of total rows.

---

## Select the Demo Entity

Switch to the **Audit_Review** tab. Filter to a single entity that has a mix of statuses — ideally one with:
- At least 2-3 **Applicable** rows (tool found evidence)
- At least 1 **Applicability Undetermined** row (tool couldn't decide)
- At least 1 **Assumed N/A — Verify** row (tool's best guess)
- At least 1 **Not Applicable** row (legacy source was N/A)
- Ideally 1 row confirmed by an IAG issue

> "Let's look at [Entity Name]. This entity has [X] L2 risks to review. Notice they're sorted by priority — the rows the tool couldn't resolve are at the top."

If the entity has an **Unmapped Findings** value in that column, acknowledge it:

> "You may notice a warning here about IAG issues tagged to legacy risk categories that couldn't be mapped to a specific L2. These are preserved in the Source tabs so you can review them, but the tool couldn't assign them to a row."

---

## Walk Through Each Status Type

### 1. Applicable Row (2 minutes)

Pick a row with **Applicable** status and high confidence.

> "This row — [L2 Name] — the tool found strong evidence. Look at the Decision Basis: it says keywords like [X, Y, Z] were found in the [Pillar] rationale. The proposed rating of [Rating] was carried forward from the legacy assessment."

> "Your job here: does this mapping make sense? Read the Source Rationale column — does the text actually discuss [L2]? If yes, confirm. If the rating seems off, you can override it in the Reviewer Rating Override column."

### Quick aside: The evidence trail (30 seconds)

> "One more thing before we move on. If you ever want to see exactly how the tool
> arrived at a determination — every keyword hit, every key risk ID, every individual
> flag — unhide the Side_by_Side tab. It has the complete evidence trail for every
> row: the raw method, individual confidence scores, and every flag column broken out
> separately. You won't need it for most rows, but it's there when you want to verify
> something or understand why two rows for the same L2 got different treatments."

Right-click the tab bar, select Unhide, then select Side_by_Side. Show the same entity's rows. Point out the `method`, `confidence`, `key_risk_evidence`, and individual flag columns. Then re-hide the tab.

> "For your day-to-day review, the Audit Review tab has everything you need. Side by
> Side is the audit trail underneath."

### Quick aside: The Source tabs (1-2 minutes)

Unhide one of the Source tabs — try **Source - Findings** first, then show the tab list.

> "The workbook has six Source tabs behind the scenes: Source - Findings for IAG issues, Source - OREs, Source - PRSA Issues, Source - GRA RAPs, Source - BM Activities, and Source - Key Risks. Each one is the raw data the tool pulled for this portfolio."

> "Tables are pre-sorted so open and active items appear first. The point is: everything you'd normally look up in Archer or another system is already here. You don't need to open Archer."

Re-hide the tab.

### 2. IAG Issue-Confirmed Row (2 minutes)

If available, show a row where an open IAG issue confirms applicability.

> "This one is interesting — the tool found an open IAG issue tagged to this L2. See the Decision Basis: 'Confirmed applicable based on an open IAG issue.' The issue detail is right there. This is the highest confidence determination — there's an active audit issue for this exact risk."

> "Also notice the Control Signals column — it's flagging a contradiction. The control is rated Well Controlled, but there's an open High issue. That's worth discussing with the team."

If an ORE row is visible in the Control Signals or Impact of Issues column, point it out:

> "You may also see ORE events referenced here. OREs now show their classification — Class A means a high-severity event that required escalation. That gives you extra context for the control assessment."

### 3. Applicability Undetermined Row (3 minutes)

Pick an Undetermined row.

> "Now here's where the tool needs your help. This row — [L2 Name] — comes from the [Pillar] pillar, which was rated [Rating]. But the pillar maps to [X] possible L2s, and the rationale text didn't clearly indicate which ones apply."

> "Notice the Proposed Rating is blank. That's intentional — we don't want you to rubber-stamp a rating without thinking about whether this L2 actually applies to this entity."

> "Read the Source Rationale. Does anything in there relate to [L2]? If yes, set Reviewer Status to 'Confirmed Applicable' and enter a rating in Reviewer Rating Override. If not, set it to 'Confirmed Not Applicable.'"

### 4. Assumed N/A — Verify Row (2 minutes)

Pick a "Assumed N/A" row.

> "This row is the tool's best guess. It says: other L2s from the same pillar had evidence, but this one — [L2 Name] — didn't. So the tool assumed it's not applicable."

> "But here's the thing — the tool only looks for specific keywords. If the rationale discusses this risk using different language, the tool won't catch it. Read the rationale and use your judgment."

### 5. Not Applicable Row (1 minute)

> "These rows at the bottom — the tool carried forward 'Not Applicable' from the legacy assessment. They're pre-confirmed. Unless something has changed about this entity's business, you can skip these."

---

## Show a Debatable Case (3 minutes)

Find a row where the tool's proposal is arguably wrong — for example:
- An "Applicable" determination where the keyword match is weak (e.g., matching "process" for Processing, Execution and Change when the rationale is really about a different kind of process)
- A "Assumed N/A" row where the Additional Signals column shows an auxiliary risk flag or application flag suggesting it should be applicable

> "Here's an example where you might disagree with the tool. The tool said [status] because [reason]. But look at the Additional Signals — [signal]. This suggests [L2] might actually be relevant."

> "This is why every row has a Reviewer Status column. The tool gives you a starting point, but your judgment is the final answer."

---

## Demo Three Reviewer Actions (2 minutes)

1. **Confirm an Applicable row:** Type "Confirmed Applicable" in the Reviewer Status cell. Notice the row turns green.

2. **Override a Assumed N/A row to Applicable:** Type "Confirmed Applicable" in Reviewer Status and enter a rating in Reviewer Rating Override. Add a note in Reviewer Notes: "Entity has [X activity] which relates to this L2."

3. **Escalate an Undetermined row:** Type "Escalate" in Reviewer Status. Add a note in Reviewer Notes: "Need SME input on whether [L2] applies given [entity's business]."

---

## Close

> "The tool resolved [X]% of your rows automatically. Your review focuses on the [Y] rows at the top that need judgment. The rest is confirmation. Any questions?"
