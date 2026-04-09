# Risk Assessment Workflow — New Taxonomy

**Purpose:** This document describes the complete workflow an audit team follows to assess risk for an audit entity under the new 6 L1 / 23 L2 taxonomy, using the Risk Taxonomy Transformer tool and supporting inputs from Risk Category Owners.

**Audience:** Audit leaders, Risk Category Owners, methodology team

---

## Overview

Completing a risk assessment for an audit entity under the new taxonomy requires answering three questions for each of the 23 L2 risk categories:

1. **Applicability** — Does this risk apply to this entity?
2. **Inherent Risk Rating** — If applicable, how severe is this risk (Low / Medium / High / Critical)?
3. **Control Assessment** — What is the state of controls for this risk, and what evidence exists of control issues?

The Risk Taxonomy Transformer provides a starting position for all three. Teams review, override, and finalize in AERA.

---

## Step 1: Applicability — "Does this risk apply to my entity?"

The tool proposes applicability for each L2 using multiple evidence sources, layered from strongest to weakest:

### Evidence Sources (in priority order)

| Source | What It Tells You | Strength |
|--------|-------------------|----------|
| **Open IAG findings** tagged to the L2 | An active audit issue exists for this exact risk. Confirms applicability. | Strongest — direct evidence |
| **RCO-provided AE lists** (by business unit / entity type) | The Risk Category Owner has identified this entity type as carrying this risk. | Strong — domain authority |
| **Keyword evidence** from legacy rationale + sub-risk descriptions | The legacy assessment text contains language consistent with this L2. | Moderate — inference from text |
| **Legacy pillar mapping** (direct 1:1) | The legacy pillar maps to exactly one L2. Straightforward carryforward. | Moderate — structural, not evidence-based |
| **Cross-boundary signals** | Keywords for this L2 appeared in a different pillar's rationale. Suggests the risk was discussed but categorized elsewhere. | Weak — informational flag only |

### What the Tool Produces

Each entity × L2 row gets one of these statuses:

| Status | Meaning | Team Action |
|--------|---------|-------------|
| **Applicable** | Evidence supports this L2 applying. | Spot-check the evidence. Confirm or override. |
| **Applicability Undetermined** | Multiple L2 candidates, rationale unclear. All candidates shown. | Read the rationale. Decide which L2s actually apply. |
| **No Evidence Found — Verify N/A** | Sibling L2s had evidence, this one didn't. Tool's best guess is N/A. | Quick check — does your knowledge of the entity suggest this is relevant despite no keyword match? |
| **Not Applicable** | Legacy assessment was explicitly N/A. | Confirm unless entity's business has changed. |
| **Not Assessed** | No legacy pillar maps to this L2. Structural gap in legacy taxonomy. | Assess from scratch if applicable, or confirm N/A. |

### What Makes This Complete

Applicability is fully resolved when:
- RCOs have validated the keyword maps for their L2s (removing false positives, adding missing terms)
- RCOs have provided their known AE lists (which entity types / business units always carry their risk)
- The tool has run with both inputs incorporated

At that point, the tool's proposals reflect both bottom-up evidence (keywords, findings) and top-down domain knowledge (RCO applicability rules). Teams still exercise judgment, but they're reacting to a well-informed starting position rather than building from zero.

---

## Step 2: Inherent Risk Rating — "How severe is this risk?"

For applicable L2s, the team must assign an inherent risk rating: Low, Medium, High, or Critical.

### What the Tool Provides

| Input | What It Tells You |
|-------|-------------------|
| **Legacy rating** (direct mappings only) | The rating assigned under the old taxonomy. Carried forward as a starting point. Blank for non-direct mappings — legacy ratings scoped to a differently-defined risk category should not be assumed to apply. |
| **Parsed likelihood / impact dimensions** | If the legacy rationale contains explicit rating language (e.g., "Likelihood: Medium, Impact: High"), the tool extracts and displays it. |
| **Derived inherent risk rating** | Where both likelihood and impact dimensions are available, the tool applies the 4×4 risk matrix to derive a rating. This is informational, not authoritative. |

### What Makes This Complete

Rating decisions require **RCO rating guidance** — what does Low, Medium, High, and Critical look like for a specific L2 risk? Today, no L2-level rating rubric exists. This is the critical gap.

When RCO rating guidance is available:
- Teams can calibrate their ratings against a defined standard rather than interpreting legacy ratings through a new lens
- The tool can surface the guidance alongside each applicable row so teams don't need to look it up separately
- Cross-entity consistency improves because everyone is rating against the same criteria

Until then, teams use legacy ratings as a reference point and apply their professional judgment.

---

## Step 3: Control Assessment — "What is the state of controls for this risk?"

The control assessment evaluates control effectiveness for each applicable L2. The tool aggregates five evidence sources that collectively represent the full picture of control performance:

### Evidence Sources

