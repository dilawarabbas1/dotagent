"""Tests for the v0.3 → v0.4 migrator."""

from __future__ import annotations

from pathlib import Path

from dotagent.canonical_structure import CURRENT_SCHEMA_VERSION
from dotagent.migration import apply_plan, build_plan
from dotagent.migration.detector import Mode
from dotagent.migration.log import KIND_CREATED, read_last_log
from dotagent.migration.v0_3_to_v0_4 import migrate_v0_3_to_v0_4


def _scaffold_pre_v0_4(repo: Path) -> None:
    """A minimal pre-v0.4 install: .agent/ exists, no .version, no brief."""
    (repo / ".agent").mkdir()
    (repo / ".agent" / "config.yaml").write_text("name: demo\n")


def test_plan_mode_returns_steps_without_touching_filesystem(tmp_path: Path):
    _scaffold_pre_v0_4(tmp_path)
    steps = migrate_v0_3_to_v0_4(tmp_path, write=False)

    assert len(steps) == 2
    paths = {s.path for s in steps}
    assert ".agent/.version" in paths
    assert ".agent/project_brief.md" in paths

    # nothing actually changed on disk
    assert not (tmp_path / ".agent" / ".version").exists()
    assert not (tmp_path / ".agent" / "project_brief.md").exists()


def test_write_mode_creates_version_file(tmp_path: Path):
    _scaffold_pre_v0_4(tmp_path)
    migrate_v0_3_to_v0_4(tmp_path, write=True)

    v = tmp_path / ".agent" / ".version"
    assert v.exists()
    assert v.read_text().strip() == "0.4.0"


def test_write_mode_creates_brief_stub(tmp_path: Path):
    _scaffold_pre_v0_4(tmp_path)
    migrate_v0_3_to_v0_4(tmp_path, write=True)

    brief = tmp_path / ".agent" / "project_brief.md"
    assert brief.exists()
    body = brief.read_text()
    assert "Project brief" in body
    assert "OBJ-01" in body  # template has IDs


def test_idempotent_re_run_makes_no_changes(tmp_path: Path):
    _scaffold_pre_v0_4(tmp_path)
    migrate_v0_3_to_v0_4(tmp_path, write=True)

    # Second run: no steps should be returned (everything already exists).
    steps = migrate_v0_3_to_v0_4(tmp_path, write=False)
    assert steps == []


def test_does_not_overwrite_existing_brief(tmp_path: Path):
    _scaffold_pre_v0_4(tmp_path)
    existing = tmp_path / ".agent" / "project_brief.md"
    existing.write_text("# my hand-written brief\nOBJ-99: do the thing\n")

    migrate_v0_3_to_v0_4(tmp_path, write=True)

    assert existing.read_text() == "# my hand-written brief\nOBJ-99: do the thing\n"


def test_build_plan_for_pre_v0_4(tmp_path: Path):
    _scaffold_pre_v0_4(tmp_path)
    plan = build_plan(tmp_path)

    assert plan.mode is Mode.PRE_V0_4
    assert plan.from_version is None
    assert plan.to_version == "0.4.0"
    assert len(plan.steps) == 2


def test_build_plan_for_fresh_install(tmp_path: Path):
    plan = build_plan(tmp_path)

    assert plan.mode is Mode.FRESH
    assert plan.steps == []
    assert any("dotagent init" in n for n in plan.notes)


def test_build_plan_for_current_schema(tmp_path: Path):
    (tmp_path / ".agent").mkdir()
    (tmp_path / ".agent" / ".version").write_text(CURRENT_SCHEMA_VERSION)
    plan = build_plan(tmp_path)

    assert plan.mode is Mode.CURRENT
    assert plan.steps == []
    assert any("already on schema version" in n for n in plan.notes)


def test_apply_plan_writes_migration_log(tmp_path: Path):
    _scaffold_pre_v0_4(tmp_path)
    plan = build_plan(tmp_path)
    apply_plan(tmp_path, plan)

    log_file = tmp_path / ".agent" / ".migration-log.md"
    assert log_file.exists()
    content = log_file.read_text()
    assert "pre-0.4" in content
    assert "0.4.0" in content
    assert "CREATED" in content


def test_apply_plan_then_doctor_clean(tmp_path: Path):
    """After migrate, the structure checker should find no fails."""
    from dotagent.canonical_structure import TIER_SINGLE_REPO
    from dotagent.structure_checker import SEVERITY_FAIL, check

    # Build a minimal v0.3-style layout that's missing .version + brief.
    (tmp_path / ".agent").mkdir()
    (tmp_path / ".agent" / "config.yaml").write_text("name: demo\n")
    (tmp_path / ".agent" / "architecture.md").write_text("# arch\n")
    (tmp_path / ".agent" / "rules.md").write_text("# rules\n")
    for sub in ("working", "episodic", "semantic", "personal"):
        (tmp_path / ".agent" / "memory" / sub).mkdir(parents=True)

    plan = build_plan(tmp_path)
    apply_plan(tmp_path, plan)

    result = check(tmp_path, tier=TIER_SINGLE_REPO)
    fails = [d for d in result.deviations if d.severity == SEVERITY_FAIL]
    assert fails == []
    assert not result.needs_migration


def test_step_kind_is_created_for_each_file(tmp_path: Path):
    _scaffold_pre_v0_4(tmp_path)
    steps = migrate_v0_3_to_v0_4(tmp_path, write=False)
    assert all(s.kind == KIND_CREATED for s in steps)


def test_read_last_log_returns_most_recent(tmp_path: Path):
    _scaffold_pre_v0_4(tmp_path)
    plan = build_plan(tmp_path)
    apply_plan(tmp_path, plan)

    log = read_last_log(tmp_path)
    assert log is not None
    assert log.to_version == "0.4.0"
    assert len(log.steps) == 2
    paths = {s.path for s in log.steps}
    assert ".agent/.version" in paths
    assert ".agent/project_brief.md" in paths
