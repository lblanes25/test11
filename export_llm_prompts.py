"""
LLM Prompt Export for Applicability Review
===========================================
Reads the transformer output and generates structured prompt files for
items needing LLM review (Applicability Undetermined and Assumed N/A — Verify).

Each prompt contains full context: entity overview, L2 definition, source
rationale, key risks, findings, applications, and signals.

The LLM responds with a JSON array (saved to each batch's response.json).
consolidate_llm_responses.py merges all batches into a single
llm_overrides_<ts>.csv that the main pipeline picks up on the next run.

Usage:
    python export_llm_prompts.py                    # uses latest output
    python export_llm_prompts.py path/to/output.xlsx  # specific file
"""

import logging
import pandas as pd
import yaml
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent

SYSTEM_PROMPT = """You are an internal audit risk classification specialist. You are reviewing audit entities that are being migrated from a legacy 14-pillar risk taxonomy to a new 23-category (L2) risk taxonomy.

For each L2 risk listed below, determine whether it is APPLICABLE or NOT_APPLICABLE to the entity based on the evidence provided. Consider:
- The entity overview (what the entity does)
- The source rationale text (what the legacy assessment said)
- Sub-risk descriptions (specific risks identified for this entity)
- Open findings (active audit issues)
- Application and third party mappings (operational dependencies)
- Cross-boundary signals (keywords from other pillars that suggest relevance)

Rules:
- If the evidence suggests this risk category is relevant to the entity's operations, classify as APPLICABLE
- If there is no meaningful connection between the entity and the risk category, classify as NOT_APPLICABLE
- Do NOT assign, suggest, or imply risk ratings — only determine applicability
- When in doubt, classify as APPLICABLE — it's better to include a risk for human review than to exclude it
- Each L2 block lists its L3 (and where present L4) sub-domains and a "Terms that count as evidence" line. If the rationale mentions ANY sub-domain or evidence term (or a clear paraphrase / "anti-X" framing of one), treat that as evidence for this L2 — do NOT dismiss it because the L2 definition's prose uses different words.

CONFLICT REVIEW — special case:
Some rows below are marked "Not Applicable" by the legacy filer but have contradicting signals (apps/TPs/models tagged to the entity, auxiliary risk dimensions, or keyword matches in the pillar rationale). These items will be marked in the prompt with a [CONFLICT REVIEW] tag. For these:
- Read the signals carefully and decide whether they genuinely contradict the legacy N/A determination
- If they do contradict, classify as APPLICABLE and your reasoning MUST start with "Originally marked N/A but auditor should reconsider because" followed by the specific contradicting evidence
- If the signals don't actually contradict (e.g., apps tagged but not relevant to this L2's domain), classify as NOT_APPLICABLE and your reasoning should start with "Confirming N/A despite signals because" and explain why the signals are not material to this L2

For each determination, provide a one-sentence reasoning citing the specific evidence that supports your classification. Reference which evidence drove your decision: entity overview, rationale text, key risk descriptions, findings, or signals.

OUTPUT FORMAT — strict:
Return a single JSON array. Each element is an object with these exact fields, in this order, no extras:
  {
    "entity_id": "<string>",
    "source_legacy_pillar": "<string>",
    "classified_l2": "<string>",
    "determination": "applicable" | "not_applicable",
    "reasoning": "<one sentence>"
  }

Rules for the JSON:
- Output ONLY the JSON array — no prose before or after, no markdown code fence.
- determination must be exactly the string "applicable" or "not_applicable" (lowercase, no other variants).
- reasoning is a single sentence; do not embed newlines, do not include risk-rating language ("high", "moderate", "low", "elevated", "rating").

Example output (verbatim shape):
[
  {"entity_id": "AE-3", "source_legacy_pillar": "Operational", "classified_l2": "Conduct", "determination": "applicable", "reasoning": "The rationale references consumer complaint handling and the key risk descriptions cite conduct risk monitoring processes."},
  {"entity_id": "AE-3", "source_legacy_pillar": "Operational", "classified_l2": "Business Disruption", "determination": "not_applicable", "reasoning": "No evidence of business continuity or disaster recovery concerns in the entity overview or key risk descriptions."},
  {"entity_id": "AE-7", "source_legacy_pillar": "Operational", "classified_l2": "Data", "determination": "applicable", "reasoning": "Originally marked N/A but auditor should reconsider because 4 primary IT applications and rationale keywords (data quality, data governance) indicate Data risk exposure."},
  {"entity_id": "AE-7", "source_legacy_pillar": "Operational", "classified_l2": "Internal Fraud", "determination": "not_applicable", "reasoning": "Confirming N/A despite signals because the auxiliary risk dimension match is unrelated to internal fraud (the dimension references third-party fraud prevention, which is a different L2)."}
]
"""


