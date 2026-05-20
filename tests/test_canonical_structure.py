"""Schema sanity tests for canonical_structure.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from dotagent.canonical_structure import (
    CURRENT_SCHEMA_VERSION,
    KIND_DIR,
    KIND_FILE,
    KIND_GENERATED,
    KIND_OPTIONAL,
    SchemaEntry,
    TIER_PROJECT_ROOT,
    TIER_SERVICE_REPO,
    TIER_SINGLE_REPO,
    all_tiers,
    detect_tier,
    schema_for,
)


def test_current_schema_version_is_semver_string():
    parts = CURRENT_SCHEMA_VERSION.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


def test_all_tiers_returns_three_distinct_names():
    tiers = all_tiers()
    assert len(tiers) == 3
    assert len(set(tiers)) == 3


def test_schema_for_returns_nonempty_for_each_tier():
    for tier in all_tiers():
        entries = schema_for(tier)
        assert len(entries) > 0


def test_schema_for_rejects_unknown_tier():
    with pytest.raises(ValueError, match="unknown tier"):
        schema_for("not-a-tier")


def test_schema_entry_rejects_unknown_kind():
    with pytest.raises(ValueError, match="unknown kind"):
        SchemaEntry(path="foo", required=True, kind="bogus")


def test_every_tier_includes_version_file_as_required():
    for tier in all_tiers():
        entries = schema_for(tier)
        version_entry = next((e for e in entries if e.path == ".agent/.version"), None)
        assert version_entry is not None, f"missing .version in tier {tier}"
        assert version_entry.required is True
        assert version_entry.kind == KIND_FILE


def test_project_root_tier_uniquely_requires_project_brief():
    pr_entries = {e.path for e in schema_for(TIER_PROJECT_ROOT)}
    assert ".agent/project_brief.md" in pr_entries

    # Service repos don't require their own brief — they inherit.
    sr_entries = {e.path for e in schema_for(TIER_SERVICE_REPO)}
    assert ".agent/project_brief.md" not in sr_entries


def test_detect_tier_returns_single_repo_for_bare_dir(tmp_path: Path):
    # No .agent/, no git.yaml, no config with parent: → single-repo
    assert detect_tier(tmp_path) == TIER_SINGLE_REPO


def test_detect_tier_returns_project_root_when_git_yaml_present(tmp_path: Path):
    (tmp_path / ".agent").mkdir()
    (tmp_path / ".agent" / "git.yaml").write_text("meta: {}\n")
    assert detect_tier(tmp_path) == TIER_PROJECT_ROOT


def test_detect_tier_returns_service_repo_on_parent_field(tmp_path: Path):
    (tmp_path / ".agent").mkdir()
    (tmp_path / ".agent" / "config.yaml").write_text("parent: ../..\nfoo: bar\n")
    assert detect_tier(tmp_path) == TIER_SERVICE_REPO


def test_detect_tier_ignores_commented_parent_line(tmp_path: Path):
    # A `# parent: ...` comment should not flip the tier.
    (tmp_path / ".agent").mkdir()
    (tmp_path / ".agent" / "config.yaml").write_text("# parent: ../..\n")
    assert detect_tier(tmp_path) == TIER_SINGLE_REPO


def test_detect_tier_ignores_bare_parent_key(tmp_path: Path):
    # `parent:` with no value (empty) should NOT count as a service-repo
    # signal — it's a YAML null and the user clearly hasn't wired anything.
    (tmp_path / ".agent").mkdir()
    (tmp_path / ".agent" / "config.yaml").write_text("parent:\nfoo: bar\n")
    assert detect_tier(tmp_path) == TIER_SINGLE_REPO


def test_schema_entries_are_immutable():
    # frozen=True on the dataclass; mutation should raise.
    e = SchemaEntry(path="x", required=True, kind=KIND_FILE)
    with pytest.raises((AttributeError, Exception)):
        e.required = False  # type: ignore[misc]
