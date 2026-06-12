"""Full-pipeline golden regression and determinism tests.

Marked `golden` and deselected by default (see pytest.ini). Run with:

    python -m pytest tests/test_golden_regression.py -m golden

The module fixture regenerates the synthetic input set in data/input/ (the
established fixture pattern), then runs `python refresh.py --skip-validate`
twice, capturing each run's transformed_risk_taxonomy_*.xlsx output.

Test 1 (determinism): the two workbooks must be value-identical across all
sheets, excluding known-volatile cells (run timestamps and timestamped
source-file names — see _is_volatile_pair).

Test 2 (golden snapshot): run 1's Audit_Review and Side_by_Side sheets
(values only, as strings, NaN -> "", volatile cells masked) must match the
committed CSVs in tests/golden/. Regenerate deliberately with:

    python -m pytest tests/test_golden_regression.py -m golden --regen-golden
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import pytest

pytestmark = pytest.mark.golden

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_INPUT_DIR = _PROJECT_ROOT / "data" / "input"
_OUTPUT_DIR = _PROJECT_ROOT / "data" / "output"
_GOLDEN_DIR = _PROJECT_ROOT / "tests" / "golden"
_VENV_PYTHON = _PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"

sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))

from diff_workbooks import _norm  # scripts/diff_workbooks.py

# Generators for every synthetic input refresh.py consumes. Order matters:
# generate_test_data imports from generate_prsa_source_test_data.
_GENERATORS = [
    "generate_prsa_source_test_data.py",   # PRSA_IRM_Archer / PRSA_Controls_Map / golden prsa_report
    "generate_test_data.py",               # legacy_risk_data / key_risks / findings_data
    "generate_ore_test_data.py",           # ORE_test_dummy
    "generate_ore_irm_raw_test_data.py",   # IRM_ORE_raw (consolidated by refresh)
    "generate_ore_irm_test_data.py",       # ORE_IRM_test_dummy
    "generate_bma_test_data.py",           # bm_activities_test_dummy
    "generate_pg_team_inputs_test_data.py",  # project_guardian_aera_inputs_test_dummy
    "generate_applications_test_data.py",  # all_applications_test_dummy
    "generate_thirdparties_test_data.py",  # all_thirdparties_test_dummy
    "generate_models_test_data.py",        # model_inventory_test_dummy
    "generate_policies_test_data.py",      # policystandardprocedure_test_dummy
    "generate_laws_test_data.py",          # lawsandapplicability_test_dummy
]

# Fixtures with no generator — must already exist in data/input/.
_REQUIRED_EXISTING = ["gra_raps_test.xlsx", "L2_Risk_Taxonomy.xlsx"]

_GOLDEN_SHEETS = ["Audit_Review", "Side_by_Side"]

_REGEN_HINT = (
    "Regenerate the golden snapshots deliberately (this is a reviewed action) "
    "via: python -m pytest tests/test_golden_regression.py -m golden --regen-golden"
)

# ---------------------------------------------------------------------------
# Volatile-cell handling
# ---------------------------------------------------------------------------

# Timestamped pipeline filenames (e.g. prsa_report_061220260630PM.xlsx,
# ORE_IRM_consolidated_..., ore_mapping_...) embedded as source-file
# references — e.g. the Upstream Tagging Gaps "Source File" column.
_TS_FILENAME_RE = re.compile(r"\b[\w\-]+_\d{12}[AP]M(?:_orphans)?\.(?:xlsx|csv)\b")
# Methodology "Run timestamp" value.
_RUN_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
# Dashboard "Generated: June 12, 2026 6:30 PM" banner cell.
_GENERATED_PREFIX = "Generated: "


def _is_volatile_pair(a: str, b: str) -> bool:
    """True when two differing cell values are a known-volatile pair."""
    if a.startswith(_GENERATED_PREFIX) and b.startswith(_GENERATED_PREFIX):
        return True
    if _RUN_TS_RE.match(a) and _RUN_TS_RE.match(b):
        return True
    if _TS_FILENAME_RE.search(a) and _TS_FILENAME_RE.search(b):
        # Same value modulo the embedded filename timestamp(s).
        return (_TS_FILENAME_RE.sub("<TS_FILE>", a)
                == _TS_FILENAME_RE.sub("<TS_FILE>", b))
    return False


def _mask_volatile(value: str) -> str:
    """Replace known-volatile content with stable tokens (golden snapshots)."""
    if value.startswith(_GENERATED_PREFIX):
        return "<GENERATED>"
    if _RUN_TS_RE.match(value):
        return "<RUN_TS>"
    return _TS_FILENAME_RE.sub("<TS_FILE>", value)


def _grid_as_strings(df: pd.DataFrame) -> pd.DataFrame:
    """Raw sheet grid -> all-string values (NaN -> ''), volatile cells masked."""
    return df.map(lambda v: _mask_volatile(_norm(v)))


# ---------------------------------------------------------------------------
# Pipeline run fixture
# ---------------------------------------------------------------------------

def _run(cmd: list[str], label: str, timeout: int = 1800) -> None:
    result = subprocess.run(
        cmd, cwd=str(_PROJECT_ROOT), capture_output=True, text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        pytest.fail(
            f"{label} failed (exit {result.returncode}):\n"
            f"--- stdout tail ---\n{result.stdout[-3000:]}\n"
            f"--- stderr tail ---\n{result.stderr[-3000:]}"
        )


def _newest_output_since(t0: float) -> Path:
    candidates = sorted(
        _OUTPUT_DIR.glob("transformed_risk_taxonomy_*.xlsx"),
        key=lambda f: f.stat().st_mtime,
    )
    assert candidates, "no transformed_risk_taxonomy_*.xlsx in data/output"
    newest = candidates[-1]
    assert newest.stat().st_mtime >= t0, (
        f"newest output {newest.name} predates this run — pipeline wrote nothing"
    )
    return newest


@pytest.fixture(scope="module")
def pipeline_runs(tmp_path_factory) -> tuple[Path, Path]:
    """Regenerate synthetic inputs and run refresh.py twice.

    Returns (run1_workbook, run2_workbook) as copies in a temp dir (run 2 can
    overwrite run 1's filename when both land in the same minute).
    """
    if not _VENV_PYTHON.exists():
        pytest.skip(f"venv python not found at {_VENV_PYTHON}")
    if not _INPUT_DIR.is_dir():
        pytest.skip(f"data/input not found at {_INPUT_DIR}")
    missing = [n for n in _REQUIRED_EXISTING if not (_INPUT_DIR / n).exists()]
    if missing:
        pytest.skip(f"required non-generated fixtures missing from data/input: {missing}")
    probe = subprocess.run(
        [str(_VENV_PYTHON), "-c", "import en_core_web_lg"],
        cwd=str(_PROJECT_ROOT), capture_output=True, text=True,
    )
    if probe.returncode != 0:
        pytest.skip("spaCy model en_core_web_lg not installed — mappers cannot run")

    for script in _GENERATORS:
        _run([str(_VENV_PYTHON), str(_PROJECT_ROOT / "tests" / script)],
             f"generator {script}", timeout=300)

    tmp = tmp_path_factory.mktemp("golden_runs")
    runs: list[Path] = []
    for i in (1, 2):
        t0 = time.time()
        _run([str(_VENV_PYTHON), str(_PROJECT_ROOT / "refresh.py"),
              "--skip-validate"], f"refresh.py run {i}")
        produced = _newest_output_since(t0)
        copy = tmp / f"run{i}.xlsx"
        shutil.copy2(produced, copy)
        runs.append(copy)
    return runs[0], runs[1]


def _load_book(path: Path) -> dict[str, pd.DataFrame]:
    return pd.read_excel(path, sheet_name=None, header=None)


# ---------------------------------------------------------------------------
# Test 1: run-to-run determinism
# ---------------------------------------------------------------------------

def test_run_to_run_determinism(pipeline_runs):
    book_a = _load_book(pipeline_runs[0])
    book_b = _load_book(pipeline_runs[1])

    assert set(book_a) == set(book_b), (
        f"sheet sets differ: only-run1={sorted(set(book_a) - set(book_b))}, "
        f"only-run2={sorted(set(book_b) - set(book_a))}"
    )

    problems: list[str] = []
    for sheet in book_a:
        a, b = book_a[sheet], book_b[sheet]
        if a.shape != b.shape:
            problems.append(f"[{sheet}] shape {a.shape} != {b.shape}")
            continue
        for c in range(a.shape[1]):
            av = a.iloc[:, c].map(_norm)
            bv = b.iloc[:, c].map(_norm)
            mask = av != bv
            for r in av.index[mask]:
                va, vb = av.loc[r], bv.loc[r]
                if _is_volatile_pair(va, vb):
                    continue
                problems.append(
                    f"[{sheet}] r{r} c{c}: {va[:80]!r} != {vb[:80]!r}"
                )
                if len(problems) > 40:
                    break
            if len(problems) > 40:
                break
        if len(problems) > 40:
            break

    assert not problems, (
        "run 1 and run 2 workbooks differ beyond known-volatile cells:\n"
        + "\n".join(problems)
    )


# ---------------------------------------------------------------------------
# Test 2: golden snapshot of the decision tabs
# ---------------------------------------------------------------------------

def test_golden_snapshot(pipeline_runs, request):
    regen = request.config.getoption("--regen-golden")
    book = _load_book(pipeline_runs[0])

    for sheet in _GOLDEN_SHEETS:
        assert sheet in book, f"sheet {sheet!r} missing from output workbook"

    if regen:
        _GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        for sheet in _GOLDEN_SHEETS:
            _grid_as_strings(book[sheet]).to_csv(
                _GOLDEN_DIR / f"{sheet}.csv", index=False, header=False,
            )
        return

    missing = [s for s in _GOLDEN_SHEETS
               if not (_GOLDEN_DIR / f"{s}.csv").exists()]
    if missing:
        pytest.fail(
            f"golden snapshot(s) missing from {_GOLDEN_DIR}: {missing}. "
            + _REGEN_HINT
        )

    problems: list[str] = []
    for sheet in _GOLDEN_SHEETS:
        current = _grid_as_strings(book[sheet])
        golden = pd.read_csv(
            _GOLDEN_DIR / f"{sheet}.csv", header=None, dtype=str,
            keep_default_na=False,
        )
        if current.shape != golden.shape:
            problems.append(
                f"[{sheet}] shape changed: golden {golden.shape} -> "
                f"current {current.shape}"
            )
            continue
        for c in range(current.shape[1]):
            cv = current.iloc[:, c].reset_index(drop=True)
            gv = golden.iloc[:, c].reset_index(drop=True)
            mask = cv != gv
            for r in cv.index[mask]:
                problems.append(
                    f"[{sheet}] r{r} c{c}: golden {gv.loc[r][:80]!r} -> "
                    f"current {cv.loc[r][:80]!r}"
                )
                if len(problems) > 40:
                    break
            if len(problems) > 40:
                break

    assert not problems, (
        "decision tabs diverged from the committed golden snapshot:\n"
        + "\n".join(problems)
        + f"\nIf this change is intended (Track 1/2 reviewed), {_REGEN_HINT}"
    )
