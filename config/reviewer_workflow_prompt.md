# Risk Taxonomy Transformer — Reviewer Workflow Redesign Prompt

You are redesigning the reviewer experience for a Risk Taxonomy Transformation tool used by internal audit teams at a large financial institution. The tool ingests legacy 14-pillar risk assessment data and produces a pre-populated Excel workbook that maps each audit entity to 23 L2 risk categories under a new 6-L1 taxonomy. Audit leaders then review the workbook, confirm or override the tool's proposals, and use the reviewed output to complete their risk assessments in the AERA system.

The tool's analytical engine — evidence hierarchy, keyword matching, deduplication, and signal flagging — is already built and working. Your task is to redesign the **output workbook structure, reviewer workflow, and supporting materials** so that audit leaders can review efficiently, make confident decisions, and track progress across their full portfolio.

---

## Context: What the Tool Produces Today

For each entity–L2 combination, the tool proposes one of five statuses:

- **Applicable** — Evidence (keyword matches in rationale/sub-risk descriptions, or open findings) supports this L2 applying to the entity. Legacy ratings are carried forward.
- **Applicability Undetermined** — The legacy pillar maps to multiple L2s but the rationale didn't clearly indicate which ones apply. All candidates are shown with the legacy rating. The reviewer must decide which apply and mark the rest N/A.
- **Assumed Not Applicable** — Other L2s from the same pillar had evidence, but this one didn't. Assumed N/A unless the reviewer overrides.
- **Not Applicable** — The legacy pillar was explicitly rated N/A.
- **Not Assessed** — No legacy pillar maps to this L2 at all (structural gap).

The tool also surfaces additional signals per row: control contradiction flags, IT application/third-party engagement tags, auxiliary risk dimension flags, and cross-boundary keyword hits from other pillars' rationales.

The current workbook has nine tabs: Methodology, Transformed_Upload, Audit_Review, Review_Queue, Side_by_Side, Legacy_Original, Findings_Source, Sub_Risks_Source, Overlay_Flags.

---

## Design Requirements

Apply all of the following requirements when redesigning the workbook and workflow. Where requirements involve specific columns, tab structures, formulas, or formatting, provide concrete implementation details — not just principles.

### 1. Onboarding & Trust-Building Materials

Design the following supporting materials that help an audit leader trust the tool's output before they begin reviewing:

**A. One-page visual decision tree (PDF).** Create a flowchart showing how the tool arrives at each status. Cover these paths:
- Legacy pillar rated N/A → all mapped L2s marked Not Applicable
- Legacy pillar maps 1:1 to a single L2 → direct mapping, Applicable with high confidence
- Legacy pillar maps to multiple L2s → keyword scoring against rationale and sub-risk descriptions → L2s with evidence are Applicable, L2s without evidence are "No Evidence Found — Verify N/A," and if no L2s have evidence then all candidates are Applicability Undetermined
- Open finding tagged to an L2 → that L2 is Applicable regardless of keyword matching
- LLM override file applied → overrides replace low-confidence determinations

The flowchart should be clean enough to print and keep next to a monitor. Use plain language, not method names from the code.

**B. Proof-entity walkthrough script.** Write a 15-minute walkthrough script that an implementation lead can use to demo the tool to an audit leader. The script should:
- Use a single entity that has a mix of statuses (at least one Applicable, one Undetermined, one Assumed N/A, one Not Applicable, and ideally one confirmed by a finding)
- Walk through each row in Audit Review for that entity, explaining what the tool found and why
- Show how to cross-reference the Side_by_Side tab for raw evidence
- Show one case where the tool's proposal is arguably wrong, demonstrating that review is genuine
- End with the reviewer making three decisions: confirming one Applicable row, overriding one Assumed N/A to Applicable, and escalating one Undetermined row

**C. Portfolio summary statistics.** Before the reviewer opens any row, the Dashboard tab (see Section 6) should show aggregate stats for their portfolio:
- Total audit entities
- Total entity–L2 rows
- Breakdown by proposed status (count and percentage)
- Count of rows with additional signals (control contradictions, cross-boundary flags, etc.)
- Estimated review effort: "X rows require active decisions, Y rows are pre-confirmed"

The goal is to let the reviewer see that the tool resolved the majority of rows with high confidence, making the remaining review workload manageable.

**D. FAQ section on the Methodology tab.** Add a "Common Questions" section at the bottom of the Methodology tab covering:
- "What if I disagree with the tool?" → Change Reviewer Status, add notes; the tool never overwrites your decisions.
- "How were keywords chosen?" → Brief explanation of the keyword map and how it was validated.
- "What does 'no evidence' actually mean?" → The tool searched the rationale text and sub-risk descriptions for specific keywords associated with this L2. No keyword match doesn't mean the L2 definitely doesn't apply — it means the available text didn't contain the terms the tool looks for.
- "Can I add a rating to a 'Not Assessed' L2?" → Yes, if you determine it's applicable through your own knowledge.

