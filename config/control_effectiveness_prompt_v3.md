# Prompt: Remaining Control Effectiveness Changes + Column Config Centralization

## Context

The `risk_taxonomy_transformer.py` (attached) already has:
- `derive_control_effectiveness()` with baseline and impact of issues columns
- ORE ingestion (`ingest_ore_mappings`, `build_ore_index`)
- Enterprise findings ingestion (`ingest_enterprise_findings`, `build_enterprise_findings_index`)
- Updated `_make_row()` with `control_effectiveness_baseline` and `impact_of_issues`
- Updated `TransformContext` with `ore_index` and `enterprise_findings_index`
- Full pipeline wiring in `main()`

The attached `taxonomy_config.yaml` has `audit_rating_baseline_map`, `staleness_thresholds_months`, `ore_confidence_filter`, and `control_effectiveness_columns`.

Three things still need to change.

## Change 1: Replace Staleness Labels with Two Dates

The current `derive_control_effectiveness()` calls `_compute_staleness()` which produces labels like "Current", "Aging", "Stale", "Outdated" based on fixed month thresholds. This is wrong — our audit frequencies range from 1 to 4 years, so a 14-month-old audit could be fresh or overdue depending on the entity.

**Remove `_compute_staleness()` entirely.**

**Update `derive_control_effectiveness()`** to read two date columns from the legacy data:
- `Last Audit Completion Date` (already configured in YAML as `control_effectiveness_columns.last_audit_completion_date`)
- `Next Planned Audit Date` (new — add to YAML as `control_effectiveness_columns.next_planned_audit_date`, column name: `"Next Planned Audit Date"`)

**Change the Control Effectiveness Baseline format** from:
```
Well Controlled (Last audit: Satisfactory, March 2024, Current)
```
to:
```
Well Controlled (Last audit: Satisfactory, June 2024 · Next planned: June 2026)
```
or if next planned date is blank/missing:
```
Well Controlled (Last audit: Satisfactory, June 2024 · Next planned: not scheduled)
```

Both dates displayed as month and year only (e.g., "June 2024"). No staleness calculation, no labels, no judgment.

**Remove from `taxonomy_config.yaml`:** the entire `staleness_thresholds_months` section.

**Update the Methodology tab:** Remove the "STALENESS LABELS" section. Update the "Control Effectiveness Baseline" description to say it shows the last audit date and next planned audit date for context, and that the reviewer interprets these based on the entity's audit cycle.

## Change 2: Impact of Issues Shows Item IDs, Not Counts

The current `_format_issue_counts()` produces aggregated counts:
```
2 audit findings (1 High open, 1 Medium in validation) · 3 OREs (2 Medium, 1 Low)
```

This doesn't let the reviewer trace back to the source system. **Replace with individual item listings showing IDs.**

**New format:**
```
Finding F-2024-089: Dual-control bypass (High, Open) · Finding F-2023-412: Reconciliation gap (Medium, In Validation) · ORE-4521: Unauthorized payment processed · No enterprise findings
```

Rules:
- Each item is listed individually with its ID, title (truncated to ~80 chars), and severity/status in parentheses
- Items within a data source are separated by ` · `
- Data sources are separated by ` · `
- If a data source has zero items, say so explicitly: "No audit findings", "No OREs", "No enterprise findings" — so the reviewer knows the tool checked
- If ALL data sources have zero items, show "No open items" (this logic already exists)
- Cap at 5 items per data source. If more exist, show the first 5 then "(+N more)"
- For OREs: show `event_id: event_title`. Severity and status are optional — include them in parentheses if present in the ORE data, omit the parentheses if not

**Replace `_format_issue_counts()`** with a new function (or rewrite it) that produces the item-level format. Update the three call sites inside `derive_control_effectiveness()` where findings, OREs, and enterprise findings are formatted.

## Change 3: Centralize Column Configuration in YAML

All column names are currently hardcoded in `main()` and in module-level constants. Move them to `taxonomy_config.yaml` so column names can be updated without touching the script.

**Add this section to `taxonomy_config.yaml`:**

