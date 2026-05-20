"""One-shot diagnostic: empirical impact of RCO keyword-map edits.

Throwaway. Diffs two transformed_risk_taxonomy_*.xlsx outputs (one pre-edit,
one RCO-vetted) and writes a single Markdown verdict report per L2.
"""

import argparse
import statistics
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root for package import

GREEN_REQUIRES_NET_GE = 0
YELLOW_MAX_NET_PCT_LOSS = 10
YELLOW_MAX_ORPHAN_DROP_KEYWORDS = 2
YELLOW_MAX_ORPHAN_DROP_AES = 5
RED_SINGLE_KEYWORD_ORPHAN_THRESHOLD = 3
JACCARD_SUBSTANTIAL_CHANGE = 0.25
TOP_N_KEYWORDS = 10
RATIONALE_SNIPPET_MAX = 200

ENTITY_COL = "Entity ID"
L2_COL = "L2"
KW_HITS_COL = "Keyword Hits"
STATUS_COL = "Suggested Status"
RATIONALE_COL = "Source Rationale Excerpt"
METHOD_COL = "Method"
CONFIDENCE_COL = "Confidence"
SHEET = "Risk_Owner_Review"
REQUIRED_COLS = [ENTITY_COL, L2_COL, KW_HITS_COL, STATUS_COL, RATIONALE_COL]


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


def _parse_kw_cell(val) -> set:
    if _is_blank(val):
        return set()
    parts = [p.strip() for p in str(val).split(", ")]
    return {p for p in parts if p}


def _truncate(s: str, n: int = RATIONALE_SNIPPET_MAX) -> str:
    s = "" if _is_blank(s) else str(s).strip().replace("\n", " ").replace("\r", " ")
    return s if len(s) <= n else s[: n - 1].rstrip() + "..."


def _load_sheet(path: Path) -> pd.DataFrame:
    try:
        df = pd.read_excel(path, sheet_name=SHEET)
    except ValueError as e:
        print(f"ERROR: sheet {SHEET!r} not found in {path}: {e}", file=sys.stderr)
        raise SystemExit(2)
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        print(f"ERROR: {path} missing required columns: {missing}", file=sys.stderr)
        raise SystemExit(2)
    return df


def _aggregate(df: pd.DataFrame) -> dict:
    """Build {l2: {"applicable_aes": set, "kw_hit_aes": set, "kws_by_ae": {ae: set}, "rationale_by_ae": {ae: str}}}."""
    by_l2: dict = {}
    for _, row in df.iterrows():
        l2 = str(row.get(L2_COL, "")).strip()
        if not l2 or l2.lower() == "nan":
            continue
        ae = str(row.get(ENTITY_COL, "")).strip()
        if not ae or ae.lower() == "nan":
            continue
        status = str(row.get(STATUS_COL, "")).strip()
        kws = _parse_kw_cell(row.get(KW_HITS_COL))
        rationale = row.get(RATIONALE_COL, "")
        bucket = by_l2.setdefault(l2, {
            "applicable_aes": set(),
            "kw_hit_aes": set(),
            "kws_by_ae": {},
            "rationale_by_ae": {},
        })
        if status == "Applicable":
            bucket["applicable_aes"].add(ae)
        if kws:
            bucket["kw_hit_aes"].add(ae)
            bucket["kws_by_ae"].setdefault(ae, set()).update(kws)
        if ae not in bucket["rationale_by_ae"] and not _is_blank(rationale):
            bucket["rationale_by_ae"][ae] = _truncate(rationale)
    return by_l2


def _kw_ae_index(kws_by_ae: dict) -> dict:
    """Invert {ae: set(kw)} to {kw: set(ae)}."""
    out: dict = {}
    for ae, kws in kws_by_ae.items():
        for kw in kws:
            out.setdefault(kw, set()).add(ae)
    return out


def _jaccard(a: set, b: set) -> float:
    u = a | b
    return 1.0 if not u else len(a & b) / len(u)