---

### 2. Review Sequencing

**Entity-first, not status-first.** The workbook must support reviewing all 23 L2 rows for a single entity before moving to the next entity. Context-switching between entities is cognitively expensive — the reviewer needs to hold the entity's business model, products, geography, and control environment in mind.

**Within each entity, sort rows in this order:**
1. Applicability Undetermined (highest judgment required)
2. Rows with any non-blank Additional Signals (the tool flagged something unexpected)
3. No Evidence Found — Verify N/A (quick scan against reviewer's knowledge)
4. Applicable with High or Critical proposed rating (spot-check the most consequential determinations)
5. Applicable with Low or Medium proposed rating (light-touch review)
6. Not Applicable (confirm and move on)
7. Not Assessed (confirm or assess from scratch)

**Entity ordering across the portfolio:** Sort entities by audit leader assignment so each leader reviews their own entities first. Within a single leader's entities, no specific order is required — let the reviewer choose via filter.

**Implementation:**
- Add an Entity ID auto-filter/slicer to the Audit Review tab so reviewers can select one entity at a time.
- Add a sort-key column (hidden) that encodes the within-entity priority above, so the default sort produces this sequence.
- Consider adding an **Entity Profile View**: a pivot-style summary showing one row per entity, one column per L2, with cell values = Proposed Status (color-coded). This lets the reviewer see the full entity profile at a glance before diving into row-level review. This can be a separate tab or a summary block at the top of each entity's row group.

---

### 3. Decision Workflow Per Row

For each status category, define the minimum columns visible by default (left to right) and what's available on expansion.

**Default visible columns (all statuses):**
Entity ID → Entity Name → New L1 → New L2 → Proposed Status → Proposed Rating → Confidence → Decision Basis → Additional Signals → Source Rationale → Legacy Source → Reviewer Status → Reviewer Notes

**Collapsed/grouped columns (available on expand):**
Rating Source, Source Control Rationale, Likelihood, Overall Impact, Impact – Financial, Impact – Reputational, Impact – Consumer Harm, Impact – Regulatory, IAG Control Effectiveness, Aligned Assurance Rating, Management Awareness Rating

**Status-specific requirements:**

- **Applicability Undetermined:** The Decision Basis must clearly state which L2s are the candidates from this legacy pillar and that the reviewer must decide which apply. **Do not carry forward the legacy rating into the Proposed Rating column for these rows.** Leave Proposed Rating blank or show "TBD." Display the legacy source rating in a reference column ("Source Rating") so the reviewer can see it, but force them to actively assign a rating when confirming applicability. This prevents the path-of-least-resistance problem where reviewers confirm all candidates at the legacy rating without thinking.

- **No Evidence Found — Verify N/A (renamed from "Assumed Not Applicable"):** The Decision Basis must name the **sibling L2s from the same legacy pillar that did have evidence.** Example: "Other L2s from the Operational pillar (Processing/Execution, Technology) had keyword matches. This L2 (Data) did not. Assumed not applicable — override if relevant." This gives the reviewer the context to judge whether the tool's assumption is correct.

- **Applicable:** For high-confidence direct mappings, use a shorter Decision Basis format: "Direct from [Pillar] (rated [Rating])." Reserve the longer narrative for evidence-match and multi-mapping rows. Show the sub-risk evidence string for evidence-based matches.

- **Not Applicable / Not Assessed:** Minimal display. One-line Decision Basis. These are confirm-and-move-on rows.

**Add an L2 definition column (hidden by default, expandable).** For each L2, include a 1–2 sentence scope definition so the reviewer doesn't need to open a separate taxonomy document to understand what an L2 covers.

---

### 4. Individual Decision Support (No Batch Actions)

**Do not build batch decision functionality.** While bulk actions would be faster, they create a significant risk that teams confirm proposals without row-level consideration. Every applicability determination must reflect an individual decision by the reviewer.

However, the tool should still surface patterns to help reviewers make informed individual decisions more quickly:

- **Filter support:** Robust auto-filters on Entity ID, New L1, New L2, Proposed Status, Confidence, and Additional Signals (blank vs. non-blank) so reviewers can focus on specific slices.
- **Contextual cues in Decision Basis:** When the tool notices a pattern (e.g., an entity has no IT applications tagged), state this in the Decision Basis for the relevant L2 rows: "No IT applications are mapped to this entity. Consider whether Technology risk applies." This informs the individual decision without making it for them.
- **Pre-populated Reviewer Status for unambiguous cases only:** For rows where the legacy source was explicitly rated N/A (status = Not Applicable) and for structural gaps (status = Not Assessed), pre-populate Reviewer Status = "Confirmed Not Applicable" or leave blank respectively. For all other statuses — including direct mappings with high confidence — leave Reviewer Status blank so the reviewer must actively confirm. The only exception: if the team explicitly opts in to pre-confirming direct/high-confidence rows, this can be toggled in configuration, but it should default to off.

---

### 5. Escalation & Collaboration

**Add an Escalation Tracker tab** with the following columns:
- Entity ID
- Entity Name
- New L2
- Escalation Reason (pulled from Reviewer Notes when Reviewer Status = "Escalate")
- Escalated By (reviewer name)
- Escalated Date
- Assigned To (SME or second-line contact — filled in by coordinator)
- Response (SME's input)
- Resolution (final determination)
- Resolution Date

This tab should auto-populate from rows where Reviewer Status = "Escalate" in the Audit Review tab. The Escalation Reason should pull from the corresponding Reviewer Notes cell.

**Define three escalation scenarios and what context the recipient needs:**

1. **"I don't understand this L2 well enough"** → Route to L2 subject matter expert. Provide: Entity overview, L2 definition, legacy source pillar and rationale, any additional signals.

2. **"The signals conflict"** (e.g., Well Controlled rating + open High finding) → Route to the issue owner or control assessment owner. Provide: Entity ID, L2, control rating, finding ID, severity, status, and the control flag text.

3. **"I disagree with the tool and want a second opinion"** → Route to peer reviewer or audit leader supervisor. Provide: Entity ID, L2, tool's proposed status and basis, reviewer's concern (from Reviewer Notes).

**Add a "Copy Row Summary" function** (VBA macro or formula-generated text column) that formats the key columns for a single row into a clean, email-ready summary. This lets reviewers quickly share context when escalating without manually copying and pasting.

---

### 6. Completion Tracking — Dashboard Tab

**Add a Dashboard tab as the first tab in the workbook.** This tab must be formula-driven (COUNTIFS referencing the Audit Review tab) so it updates automatically as reviewers fill in Reviewer Status values.

**Section A: Portfolio Summary (top of Dashboard)**
- Total audit entities in portfolio
- Total entity–L2 rows
- Entities fully reviewed (all 23 L2s have Reviewer Status filled in): count and percentage
- Entities in progress (at least one Reviewer Status filled, but not all 23): count and percentage
- Entities not started (zero Reviewer Status values): count and percentage
- Total rows reviewed vs. pending vs. escalated (pending resolution)
- A simple progress indicator (percentage complete)

**Section B: Entity Summary Table (one row per audit entity)**
- Entity ID
- Entity Name
- Audit Leader
- Total L2s: 23
- Confirmed Applicable: count
- Confirmed Not Applicable: count
- Escalated (pending): count
- Not Yet Reviewed: count (Reviewer Status blank)
- % Complete: (23 − not yet reviewed − escalated pending) / 23
- Missing Ratings: count of rows where Reviewer Status implies applicable but Proposed Rating is blank and no Reviewer Rating Override is provided

**Section C: Status Distribution (summary counts)**
- Rows by Proposed Status (before review): count per status
- Rows by Reviewer Status (after review): count per status
- Disagreement count: rows where Reviewer Status implies a different determination than Proposed Status

**"Done" is defined at three levels:**
1. **Row complete:** Reviewer Status is not blank.
2. **Entity complete:** All 23 L2 rows have Reviewer Status filled, no unresolved escalations, every Confirmed Applicable row has a rating.
3. **Portfolio complete:** All entities at level 2, all escalations resolved, QA checks passed.

---

### 7. Output & Handoff

**Remove the Transformed_Upload tab.** Reviewers will use the reviewed Audit Review tab as a reference to manually complete their assessments in the AERA system. The workbook is a decision-support tool, not a system upload file.

**QA Checks — Add a QA Results tab** that runs validation checks via formulas and displays pass/fail for each check. Checks to include:

1. **No Applicability Undetermined remaining.** Every row must have a Reviewer Status. Flag any row where Reviewer Status is blank.
2. **No unresolved escalations.** Every row with Reviewer Status = "Escalate" must have a corresponding Resolution in the Escalation Tracker. Flag any open escalations.
3. **Every Confirmed Applicable row has a rating.** If Reviewer Status implies applicable and both Proposed Rating and Reviewer Rating Override are blank, flag it.
4. **No impossible rating values.** Likelihood and impact values must be 1–4, control values 1–4, where present.
5. **Entity completeness.** Every entity must have exactly 23 L2 rows. Flag any entity with a different count.
6. **No duplicate entity–L2 combinations.** Flag any duplicates.
7. **Reviewer coverage.** Show the count and list of rows with blank Reviewer Status.

For each failing check, list the specific Entity ID + L2 combinations that fail so the reviewer can navigate directly to them.

**Add a Review Log tab** that captures an audit trail:
- Row identifier (Entity ID + L2)
- Reviewer Name
- Timestamp
- Action (Confirmed Applicable / Confirmed Not Applicable / Escalated / Rating Overridden)
- Previous Proposed Status
- Reviewer Status
- Reviewer Notes

This can be driven by a VBA macro triggered on changes to Reviewer Status or Reviewer Rating Override columns in Audit Review. If VBA is not feasible, include instructions for the reviewer to manually log significant overrides.

---

### 8. Workbook Tab Structure (Revised)

Restructure from nine tabs to this layout:

| Tab | Visibility | Purpose |
|-----|-----------|---------|
| **Dashboard** | Visible, first tab | Portfolio summary, entity completion table, progress tracking |
| **Audit Review** | Visible, primary workspace | All entity–L2 rows with reviewer columns; this is where decisions happen |
| **Escalation Tracker** | Visible | Escalated items with routing, response, and resolution tracking |
| **QA Results** | Visible | Pre-submission validation checks with pass/fail and failing row details |
| **Methodology** | Visible | Tool logic explanation, status definitions, column legend, FAQ |
| **Review Queue** | Hidden (unhide on demand) | Filtered view of Undetermined and No Evidence rows — useful as a checklist but redundant with filtered Audit Review |
| **Side by Side** | Hidden | Full traceability with every internal column; for debugging and audit trail |
| **Source: Legacy Data** | Hidden | Unmodified legacy risk data as ingested |
| **Source: Findings** | Hidden | All findings with disposition and L2 mapping |
| **Source: Sub-Risks** | Hidden | All sub-risk descriptions with keyword contribution |
| **Overlay Flags** | Hidden | Country risk overlay details |
| **Review Log** | Visible | Audit trail of reviewer actions |

---

### 9. Status and Column Naming Changes

**Rename statuses for clarity:**
- "Assumed Not Applicable" → **"No Evidence Found — Verify N/A"** (This prevents reviewers from treating it as a final determination. The name makes clear that the reviewer must verify.)
- All other status names remain as-is.

**Expand Reviewer Status dropdown options:**
- Confirmed Applicable
- Confirmed Applicable — Rating Adjusted (use when Reviewer Rating Override is populated)
- Confirmed Not Applicable
- Escalate

**Separate control contradiction flags from the Additional Signals column.** Control contradictions (e.g., "Well Controlled but open High finding") are high-value, actionable signals. Cross-boundary keyword flags are lower-signal and higher-noise. If they share a column, reviewers will learn to ignore the entire column once they encounter a few irrelevant cross-boundary flags. Create two columns:
- **Control Signals** — control contradiction flags only
- **Additional Signals** — application/engagement tags, auxiliary risk flags, cross-boundary flags

**Set a minimum threshold for cross-boundary flags.** Require at least 2 keyword hits from a single pillar's rationale or sub-risks before generating a cross-boundary flag. Single common-keyword hits generate too much noise.

---

### 10. Formatting and UX Details

- **Freeze panes:** Freeze Entity ID + Entity Name columns and the header row so they remain visible during horizontal scrolling.
- **Color coding by Proposed Status:** Applicable = green, Applicability Undetermined = yellow, No Evidence Found — Verify N/A = orange, Not Applicable = gray, Not Assessed = blue. Apply to the Proposed Status cell only (not the full row) to avoid visual overload.
- **Reviewer columns highlighted:** Reviewer Status, Reviewer Rating Override, and Reviewer Notes columns should have a distinct header color (green) and remain unlocked when sheet protection is active. All other columns are locked.
- **Row height:** Set a minimum row height that accommodates 2–3 lines of wrapped text in the Decision Basis column without requiring the reviewer to manually resize.
- **Entity group separators:** Insert a thin border or shaded separator row between entity groups to visually delineate where one entity ends and the next begins.
- **Data validation on Reviewer Status:** Dropdown list with the four options above. Show an input message on cell select: "Select your determination for this L2 risk."
- **Conditional formatting on Reviewer Status:** When Reviewer Status is filled in, apply a subtle green background to the entire row to visually indicate completion. Rows with Reviewer Status = "Escalate" get a subtle red/orange background.
