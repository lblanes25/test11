# Current renderSignals behavior

Source: `export_html_report.py` lines 1435–1511. Called from line 1913 with `row["Additional Signals"]` (the pipe/newline-separated string produced by the transformer into the `Audit_Review` sheet). Runs client-side on L2 row expansion, so the emitted HTML does NOT appear anywhere in the static report file until a user expands a row.

## Pipeline (in order)

1. **Empty guard** — `isEmpty(signals)` returns `""`; no section rendered.
2. **Split into atomic items** — `String(signals).split(/\n| \| /)` on newline OR space-pipe-space. Empty results filtered.
3. **Per-item classification (first match wins)**:
   a. **Contradiction** — if `.toLowerCase()` contains `"well controlled but"` OR `"review whether"`, stored as `{kind:"contradiction", text: <raw>}` and no further parsing. Note: a literal `"review whether"` substring inside any other signal also routes here.
   b. **Otherwise `{kind:"signal"}`**, with sub-parsing:
      - **Leading tag** — `/^\[([^\]]+)\]\s*/` matched and **stripped from body; the captured tag value is discarded entirely** (never rendered as chip or prefix). The `.signal-tag` CSS class defined at line 455 is defined but never emitted.
      - **Em-dash split** — first `\u2014` splits body into `body` (before) and `hint` (after). Only the FIRST em-dash is used.
      - **Paren-with-semicolons IDs** — finds first `(`...`)`; if the inner text contains `;`, splits on `;`, joins with `\u00B7` middle-dots, stores in `ids`, and removes the `(...)` from body. **Commas inside parens are NOT treated as IDs.** Without a `;`, the parens stay in `body`.
4. **Shared-hint consolidation** — if there are ≥2 signal rows AND every signal row has the exact same non-empty `hint`, the hint is extracted to a single parenthesized suffix on the section label (`<em class="label-suffix">(...)</em>`), and per-row hints are cleared. Contradictions are excluded from this check.
5. **Emit HTML** — container: `<div class="drill-section"><span class="label">Additional Signals …</span>`.
   - Contradictions (in input order): `<div class="signal-row signal-contradiction">🚨 <raw text></div>`.
   - Signal rows, wrapped once in `<div class="drill-signal-grid">`:
     - If `ids` present: two cells, `<div class="label-cell">bodyText</div>` + `<div class="ids-cell">ids</div>`.
     - Else: single `<div class="full-cell">bodyText</div>` spanning both columns.
   - `bodyText` = `body` + (if non-shared hint) `" — " + hint`.

## CSS classes

Defined (`export_html_report.py` lines 453–502):
- `.signal-row`, `.signal-contradiction` — contradiction row only.
- `.signal-tag`, `.signal-ids`, `.signal-hint` — **defined but never emitted** by `renderSignals`. Dead styles.
- `.drill-signal-grid` (2-col: `minmax(180px,auto) 1fr`) with children `.label-cell`, `.ids-cell`, `.full-cell`.
- `.drill-section .label em.label-suffix` — styles the consolidated shared-hint suffix.

## Fall-through paths that render raw text essentially as-is

- A signal containing the substring `"review whether"` anywhere becomes a contradiction and is emitted as one un-parsed line with the raw `[TAG]` preserved.
- A no-tag, no-em-dash, no-semicolon-parens signal becomes a single `.full-cell` with the entire raw string (minus nothing).

---

# Observed rendered output

Source report (most recent by mtime): `data/output/risk_taxonomy_report_041820260200PM.html` (2026-04-18 14:00).

The drill-down section is built at runtime on expand, so the rendered HTML does **not** appear in the static file. `renderSignals` emissions were simulated in Python using a 1:1 port of the JS logic and fed real raw strings from the embedded `const auditData = [...]` payload.

230 audit-review rows total; **59 rows with non-empty `Additional Signals`**; 27 of those are multi-atom (contain ` | ` and/or newline); 100 total atomic signals across those 59 rows. Zero contradictions in this dataset.

## Sample 1 — AE-3 / Processing, Execution and Change (Applicability Undetermined)

