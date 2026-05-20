"""Tests for archive.mover.run() and the H2-section extraction."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotagent.archive import list_archived, run, scan
from dotagent.archive.triggers import KIND_ANTI_PATTERNS, KIND_BUG_REGISTRY, KIND_MODULES


def _now() -> datetime:
    return datetime(2026, 6, 1, tzinfo=timezone.utc)


def _setup_repo_with_archivable_bug(tmp_path: Path) -> Path:
    (tmp_path / ".agent").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "bug-registry.md").write_text(
        "# Bug registry\n\n"
        "## BUG-007 · Auth loop\n"
        "- status: fixed\n"
        "- fix-frozen: 2026-04-01\n"
        "\n"
        "Steps to reproduce: ...\n"
        "\n"
        "## BUG-008 · Still open\n"
        "- status: open\n"
        "\n"
        "Working on it.\n"
    )
    return tmp_path


def test_run_moves_bug_section_to_archive_file(tmp_path: Path):
    repo = _setup_repo_with_archivable_bug(tmp_path)
    candidates = scan(repo, now=_now()).candidates
    result = run(repo, candidates=candidates)

    assert len(result.moved) == 1
    assert result.errors == []

    # Source file now has only BUG-008
    src = (repo / "docs" / "bug-registry.md").read_text()
    assert "BUG-007" not in src
    assert "BUG-008" in src
    assert "Steps to reproduce" not in src

    # Archive file has BUG-007
    arch = (repo / "docs" / "archive" / "2026" / "bug-registry.md").read_text()
    assert "BUG-007" in arch
    assert "Steps to reproduce" in arch
    assert arch.startswith("<!--")  # banner
    assert "## BUG-007" in arch


def test_run_dry_run_touches_nothing(tmp_path: Path):
    repo = _setup_repo_with_archivable_bug(tmp_path)
    candidates = scan(repo, now=_now()).candidates
    result = run(repo, candidates=candidates, dry_run=True)

    assert len(result.moved) == 1
    # Source unchanged
    src = (repo / "docs" / "bug-registry.md").read_text()
    assert "BUG-007" in src
    # No archive directory created
    assert not (repo / "docs" / "archive").exists()
    # No log
    assert not (repo / ".agent" / "archive-log.md").exists()


def test_run_writes_archive_log(tmp_path: Path):
    repo = _setup_repo_with_archivable_bug(tmp_path)
    candidates = scan(repo, now=_now()).candidates
    run(repo, candidates=candidates)

    log = (repo / ".agent" / "archive-log.md").read_text()
    assert "BUG-007" in log
    assert "ARCHIVED:" in log
    assert "bug-registry" in log


def test_list_archived_returns_moved_entries(tmp_path: Path):
    repo = _setup_repo_with_archivable_bug(tmp_path)
    candidates = scan(repo, now=_now()).candidates
    run(repo, candidates=candidates)

    archived = list_archived(repo)
    assert len(archived) == 1
    assert archived[0].entry_id == "BUG-007"
    assert archived[0].source_kind == KIND_BUG_REGISTRY


def test_run_handles_anti_pattern_section(tmp_path: Path):
    (tmp_path / ".agent").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "anti-patterns.md").write_text(
        "## AP-001 · No longer applies\n"
        "- rescinded: true\n"
        "- rescinded-at: 2025-12-01\n"
        "\n"
        "After the Postgres 16 upgrade...\n"
        "\n"
        "## AP-002 · Still active\n"
        "- rescinded: false\n"
    )
    candidates = scan(tmp_path, now=_now()).candidates
    run(tmp_path, candidates=candidates)

    src = (tmp_path / "docs" / "anti-patterns.md").read_text()
    assert "AP-001" not in src
    assert "AP-002" in src

    arch = (tmp_path / "docs" / "archive" / "2026" / "anti-patterns.md").read_text()
    assert "AP-001" in arch
    assert "Postgres 16 upgrade" in arch


def test_run_moves_module_directory(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    mod_dir = tmp_path / ".agent" / "project" / "modules" / "M01-auth"
    mod_dir.mkdir(parents=True)
    frozen = (_now() - timedelta(days=120)).isoformat()
    (mod_dir / "module.yaml").write_text(
        f"id: M01-auth\nstate: shipped\n"
        f"cycles:\n  - contract:\n      frozen_at: {frozen}\n"
    )
    (mod_dir / "PLAN.md").write_text("# plan\n")
    (mod_dir / "cycles").mkdir()
    (mod_dir / "cycles" / "01").mkdir()
    (mod_dir / "cycles" / "01" / "contract.md").write_text("# contract\n")

    candidates = scan(tmp_path, now=_now()).candidates
    run(tmp_path, candidates=candidates)

    # Original location gone
    assert not mod_dir.exists()
    # Archive location has the whole tree
    arch_dir = tmp_path / ".agent" / "project" / "archive" / "2026" / "M01-auth"
    assert arch_dir.is_dir()
    assert (arch_dir / "module.yaml").exists()
    assert (arch_dir / "PLAN.md").exists()
    assert (arch_dir / "cycles" / "01" / "contract.md").exists()


def test_run_with_no_candidates_is_noop(tmp_path: Path):
    (tmp_path / ".agent").mkdir()
    (tmp_path / "docs").mkdir()
    result = run(tmp_path, candidates=[])
    assert result.moved == []
    assert result.errors == []
    assert not (tmp_path / ".agent" / "archive-log.md").exists()


def test_archive_file_appends_across_runs(tmp_path: Path):
    """Two separate archive operations append to the same year-file."""
    repo = _setup_repo_with_archivable_bug(tmp_path)
    candidates_a = [c for c in scan(repo, now=_now()).candidates if c.entry_id == "BUG-007"]
    run(repo, candidates=candidates_a)

    # Add another fixable bug, archive again
    (repo / "docs" / "bug-registry.md").write_text(
        (repo / "docs" / "bug-registry.md").read_text()
        + "\n## BUG-009 · Another fix\n- status: fixed\n- fix-frozen: 2026-04-15\n\nDetails\n"
    )
    candidates_b = scan(repo, now=_now()).candidates
    run(repo, candidates=candidates_b)

    arch = (repo / "docs" / "archive" / "2026" / "bug-registry.md").read_text()
    assert "BUG-007" in arch
    assert "BUG-009" in arch