def _verdict(net_delta: int, net_delta_pct: float, removed_analysis: list) -> tuple[str, str]:
    max_single_orphan = max((r["orphan_count"] for r in removed_analysis), default=0)
    orphan_kw_count = sum(1 for r in removed_analysis if r["orphan_count"] > 0)
    total_orphan_aes = sum(r["orphan_count"] for r in removed_analysis)

    if max_single_orphan >= RED_SINGLE_KEYWORD_ORPHAN_THRESHOLD:
        return "Red", f"single removed keyword orphans {max_single_orphan} AEs (>= {RED_SINGLE_KEYWORD_ORPHAN_THRESHOLD})"
    if net_delta_pct <= -YELLOW_MAX_NET_PCT_LOSS:
        return "Red", f"net AE change {net_delta_pct:.1f}% (<= -{YELLOW_MAX_NET_PCT_LOSS}%)"
    if net_delta >= GREEN_REQUIRES_NET_GE and orphan_kw_count == 0:
        return "Green", "no orphan drops and net AE change non-negative"
    if orphan_kw_count <= YELLOW_MAX_ORPHAN_DROP_KEYWORDS and total_orphan_aes <= YELLOW_MAX_ORPHAN_DROP_AES:
        return "Yellow", f"{orphan_kw_count} kw(s) orphan-drop, {total_orphan_aes} AE(s) affected"
    return "Yellow", f"{orphan_kw_count} kw(s) orphan-drop, {total_orphan_aes} AE(s) affected"


def _analyze_removed(removed: set, orig_by_ae: dict, vetted_by_ae: dict, rationale_o: dict) -> list:
    """For each removed keyword, count hits-lost, AEs-affected, synonyms-retained, orphan drops."""
    out = []
    for kw in removed:
        affected = [ae for ae, kws in orig_by_ae.items() if kw in kws]
        if not affected:
            continue
        synonyms_retained = set()
        orphans = []
        caught = 0
        for ae in affected:
            vetted_kws = vetted_by_ae.get(ae, set())
            if vetted_kws:
                caught += 1
                synonyms_retained.update(vetted_kws)
            else:
                orphans.append(ae)
        example_ae = affected[0]
        out.append({
            "keyword": kw,
            "hits_lost": len(affected),
            "aes": affected,
            "synonyms_retained": sorted(synonyms_retained),
            "caught_count": caught,
            "orphan_count": len(orphans),
            "orphan_aes": orphans,
            "example_ae": example_ae,
            "example_rationale": rationale_o.get(example_ae, ""),
        })
    out.sort(key=lambda r: (-r["hits_lost"], r["keyword"]))
    return out


def _analyze_added(added: set, orig_by_ae: dict, vetted_by_ae: dict, orig_kw_universe: set, rationale_v: dict) -> list:
    """For each added keyword, count hits-gained, AEs-affected, spot-check label."""
    out = []
    for kw in added:
        affected = [ae for ae, kws in vetted_by_ae.items() if kw in kws]
        if not affected:
            continue
        consistent = 0
        novel = 0
        for ae in affected:
            orig_kws_for_ae = orig_by_ae.get(ae, set())
            other_vetted_for_ae = vetted_by_ae.get(ae, set()) - {kw}
            if other_vetted_for_ae & orig_kw_universe or orig_kws_for_ae:
                consistent += 1
            else:
                novel += 1
        label = "consistent with prior signal" if consistent >= novel else "novel signal -- verify"
        example_ae = affected[0]
        out.append({
            "keyword": kw,
            "hits_gained": len(affected),
            "aes": affected,
            "spot_check": label,
            "consistent_count": consistent,
            "novel_count": novel,
            "example_ae": example_ae,
            "example_rationale": rationale_v.get(example_ae, ""),
        })
    out.sort(key=lambda r: (-r["hits_gained"], r["keyword"]))
    return out


