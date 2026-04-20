# Hint Diff Report

**Source xlsx**: `transformed_risk_taxonomy_042020260854AM.xlsx` (most recent by mtime)
**Sheet**: `Audit_Review`
**Rows scanned**: 230
**Rows with non-empty `Additional Signals`**: 62

## Methodology

Replicated the `renderSignals` parser pipeline in both Python and Node.js:
1. Split `Additional Signals` on `\n`.
2. Split each line on `" | "`.
3. Tag-boundary split: `\s\[[A-Za-z][A-Za-z0-9 \-]*\]\s`.
4. For each atom, extract leading `[Tag]` (with same-line inheritance after the first tagged atom) and hint (substring after first `\u2014`, `.trim()`-ed per the JS code).
5. Group atoms by tag across all rows.
6. For each per-entity per-tag group with 2+ atoms, evaluate the current JS hoist check verbatim: `first = items[0].hint; fires = !!first && items.every(it => it.hint === first)`.

To rule out any Python-vs-JS string handling discrepancy, the final check was executed in Node.js v22.15.0 using the exact same regexes and `.trim()` semantics as the in-browser code.

## Findings

| Metric | Count |
|---|---|
| Hint groups inspected (>=2 atoms, same tag, same entity) | **30** |
| Groups where hoist fires under current `===` logic | **30** |
| Groups where hoist fails (any cause) | **0** |
| Near-matches blocked by trailing whitespace | 0 |
| Near-matches blocked by trailing period | 0 |
| Near-matches blocked by case | 0 |
| Near-matches blocked by smart-vs-straight quotes | 0 |
| Near-matches blocked by NBSP (U+00A0) | 0 |
| Near-matches blocked by zero-width chars | 0 |
| Near-matches blocked by internal whitespace | 0 |
| Mixed-hint groups (some atoms with hint, some without) | 0 |

## Verification of the symptom entities

The entities referenced by the symptom both have multi-App + multi-Cross-boundary patterns:

### `AE-1`
**App hints** (identical under `repr()`):
  - `'consider this risk may be applicable'`
  - `'consider this risk may be applicable'`

**Cross-boundary hints** (identical under `repr()`):
  - `'outside normal mapping. Consider whether this L2 applies to this entity.'`
  - `'outside normal mapping. Consider whether this L2 applies to this entity.'`

### `AE-3`
**App hints**:
  - `'consider this risk may be applicable'`
  - `'consider this risk may be applicable'`

**Cross-boundary hints**:
  - `'outside normal mapping. Consider whether this L2 applies to this entity.'`
  - `'outside normal mapping. Consider whether this L2 applies to this entity.'`

For both entities, strict `===` returns `true` between the paired hints, and the Node.js emulation of the exact JS hoist logic reports that the hoist **does** fire.

## Conclusion

The data shows the hoist is already working against the current xlsx. No normalization is justified by the evidence. The reported symptom was either from an older xlsx (pre-dating whatever transformer change canonicalized the hints) or a stale cached HTML report in the user's browser.

**Recommendation**: no code change. Regenerate the HTML report and hard-refresh the browser.
