# Risk Taxonomy Transformer — Simplification Prompt

You are simplifying the Risk Taxonomy Transformer workbook output. The workbook is used as a **reference tool**, not a live tracking document. Audit leaders filter to their entities and use it as a starting point for completing assessments in AERA. Risk category owners filter to their L2 and scan across entities. Nobody fills in Reviewer Status systematically, nobody submits this workbook, and it is not shared as a live collaborative file.

The current implementation has infrastructure — progress tracking, QA validation, escalation routing, sheet protection, data validation — designed for a formal review workflow that doesn't exist. Remove it.

---

## 1. Dashboard Tab — Keep Only the Tool Proposals Section

**Remove** Section B (Your Review Progress) and Section C (Entity Completion Table) entirely. These tracked Reviewer Status values that nobody will fill in.

**Keep** Section A (Tool Proposals) exactly as it is today. This section uses COUNTIF formulas against the Proposed Status column and shows:

```
TOOL PROPOSALS                        Count    %
Total Audit Entities                  10
Total Entity-L2 Rows                  230
Applicable (evidence found)           142      61.7%
Applicability Undetermined            16       7.0%
No Evidence Found — Verify N/A        17       7.4%
Not Applicable (legacy N/A)           55       23.9%
Not Assessed (structural gap)         0        0.0%

Rows Requiring Your Judgment          33       14.3%
Rows With Control Signals             5        2.2%
Rows With Additional Signals          59       25.7%
```

This is the "here's what the tool did for you" summary that builds trust on first open.

**Implementation:** In the Dashboard-building section of `export_results`, delete all code after the Tool Proposals section — everything related to Section B (progress items, % complete formula) and Section C (entity headers, entity loop, COUNTIFS per entity, column widths for entity table). Keep the Dashboard title, generated date, Section A formulas, and Section A formatting. Remove the freeze pane (it was set at the entity table header, which no longer exists). The Dashboard should be a compact single-screen summary.

---

## 2. Remove Tabs

Delete the following tabs from the workbook output entirely — remove both the code that writes them and any references to them:

- **Escalation_Tracker** — No formal escalation workflow. Remove the empty-with-headers DataFrame creation and the `to_excel` call.
- **QA_Results** — No submission step from this workbook. Remove the QA checks section that builds this tab via openpyxl.
- **Review_Log** — No one is tracking changes in this file. Remove the empty-with-headers DataFrame creation and the `to_excel` call.

**Update the tab visibility and ordering code** to remove these three tabs from the `desired_order` list and the `hidden_tabs` list.

**Update the Methodology tab** to remove references to these three tabs in the "TABS IN THIS WORKBOOK" section. The remaining tabs should be:

| Tab | Purpose |
|-----|---------|
| Dashboard | Tool proposals summary — what the tool resolved and what needs judgment |
| Audit_Review | All entity–L2 rows with proposed statuses, ratings, and decision basis |
| Methodology | Tool logic explanation, status definitions, column legend, FAQ |
| Review_Queue | *(hidden)* Filtered view of Undetermined and No Evidence rows |
| Side_by_Side | *(hidden)* Full traceability for debugging and audit trail |
| Legacy_Original or Source - Legacy Data | *(hidden)* Unmodified legacy risk data |
| Findings_Source or Source - Findings | *(hidden)* Findings with disposition |
| Sub_Risks_Source or Source - Sub-Risks | *(hidden)* Sub-risk descriptions with keyword contributions |
| Overlay_Flags | *(hidden)* Country risk overlay details |

---

## 3. Remove Formal Review Infrastructure from Audit Review Tab

The Reviewer Status, Reviewer Rating Override, and Reviewer Notes columns should **remain** in the Audit Review tab as plain editable columns — they're useful scratch space for leaders annotating while they work. But remove all the formal workflow infrastructure built around them:

**Remove sheet protection.** Delete all code that sets `cell.protection = Protection(locked=True)` or `Protection(locked=False)`, and delete `ws.protection.sheet = True` and its associated settings (`autoFilter`, `sort`, `formatColumns`, `formatRows`). The sheet should be fully editable.

**Remove data validation on Reviewer Status.** Delete the `DataValidation` object creation, the dropdown formula, the error message, the input prompt message, and the `ws.add_data_validation(dv)` call. Leaders can type whatever they want in these columns.

**Remove conditional formatting tied to Reviewer Status.** Delete the `FormulaRule` that applies green fill to rows where Reviewer Status is non-blank. This was designed to show review progress, which isn't happening in this workbook.

**Keep** all other Audit Review formatting:
- Header styling
- Proposed Status cell color coding (green/yellow/orange/gray/blue)
- Status tier left border colors (orange for Undetermined, yellow for No Evidence)
- Column widths
- Text wrapping on long-text columns
- Frozen panes (Entity ID + Entity Name + header row)
- Column grouping (rating detail columns hidden by default)
- Entity group separators (medium border between entity groups)
- Reviewer column header color (green header fill) — keep this so the columns are visually distinct as "your space"

---

## 4. Update Methodology Tab Content

Remove references to the deleted tabs and the formal review workflow:

- In the "TABS IN THIS WORKBOOK" section, remove rows for Dashboard entity tracking, Escalation_Tracker, QA_Results, and Review_Log. Update the Dashboard description to: "Tool proposals summary — what the tool resolved and what needs judgment."
- Remove any FAQ entries about escalation workflow or QA submission.
- Keep all other Methodology content: status definitions, confidence levels, evidence sources, rating source explanations, finding filters, deduplication rules. These explain the tool's logic and are valuable reference material regardless of workflow.

---

## Summary of Changes

| What | Action |
|------|--------|
| Dashboard Section B (Review Progress) | Remove |
| Dashboard Section C (Entity Completion) | Remove |
| Dashboard Section A (Tool Proposals) | Keep as-is |
| Dashboard freeze pane | Remove |
| Escalation_Tracker tab | Remove entirely |
| QA_Results tab | Remove entirely |
| Review_Log tab | Remove entirely |
| Sheet protection on Audit Review | Remove |
| Data validation on Reviewer Status | Remove |
| Conditional formatting on Reviewer Status | Remove |
| Reviewer Status / Override / Notes columns | Keep as plain editable columns |
| All other Audit Review formatting | Keep |
| Methodology tab references to removed tabs | Update |
| Tab ordering code | Update to reflect removed tabs |
| Hidden source tabs | Keep as-is |