def _stability(orig_by_ae: dict, vetted_by_ae: dict, both_aes: set) -> dict:
    jaccards = []
    substantial = 0
    for ae in both_aes:
        j = _jaccard(orig_by_ae.get(ae, set()), vetted_by_ae.get(ae, set()))
        jaccards.append(j)
        if j < JACCARD_SUBSTANTIAL_CHANGE:
            substantial += 1
    if not jaccards:
        return {"mean": None, "median": None, "min": None, "substantial": 0, "n": 0}
    return {
        "mean": statistics.mean(jaccards),
        "median": statistics.median(jaccards),
        "min": min(jaccards),
        "substantial": substantial,
        "n": len(jaccards),
    }


def _build_l2_record(l2: str, o_bucket: dict, v_bucket: dict) -> dict:
    o_app = o_bucket.get("applicable_aes", set())
    v_app = v_bucket.get("applicable_aes", set())
    o_by_ae = o_bucket.get("kws_by_ae", {})
    v_by_ae = v_bucket.get("kws_by_ae", {})

    o_kw_universe = set().union(*o_by_ae.values()) if o_by_ae else set()
    v_kw_universe = set().union(*v_by_ae.values()) if v_by_ae else set()

    removed = o_kw_universe - v_kw_universe
    added = v_kw_universe - o_kw_universe

    removed_analysis = _analyze_removed(removed, o_by_ae, v_by_ae, o_bucket.get("rationale_by_ae", {}))
    added_analysis = _analyze_added(added, o_by_ae, v_by_ae, o_kw_universe, v_bucket.get("rationale_by_ae", {}))

    both = o_app & v_app
    stab = _stability(o_by_ae, v_by_ae, both)

    net_delta = len(v_app) - len(o_app)
    net_pct = (net_delta / len(o_app) * 100.0) if o_app else (100.0 if v_app else 0.0)

    newly_plus = sorted(v_app - o_app)
    newly_minus = sorted(o_app - v_app)

    verdict, verdict_reason = _verdict(net_delta, net_pct, removed_analysis)

    return {
        "l2": l2,
        "orig_count": len(o_app),
        "vetted_count": len(v_app),
        "net_delta": net_delta,
        "net_pct": net_pct,
        "newly_plus": newly_plus,
        "newly_minus": newly_minus,
        "removed_analysis": removed_analysis,
        "added_analysis": added_analysis,
        "stability": stab,
        "verdict": verdict,
        "verdict_reason": verdict_reason,
    }


def _md_header(orig_path: Path, vetted_path: Path) -> list:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    return [
        "# RCO Keyword Edit -- Empirical Impact Report",
        "",
        f"Generated: {ts}  ",
        f"Original: `{orig_path.name}`  ",
        f"Vetted:   `{vetted_path.name}`",
        "",
        "**Verdict thresholds**",
        "",
        f"- **Green**: net AE change >= {GREEN_REQUIRES_NET_GE} AND zero orphan-drop keywords.",
        f"- **Yellow**: net AE change > -{YELLOW_MAX_NET_PCT_LOSS}% AND <= {YELLOW_MAX_ORPHAN_DROP_KEYWORDS} orphan-drop keywords AND <= {YELLOW_MAX_ORPHAN_DROP_AES} orphan-dropped AEs.",
        f"- **Red**: net AE change <= -{YELLOW_MAX_NET_PCT_LOSS}% OR any single removed keyword orphans >= {RED_SINGLE_KEYWORD_ORPHAN_THRESHOLD} AEs.",
        "",
    ]


def _md_exec_summary(records: list) -> list:
    lines = ["## Executive summary", "", "| L2 | Orig AEs | Vetted AEs | Delta | Delta % | Newly+ | Newly- | Verdict |", "|---|---:|---:|---:|---:|---:|---:|---|"]
    for r in sorted(records, key=lambda x: x["l2"].lower()):
        lines.append(
            f"| {r['l2']} | {r['orig_count']} | {r['vetted_count']} | "
            f"{r['net_delta']:+d} | {r['net_pct']:+.1f}% | "
            f"{len(r['newly_plus'])} | {len(r['newly_minus'])} | **{r['verdict']}** |"
        )
    lines.append("")
    return lines


