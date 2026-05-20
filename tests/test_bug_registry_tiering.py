"""Bug registry tiering, prefix declaration, and cross-reference extraction."""

from __future__ import annotations

from pathlib import Path

from dotagent.config import Config, DEFAULT_CONFIG
from dotagent.doctor import _check_bug_id_prefix
from dotagent.paths import Paths
from dotagent.sources import (
    _parse_bug_registry,
    _prefix_of,
    extract_cross_references,
)


def test_extract_cross_references_finds_other_prefix_ids():
    body = (
        "## Some title\n"
        "Steps to reproduce: see AGT-0042 for project-level context.\n"
        "Also related: PORTAL-0089."
    )
    refs = extract_cross_references(body, self_prefix="BE")
    assert "AGT-0042" in refs
    assert "PORTAL-0089" in refs


def test_extract_cross_references_filters_self_prefix():
    body = "References BE-0001 (self) and AGT-0042 (other)."
    refs = extract_cross_references(body, self_prefix="BE")
    assert refs == ["AGT-0042"]


def test_extract_cross_references_dedupes():
    body = "See AGT-0042. Also AGT-0042 again."
    refs = extract_cross_references(body, self_prefix="BE")
    assert refs == ["AGT-0042"]


def test_extract_cross_references_handles_no_refs():
    body = "No bug references in this text."
    refs = extract_cross_references(body, self_prefix="BE")
    assert refs == []


def test_extract_cross_references_ignores_lowercase():
    body = "Mentions agt-0042 (lowercase, not a real ref)."
    refs = extract_cross_references(body, self_prefix="BE")
    assert refs == []


def test_prefix_of_extracts_clean_prefix():
    assert _prefix_of("BE-0042") == "BE"
    assert _prefix_of("AGT-0001") == "AGT"
    assert _prefix_of("PORTAL-0089") == "PORTAL"


def test_prefix_of_returns_empty_for_no_prefix():
    assert _prefix_of("") == ""
    assert _prefix_of("0042") == ""
    assert _prefix_of("lowercase-007") == ""


def test_parse_bug_registry_populates_cross_references():
    text = (
        "## BE-0123 · Auth manifests as 401-loop in /chat\n"
        "- status: open\n\n"
        "Cross-reference: see AGT-0042 (Project Root).\n"
    )
    entries = _parse_bug_registry(text)
    assert len(entries) == 1
    assert entries[0].id == "BE-0123"
    assert entries[0].cross_references == ["AGT-0042"]


def test_doctor_warns_when_prefix_undeclared(tmp_path: Path):
    (tmp_path / ".agent").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "bug-registry.md").write_text(
        "## BE-0001 · Auth bug\n- status: open\n"
    )
    paths = Paths(repo=tmp_path)
    cfg = Config(raw=dict(DEFAULT_CONFIG))
    cfg.raw["bugs"] = {"id_prefix": "", "cross_reference_prefixes": []}

    diag = _check_bug_id_prefix(paths, cfg)
    assert diag.status == "warn"
    assert "BE" in diag.message
    assert diag.fix


def test_doctor_ok_when_prefix_matches(tmp_path: Path):
    (tmp_path / ".agent").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "bug-registry.md").write_text(
        "## BE-0001 · Auth bug\n- status: open\n"
    )
    paths = Paths(repo=tmp_path)
    cfg = Config(raw=dict(DEFAULT_CONFIG))
    cfg.raw["bugs"] = {"id_prefix": "BE", "cross_reference_prefixes": []}

    diag = _check_bug_id_prefix(paths, cfg)
    assert diag.status == "ok"


def test_doctor_warns_when_prefix_mismatch(tmp_path: Path):
    (tmp_path / ".agent").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "bug-registry.md").write_text(
        "## BE-0001 · Auth bug\n- status: open\n"
    )
    paths = Paths(repo=tmp_path)
    cfg = Config(raw=dict(DEFAULT_CONFIG))
    cfg.raw["bugs"] = {"id_prefix": "PORTAL", "cross_reference_prefixes": []}

    diag = _check_bug_id_prefix(paths, cfg)
    assert diag.status == "warn"
    assert "PORTAL" in diag.message
    assert "BE" in diag.message


def test_doctor_info_when_no_bug_registry(tmp_path: Path):
    (tmp_path / ".agent").mkdir()
    paths = Paths(repo=tmp_path)
    cfg = Config(raw=dict(DEFAULT_CONFIG))

    diag = _check_bug_id_prefix(paths, cfg)
    assert diag.status == "info"


def test_default_config_includes_bugs_section():
    assert "bugs" in DEFAULT_CONFIG
    assert DEFAULT_CONFIG["bugs"].get("id_prefix") == ""
    assert DEFAULT_CONFIG["bugs"].get("cross_reference_prefixes") == []
