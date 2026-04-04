# Risk Taxonomy Transformer — Refactoring Prompt

You are refactoring `risk_taxonomy_transformer.py` (~3,900 lines, single file) into a clean, testable, modular codebase. The code works correctly today — the goal is structural improvement with zero behavior change. Every refactored version must produce byte-identical output given the same inputs.

Below are the changes, grouped into phases. Complete each phase fully before moving to the next. After each phase, confirm that the public API of `main()` is preserved and all inter-module imports resolve.

---

## Phase 1: Extract Constants and Kill Magic Strings

### 1A — Status enum
Create `constants.py`. Define a `Status` str enum (or string constants namespace) for:
- `APPLICABLE = "Applicable"`
- `NOT_APPLICABLE = "Not Applicable"`
- `NO_EVIDENCE = "No Evidence Found — Verify N/A"`
- `UNDETERMINED = "Applicability Undetermined"`
- `NOT_ASSESSED = "Not Assessed"`
- `NEEDS_REVIEW = "Needs Review"`

Replace all ~40+ bare string occurrences across `_derive_status`, `_derive_decision_basis`, `build_audit_review_df`, `_compute_priority_score`, `build_risk_owner_review_df`, `build_ro_summary_df`, and `export_results`.

### 1B — Method constants
In the same `constants.py`, define a `Method` namespace:
- `ISSUE_CONFIRMED = "issue_confirmed"`
- `EVALUATED_NO_EVIDENCE = "evaluated_no_evidence"`
- `NO_EVIDENCE_ALL_CANDIDATES = "no_evidence_all_candidates"`
- `TRUE_GAP_FILL = "true_gap_fill"`
- `SOURCE_NOT_APPLICABLE = "source_not_applicable"`
- `LLM_OVERRIDE = "llm_override"`
- `LLM_CONFIRMED_NA = "llm_confirmed_na"`
- `DIRECT = "direct"`
- `EVIDENCE_MATCH = "evidence_match"`

Replace all bare method strings. Update `BLANK_METHODS` to reference these constants. Note: `_derive_status` and `_derive_decision_basis` use substring matching (`"direct" in method`), so ensure the constants work with that pattern or refactor to use `method.startswith()` where appropriate.

### 1C — Empty sentinel set
Define `EMPTY_SENTINELS = {"", "nan", "none", "nat"}` in `constants.py`. Replace the ~12 scattered variations of NaN-checking (`val.lower() in ("nan", "none", "")`, `val.lower() not in ("", "nan", "none")`, etc.) with a shared helper:

```python
def is_empty(val) -> bool:
    """Return True if val is None, NaN, or a sentinel string."""
    if val is None:
        return True
    if isinstance(val, float) and pd.isna(val):
        return True
    return str(val).strip().lower() in EMPTY_SENTINELS
```

Refactor `_clean_str` to use this helper. Replace inline checks everywhere.

### 1D — Delete the redundant import
Line 599 has `import re as _re` inside `normalize_l2_name`. The module already imports `re` at line 26. Remove the inner import and use `re` directly.

---

## Phase 2: Extract Shared Utilities

### 2A — Unified file reader
The pattern `if filepath.endswith(".csv"): pd.read_csv(filepath) else: pd.read_excel(filepath)` appears in 8+ functions. Extract into `utils.py`:

```python
def read_tabular_file(filepath: str, **kwargs) -> pd.DataFrame:
    """Read CSV or Excel file based on extension. Normalizes column names."""
    path = str(filepath)
    if path.endswith(".csv"):
        df = pd.read_csv(path, **kwargs)
    else:
        df = pd.read_excel(path, **kwargs)
    df.columns = [str(c).strip() for c in df.columns]
    return df
```

Replace all 8 call sites: `ingest_legacy_data`, `ingest_sub_risks`, `load_overrides`, `ingest_findings`, `ingest_enterprise_findings`, `ingest_rco_overrides`, `_enrich_findings_source`, `_enrich_sub_risks_source`. Include basic error handling (catch `FileNotFoundError`, `pd.errors.EmptyDataError`) with a clear log message.