Raw:
```
[Aux] Listed as auxiliary risk in legacy entity data (AXP) — consider this risk may be applicable
[Cross-boundary] Referenced in Compliance pillar rationale ('procedure', 'transaction') and sub-risk CO-301 ('transaction') — outside normal mapping. Consider whether this L2 applies to this entity.
```

Simulated render:
```html
<div class="drill-section"><span class="label">Additional Signals</span>
  <div class="drill-signal-grid">
    <div class="full-cell">Listed as auxiliary risk in legacy entity data (AXP) — consider this risk may be applicable</div>
    <div class="full-cell">Referenced in Compliance pillar rationale (&#x27;procedure&#x27;, &#x27;transaction&#x27;) and sub-risk CO-301 (&#x27;transaction&#x27;) — outside normal mapping. Consider whether this L2 applies to this entity.</div>
  </div>
</div>
```

Classes: `drill-section`, `label`, `drill-signal-grid`, `full-cell`. Pipe separator: not present in input (only newline). Tag prefix: stripped, lost. Hints: two different hints → no shared-hint suffix.

## Sample 2 — AE-3 / Third Party (Applicable)

Raw:
```
[App] Primary third party engagement mapped to entity (TLM-1004, TLM-1005) — consider this risk may be applicable | Secondary third party engagement related to entity (TLM-1006) — consider this risk may be applicable
[Aux] Listed as auxiliary risk in legacy entity data (AXP) — consider this risk may be applicable
```

Simulated render (abridged):
```html
<div class="drill-section"><span class="label">Additional Signals <em class="label-suffix">(consider this risk may be applicable)</em></span>
  <div class="drill-signal-grid">
    <div class="full-cell">Primary third party engagement mapped to entity (TLM-1004, TLM-1005)</div>
    <div class="full-cell">Secondary third party engagement related to entity (TLM-1006)</div>
    <div class="full-cell">Listed as auxiliary risk in legacy entity data (AXP)</div>
  </div>
</div>
```

Classes: `drill-section`, `label`, `label-suffix`, `drill-signal-grid`, `full-cell`. Pipe separator: consumed (does NOT survive). All three rows share the hint, so consolidation kicks in and the suffix appears once. IDs use comma separators so they stay inside the parens in the body (no `ids-cell` split). Tags (`[App]`, `[Aux]`) both stripped and lost — no visual distinction between the two signal categories.

## Sample 3 — AE-3 / Data (Applicable)

Raw:
```
[App] Primary application mapped to entity (ARA-1011; ARA-1012; ARA-1013) — consider this risk may be applicable | Secondary application related to entity (ARA-1014) — consider this risk may be applicable
```

Simulated render (abridged):
```html
<span class="label">Additional Signals <em class="label-suffix">(consider this risk may be applicable)</em></span>
<div class="drill-signal-grid">
  <div class="label-cell">Primary application mapped to entity</div>
  <div class="ids-cell">ARA-1011 · ARA-1012 · ARA-1013</div>
  <div class="full-cell">Secondary application related to entity (ARA-1014)</div>
</div>
```

Classes: `drill-section`, `label`, `label-suffix`, `drill-signal-grid`, `label-cell`, `ids-cell`, `full-cell`. Pipe consumed. **Inconsistent row layout within the same grid** — first row uses two-column label/ids split, second row uses a single-cell full-cell because it has one ID (no semicolon) so the parens stay inline. Visually: the Primary row's body is right-padded to the min column width (180px), and then ARA IDs mono/gray on the right; the Secondary row spans full width and shows the ID still parenthesized inside the sentence.

## Sample 4 — AE-3 / Technology (Applicable) — the worst case

Raw:
```
[App] Primary application mapped to entity (ARA-1011; ARA-1012; ARA-1013) — consider this risk may be applicable | Secondary application related to entity (ARA-1014) — consider this risk may be applicable
[Cross-boundary] Referenced in Credit pillar rationale ('it ') and sub-risk CR-301 ('it ') — outside normal mapping. Consider whether this L2 applies to this entity. | Referenced in External Fraud pillar rationale ('it ') and sub-risk EF-301 ('it ') — outside normal mapping. Consider whether this L2 applies to this entity.
```

