# SVP Presentation Brief: Risk Taxonomy Transformer

**Prepared for:** SVP briefing on the new taxonomy migration tooling
**Date:** April 2026
**Presenter:** Lurian Blanes

---

## 1. The Problem

The institution is migrating from 14 risk pillars to a new taxonomy of 6 L1 categories and 23 L2 risk categories. Over 200 audit entities must be reassessed against the new structure. Each entity requires an applicability determination and risk rating for every L2 category. That is 4,600+ individual decisions.

Done manually, this takes weeks. Each audit leader would need to read legacy rationale text, interpret which new categories apply, cross-reference findings and sub-risk data, and assign ratings -- for every entity in their portfolio. The work is repetitive, error-prone, and pulls experienced auditors away from actual audit work.

---

## 2. Origin

This tool automates the exact methodology the presenter used when reviewing Audit Entity Risk Assessments as QA. The same analytical steps performed manually -- reading rationale text to determine which risk categories apply, cross-referencing sub-risk descriptions for supporting evidence, checking whether open findings confirm a risk is present, flagging contradictions between control ratings and finding severity, and identifying structural gaps where no legacy source covers a new risk category -- are now executed programmatically.

What took hours per entity now runs in minutes across the full portfolio. The logic is not theoretical. It was tested through hands-on QA review before being codified.

---

## 3. What the Tool Produces

The tool produces a multi-sheet Excel workbook that serves as the starting point for every audit leader's taxonomy migration work.

**How it works:** The tool ingests legacy risk assessment data, open findings, sub-risk descriptions, and operational risk events. It maps each legacy pillar to the appropriate new L2 categories using a defined crosswalk. For pillars that map to multiple L2s, it uses keyword evidence scoring against rationale text and sub-risk descriptions to determine which L2s actually apply. It then enriches each row with control effectiveness baselines, parsed rating dimensions, and signal flags.

**What audit leaders see:** A workbook filtered to their entities, sorted by priority. Every row represents one entity-L2 combination with a proposed status, proposed rating, decision basis explaining the determination, and the source evidence that supports it. Leaders work top-down: the rows requiring judgment are at the top, the confirmed rows are at the bottom.

**The five statuses:**

| Status | Meaning |
|--------|---------|
| **Applicable** | Evidence supports this L2 applying to this entity. Rating carried forward from the legacy assessment. |
| **Not Applicable** | The legacy source explicitly rated this pillar as not applicable. |
| **Assumed N/A -- Verify** | Sibling L2s from the same pillar had evidence, but this one did not. The tool assumes not applicable, but the leader should verify. |
| **Applicability Undetermined** | The pillar maps to multiple L2s and the rationale did not clearly indicate which ones apply. All candidates are shown. Rating left blank -- the leader must decide. |
| **No Legacy Source** | No legacy pillar maps to this L2. This is a structural gap in the old taxonomy. The leader must assess from scratch or confirm not applicable. |

**LLM override workflow:** For rows where the deterministic pipeline cannot resolve applicability (primarily Undetermined rows), the tool exports prompts that can be processed through an LLM in batch. The LLM reads the rationale text and makes a judgment call. Those results feed back into the tool as overrides, replacing low-confidence determinations with LLM-informed ones. This capability is built and proven. It handles the ambiguous middle that keyword matching cannot resolve.

---

## 4. Results and Proof of Value

Exact percentages require a production run on the current dataset, but the pattern is consistent across test runs:

- **The tool resolves the majority of rows with evidence.** Direct mappings, keyword-confirmed applicability, finding-confirmed applicability, and explicit N/A determinations account for most of the portfolio.
- **Manual work is concentrated on a small subset.** Undetermined rows (where rationale is ambiguous) and No Legacy Source rows (structural gaps) are the only rows that require judgment from scratch.
- **The LLM override layer further reduces the manual set.** When activated, ambiguous rows that would otherwise require a leader to read rationale and decide are handled by the LLM, with the leader reviewing the LLM's determination rather than starting from zero.

The net effect: audit leaders spend their time on the rows that genuinely need human judgment, not on the thousands of rows where the answer is straightforward.

