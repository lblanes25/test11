# Phase 2 Scope: Risk Taxonomy Transformer

**Date:** April 2026
**Author:** Lurian Blanes
**Status:** Active — SVP decisions received 2026-04-07

---

## Phase 1 Summary

Phase 1 delivered a production-ready tool that automates 4,600+ taxonomy migration decisions across 200+ audit entities. The pipeline, workbook output, Streamlit dashboard, LLM override workflow, ORE event integration, and reviewer workflow are all built and operational. Phase 1 is code-complete.

**Remaining Phase 1 cleanup:** ~50 findings with unmappable L2 risk categories need alias additions in normalization.py. Minor data quality fix, not a feature gap.

---

## Phase 2 Definition

Phase 2 transitions the tool from **built** to **adopted**. The work falls into three tracks, sequenced by dependency.

---

### Track 1: Validate and Deploy (Weeks 1-3)

These items have no dependency on SVP decisions and can begin immediately.

| Item | Description | Owner |
|------|-------------|-------|
| Rating carryforward change | Blank Proposed Rating for non-direct mappings. Legacy rating preserved in Source Rating column. **Done.** | Lurian |
| Fix remaining dropped findings | Add ~50 missing aliases to normalization.py, rerun pipeline, confirm counts | Lurian |
| Production run | Full dataset run to establish baseline resolution percentages (run without LLM overrides for honest baseline) | Lurian |
| Pilot with one audit leader (Ask 3) | One leader uses the workbook on their portfolio; collects feedback on workflow, proposals, and usability | Lurian + pilot leader |
| Incorporate pilot feedback | Adjust workbook layout, decision basis messaging, or priority sorting based on pilot results | Lurian |

---

### Track 2: RCO Engagement (Weeks 2-6)

Requires Ask 2 approval. Three parallel workstreams with Risk Category Owners.

| Workstream | Description | Dependency |
|------------|-------------|------------|
| **(a) Keyword validation** | RCOs review and refine the ~450 keywords mapped to their L2 categories. Heather already engaged. Remaining RCOs need assignment. | Ask 2a approved |
| **(b) Output review** | RCOs review tool output for their L2 across all entities. Cross-entity calibration check — do proposals look reasonable? | Ask 2b approved; production run complete |
| **(c) L2 rating guidance** | RCOs develop what differentiates Low / Medium / High / Critical for their specific L2. No L2-level rubric exists today. Without it, teams rate without a standard. | Ask 2c approved |

| **(d) AE-to-RCO mapping** | Align which audit entities apply to each RCO. Lurian working with Heather to get the list. RCOs have domain knowledge about which entity types/business units should carry their risk. Tool will use this to flag missing L2s and pre-populate applicability. | Heather provides mapping |

**Expected outcome:** Keyword refinements feed back into the tool (config update). Rating guidance feeds into the tool when available. AE-to-RCO mapping enables top-down applicability rules that complement bottom-up evidence.

---

### Track 3: Extend Capabilities (Weeks 4-8+)

These are tool enhancements unlocked by Track 1/2 results or SVP decisions.

| Item | Description | Dependency |
|------|-------------|------------|
| IT/InfoSec strategy implementation | Finalize whether IT and InfoSec auto-populate both L2s or require separate determination. Implement whichever direction is chosen. | Ask 5 decided |
| Assumed N/A review policy | Configure tool behavior based on active-review vs. passive-acceptance decision. May affect sorting, flagging, or default status. | Ask 6 decided |
| Rationale generation | If rationales are required for new taxonomy assessments (Ask 1), extend the LLM batch pattern to generate draft control assessment summaries from 1st/2nd/3rd line and regulatory results. | Ask 1 confirmed yes |
| Business monitoring events | Investigate schema and determine if business monitoring results add signal beyond what ORE events already provide. If yes, integrate as additional evidence source. | Ask 4 direction given |
| RCO guidance integration | When RCO rating guidance becomes available, integrate into tool to inform proposed ratings for non-direct mappings. | Track 2c guidance delivered |
| AE-to-RCO applicability rules | Use AE-to-RCO mapping to flag entities missing expected L2s and pre-populate applicability for entity types RCOs say always apply. | Track 2d mapping delivered |
| Legacy Ratings Lookup enhancement | Add entity metadata header (entity name, audit leader, PGA, last audit date) that populates when filtered — portable Archer entity screen experience without Archer load times. | Pilot feedback |
| Broader rollout | Deploy workbooks to all audit leaders. Includes training, walkthrough sessions, and support during first review cycle. | Pilot complete; RCO keyword validation complete |

---

## What Phase 2 Does NOT Include

- **Replacing auditor judgment.** The tool proposes; leaders decide. Phase 2 does not change this.
- **Automating ratings.** Ratings require RCO guidance (Track 2c). Only direct 1:1 mappings carry forward legacy ratings; all others are blank until guidance exists.
- **Building a production application.** The tool remains a locally-run Python script with Excel output. No infrastructure, no deployment pipeline, no ongoing hosting cost.

---

## Success Criteria

| Metric | Target |
|--------|--------|
| Pilot leader validates workbook is usable and proposals are reasonable | Yes/No gate before broader rollout |
| RCO keyword validation complete for all 23 L2 categories | 23/23 |
| Resolution rate on production run (rows resolved with evidence, not requiring judgment from scratch) | Establish baseline; expect >70% |
| Audit leader time per entity reduced vs. manual process | Qualitative feedback from pilot |
| Dropped findings after normalization fix | <10 unmappable |

---

## Decision Log

Decisions made during Phase 2 will be recorded here as they occur.

| Date | Decision | Made By |
|------|----------|---------|
| 2026-04-07 | Stop auto-carrying legacy ratings unless direct 1:1 mapping. Leave Proposed Rating blank for non-direct mappings. | SVP presentation |
| 2026-04-07 | Where RCO rating guidance exists, use it. Design should accept guidance input. No guidance exists currently. | SVP presentation |
| 2026-04-07 | Align which audit entities apply to each RCO. Lurian working with Heather to get AE-to-RCO mapping. | SVP presentation |
| 2026-04-07 | Keith (methodology VP) interested in applying dashboard approach to 12 inventories (apps, models, third parties, etc.). | SVP presentation |

---

## Timeline Summary

```
Week 1-2:  Fix findings, production run, begin pilot
Week 2-4:  RCO keyword validation (parallel with pilot)
Week 3-5:  Incorporate pilot feedback, RCO output review
Week 4-6:  RCO rating guidance development
Week 5-8:  Extend capabilities based on SVP decisions
Week 6+:   Broader rollout (gated on pilot + RCO keyword validation)
```

Exact dates depend on RCO availability and Heather's AE-to-RCO mapping delivery.

---

## Future: Inventory Visibility Dashboard (Keith's Ask)

Keith (methodology VP) expressed interest in applying the dashboard approach to the 12 inventories (applications, models, third parties, etc.). This is a separate initiative that reuses the Streamlit dashboard pattern. Scoping deferred until Phase 2 Track 1 is complete.
