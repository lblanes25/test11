# Prompt: Fix Risk Owner Review Tab — Readability, Visibility, and Documentation

## Context

You are fixing issues in the Risk Owner Review implementation in `risk_taxonomy_transformer.py`. The `build_risk_owner_review_df()`, `build_ro_summary_df()`, and related formatting code in `export_results()` are functional but have readability problems, a visibility mistake, missing documentation, and several bugs that need to be corrected before shipping to Risk Category Owners (RCOs).

RCOs are senior audit professionals who own a single L2 risk across 200+ entities. They are not developers. They will open this workbook, see unfamiliar column names, and need to understand what they're looking at immediately. Every column name, every cell value, and every computed field must be self-explanatory or explained in adjacent documentation.

## Issues to Fix

### Issue 1: Risk_Owner_Review tab should be VISIBLE, not hidden

The tab is currently added to the `hidden_tabs` list:

```python
hidden_tabs = ["Risk_Owner_Review", "Review_Queue", "Side_by_Side", ...]
```

This is wrong. The entire point of this tab is that RCOs use it. It should be visible. Remove `"Risk_Owner_Review"` from `hidden_tabs`. The tab order should be:

```
Dashboard | Risk_Owner_Summary | Risk_Owner_Review | Audit_Review | Methodology
```

All three RCO-facing tabs (Dashboard, Summary, Review) are visible. Audit_Review remains visible for audit leaders. Everything else stays hidden.

### Issue 2: Sibling L2 Summary is an unreadable wall of text

Current output looks like this:

```
Data: Applicable-High | Fraud (External and Internal): Applicable-Critical | Information and Cyber Security: Applicable-High | Technology: Applicable-Medium | Processing, Execution and Change: Applicability Undetermined-High | Human Capital: Applicability Undetermined-High | Financial Reporting: Applicable-Low | Third Party: Applicable-High | Conduct: Applicability Undetermined-High | Prudential & bank administration compliance: Applicable-High | Customer / client protection and product compliance: Applicable-High | Financial crimes: Applicable-High | Privacy: Applicable-nan
```

Problems:
- There are 13 siblings listed. Nobody can parse a pipe-delimited string with 13 entries in a 45-character-wide Excel cell.
- Full status names like "Applicability Undetermined" make entries very long.
- L2 names like "Customer / client protection and product compliance" are absurdly long in this context.
- `Applicable-nan` is leaking through — the rating is None/NaN but it's being stringified as "nan".
- Undetermined siblings aren't useful context. The RCO cares about siblings that ARE applicable (confirmed signal) not siblings that are also unresolved.

**Fix:** Completely redesign this column. The RCO needs a quick visual signal, not a comprehensive dump.

**New logic for Sibling L2 Summary:**

1. **Only include Applicable siblings.** Drop Undetermined, No Evidence Found, Not Applicable, and Not Assessed siblings entirely. These are noise — the RCO wants to know "what other risks ARE confirmed for this entity," not "what other risks are also unclear."

2. **Use short L2 names.** Create a short-name mapping (same concept as the tab naming, but for display in cells):

```python
_L2_SHORT_DISPLAY = {
    "Information and Cyber Security": "InfoSec",
    "Processing, Execution and Change": "Proc/Exec",
    "Customer / client protection and product compliance": "Customer Protection",
    "Prudential & bank administration compliance": "Prudential Compliance",
    "Fraud (External and Internal)": "Fraud",
    "Consumer and Small Business": "Consumer/SMB",
    "Financial Reporting": "Fin. Reporting",
    "Financial crimes": "Fin. Crimes",
    "FX and Price": "FX/Price",
    "Interest Rate": "Interest Rate",
    "Human Capital": "Human Capital",
    "Third Party": "Third Party",
    "Technology": "Technology",
    "Privacy": "Privacy",
    "Data": "Data",
    "Legal": "Legal",
    "Conduct": "Conduct",
    "Earnings": "Earnings",
    "Capital": "Capital",
    "Funding & Liquidity": "Funding/Liquidity",
    "Country": "Country",
    "Model": "Model",
    "Reputational": "Reputational",
}
```

