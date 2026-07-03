"""
RCO Rating Prompt Export
========================
Produces per-batch ChatGPT prompt files that ask for a proposed inherent risk
rating (Low / Medium / High / Critical) for every audit entity, for a single
specified L2 risk (Conduct, Internal Fraud, Model Risk, etc.).

Unlike the applicability LLM prompts, this runs over ALL audit entities
regardless of their current LUminate applicability status — the RCO's guidance
is the authoritative framing.

Per entity the prompt includes:
  - Archer entity overview (from Audit_Review)
  - Optro entity overview (from optro_ae_overview_*.xlsx — most current)
  - Core / Auxiliary relationship for this L2 (from Side_by_Side flags)
  - L2 / L3 / L4 taxonomy definitions
  - RCO applicability and rating guidance  [placeholder — paste before sending]
  - Open issues tagged to this L2

Model Risk mode (auto-enabled when --l2 "Model" or "Model Risk"):
  - Models in scope with per-model impact category, class, and purpose
    (from model_inventory_*.xlsx)
  - RCO Model Risk guidance (impact / likelihood rules, frequency definitions)
    is embedded in the system prompt; only IAG Procedure Manual Table 3.1
    remains a paste placeholder
  - Cross-check warning when models are confirmed in scope but LUminate suggests N/A
  - Legacy rating + rationale are deliberately NOT in the prompt (anchoring risk);
    they surface in the consolidation output for the RCO instead

ChatGPT returns a JSON array:
  [{"entity_id": "...", "entity_name": "...",
    "proposed_rating": "Low|Medium|High|Critical",
    "rating_rationale": "<1-2 sentences>"}]

Usage:
    python export_rco_rating_prompts.py --l2 Conduct
    python export_rco_rating_prompts.py --l2 "Internal Fraud"
    python export_rco_rating_prompts.py --l2 "Model Risk"
    python export_rco_rating_prompts.py --l2 Conduct --workbook path/to/output.xlsx
    python export_rco_rating_prompts.py --l2 Conduct --max-aes 20
"""

import argparse
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

from risk_taxonomy_transformer.utils import latest_input

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent
_CONFIG_PATH = _PROJECT_ROOT / "config" / "taxonomy_config.yaml"


def _load_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)

# ---------------------------------------------------------------------------
# Placeholder text that the RCO will replace before sending to ChatGPT.
# ---------------------------------------------------------------------------
_RCO_GUIDANCE_PLACEHOLDER = """
[PASTE RCO GUIDANCE HERE BEFORE SENDING]

Include:
  1. Applicability guidance (when is this risk applicable / not applicable)
  2. Likelihood guidance (factors that drive likelihood ratings for this risk)
  3. Impact guidance (factors that drive Low / Medium / High / Critical ratings)
"""

VALID_RATINGS = ["Low", "Medium", "High", "Critical"]


# ---------------------------------------------------------------------------
# Model Risk helpers
# ---------------------------------------------------------------------------

def _load_model_risk_legacy(cfg: dict) -> dict[str, dict]:
    """Return {ae_id: {rating, rationale, control, control_rationale, models_text}}."""
    legacy_file = latest_input(
        _PROJECT_ROOT / "data" / "input",
        ["legacy_risk_data_*.xlsx"],
        log_label="legacy risk data",
    )
    if legacy_file is None:
        logger.warning("No legacy_risk_data_*.xlsx — legacy Model Risk data will be omitted")
        return {}

    cols = cfg.get("columns", {})
    suffixes = cols.get("pillar_suffixes", {})
    pillar = "Model"
    rating_col = f"{pillar} {suffixes.get('rating', 'Inherent Risk')}"
    rationale_col = f"{pillar} {suffixes.get('rationale', 'Inherent Risk Rationale')}"
    control_col = f"{pillar} {suffixes.get('control', 'Control Assessment')}"
    control_rationale_col = f"{pillar} {suffixes.get('control_rationale', 'Control Assessment Rationale')}"
    models_col = cols.get("applications", {}).get("models", "Models")

    df = pd.read_excel(legacy_file)
    result: dict[str, dict] = {}
    for _, row in df.iterrows():
        ae_id = str(row.get("Audit Entity ID", "")).strip()
        if not ae_id or ae_id.lower() in ("nan", ""):
            continue
        result[ae_id] = {
            "rating": str(row.get(rating_col, "")).strip(),
            "rationale": str(row.get(rationale_col, "")).strip(),
            "control": str(row.get(control_col, "")).strip(),
            "control_rationale": str(row.get(control_rationale_col, "")).strip(),
            "models_text": str(row.get(models_col, "")).strip(),
        }
    logger.info(f"Loaded legacy Model Risk data for {len(result)} entities from {legacy_file.name}")
    return result