Simulated render (abridged):
```html
<span class="label">Additional Signals</span>   <!-- no shared-hint suffix: hints differ across rows -->
<div class="drill-signal-grid">
  <div class="label-cell">Primary application mapped to entity — consider this risk may be applicable</div>
  <div class="ids-cell">ARA-1011 · ARA-1012 · ARA-1013</div>
  <div class="full-cell">Secondary application related to entity (ARA-1014) — consider this risk may be applicable</div>
  <div class="full-cell">Referenced in Credit pillar rationale (&#x27;it &#x27;) and sub-risk CR-301 (&#x27;it &#x27;) — outside normal mapping. Consider whether this L2 applies to this entity.</div>
  <div class="full-cell">Referenced in External Fraud pillar rationale (&#x27;it &#x27;) and sub-risk EF-301 (&#x27;it &#x27;) — outside normal mapping. Consider whether this L2 applies to this entity.</div>
</div>
```

Classes: same set. Pipe consumed (both the `[App]` line and the `[Cross-boundary]` line contained `" | "`). **Shared-hint consolidation fails** because the [App] rows hint ≠ [Cross-boundary] rows hint, so "consider this risk may be applicable" is repeated **twice** inline and "outside normal mapping. Consider whether this L2 applies to this entity." is repeated **twice** inline. Tags both stripped — nothing visually separates the Applicability signal from the Cross-boundary signal. The single-ID row (ARA-1014) and the semicolon-ID row layout differently inside the same grid. The `'it '` keyword match (with trailing space) is a noise artifact from upstream but survives into the rendered string as escaped HTML entities.

## Sample 5 — AE-3 / Prudential & bank administration compliance (Applicable)

Raw:
```
[Aux] Listed as auxiliary risk in legacy entity data (AXP) — consider this risk may be applicable
```

Simulated render:
```html
<span class="label">Additional Signals</span>
<div class="drill-signal-grid">
  <div class="full-cell">Listed as auxiliary risk in legacy entity data (AXP) — consider this risk may be applicable</div>
</div>
```

Classes: `drill-section`, `label`, `drill-signal-grid`, `full-cell`. Single-atom rows never benefit from shared-hint consolidation (guard is `signalRows.length >= 2`). Tag stripped.

---

# Diagnosis

1. **Is `renderSignals` actually being called?** Yes. Simulation output matches what a grid-styled container would produce, and the function is invoked unconditionally at `export_html_report.py:1913` on drill-down expand. The reason the rendered DOM classes don't show up in the static HTML file is expected — the function runs client-side on expand. So the user's "looks like raw text" impression is not a bypass; the parser IS running. The issue is what it produces.

2. **Walk of regexes on Sample 4's first atom** `[App] Primary application mapped to entity (ARA-1011; ARA-1012; ARA-1013) — consider this risk may be applicable`:
   - Split on `\n| \| ` → yields this atom (split consumed the ` | ` before "Secondary...").
   - `lower.includes("well controlled but")` → false. `lower.includes("review whether")` → false. Not contradiction.
   - `/^\[([^\]]+)\]\s*/` matches `[App] `. Captured tag `App` **discarded**. `body` becomes `"Primary application mapped to entity (ARA-1011; ARA-1012; ARA-1013) — consider this risk may be applicable"`.
   - `indexOf("\u2014")` finds the em-dash. `hint = "consider this risk may be applicable"`. `body = "Primary application mapped to entity (ARA-1011; ARA-1012; ARA-1013)"`.
   - `indexOf("(")` → 38; `indexOf(")", 38)` → 72; inner = `"ARA-1011; ARA-1012; ARA-1013"`. Contains `;`. Split → `["ARA-1011","ARA-1012","ARA-1013"]`, joined → `"ARA-1011 · ARA-1012 · ARA-1013"`. `body = "Primary application mapped to entity"` (parens and contents removed).
   - Result: `{kind:"signal", body:"Primary application mapped to entity", ids:"ARA-1011 · ARA-1012 · ARA-1013", hint:"consider this risk may be applicable"}`.
   - Paired with the other 4 atoms in this row, shared-hint check fails (mixed hints) so hint is kept inline. Emits `.label-cell` + `.ids-cell`.

