"""One-shot diagnostic: per-Gap-ID AE attribution under PRSA route vs PG-team/FND route.

Throwaway. Reuses the pipeline's own ingestion functions so its (AE, L2)
attributions equal a real refresh run; it never re-implements bridge logic.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root for package import

from risk_taxonomy_transformer.config import get_config
from risk_taxonomy_transformer.ingestion import (
    build_pg_gap_index,
    build_pg_gap_index_from_pg_team,
    ingest_findings,
    ingest_pg_team_inputs,
    ingest_prsa,
)

VERDICT_ORDER = ["disagree", "pg-only", "prsa-only", "match", "both-empty"]


def _latest(paths) -> Path | None:
    paths = list(paths)
    if not paths:
        return None
    return sorted(paths, key=lambda f: f.stat().st_mtime)[-1]


def _is_blank(v) -> bool:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return True
    s = str(v).strip()
    return s == "" or s.lower() in {"nan", "none"}


def _invert_pg_index(pg_index: dict) -> dict:
    """Invert {entity_id: {l2: [items]}} to {issue_id: [(entity_id, l2), ...]}."""
    out: dict[str, list[tuple[str, str]]] = {}
    for eid, by_l2 in (pg_index or {}).items():
        for l2, items in by_l2.items():
            for item in items:
                iid = str(item.get("issue_id", "")).strip()
                if not iid:
                    continue
                out.setdefault(iid, []).append((eid, l2))
    return out


def _classify(prsa_set: set, pg_set: set) -> str:
    if not prsa_set and not pg_set:
        return "both-empty"
    if prsa_set and not pg_set:
        return "prsa-only"
    if pg_set and not prsa_set:
        return "pg-only"
    return "match" if prsa_set == pg_set else "disagree"


def _fmt_set(items) -> str:
    if not items:
        return "_(none)_"
    return ", ".join(f"`{s}`" for s in sorted(items))


def _md_header(pg_team_path: Path, prsa_path: Path | None, findings_path: Path | None,
               pg_team_cols: dict, prsa_cols: dict, findings_cols: dict) -> list:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# PG Mapping Comparison -- PRSA route vs PG-team/FND route",
        "",
        f"Generated: {ts}  ",
        f"PG team inputs: `{pg_team_path.name}`  ",
        f"PRSA report:    `{prsa_path.name if prsa_path else '(not found)'}`  ",
        f"Findings:       `{findings_path.name if findings_path else '(not found)'}`",
        "",
        "**YAML resolution snapshot**",
        "",
        f"- `columns.pg_team_inputs.gap_id` = `{pg_team_cols.get('gap_id', 'Gap ID')!r}`",
        f"- `columns.pg_team_inputs.impact_rating` = `{pg_team_cols.get('impact_rating', 'Impact Rating')!r}`",
        f"- `columns.pg_team_inputs.issue_id` = `{pg_team_cols.get('issue_id', 'Issue ID (Archer IRM)')!r}`",
        f"- `columns.pg_team_inputs.finding_id` = `{pg_team_cols.get('finding_id', 'Archer eGRC FND ID')!r}`",
        f"- `columns.pg_team_inputs.file_pattern` = `{pg_team_cols.get('file_pattern', 'project_guardian_aera_inputs_*.xlsx')!r}`",
        f"- `columns.prsa.issue_id` = `{prsa_cols.get('issue_id', 'Issue ID')!r}`",
        f"- `columns.findings.issue_id` = `{findings_cols.get('issue_id', 'Finding ID')!r}`",
        "",
    ]
    return lines


def _md_exec_summary(rows: list, totals: dict) -> list:
    total = len(rows)
    counts = {v: sum(1 for r in rows if r["verdict"] == v) for v in VERDICT_ORDER}
    prsa_attributed = sum(1 for r in rows if r["prsa_aes"])
    pg_attributed = sum(1 for r in rows if r["pg_aes"])

    def _pct(n: int) -> str:
        return f"{(n / total * 100.0):.1f}%" if total else "0.0%"

    lines = ["## Executive summary", ""]
    lines.append(f"Total Gap IDs analyzed: **{total}**")
    lines.append("")
    lines.append("| Verdict | Count | % of total |")
    lines.append("|---|---:|---:|")
    for v in VERDICT_ORDER:
        lines.append(f"| {v} | {counts[v]} | {_pct(counts[v])} |")
    lines.append(f"| **all** | **{total}** | **100.0%** |")
    lines.append("")
    lines.append(f"Attributed by PRSA route: **{prsa_attributed}** ({_pct(prsa_attributed)}); "
                 f"attributed by PG-team/FND route: **{pg_attributed}** ({_pct(pg_attributed)}).")
    lines.append("")
    consistency = counts["match"] + counts["pg-only"] + counts["prsa-only"] + counts["disagree"] + counts["both-empty"]
    lines.append(f"Internal consistency check: {counts['match']} + {counts['pg-only']} + "
                 f"{counts['prsa-only']} + {counts['disagree']} + {counts['both-empty']} "
                 f"= **{consistency}** (must equal total {total}: "
                 f"{'OK' if consistency == total else 'MISMATCH'}).")
    lines.append("")
    lines.append(f"Data-quality totals: rows missing Finding ID = {totals['missing_fid']}, "
                 f"rows missing Issue ID = {totals['missing_iid']}, "
                 f"rows missing both = {totals['missing_both']}, "
                 f"FND_IDs not in findings_df = {totals['fid_unmatched']}, "
                 f"Issue IDs not in prsa_df = {totals['iid_unmatched']}.")
    lines.append("")
    return lines


def _row_md(r: dict) -> str:
    return (
        f"| `{r['gap_id']}` | `{r['issue_id'] or '-'}` | `{r['finding_id'] or '-'}` | "
        f"{r['impact_rating'] or '-'} | "
        f"{_fmt_set(r['prsa_aes'])} | {_fmt_set(r['prsa_l2s'])} | "
        f"{_fmt_set(r['pg_aes'])} | {_fmt_set(r['pg_l2s'])} | "
        f"**{r['verdict']}** |"
    )


def _md_discrepancy_table(rows: list) -> list:
    order = {v: i for i, v in enumerate(VERDICT_ORDER)}
    sorted_rows = sorted(rows, key=lambda r: (order.get(r["verdict"], 99), r["gap_id"]))
    lines = [
        "## Discrepancy table (all Gap IDs)",
        "",
        "Sorted: `disagree` -> `pg-only` -> `prsa-only` -> `match` -> `both-empty`.",
        "",
        "| Gap ID | Issue ID (Archer IRM) | Finding ID | Impact Rating | "
        "AE(s) via PRSA route | L2(s) via PRSA route | "
        "AE(s) via PG-team/FND route | L2(s) via PG-team/FND route | Verdict |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted_rows:
        lines.append(_row_md(r))
    lines.append("")
    return lines


def _md_section(title: str, body: str, rows: list) -> list:
    lines = [f"## {title}", "", body, ""]
    if not rows:
        lines.append("_(no rows)_")
        lines.append("")
        return lines
    lines.append(
        "| Gap ID | Issue ID (Archer IRM) | Finding ID | Impact Rating | "
        "AE(s) via PRSA route | L2(s) via PRSA route | "
        "AE(s) via PG-team/FND route | L2(s) via PG-team/FND route | Verdict |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda x: x["gap_id"]):
        lines.append(_row_md(r))
    lines.append("")
    return lines


def _md_data_quality_footer(totals: dict, unmatched_fids: list, unmatched_iids: list) -> list:
    lines = ["## Data-quality footer", ""]
    lines.append(f"- Rows missing Finding ID: **{totals['missing_fid']}**")
    lines.append(f"- Rows missing Issue ID: **{totals['missing_iid']}**")
    lines.append(f"- Rows missing both Finding ID and Issue ID: **{totals['missing_both']}**")
    lines.append(f"- FND_IDs in PG team file not found in findings_df: **{totals['fid_unmatched']}**")
    lines.append(f"- Issue IDs in PG team file not found in prsa_df: **{totals['iid_unmatched']}**")
    lines.append("")
    if unmatched_fids:
        lines.append("Unmatched FND_IDs (up to 50 shown):")
        lines.append("")
        for fid in unmatched_fids[:50]:
            lines.append(f"- `{fid}`")
        if len(unmatched_fids) > 50:
            lines.append(f"- ... (+{len(unmatched_fids) - 50} more)")
        lines.append("")
    if unmatched_iids:
        lines.append("Unmatched Issue IDs (up to 50 shown):")
        lines.append("")
        for iid in unmatched_iids[:50]:
            lines.append(f"- `{iid}`")
        if len(unmatched_iids) > 50:
            lines.append(f"- ... (+{len(unmatched_iids) - 50} more)")
        lines.append("")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Compare per-Gap-ID AE attribution under the PRSA control route and "
            "the new PG-team/FND route (read-only). Emits a Markdown report."
        ),
    )
    ap.add_argument("--pg-team", default=None, help="Path to project_guardian_aera_inputs_*.xlsx")
    ap.add_argument("--prsa", default=None, help="Path to prsa_report_*.xlsx")
    ap.add_argument("--findings", default=None, help="Path to findings_data_*.xlsx")
    ap.add_argument("--input-dir", default="data/input")
    ap.add_argument("--output-dir", default="data/output")
    args = ap.parse_args()

    cfg = get_config()
    col_cfg = cfg.get("columns", {})
    pg_team_cols = col_cfg.get("pg_team_inputs", {})
    prsa_cols = col_cfg.get("prsa", {})
    findings_cols = col_cfg.get("findings", {})

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    file_pattern = pg_team_cols.get("file_pattern", "project_guardian_aera_inputs_*.xlsx")
    pg_team_path = Path(args.pg_team) if args.pg_team else _latest(input_dir.glob(file_pattern))
    if pg_team_path is None or not pg_team_path.exists():
        print(
            f"no PG team file found in {input_dir.resolve()} (pattern {file_pattern!r}) "
            "-- nothing to compare",
            file=sys.stderr,
        )
        return 0

    prsa_path = Path(args.prsa) if args.prsa else _latest(
        [f for f in input_dir.glob("prsa_report_*.xlsx") if "_orphans" not in f.stem]
        + [f for f in input_dir.glob("prsa_report_*.csv") if "_orphans" not in f.stem]
    )
    findings_path = Path(args.findings) if args.findings else _latest(
        list(input_dir.glob("findings_data_*.xlsx"))
        + list(input_dir.glob("findings_data_*.csv"))
    )

    print(f"PG team inputs: {pg_team_path.resolve()}")
    print(f"PRSA report   : {prsa_path.resolve() if prsa_path else '(not found)'}")
    print(f"Findings      : {findings_path.resolve() if findings_path else '(not found)'}")

    pg_team_df = ingest_pg_team_inputs(str(pg_team_path), pg_team_cols)

    prsa_df = ingest_prsa(str(prsa_path), prsa_cols) if (prsa_path and prsa_path.exists()) else pd.DataFrame()
    if findings_path and findings_path.exists():
        findings_df, _unmapped, _orphans, _src = ingest_findings(str(findings_path), findings_cols)
    else:
        findings_df = pd.DataFrame()

    prsa_route_index = build_pg_gap_index(prsa_df, prsa_cols) if not prsa_df.empty else {}
    if not findings_df.empty and not prsa_df.empty:
        pg_team_route_index, _diag = build_pg_gap_index_from_pg_team(
            pg_team_df, findings_df, prsa_df, pg_team_cols, prsa_cols,
        )
    else:
        pg_team_route_index = {}

    prsa_by_iid = _invert_pg_index(prsa_route_index)
    pg_by_iid = _invert_pg_index(pg_team_route_index)

    prsa_issue_id_col = prsa_cols.get("issue_id", "Issue ID")
    prsa_issue_ids: set[str] = set()
    if not prsa_df.empty and prsa_issue_id_col in prsa_df.columns:
        prsa_issue_ids = {
            str(v).strip() for v in prsa_df[prsa_issue_id_col].tolist()
            if not _is_blank(v)
        }
    findings_finding_ids: set[str] = set()
    if not findings_df.empty and "issue_id" in findings_df.columns:
        findings_finding_ids = {
            str(v).strip() for v in findings_df["issue_id"].tolist()
            if not _is_blank(v)
        }

    gap_id_col = pg_team_cols.get("gap_id", "Gap ID")
    impact_col = pg_team_cols.get("impact_rating", "Impact Rating")
    pg_iid_col = pg_team_cols.get("issue_id", "Issue ID (Archer IRM)")
    pg_fid_col = pg_team_cols.get("finding_id", "Archer eGRC FND ID")

    rows: list[dict] = []
    totals = {
        "missing_fid": 0,
        "missing_iid": 0,
        "missing_both": 0,
        "fid_unmatched": 0,
        "iid_unmatched": 0,
    }
    unmatched_fids: list[str] = []
    unmatched_iids: list[str] = []

    for _, raw in pg_team_df.iterrows():
        gap_id = str(raw.get(gap_id_col, "")).strip()
        issue_id = str(raw.get(pg_iid_col, "")).strip()
        finding_id = str(raw.get(pg_fid_col, "")).strip()
        impact_rating = str(raw.get(impact_col, "")).strip()
        if impact_rating.lower() in ("nan", "none"):
            impact_rating = ""

        if not finding_id:
            totals["missing_fid"] += 1
        if not issue_id:
            totals["missing_iid"] += 1
        if not finding_id and not issue_id:
            totals["missing_both"] += 1
        if finding_id and finding_id not in findings_finding_ids:
            totals["fid_unmatched"] += 1
            unmatched_fids.append(finding_id)
        if issue_id and issue_id not in prsa_issue_ids:
            totals["iid_unmatched"] += 1
            unmatched_iids.append(issue_id)

        prsa_pairs = prsa_by_iid.get(issue_id, []) if issue_id else []
        pg_pairs = pg_by_iid.get(issue_id, []) if issue_id else []
        prsa_aes = {p[0] for p in prsa_pairs}
        prsa_l2s = {p[1] for p in prsa_pairs}
        pg_aes = {p[0] for p in pg_pairs}
        pg_l2s = {p[1] for p in pg_pairs}

        ae_verdict = _classify(prsa_aes, pg_aes)
        l2_verdict = _classify(prsa_l2s, pg_l2s)
        if ae_verdict == "match" and l2_verdict == "match":
            verdict = "match"
        elif ae_verdict == "both-empty" and l2_verdict == "both-empty":
            verdict = "both-empty"
        elif not prsa_aes and not prsa_l2s and (pg_aes or pg_l2s):
            verdict = "pg-only"
        elif not pg_aes and not pg_l2s and (prsa_aes or prsa_l2s):
            verdict = "prsa-only"
        else:
            verdict = "disagree"

        rows.append({
            "gap_id": gap_id,
            "issue_id": issue_id,
            "finding_id": finding_id,
            "impact_rating": impact_rating,
            "prsa_aes": prsa_aes,
            "prsa_l2s": prsa_l2s,
            "pg_aes": pg_aes,
            "pg_l2s": pg_l2s,
            "verdict": verdict,
        })

    pg_only = [r for r in rows if r["verdict"] == "pg-only"]
    prsa_only = [r for r in rows if r["verdict"] == "prsa-only"]
    disagree = [r for r in rows if r["verdict"] == "disagree"]

    out_lines: list[str] = []
    out_lines += _md_header(pg_team_path, prsa_path, findings_path,
                            pg_team_cols, prsa_cols, findings_cols)
    out_lines += _md_exec_summary(rows, totals)
    out_lines += _md_discrepancy_table(rows)
    out_lines += _md_section(
        "PG-team-only (PRSA route misses these)",
        "Gap IDs the PG-team/FND route resolves that the PRSA control route misses. "
        "This is the value-add narrative for the new bridge.",
        pg_only,
    )
    out_lines += _md_section(
        "PRSA-only (PG-team/FND route misses these)",
        "Gap IDs the PRSA control route resolves that the PG-team/FND route does not. "
        "Likely cause: blank Finding ID in the PG team file or FND_ID absent from findings_df.",
        prsa_only,
    )
    out_lines += _md_section(
        "Disagreement deep-dive",
        "Gap IDs where both routes resolve but to different AE-sets or L2-sets. "
        "Flag for human review -- the union behaviour means the gap will render under "
        "every AE either route names, which may or may not be desired.",
        disagree,
    )
    out_lines += _md_data_quality_footer(totals, unmatched_fids, unmatched_iids)

    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    out_path = output_dir / f"pg_mapping_comparison_{ts}.md"
    out_path.write_text("\n".join(out_lines), encoding="utf-8")

    print(f"Report  : {out_path.resolve()}")
    print(f"Gap IDs : {len(rows)} (match={sum(1 for r in rows if r['verdict']=='match')}, "
          f"pg-only={len(pg_only)}, prsa-only={len(prsa_only)}, "
          f"disagree={len(disagree)}, "
          f"both-empty={sum(1 for r in rows if r['verdict']=='both-empty')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