def _cell(row, col: str) -> str:
    v = str(row.get(col, "")).strip()
    return "" if v.lower() in ("nan", "none") else v


def _load_model_inventory(cfg: dict) -> dict[str, dict]:
    """Return {model_id: {name, class_, markets, impact, purpose}}
    from model_inventory_*.xlsx."""
    inv_file = latest_input(
        _PROJECT_ROOT / "data" / "input",
        ["model_inventory_*.xlsx"],
        log_label="model inventory",
    )
    if inv_file is None:
        logger.warning("No model_inventory_*.xlsx — model inventory data will be omitted")
        return {}

    inv_cfg = cfg.get("columns", {}).get("model_inventory", {})
    id_col = inv_cfg.get("id", "Model ID")
    name_col = inv_cfg.get("name", "Model Name")
    class_col = inv_cfg.get("model_class", "Model Class")
    markets_col = inv_cfg.get("markets", "Markets")
    impact_col = inv_cfg.get("impact", "Model Impact Category")
    purpose_col = inv_cfg.get("purpose", "Model Purpose & Intended Use")

    df = pd.read_excel(inv_file)
    result: dict[str, dict] = {}
    for _, row in df.iterrows():
        mid = _cell(row, id_col)
        if not mid:
            continue
        result[mid] = {
            "name": _cell(row, name_col),
            "class_": _cell(row, class_col),
            "markets": _cell(row, markets_col),
            "impact": _cell(row, impact_col),
            "purpose": _cell(row, purpose_col),
        }
    logger.info(f"Loaded {len(result)} model inventory records from {inv_file.name}")
    return result


def _parse_model_ids(models_text: str) -> list[str]:
    """Extract numeric model IDs from text like 'Name-1001-v3; 1002; Name-1003-current'."""
    if not models_text or models_text.lower() in ("nan", "none", ""):
        return []
    return list(dict.fromkeys(re.findall(r"\b(\d{4,})\b", models_text)))


