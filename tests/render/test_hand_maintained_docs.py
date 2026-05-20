"""Regression tests for the hand-maintained documentation convention.

The contract (see docs/HAND_MAINTAINED_DOCS_CONVENTION.md):

1. Every path listed here is in the schema with kind=KIND_FILE
   (NOT KIND_GENERATED).
2. Every path renders in the CLAUDE.md manifest, in the right category.
3. The Feature documentation entry-point pointer text is present.
4. dotagent's regenerate_derived_files() NEVER touches these paths.

If any of these break, dotagent has crossed the boundary. CI blocks.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dotagent.canonical_structure import (
    CAT_BUGS,
    CAT_DATA_LAYER,
    CAT_FEATURE_DOCS,
    CAT_OPS,
    KIND_FILE,
    KIND_GENERATED,
    TIER_PROJECT_ROOT,
    TIER_SINGLE_REPO,
    schema_for,
)
from dotagent.paths import Paths
from dotagent.render.derived import regenerate_derived_files
from dotagent.render.manifest import render_manifest


_HAND_MAINTAINED_PATHS = (
    # Feature documentation
    ("docs/feature_master.md", CAT_FEATURE_DOCS),
    ("docs/feature_master/FM-<id>-<slug>.md", CAT_FEATURE_DOCS),
    # Deep DB dependency
    ("docs/db-impact-map-master.md", CAT_DATA_LAYER),
    ("docs/db-impact-map-tenant.md", CAT_DATA_LAYER),
    ("docs/db-impact-map-vector.md", CAT_DATA_LAYER),
    # Deep Redis dependency
    ("docs/redis-key-registry-tenant.md", CAT_DATA_LAYER),
    ("docs/redis-key-registry-global.md", CAT_DATA_LAYER),
    ("docs/redis-key-registry-events.md", CAT_DATA_LAYER),
    # Sharded bug history
    ("docs/bug-registry-infrastructure.md", CAT_BUGS),
    ("docs/bug-registry-agents.md", CAT_BUGS),
    ("docs/bug-registry-orchestrator.md", CAT_BUGS),
    # Ops
    ("docs/ops/service-registry.md", CAT_OPS),
    ("docs/ops/server-dependencies.md", CAT_OPS),
    ("docs/ops/tuning.md", CAT_OPS),
    ("docs/ops/tls-and-env.md", CAT_OPS),
)


# ---------------------------------------------------------------------------
# Guarantee 1: every path is in the schema with kind=KIND_FILE
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tier", (TIER_PROJECT_ROOT, TIER_SINGLE_REPO))
@pytest.mark.parametrize("path,expected_cat", _HAND_MAINTAINED_PATHS)
def test_path_is_in_schema_with_kind_file(tier: str, path: str, expected_cat: str):
    schema = schema_for(tier)
    matching = [e for e in schema if e.path == path]
    assert matching, f"tier={tier}: schema missing {path!r}"
    entry = matching[0]
    assert entry.kind == KIND_FILE, (
        f"{path!r} must be KIND_FILE (hand-maintained), got {entry.kind!r}. "
        "If you marked it KIND_GENERATED you crossed the boundary — see "
        "docs/HAND_MAINTAINED_DOCS_CONVENTION.md."
    )
    assert entry.kind != KIND_GENERATED
    assert entry.category == expected_cat, (
        f"{path!r}: expected category {expected_cat!r}, got {entry.category!r}"
    )
    assert not entry.required, f"{path!r} must be required=False (project opts in)"


def test_no_hand_maintained_path_marked_generated():
    """Across BOTH tiers, none of these paths can be KIND_GENERATED.

    Defense-in-depth in case someone refactors and accidentally flips a
    kind."""
    for tier in (TIER_PROJECT_ROOT, TIER_SINGLE_REPO):
        schema = schema_for(tier)
        for path, _ in _HAND_MAINTAINED_PATHS:
            for entry in schema:
                if entry.path == path:
                    assert entry.kind == KIND_FILE, (
                        f"tier={tier}, {path!r} marked {entry.kind!r}; must be KIND_FILE"
                    )


# ---------------------------------------------------------------------------
# Guarantee 2: every path renders in the manifest
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tier", (TIER_PROJECT_ROOT, TIER_SINGLE_REPO))
@pytest.mark.parametrize("path,_", _HAND_MAINTAINED_PATHS)
def test_path_renders_in_manifest(tier: str, path: str, _, tmp_path: Path):
    (tmp_path / ".agent").mkdir()
    paths = Paths(repo=tmp_path)
    rendered = render_manifest(paths, tier=tier)
    assert path in rendered, (
        f"tier={tier}: rendered manifest missing {path!r}. "
        f"Check _CATEGORY_RENDER_ORDER in render/manifest.py."
    )


def test_hand_maintained_marker_present_in_descriptions(tmp_path: Path):
    """Every hand-maintained entry's description carries the marker so
    the AI knows precedence without reading this doc."""
    (tmp_path / ".agent").mkdir()
    paths = Paths(repo=tmp_path)
    rendered = render_manifest(paths, tier=TIER_PROJECT_ROOT)
    assert "HAND-MAINTAINED" in rendered, (
        "renderer should preserve the HAND-MAINTAINED marker from when_to_read"
    )


def test_feature_docs_section_header_present(tmp_path: Path):
    (tmp_path / ".agent").mkdir()
    paths = Paths(repo=tmp_path)
    rendered = render_manifest(paths, tier=TIER_PROJECT_ROOT)
    assert "📑 Feature documentation (hand-maintained)" in rendered


def test_ops_section_header_present(tmp_path: Path):
    (tmp_path / ".agent").mkdir()
    paths = Paths(repo=tmp_path)
    rendered = render_manifest(paths, tier=TIER_PROJECT_ROOT)
    assert "🔧 Operations (hand-maintained" in rendered


# ---------------------------------------------------------------------------
# Guarantee 3: the entry-point pointer text is in the rendered manifest
# ---------------------------------------------------------------------------

def test_feature_entry_point_pointer_text(tmp_path: Path):
    (tmp_path / ".agent").mkdir()
    paths = Paths(repo=tmp_path)
    rendered = render_manifest(paths, tier=TIER_PROJECT_ROOT)
    assert "Entry point for any feature work" in rendered, (
        "the Feature documentation preface must guide the AI to feature_master.md "
        "first, then FM-###-<slug>.md"
    )
    assert "docs/feature_master.md" in rendered
    assert "FM-###-<slug>.md" in rendered or "FM-<id>-<slug>.md" in rendered


# ---------------------------------------------------------------------------
# Guarantee 4: dotagent NEVER writes to these paths
# ---------------------------------------------------------------------------

def test_regenerate_derived_files_never_writes_hand_maintained(tmp_path: Path):
    """Run the full derived-file orchestrator on a populated project and
    confirm none of the hand-maintained paths appear in the write set."""
    (tmp_path / ".agent").mkdir()
    (tmp_path / ".agent" / "git.yaml").write_text(
        "meta:\n  strategy: dedicated_repo\n  remote: ''\n  branch: dotagent/meta\n"
        "repos:\n  - id: foo\n    path: foo\n"
    )
    (tmp_path / ".agent" / "project").mkdir()
    (tmp_path / ".agent" / "project" / "plan.yaml").write_text(
        "name: demo\nmodules:\n  01-foo:\n    id: 01-foo\n    name: Foo\n    state: DEFINED\n"
    )
    # Create the hand-maintained files with sentinel content
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "feature_master").mkdir()
    (tmp_path / "docs" / "ops").mkdir()
    sentinel = "DO NOT OVERWRITE — owned by human + Claude\n"
    hand_files = [
        tmp_path / "docs" / "feature_master.md",
        tmp_path / "docs" / "feature_master" / "FM-001-foo.md",
        tmp_path / "docs" / "db-impact-map-tenant.md",
        tmp_path / "docs" / "redis-key-registry-global.md",
        tmp_path / "docs" / "bug-registry-infrastructure.md",
        tmp_path / "docs" / "ARCHITECTURE.md",
        tmp_path / "docs" / "ops" / "service-registry.md",
        tmp_path / "docs" / "ops" / "tuning.md",
    ]
    for f in hand_files:
        f.write_text(sentinel)

    paths = Paths(repo=tmp_path)
    written = regenerate_derived_files(paths)
    written_paths = {p.relative_to(tmp_path).as_posix() for p in written}

    # None of the hand-maintained files should appear in the write set
    forbidden = {
        "docs/feature_master.md",
        "docs/feature_master/FM-001-foo.md",
        "docs/db-impact-map-tenant.md",
        "docs/redis-key-registry-global.md",
        "docs/bug-registry-infrastructure.md",
        "docs/ARCHITECTURE.md",
        "docs/ops/service-registry.md",
        "docs/ops/tuning.md",
    }
    leaked = forbidden & written_paths
    assert not leaked, (
        f"dotagent crossed the hand-maintained boundary: {leaked}. "
        "These paths must never be written by the derived-files orchestrator."
    )

    # And confirm the sentinel content is unchanged on disk
    for f in hand_files:
        assert f.read_text() == sentinel, (
            f"dotagent overwrote a hand-maintained file: {f}"
        )


def test_config_default_sources_extra_registers_hand_maintained_paths():
    """The default config should declare these as `sources.extra` so the
    indexer picks them up when they exist."""
    from dotagent.config import DEFAULT_CONFIG

    extras = DEFAULT_CONFIG.get("sources", {}).get("extra") or []
    extra_paths = {e.get("path") for e in extras if isinstance(e, dict)}

    expected_in_extras = {
        "docs/feature_master.md",
        "docs/db-impact-map-master.md",
        "docs/db-impact-map-tenant.md",
        "docs/db-impact-map-vector.md",
        "docs/redis-key-registry-tenant.md",
        "docs/redis-key-registry-global.md",
        "docs/redis-key-registry-events.md",
        "docs/bug-registry-infrastructure.md",
        "docs/bug-registry-agents.md",
        "docs/bug-registry-orchestrator.md",
        "docs/ARCHITECTURE.md",
        "docs/ops/service-registry.md",
        "docs/ops/server-dependencies.md",
        "docs/ops/tuning.md",
        "docs/ops/tls-and-env.md",
    }
    missing = expected_in_extras - extra_paths
    assert not missing, (
        f"DEFAULT_CONFIG.sources.extra missing: {missing}. "
        "Hand-maintained paths must be auto-registered for indexing."
    )
