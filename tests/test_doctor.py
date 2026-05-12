from __future__ import annotations

import os
from pathlib import Path

from dotagent.config import merge_defaults
from dotagent.doctor import (
    _check_agent_dir,
    _check_anthropic_key,
    _check_cache_gitignored,
    _check_episodic_index,
    _check_hooks,
    _check_python_version,
    _check_sources,
)
from dotagent.config import Config
from dotagent.paths import Paths
from dotagent.scaffold import scaffold_agent_dir
from dotagent.sources import reindex_all
from dotagent.util import dump_yaml


def test_python_version_check_passes_on_311_plus():
    d = _check_python_version()
    assert d.status == "ok"


def test_anthropic_key_check_reports_info_or_ok(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    d = _check_anthropic_key()
    assert d.status == "info"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    d = _check_anthropic_key()
    assert d.status == "ok"


def test_agent_dir_check_fails_when_uninitialized(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    d = _check_agent_dir(paths)
    assert d.status == "fail"
    assert "init" in d.fix


def test_agent_dir_check_passes_after_init(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    dump_yaml(paths.config, merge_defaults({}))
    d = _check_agent_dir(paths)
    assert d.status == "ok"


def test_sources_check_warns_when_no_docs(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    dump_yaml(paths.config, merge_defaults({}))
    cfg = Config.load(paths)
    d = _check_sources(paths, cfg)
    assert d.status == "warn"


def test_sources_check_ok_when_at_least_one_exists(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    dump_yaml(paths.config, merge_defaults({}))
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "bug-registry.md").write_text("# Bug Registry\n\n## BUG-1: x\n\nbody.\n")
    cfg = Config.load(paths)
    reindex_all(paths, cfg.raw["sources"])
    d = _check_sources(paths, cfg)
    assert d.status == "ok"


def test_hooks_check_warns_without_git(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    d = _check_hooks(paths)
    assert d.status == "warn"


def test_episodic_index_check_info_when_empty(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    d = _check_episodic_index(paths)
    assert d.status in ("info", "ok")


def test_cache_gitignored_check(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    dump_yaml(paths.config, merge_defaults({}))
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "bug-registry.md").write_text("# x\n\n## BUG-1: y\n\nbody.\n")
    cfg = Config.load(paths)
    reindex_all(paths, cfg.raw["sources"])  # writes the .gitignore
    d = _check_cache_gitignored(paths)
    assert d.status == "ok"