def _build_system_prompt_model_risk() -> str:
    return """\
You are an internal audit risk rating specialist. You are assessing the \
INHERENT risk rating for "Model Risk" for each audit entity in the portfolio.

For each entity listed below, propose a risk rating using the four-point scale:
  Low | Medium | High | Critical

Base your rating on:
1. The Optro entity overview (most current — authored by the audit team)
2. The Archer entity overview (upstream extract — may be slightly older)
3. The models confirmed in scope for this entity — their class, purpose, \
markets, and individual Model Impact Category
4. The L2 / L3 / L4 Model Risk taxonomy definitions
5. The RCO's Model Risk inherent risk guidance (below)
6. Open audit issues tagged to Model Risk (ancillary signal)

RCO GUIDANCE — MODEL RISK INHERENT RISK ASSESSMENT
==================================================
Assess inherent model risk in two steps:
  Step 1 — Determine IMPACT and LIKELIHOOD using the rules below, based on:
    (1) applicability/use of the models in the business process,
    (2) each model's impact category, and
    (3) the number of models tagged to the entity.
  Step 2 — Combine Impact and Likelihood into the Inherent Risk rating using \
Table 3.1 "Guidance for Assessing Inherent Risk" from the IAG Procedure Manual:

[PASTE IAG PROCEDURE MANUAL TABLE 3.1 HERE BEFORE SENDING]

IMPACT rules (choose the more severe rating when scenarios conflict):
  - If any in-scope model's purpose is Regulatory, Liquidity, Capital, P&L, \
Direct Credit / Fraud Decision / AML, or Direct Customer Harm -> Impact = Critical
  - Otherwise (purpose is Operations, Servicing, Marketing, Indirect Credit / \
Fraud Decisions / AML, or Indirect Customer Harm), rate by model counts:
      * >= 1 Critical-impact model                            -> Impact = Critical
      * >= 1 High-impact model                                -> Impact = High
      * Medium-impact models >= 30% of the entity's models,
        or at least 2 Medium-impact models                    -> Impact = Medium
      * All other cases                                       -> Impact = Low

LIKELIHOOD rules (model counts x frequency of use; more severe when conflicting):
  >= 1 Critical-impact model:
      Continuous -> Critical | Frequent or Periodic -> High | Infrequent -> Medium
  >= 1 High-impact model:
      Continuous -> Critical | Frequent -> High | Periodic -> Medium | Infrequent -> Low
  Medium-impact models >= 30% or at least 2:
      Continuous -> High | Frequent -> Medium | Periodic or Infrequent -> Low
  All other cases:
      Continuous -> Medium | Frequent / Periodic / Infrequent -> Low

Frequency of use definitions:
  Continuous — real time, near real time, daily production, automated \
decisioning, or embedded in a core process
  Frequent   — regular use (weekly or multiple times per month) supporting \
recurring business decisions
  Periodic   — occasional use (monthly, quarterly, or scheduled reporting/analysis)
  Infrequent — rare, ad hoc, annual, or only under specific conditions

Working with the data provided:
  - Model purpose is a free-text field. Classify each model's purpose against \
the purpose lists in the IMPACT rules; when a purpose is ambiguous or missing, \
take the more conservative (more severe) reading.
  - Model class is a preset field: Credit & Fraud, Marketing, Technology / \
Operations, AML (Anti-Money Laundering), Finance/Treasury, Capital, or Climate \
Risk. Use it as a supporting signal when classifying purpose (e.g., Capital or \
AML class often indicates a Critical-list purpose), but the purpose text governs.
  - Frequency of use is NOT a field in the model data. Infer it from each \
model's purpose, class, and the entity overviews using the definitions \
above; when uncertain, use the more severe plausible frequency.
  - Explain the qualitative considerations that drive the inherent risk — the \
underlying risk, its significance, and the volume of underlying relationships.

Cross-check: If the entity's models are confirmed in scope but LUminate suggests \
Not Applicable, a cross-check warning is included. Weight the confirmed model inventory \
as the authoritative signal.

Rules:
  - Assess every entity listed, even if LUminate shows it as "Not Applicable" — the \
RCO's view takes precedence for this exercise
  - Do NOT reference or defer to the LUminate suggested status in your rating
  - proposed_rating must be exactly one of: Low, Medium, High, Critical
  - rating_rationale is 1-2 sentences stating the Impact and Likelihood you derived \
and the specific evidence (model purposes, impact categories, assumed frequency of \
use) that drove them

OUTPUT FORMAT — strict:
Return a single JSON array. Each element:
  {
    "entity_id": "<string>",
    "entity_name": "<string>",
    "proposed_rating": "Low" | "Medium" | "High" | "Critical",
    "rating_rationale": "<1-2 sentences>"
  }

Output ONLY the JSON array — no prose before or after, no markdown code fence.

Example:
[
  {"entity_id": "AE-1", "entity_name": "North America Cards",
    "proposed_rating": "High",
    "rating_rationale": "Impact is High (two High-impact models supporting indirect \
credit decisions, no models with a Regulatory/Capital/P&L purpose) and Likelihood is \
High (models appear embedded in recurring underwriting campaigns, assumed Frequent \
use), combining to High inherent risk per Table 3.1."}
]
"""