### 2B — Date formatter
`_format_date_month_year` is a pure utility. Move to `utils.py`.

### 2C — Item listing formatter
`_format_item_listings` is a pure formatting utility. Move to `utils.py`.

---

## Phase 3: Decouple Configuration from Module Import

### 3A — Lazy config loading
Currently `_CFG = _load_config()` runs at import time, which means importing any function triggers file I/O and can raise. Refactor so that:
1. `_load_config()` remains available but is not called at module level.
2. Config is loaded once on first access via a module-level `get_config()` function or a simple lazy wrapper.
3. All downstream consumers (`CROSSWALK_CONFIG`, `KEYWORD_MAP`, `L2_TO_L1`, `RISK_RATING_MAP`, etc.) are accessed through the config object or a thin accessor, not as bare module globals.
4. `_apply_column_config` no longer mutates globals `_APP_COLS` and `_AUX_COLS`. Instead, pass column config through `TransformContext` or return them from the config loader.

This is the hardest single change. Take care to preserve the existing behavior where config values are used as module-level names (e.g., `CROSSWALK_CONFIG`, `KEYWORD_MAP`). A reasonable intermediate step is to keep the module-level names but populate them inside a `_init_config()` that `main()` calls explicitly, with a guard so tests can call it with a test config.

### 3B — Externalize methodology content
The ~190 lines of `methodology_data` inside `export_results` are static content. Move them to a separate file: either `methodology.yaml`, `methodology.json`, or a `_build_methodology_data()` function in a `methodology.py` module. The content is maintained by non-developers, so a data file format is preferred over Python code.

---

## Phase 4: Split the God Module

Decompose `risk_taxonomy_transformer.py` along the natural seams already marked by section comments. Target structure:

```
risk_taxonomy_transformer/
├── __init__.py              # Public API re-exports
├── constants.py             # Phase 1 output
├── utils.py                 # Phase 2 output
├── config.py                # Phase 3A output — config loading and accessors
├── ingestion.py             # SECTION 2: all ingest_* and build_*_index functions
├── normalization.py         # L2 name normalization, aliases, prefix stripping
├── rating.py                # SECTION 3: convert_risk_rating, convert_control_rating,
│                            #   parse_rationale_for_dimensions, _make_row
├── mapping.py               # SECTION 4: _resolve_multi_mapping,
│                            #   _deduplicate_transformed_rows, transform_entity
├── pipeline.py              # run_pipeline, apply_overlay_flags
├── flags.py                 # flag_control_contradictions, flag_application_applicability,
│                            #   flag_auxiliary_risks, flag_cross_boundary_signals
├── enrichment.py            # derive_inherent_risk_rating, derive_control_effectiveness,
│                            #   _derive_status, _derive_decision_basis
├── review_builders.py       # build_audit_review_df, build_review_queue_df,
│                            #   build_risk_owner_review_df, build_ro_summary_df
├── export.py                # export_results (data assembly only — calls formatting)
├── formatting.py            # All openpyxl styling: style_header, _find_header_column,
│                            #   _color_rows_by_column, sheet-specific formatting functions
├── methodology.py           # or methodology.yaml — Phase 3B output
└── __main__.py              # main() entrypoint
```

Rules for the split:
- Each module should be importable independently without triggering file I/O (Phase 3A makes this possible).
- `TransformContext` stays in `config.py` or `__init__.py` — it's the shared data object.
- Cross-module imports should flow downward: `__main__` → `pipeline`/`export` → `mapping`/`flags`/`enrichment` → `ingestion`/`rating`/`normalization` → `constants`/`utils`. No circular imports.
- `_make_row` goes in `rating.py` since it's the row factory used by the mapping engine.

---

## Phase 5: Extract Functions (Targeted)

These are the specific extraction calls from the review. Do them during or after the module split, placing each extracted function in the appropriate new module.