_FRAUD_L3_SUBTYPES = {
    "External Fraud - First Party",
    "External Fraud - Victim Fraud",
    "Internal Fraud",
}


def load_l2_definitions() -> tuple[dict, dict]:
    """Load L2 definitions + sub-domain context from taxonomy config.

    The real enterprise taxonomy file has L1/L2/L3 (and optionally L4) columns
    with merged cells that pandas reads as NaN on continuation rows; forward-fill
    restores them.

    Returns (l2_defs, keyword_map):
      l2_defs keyed by Audit_Review.New L2 (canonical L2 or Fraud L3 sub-type).
      Each value: {l1, definition, children: [{l3, l3_def, l4s: [{l4, l4_def}]}]}
      children is empty when no L3 data exists for the L2 (or for Fraud L3
      sub-types — the L3 IS the unit).
      keyword_map is the YAML keyword_map dict, used downstream as a
      concrete-vocabulary hint for the LLM.
    """
    config_path = _PROJECT_ROOT / "config" / "taxonomy_config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    keyword_map = cfg.get("keyword_map", {}) or {}

    l2_defs = {}
    l2_file = _PROJECT_ROOT / "data" / "input" / "L2_Risk_Taxonomy.xlsx"
    if l2_file.exists():
        df = pd.read_excel(l2_file)
        ffill_cols = [c for c in ("L1", "L2", "L3", "L4") if c in df.columns]
        if ffill_cols:
            df[ffill_cols] = df[ffill_cols].ffill()

        has_l3 = "L3" in df.columns
        has_l3_def = "L3 Definition" in df.columns
        has_l4 = "L4" in df.columns
        has_l4_def = "L4 Definition" in df.columns

        for _, row in df.iterrows():
            l2_name = row.get("L2", "")
            if pd.isna(l2_name) or not str(l2_name).strip():
                continue
            l2_name = str(l2_name).strip()

            l3_name = str(row.get("L3", "")).strip() if has_l3 else ""
            l3_def = str(row.get("L3 Definition", "")).strip() if has_l3_def else ""
            l4_name = str(row.get("L4", "")).strip() if has_l4 else ""
            l4_def = str(row.get("L4 Definition", "")).strip() if has_l4_def else ""
            l2_def = str(row.get("L2 Definition", "")).strip()

            if l3_name and l3_name in _FRAUD_L3_SUBTYPES:
                l2_defs.setdefault(l3_name, {
                    "l1": row.get("L1", ""),
                    "definition": l3_def or l2_def,
                    "children": [],
                })
                continue

            entry = l2_defs.setdefault(l2_name, {
                "l1": row.get("L1", ""),
                "definition": l2_def,
                "children": [],
            })
            if not entry["definition"] and l2_def:
                entry["definition"] = l2_def

            if l3_name and l3_name.lower() not in ("nan", ""):
                l3_entry = next((c for c in entry["children"] if c["l3"] == l3_name), None)
                if l3_entry is None:
                    l3_entry = {"l3": l3_name, "l3_def": l3_def, "l4s": []}
                    entry["children"].append(l3_entry)
                elif not l3_entry["l3_def"] and l3_def:
                    l3_entry["l3_def"] = l3_def

                if l4_name and l4_name.lower() not in ("nan", ""):
                    if not any(l["l4"] == l4_name for l in l3_entry["l4s"]):
                        l3_entry["l4s"].append({"l4": l4_name, "l4_def": l4_def})

    # Fallback: build from taxonomy config
    if not l2_defs:
        for l1, l2_list in cfg.get("new_taxonomy", {}).items():
            for l2 in l2_list:
                l2_defs[l2] = {"l1": l1, "definition": "", "children": []}

    return l2_defs, keyword_map