def _md_per_l2(r: dict) -> list:
    lines = [f"### {r['l2']} -- {r['verdict']}", ""]
    lines.append(
        f"**Headline.** {r['orig_count']} AEs orig -> {r['vetted_count']} vetted "
        f"(delta {r['net_delta']:+d}, {r['net_pct']:+.1f}%). "
        f"{len(r['newly_plus'])} newly classified, {len(r['newly_minus'])} newly unclassified. "
        f"Verdict basis: {r['verdict_reason']}."
    )
    lines.append("")

    lines.append("**Loss analysis.** Top removed keywords by hits lost:")
    if not r["removed_analysis"]:
        lines.append("")
        lines.append("- _(none)_")
    else:
        lines.append("")
        for i, item in enumerate(r["removed_analysis"][:TOP_N_KEYWORDS], 1):
            syn = ", ".join(f"`{s}`" for s in item["synonyms_retained"]) or "_none_"
            example = item["example_rationale"] or "_(no rationale captured)_"
            lines.append(
                f"{i}. `{item['keyword']}` -- {item['hits_lost']} hit(s) lost across "
                f"{len(item['aes'])} AE(s). "
                f"Example (AE {item['example_ae']}): \"{example}\" "
                f"Synonyms retained ({item['caught_count']}/{item['hits_lost']} AEs): {syn}. "
                f"Orphan drops: {item['orphan_count']}."
            )
    lines.append("")

    lines.append("**Gain analysis.** Top added keywords by hits gained:")
    if not r["added_analysis"]:
        lines.append("")
        lines.append("- _(none)_")
    else:
        lines.append("")
        for i, item in enumerate(r["added_analysis"][:TOP_N_KEYWORDS], 1):
            example = item["example_rationale"] or "_(no rationale captured)_"
            lines.append(
                f"{i}. `{item['keyword']}` -- {item['hits_gained']} hit(s) gained across "
                f"{len(item['aes'])} AE(s). "
                f"Example (AE {item['example_ae']}): \"{example}\" "
                f"Spot-check: {item['spot_check']} "
                f"({item['consistent_count']} consistent / {item['novel_count']} novel)."
            )
    lines.append("")

    stab = r["stability"]
    if stab["n"] == 0:
        lines.append("**Stability check.** No AEs in both runs for this L2; skipped.")
    else:
        lines.append(
            f"**Stability check.** Of {stab['n']} AEs matched (Applicable) by both lists, "
            f"keyword-hit Jaccard mean={stab['mean']:.2f}, median={stab['median']:.2f}, "
            f"min={stab['min']:.2f}. {stab['substantial']} AE(s) had keyword sets that "
            f"changed substantially (Jaccard < {JACCARD_SUBSTANTIAL_CHANGE})."
        )
    lines.append("")
    return lines


def _md_reinstatement(records: list) -> list:
    reds = [r for r in records if r["verdict"] == "Red"]
    if not reds:
        return []
    lines = ["## Reinstatement requests", ""]
    for r in reds:
        orphan_items = [it for it in r["removed_analysis"] if it["orphan_count"] > 0]
        orphan_items.sort(key=lambda it: -it["orphan_count"])
        if not orphan_items:
            continue
        lines.append(f"### {r['l2']}")
        lines.append("")
        for item in orphan_items:
            ae_list = ", ".join(f"`{a}`" for a in item["orphan_aes"][:10])
            if len(item["orphan_aes"]) > 10:
                ae_list += f", ... (+{len(item['orphan_aes']) - 10} more)"
            example = item["example_rationale"] or "_(no rationale captured)_"
            lines.append(
                f"- `{item['keyword']}` -- would recover {item['orphan_count']} AE(s): {ae_list}. "
                f"Example rationale: \"{example}\" "
                f"Justification: no synonym in the vetted list matches this language; "
                f"removal causes a clean drop, not a re-route."
            )
        lines.append("")
    return lines