### In `mapping.py`
- Extract the findings pre-check loop (original lines 974–996) into `_create_findings_confirmed_rows(entity_id, findings_index) -> list[dict]`.
- Extract rationale dimension parsing + impact fallback (original lines 1043–1058) into `_resolve_rating_dimensions(rating_numeric, parsed_dims) -> dict`.
- Add a block comment at the top of the `else` branch in `_deduplicate_transformed_rows` explaining the 6-branch dedup logic: which source wins in each case and why.

### In `flags.py`
- In `flag_application_applicability`: replace the 4 `elif` branches producing near-identical strings with a dict lookup:
  ```python
  _APP_COL_LABELS = {
      "primary_it": "Primary application mapped to entity",
      "secondary_it": "Secondary application related to entity",
      "primary_tp": "Primary third party engagement mapped to entity",
      "secondary_tp": "Secondary third party engagement related to entity",
  }
  ```
- In `flag_cross_boundary_signals`: extract lines that format signals into plain-language flags into `_format_cross_boundary_flags(pillar_signals: dict) -> str`.
- In `flag_application_applicability`: extract the set comprehension in the logger call into a named variable `entities_with_apps`.

### In `enrichment.py`
- In `derive_control_effectiveness`: extract the baseline string construction into `_format_baseline(audit_info, baseline_map) -> str`.
- Add a comment in `_derive_decision_basis` before the substring matching block: `# Order matters: check specific method substrings before generic ones`.

### In `review_builders.py`
- Promote `_split_signals` (defined inside `build_audit_review_df`) to a module-level function so it's testable.
- Promote `_row_sort_key` (defined inside `build_audit_review_df`) to a module-level function.
- In `build_risk_owner_review_df`: extract sibling context computation (~60 lines) into `_compute_sibling_context(entity_id, l2, entity_l2_lookup, status) -> tuple[str, str]`.
- In `build_risk_owner_review_df`: extract business line comparison into `_format_business_line_comparison(bl, l2, peer_ratings, status, rating) -> str`.

### In `export.py`
- Extract Audit_Review sheet formatting into `_format_audit_review_sheet(ws, status_fills)`.
- Extract Risk_Owner_Review formatting into `_format_risk_owner_review_sheet(ws, status_fills)`.
- Extract Risk_Owner_Summary formatting into `_format_risk_owner_summary_sheet(ws)`.
- Extract Dashboard tab construction into `_build_dashboard_sheet(wb, ar_ws)`.

### In `__main__.py`
- Extract file discovery + column config resolution (original lines 3657–3770) into `_resolve_input_paths_and_columns(input_dir, output_dir, col_cfg) -> dict`.

---

## Phase 6: Performance and Robustness

### 6A — Replace `iterrows()` in flag functions
`flag_application_applicability`, `flag_auxiliary_risks`, `flag_cross_boundary_signals`, and `flag_control_contradictions` all iterate with `iterrows()`. Convert the entity metadata lookups to dict-based joins or vectorized operations. At minimum, replace `iterrows()` with `to_dict('records')` for the inner loops.

### 6B — Error handling on file reads
Wrap the `read_tabular_file` calls in `ingestion.py` with try/except for `FileNotFoundError`, `PermissionError`, and `pd.errors.EmptyDataError`. Log a clear message naming the file and the expected format, then re-raise.

### 6C — Guard against missing columns
Several ingestion functions assume columns exist after rename. Add explicit checks:
```python
missing = [c for c in required_cols if c not in df.columns]
if missing:
    raise ValueError(f"{filepath} missing required columns: {missing}. Available: {list(df.columns)}")
```

---

## General Rules

- **No behavior changes.** Every refactoring step must preserve identical output. If you're unsure whether a change alters behavior, don't make it.
- **Preserve logging.** All existing `logger.info` and `logger.warning` calls must remain with the same messages and levels.
- **Preserve the public API.** `main()` must remain callable with no arguments. `run_pipeline`, `transform_entity`, `export_results`, and all `build_*_df` functions must keep their existing signatures (add new optional parameters only if needed).
- **One phase at a time.** Don't start Phase 4 until Phases 1–3 are complete and the single-file version passes.
- **Add docstrings to every new module** explaining its role in the pipeline.
