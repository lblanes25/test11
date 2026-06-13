# LUminate Improvement Plan

Date: 2026-06-12. Based on a full exploration of the codebase.
User decisions baked in (confirmed 2026-06-12): mapper consolidation **approved**, HTML exporter split **approved**, latest-file selection fix **approved**, Keyword Hits leak **fix at source**.

> **Execution status (2026-06-12, branch `improvement-plan`):** Tiers 1–3 and
> 5.1/5.3 EXECUTED and verified (168 unit tests + golden regression green;
> mapper outputs value-identical; HTML byte-identical; Keyword Hits Track 1
> column diff captured). Tier 4 intentionally untouched. Outstanding: 5.2 done
> earlier same day; 5.4 root-md hygiene (owner's call); 5.5 alias backlog
> (existing TODO). New follow-ups found by characterization tests (reported,
> not fixed — candidate Track 1 items): dead abbreviation regexes in
> rating.py (~119–130, can never match post-lowercase); Key Risk IDs column
> leaks keywords (mapping.py:121 unused `truncated`); parenthesized impact
> form `impact (financial): high` never parses.

---

## Part 1 — Assessment

### Architecture

Sound overall. The pipeline is a clean layered package (`risk_taxonomy_transformer/`) with imports flowing one direction: `config/constants/normalization` → `ingestion` → `mapping/pipeline` → `enrichment/rating/flags/optro` → `review_builders/export/formatting`. Root-level scripts (mappers, Frankenstein build, consolidators, validators) are orchestrated by `refresh.py` with sensible gate/warn semantics. Decision logic is deterministic (crosswalk + findings); NLP is advisory only — this separation is consistently maintained.

Three structural weak points:

1. **`export_html_report.py` is a 5,800-line single file** — ~430 lines Python, ~870 lines CSS, and a ~4,000-line JavaScript template string edited blind (no syntax checking inside a Python string), plus one ~400-line `generate_html_report` function.
2. **The three NLP mappers are ~50–65% copy-paste of each other** (`ore_mapper.py` 1,063 lines, `prsa_mapper.py` 779, `rap_mapper.py` 730). `build_reference_vectors`, `compute_mappings`, `determine_ambiguity_threshold`, `classify_mappings`, and the Excel export/styling helpers are near-identical (~400–500 duplicated lines per file). They *do* correctly import `normalize_l2_name`, `L2_TO_L1`, and provenance logging from the package — the duplication is application logic, not reinvention.
3. **`__main__.py` is a 1,000-line orchestrator** mixing file discovery, Track B substitution logic, and orphan capture. Functional, but the Track B block (lines 751–831) is business logic living in the entrypoint.

### Code quality

Good: comprehensive type hints, mostly surgical exception handling, config-driven column names (with exceptions below), intentional patterns documented in docstrings. The convention "all data-source column mappings in `taxonomy_config.yaml`" is mostly honored.

Violations and fragilities found:

- Hardcoded L2-keyed maps that silently break on an L2 rename: `flags.py:30–36` (`_APP_L2_MAP`), `review_builders.py:81–105` (`_L2_SHORT_DISPLAY`), `optro.py:33–40` (signal column list). The documented L2-rename procedure assumes a YAML-only change; these maps make that assumption false.
- `enrichment.py:48–75` (`_parse_control_level`) hardcodes terminology that duplicates config.
- Mapper margin thresholds (floor 0.01, cap 0.05, P25 quantile) hardcoded in all three mappers.
- ~12 call sites select "the latest file" by `st_mtime` even though filenames carry timestamps — copying/touching an older export silently selects the wrong file.
- Two non-deterministic sort sites (`ingestion.py:52–53`, `review_builders.py:298`) — same-key rows get arbitrary order, breaking run-to-run reproducibility.
- One silent `except Exception: return pd.DataFrame()` in `export_html_report.py:208–209` that can empty an inventory tab with no log line.
- `consolidate_ore_irm.py:238–250` reads config columns by list position rather than name.

### Test coverage

Thin. Two test files exist: `tests/test_ore_irm_consolidate.py` (proper pytest, 13 cases, good) and `tests/test_prsa_provenance.py` (a manual `python` script with `exit()` semantics, needs pre-built fixtures). There is **no conftest.py, pytest.ini, or pyproject.toml** — no single command runs the suite. The 13 `generate_*_test_data.py` scripts produce synthetic fixtures into `data/input/` but are invoked manually.

Zero direct coverage on the decision path: `normalization.py`, `mapping.py` (including the 6-branch dedup), `rating.py`, `enrichment.py`, `flags.py`, `review_builders.py`, `optro.py`, the three mappers, and the HTML exporter. The project's gating validation is sample reconciliation (manual re-derivation), which is appropriate for sign-off but doesn't protect day-to-day changes; Track 2 changes nominally require "regression" with no automated harness behind the word.

### Dependencies

Small and well-pinned: `pandas==3.0.1`, `openpyxl==3.1.5`, `PyYAML==6.0.3`, `spacy==3.8.14`, and the spaCy model wheel pinned to `en_core_web_lg-3.8.0` (good EUC reproducibility; provenance stamped into outputs). Gaps: `numpy` is used directly (mappers) but only present transitively; `python-pptx` and `lxml` are used by the untracked presentation builders but undeclared. `risk_taxonomy_transformer_original.py` (173KB pre-refactor monolith) is dead — referenced by nothing, already gitignored.

---

## Part 2 — Prioritized improvements

Ordering: correctness → tests → refactors → performance → nice-to-haves. Within each tier, highest impact-per-risk first.
Change-control note: items marked **[Track 1]** change governed output values and need a before/after diff as evidence; everything else must produce **identical output** (Track 2) and is verified by output comparison.

### Tier 1 — Bugs and correctness

**1.1 Centralize "latest file" selection on filename timestamp, mtime fallback** — *high impact, low risk*
- **Files:** new helper in `risk_taxonomy_transformer/utils.py`; call sites in `risk_taxonomy_transformer/__main__.py` (≈10 sites, lines 89–168, 533, 555, 573, 631, 651, 672, 686, 700, 727, 834, 853), `export_html_report.py:199–203` and `:5800`, `ore_mapper.py:177`, `prsa_mapper.py:120`, `rap_mapper.py:107`, `build_prsa_frankenstein.py:165–182`, `consolidate_ore_irm.py:133–141`, `export_llm_prompts.py`, `consolidate_llm_responses.py`.
- **Approach:** one helper `latest_input(dir, patterns)` that parses the trailing timestamp from the filename (pipeline outputs use `%m%d%Y%I%M%p`; upstream exports vary, so fall back to mtime when unparsable), logs which file was chosen and by which rule, and warns when filename order and mtime order disagree. Replace all call sites.
- **Verify:** unit tests on the helper (parsable names, unparsable names, ties, disagreement warning); then a full `python refresh.py` on the current input set confirming the log shows the same files selected as before.

**1.2 Keyword Hits residual leak [Track 1]** — *high impact, low risk*
- **Files:** `risk_taxonomy_transformer/review_builders.py:153–174` (`_parse_keyword_hits`); stale comment in `scripts/compare_keyword_runs.py:460–462`.
- **Approach:** when the dedup at `mapping.py:243/259` produces evidence that is *only* `"Finding detail: ..."` (no keyword evidence), `_parse_keyword_hits` extracts the finding prose after `": "` into the Keyword Hits cell. Add a guard skipping parts that start with `Finding detail:`. Update the now-stale comment in `compare_keyword_runs.py`.
- **Verify:** full run before/after; diff the Keyword Hits column — only polluted cells may change, and they become blank. Keep the diff as Track 1 evidence.

**1.3 Deterministic run-to-run output** — *medium impact, low risk*
- **Files:** `risk_taxonomy_transformer/ingestion.py:52–53` (legacy dedup sorted by report date only), `risk_taxonomy_transformer/review_builders.py:298` (sibling sort by rating only).
- **Approach:** add stable secondary sort keys (entity ID; L2 name).
- **Verify:** run the pipeline twice on the synthetic fixture set; assert the two workbooks are value-identical. (This determinism check becomes a permanent test in 2.3.)

**1.4 Startup validation for hardcoded L2-keyed maps** — *medium impact, low risk*
- **Files:** `risk_taxonomy_transformer/flags.py:30–36`, `review_builders.py:81–105`, `optro.py:33–40`, validation hook in `config.py`.
- **Approach:** the L2-rename procedure assumes renames are a YAML-only change; these maps silently stop matching after a rename. Either move the maps into `taxonomy_config.yaml` or (lower-risk first step) add a startup check in `config.py` that every key in these maps exists in `L2_TO_L1`, failing loudly otherwise. Same treatment for `enrichment.py:48–75` terminology vs the config dict.
- **Verify:** rename an L2 in a scratch config copy → startup error names the offending map; normal run → byte-identical output.

**1.5 Stop swallowing inventory read errors** — *low impact, trivial risk*
- **Files:** `export_html_report.py:208–209` (`_load_inventory`).
- **Approach:** log the exception and filename at WARNING before returning the empty frame.
- **Verify:** point it at a corrupt file, confirm the log line; normal run output unchanged.

### Tier 2 — Test gaps

**2.1 Pytest scaffolding and one command to run everything** — *prerequisite for the rest*
- **Files:** new `pytest.ini` (or `pyproject.toml`) at root, `tests/conftest.py`; convert `tests/test_prsa_provenance.py` from a manual exit-code script to pytest (fixture generation moves into a fixture function, as `test_ore_irm_consolidate.py` already does).
- **Verify:** `python -m pytest tests/ -q` is green from a clean checkout plus generated fixtures; document the command in CLAUDE.md (done) and `docs/Validation.md`.

**2.2 Unit tests for the pure decision-path functions** — *highest value per line of test code*
- **Targets, in order:**
  - `normalization.normalize_l2_name` — prefix stripping, YAML aliases, unmappable list, exact match (protects the TODO.md alias backlog work).
  - `mapping.deduplicate` — all 6 documented branches, including the evidence-merge cases from 1.2.
  - `review_builders._parse_keyword_hits` / `_parse_key_risk_ids` — including the new `Finding detail:` guard.
  - `ingestion._derive_irm_ore_status` / `_derive_irm_ore_statuses` — cancelled short-circuit, consolidated-flag gate, all-impacts-done roll-up.
  - `rating.py` rationale/dimension parsing and rating conversion.
  - `enrichment.derive_inherent_risk_rating` matrix.
  - the new `latest_input` helper from 1.1.
- **Verify:** tests green; each test file imports only the module under test (no pipeline run needed).

**2.3 Values-only golden regression for Track 2 changes** — *gives "regression required" real teeth*
- **Files:** new `tests/test_golden_regression.py`; uses `tests/generate_test_data.py` (+ source generators) fixtures.
- **Approach:** generate the synthetic input set, run the pipeline, snapshot the key tabs (Audit_Review, Side_by_Side, decision columns) as CSV under `tests/golden/`, and compare values (not formatting) on subsequent runs. Include the run-twice determinism assertion from 1.3. Regenerating the golden snapshot is an explicit, reviewed action.
- **Verify:** the harness passes on main, fails when a decision value is deliberately perturbed.
- **Sequencing note:** land 2.3 *before* Tier 3 refactors — it is the safety net that verifies them.

### Tier 3 — Refactors (approved 2026-06-12)

**3.1 Consolidate the three mappers into a shared module** — *~800-line reduction; do after 2.3*
- **Files:** new `mapper_common.py` (or `risk_taxonomy_transformer/mapper_common.py`); `ore_mapper.py`, `prsa_mapper.py`, `rap_mapper.py` shrink to source-specific loading + config binding.
- **Approach:** extract the four near-identical pipeline functions (`build_reference_vectors`, `compute_mappings`, `determine_ambiguity_threshold`, `classify_mappings`) and the Excel export/styling/orphans-sidecar helpers. Keep per-mapper config blocks in YAML untouched. Reconcile the three config-loading styles (ore's `set_active_source` dynamic binding vs prsa/rap flat globals) toward the ore pattern.
- **Verify:** run each mapper on the same inputs before and after; outputs must be value-identical sheet-by-sheet (spaCy is deterministic with the pinned model). Run on both synthetic fixtures and the latest real inputs.

**3.2 Split `export_html_report.py`** — *do in two phases, after 2.3*
- **Files:** `export_html_report.py` → `templates/report.css`, `templates/report.js`, and a thinner Python module (optionally a small package for per-tab data builders).
- **Approach:** Phase A (low risk): move `_CSS` (lines 433–1301) and `_JS` (lines 1419–5384) verbatim into sibling files read at generation time; the `__PLACEHOLDER__` `.replace()` substitution mechanism stays exactly as is (it was chosen to avoid brace-escaping and that reasoning still holds). Phase B: break `generate_html_report` (lines 5385–5789) into per-source data-builder functions. The generated HTML remains one self-contained artifact.
- **Verify:** Phase A must produce a **byte-identical** HTML file from the same workbook (modulo nothing — the strings are moved verbatim). Phase B compared the same way. Riskiest seams to leave alone: the banner header-row offset logic (`header=1` for `_BANNER_SOURCE_TABS`, line 5407), the `PG Gap`→`Is PG Gap` rename (5419–5421), and the mixed-grain `Source - OREs` handling in JS (dedupe by Event ID convention).

**3.3 Move tuneable thresholds and positional config reads into YAML** — *small*
- **Files:** the margin floor/cap/quantile in all three mappers (e.g., `ore_mapper.py:434–455`); `consolidate_ore_irm.py:238–250` positional `C["risk_cols"][1]`-style reads → named keys.
- **Approach:** add keys to `taxonomy_config.yaml` with the current values as defaults so output is unchanged. Flag in PROJECT_DECISIONS.md that these join the three already-tracked unratified thresholds.
- **Verify:** value-identical mapper outputs; golden regression green.

**3.4 Retire the dead monolith** — *zero risk*
- **Files:** `risk_taxonomy_transformer_original.py` (unreferenced, already gitignored) → move into `archive/`.
- **Verify:** grep shows no imports of it (already confirmed); pipeline runs.

### Tier 4 — Performance

No user-visible performance problem exists at current scale (~450 entities / ~10k decisions); nothing here should be done unless runtime becomes a complaint. For the record: mapper runtime is dominated by spaCy doc vectorization (reference vectors are rebuilt for the ore and ore_irm runs and could be cached); `__main__.py:764` iterates `prsa_df` row-by-row for Track B and `export_html_report.py` builds `key_inventory_dict` via `iterrows` — all fine at this data volume.

### Tier 5 — Nice-to-haves

- **5.1 Declare missing dependencies:** `numpy` (used directly by mappers) pinned in `requirements.txt`; `python-pptx`/`lxml` either added or the presentation builders moved to `archive/` with a note. Verify: fresh venv installs and runs `refresh.py`.
- **5.2 Refresh stale reference docs: DONE 2026-06-12.** The nine `config/*.md` files were swept: `data_flow.md` relocated to `docs/reference/` and refreshed (ORE IRM, Optro, PG team inputs, orphans, inventories added); the other eight (`methodology_reference.md`, `decision_tree.md`, three completed dev prompts, three stale May-2 training/walkthrough docs) retired to `archive/superseded_docs/` along with `AUDIT_INPUTS_DATAFLOW.md`. Governed-doc pointers updated (`docs/Methodology.md`, `docs/Validation.md`, `docs/README.md`).
- **5.3 Harden `</script>` injection seams:** pandas `to_json` escapes `/` so the `_safe_json` paths are safe, but the `json.dumps(...)` substitutions (banners, entity names, methodology rows) would break the script tag if a value ever contained `</script>`. A shared `_js_json()` wrapper that replaces `</` with `<\/` closes it. Verify: byte-identical HTML on current data.
- **5.4 Root-directory hygiene:** ~20 untracked working `.md` files, one-off slide builders, `GPTExploration/`, `.codex/`, `graphify-out/` sit at root. Decide keep/track/archive per file. No code risk; do opportunistically.
- **5.5 TODO.md alias backlog:** the existing scope item (~50 aliases into the YAML alias map, confirm drop count <10) is protected by the new `normalize_l2_name` tests from 2.2.

---

## Suggested sequencing

1. Tier 1 fixes (1.1–1.5) — small, independent, each verifiable in isolation.
2. Tier 2 (2.1 → 2.2 → 2.3) — the golden harness is the gate for everything after it.
3. Tier 3 refactors (3.4 anytime; 3.1, 3.2, 3.3 only after 2.3 is green).
4. Tiers 4–5 opportunistically.
