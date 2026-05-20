"""Mode detection tests."""

from __future__ import annotations

from pathlib import Path

from dotagent.canonical_structure import CURRENT_SCHEMA_VERSION
from dotagent.migration.detector import Mode, detect_mode


def test_fresh_when_neither_git_nor_agent(tmp_path: Path):
    assert detect_mode(tmp_path) is Mode.FRESH


def test_mid_project_when_git_but_no_agent(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    assert detect_mode(tmp_path) is Mode.MID_PROJECT


def test_pre_v0_4_when_agent_but_no_version(tmp_path: Path):
    (tmp_path / ".agent").mkdir()
    assert detect_mode(tmp_path) is Mode.PRE_V0_4


def test_pre_v0_4_when_version_file_empty(tmp_path: Path):
    (tmp_path / ".agent").mkdir()
    (tmp_path / ".agent" / ".version").write_text("\n")
    assert detect_mode(tmp_path) is Mode.PRE_V0_4


def test_current_when_version_matches(tmp_path: Path):
    (tmp_path / ".agent").mkdir()
    (tmp_path / ".agent" / ".version").write_text(CURRENT_SCHEMA_VERSION)
    assert detect_mode(tmp_path) is Mode.CURRENT


def test_upgrade_when_version_older(tmp_path: Path):
    (tmp_path / ".agent").mkdir()
    (tmp_path / ".agent" / ".version").write_text("0.3.0")
    assert detect_mode(tmp_path) is Mode.UPGRADE


def test_current_when_version_newer(tmp_path: Path):
    # Future version → treated as CURRENT (don't downgrade).
    (tmp_path / ".agent").mkdir()
    (tmp_path / ".agent" / ".version").write_text("9.9.9")
    assert detect_mode(tmp_path) is Mode.CURRENT