def _md_summary_paragraph(records: list) -> list:
    reds = [r for r in records if r["verdict"] == "Red"]
    yellows = [r for r in records if r["verdict"] == "Yellow"]
    greens = [r for r in records if r["verdict"] == "Green"]
    total_orig = sum(r["orig_count"] for r in records)
    total_vetted = sum(r["vetted_count"] for r in records)
    total_delta = total_vetted - total_orig

    if reds:
        worst = min(reds, key=lambda r: r["net_pct"])
        worst_kw = max(
            worst["removed_analysis"], key=lambda it: it["orphan_count"], default=None
        )
        sentence = (
            f"The RCO edits net {total_delta:+d} Applicable AE classifications across "
            f"{len(records)} L2s ({len(greens)} Green, {len(yellows)} Yellow, {len(reds)} Red). "
            f"The most-affected L2 is **{worst['l2']}** at {worst['net_pct']:+.1f}% "
            f"({worst['orig_count']} -> {worst['vetted_count']} AEs)."
        )
        if worst_kw and worst_kw["orphan_count"] > 0:
            sentence += (
                f" Within that L2, removing `{worst_kw['keyword']}` orphan-drops "
                f"{worst_kw['orphan_count']} AE(s) with no synonym catch -- reinstatement "
                f"is the smallest fix."
            )
        sentence += f" {len(reds)} L2(s) need RCO review before sign-off."
    elif yellows:
        sentence = (
            f"The RCO edits net {total_delta:+d} Applicable AE classifications across "
            f"{len(records)} L2s ({len(greens)} Green, {len(yellows)} Yellow, 0 Red). "
            f"No L2 crosses the Red threshold; {len(yellows)} have minor orphan drops "
            f"worth a quick look but no blocking changes."
        )
    else:
        sentence = (
            f"The RCO edits net {total_delta:+d} Applicable AE classifications across "
            f"{len(records)} L2s; all {len(greens)} are Green (no orphan drops, "
            f"non-negative net change). Sign-off is supported by the data."
        )
    return ["## One-paragraph SME summary", "", sentence, ""]