| Source | What It Shows | Status |
|--------|---------------|--------|
| **IAG Findings** | Open audit findings from Internal Audit Group engagements, tagged to the L2. Includes finding rating (High/Medium/Low), status (Open, In Validation, In Sustainability), and finding detail. | Integrated |
| **Operational Risk Events (OREs)** | Loss events and near-misses mapped to the L2 via TF-IDF text matching. Includes event IDs, descriptions, and classification (Class A = high severity, Class B, Class C). | Integrated |
| **Regulatory / Enterprise Findings** | Findings from regulatory exams and enterprise-level reviews, tagged to the L2. | Integrated |
| **PRSA Control Problems** | Process Risk Self-Assessment issues identifying control failures. Maps control deficiencies from the first line's own assessment to the relevant L2. Includes issue rating, status, and control title. | Display integrated; L2 mapping in progress |
| **Business Monitoring Activities** | Open cases from business monitoring with AERA impact. Represents ongoing concerns or investigations relevant to the entity's risk profile. | Display integrated |

### What the Tool Produces

For each entity × L2 row, the tool provides:

- **Control Effectiveness Baseline** — The last engagement rating and date, giving teams the most recent independent assessment
- **Impact of Issues** — A consolidated listing of all tagged findings, OREs, regulatory items, PRSA issues, and BMA cases, with individual item details (ID, rating, status, description)
- **Control Signals** — Flags where the control rating contradicts the evidence (e.g., "Well Controlled" with an open High finding)

### What Makes This Complete

The five sources above represent every major channel through which control issues surface in the institution:

| Channel | Question It Answers |
|---------|-------------------|
| IAG Findings | What has Internal Audit found? |
| OREs | What has actually gone wrong (losses, near-misses)? |
| Regulatory Findings | What have regulators found? |
| PRSA Issues | What has the first line's own self-assessment identified? |
| Business Monitoring | What is actively being monitored or investigated? |

When all five are populated and mapped to L2s, teams have a complete view of control performance without opening Archer, checking separate systems, or relying on institutional memory. Every control concern — whether from audit, operations, regulators, self-assessment, or monitoring — is visible in one place per risk.

---

## Putting It Together — The Complete Review

An audit leader reviewing Entity X works through this sequence:

### 1. Open the workbook, filter to Entity X

All 23 L2 rows appear, sorted by priority: undetermined items first, then items with signals, then confirmed items.

### 2. For each L2, answer: "Is this applicable?"

- **Applicable / Finding-Confirmed rows:** Spot-check the evidence. The Decision Basis column explains why. Confirm or override.
- **Undetermined rows:** Read the Source Rationale. Use your knowledge of the entity. Decide.
- **Assumed N/A rows:** Quick gut check — does anything about this entity suggest this risk is relevant? If not, move on.
- **Not Assessed rows:** New L2 with no legacy source. Consider from scratch.

### 3. For each applicable L2, answer: "How severe is this risk?"

- Start from the Proposed Rating (if populated from a direct mapping).
- Reference the RCO rating guidance for this L2 (when available).
- Use the parsed likelihood/impact dimensions if the legacy rationale contained them.
- Override in Reviewer Rating Override if your judgment differs.

### 4. For each applicable L2, review the control picture

- Check the Control Effectiveness Baseline — when was this last assessed, and what was the rating?
- Review Impact of Issues — are there open findings, OREs, regulatory items, PRSA issues, or BMA cases?
- Check Control Signals — does the evidence contradict the baseline rating?
- Use this to inform the control effectiveness assessment you'll enter in AERA.

### 5. Enter final assessments in AERA

The workbook is the map; AERA is the destination. Transfer your applicability decisions, risk ratings, and control assessments into the system of record.

---

## Role of Risk Category Owners

RCOs contribute to all three pillars of the workflow:

| Contribution | Pillar | Impact |
|-------------|--------|--------|
| **Validate keywords** for their L2 | Applicability | Reduces false positives and missed risks in tool proposals |
| **Provide AE lists** (which entity types / business units carry their risk) | Applicability | Enables top-down applicability rules that complement bottom-up evidence |
| **Develop rating guidance** (what L/M/H/C means for their L2) | Inherent Risk Rating | Gives teams a calibration standard; enables cross-entity consistency |
| **Review cross-entity output** for their L2 | All | Catches inconsistencies the tool can't — e.g., two similar entities with different ratings |

---

## Summary

| Question | Tool Provides | RCO Provides | Team Decides |
|----------|--------------|-------------|-------------|
| **Is this risk applicable?** | Evidence-based proposals from 5 sources + keyword matching | Keyword validation + known AE lists | Final applicability determination |
| **How severe is this risk?** | Legacy ratings (direct mappings) + parsed dimensions | Rating guidance per L2 | Final inherent risk rating |
| **What's the control picture?** | Consolidated view of findings, OREs, regulatory items, PRSA issues, BMA cases | Cross-entity calibration review | Final control effectiveness assessment |

The tool answers the starting question. The RCO provides the standard. The team makes the call.
