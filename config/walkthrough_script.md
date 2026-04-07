# Risk Taxonomy Transformer — Proof-Entity Walkthrough Script

**Duration:** 15 minutes
**Audience:** Audit leaders seeing the tool output for the first time
**Goal:** Build trust by showing exactly how the tool works, including a case where it's arguably wrong

---

## Setup

Open the output workbook. Navigate to the **Dashboard** tab to show the portfolio summary.

> "Before we dive into a specific entity, let me show you the overall picture. The Dashboard shows how much work the tool handled and how much needs your judgment."

Point out the key metrics: total rows, reviewed vs. pending. Note that the percentage will update as you fill in Reviewer Status values.

---

## Select the Demo Entity

Switch to the **Audit_Review** tab. Filter to a single entity that has a mix of statuses — ideally one with:
- At least 2-3 **Applicable** rows (tool found evidence)
- At least 1 **Applicability Undetermined** row (tool couldn't decide)
- At least 1 **Assumed N/A — Verify** row (tool's best guess)
- At least 1 **Not Applicable** row (legacy source was N/A)
- Ideally 1 row confirmed by a finding

> "Let's look at [Entity Name]. This entity has [X] L2 risks to review. Notice they're sorted by priority — the rows the tool couldn't resolve are at the top."

---

## Walk Through Each Status Type

### 1. Applicable Row (2 minutes)

Pick a row with **Applicable** status and high confidence.

> "This row — [L2 Name] — the tool found strong evidence. Look at the Decision Basis: it says keywords like [X, Y, Z] were found in the [Pillar] rationale. The proposed rating of [Rating] was carried forward from the legacy assessment."

> "Your job here: does this mapping make sense? Read the Source Rationale column — does the text actually discuss [L2]? If yes, confirm. If the rating seems off, you can override it in the Reviewer Rating Override column."

### Quick aside: The evidence trail (30 seconds)

> "One more thing before we move on. If you ever want to see exactly how the tool
> arrived at a determination — every keyword hit, every sub-risk ID, every individual
> flag — unhide the Side_by_Side tab. It has the complete evidence trail for every
> row: the raw method, individual confidence scores, and every flag column broken out
> separately. You won't need it for most rows, but it's there when you want to verify
> something or understand why two rows for the same L2 got different treatments."

Right-click the tab bar, select Unhide, then select Side_by_Side. Show the same entity's rows. Point out the `method`, `confidence`, `sub_risk_evidence`, and individual flag columns. Then re-hide the tab.

> "For your day-to-day review, the Audit Review tab has everything you need. Side by
> Side is the audit trail underneath."

### 2. Finding-Confirmed Row (2 minutes)

If available, show a row where an open finding confirms applicability.

> "This one is interesting — the tool found an open finding tagged to this L2. See the Decision Basis: 'Confirmed applicable based on an open finding.' The finding detail is right there. This is the highest confidence determination — there's an active audit issue for this exact risk."

> "Also notice the Control Signals column — it's flagging a contradiction. The control is rated Well Controlled, but there's an open High finding. That's worth discussing with the team."

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
