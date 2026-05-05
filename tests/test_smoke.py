from __future__ import annotations

from pathlib import Path

import dotagent
from dotagent.config import merge_defaults
from dotagent.discovery import discover
from dotagent.paths import Paths
from dotagent.scaffold import scaffold_agent_dir


def test_version():
    assert dotagent.__version__


def test_default_config_shape():
    cfg = merge_defaults({})
    assert "adapters" in cfg
    assert cfg["adapters"]["claude"] is True
    assert "dream" in cfg
    assert cfg["share"]["personal"] == "never"


def test_scaffold_creates_canonical_layout(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    written = scaffold_agent_dir(paths)
    assert written, "scaffold should write at least one file"
    assert (tmp_path / ".agent" / "style.md").exists()
    assert (tmp_path / ".agent" / "rules.md").exists()
    assert (tmp_path / ".agent" / "architecture.md").exists()
    assert (tmp_path / ".agent" / "patterns.md").exists()
    assert (tmp_path / ".agent" / "preferences.md").exists()
    assert (tmp_path / ".agent" / "skills" / "observer.md").exists()
    assert (tmp_path / ".agent" / "tools" / "git-proxy.md").exists()
    assert (tmp_path / ".agent" / "memory" / "episodic").is_dir()
    assert (tmp_path / ".agent" / "memory" / "semantic").is_dir()
    assert (tmp_path / ".agent" / "memory" / "personal").is_dir()
    assert (tmp_path / ".agent" / "dream" / "graduated").is_dir()


def test_scaffold_is_idempotent(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    first = scaffold_agent_dir(paths)
    second = scaffold_agent_dir(paths)
    assert second == [], "second scaffold should write nothing"
    assert len(first) > 0


def test_discover_empty_dir(tmp_path: Path):
    d = discover(tmp_path)
    assert d.repo == tmp_path
    assert isinstance(d.languages, list)
    assert d.has_claude_code_optimization is False
    assert d.existing_ai_configs == []