def _build_system_prompt(l2_name: str) -> str:
    return f"""You are an internal audit risk rating specialist. You are assessing the \
INHERENT risk rating for "{l2_name}" for each audit entity in the portfolio.

For each entity listed below, propose a risk rating using the four-point scale:
  Low | Medium | High | Critical

Base your rating on:
1. The Optro entity overview (most current — authored by the audit team)
2. The Archer entity overview (upstream extract — may be slightly older)
3. Whether this risk is Core or Auxiliary to the entity's primary activities
4. The L2 / L3 / L4 risk taxonomy definitions
5. The RCO's applicability and rating guidance (provided below)
6. Open audit issues tagged to this risk (ancillary signal)

Rating guidance:
  Low      — Risk exists but entity activities have minimal exposure; strong mitigating \
context
  Medium   — Moderate exposure; risk is present and warrants monitoring but is not a \
primary driver
  High     — Significant exposure; risk is a primary consideration for this entity's \
operations
  Critical — Severe or pervasive exposure; risk is central to the entity's risk profile \
and requires heightened focus

RCO Guidance for {l2_name}:
{_RCO_GUIDANCE_PLACEHOLDER}

Rules:
  - Assess every entity listed, even if LUminate shows it as "Not Applicable" — the \
RCO's view takes precedence for this exercise
  - Do NOT reference or defer to the LUminate suggested status in your rating
  - proposed_rating must be exactly one of: Low, Medium, High, Critical
  - rating_rationale is 1-2 sentences citing the specific evidence that drove your rating
  - Do NOT include risk-rating words in the rationale except as part of the rating itself

OUTPUT FORMAT — strict:
Return a single JSON array. Each element:
  {{
    "entity_id": "<string>",
    "entity_name": "<string>",
    "proposed_rating": "Low" | "Medium" | "High" | "Critical",
    "rating_rationale": "<1-2 sentences>"
  }}

Output ONLY the JSON array — no prose before or after, no markdown code fence.

Example:
[
  {{"entity_id": "AE-1", "entity_name": "North America Cards",
    "proposed_rating": "High",
    "rating_rationale": "The entity has direct customer-facing sales and servicing \
activity across consumer and co-brand segments, with documented conduct concerns in \
complaint handling and CFPB examination requirements making this a primary risk area."}}
]
"""


def _load_l2_definitions(l2_name: str) -> dict:
    """Return the definition + children for a single L2 from L2_Risk_Taxonomy.xlsx."""
    l2_file = _PROJECT_ROOT / "data" / "input" / "L2_Risk_Taxonomy.xlsx"
    if not l2_file.exists():
        logger.warning("L2_Risk_Taxonomy.xlsx not found — definitions will be omitted")
        return {}

    df = pd.read_excel(l2_file)
    ffill_cols = [c for c in ("L1", "L2", "L3", "L4") if c in df.columns]
    if ffill_cols:
        df[ffill_cols] = df[ffill_cols].ffill()

    has_l3 = "L3" in df.columns
    has_l3_def = "L3 Definition" in df.columns
    has_l4 = "L4" in df.columns
    has_l4_def = "L4 Definition" in df.columns

    entry: dict = {"l1": "", "definition": "", "children": []}
    target = l2_name.strip().lower()

    for _, row in df.iterrows():
        l2_val = str(row.get("L2", "")).strip()
        if l2_val.lower() != target:
            continue

        l2_def = str(row.get("L2 Definition", "")).strip()
        if not entry["definition"] and l2_def and l2_def.lower() != "nan":
            entry["definition"] = l2_def
        if not entry["l1"]:
            l1_val = str(row.get("L1", "")).strip()
            if l1_val and l1_val.lower() != "nan":
                entry["l1"] = l1_val

        if not has_l3:
            continue
        l3_name = str(row.get("L3", "")).strip()
        if not l3_name or l3_name.lower() in ("nan", ""):
            continue
        l3_def = str(row.get("L3 Definition", "")).strip() if has_l3_def else ""
        l4_name = str(row.get("L4", "")).strip() if has_l4 else ""
        l4_def = str(row.get("L4 Definition", "")).strip() if has_l4_def else ""

        l3_entry = next((c for c in entry["children"] if c["l3"] == l3_name), None)
        if l3_entry is None:
            l3_entry = {"l3": l3_name, "l3_def": l3_def, "l4s": []}
            entry["children"].append(l3_entry)

        if l4_name and l4_name.lower() not in ("nan", ""):
            if not any(l["l4"] == l4_name for l in l3_entry["l4s"]):
                l3_entry["l4s"].append({"l4": l4_name, "l4_def": l4_def})

    return entry


def _load_optro_overviews() -> dict[str, str]:
    """Return {ae_id: overview_text} from the latest optro_ae_overview_*.xlsx."""
    optro_file = latest_input(
        _PROJECT_ROOT / "data" / "input",
        ["optro_ae_overview_*.xlsx"],
        log_label="Optro AE overview",
    )
    if optro_file is None:
        logger.warning("No optro_ae_overview_*.xlsx found — Optro overviews will be omitted")
        return {}

    df = pd.read_excel(optro_file)
    result = {}
    for _, row in df.iterrows():
        ae_id = str(row.get("AE ID", "")).strip()
        overview = str(row.get("AE Overview", "")).strip()
        if ae_id and ae_id.lower() not in ("nan", "") and overview.lower() != "nan":
            result[ae_id] = overview
    logger.info(f"Loaded {len(result)} Optro overviews from {optro_file.name}")
    return result


