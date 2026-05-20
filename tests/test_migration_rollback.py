"""Rollback tests."""

from __future__ import annotations

from pathlib import Path

from dotagent.migration import apply_plan, build_plan
from dotagent.migration.log import read_last_log
from dotagent.migration.v0_3_to_v0_4 import rollback_step


def _scaffold_pre_v0_4(repo: Path) -> None:
    (repo / ".agent").mkdir()
    (repo / ".agent" / "config.yaml").write_text("name: demo\n")


def test_rollback_removes_created_files(tmp_path: Path):
    _scaffold_pre_v0_4(tmp_path)
    plan = build_plan(tmp_path)
    apply_plan(tmp_path, plan)

    # Confirm migrate created both files
    assert (tmp_path / ".agent" / ".version").exists()
    assert (tmp_path / ".agent" / "project_brief.md").exists()

    # Reverse via the rollback runner
    log = read_last_log(tmp_path)
    assert log is not None
    for step in reversed(log.steps):
        assert rollback_step(tmp_path, step) is True

    # Both files gone
    assert not (tmp_path / ".agent" / ".version").exists()
    assert not (tmp_path / ".agent" / "project_brief.md").exists()


def test_rollback_handles_already_gone_file(tmp_path: Path):
    """If a target was already removed (e.g., user nuked it), rollback is
    still considered a success — best-effort."""
    _scaffold_pre_v0_4(tmp_path)
    plan = build_plan(tmp_path)
    apply_plan(tmp_path, plan)

    # User manually removes one file before running rollback
    (tmp_path / ".agent" / ".version").unlink()

    log = read_last_log(tmp_path)
    assert log is not None
    for step in reversed(log.steps):
        assert rollback_step(tmp_path, step) is True


def test_read_last_log_returns_none_when_missing(tmp_path: Path):
    _scaffold_pre_v0_4(tmp_path)
    assert read_last_log(tmp_path) is None


def test_log_supports_multiple_runs(tmp_path: Path):
    """Two migrate runs append; read_last_log returns the most recent."""
    _scaffold_pre_v0_4(tmp_path)

    # First run — does the real migration
    plan = build_plan(tmp_path)
    apply_plan(tmp_path, plan)

    # Simulate a second run by writing another section manually
    log_file = tmp_path / ".agent" / ".migration-log.md"
    log_file.write_text(
        log_file.read_text()
        + "\n## 2026-06-01T00:00:00Z · v0.4.0 → v0.5.0\n\n- CREATED: .agent/foo.md\n"
    )

    log = read_last_log(tmp_path)
    assert log is not None
    assert log.to_version == "0.5.0"
    assert log.from_version == "0.4.0"
    assert len(log.steps) == 1
    assert log.steps[0].path == ".agent/foo.md"
