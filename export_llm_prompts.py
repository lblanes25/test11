"""
LLM Prompt Export for Applicability Review
===========================================
Reads the transformer output and generates structured prompt files for
items needing LLM review (Applicability Undetermined and Assumed N/A — Verify).

Each prompt contains full context: entity overview, L2 definition, source
rationale, key risks, findings, applications, and signals.

The LLM responds with CSV rows that can be saved as llm_overrides.csv
and fed back into the transformer.

Usage:
    python export_llm_prompts.py                    # uses latest output
    python export_llm_prompts.py path/to/output.xlsx  # specific file
"""

import logging
import pandas as pd
import yaml
import sys
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

For each determination, provide a one-sentence reasoning citing the specific evidence that supports your classification. Reference which evidence drove your decision: entity overview, rationale text, key risk descriptions, findings, or signals.

Output your responses as CSV rows with these exact columns, no header row:
entity_id,source_legacy_pillar,classified_l2,determination,reasoning

Valid determination values: applicable, not_applicable

Example output:
AE-3,Operational,Conduct,applicable,The rationale references consumer complaint handling and the key risk descriptions cite conduct risk monitoring processes.
AE-3,Operational,Business Disruption,not_applicable,No evidence of business continuity or disaster recovery concerns in the entity overview or key risk descriptions.
"""


_FRAUD_L3_SUBTYPES = {
    "External Fraud - First Party",
    "External Fraud - Victim Fraud",
    "Internal Fraud",
}


def load_l2_definitions() -> dict:
    """Load L2 definitions from taxonomy config.

    The real enterprise taxonomy file has L1/L2/L3 columns with merged cells
    that pandas reads as NaN on continuation rows; forward-fill restores them.

    Returned dict is keyed by the name as it appears in Audit_Review.New L2:
    canonical L2 for normal rows, and the L3 sub-type name for the three Fraud
    sub-types (definition pulled from L3 Definition).
    """
    config_path = _PROJECT_ROOT / "config" / "taxonomy_config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    l2_defs = {}
    l2_file = _PROJECT_ROOT / "data" / "input" / "L2_Risk_Taxonomy.xlsx"
    if l2_file.exists():
        df = pd.read_excel(l2_file)
        ffill_cols = [c for c in ("L1", "L2", "L3") if c in df.columns]
        if ffill_cols:
            df[ffill_cols] = df[ffill_cols].ffill()

        for _, row in df.iterrows():
            l2_name = row.get("L2", "")
            if pd.isna(l2_name) or not str(l2_name).strip():
                continue
            l2_name = str(l2_name).strip()

            l3_name = str(row.get("L3", "")).strip() if "L3" in df.columns else ""
            l3_def = str(row.get("L3 Definition", "")).strip() if "L3 Definition" in df.columns else ""
            l2_def = str(row.get("L2 Definition", "")).strip()

            if l3_name and l3_name in _FRAUD_L3_SUBTYPES:
                l2_defs[l3_name] = {
                    "l1": row.get("L1", ""),
                    "definition": l3_def or l2_def,
                }
            elif l2_name not in l2_defs:
                l2_defs[l2_name] = {
                    "l1": row.get("L1", ""),
                    "definition": l2_def,
                }

    # Fallback: build from taxonomy config
    if not l2_defs:
        for l1, l2_list in cfg.get("new_taxonomy", {}).items():
            for l2 in l2_list:
                l2_defs[l2] = {"l1": l1, "definition": ""}

    return l2_defs


def generate_prompts(excel_path: str, output_dir: str, max_per_file: int = 5):
    """Generate LLM prompt files from transformer output.

    Args:
        excel_path: Path to the transformer output Excel
        output_dir: Directory to write prompt files
        max_per_file: Max entities per prompt file (for manageable paste sizes)
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

    # Load L2 definitions
    l2_defs = load_l2_definitions()

    # Filter to items needing review
    review_statuses = ["Applicability Undetermined", "Assumed N/A — Verify"]
    review_df = audit_df[audit_df["Status"].isin(review_statuses)]

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

            prompt += f"---\n"
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

        all_prompts.append((eid, prompt))

    # Write prompt files (batched)
    file_count = 0
    for batch_start in range(0, len(all_prompts), max_per_file):
        batch = all_prompts[batch_start:batch_start + max_per_file]
        file_count += 1
        filename = f"llm_prompt_batch_{file_count:03d}.txt"
        filepath = output_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            # System prompt at top of each file
            f.write("SYSTEM PROMPT:\n")
            f.write(SYSTEM_PROMPT)
            f.write("\n" + "=" * 60 + "\n")
            f.write("ENTITY DATA — Review each L2 risk below and provide your determination.\n")
            f.write("=" * 60 + "\n")

            entity_ids = []
            total_items = 0
            for eid, prompt_text in batch:
                f.write(prompt_text)
                entity_ids.append(eid)
                total_items += len(review_df[review_df["Entity ID"] == eid])

            # Reminder at end
            f.write("\n" + "=" * 60 + "\n")
            f.write("OUTPUT FORMAT REMINDER:\n")
            f.write("Respond with CSV rows only, no header, no explanation:\n")
            f.write("entity_id,source_legacy_pillar,classified_l2,determination,reasoning\n\n")
            f.write("Valid determination values: applicable, not_applicable\n")
            f.write("Reasoning: one sentence citing the specific evidence that drove the determination.\n")
            f.write(f"\nEntities in this batch: {', '.join(entity_ids)}\n")

        print(f"  {filename}: {len(batch)} entities, {total_items} items")

    # Summary
    print(f"\nGenerated {file_count} prompt files in {output_dir}/")
    print(f"  Total entities: {len(entities)}")
    print(f"  Total items for review: {len(review_df)}")
    print(f"  Items per file: up to {max_per_file} entities")
    print(f"\nWorkflow:")
    print(f"  1. Open each prompt file and paste into ChatGPT")
    print(f"  2. Copy the CSV output")
    print(f"  3. Save all CSV rows to: data/input/llm_overrides.csv")
    print(f"     Header row: entity_id,source_legacy_pillar,classified_l2,determination,reasoning")
    print(f"  4. Re-run: python risk_taxonomy_transformer.py")
    print(f"     Set override_path in main() to point to llm_overrides.csv")


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
