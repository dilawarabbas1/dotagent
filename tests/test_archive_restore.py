"""Restore tests — un-archiving works for every source kind."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dotagent.archive import list_archived, restore, run, scan


def _now() -> datetime:
    return datetime(2026, 6, 1, tzinfo=timezone.utc)


def _setup_with_bug(tmp_path: Path) -> Path:
    (tmp_path / ".agent").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "bug-registry.md").write_text(
        "# Bug registry\n\n"
        "## BUG-007 · Auth loop\n- status: fixed\n- fix-frozen: 2026-04-01\n\nDescription\n"
    )
    return tmp_path


def test_restore_bug_registry_entry(tmp_path: Path):
    repo = _setup_with_bug(tmp_path)
    candidates = scan(repo, now=_now()).candidates
    run(repo, candidates=candidates)

    # Confirm it was moved
    assert "BUG-007" not in (repo / "docs" / "bug-registry.md").read_text()

    entry = restore(repo, "BUG-007")
    assert entry is not None
    assert entry.entry_id == "BUG-007"
    assert entry.restored_at != ""

    # Source has it back; archive file no longer contains it
    src = (repo / "docs" / "bug-registry.md").read_text()
    assert "BUG-007" in src
    arch = (repo / "docs" / "archive" / "2026" / "bug-registry.md").read_text()
    assert "BUG-007" not in arch


def test_restore_module_directory(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    mod_dir = tmp_path / ".agent" / "project" / "modules" / "M01-auth"
    mod_dir.mkdir(parents=True)
    frozen = (_now() - timedelta(days=120)).isoformat()
    (mod_dir / "module.yaml").write_text(
        f"id: M01-auth\nstate: shipped\n"
        f"cycles:\n  - contract:\n      frozen_at: {frozen}\n"
    )

    candidates = scan(tmp_path, now=_now()).candidates
    run(tmp_path, candidates=candidates)
    assert not mod_dir.exists()

    entry = restore(tmp_path, "M01-auth")
    assert entry is not None
    assert mod_dir.exists()
    assert (mod_dir / "module.yaml").exists()


def test_restore_returns_none_for_unknown_id(tmp_path: Path):
    repo = _setup_with_bug(tmp_path)
    candidates = scan(repo, now=_now()).candidates
    run(repo, candidates=candidates)

    result = restore(repo, "NOT-A-THING")
    assert result is None


def test_restore_raises_when_log_missing(tmp_path: Path):
    (tmp_path / ".agent").mkdir()
    with pytest.raises(FileNotFoundError):
        restore(tmp_path, "BUG-001")


def test_restore_marks_entry_as_restored_in_log(tmp_path: Path):
    repo = _setup_with_bug(tmp_path)
    candidates = scan(repo, now=_now()).candidates
    run(repo, candidates=candidates)

    restore(repo, "BUG-007")

    log = list_archived(repo)
    assert len(log) == 1
    assert log[0].restored_at != ""


def test_restore_double_restore_returns_none(tmp_path: Path):
    repo = _setup_with_bug(tmp_path)
    candidates = scan(repo, now=_now()).candidates
    run(repo, candidates=candidates)

    first = restore(repo, "BUG-007")
    assert first is not None

    # Second attempt — entry is already restored
    second = restore(repo, "BUG-007")
    assert second is None
