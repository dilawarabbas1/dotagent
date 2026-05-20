"""Tests for the regenerate_derived_files() orchestrator.

The orchestrator is called from `dotagent sync`, `dotagent project
regenerate`, and the observe pre-commit hook. It should be safe to call
in any state (no project, no git.yaml, no modules) and fail soft on
individual generator failures.
"""

from __future__ import annotations

from pathlib import Path

from dotagent.paths import Paths
from dotagent.render.derived import regenerate_derived_files


def test_no_agent_dir_returns_empty(tmp_path: Path):
    """No .agent/ → no-op, no errors."""
    paths = Paths(repo=tmp_path)
    written = regenerate_derived_files(paths)
    assert written == []


def test_agent_dir_only_no_inputs_returns_empty(tmp_path: Path):
    """Bare .agent/ with no git.yaml and no project state → no files."""
    (tmp_path / ".agent").mkdir()
    paths = Paths(repo=tmp_path)
    written = regenerate_derived_files(paths)
    assert written == []


def test_git_yaml_only_writes_service_registry(tmp_path: Path):
    """With just a git.yaml, only service-registry.md is generated."""
    (tmp_path / ".agent").mkdir()
    (tmp_path / ".agent" / "git.yaml").write_text(
        "meta:\n  strategy: dedicated_repo\n"
        "  remote: ''\n"
        "  branch: dotagent/meta\n"
        "repos:\n"
        "  - id: portal\n"
        "    path: customer-portal\n"
        "    role: UI\n"
    )
    paths = Paths(repo=tmp_path)
    written = regenerate_derived_files(paths)
    rel = {p.relative_to(tmp_path).as_posix() for p in written}
    assert "docs/service-registry.md" in rel
    body = (tmp_path / "docs" / "service-registry.md").read_text()
    assert "portal" in body
    assert "customer-portal/" in body


def test_plan_yaml_writes_history_and_dashboard(tmp_path: Path):
    """With a project plan + modules, HISTORY.md and dashboard.md appear."""
    (tmp_path / ".agent").mkdir()
    (tmp_path / ".agent" / "project").mkdir()
    (tmp_path / ".agent" / "project" / "plan.yaml").write_text(
        "name: demo\n"
        "goal: test the regen pipeline\n"
        "modules:\n"
        "  01-auth:\n"
        "    id: 01-auth\n"
        "    name: Auth\n"
        "    state: DEFINED\n"
    )
    paths = Paths(repo=tmp_path)
    written = regenerate_derived_files(paths)
    rel = {p.relative_to(tmp_path).as_posix() for p in written}
    # Dashboard always writes when project loads
    assert ".agent/dashboard.md" in rel
    # HISTORY.md writes per-module
    assert ".agent/project/modules/01-auth/HISTORY.md" in rel


def test_orchestrator_is_idempotent(tmp_path: Path):
    """Calling twice produces the same file set."""
    (tmp_path / ".agent").mkdir()
    (tmp_path / ".agent" / "git.yaml").write_text(
        "meta:\n  strategy: dedicated_repo\n  remote: ''\n  branch: dotagent/meta\n"
        "repos:\n  - id: foo\n    path: foo\n"
    )
    paths = Paths(repo=tmp_path)
    first = sorted(p.relative_to(tmp_path).as_posix() for p in regenerate_derived_files(paths))
    second = sorted(p.relative_to(tmp_path).as_posix() for p in regenerate_derived_files(paths))
    assert first == second


def test_corrupt_git_yaml_does_not_block_other_generators(tmp_path: Path):
    """A truly broken git.yaml should fail soft and still let dashboard run."""
    (tmp_path / ".agent").mkdir()
    # Tab-indented mixed with spaces is hard-fail in PyYAML
    (tmp_path / ".agent" / "git.yaml").write_text("foo:\n\t- a: 1\n  - b: 2\n")
    (tmp_path / ".agent" / "project").mkdir()
    (tmp_path / ".agent" / "project" / "plan.yaml").write_text(
        "name: demo\nmodules: {}\n"
    )
    paths = Paths(repo=tmp_path)
    # Should not raise — log_exception swallows it. Project still runs.
    written = regenerate_derived_files(paths)
    rel = {p.relative_to(tmp_path).as_posix() for p in written}
    # dashboard always still written even if other generators fail
    assert ".agent/dashboard.md" in rel
