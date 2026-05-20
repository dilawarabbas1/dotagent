"""Tests for dynamic docs/ listing in the manifest.

Canonical filenames (bug-registry.md, etc.) keep their schema-driven
pointers. Any OTHER files in docs/ are auto-listed under
"Other docs in this repo" with the first H1 as description.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dotagent.canonical_structure import (
    TIER_PROJECT_ROOT,
    TIER_SERVICE_REPO,
    TIER_SINGLE_REPO,
)
from dotagent.paths import Paths
from dotagent.render.manifest import (
    _first_h1_or_line,
    _render_other_docs,
    render_manifest,
)
from dotagent.canonical_structure import schema_for


def _fixture_paths(tmp_path: Path) -> Paths:
    (tmp_path / ".agent").mkdir()
    (tmp_path / "docs").mkdir()
    return Paths(repo=tmp_path)


# ---------------------------------------------------------------------------
# _first_h1_or_line
# ---------------------------------------------------------------------------

def test_first_h1_extracts_clean_heading(tmp_path: Path):
    p = tmp_path / "doc.md"
    p.write_text("<!-- generated -->\n\n# Voice architecture\n\nbody")
    assert _first_h1_or_line(p) == "Voice architecture"


def test_first_h1_skips_html_comments(tmp_path: Path):
    p = tmp_path / "doc.md"
    p.write_text("<!-- one -->\n<!-- two -->\n\n# Real title\n")
    assert _first_h1_or_line(p) == "Real title"


def test_first_line_when_no_h1(tmp_path: Path):
    p = tmp_path / "doc.md"
    p.write_text("Just some prose without a heading.\nMore text.")
    assert _first_h1_or_line(p) == "Just some prose without a heading."


def test_first_h1_handles_empty_file(tmp_path: Path):
    p = tmp_path / "doc.md"
    p.write_text("")
    assert _first_h1_or_line(p) == ""


def test_first_h1_truncates_long_first_line(tmp_path: Path):
    p = tmp_path / "doc.md"
    long_line = "x" * 200
    p.write_text(long_line)
    result = _first_h1_or_line(p)
    assert len(result) <= 100
    assert result.endswith("…")


# ---------------------------------------------------------------------------
# _render_other_docs
# ---------------------------------------------------------------------------

def test_no_docs_dir_returns_empty(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    (tmp_path / ".agent").mkdir()
    assert _render_other_docs(paths, schema_for(TIER_SINGLE_REPO)) == ""


def test_empty_docs_dir_returns_empty(tmp_path: Path):
    paths = _fixture_paths(tmp_path)
    assert _render_other_docs(paths, schema_for(TIER_SINGLE_REPO)) == ""


def test_only_canonical_docs_returns_empty(tmp_path: Path):
    """If docs/ only contains canonical filenames, nothing new to list."""
    paths = _fixture_paths(tmp_path)
    (paths.repo / "docs" / "bug-registry.md").write_text("# Bugs\n")
    (paths.repo / "docs" / "redis-keys.md").write_text("# Redis\n")
    result = _render_other_docs(paths, schema_for(TIER_SINGLE_REPO))
    assert result == ""


def test_non_canonical_docs_are_listed(tmp_path: Path):
    """A file like docs/voice-architecture.md appears in the listing."""
    paths = _fixture_paths(tmp_path)
    (paths.repo / "docs" / "voice-architecture.md").write_text(
        "# Voice Architecture\n\nHow WebRTC + PSTN are wired.\n"
    )
    (paths.repo / "docs" / "onboarding-flow.md").write_text(
        "# Onboarding\n\n1. Sign up\n"
    )
    result = _render_other_docs(paths, schema_for(TIER_SINGLE_REPO))
    assert "Other docs in this repo" in result
    assert "docs/voice-architecture.md" in result
    assert "Voice Architecture" in result
    assert "docs/onboarding-flow.md" in result
    assert "Onboarding" in result


def test_canonical_docs_excluded_from_dynamic_listing(tmp_path: Path):
    """Mixed docs/: canonical files don't appear in 'Other docs', only non-canonical."""
    paths = _fixture_paths(tmp_path)
    (paths.repo / "docs" / "bug-registry.md").write_text("# Bugs\n")
    (paths.repo / "docs" / "custom-doc.md").write_text("# Custom\n")
    result = _render_other_docs(paths, schema_for(TIER_SINGLE_REPO))
    # bug-registry is canonical → should not appear in dynamic listing
    assert "docs/bug-registry.md" not in result
    # custom-doc is novel → should appear
    assert "docs/custom-doc.md" in result


def test_archived_docs_are_skipped(tmp_path: Path):
    """Files under docs/archive/ are dotagent-generated archives;
    don't list them in the dynamic section."""
    paths = _fixture_paths(tmp_path)
    (paths.repo / "docs" / "archive" / "2025").mkdir(parents=True)
    (paths.repo / "docs" / "archive" / "2025" / "old-bugs.md").write_text("# Old\n")
    (paths.repo / "docs" / "active-doc.md").write_text("# Active\n")
    result = _render_other_docs(paths, schema_for(TIER_SINGLE_REPO))
    assert "docs/active-doc.md" in result
    assert "archive" not in result


def test_nested_docs_subdirs_listed(tmp_path: Path):
    """Subdirectories under docs/ (e.g. docs/api/openapi.md) are walked."""
    paths = _fixture_paths(tmp_path)
    (paths.repo / "docs" / "api").mkdir()
    (paths.repo / "docs" / "api" / "openapi.md").write_text("# OpenAPI spec\n")
    result = _render_other_docs(paths, schema_for(TIER_SINGLE_REPO))
    assert "docs/api/openapi.md" in result


# ---------------------------------------------------------------------------
# Integration with full manifest
# ---------------------------------------------------------------------------

def test_manifest_includes_other_docs_section_when_present(tmp_path: Path):
    paths = _fixture_paths(tmp_path)
    (paths.repo / "docs" / "voice-architecture.md").write_text(
        "# Voice Architecture\n\nProject voice/PSTN.\n"
    )
    rendered = render_manifest(paths, tier=TIER_SINGLE_REPO)
    assert "Other docs in this repo" in rendered
    assert "voice-architecture.md" in rendered


def test_manifest_omits_other_docs_section_when_empty(tmp_path: Path):
    """No non-canonical docs → no 'Other docs' section in manifest."""
    paths = _fixture_paths(tmp_path)
    # Only canonical files
    (paths.repo / "docs" / "bug-registry.md").write_text("# Bugs\n")
    rendered = render_manifest(paths, tier=TIER_SINGLE_REPO)
    assert "Other docs in this repo" not in rendered


def test_works_across_all_tiers(tmp_path: Path):
    """Other-docs listing works for every tier (project-root, service-repo, single-repo)."""
    for tier in (TIER_PROJECT_ROOT, TIER_SERVICE_REPO, TIER_SINGLE_REPO):
        paths = _fixture_paths(tmp_path)
        (paths.repo / "docs" / "custom.md").write_text("# Custom doc\n")
        rendered = render_manifest(paths, tier=tier)
        assert "Other docs in this repo" in rendered, f"failed for tier={tier}"
        assert "custom.md" in rendered
        # Cleanup for next iteration
        import shutil
        shutil.rmtree(tmp_path / ".agent")
        shutil.rmtree(tmp_path / "docs")