def _md_yaml_footer(yaml_orig: Path, yaml_vetted: Path, records: list) -> list:
    try:
        import yaml
    except ImportError:
        return []
    try:
        with open(yaml_orig, encoding="utf-8") as f:
            y_o = yaml.safe_load(f) or {}
        with open(yaml_vetted, encoding="utf-8") as f:
            y_v = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as e:
        return ["## Cosmetic-only edits", "", f"_YAML load failed: {e}_", ""]

    km_o = y_o.get("keyword_map", {}) or {}
    km_v = y_v.get("keyword_map", {}) or {}

    fired_removed_by_l2 = {r["l2"]: {it["keyword"] for it in r["removed_analysis"]} for r in records}
    fired_added_by_l2 = {r["l2"]: {it["keyword"] for it in r["added_analysis"]} for r in records}

    lines = ["## Cosmetic-only edits (in YAML but never fired)", ""]
    any_found = False
    all_l2s = sorted(set(km_o) | set(km_v))
    for l2 in all_l2s:
        y_removed = {k.lower() for k in (km_o.get(l2) or [])} - {k.lower() for k in (km_v.get(l2) or [])}
        y_added = {k.lower() for k in (km_v.get(l2) or [])} - {k.lower() for k in (km_o.get(l2) or [])}
        empirical_removed = {k.lower() for k in fired_removed_by_l2.get(l2, set())}
        empirical_added = {k.lower() for k in fired_added_by_l2.get(l2, set())}
        cosmetic_removed = y_removed - empirical_removed
        cosmetic_added = y_added - empirical_added
        if cosmetic_removed or cosmetic_added:
            any_found = True
            lines.append(f"### {l2}")
            if cosmetic_removed:
                lines.append(f"- Removed in YAML, never fired in original run: {', '.join(f'`{k}`' for k in sorted(cosmetic_removed))}")
            if cosmetic_added:
                lines.append(f"- Added in YAML, never fires in vetted run: {', '.join(f'`{k}`' for k in sorted(cosmetic_added))}")
            lines.append("")
    if not any_found:
        lines.append("_No cosmetic-only edits detected._")
        lines.append("")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Diff two LUminate runs to assess RCO keyword-map impact (read-only).")
    ap.add_argument("--original", default=None, help="Path to original run xlsx")
    ap.add_argument("--vetted", default=None, help="Path to RCO-vetted run xlsx")
    ap.add_argument("--input-dir", default="data/output")
    ap.add_argument("--output-dir", default="data/output")
    ap.add_argument("--keyword-yaml-original", default=None)
    ap.add_argument("--keyword-yaml-vetted", default=None)
    args = ap.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    orig_path = Path(args.original) if args.original else _latest(
        f for f in input_dir.glob("transformed_risk_taxonomy_*_original.xlsx")
        if "_orphans" not in f.stem
    )
    vetted_path = Path(args.vetted) if args.vetted else _latest(
        f for f in input_dir.glob("transformed_risk_taxonomy_*_rco.xlsx")
        if "_orphans" not in f.stem
    )

    if orig_path is None or not orig_path.exists() or vetted_path is None or not vetted_path.exists():
        missing = []
        if orig_path is None or not (orig_path and orig_path.exists()):
            missing.append("--original (expected: transformed_risk_taxonomy_*_original.xlsx)")
        if vetted_path is None or not (vetted_path and vetted_path.exists()):
            missing.append("--vetted (expected: transformed_risk_taxonomy_*_rco.xlsx)")
        print(
            f"ERROR: Could not locate input file(s): {', '.join(missing)}. "
            f"Searched: {input_dir.resolve()}. "
            f"Pass --original/--vetted explicitly or rename your runs to follow the "
            f"`*_original.xlsx` / `*_rco.xlsx` convention.",
            file=sys.stderr,
        )
        return 2

    print(f"Original : {orig_path.resolve()}")
    print(f"Vetted   : {vetted_path.resolve()}")

    orig_df = _load_sheet(orig_path)
    vetted_df = _load_sheet(vetted_path)

    o_agg = _aggregate(orig_df)
    v_agg = _aggregate(vetted_df)
    all_l2s = sorted(set(o_agg) | set(v_agg), key=lambda s: s.lower())

    empty_bucket = {"applicable_aes": set(), "kw_hit_aes": set(), "kws_by_ae": {}, "rationale_by_ae": {}}
    records = [_build_l2_record(l2, o_agg.get(l2, empty_bucket), v_agg.get(l2, empty_bucket)) for l2 in all_l2s]

    out_lines: list = []
    out_lines += _md_header(orig_path, vetted_path)
    out_lines += _md_exec_summary(records)
    out_lines.append("## Per-L2 sections")
    out_lines.append("")
    for r in sorted(records, key=lambda x: x["l2"].lower()):
        out_lines += _md_per_l2(r)
    out_lines += _md_reinstatement(records)
    out_lines += _md_summary_paragraph(records)

    if args.keyword_yaml_original and args.keyword_yaml_vetted:
        y_o_path = Path(args.keyword_yaml_original)
        y_v_path = Path(args.keyword_yaml_vetted)
        if y_o_path.exists() and y_v_path.exists():
            out_lines += _md_yaml_footer(y_o_path, y_v_path, records)

    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%m%d%Y%I%M%p")
    out_path = output_dir / f"keyword_diff_report_{ts}.md"
    out_path.write_text("\n".join(out_lines), encoding="utf-8")

    print(f"Report   : {out_path.resolve()}")
    print(f"L2s analyzed: {len(records)} "
          f"(Green={sum(1 for r in records if r['verdict']=='Green')}, "
          f"Yellow={sum(1 for r in records if r['verdict']=='Yellow')}, "
          f"Red={sum(1 for r in records if r['verdict']=='Red')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