3. **Use abbreviated status/rating format.** Instead of `"Data: Applicable-High"`, show `"Data (High)"`. If it's Applicable, just show the rating — "Applicable" is implied since we're only showing Applicable siblings. Append `" ✓RCO"` if the source is `"rco_override"`.

4. **Fix the NaN leak.** If rating is empty, None, NaN, or "nan", show just the L2 name without a rating: `"Data"` not `"Data (nan)"`.

5. **Limit to 6 siblings max.** If more than 6 are Applicable, show the 6 highest-rated ones and append `"+N more"`. For Operational and Compliance L1 with 13 possible siblings, this prevents the cell from becoming a paragraph.

6. **If zero siblings are Applicable**, show `"None applicable"` (short, clear).

**Example of improved output:**

Before: `Data: Applicable-High | Fraud (External and Internal): Applicable-Critical | Information and Cyber Security: Applicable-High | Technology: Applicable-Medium | Processing, Execution and Change: Applicability Undetermined-High | ...`

After: `Fraud (Critical) | Data (High) | InfoSec (High) | Third Party (High) | Technology (Medium) | Fin. Reporting (Low) +2 more`

(Sorted by rating descending so the most significant siblings appear first.)

### Issue 3: Peer Group Rating is confusing

Current output: `Peer modal: Low (2 of 4 peers)`

An RCO reading this will think: "What is a modal? What are peers? Peers of what?" This is statistician language, not auditor language.

**Fix:** Rewrite to be self-explanatory:

Instead of: `Peer modal: Low (2 of 4 peers)`
Write: `Most common rating in this business line: Low (2 of 4 entities)`

Instead of: `Peer modal: Medium (14 of 18 peers) — this entity is High`
Write: `Most common rating in this business line: Medium (14 of 18 entities). This entity is rated High.`

Instead of: `Insufficient peers`
Write: `Fewer than 3 entities in this business line — no comparison available`

Instead of: `Business line not available`
Write: `Business line data not available`

The column name itself should also change from `"Peer Group Rating"` to `"Business Line Comparison"`. "Peer group" is jargon.

### Issue 4: RCOs won't understand the columns without documentation

The Risk_Owner_Review tab has columns like "Review Priority," "Sibling Alert," "Confidence," "Method," and "Business Line Comparison" that are meaningless without explanation. The Methodology tab was updated to list the new tabs but doesn't explain any of the new columns or concepts.

**Fix:** Add a new section to the Methodology tab AND add a frozen "instructions" row or a companion documentation approach. Here's the Methodology content to add:

Add to `methodology_data` list, after the existing TABS section:

