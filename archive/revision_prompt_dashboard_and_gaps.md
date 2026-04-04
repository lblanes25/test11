# Risk Taxonomy Transformer — Revision Prompt: Dashboard, Decision Basis, and UX Gaps

You are updating the Risk Taxonomy Transformer tool based on a review of the current implementation against the workflow design specification. Four gaps were identified. Address all four in the code changes described below.

The current codebase is the `risk_taxonomy_transformer.py` file provided. All changes should preserve existing functionality — these are additions and modifications, not rewrites.

---

## Gap 1: Dashboard Restructure — Add Tool Proposals and Entity-Level Metrics

### Problem

The current Dashboard only tracks **reviewer progress** (Reviewer Status counts). When a reviewer opens the workbook for the first time, almost every Reviewer Status cell is blank, so the Dashboard communicates almost nothing. The walkthrough script promises: *"The Dashboard shows how much work the tool handled and how much needs your judgment."* The Dashboard must deliver on that promise by showing a breakdown of the tool's Proposed Status values — which are fully populated at generation time — before the reviewer touches anything.

Additionally, the Dashboard is missing **entity-level metrics** entirely. The reviewer needs to see how many audit entities are in their portfolio and track completion at the entity level, not just the row level.

### Required Changes

Restructure the Dashboard tab (built in the `export_results` function's openpyxl section) into three sections:

**Section A — Tool Proposals (static after generation, references Proposed Status column)**

This section answers: "What did the tool do for me?"

| Row Label | Formula |
|-----------|---------|
| **TOOL PROPOSALS** | *(section header, bold)* |
| Total Audit Entities | `=SUMPRODUCT(1/COUNTIF(Audit_Review!{eid_col}2:{eid_col}{max}}, Audit_Review!{eid_col}2:{eid_col}{max}))` — count of unique Entity IDs |
| Total Entity–L2 Rows | `=COUNTA(Audit_Review!A2:A{max})` |
| Applicable (evidence found) | `=COUNTIF(Audit_Review!{ps_col}2:{ps_col}{max}, "Applicable")` |
| Applicability Undetermined | `=COUNTIF(Audit_Review!{ps_col}2:{ps_col}{max}, "Applicability Undetermined")` |
| No Evidence Found — Verify N/A | `=COUNTIF(Audit_Review!{ps_col}2:{ps_col}{max}, "No Evidence Found*")` |
| Not Applicable (legacy N/A) | `=COUNTIF(Audit_Review!{ps_col}2:{ps_col}{max}, "Not Applicable")` |
| Not Assessed (structural gap) | `=COUNTIF(Audit_Review!{ps_col}2:{ps_col}{max}, "Not Assessed")` |
| *(blank row)* | |
| Rows Requiring Your Judgment | `=COUNTIF(..., "Applicability Undetermined") + COUNTIF(..., "No Evidence Found*")` |
| Rows With Control Signals | `=COUNTIF(Audit_Review!{cs_col}2:{cs_col}{max}, "<>")` — where `{cs_col}` is the Control Signals column letter |
| Rows With Additional Signals | `=COUNTIF(Audit_Review!{as_col}2:{as_col}{max}, "<>")` — where `{as_col}` is the Additional Signals column letter |

For each status count row, add a **percentage column** (column C): `=B{row}/B{total_rows_row}` formatted as `0.0%`.

**Section B — Your Review Progress (updates as reviewer works, references Reviewer Status column)**

This section answers: "How far along am I?"

| Row Label | Formula |
|-----------|---------|
| **YOUR REVIEW PROGRESS** | *(section header, bold)* |
| Confirmed Applicable | `=COUNTIF(Audit_Review!{rs_col}2:{rs_col}{max}, "Confirmed Applicable")` |
| Confirmed Applicable — Rating Adjusted | `=COUNTIF(Audit_Review!{rs_col}2:{rs_col}{max}, "Confirmed Applicable*Rating*")` |
| Confirmed Not Applicable | `=COUNTIF(Audit_Review!{rs_col}2:{rs_col}{max}, "Confirmed Not Applicable")` |
| Escalated (Pending) | `=COUNTIF(Audit_Review!{rs_col}2:{rs_col}{max}, "Escalate")` |
| Not Yet Reviewed | `=COUNTIF(Audit_Review!{rs_col}2:{rs_col}{max}, "")` |
| % Complete | `=1 - {not_yet_reviewed_cell} / {total_rows_cell}` formatted as `0.0%` |

**Section C — Entity Completion Table (one row per audit entity)**

This section answers: "Which entities are done and which still need work?"

Build this section starting below Sections A and B. It requires one row per unique entity in the Audit Review tab.

Since Excel COUNTIFS formulas can handle this but dynamically generating one formula row per entity requires knowing the entity list at generation time, **build this section in Python using the transformed data** rather than pure Excel formulas:

1. Get the unique list of entity IDs and their entity names from the Audit Review dataframe.
2. For each entity, compute:
   - Entity ID
   - Entity Name
   - Audit Leader (if available)
   - Total L2s (should be 23 for every entity)
   - Proposed Applicable: count of rows where Proposed Status = "Applicable"
   - Proposed Undetermined: count of rows where Proposed Status = "Applicability Undetermined"
   - Proposed No Evidence: count of rows where Proposed Status starts with "No Evidence Found"
   - Proposed Not Applicable: count of rows where Proposed Status = "Not Applicable"
   - Proposed Not Assessed: count of rows where Proposed Status = "Not Assessed"
   - Reviewer: Confirmed Applicable (count of Reviewer Status = "Confirmed Applicable" or "Confirmed Applicable — Rating Adjusted")
   - Reviewer: Confirmed Not Applicable (count)
   - Reviewer: Escalated (count)
   - Reviewer: Not Yet Reviewed (count where Reviewer Status is blank)
   - % Complete: `(23 - not_yet_reviewed) / 23`
   - Missing Ratings: count of rows where Reviewer Status starts with "Confirmed Applicable" but both Proposed Rating and Reviewer Rating Override are blank
3. Write this as a table with headers, starting at a row below the Section B content.
4. Add header styling (same as other tabs) and format % Complete as percentage.
5. Sort by % Complete ascending (least complete entities first).

The entity-level columns are **static values written by Python at generation time** for the Proposed Status counts (these won't change), and **will need to be manually updated or regenerated** for the Reviewer Status counts. This is acceptable — the primary value of Section C is showing the entity list with Proposed Status breakdowns so the reviewer can see which entities have the most undetermined rows. Add a note above Section C: *"Proposed Status columns are pre-calculated. Reviewer progress columns reflect the state at workbook generation — re-run the tool or use filters in the Audit Review tab for live progress."*

Alternatively, if you can construct COUNTIFS formulas per entity (e.g., `=COUNTIFS(Audit_Review!{eid_col}2:{eid_col}{max}, "{entity_id}", Audit_Review!{rs_col}2:{rs_col}{max}, "Confirmed Applicable")`), use formulas for the Reviewer Status columns so they update live. This is preferred if the entity count is manageable (under ~100 entities).

### Formatting

- Section headers ("TOOL PROPOSALS", "YOUR REVIEW PROGRESS", "ENTITY COMPLETION") should use bold, 11pt, dark blue font — consistent with the existing Methodology section header styling.
- Add a thin horizontal border between sections.
- Column A width: 40. Column B width: 15. Column C (percentage): 10.
- Entity Completion table headers should use the standard `style_header` formatting.
- Freeze the header row of the Entity Completion table if possible (note: Excel only supports one freeze pane per sheet — freeze at the Entity Completion header row so the portfolio summary stays visible when scrolling the entity table).

---

## Gap 2: Decision Basis for "No Evidence Found" Rows Must Name Sibling L2s

### Problem

The `_derive_decision_basis` function produces generic text for `evaluated_no_evidence` rows:

> *"The [Pillar] pillar (rated [Rating]) rationale was reviewed for relevance to this L2 risk. No direct connection was found..."*

This doesn't tell the reviewer which other L2s from the same pillar *did* have evidence. That context is essential — if the reviewer sees "Processing/Execution and Technology had keyword matches from the Operational pillar, but Data did not," they can quickly judge whether the tool's assumption is reasonable. Without it, they have to read the full rationale and mentally reconstruct which L2s matched, which defeats the purpose of the tool.

### Required Changes

**Step 1: Capture sibling match information during transformation.**

In the `transform_entity` function, after `_resolve_multi_mapping` returns `targets_to_create` for a `multi` mapping type, the code already iterates over `pillar_config["targets"]` to create `evaluated_no_evidence` rows for candidates not in `matched_l2s_this_pillar`. At this point, `matched_l2s_this_pillar` contains the L2s that *did* have evidence.

When creating the `evaluated_no_evidence` row (the `_make_row` call in the `if candidate_l2 not in matched_l2s_this_pillar` block), pass the sibling information into the row. Use the `sub_risk_evidence` field (which is currently empty for these rows) to store a formatted string like:

```
siblings_with_evidence: Processing, Execution and Change; Technology
```

Alternatively, add a new field to the row dict. The `_make_row` function would need a new keyword argument (e.g., `sibling_evidence=""`), or you can overload `sub_risk_evidence` since it's unused for no-evidence rows.

**Step 2: Update `_derive_decision_basis` to include sibling names.**

In the `evaluated_no_evidence` branch of `_derive_decision_basis`, check for sibling information in the row and include it:

**Current:**
> "The Operational pillar (rated High) rationale was reviewed for relevance to this L2 risk. No direct connection was found, so this L2 is marked as not applicable for this entity. If your review of the rationale suggests otherwise, this can be changed to applicable."

**Updated:**
> "The Operational pillar (rated High) maps to multiple L2 risks. Other L2s from this pillar — Processing, Execution and Change; Technology — had keyword matches in the rationale or sub-risk descriptions. This L2 (Data) did not. Assumed not applicable — override if your review of the rationale suggests this L2 is relevant to this entity."

If no siblings had evidence (which shouldn't happen for `evaluated_no_evidence` rows, but as a safety net), fall back to the current generic text.

**Step 3: Update the Methodology tab.**

The Methodology tab's description of "No Evidence Found — Verify N/A" currently says:

> "Other L2s from the same legacy pillar had keyword evidence, but this one did not. No evidence was found for this L2 — verify whether it applies to this entity."

Update to:

> "Other L2s from the same legacy pillar had keyword evidence, but this one did not. The Decision Basis column names which sibling L2s matched. No evidence was found for this L2 — verify whether it applies to this entity."

---

## Gap 3: Entity Group Separators in Audit Review Tab

### Problem

When scrolling through the Audit Review tab, there is no visual boundary between where one entity's 23 rows end and the next entity's rows begin. This makes it hard to orient yourself, especially when entities have similar L2 patterns.

### Required Changes

In the `export_results` function's formatting section for the Audit Review sheet, after all other formatting is applied:

1. Iterate through the data rows (starting at row 2) and identify where the Entity ID value changes from one row to the next.
2. At each entity boundary, apply a **top border** to the first row of the new entity group. Use a medium-weight border in a neutral color:

```python
entity_border = Border(top=Side(style="medium", color="2F5496"))
```

3. Apply this border to every cell in the boundary row (all columns), so it reads as a full-width horizontal line.

4. Do **not** insert blank separator rows — these would break formulas, filters, and the data structure. A border-only separator preserves the data while providing visual delineation.

**Implementation detail:** You'll need to find the Entity ID column index in the Audit Review sheet (it should be column A / column 1), then loop:

```python
# Find entity ID column
eid_col_idx = 1  # Entity ID is first column per the column order spec

prev_eid = None
for row_idx in range(2, ws.max_row + 1):
    current_eid = ws.cell(row=row_idx, column=eid_col_idx).value
    if prev_eid is not None and current_eid != prev_eid:
        # Apply top border to this row
        for col_idx in range(1, ws.max_column + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            # Preserve existing borders, only add top
            existing = cell.border
            cell.border = Border(
                top=Side(style="medium", color="2F5496"),
                left=existing.left,
                right=existing.right,
                bottom=existing.bottom,
            )
    prev_eid = current_eid
```

---

## Gap 4: Walkthrough Script — Add Side_by_Side Cross-Reference

### Problem

The walkthrough script never shows the reviewer how to access the Side_by_Side tab for raw evidence. The design specification called for this as a trust-building step — demonstrating that full traceability exists if the reviewer wants to dig deeper.

### Required Change

In the `walkthrough_script.md` file, add a brief aside after the **first Applicable row walkthrough** (Section "1. Applicable Row"), before moving to the Finding-Confirmed Row section. Insert the following:

```markdown
### Quick aside: The evidence trail (30 seconds)

> "One more thing before we move on. If you ever want to see exactly how the tool
> arrived at a determination — every keyword hit, every sub-risk ID, every individual
> flag — unhide the Side_by_Side tab. It has the complete evidence trail for every
> row: the raw method, individual confidence scores, and every flag column broken out
> separately. You won't need it for most rows, but it's there when you want to verify
> something or understand why two rows for the same L2 got different treatments."

Right-click the tab bar → Unhide → select Side_by_Side. Show the same entity's rows. Point out the `method`, `confidence`, `sub_risk_evidence`, and individual flag columns. Then re-hide the tab.

> "For your day-to-day review, the Audit Review tab has everything you need. Side by
> Side is the audit trail underneath."
```

---

## Summary of All Changes

| Gap | File(s) Modified | What Changes |
|-----|-----------------|--------------|
| 1. Dashboard restructure | `risk_taxonomy_transformer.py` — `export_results` Dashboard-building section | Replace current single-section Dashboard with three sections: Tool Proposals (Proposed Status counts), Your Review Progress (Reviewer Status counts), Entity Completion table (one row per entity with both Proposed and Reviewer breakdowns) |
| 2. Sibling L2 naming | `risk_taxonomy_transformer.py` — `transform_entity` (capture siblings), `_derive_decision_basis` (format text), Methodology data | Pass matched sibling L2 names into no-evidence rows; update Decision Basis text to name them; update Methodology description |
| 3. Entity group separators | `risk_taxonomy_transformer.py` — `export_results` Audit Review formatting section | Add medium-weight top border at each entity boundary row |
| 4. Walkthrough Side_by_Side | `walkthrough_script.md` | Add 30-second Side_by_Side cross-reference segment after first Applicable row walkthrough |

All four changes are additive. No existing functionality is removed or altered except the Dashboard layout (which is being expanded, not reduced) and the `evaluated_no_evidence` Decision Basis text (which is being made more informative, not shortened).
