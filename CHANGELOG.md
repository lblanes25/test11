# Changelog — LUminate

Tracks tool version, crosswalk version, and methodology version per release.
Seeded from git history 2026-05-15. Going forward, every production run that
relies on changed crosswalk/keywords/rules gets an entry and a version bump
(see `docs/Governance.md` Part 2). Stamp the version into each generated output.

Versioning: `tool` = LUminate code; `crosswalk` = `docs/Crosswalk_vX.md`;
`methodology` = AERA taxonomy revision (Matt).

---

## [1.0] — 2026-05-15 (governance baseline)

- **tool:** 1.0 · **crosswalk:** v1.0 · **methodology:** AERA taxonomy —
  23 evaluated L2 of a 24-risk taxonomy (Earnings, Reputation, Country =
  "Not Assessed", no rows generated) (Matt 2026-05-01)
- First version with a full EUC documentation set (`docs/`).
- LLM round-trip artifacts persisted per batch (prompt.md + response.json).
- PRSA Frankenstein build automated from three Archer extracts; legacy/Archer
  inputs deduped.
- IRM ORE added as a second ORE source via `IRM ORE ID` bridge.
- Known open items at baseline: unpinned dependencies / unrecorded spaCy model
  version (**resolved in 1.0.1 below**); confidence/similarity/BMA-cutoff
  threshold *values* set but approving authority unattributed (see
  `docs/Methodology.md` §4.E open items). NOTE: the LLM
  prompt stale-sheet-name defect (raised in the earlier checklist) was a
  pre-1.0 issue **fixed 2026-05-02** ("LLM prompts: read renamed source-tab
  sheets"); current code reads the correct source sheets — not an open item.

### [1.0.1] — 2026-05-16 (canonical model correction + reproducibility)

- **Methodology correction / disclosure:** the canonical NLP mapper model is
  `en_core_web_lg`, not `en_core_web_md`. Production runs used `lg`; config,
  code, and all docs incorrectly stated `md`. All corrected to `lg`. Mapper
  similarity scores and Suggested-Match/Needs-Review banding are
  model-dependent — **outputs generated before 2026-05-16 were produced under
  `lg` while documentation said `md`**; this is disclosed in
  `docs/Governance.md` Part 3, and the sample reconciliation must run under
  canonical `lg` (now the pinned default).
- **Reproducibility:** `requirements.txt` pinned to exact installed versions
  (`pandas==3.0.1`, `openpyxl==3.1.5`, `PyYAML==6.0.3`, `spacy==3.8.14`) +
  pinned `en_core_web_lg-3.8.0` wheel. Residual: no full transitive lockfile
  (declined as excessive for a transitional tool).
- **Run provenance:** tool commit, spaCy model+version, and library versions
  now logged to the run log and stamped into the Excel Methodology tab and
  HTML report banner (`utils.get_run_provenance`).

### [1.0.2] — 2026-05-17 (documentation consolidation)

- EUC documentation set consolidated from 13 documents into 5
  (`docs/Methodology.md`, `Operations.md`, `Validation.md`, `Governance.md`,
  `Crosswalk_v1.0.md`) + this changelog. Driver: the prior set threaded the
  same facts through many files (the md→lg and stale-LLM-bug corrections each
  required ~7–8 edits), a maintenance hazard for a single-owner transitional
  tool. Now one home per fact; old artifact names preserved as titled
  sections; `docs/README.md` carries the old→new map. No content removed.
- Scope figure corrected to **~10,000 decisions / 450+ entities** across the
  EUC doc set (the earlier ~4,600/200+ figure was incorrect).

### [1.0.3] — 2026-05-17 (NLP confidence band removed)

- NLP mappers (ORE/ORE-IRM/PRSA/GRA RAP) no longer assert a positive-
  confidence band. Every item above the 0.50 similarity floor presents as
  **"Needs Review"**; the Suggested-vs-Needs ambiguity-margin threshold is
  gone. Removes a threshold the tool could not defend at governance and
  strengthens the over-reliance mitigation. `Source-Tagged` (PRSA Track B /
  IRM provenance) and `No Match` (below floor) preserved.
- Point-of-use caveat added to the mapper-evidence surfaces: source-tab
  banners (Excel + HTML) and a `title=` tooltip on the Mapping Status column
  headers (HTML) — "starting point; NLP can be wrong; confirm the L2".
- Docs squared: `Methodology.md` §4.C5–C6/§4.E, `luminate_disclaimers.md`,
  `risk_taxonomy_transformer/methodology.yaml` "NLP mapping confidence".
- "Suggested Match" left in `*_confidence_filter` for backward-compat with
  previously-generated workbooks (no behavior change — membership filter).

### [1.0.4] — 2026-05-17 (per-edge `conditions:` keyword lists removed)

- The per-edge `conditions:` keyword lists on `conditional` multi-targets were
  removed. Conditional targets (Operational → Data, Operational → Internal
  Fraud) now gate purely on the target L2's own `keyword_map` list — one
  keyword list per L2, no separate surface.
- **Why:** the two `conditions:` lists were fully redundant with
  `keyword_map["Data"]` / `keyword_map["Internal Fraud"]`, added no term those
  lists didn't already supply, had no owner (out of RCO keyword-validation
  scope), and — because code concatenated `keyword_map + conditions` — caused
  overlapping terms to be **double-counted** in the confidence score,
  inflating some `medium` matches to `high`.
