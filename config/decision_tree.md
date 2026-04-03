# Risk Taxonomy Transformer — Decision Tree

How the tool determines the status for each L2 risk per entity.

## Decision Flow

```
START: For each legacy pillar rating on this entity
  |
  |-- Was the legacy pillar rated "Not Applicable"?
  |     YES --> All mapped L2s = NOT APPLICABLE
  |             (Reviewer Status pre-filled: "Confirmed Not Applicable")
  |
  |-- Does this pillar have no rationale column? (IT, InfoSec, Third Party)
  |     YES --> All primary L2s = APPLICABLE (direct, high confidence)
  |             (No keyword matching needed — both L2s always apply)
  |
  |-- Is this a direct 1:1 mapping? (e.g., Model, Financial Reporting)
  |     YES --> Single L2 = APPLICABLE (direct, high confidence)
  |             Legacy rating carried forward as proposed rating
  |
  |-- Is this a multi-target mapping? (e.g., Operational -> 6 L2s)
  |     YES --> Check for LLM overrides first
  |             |
  |             |-- LLM override exists for this entity+pillar+L2?
  |             |     YES --> Use LLM determination (applicable or not applicable)
  |             |
  |             |-- No override: Score rationale + sub-risk text against keywords
  |                   |
  |                   |-- 3+ keyword hits for this L2?
  |                   |     YES --> APPLICABLE (high confidence)
  |                   |
  |                   |-- 1-2 keyword hits for this L2?
  |                   |     YES --> APPLICABLE (medium confidence)
  |                   |
  |                   |-- Zero hits for this L2, but other L2s matched?
  |                   |     YES --> NO EVIDENCE FOUND -- VERIFY N/A
  |                   |             "The tool found no keywords for this L2 in the
  |                   |              rationale, but other L2s from the same pillar
  |                   |              did match. Verify whether this L2 applies."
  |                   |
  |                   |-- Zero hits for ANY L2 from this pillar?
  |                         YES --> APPLICABILITY UNDETERMINED
  |                                 All candidate L2s populated with legacy rating.
  |                                 Reviewer must decide which apply.
  |
  |-- Does this entity have an open finding tagged to this L2?
  |     YES --> APPLICABLE (confirmed by finding, regardless of keyword matching)
  |             Finding detail shown in Decision Basis
  |
  |-- Is there a Country risk overlay?
        YES --> Flags target L2s as amplified (informational only, no status change)
```

## Additional Signals (do not change status, only flag for reviewer attention)

- **Control Contradiction**: Legacy control rated "Well Controlled" but an open High/Critical finding exists for this L2
- **Application/Engagement Flag**: IT applications or third party engagements are tagged to this entity, suggesting Technology/Data/InfoSec/Third Party may be applicable
- **Auxiliary Risk Flag**: This L2 was listed as an auxiliary risk in the entity's legacy data
- **Cross-Boundary Flag**: Keywords for this L2 were found in a different pillar's rationale (2+ hits required)

## Reviewer Actions by Status

| Status | What the reviewer does |
|--------|----------------------|
| Applicability Undetermined | Read the rationale. Decide which candidate L2s apply. Mark the rest "Confirmed Not Applicable." |
| No Evidence Found -- Verify N/A | Read the rationale and consider the entity's business. Confirm N/A or override to Applicable. |
| Applicable | Verify the mapping makes sense. Check the proposed rating. Confirm or adjust. |
| Not Applicable | Legacy source was N/A. Pre-confirmed. Override only if circumstances changed. |
| Not Assessed | No legacy pillar covers this L2. Assess from scratch if needed. |