---

## 5. The Asks

### Ask 1: Timeline for rationale requirements in new taxonomy assessments

It is still being debated whether rationales will be required for the new taxonomy assessments. The presenter needs to know when this will be finalized.

**Why it matters:** If rationales are required, the presenter can extend the same LLM batch approach -- already proven for applicability determinations -- to generate control assessment summaries. These summaries would synthesize 1st line, 2nd line, 3rd line, and regulatory results per entity into draft rationale text. The path is proven. The same pattern that handles applicability works for this next piece. Knowing the direction now allows the presenter to begin scoping the extension rather than reacting after the decision is made.

### Ask 2: Approve Risk Category Owner involvement

Three specific workstreams require RCO participation:

**(a) Keyword map validation.** RCOs validate the keyword listings that drive applicability determinations for their L2 category. Are the right terms included? Are important terms missing? Heather is already on board with this. The keyword listings per risk have been shared.

**(b) Output review.** RCOs review the tool's output for their L2 across all entities. Do they disagree with any of the proposals? This is the cross-entity calibration check that only an RCO can perform.

**(c) L2-level rating guidance.** RCOs develop guidance on what differentiates Low vs. Medium vs. High vs. Critical for their specific L2 risk category. Today, RCSA guidance evaluates risk at the L4 level and uses rules to aggregate upward. There is nothing at the L2 level to anchor rating decisions. Without this guidance, audit teams are rating against L2 categories with no rubric.

**The presenter's hypothesis:** Teams will arrive at similar ratings to what the tool proposes. The output will not change significantly unless more specific guidance is given that steers teams in a different direction. RCO rating guidance is the mechanism that would steer it.

### Ask 3: Approve a pilot with one audit leader

Before full rollout, let one audit leader use the workbook on their entity portfolio. They provide feedback on the workflow, validate that the proposals are reasonable, and confirm the workbook is usable before it goes to the broader team.

### Ask 4: Direction on Business Monitoring events as an evidence source

Business Monitoring events and results exist in structured format, similar to findings. They represent another source of evidence that could confirm whether a risk category applies to an entity. The presenter needs to investigate the schema further but wants to know: should this be in scope?

### Ask 5: IT and InfoSec -- auto-populate both L2s or require separate determination?

Currently, when the legacy IT pillar applies, both Technology and Data are auto-populated as applicable. When InfoSec applies, both Information and Cyber Security and Data are auto-populated. Should this continue, or should teams make a separate applicability judgment for each L2?

### Ask 6: Assumed N/A rows -- active review or accept unless overridden?

When the tool marks a row as "Assumed N/A -- Verify," should teams actively review every such row, or accept the automated determination unless they have independent reason to believe the risk applies? This is a workload trade-off: active review is more thorough but adds volume; passive acceptance is efficient but risks missing cases where the tool's keyword matching failed to detect an applicable risk.

---

## 6. Risks and Limitations

**~50 findings with unmappable L2 risk categories.** A small number of findings have L2 risk category values that do not map to the new taxonomy (blank or unrecognized values). These need alias additions in the normalization layer. Until fixed, the tool may undercount finding-confirmed applicability for a small number of entities.

**Trust is the bottleneck.** If the first entity an audit leader reviews looks wrong -- a bad mapping, a missing finding, an obviously incorrect determination -- they will lose confidence in the tool and redo everything manually. The walkthrough script and pilot (Ask 3) are designed to manage this. First impressions determine adoption.

**The tool solves applicability, not ratings.** The tool determines which L2 risks apply to each entity and carries forward legacy ratings as a starting point. But legacy ratings were assigned under a differently-scoped risk category and may not be appropriate for the new L2. Accurate L2-level ratings require rating guidance from Risk Category Owners -- guidance that does not exist yet. That is Ask 2c.

**Keyword matching has limits.** The deterministic pipeline relies on keyword evidence. If a rationale discusses a risk using language the keyword map does not include, the tool will miss it. RCO keyword validation (Ask 2a) mitigates this, and the LLM override layer handles cases where keyword matching is insufficient.

---