```python
["", ""],
["RISK OWNER REVIEW — COLUMN GUIDE", ""],
["Column", "What It Means"],
["Review Priority", "A score from 10-100 indicating how urgently this row needs your attention. "
 "100 = the tool says N/A but other signals disagree (most likely error). "
 "90 = the tool couldn't determine applicability. "
 "80 = marked Applicable but with weak evidence. "
 "50 = Applicable at High or Critical (check for rating consistency). "
 "20 = legacy N/A carried forward, no contradicting signals (lowest urgency). "
 "Rows are sorted by this score within each L2, so the most important rows appear first when you filter."],
["Proposed Status", "The tool's applicability determination. Same values as the Audit Review tab. "
 "See STATUS VALUES section above for definitions."],
["Proposed Rating", "The inherent risk rating the tool derived from legacy data. May be blank "
 "if the tool could not determine a rating."],
["Confidence", "How much evidence the tool had. 'high' = strong match or direct mapping. "
 "'medium' = 1-2 keyword hits. 'low' = no keywords matched, all candidates shown. "
 "'none' = evaluated but no evidence found."],
["Method", "The technical method code the tool used. Experienced users can scan this faster "
 "than reading the Decision Basis prose. Common values: 'direct' (1:1 pillar mapping), "
 "'evidence_match' (keyword hits), 'source_not_applicable' (legacy N/A), "
 "'issue_confirmed' (finding tagged to this L2), 'evaluated_no_evidence' (checked but no match), "
 "'no_evidence_all_candidates' (couldn't tell which L2s apply), 'true_gap_fill' (no legacy source)."],
["Keyword Hits", "The specific keywords that matched in the rationale text or sub-risk "
 "descriptions. If this column is empty, the tool had no keyword evidence for this L2."],
["Sub-Risk IDs", "The Key Risk IDs whose descriptions contained keyword matches. "
 "These are references back to the entity's sub-risk inventory."],
["Finding Reference", "Open findings tagged to this L2 for this entity. Format: "
 "finding ID (severity, status). If populated, this is the strongest evidence of applicability."],
["Sibling L2 Summary", "Other L2 risks under the same L1 category that are confirmed Applicable "
 "for this entity, with their ratings. Sorted by rating (highest first). Only shows Applicable "
 "siblings — unresolved or N/A siblings are excluded. If an entry shows '✓RCO', that sibling's "
 "status was confirmed by another Risk Category Owner in a prior review round."],
["Sibling Alert", "A warning that appears when a sibling L2 (same risk category) is rated High "
 "or Critical for this entity, but THIS L2 is marked as not applicable. This is a potential "
 "false negative — the entity has significant exposure to a related risk, so this L2 may also apply."],
["Business Line Comparison", "How this entity's rating compares to other entities in the same "
 "business line (PGA) for this L2. Shows the most common rating among entities where this L2 is "
 "Applicable. Helps identify outliers — if most entities in a business line are rated Medium but "
 "this one is High, it may warrant a closer look."],
["RCO Agrees", "YOUR INPUT. After reviewing the row, enter: Yes (you agree with the tool), "
 "No (you disagree), or Needs Discussion (you want to discuss with the audit leader)."],
["RCO Recommended Status", "YOUR INPUT. If you disagree, enter your recommendation: "
 "Confirmed Applicable, Confirmed Not Applicable, or Escalate."],
["RCO Recommended Rating", "YOUR INPUT. If you recommend Applicable, enter the rating you "
 "believe is correct: Low, Medium, High, or Critical."],
["RCO Comment", "YOUR INPUT. Explain your reasoning. This comment will be shared with the "
 "audit leader who owns this entity. Be specific: name the business activity that triggers "
 "the risk, or explain why the tool's evidence is insufficient."],
["", ""],
["RISK OWNER REVIEW — HOW TO USE", ""],
["Step", "Action"],
["1. Find your L2", "Go to the Risk Owner Summary tab. Find your L2 risk row. Note the counts "
 "in the Contradicted N/A and Sibling Alerts columns — these are your highest-priority items."],
["2. Filter the detail tab", "Go to Risk Owner Review tab. Click the filter dropdown on the L2 column "
 "and select your L2 risk. The rows are pre-sorted by Review Priority (highest urgency first)."],
["3. Review priority 100 rows first", "These are rows where the tool says N/A but other signals "
 "disagree. Read the Entity Overview and signal columns. If the entity's business clearly involves "
 "your risk, enter 'No' in RCO Agrees and fill in your recommendation."],
["4. Review priority 90 rows", "These are rows where the tool couldn't decide. Use the Entity "
 "Overview and your domain knowledge to determine if this L2 applies."],
["5. Scan applicable rows for consistency", "Filter to Proposed Status = Applicable. Look at the "
 "Business Line Comparison column. Flag outliers where the rating differs significantly from peers."],
["6. Export your overrides", "When done, your filled-in RCO columns can be exported as an override "
 "file (rco_overrides_*.csv) and fed back into the tool. On the next run, your overrides will "
 "appear as validated sibling context for other RCOs reviewing related risks."],
["", ""],
["RISK OWNER REVIEW — PRIORITY SCORING", ""],
["Score", "Meaning"],
["100", "Tool proposes N/A but signals contradict: application flags, auxiliary risk flags, "
 "cross-boundary keyword hits, or a sibling L2 is rated High/Critical. Most likely false negative."],
["90", "Tool could not determine applicability (Applicability Undetermined). RCO input needed."],
["80", "Tool proposes Applicable but with low or medium confidence. Possible false positive."],
["70", "Tool found no evidence (proposed Verify N/A) and no other signals contradict. "
 "Needs verification but lower urgency than contradicted rows."],
["60", "No legacy pillar maps to this L2 (Not Assessed). Structural gap, needs first-time assessment."],
["50", "Tool proposes Applicable at High or Critical. Likely correct, but review for "
 "rating consistency across the portfolio."],
["40", "Tool proposes Applicable at Low or Medium. Lowest urgency among applicable rows."],
["20", "Legacy assessment was N/A, no contradicting signals. Lowest review priority."],
]
```