def _empty(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float):
        import math
        return math.isnan(v)
    return str(v).strip().lower() in ("", "nan", "none")


def _relationship_label(core_flag, aux_flag) -> str:
    is_core = not _empty(core_flag) and str(core_flag).strip().lower() not in ("false", "0", "nan")
    is_aux = not _empty(aux_flag) and str(aux_flag).strip().lower() not in ("false", "0", "nan")
    if is_core:
        return "Core"
    if is_aux:
        return "Auxiliary"
    return "Not specified"


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 characters per token (GPT convention)."""
    return max(1, len(text) // 4)


def generate_prompts(
    l2_name: str,
    workbook_path: str,
    output_dir: str,
    max_aes_per_batch: int = 25,
    dry_run: bool = False,
    include_key_risks: bool = False,
):
    output_dir = Path(output_dir)
    is_model_risk = l2_name.strip().lower() in ("model risk", "model")

    cfg = _load_config()

    xls = pd.ExcelFile(workbook_path)
    audit_df = pd.read_excel(xls, sheet_name="Audit_Review")
    sbs_df = (
        pd.read_excel(xls, sheet_name="Side_by_Side")
        if "Side_by_Side" in xls.sheet_names else None
    )
    findings_df = None
    if "Source - Findings" in xls.sheet_names:
        findings_df = pd.read_excel(xls, sheet_name="Source - Findings", header=1)
    key_risks_df = None
    if include_key_risks and "Source - Key Risks" in xls.sheet_names:
        key_risks_df = pd.read_excel(xls, sheet_name="Source - Key Risks", header=1)

    model_risk_legacy: dict[str, dict] = {}
    model_inventory: dict[str, dict] = {}
    if is_model_risk:
        model_risk_legacy = _load_model_risk_legacy(cfg)
        model_inventory = _load_model_inventory(cfg)

    optro_overviews = _load_optro_overviews()
    l2_def_info = _load_l2_definitions(l2_name)

    # All AEs that have a row for this L2 — regardless of status.
    l2_rows = audit_df[audit_df["New L2"] == l2_name].copy()
    if l2_rows.empty:
        print(f'No rows found for L2 "{l2_name}" in Audit_Review.')
        sys.exit(1)

    entities = sorted(l2_rows["Entity ID"].unique())
    mode = "DRY RUN" if dry_run else "Building"
    print(f'{mode} — L2 "{l2_name}": {len(entities)} entities')

    # Build one prompt block per entity.
    entity_blocks: list[tuple[str, str]] = []
    for eid in entities:
        l2_row = l2_rows[l2_rows["Entity ID"] == eid].iloc[0]
        all_ae_rows = audit_df[audit_df["Entity ID"] == eid]
        first = all_ae_rows.iloc[0]

        name = str(l2_row.get("Entity Name", first.get("Entity Name", ""))).strip()

        # Core / Auxiliary from Side_by_Side
        relationship = "Not specified"
        if sbs_df is not None:
            sbs_match = sbs_df[
                (sbs_df["entity_id"].astype(str) == eid) &
                (sbs_df["new_l2"].astype(str) == l2_name)
            ]
            if not sbs_match.empty:
                sr = sbs_match.iloc[0]
                relationship = _relationship_label(
                    sr.get("core_flag"), sr.get("aux_flag")
                )

        block = f"\n{'='*60}\n"
        block += f"ENTITY: {eid}"
        if name and name.lower() != "nan":
            block += f" — {name}"
        block += "\n"
        block += f"Risk relationship to {l2_name}: {relationship}\n"
        block += f"LUminate suggested status: {l2_row.get('Suggested Status', 'N/A')}"
        block += " [informational only — do not factor into your rating]\n"
        block += f"{'='*60}\n\n"

        # Optro overview (most current)
        optro_text = optro_overviews.get(eid, "")
        if optro_text:
            block += f"Entity Overview (Optro — most current):\n{optro_text}\n\n"

        # Archer overview
        archer_text = str(first.get("Entity Overview", "")).strip()
        if archer_text and archer_text.lower() not in ("nan", ""):
            block += f"Entity Overview (Archer — upstream extract):\n{archer_text}\n\n"

        # L2 / L3 / L4 definitions
        block += f"--- {l2_name} Risk Taxonomy ---\n"
        defn = l2_def_info.get("definition", "")
        if defn:
            l1 = l2_def_info.get("l1", "")
            block += f"L1: {l1}\n" if l1 else ""
            block += f"L2 ({l2_name}): {defn}\n"
        children = l2_def_info.get("children", [])
        if children:
            block += "\nL3 sub-domains:\n"
            for child in children:
                l3_def_text = child.get("l3_def", "")
                if l3_def_text:
                    block += f"  {child['l3']}: {l3_def_text}\n"
                else:
                    block += f"  {child['l3']}\n"
                for l4 in child.get("l4s", []):
                    l4_def_text = l4.get("l4_def", "")
                    if l4_def_text:
                        block += f"      * {l4['l4']}: {l4_def_text}\n"
                    else:
                        block += f"      * {l4['l4']}\n"

        # Key risks (optional — omitted by default)
        if key_risks_df is not None:
            eid_col_kr = next(
                (c for c in ("entity_id", "Audit Entity", "Audit Entity ID")
                 if c in key_risks_df.columns),
                None,
            )
            desc_col_kr = next(
                (c for c in ("risk_description", "Key Risk Description")
                 if c in key_risks_df.columns),
                None,
            )
            id_col_kr = next(
                (c for c in ("risk_id", "Key Risk ID") if c in key_risks_df.columns),
                None,
            )
            block += f"\n--- Key Risk Descriptions ---\n"
            if eid_col_kr and desc_col_kr:
                kr_matched = key_risks_df[
                    key_risks_df[eid_col_kr].astype(str).str.strip() == eid
                ]
                if not kr_matched.empty:
                    for _, kr in kr_matched.iterrows():
                        rid = str(kr.get(id_col_kr, "")).strip() if id_col_kr else ""
                        desc = str(kr.get(desc_col_kr, "")).strip()[:300]
                        if desc and desc.lower() not in ("nan", ""):
                            prefix = f"{rid}: " if rid and rid.lower() != "nan" else ""
                            block += f"  • {prefix}{desc}\n"
                else:
                    block += "  None on file\n"
            else:
                block += "  (key risk columns not matched)\n"

        # Model Risk: models in scope + cross-check
        # (legacy rating deliberately excluded from the prompt — it would anchor
        # the LLM to the old assessment; it surfaces in consolidation instead)
        if is_model_risk:
            legacy = model_risk_legacy.get(eid, {})
            models_text = legacy.get("models_text", "")

            model_ids = _parse_model_ids(models_text)
            block += f"\n--- Models in Scope ({len(model_ids)}) ---\n"
            matched_count = 0
            if model_ids:
                for mid in model_ids:
                    inv = model_inventory.get(mid, {})
                    if inv:
                        matched_count += 1
                        parts = [f"Model {mid}", inv.get("name", "")]
                        if inv.get("class_"):
                            parts.append(f"Class: {inv['class_']}")
                        if inv.get("markets"):
                            parts.append(f"Markets: {inv['markets']}")
                        if inv.get("impact"):
                            parts.append(f"Impact: {inv['impact']}")
                        if inv.get("purpose"):
                            parts.append(f"Purpose: {inv['purpose'][:300]}")
                        block += f"  • {' | '.join(p for p in parts if p)}\n"
                    else:
                        block += f"  • Model {mid} (not found in inventory)\n"
            else:
                block += "  None confirmed in model inventory\n"

            luminate_status = str(l2_row.get("Suggested Status", "")).strip()
            if matched_count > 0 and luminate_status.lower() in ("not applicable", "n/a"):
                block += (
                    f"\n  [!] CROSS-CHECK: LUminate suggests Not Applicable, but "
                    f"{matched_count} model(s) are confirmed in scope for this entity. "
                    f"A Not Applicable rating would be inconsistent with the model inventory.\n"
                )

        # Open issues tagged to this L2
        block += f"\n--- Open Issues Tagged to {l2_name} ---\n"
        if findings_df is not None:
            eid_col = next(
                (c for c in ("entity_id", "Audit Entity ID") if c in findings_df.columns),
                None,
            )
            l2_col = next(
                (c for c in ("l2_risk", "Mapped To L2(s)", "Risk Dimension Categories")
                 if c in findings_df.columns),
                None,
            )
            if eid_col and l2_col:
                matched = findings_df[
                    (findings_df[eid_col].astype(str).str.strip() == eid) &
                    (findings_df[l2_col].astype(str).str.contains(l2_name, na=False))
                ]
                if not matched.empty:
                    for _, f in matched.iterrows():
                        fid = f.get("issue_id", "")
                        title = f.get("issue_title", "")
                        sev = f.get("severity", "")
                        fstatus = f.get("status", "")
                        parts = [str(x) for x in (fid, title, sev, fstatus)
                                 if not _empty(x)]
                        block += "  • " + " | ".join(parts) + "\n"
                else:
                    block += "  None on file\n"
            else:
                block += "  (findings columns not matched)\n"
        else:
            block += "  (no findings data available)\n"

        entity_blocks.append((eid, block))

    # Batch into groups.
    batches: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    for item in entity_blocks:
        if current and len(current) >= max_aes_per_batch:
            batches.append(current)
            current = []
        current.append(item)
    if current:
        batches.append(current)

    system_prompt_text = (
        _build_system_prompt_model_risk() if is_model_risk
        else _build_system_prompt(l2_name)
    )
    system_tokens = _estimate_tokens(system_prompt_text)

    # -------------------------------------------------------------------
    # Dry-run: print token estimates and batch plan without writing files.
    # -------------------------------------------------------------------
    if dry_run:
        entity_token_counts = [
            (eid, _estimate_tokens(block)) for eid, block in entity_blocks
        ]
        all_entity_tokens = [t for _, t in entity_token_counts]
        total_entity_tokens = sum(all_entity_tokens)

        print()
        print(f"  System prompt:  ~{system_tokens:,} tokens (shared across all batches)")
        print(f"  Entity blocks:  ~{total_entity_tokens:,} tokens total across {len(entities)} entities")
        print(f"                  min {min(all_entity_tokens):,} / "
              f"avg {total_entity_tokens // len(entities):,} / "
              f"max {max(all_entity_tokens):,} tokens per entity")
        print()
        print(f"  Batch plan ({len(batches)} batch(es) at --max-aes {max_aes_per_batch}):")
        print(f"  {'Batch':<12} {'Entities':<10} {'Entity tokens':>14} {'+ system':>10} {'= total':>10}")
        print(f"  {'-'*58}")
        for batch_num, batch in enumerate(batches, start=1):
            ae_ids = [eid for eid, _ in batch]
            batch_entity_tokens = sum(
                t for eid, t in entity_token_counts if eid in ae_ids
            )
            batch_total = system_tokens + batch_entity_tokens
            print(f"  batch_{batch_num:03d}    {len(ae_ids):<10} "
                  f"{batch_entity_tokens:>14,} {system_tokens:>10,} {batch_total:>10,}")
        print(f"  {'-'*58}")
        grand_total = system_tokens * len(batches) + total_entity_tokens
        print(f"  {'TOTAL':<12} {len(entities):<10} "
              f"{total_entity_tokens:>14,} {system_tokens * len(batches):>10,} {grand_total:>10,}")
        print()
        print("  Note: estimates use ~4 chars/token. Actual counts depend on")
        print("  the RCO guidance you paste in and ChatGPT's tokenizer.")
        print()
        print("  No files written. Remove --dry-run to generate prompt files.")
        return

    # -------------------------------------------------------------------
    # Full run: write batch folders and manifests.
    # -------------------------------------------------------------------
    output_dir.mkdir(parents=True, exist_ok=True)

    overall_manifest: dict = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "l2": l2_name,
        "source_workbook": Path(workbook_path).name,
        "total_entities": len(entities),
        "batch_count": len(batches),
        "max_aes_per_batch": max_aes_per_batch,
        "batches": [],
    }

    for batch_num, batch in enumerate(batches, start=1):
        batch_name = f"batch_{batch_num:03d}"
        batch_dir = output_dir / batch_name
        batch_dir.mkdir(parents=True, exist_ok=True)

        ae_ids = [eid for eid, _ in batch]
        manifest = {
            "batch_number": batch_num,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "l2": l2_name,
            "source_workbook": Path(workbook_path).name,
            "entity_count": len(ae_ids),
            "entities": ae_ids,
            "expected_response_fields": [
                "entity_id", "entity_name", "proposed_rating", "rating_rationale"
            ],
            "valid_rating_values": VALID_RATINGS,
        }
        (batch_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

        # prompt.md
        with open(batch_dir / "prompt.md", "w", encoding="utf-8") as f:
            f.write(f"# LUminate RCO Rating Prompt — {l2_name} — {batch_name}\n\n")
            f.write("## System Prompt\n\n")
            f.write(system_prompt_text)
            f.write("\n\n## Entity Data\n\n")
            f.write(
                "Review each entity below and propose a risk rating for "
                f'"{l2_name}".\n\n'
            )
            for _, block_text in batch:
                f.write(block_text)
            f.write("\n\n## Output Format Reminder\n\n")
            f.write("Return a single JSON array. Each element:\n\n")
            f.write("```\n")
            f.write(
                '{"entity_id": "...", "entity_name": "...", '
                '"proposed_rating": "Low|Medium|High|Critical", '
                '"rating_rationale": "<1-2 sentences>"}\n'
            )
            f.write("```\n\n")
            f.write("- Output ONLY the JSON array (no prose, no code fence around the whole array).\n")
            f.write("- proposed_rating must be exactly one of: Low, Medium, High, Critical.\n")
            f.write("- rating_rationale is 1-2 sentences; no applicability language.\n\n")
            f.write(f"**Entities in this batch:** {', '.join(ae_ids)}\n")

        (batch_dir / "response.json").write_text("[]\n", encoding="utf-8")

        overall_manifest["batches"].append({
            "batch": batch_name,
            "entities": ae_ids,
        })
        print(f"  {batch_name}/: {len(ae_ids)} entities")

    (output_dir / "manifest.json").write_text(
        json.dumps(overall_manifest, indent=2), encoding="utf-8"
    )

    print(f"\nGenerated {len(batches)} batch folder(s) in {output_dir}/")
    print(f"  Total entities: {len(entities)}")
    print()
    print("Workflow:")
    print("  1. For each batch_NNN/ folder:")
    print("     - Open prompt.md")
    if is_model_risk:
        print("     - Replace the [PASTE IAG PROCEDURE MANUAL TABLE 3.1] placeholder")
        print("       (RCO impact/likelihood guidance is already embedded)")
    else:
        print("     - Replace the [PASTE RCO GUIDANCE HERE] placeholder with the RCO's guidance")
    print("     - Paste into ChatGPT")
    print("     - Paste ChatGPT's JSON array into response.json (replacing [])")
    print("  2. Collect response.json files for downstream use")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Export RCO rating prompts for a single L2 risk"
    )
    parser.add_argument(
        "--l2",
        required=True,
        help='L2 name, e.g. "Conduct" or "Internal Fraud"',
    )
    parser.add_argument(
        "--workbook",
        help="Path to transformer output Excel (default: latest in data/output/)",
    )
    parser.add_argument(
        "--max-aes",
        type=int,
        default=25,
        dest="max_aes",
        help="Max audit entities per batch (default: 25)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Print token estimates and batch plan without writing any files",
    )
    parser.add_argument(
        "--include-key-risks",
        action="store_true",
        dest="include_key_risks",
        help="Include key risk descriptions in each entity block (omitted by default)",
    )
    ns = parser.parse_args()

    if ns.workbook:
        workbook = ns.workbook
    else:
        latest = latest_input(
            _PROJECT_ROOT / "data" / "output",
            ["transformed_risk_taxonomy_*.xlsx"],
            log_label="transformer output",
        )
        if latest is None:
            print("No transformer output found in data/output/")
            sys.exit(1)
        workbook = str(latest)

    l2_slug = ns.l2.lower().replace(" ", "_").replace("/", "_")
    out_dir = str(_PROJECT_ROOT / "data" / "output" / "rco_rating_prompts" / l2_slug)

    generate_prompts(
        l2_name=ns.l2,
        workbook_path=workbook,
        output_dir=out_dir,
        max_aes_per_batch=ns.max_aes,
        dry_run=ns.dry_run,
        include_key_risks=ns.include_key_risks,
    )