## 7. Suggested Demo

**Duration:** 15 minutes
**Format:** Live walkthrough of one entity in the output workbook

1. Open the Dashboard tab. Show the portfolio summary: total rows, how many the tool resolved with evidence, how many need review.
2. Filter the Audit Review tab to a single entity with a mix of statuses.
3. Walk through one row of each status type -- Applicable, Not Applicable, Assumed N/A, Undetermined, No Legacy Source -- showing the Decision Basis and source evidence for each.
4. Show a debatable case where the tool's proposal is arguably wrong. Demonstrate the Reviewer Status override workflow.
5. Show the Side by Side tab (hidden by default) as the full evidence trail for anyone who wants to verify the logic.

The goal is to show the VP both the value (the tool did most of the work) and the honesty (here is where it needs human judgment, and here is how leaders provide it).

### If You Only Have 5 Minutes

Skip the walkthrough. Open the workbook and do this:

1. **Dashboard tab, 30 seconds.** Point at the status distribution. "The tool resolved X% of 4,600 rows with evidence. Y% need team judgment. The rest are structural gaps in the old taxonomy."
2. **Filter to one entity, 60 seconds.** Show the 23 rows. "Every entity gets this. Sorted by priority — the rows needing judgment are at the top, confirmed rows at the bottom."
3. **Read one Decision Basis aloud, 30 seconds.** Pick an Applicable row with evidence. "This is what the tool tells the leader: which pillar it came from, what keywords matched, what the legacy rating was."
4. **Show one Undetermined row, 30 seconds.** "This is where the tool is honest. It couldn't decide, so it shows all candidates and asks the leader to choose."
5. **State the asks, 90 seconds.** Go straight to the six asks. Lead with Ask 1 (rationale timeline) and Ask 3 (pilot approval) — those are the two that unblock the most work.

**What NOT to do in 5 minutes:** Don't explain how the keyword matching works. Don't show hidden tabs. Don't demo the LLM workflow. The VP needs to see the output and hear the asks.

---

## 8. Anticipated VP Questions

**"How accurate is it?"**
The tool does not make subjective judgments -- it maps evidence to categories. For direct mappings (one pillar to one L2), accuracy is definitional. For multi-target mappings, accuracy depends on the keyword map, which RCOs will validate (Ask 2a). The LLM layer handles ambiguous cases the keywords cannot resolve. Exact resolution percentages require a production run, but the majority of rows resolve with evidence across test runs.

**"Why not just use AI for everything?"**
The deterministic pipeline handles the majority of rows -- direct mappings, keyword matches, finding confirmations, explicit N/A carryovers. These do not need AI; they need structured logic. The LLM layer is reserved for the ambiguous middle: rows where the rationale text is unclear and keyword matching cannot determine applicability. This approach is more transparent, more auditable, and cheaper than running every row through an LLM.

**"When will this be done?"**
Phase 1 is code-complete. All 21 deliverables are built, tested, and working. This is a deployment conversation, not a development conversation. The open items are the decisions in the Asks section and the findings drop validation.

**"What about ratings?"**
The tool carries forward legacy ratings as a starting point. Legacy ratings were assigned under the old 14-pillar taxonomy and may not map cleanly to the new L2 categories. Accurate L2-level ratings require rating guidance: what makes a risk Low vs. Medium vs. High vs. Critical for a specific L2? That guidance does not exist yet. Risk Category Owners need to develop it. That is Ask 2c. Until it exists, teams are rating against L2 categories with no rubric.

**"What if audit leaders don't trust the output?"**
Trust is earned one entity at a time. The pilot (Ask 3) lets one leader validate the tool before broad rollout. The walkthrough script builds trust in the first 15 minutes by showing exactly how the tool works, including a case where it is arguably wrong. The Decision Basis column on every row explains why the tool made each determination. Transparency is the trust strategy -- not polish.

**"What does this cost to run?"**
The tool is a Python script that runs locally. No infrastructure, no licenses, no ongoing cost. The LLM override workflow uses batch API calls, which have a per-token cost, but only for the subset of ambiguous rows -- not the full portfolio.
