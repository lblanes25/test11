"""Unit tests for utils.latest_input (filename-timestamp-first file selection).

Uses tmp_path; mtimes are set explicitly with os.utime so the
filename-timestamp rule can be tested against a deliberately conflicting
mtime order.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from risk_taxonomy_transformer.utils import latest_input


def _make(directory: Path, name: str, mtime_offset: float) -> Path:
    f = directory / name
    f.write_text("x")
    t = time.time() + mtime_offset
    os.utime(f, (t, t))
    return f


def test_all_parseable_filename_timestamp_beats_mtime(tmp_path):
    # Newest filename timestamp gets the OLDEST mtime — filename must win.
    newest_by_name = _make(tmp_path, "legacy_risk_data_061020260900AM.xlsx", -300)
    _make(tmp_path, "legacy_risk_data_060920260900AM.xlsx", -100)
    _make(tmp_path, "legacy_risk_data_060120260900AM.xlsx", 0)

    got = latest_input(tmp_path, ["legacy_risk_data_*.xlsx"])
    assert got == newest_by_name


def test_pm_timestamp_later_than_am(tmp_path):
    pm = _make(tmp_path, "findings_data_061020260200PM.xlsx", -300)
    _make(tmp_path, "findings_data_061020261100AM.xlsx", 0)
    got = latest_input(tmp_path, ["findings_data_*.xlsx"])
    assert got == pm


def test_mixed_set_falls_back_to_mtime(tmp_path):
    # One unparsable stem poisons the set: the whole selection is by mtime.
    _make(tmp_path, "prsa_report_061020260900AM.xlsx", -100)
    dummy = _make(tmp_path, "prsa_report_test_dummy.xlsx", 0)
    got = latest_input(tmp_path, ["prsa_report_*.xlsx"])
    assert got == dummy


def test_orphan_sidecars_excluded_by_default(tmp_path):
    real = _make(tmp_path, "prsa_report_061020260900AM.xlsx", -100)
    _make(tmp_path, "prsa_report_061020260900AM_orphans.xlsx", 0)
    got = latest_input(tmp_path, ["prsa_report_*.xlsx"])
    assert got == real


def test_orphan_exclusion_can_be_disabled(tmp_path):
    _make(tmp_path, "prsa_report_061020260900AM.xlsx", -100)
    orphans = _make(tmp_path, "prsa_report_061020260900AM_orphans.xlsx", 0)
    got = latest_input(tmp_path, ["prsa_report_*.xlsx"], exclude_orphans=False)
    # Orphan stem ends in "_orphans" (no trailing timestamp) -> mixed set ->
    # mtime fallback picks the newer orphan file.
    assert got == orphans


def test_no_matches_returns_none(tmp_path):
    assert latest_input(tmp_path, ["does_not_exist_*.xlsx"]) is None


def test_only_orphans_returns_none(tmp_path):
    _make(tmp_path, "prsa_report_061020260900AM_orphans.xlsx", 0)
    assert latest_input(tmp_path, ["prsa_report_*.xlsx"]) is None


def test_multiple_patterns_deduplicated(tmp_path):
    f = _make(tmp_path, "key_risks_061020260900AM.xlsx", 0)
    got = latest_input(
        tmp_path, ["key_risks_*.xlsx", "key_risks_0610*.xlsx"])
    assert got == f


def test_disagreement_logs_warning(tmp_path, caplog):
    _make(tmp_path, "legacy_risk_data_061020260900AM.xlsx", -300)
    _make(tmp_path, "legacy_risk_data_060120260900AM.xlsx", 0)
    with caplog.at_level("WARNING", logger="risk_taxonomy_transformer.utils"):
        latest_input(tmp_path, ["legacy_risk_data_*.xlsx"])
    assert any("Latest-file rules disagree" in r.message for r in caplog.records)