3. **Plain / full-cell branch quality.** The grid renders one-line items acceptably. But when the grid contains a MIX of rows — some with `label-cell`+`ids-cell`, some with `full-cell` — the column widths are determined by the tallest/widest label-cell, leaving awkward empty right-columns on full-cell rows (they span both columns, which is fine, but the two layout modes look visually unrelated). Sample 3 and Sample 4 both exhibit this.

4. **Real-data shapes that the parser does NOT handle cleanly:**
   - **Comma-separated ID lists** (`TLM-1004, TLM-1005`) — ID extraction only fires on `;`, so commas leave the IDs inline in the body. 7 of 34 [App] atoms use commas.
   - **Multiple parenthesized groups on one line** — Cross-boundary signals like `Referenced in X pillar rationale ('a', 'b') and sub-risk ID (...)`. The parser finds only the FIRST `(...)` and never the second. If the first paren contains `;` (doesn't in practice), it would eat the keyword-quotes paren and leave the sub-risk ID paren in the body. In practice, the first paren is keyword-quotes with commas (no `;`), so both parens survive in body → full-cell render.
   - **Second em-dash** — the parser only splits on the first. No signal in this dataset has a second em-dash, so this is latent.
   - **No-tag plain signals** — 27 of 100 atoms arrive with no `[TAG]` prefix at all; the parser handles them but they still look identical to tagged signals (because tags are stripped anyway).
   - **Repeated boilerplate** — "outside normal mapping. Consider whether this L2 applies to this entity." appears verbatim in 17 atoms across 14 rows. Consolidates cleanly only when a row is ALL Cross-boundary with ≥2 atoms; otherwise it's repeated per row.

---

# Visual problems

Per sample, based on simulated DOM + the defined CSS (`.drill-signal-grid` = 2-col grid with `minmax(180px,auto) 1fr`, 6px/16px gap, 13px body font).

- **Boilerplate repetition.** "outside normal mapping. Consider whether this L2 applies to this entity." appears once per Cross-boundary atom. In Sample 4 it appears twice in adjacent rows. Shared-hint consolidation only fires when every row's hint is identical, so any mixed-signal row (App+Cross-boundary, App+Aux with differing hints) repeats boilerplate inline. 5 of 27 multi-atom rows fall in the "consolidation fails" bucket; the other 22 do consolidate (22 rows render boilerplate once as the label suffix).
- **RISK IDs (e.g. RISK ID-6208 / CO-301 / CR-301) are NOT visually distinguished** except in the narrow case where they appear as a semicolon-separated list inside the first paren (then they move to `.ids-cell` with mono font). For the Cross-boundary pattern `sub-risk CO-301 ('transaction')`, the ID is free-standing text inside `body` with no styling, and then the keyword-quotes paren `('transaction')` is also in body.
- **Quoted keyword snippets (`'procedure'`, `'it '`)** have no special styling. They appear as HTML-escaped single quotes (`&#x27;`) inside the body text.
- **`[TAG]` prefix is neither chip nor prefix — it is DELETED.** The captured tag string is never rendered. `.signal-tag` CSS exists but is dead. So a user reading the grid has no way to tell "[App]" from "[Aux]" from "[Cross-boundary]" — the only cue is the body wording.
- **Space efficiency.** Each atom is ~90–200 chars (median 103). Rendered grid rows are short prose lines; the grid gap is 6px vertical which is tight. In consolidation-fails cases, the same 40-char hint is repeated per row, costing horizontal and vertical budget. Grid columns (180px label + remainder for ids) leave odd empty right-space on `full-cell` rows in mixed grids.
- **Overall scannability.** The grid makes 2+ same-shape rows scannable IF they consolidate, but the mixed-tag cases look like a wall of text because: (a) no tag chip to group by, (b) repeated boilerplate, (c) inconsistent label-cell vs full-cell layout within one grid, (d) no visual weight on IDs unless the specific semicolon condition triggers. The user's "looks like raw text" description matches the worst-case mixed rows (Sample 4 is the archetype). Simple single-tag-multi-atom cases (Sample 2) look acceptable.

---

# Signal shapes in real data

59 rows, 100 atomic signals. Distinct shapes observed (counts by atomic signal):

1. **`[App] Primary application mapped to entity ({semicolon-ID-list}) — consider this risk may be applicable`** — 27 atoms. Renders nicely (label-cell + ids-cell) when consolidation works.
2. **`[Aux] Listed as auxiliary risk in legacy entity data ({code}) — consider this risk may be applicable`** — 25 atoms. The `(AXP)` paren has no semicolon, so it stays in body. Always full-cell.
3. **`[App] Secondary application related to entity ({semicolon-ID-list-OR-single}) — consider this risk may be applicable`** — 18 atoms. Sometimes semicolon (→ grid split), sometimes single ID (→ full-cell).
4. **`[App] Primary third party engagement mapped to entity ({comma-ID-list}) — consider this risk may be applicable`** — 7 atoms. Commas, not semicolons → no ID extraction → full-cell.
5. **`[App] Secondary third party engagement related to entity ({comma-ID-list}) — consider this risk may be applicable`** — 6 atoms. Same as #4.
6. **`[Cross-boundary] Referenced in {Pillar} pillar rationale ({'kw',...}) and sub-risk {ID} ({'kw',...}) — outside normal mapping. Consider whether this L2 applies to this entity.`** — ~13 atoms (spans 7 pillar variants: Credit 4, Compliance 3, Operational 3, External Fraud 1, Market 1, Strategic & Business 1, Information Technology variant 1). Two parens, first has no `;`, so everything stays in body → full-cell. Long, boilerplate-heavy.
7. **`[Cross-boundary] Referenced in {Pillar} pillar rationale ({'kw',...}) — outside normal mapping. Consider whether this L2 applies to this entity.`** — 2 atoms (Market, Funding & Liquidity). No sub-risk ID.
8. **`[Cross-boundary] Referenced in {Pillar} sub-risk {ID} ({'kw',...}) — outside normal mapping. Consider whether this L2 applies to this entity.`** — 2 atoms. No pillar rationale half.

Tag distribution across all 100 atoms: `[App]` 34, `[Aux]` 25, `[Cross-boundary]` 14, no-tag 27. (The no-tag count is higher than expected; likely those are parts of the [App] shape where the second pipe-separated atom does NOT carry its own `[TAG]`, e.g. `[App] Primary ... | Secondary ... (note the Secondary atom has no bracket tag)`. This is consistent with the shapes above — tags only lead the first atom, subsequent pipe-joined continuations inherit implicitly but the parser has no concept of "inherited tag".)

Contradictions: **0** in this dataset. The contradiction branch is unreachable with current data.

---

# Recommendations for redesign

- **Make the tag visible.** Either emit it as a chip (use the already-defined `.signal-tag` CSS) or group atoms by tag under a sub-heading so "Applicability" vs "Cross-boundary" vs "Auxiliary" is scannable at a glance. Currently the tag is parsed and then thrown away.
- **Consolidate boilerplate unconditionally.** For both hints AND the "outside normal mapping / Consider whether…" suffix, strip once at the group level (per tag) rather than requiring global identity. The shared-hint check already fails on any mixed-tag row.
- **Extend ID extraction to commas** (and handle multiple parens per atom). 13 of 34 [App] atoms use comma ID lists and currently don't render in the mono `.ids-cell`. Decide on one consistent row layout — either always label+ids or always full-cell — so the grid doesn't render two visual styles in one block.
- **Treat the no-tag continuation atom as inheriting the prior tag** (or emit the full tag on every atom upstream in `Audit_Review` construction). Today a Primary/Secondary pair renders as a tagged row followed by an implicitly-same-category row that looks tag-less.
- **Drop the dead contradiction branch or rewire it to something that actually fires in current data.** Zero atoms match `well controlled but` or `review whether` — the branch plus its `.signal-contradiction` CSS is presently unreachable, which misleads readers of the code.
