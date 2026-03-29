"""Diagnose row count issues in transformer output.

Run this after the transformer completes. It reads the latest output
and prints statistics to help identify why row counts are off.

Usage: python tests/diagnose_output.py
"""

import pandas as pd
from pathlib import Path

output_dir = Path(__file__).parent.parent / "data" / "output"
latest = sorted(output_dir.glob("transformed_risk_taxonomy_*.xlsx"),
                key=lambda f: f.stat().st_mtime)
if not latest:
    print("No output files found in data/output/")
    exit(1)

print(f"Analyzing: {latest[-1].name}\n")

# Read Side_by_Side for full detail
df = pd.read_excel(latest[-1], sheet_name="Side_by_Side")

total = len(df)
entities = df["entity_id"].nunique()
expected = entities * 23

print(f"Total rows: {total}")
print(f"Unique entities: {entities}")
print(f"Expected (entities x 23 L2s): {expected}")
print(f"Excess rows: {total - expected}")
print()

# Rows per entity distribution
per_entity = df.groupby("entity_id").size()
print(f"Rows per entity — min: {per_entity.min()}, max: {per_entity.max()}, "
      f"mean: {per_entity.mean():.1f}, median: {per_entity.median():.0f}")
print()

# Entities with more than 23 rows
over_23 = per_entity[per_entity > 23]
print(f"Entities with >23 rows: {len(over_23)} of {entities}")
if len(over_23) > 0:
    print(f"  Top 10 worst:")
    for eid, count in over_23.sort_values(ascending=False).head(10).items():
        print(f"    {eid}: {count} rows ({count - 23} extra)")
print()

# Duplicate entity+L2 pairs
dupes = df.groupby(["entity_id", "new_l2"]).size()
dupes_gt1 = dupes[dupes > 1]
print(f"Duplicate entity+L2 pairs: {len(dupes_gt1)}")
if len(dupes_gt1) > 0:
    print(f"  Top 10 duplicates:")
    for (eid, l2), count in dupes_gt1.sort_values(ascending=False).head(10).items():
        print(f"    {eid} / {l2}: {count} rows")

    # Show methods for a sample duplicate
    sample_eid, sample_l2 = list(dupes_gt1.index)[0]
    print(f"\n  Detail for {sample_eid} / {sample_l2}:")
    sample = df[(df["entity_id"] == sample_eid) & (df["new_l2"] == sample_l2)]
    for _, row in sample.iterrows():
        print(f"    method={row.get('method', '?')}  "
              f"confidence={row.get('confidence', '?')}  "
              f"source={row.get('source_legacy_pillar', '?')}  "
              f"rating={row.get('likelihood', '?')}")
print()

# Method distribution
print("Method distribution:")
method_counts = df["method"].value_counts()
for method, count in method_counts.items():
    print(f"  {method}: {count}")
print()

# L2s that appear more than once per entity on average
l2_avg = df.groupby("new_l2").size() / entities
over_1 = l2_avg[l2_avg > 1.0].sort_values(ascending=False)
if len(over_1) > 0:
    print("L2s averaging >1 row per entity (should be exactly 1.0):")
    for l2, avg in over_1.items():
        print(f"  {l2}: {avg:.2f} rows/entity")
