# Phase 2 Scope: Risk Taxonomy Transformer

**Date:** April 2026
**Author:** Lurian Blanes
**Status:** Draft — pending SVP decisions from Phase 1 Asks

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
| Fix remaining dropped findings | Add ~50 missing aliases to normalization.py, rerun pipeline, confirm counts | Lurian |
| Production run | Full dataset run to establish baseline resolution percentages for presentation | Lurian |
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

**Expected outcome:** Keyword refinements feed back into the tool (config update). Rating guidance feeds into audit leader training — not the tool itself.

---

### Track 3: Extend Capabilities (Weeks 4-8+)

These are tool enhancements unlocked by Track 1/2 results or SVP decisions.

| Item | Description | Dependency |
|------|-------------|------------|
| IT/InfoSec strategy implementation | Finalize whether IT and InfoSec auto-populate both L2s or require separate determination. Implement whichever direction is chosen. | Ask 5 decided |
| Assumed N/A review policy | Configure tool behavior based on active-review vs. passive-acceptance decision. May affect sorting, flagging, or default status. | Ask 6 decided |
| Rationale generation | If rationales are required for new taxonomy assessments (Ask 1), extend the LLM batch pattern to generate draft control assessment summaries from 1st/2nd/3rd line and regulatory results. | Ask 1 confirmed yes |
| Business monitoring events | Investigate schema and determine if business monitoring results add signal beyond what ORE events already provide. If yes, integrate as additional evidence source. | Ask 4 direction given |
| Broader rollout | Deploy workbooks to all audit leaders. Includes training, walkthrough sessions, and support during first review cycle. | Pilot complete; RCO keyword validation complete |

---

## What Phase 2 Does NOT Include

- **Replacing auditor judgment.** The tool proposes; leaders decide. Phase 2 does not change this.
- **Automating ratings.** Ratings require RCO guidance (Track 2c). The tool carries forward legacy ratings as a starting point but does not generate new ones.
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
| | | |

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

Exact dates depend on SVP decisions from Phase 1 Asks and RCO availability.
