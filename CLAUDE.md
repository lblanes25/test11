# LUminate (risk_taxonomy_transformer)

Internal audit EUC that transforms a legacy 14-pillar risk taxonomy into the new AERA taxonomy (6 L1s / 24 risks, 23 L2s evaluated), producing a multi-tab Excel workbook plus a self-contained HTML dashboard. The tool's decisions are deterministic (crosswalk + findings evidence); NLP/LLM inputs are advisory only and always surface as "Needs Review", never as a confidence score.

Terminology: **AERA** is the assessment process; **Optro** is the system of record teams enter results into; **Archer** is the upstream extract source. The package directory is still `risk_taxonomy_transformer` even though the tool was renamed LUminate.

## Layout

```
risk_taxonomy_transformer/   The pipeline package. Imports flow one direction:
                             config/constants/normalization -> ingestion ->
                             mapping/pipeline -> enrichment/rating/flags/optro ->
                             review_builders/export/formatting. __main__.py orchestrates.
refresh.py                   One-button end-to-end run (validate -> build -> consolidate
                             -> mappers -> main pipeline). Start here.
validate_inputs.py           Input gate: file manifest + column headers vs YAML.
build_prsa_frankenstein.py   Joins three extracts into prsa_report_*.xlsx (hard
                             prerequisite for the PRSA mapper and main ingest).
consolidate_ore_irm.py       Collapses the stacked raw IRM ORE export to one row per ORE.
ore_mapper.py / prsa_mapper.py / rap_mapper.py
                             spaCy similarity mappers (ore_mapper also handles
                             --source ore_irm). Outputs land in data/output/.
export_html_report.py        Excel workbook -> single-file HTML dashboard. Also called
                             automatically at the end of the main pipeline.
export_llm_prompts.py        Batches undetermined items into LLM review prompts;
consolidate_llm_responses.py merges the responses into llm_overrides_*.csv.
config/taxonomy_config.yaml  THE config: taxonomy, crosswalk, keyword map, L2 aliases,
                             thresholds, and every data-source column mapping.
config/banners.yaml          HTML report disclaimer banners.
docs/                        Governed EUC docs (Methodology, Operations, Validation,
                             Governance, Crosswalk). One home per fact — see docs/README.md.
docs/reference/data_flow.md  Non-governed developer reference: per-source code-level
                             plumbing (where each input is read, filters, destinations).
                             Update it when adding/changing a data source.
.claude/agents/              project-manager, audit-leader, transformer-builder,
                             validation-qa. All four share a byte-identical
                             "Project Canon v1" block — edit all four together.
scripts/                     Read-only diagnostics (reuse pipeline ingestion; never
                             re-implement gate logic).
tests/                       Two test files + 13 generate_*_test_data.py fixture
                             generators (write synthetic inputs into data/input/).
data/input/, data/output/    Gitignored working data. Inputs are discovered by
                             glob pattern, most-recent file wins.
archive/                     Gitignored. Never stage or commit from it.
```

`risk_taxonomy_transformer_original.py` is the dead pre-refactor monolith (gitignored, unreferenced). Many root-level `.md` files are untracked working notes, not governed docs.

## Running

```
python refresh.py                  # full pipeline (validate gate halts on bad inputs)
python refresh.py --only prsa      # re-run one mapper (skips validate/build/consolidate)
python refresh.py --skip-build     # reuse existing prsa_report_*.xlsx
python -m risk_taxonomy_transformer   # main pipeline only
python export_html_report.py [workbook.xlsx]   # regenerate HTML from latest output
```

Mapper failures warn and continue; validation and Frankenstein-build failures halt. Outputs: `data/output/transformed_risk_taxonomy_<ts>.xlsx` + `risk_taxonomy_report_<ts>.html`. Logs: `logs/transform_log.txt`.

## Tests

```
python -m pytest tests/test_ore_irm_consolidate.py -q   # pytest; generates own fixtures
python tests/test_prsa_provenance.py                    # manual script (exit code 0/1);
                                                        # needs generate_prsa_source_test_data.py
                                                        # + build_prsa_frankenstein.py --test-dummy first
```

There is no pytest.ini/conftest.py yet (see IMPROVEMENT_PLAN.md Tier 2). For an end-to-end smoke run on synthetic data: `python tests/generate_test_data.py` (plus the per-source generators) then `python refresh.py`. The gating validation for decision-affecting changes is sample reconciliation, not unit tests — see docs/Validation.md.

## Conventions (enforced — violating these gets changes rejected)

- **All data-source column names live in `config/taxonomy_config.yaml`**, never hardcoded in Python.
- **L2 renames are a YAML-only change** (aliases in `l2_aliases`, validated at startup).
- **Change control has two tracks** (docs/Governance.md): Track 1 = anything that changes decision outputs → methodology sign-off + before/after reconciliation evidence; Track 2 = code/cosmetics → regression + code review. Refactors must produce value-identical output.
- **Canonical spaCy model is `en_core_web_lg` 3.8.0** (pinned in requirements.txt); provenance is stamped into every output. Never let it silently fall back to `md`.
- **No rationale-comment blocks in code** — don't write multi-line comments explaining design decisions; put constraints the code can't express in a short comment, decisions in docs/PROJECT_DECISIONS.md.
- **No speculative scaffolds** — don't pre-build ingestion for data formats that haven't arrived.
- **Copy conventions:** "L2 doesn't map to" (not "normalize"); "Audit / Management provided" (not "filer-provided"); Unmapped Findings is Excel-only.
- **Route substantive work through `.claude/agents/`** — project-manager scopes, transformer-builder is the only agent that writes code, validation-qa verifies, audit-leader reviews UX from the user's seat.
- **Check the existing renderer before proposing UX/formatting changes** — much already exists.

## Sharp edges

- **Latest-file selection is by mtime**, not filename timestamp — touching/copying an older export silently wins (fix planned: IMPROVEMENT_PLAN.md 1.1).
- **`Source - OREs` in the HTML report is mixed-grain** (exploded ORE×L2): dedupe by Event ID (Title|Desc fallback); never `resolveCol` on the mixed-schema oreData, use `oreRowEid`.
- **HTML template substitution uses `.replace("__PLACEHOLDER__", ...)`, not f-strings** — deliberate, so embedded JS/CSS braces need no escaping. Keep it that way.
- **Banner-bearing "Source - *" Excel tabs have their header on row 2** (row 1 is the banner); the HTML reader passes `header=1` for those sheets.
- **`Keyword Hits` can contain leaked finding prose** in one dedup scenario (fix approved: IMPROVEMENT_PLAN.md 1.2); consumers split on `\n` and vocab-filter.
- The mappers emit a uniform "Needs Review" band by design — do not add positive-confidence labels to NLP matches.