- **Decision-outcome effect:** for the same inputs, an Operational rationale
  hitting an overlapping Data/Internal-Fraud term now scores once, not twice;
  borderline rows that were `high` purely from the double-count become
  `medium`. Applicability (the row appearing at all) is unchanged — every
  trigger term still lives in `keyword_map`. Verified: conditional still fires
  on `keyword_map` hits and stays silent without them; negative control clean.
- **Files:** `risk_taxonomy_transformer/mapping.py` (both scoring sites + N/A
  path), `risk_taxonomy_transformer/config.py` (dropped conditions
  lower-casing), `config/taxonomy_config.yaml` (removed both `conditions:`
  blocks + comments), `docs/Crosswalk_v1.0.md` (header note, legend, Operational
  rows), `config/methodology_reference.md` (Operational target count/desc).
- No route or relationship changed (crosswalk stays v1.0). This is part of
  the still-unsigned crosswalk/keyword baseline; whenever the methodology-owner
  sign-off eventually happens it covers this along with everything else — it
  is not a separately gated item.

### [1.0.5] — 2026-05-17 (multi-target `secondary` relationship collapsed into `primary`)

- The `secondary` relationship tier was removed. Multi-target relationships
  are now just `primary` and `conditional`. The three former `secondary`
  targets (Operational → Conduct, Operational → Privacy, Compliance →
  Conduct) are now `primary`.
- **Why:** `secondary` had no distinct behavior. For rationale-bearing
  pillars all targets are scored identically against the L2's `keyword_map`;
  `relationship` only ever affected the `evidence_match (…)` label and the
  no-rationale-pillar auto-populate filter (which keys on `primary`). The
  "secondary = always populated, flagged" tiering in the comments was never
  implemented. Removed dead `first_primary_l2` in `_resolve_multi_mapping`.
- **Decision-outcome effect:** none. Same scoring, same gating, same rows;
  only the method label changes `evidence_match (secondary)` →
  `evidence_match (primary)` for those three edges. Verified: pipeline clean,
  no `(secondary)` labels emitted, Conduct/Privacy rows unchanged.
- **Files:** `risk_taxonomy_transformer/mapping.py` (dead-code removal),
  `config/taxonomy_config.yaml` (3 relationships + legend comment),
  `docs/Crosswalk_v1.0.md` (semantics table + 3 rows),
  `config/methodology_reference.md` (relationship desc, counts, method table).
- No route changed (crosswalk stays v1.0). Part of the still-unsigned
  baseline; not a separately gated item.

### [proposed, pending Matt sign-off] — Strategic & Business → Capital (Option C)

- `Strategic & Business` keeps `mapping_type: direct` (Capital applicability
  still carries) but gains `suppress_rating: true` — legacy S&B rating no
  longer populates Capital's Proposed Rating; reviewer assigns it. Reuses the
  existing External Fraud mechanism (no new config keys).
- `enrichment.py` DIRECT decision-basis text guarded so a suppressed-rating
  direct pillar no longer claims "Rating … carried forward" on a blank cell.
  New text: "Direct from Strategic & Business. Rating not carried forward —
  review and assign an L2-specific rating."
- Verified: Capital = Applicable, Proposed Rating blank; External Fraud and
  normal direct pillars (Model) unchanged; PRSA provenance regression PASS.
- **Governance status:** implemented in config + behaviour-verified, **NOT
  signed**. Crosswalk stays **v1.0**. On AERA methodology-owner approval
  (sign-off item 1a) → Crosswalk **v1.1** + sign + this entry finalized.
  Docs squared: `Methodology.md` §4.B5/§4.E, `Crosswalk_v1.0.md`.

## Pre-1.0 history (condensed from git)

### 2026-05 — taxonomy & source expansion
- Fraud promoted to L3 evaluation grain; External Fraud rating carryforward
  suppressed (Matt 2026-05-01). L2 canonical renames.
- Branding renamed to LUminate (2026-05-06).
- Source banner rework: per-source methodology + Upstream Tagging Gaps tab.
- Models inventory enriched; LLM prompt batched by item count.

### 2026-05 — crosswalk/config hardening
- L2 alias map moved code→YAML with startup validation.
- Reputational/Country documented as out-of-crosswalk ("Not Assessed").
- Cross-boundary keyword threshold trade-off documented.
- Mapper filters standardized (Suggested Match across ORE/PRSA/RAP).
- `validate_inputs.py` added (file manifest + column-header alignment).
- `refresh.py` one-button runner added.

### 2026-04 — workflow & UX
- Decision Basis consolidation; rating policy tightened (blank for non-direct,
  SVP 2026-04-07).
- Audit_Review column/visibility cleanups; diagnostics moved to Side_by_Side.
- Mapper L3-canonical bucketing.

### Earlier
- Initial pipeline: ingestion / mapping / enrichment / flags / export split
  from `risk_taxonomy_transformer_original.py`; crosswalk + keyword scoring +
  dedup + gap-fill; HTML report.

Full commit-level history: `git log`.