```yaml
columns:
  entity_id: "Audit Entity ID"

  org_metadata:
    entity_name: "Audit Entity Name"
    entity_overview: "Audit Entity Overview"
    audit_leader: "Audit Leader"
    pga: "PGA/ASL"
    core_audit_team: "Core Audit Team"

  control_effectiveness:
    last_engagement_rating: "Last Engagement Rating"
    last_audit_completion_date: "Last Audit Completion Date"
    next_planned_audit_date: "Next Planned Audit Date"

  key_risks:
    entity_id: "Audit Entity ID"
    risk_id: "Key Risk ID"
    risk_description: "Key Risk Description"
    legacy_l1: "Level 1 Risk Category"
    rating: "Inherent Risk Rating"

  findings:
    entity_id: "Audit Entity ID"
    issue_id: "Finding ID"
    l2_risk: "Risk Dimension Categories"
    severity: "Final Reportable Finding Risk Rating"
    status: "Finding Status"
    issue_title: "Finding Name"
    remediation_date: "Actual Remediation Date"
    approval_status: "Finding Approval Status"

  enterprise_findings:
    entity_id: "Audit Entity ID"
    finding_id: "Enterprise Finding ID"
    l2_risk: "Risk Category"
    severity: "Severity"
    status: "Status"
    title: "Finding Title"

  ore_mappings:
    event_id: "Event ID"
    entity_id: "Audit Entity ID"
    mapped_l2s: "Mapped L2s"
    status: "Status"
    event_title: "Event Title"
    severity: "Event Severity"
    ore_status: "Event Status"

  pillar_suffixes:
    rating: "Inherent Risk"
    rationale: "Inherent Risk Rationale"
    control: "Control Assessment"
    control_rationale: "Control Assessment Rationale"

  pillars_with_rationale:
    - Credit
    - Market
    - "Strategic & Business"
    - "Funding & Liquidity"
    - Reputational
    - Model
    - "Financial Reporting"
    - "External Fraud"
    - Operational
    - Compliance
    - Country

  pillars_without_rationale:
    - "Information Technology"
    - "Information Security"
    - "Third Party"

  applications:
    primary_it: "PRIMARY IT APPLICATIONS (MAPPED)"
    secondary_it: "SECONDARY IT APPLICATIONS (RELATED OR RELIED ON)"
    primary_tp: "PRIMARY TLM THIRD PARTY ENGAGEMENT"
    secondary_tp: "SECONDARY TLM THIRD PARTY ENGAGEMENTS (RELATED OR RELIED ON)"

  auxiliary_risk_dimensions:
    - "AXP Auxiliary Risk Dimensions"
    - "AENB Auxiliary Risk Dimensions"
```

**Then remove the existing `control_effectiveness_columns` section** from the YAML — it's replaced by `columns.control_effectiveness`.

**In the script, update these locations to read from config instead of hardcoded values:**

| Currently hardcoded | Location in script | Read from config key |
|---|---|---|
| `entity_id_col = "Audit Entity ID"` | `main()` | `columns.entity_id` |
| `key_risk_cols` dict | `main()` | `columns.key_risks` |
| `findings_cols` dict | `main()` | `columns.findings` |
| `pillar_columns` dict (built via `_pillar()` and `_pillar_no_rationale()`) | `main()` | `columns.pillar_suffixes` + `columns.pillars_with_rationale` + `columns.pillars_without_rationale` |
| `_APP_COLS` module-level dict | module level | `columns.applications` |
| `_AUX_COLS` module-level list | module level | `columns.auxiliary_risk_dimensions` |
| `"Finding Approval Status"` hardcoded string | `ingest_findings()` | `columns.findings.approval_status` |
| `"Audit Leader"`, `"Audit Entity Name"`, etc. | `build_audit_review_df()`, `build_risk_owner_review_df()` | `columns.org_metadata` |

**Build `pillar_columns` dynamically** from the config:
```python
pillar_columns = {}
suffixes = cfg["columns"]["pillar_suffixes"]
for name in cfg["columns"]["pillars_with_rationale"]:
    pillar_columns[name] = {
        "rating": f"{name} {suffixes['rating']}",
        "rationale": f"{name} {suffixes['rationale']}",
        "control": f"{name} {suffixes['control']}",
        "control_rationale": f"{name} {suffixes['control_rationale']}",
    }
for name in cfg["columns"]["pillars_without_rationale"]:
    pillar_columns[name] = {
        "rating": f"{name} {suffixes['rating']}",
        "rationale": None,
        "control": f"{name} {suffixes['control']}",
        "control_rationale": None,
    }
```

**Backward compatibility:** If the `columns` key is missing from the YAML (someone running with an older config), fall back to the current hardcoded defaults and log a warning. Don't break existing setups.

## What NOT to Change

- Do not modify the applicability determination logic
- Do not modify the inherent risk rating derivation
- Do not change the existing findings integration for applicability
- Do not remove `flag_control_contradictions()` — it coexists for now
- Do not change any tab structure, formatting, or sheet ordering
- Do not touch `_resolve_multi_mapping`, `transform_entity`, or the keyword/evidence scoring

## Output

1. Updated `derive_control_effectiveness()` with the two-date format (no staleness)
2. Replacement for `_format_issue_counts()` that produces item-level listings with IDs
3. Updated `_load_config()` to parse the `columns` section
4. Updated `main()` showing how each hardcoded value is replaced with a config read
5. The `columns` section for `taxonomy_config.yaml`
6. List of every module-level constant and hardcoded string that was replaced
7. Updated Methodology tab content (remove staleness, update control effectiveness description)
