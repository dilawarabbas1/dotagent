"""Trigger-eligibility tests for archive.scan()."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotagent.archive.triggers import (
    KIND_ANTI_PATTERNS,
    KIND_BUG_REGISTRY,
    KIND_MODULES,
    scan,
)


def _now() -> datetime:
    return datetime(2026, 6, 1, tzinfo=timezone.utc)


def _setup_repo(tmp_path: Path) -> Path:
    (tmp_path / ".agent").mkdir()
    (tmp_path / "docs").mkdir()
    return tmp_path


# ---------- bug-registry ----------

def test_bug_registry_archives_fixed_old_entry(tmp_path: Path):
    repo = _setup_repo(tmp_path)
    (repo / "docs" / "bug-registry.md").write_text(
        "# Bug registry\n\n"
        "## BUG-007 · Auth loop\n"
        "- status: fixed\n"
        "- fix-frozen: 2026-04-01\n"
        "\n"
        "Description...\n"
    )
    report = scan(repo, now=_now())
    bugs = [c for c in report.candidates if c.source_kind == KIND_BUG_REGISTRY]
    assert len(bugs) == 1
    assert bugs[0].entry_id == "BUG-007"
    assert bugs[0].title == "Auth loop"


def test_bug_registry_skips_recent_fix(tmp_path: Path):
    repo = _setup_repo(tmp_path)
    recent_iso = (_now() - timedelta(days=10)).date().isoformat()
    (repo / "docs" / "bug-registry.md").write_text(
        "## BUG-008 · Recent fix\n"
        f"- status: fixed\n"
        f"- fix-frozen: {recent_iso}\n"
    )
    report = scan(repo, now=_now())
    bugs = [c for c in report.candidates if c.source_kind == KIND_BUG_REGISTRY]
    assert bugs == []


def test_bug_registry_skips_open_status(tmp_path: Path):
    repo = _setup_repo(tmp_path)
    (repo / "docs" / "bug-registry.md").write_text(
        "## BUG-009 · Open\n- status: open\n"
    )
    report = scan(repo, now=_now())
    assert not [c for c in report.candidates if c.source_kind == KIND_BUG_REGISTRY]


def test_bug_registry_skips_fixed_without_date(tmp_path: Path):
    repo = _setup_repo(tmp_path)
    (repo / "docs" / "bug-registry.md").write_text(
        "## BUG-010 · No date\n- status: fixed\n"
    )
    report = scan(repo, now=_now())
    # No fix-frozen date → can't compute age → skipped
    assert not [c for c in report.candidates if c.source_kind == KIND_BUG_REGISTRY]


def test_bug_registry_respects_custom_min_age(tmp_path: Path):
    repo = _setup_repo(tmp_path)
    (repo / ".agent" / "config.yaml").write_text(
        "archive:\n  bug_min_age_days: 365\n"
    )
    fix_date = (_now() - timedelta(days=100)).date().isoformat()
    (repo / "docs" / "bug-registry.md").write_text(
        f"## BUG-011 · 100d ago\n- status: fixed\n- fix-frozen: {fix_date}\n"
    )
    # 100 days < 365 day threshold
    report = scan(repo, now=_now())
    assert not [c for c in report.candidates if c.source_kind == KIND_BUG_REGISTRY]


# ---------- anti-patterns ----------

def test_anti_patterns_archives_rescinded(tmp_path: Path):
    repo = _setup_repo(tmp_path)
    (repo / "docs" / "anti-patterns.md").write_text(
        "## AP-003 · Caching everywhere\n- rescinded: true\n- rescinded-at: 2025-12-01\n"
    )
    report = scan(repo, now=_now())
    aps = [c for c in report.candidates if c.source_kind == KIND_ANTI_PATTERNS]
    assert len(aps) == 1
    assert aps[0].entry_id == "AP-003"
    assert aps[0].eligible_since == "2025-12-01"


def test_anti_patterns_skips_active(tmp_path: Path):
    repo = _setup_repo(tmp_path)
    (repo / "docs" / "anti-patterns.md").write_text(
        "## AP-004 · Still active\n- rescinded: false\n"
    )
    report = scan(repo, now=_now())
    assert not [c for c in report.candidates if c.source_kind == KIND_ANTI_PATTERNS]


# ---------- modules ----------

def test_modules_archives_shipped_and_old(tmp_path: Path):
    repo = _setup_repo(tmp_path)
    mod_dir = repo / ".agent" / "project" / "modules" / "M01-auth"
    mod_dir.mkdir(parents=True)
    frozen_at = (_now() - timedelta(days=120)).isoformat()
    (mod_dir / "module.yaml").write_text(
        f"id: M01-auth\nname: Auth\nstate: shipped\n"
        f"cycles:\n"
        f"  - n: 1\n"
        f"    contract:\n"
        f"      frozen_at: {frozen_at}\n"
    )
    report = scan(repo, now=_now())
    mods = [c for c in report.candidates if c.source_kind == KIND_MODULES]
    assert len(mods) == 1
    assert mods[0].entry_id == "M01-auth"


def test_modules_skips_in_progress(tmp_path: Path):
    repo = _setup_repo(tmp_path)
    mod_dir = repo / ".agent" / "project" / "modules" / "M02-x"
    mod_dir.mkdir(parents=True)
    (mod_dir / "module.yaml").write_text("state: in-progress\n")
    report = scan(repo, now=_now())
    assert not [c for c in report.candidates if c.source_kind == KIND_MODULES]


def test_modules_skips_recent_shipped(tmp_path: Path):
    repo = _setup_repo(tmp_path)
    mod_dir = repo / ".agent" / "project" / "modules" / "M03-recent"
    mod_dir.mkdir(parents=True)
    frozen_at = (_now() - timedelta(days=30)).isoformat()
    (mod_dir / "module.yaml").write_text(
        f"state: shipped\ncycles:\n  - contract:\n      frozen_at: {frozen_at}\n"
    )
    report = scan(repo, now=_now())
    # 30d < 90d threshold
    assert not [c for c in report.candidates if c.source_kind == KIND_MODULES]


# ---------- report shape ----------

def test_scan_report_to_dict_has_stable_shape(tmp_path: Path):
    repo = _setup_repo(tmp_path)
    payload = scan(repo, now=_now()).to_dict()
    assert set(payload.keys()) == {"candidates", "counts", "total"}
    assert "bug-registry" in payload["counts"]
    assert "anti-patterns" in payload["counts"]
    assert "modules" in payload["counts"]


def test_scan_on_repo_with_no_sources_returns_empty(tmp_path: Path):
    repo = _setup_repo(tmp_path)
    report = scan(repo, now=_now())
    assert report.candidates == []
    assert all(v == 0 for v in report.counts.values())