### Issue 5: Fix the NaN leak in ratings throughout the RCO tab

Multiple places stringify NaN/None values and let `"nan"` appear in cell text. The current code has some guards but they're inconsistent:

```python
rating = str(row.get("inherent_risk_rating_label", "") or "")
if rating in ("nan", "None"):
    rating = ""
```

This pattern needs to be applied consistently. Create a helper:

```python
def _clean_str(val) -> str:
    """Convert value to string, replacing NaN/None/nan with empty string."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    return "" if s.lower() in ("nan", "none", "") else s
```

Use this helper everywhere a value is stringified for display in the RCO tab: ratings, evidence fields, flag fields, legacy source, etc. Audit every string field in the output row dict in `build_risk_owner_review_df()`.

Specific places where `"nan"` currently leaks through:
- Sibling summary rating display: `f"-{sib_rating}"` where `sib_rating` can be `"nan"`
- Application Flag, Auxiliary Risk Flag, etc.: the guards check `!= "nan"` but this is after `str()` conversion and may miss edge cases
- `Source Rationale Excerpt`: `str(row.get("source_rationale", "") or "")[:300]` — if the value is NaN, `str(NaN)` = `"nan"`
- `Legacy Pillar Rating`: raw value from the row, not cleaned

### Issue 6: Fix the dead code loop in signal flag computation

Remove this dead loop:

```python
for flag_name in ("app_flag", "aux_flag", "cross_boundary_flag", "control_flag"):
    val = locals().get(flag_name.replace("cross_boundary_flag", "cross_flag"), "")
```

It does nothing. The `has_any_signal` computation below it is correct without it.

### Issue 7: Fix the double-computation of sibling_alerts in build_ro_summary_df

```python
sibling_alerts = (l2_rows["Sibling Alert"].astype(str).str.len() > 0).sum()
# Exclude empty strings and "nan"
sibling_alerts = l2_rows["Sibling Alert"].apply(
    lambda x: bool(x and str(x) not in ("", "nan"))
).sum()
```

Delete the first line. Keep only the second (correct) one.

### Issue 8: Incorporate RCO overrides into peer comparison computation

The `peer_ratings` pre-computation currently only uses tool proposals:

```python
if has_pga:
    for _, row in transformed_df.iterrows():
        ...
        status = _derive_status(row["method"])
        if status == "Applicable":
            ...
```

After this loop, overlay RCO overrides the same way sibling context does:

```python
if rco_overrides and has_pga:
    for (eid, l2), override in rco_overrides.items():
        if override["status"] == "Confirmed Applicable":
            bl = entity_meta.get(eid, {}).get("business_line", "")
            rating = override.get("rating") or ""
            if bl and rating:
                peer_ratings[(bl, l2)][rating] += 1
```