def generate_prompts(excel_path: str, output_dir: str, max_items_per_batch: int = 75):
    """Generate LLM prompt files from transformer output.

    Args:
        excel_path: Path to the transformer output Excel
        output_dir: Directory to write prompt files
        max_items_per_batch: Max review items per batch. AEs are packed
            greedily up to this cap and never split across batches; an AE
            larger than the cap gets its own batch.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load sheets
    xls = pd.ExcelFile(excel_path)
    audit_df = pd.read_excel(xls, sheet_name="Audit_Review")
    audit_df = audit_df.rename(columns={"Proposed Status": "Status",
                                         "Proposed Rating": "Inherent Risk Rating"})
    detail_df = pd.read_excel(xls, sheet_name="Side_by_Side") if "Side_by_Side" in xls.sheet_names else None
    findings_df = pd.read_excel(xls, sheet_name="Source - Findings") if "Source - Findings" in xls.sheet_names else None
    key_risks_df = pd.read_excel(xls, sheet_name="Source - Key Risks") if "Source - Key Risks" in xls.sheet_names else None

    # Load L2 definitions + keyword map for sub-domain hints
    l2_defs, keyword_map = load_l2_definitions()

    # Filter to items needing review.
    # Three categories qualify:
    #   1. Applicability Undetermined — tool found no evidence either way
    #   2. Assumed N/A — Verify — tool inferred N/A but wasn't confident
    #   3. Not Applicable WITH contradicting signals — legacy filer said N/A
    #      but inventory / aux / core / cross-boundary flags or keyword
    #      matches in the pillar rationale suggest otherwise. AI is asked to
    #      validate or challenge the legacy N/A given the signals.
    review_statuses = ["Applicability Undetermined", "Assumed N/A — Verify"]
    primary_review = audit_df[audit_df["Status"].isin(review_statuses)]

    def _has_signals(row) -> bool:
        # Additional Signals aggregates app/tp/model/aux/core flags from
        # transformed_df (review_builders.py:_collect_flag). Non-empty here
        # means at least one signal flag fired on this row.
        sig = str(row.get("Additional Signals", "") or "").strip()
        if sig and sig.lower() not in ("nan", "none"):
            return True
        # Decision Basis on a source_not_applicable row leads with "Review note:"
        # when keyword evidence or signals exist (see enrichment.py). Catch
        # rows where the keyword-only case fires (no inventory but rationale
        # keywords matched).
        db = str(row.get("Decision Basis", "") or "").strip()
        return db.startswith("Review note:")

    na_with_signals = audit_df[
        (audit_df["Status"] == "Not Applicable")
        & audit_df.apply(_has_signals, axis=1)
    ]

    review_df = pd.concat([primary_review, na_with_signals]).drop_duplicates()

    if review_df.empty:
        print("No items need LLM review — all mappings already determined.")
        return

    # Group by entity
    entities = sorted(review_df["Entity ID"].unique())
    print(f"Generating prompts for {len(entities)} entities, "
          f"{len(review_df)} items needing review")

    # Helper to check if value is empty
    def _empty(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return True
        return str(v).strip().lower() in ("", "nan", "none")

    # Build prompts
    all_prompts = []
    for eid in entities:
        entity_rows = review_df[review_df["Entity ID"] == eid]
        item_count = int(len(entity_rows))
        all_entity_rows = audit_df[audit_df["Entity ID"] == eid]
        first = all_entity_rows.iloc[0]

        # Entity context
        prompt = f"\n{'='*60}\n"
        prompt += f"ENTITY: {eid}"
        name = first.get("Entity Name", "")
        if not _empty(name):
            prompt += f" — {name}"
        prompt += "\n"

        overview = first.get("Entity Overview", "")
        if not _empty(overview):
            prompt += f"Overview: {overview}\n"

        al = first.get("Audit Leader", "")
        pga = first.get("PGA", "")
        meta_parts = []
        if not _empty(al):
            meta_parts.append(f"Audit Leader: {al}")
        if not _empty(pga):
            meta_parts.append(f"PGA: {pga}")
        if meta_parts:
            prompt += " | ".join(meta_parts) + "\n"

        # Applications and engagements (from any row for this entity)
        for col_label, col_name in [
            ("Primary IT Applications", "PRIMARY IT APPLICATIONS (MAPPED)"),
            ("Secondary IT Applications", "SECONDARY IT APPLICATIONS (RELATED OR RELIED ON)"),
            ("Primary Third Party", "PRIMARY TLM THIRD PARTY ENGAGEMENT"),
            ("Secondary Third Party", "SECONDARY TLM THIRD PARTY ENGAGEMENTS (RELATED OR RELIED ON)"),
        ]:
            # Check detail_df for these columns since they're from legacy data
            if detail_df is not None and col_name in detail_df.columns:
                ed = detail_df[detail_df["entity_id"].astype(str) == eid]
                if not ed.empty:
                    vals = ed[col_name].dropna().unique()
                    if len(vals) > 0 and not _empty(vals[0]):
                        prompt += f"{col_label}: {vals[0]}\n"

        prompt += f"{'='*60}\n\n"

        # Each L2 needing review
        for _, row in entity_rows.iterrows():
            l2 = row.get("New L2", "")
            l1 = row.get("New L1", "")
            status = row.get("Status", "")
            legacy_source = row.get("Legacy Source", "")

            # Conflict review case: legacy filer rated Not Applicable but
            # signals contradict. Flag the row so the AI knows to apply the
            # special CONFLICT REVIEW reasoning template from SYSTEM_PROMPT.
            is_conflict = (str(status).strip() == "Not Applicable")

            prompt += f"---\n"
            if is_conflict:
                prompt += "[CONFLICT REVIEW] Legacy filer rated this Not Applicable, but contradicting signals exist. Validate or challenge.\n"
            prompt += f"L2 Risk: {l2}\n"
            prompt += f"Parent L1: {l1}\n"

            # L2 definition (or L3 definition for Fraud sub-types)
            l2_info = l2_defs.get(l2, {})
            defn = l2_info.get("definition", "")
            if defn:
                prompt += f"Definition: {defn}\n"
                if l2 in _FRAUD_L3_SUBTYPES:
                    prompt += '(Sub-type of L2 "Fraud (External and Internal)")\n'
            else:
                logger.warning(f"  No definition found for L2 '{l2}' (entity {eid})")

            children = l2_info.get("children", [])
            if children:
                prompt += "\nL3 sub-domains of this L2:\n"
                for child in children:
                    l3_label = child["l3"]
                    l3_def_text = child.get("l3_def", "")
                    if l3_def_text:
                        prompt += f"  - {l3_label}: {l3_def_text}\n"
                    else:
                        prompt += f"  - {l3_label}\n"
                    for l4 in child.get("l4s", []):
                        l4_label = l4["l4"]
                        l4_def_text = l4.get("l4_def", "")
                        if l4_def_text:
                            prompt += f"      * {l4_label}: {l4_def_text}\n"
                        else:
                            prompt += f"      * {l4_label}\n"

            terms = keyword_map.get(l2, []) or []
            if terms:
                prompt += "\nTerms that count as evidence for this L2 (paraphrases also qualify):\n"
                prompt += "  " + ", ".join(terms) + "\n"

            prompt += f"\nCurrent Status: {status}\n"

            # Legacy source and rationale
            if not _empty(legacy_source):
                base_pillar = str(legacy_source).split(" (also")[0].strip()
                prompt += f"Legacy Source: {base_pillar}\n"

            # Get detail row for rationale
            if detail_df is not None:
                detail_match = detail_df[
                    (detail_df["entity_id"].astype(str) == eid) &
                    (detail_df["new_l2"] == l2)
                ]
                if not detail_match.empty:
                    dr = detail_match.iloc[0]
                    rationale = dr.get("source_rationale", "")
                    if not _empty(rationale):
                        prompt += f"Source Rationale: \"{rationale}\"\n"

                    raw_rating = dr.get("source_risk_rating_raw", "")
                    if not _empty(raw_rating):
                        prompt += f"Legacy Rating: {raw_rating}\n"

                    evidence = dr.get("key_risk_evidence", "")
                    if not _empty(evidence):
                        prompt += f"Keyword Evidence: {evidence}\n"

            # Sub-risks for this entity + source pillar
            if key_risks_df is not None and not _empty(legacy_source):
                base_pillar = str(legacy_source).split(" (also")[0].strip()
                eid_col = next((c for c in ("entity_id", "Audit Entity ID")
                                if c in key_risks_df.columns), None)
                l1_col = next((c for c in ("legacy_l1", "Level 1 Risk Category")
                               if c in key_risks_df.columns), None)
                if eid_col and l1_col:
                    matched_subs = key_risks_df[
                        (key_risks_df[eid_col].astype(str).str.strip() == eid) &
                        (key_risks_df[l1_col].astype(str).str.strip() == base_pillar)
                    ]
                    if not matched_subs.empty:
                        prompt += "\nKey Risk Descriptions:\n"
                        desc_col = next((c for c in ("risk_description", "Key Risk Description")
                                         if c in matched_subs.columns), None)
                        id_col = next((c for c in ("risk_id", "Key Risk ID")
                                       if c in matched_subs.columns), None)
                        for _, sr in matched_subs.iterrows():
                            rid = sr.get(id_col, "") if id_col else ""
                            desc = str(sr.get(desc_col, ""))[:300] if desc_col else ""
                            if desc and desc != "nan":
                                prompt += f"  • {rid}: {desc}\n"

            # Findings for this entity + L2
            if findings_df is not None:
                eid_col = next((c for c in ("entity_id", "Audit Entity ID")
                                if c in findings_df.columns), None)
                l2_col = next((c for c in ("l2_risk", "Mapped To L2(s)", "Risk Dimension Categories")
                               if c in findings_df.columns), None)
                if eid_col and l2_col:
                    matched_findings = findings_df[
                        (findings_df[eid_col].astype(str).str.strip() == eid) &
                        (findings_df[l2_col].astype(str).str.contains(l2, na=False))
                    ]
                    if not matched_findings.empty:
                        prompt += "\nFindings tagged to this L2:\n"
                        for _, f in matched_findings.iterrows():
                            fid = f.get("issue_id", f.get("Finding ID", ""))
                            title = f.get("issue_title", f.get("Finding Name", ""))
                            sev = f.get("severity", f.get("Final Reportable Finding Risk Rating", ""))
                            fstatus = f.get("status", f.get("Finding Status", ""))
                            prompt += f"  • {fid}: {title} ({sev}, {fstatus})\n"
                    else:
                        prompt += "\nFindings tagged to this L2: None\n"

            # Additional Signals
            signals = row.get("Additional Signals", "")
            if not _empty(signals):
                prompt += f"\nAdditional Signals: {signals}\n"

            prompt += "\n"

        all_prompts.append((eid, prompt, item_count))

    batches = []
    current_batch = []
    current_items = 0
    for eid, prompt_text, item_count in all_prompts:
        if current_batch and current_items + item_count > max_items_per_batch:
            batches.append(current_batch)
            current_batch = []
            current_items = 0
        current_batch.append((eid, prompt_text, item_count))
        current_items += item_count
    if current_batch:
        batches.append(current_batch)

    # Write per-batch folders. Each batch_NNN/ contains:
    #   - manifest.json   : entities + items in this batch
    #   - prompt.md       : the prompt to paste into ChatGPT
    #   - response.json   : empty-array template for user to paste LLM output
    # Plus an overall manifest.json at the prompts root mapping AE -> batch.
    import json as _json
    overall_ae_to_batch: dict[str, str] = {}
    overall_batches: list[dict] = []
    file_count = 0
    for batch in batches:
        file_count += 1
        batch_name = f"batch_{file_count:03d}"
        batch_dir = output_dir / batch_name
        batch_dir.mkdir(parents=True, exist_ok=True)

        # Manifest — what's in this batch + when it was generated.
        # `expected_items` lists every (entity_id, source_legacy_pillar,
        # classified_l2) triple the LLM is asked to determine, so the
        # consolidator can validate exact coverage (not just entity-level).
        entity_ids = [eid for eid, _, _ in batch]
        items_per_entity = {}
        expected_items = []
        total_items = 0
        for eid in entity_ids:
            eid_rows = review_df[review_df["Entity ID"] == eid]
            n = int(len(eid_rows))
            items_per_entity[eid] = n
            total_items += n
            for _, item_row in eid_rows.iterrows():
                legacy_source = str(item_row.get("Legacy Source", "")).strip()
                # Strip "(also: ...)" annotations so the triple matches what
                # the prompt asks the LLM to use as source_legacy_pillar.
                base_pillar = legacy_source.split(" (also")[0].strip() if legacy_source else ""
                l2 = str(item_row.get("New L2", "")).strip()
                if base_pillar and l2 and l2.lower() not in ("nan", "none"):
                    expected_items.append({
                        "entity_id": eid,
                        "source_legacy_pillar": base_pillar,
                        "classified_l2": l2,
                    })
        manifest = {
            "batch_number": file_count,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source_workbook": str(Path(excel_path).name),
            "entity_count": len(entity_ids),
            "item_count": total_items,
            "entities": entity_ids,
            "items_per_entity": items_per_entity,
            "expected_items": expected_items,
            "expected_response_format": "JSON array of objects",
            "expected_response_fields": [
                "entity_id", "source_legacy_pillar", "classified_l2",
                "determination", "reasoning",
            ],
            "valid_determination_values": ["applicable", "not_applicable"],
        }
        (batch_dir / "manifest.json").write_text(
            _json.dumps(manifest, indent=2), encoding="utf-8"
        )

        # Prompt — markdown for readability and clean paste into ChatGPT.
        # Content is the same text as before; markdown headers wrap it.
        with open(batch_dir / "prompt.md", "w", encoding="utf-8") as f:
            f.write(f"# LUminate LLM Review — {batch_name}\n\n")
            f.write("## System Prompt\n\n")
            f.write(SYSTEM_PROMPT)
            f.write("\n## Entity Data\n\n")
            f.write("Review each L2 risk below and provide your determination.\n\n")
            for _, prompt_text, _ in batch:
                f.write(prompt_text)
            f.write("\n## Output Format Reminder\n\n")
            f.write("Return a single JSON array. Each element is an object with these exact fields:\n\n")
            f.write("```\n")
            f.write('{"entity_id": "...", "source_legacy_pillar": "...", "classified_l2": "...", '
                    '"determination": "applicable" | "not_applicable", "reasoning": "<one sentence>"}\n')
            f.write("```\n\n")
            f.write("- Output ONLY the JSON array (no prose, no code fence around the whole array).\n")
            f.write("- determination is exactly `applicable` or `not_applicable`.\n")
            f.write("- reasoning is one sentence; no risk-rating language.\n\n")
            f.write(f"**Entities in this batch:** {', '.join(entity_ids)}\n")

        # Response template — empty JSON array; user pastes ChatGPT JSON output
        # replacing the [] entirely.
        (batch_dir / "response.json").write_text("[]\n", encoding="utf-8")

        for eid in entity_ids:
            overall_ae_to_batch[eid] = batch_name
        overall_batches.append({
            "batch": batch_name,
            "entities": entity_ids,
            "items": total_items,
        })

        print(f"  {batch_name}/: {len(batch)} entities, {total_items} items")

    # Top-level manifest — answers "which batch contains AE-X?" and
    # "what's in batch_NNN?" without opening per-batch files.
    overall_manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_workbook": str(Path(excel_path).name),
        "batch_count": file_count,
        "total_entities": len(entities),
        "total_items": int(len(review_df)),
        "max_items_per_batch": int(max_items_per_batch),
        "ae_to_batch": dict(sorted(overall_ae_to_batch.items())),
        "batches": overall_batches,
    }
    (output_dir / "manifest.json").write_text(
        _json.dumps(overall_manifest, indent=2), encoding="utf-8"
    )

    # Summary
    print(f"\nGenerated {file_count} batch folders in {output_dir}/")
    print(f"  Top-level manifest: {output_dir}/manifest.json (AE -> batch lookup)")
    print(f"  Total entities: {len(entities)}")
    print(f"  Total items for review: {len(review_df)}")
    print(f"  Items per batch: up to {max_items_per_batch} review items (AEs never split)")
    print(f"\nWorkflow:")
    print(f"  1. For each batch_NNN/ folder:")
    print(f"     - Open prompt.md and paste into ChatGPT")
    print(f"     - Paste ChatGPT's JSON array into response.json (replacing [])")
    print(f"  2. Run: python consolidate_llm_responses.py")
    print(f"     Validates each response.json, merges into data/input/llm_overrides_<ts>.csv")
    print(f"  3. Re-run main pipeline: python -m risk_taxonomy_transformer")
    print(f"     The merged overrides file will be picked up automatically.")


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    output_dir_path = _PROJECT_ROOT / "data" / "output"

    if len(sys.argv) > 1:
        excel_path = sys.argv[1]
    else:
        files = sorted(output_dir_path.glob("transformed_risk_taxonomy_*.xlsx"),
                       key=lambda f: f.stat().st_mtime)
        if not files:
            print("No transformer output found in data/output/")
            sys.exit(1)
        excel_path = str(files[-1])

    prompt_dir = str(_PROJECT_ROOT / "data" / "output" / "llm_prompts")
    generate_prompts(excel_path, prompt_dir)
