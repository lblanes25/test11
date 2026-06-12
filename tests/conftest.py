"""Shared pytest fixtures and options for the LUminate test suite."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Make both the package and root-level scripts importable from any rootdir.
for _p in (str(PROJECT_ROOT), str(PROJECT_ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def pytest_addoption(parser):
    parser.addoption(
        "--regen-golden",
        action="store_true",
        default=False,
        help="Regenerate the tests/golden/ snapshot CSVs from the current "
             "pipeline run instead of comparing against them.",
    )


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Absolute path to the repository root."""
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def input_dir(project_root: Path) -> Path:
    """data/input directory (the established fixture-generation target)."""
    return project_root / "data" / "input"


@pytest.fixture(scope="session")
def output_dir(project_root: Path) -> Path:
    """data/output directory (pipeline workbook target)."""
    return project_root / "data" / "output"