This ensures that when RCO A confirms 10 entities as Applicable-Medium for Privacy, the peer comparison for Privacy reflects those 10 entities in round 2.

### Issue 9: Drop internal columns from DataFrame before writing to Excel

Instead of writing `_has_any_signal` and `_priority` to Excel and then deleting the columns with `delete_cols()` (which is slow on large sheets and can break auto-filter references), drop them from the DataFrame before `.to_excel()`:

In `export_results()`, after calling `build_risk_owner_review_df()`:

```python
# Store priority for formatting, then drop internal columns before writing
ro_priority_lookup = dict(zip(ro_review_df.index, ro_review_df["_priority"]))
ro_review_clean = ro_review_df.drop(columns=[c for c in ro_review_df.columns if c.startswith("_")])
ro_review_clean.to_excel(writer, sheet_name="Risk_Owner_Review", index=False)
```

Then in the formatting pass, use `Review Priority` column (value == 100) to apply the red row fill instead of the deleted `_priority` column:

```python
priority_col = _find_header_column(ws_ro, "Review Priority")
if priority_col:
    for row_idx in range(data_start, ws_ro.max_row + 1):
        if ws_ro.cell(row=row_idx, column=priority_col).value == 100:
            for col_idx in range(1, ws_ro.max_column + 1):
                ws_ro.cell(row=row_idx, column=col_idx).fill = red_fill
```

Remove the entire `cols_to_delete` block that searches for `_`-prefixed columns.

### Issue 10: Append truncation indicator to Entity Overview

```python
overview_raw = str(row.get("Audit Entity Overview", "") or "")
overview = overview_raw[:300] + ("..." if len(overview_raw) > 300 else "")
```

Same for Source Rationale Excerpt.

## Summary of All Changes

| # | What | Where |
|---|---|---|
| 1 | Make Risk_Owner_Review visible | `hidden_tabs` list in `export_results()` |
| 2 | Redesign Sibling L2 Summary: only Applicable, short names, sorted by rating, max 6, fix NaN | `build_risk_owner_review_df()` sibling context block |
| 3 | Rewrite Peer Group Rating for plain language, rename column to Business Line Comparison | `build_risk_owner_review_df()` peer section, column name in output dict |
| 4 | Add full column guide, usage instructions, and priority scoring to Methodology tab | `methodology_data` in `export_results()` |
| 5 | Create and use `_clean_str()` helper to eliminate NaN leaks | New helper, used throughout `build_risk_owner_review_df()` |
| 6 | Remove dead signal flag loop | `build_risk_owner_review_df()` |
| 7 | Remove duplicate sibling_alerts computation | `build_ro_summary_df()` |
| 8 | Incorporate RCO overrides into peer comparison | `build_risk_owner_review_df()` peer_ratings pre-computation |
| 9 | Drop internal columns from DataFrame before writing, use Review Priority for red row formatting | `export_results()` |
| 10 | Append "..." when truncating Entity Overview and Source Rationale Excerpt | `build_risk_owner_review_df()` |

## Constraints

- Do not change any existing tab behavior (Audit_Review, Dashboard, Side_by_Side, etc.)
- Do not add new dependencies
- Follow existing code style
- The `Risk_Owner_Summary` column name `"Peer Group Rating"` should also be renamed to match: update the summary computation and column name to `"Business Line Comparison"` — wait, this column doesn't exist on the summary tab. No change needed there. But DO rename the `"Sibling Alerts"` count column on the summary if needed for consistency — actually, "Sibling Alerts" is fine as a count label on the summary since it's just a number.
- Update the `ro_col_widths` dict in the formatting pass to use the new column name `"Business Line Comparison"` instead of `"Peer Group Rating"`, and also rename `"Sibling L2 Summary"` to just `"Applicable Siblings"` for brevity in the column header (the Methodology tab explains what it means). Set width to 45 for Applicable Siblings.
