"""Service-repo CLAUDE.md acts as a CHILD of the layered project root.

These tests assert two complementary guarantees:

1. The service-repo schema surfaces the LOCAL contract layer
   (`.agent/project/modules/` + cycle artifacts).
2. The service-repo schema surfaces INHERITED project-root context
   via `../`-prefixed pointers in the rendered manifest.

If a service has no parent (single-repo install), the pointers still
appear in the manifest body but point at paths that don't exist on
disk — that's fine, the manifest is a navigation index, not a file
existence check.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dotagent.canonical_structure import (
    TIER_SERVICE_REPO,
    schema_for,
)
from dotagent.paths import Paths
from dotagent.render.manifest import render_manifest


def _fixture_paths(tmp_path: Path) -> Paths:
    (tmp_path / ".agent").mkdir()
    return Paths(repo=tmp_path)


# ---------------------------------------------------------------------------
# Local contract-layer entries
# ---------------------------------------------------------------------------

_LOCAL_CONTRACT_PATHS = (
    ".agent/project/modules",
    ".agent/project/modules/<id>/module.yaml",
    ".agent/project/modules/<id>/PLAN.md",
    ".agent/project/modules/<id>/cycles/<NN>/contract.md",
    ".agent/project/modules/<id>/cycles/<NN>/contract.frozen.md",
    ".agent/project/modules/<id>/cycles/<NN>/dev-handoff.md",
    ".agent/project/modules/<id>/cycles/<NN>/qa-findings.md",
    ".agent/project/modules/<id>/completion.md",
)


@pytest.mark.parametrize("path", _LOCAL_CONTRACT_PATHS)
def test_local_contract_paths_in_service_repo_schema(path: str):
    """Each local-contract path is present in the service-repo schema."""
    schema_paths = {e.path for e in schema_for(TIER_SERVICE_REPO)}
    assert path in schema_paths, (
        f"service-repo schema is missing local contract path: {path!r}"
    )


@pytest.mark.parametrize("path", _LOCAL_CONTRACT_PATHS)
def test_local_contract_paths_in_rendered_manifest(path: str, tmp_path: Path):
    paths = _fixture_paths(tmp_path)
    rendered = render_manifest(paths, tier=TIER_SERVICE_REPO)
    assert path in rendered, (
        f"service-repo manifest missing local contract path: {path!r}"
    )


# ---------------------------------------------------------------------------
# Inherited (project-root) entries
# ---------------------------------------------------------------------------

_INHERITED_PATHS = (
    "../.agent/project_brief.md",
    "../.agent/rules.md",
    "../.agent/git.md",
    "../.agent/architecture.md",
    "../.agent/style.md",
    "../.agent/patterns.md",
    # NOTE: ../.agent/git.yaml is intentionally NOT in the service-repo
    # schema — git.yaml is project-root scope. Service-repo devs read
    # the rendered dashboard `../.agent/git.md` instead.
    "../.agent/project/plan.yaml",
    "../.agent/project/SCOPE.md",
    "../.agent/project/CONTRACTS.md",
    "../.agent/project/modules",
    "../contracts.md",
    "../docs/service-registry.md",
    "../docs/shared-contracts.md",
    "../docs/dependency-map.md",
    "../docs/architecture.md",
    "../docs/bug-registry.md",
    "../docs/anti-patterns.md",
)


@pytest.mark.parametrize("path", _INHERITED_PATHS)
def test_inherited_paths_in_service_repo_schema(path: str):
    schema_paths = {e.path for e in schema_for(TIER_SERVICE_REPO)}
    assert path in schema_paths, (
        f"service-repo schema is missing inherited path: {path!r}"
    )


@pytest.mark.parametrize("path", _INHERITED_PATHS)
def test_inherited_paths_in_rendered_manifest(path: str, tmp_path: Path):
    paths = _fixture_paths(tmp_path)
    rendered = render_manifest(paths, tier=TIER_SERVICE_REPO)
    assert path in rendered, (
        f"service-repo manifest missing inherited path: {path!r}"
    )


def test_inherited_paths_carry_inherited_marker(tmp_path: Path):
    """Each `../`-prefixed entry should be visually distinguished in the
    manifest via the INHERITED marker in its when_to_read text."""
    paths = _fixture_paths(tmp_path)
    rendered = render_manifest(paths, tier=TIER_SERVICE_REPO)
    # At minimum: the manifest must contain the INHERITED marker
    assert "INHERITED" in rendered, (
        "service-repo manifest should highlight parent-inherited paths via "
        "'INHERITED' markers in when_to_read text"
    )


def test_inherited_must_read_section_includes_parent_brief(tmp_path: Path):
    """Parent brief + rules + git should appear in the MUST_READ section
    (the most prominent block)."""
    paths = _fixture_paths(tmp_path)
    rendered = render_manifest(paths, tier=TIER_SERVICE_REPO)
    # Use the same split-by-marker style as test_manifest_coverage.py
    must_read = rendered.split("🔴  MUST READ", 1)[1].split("---", 1)[0]
    assert "../.agent/project_brief.md" in must_read
    assert "../.agent/rules.md" in must_read
    assert "../.agent/git.md" in must_read


def test_parent_contracts_dashboard_present(tmp_path: Path):
    """The cross-service rollup `../contracts.md` should be visible in
    the manifest so the AI knows to read it for sibling-service status."""
    paths = _fixture_paths(tmp_path)
    rendered = render_manifest(paths, tier=TIER_SERVICE_REPO)
    assert "../contracts.md" in rendered
    assert "../.agent/project/CONTRACTS.md" in rendered


def test_service_registry_present(tmp_path: Path):
    """`../docs/service-registry.md` is the entry point for navigating
    to sibling services — must be in the manifest."""
    paths = _fixture_paths(tmp_path)
    rendered = render_manifest(paths, tier=TIER_SERVICE_REPO)
    assert "../docs/service-registry.md" in rendered


def test_git_yaml_is_project_root_only_not_service_repo(tmp_path: Path):
    """`git.yaml` is the source of truth for branch rules and lives only
    at the project-root layer. Service-repos should NEVER surface it in
    their manifest — they read the rendered `git.md` dashboard instead.

    Regression: an earlier draft included `../.agent/git.yaml` as an
    INHERITED CAT_CONFIG entry. That's wrong: service-repo devs never
    edit YAML, only read the dashboard.
    """
    paths = _fixture_paths(tmp_path)
    rendered = render_manifest(paths, tier=TIER_SERVICE_REPO)
    schema_paths = {e.path for e in schema_for(TIER_SERVICE_REPO)}

    assert "../.agent/git.yaml" not in schema_paths, (
        "service-repo schema must not declare ../.agent/git.yaml — that's "
        "project-root scope. Use ../.agent/git.md (the dashboard) instead."
    )
    assert "../.agent/git.yaml" not in rendered, (
        "service-repo manifest leaked git.yaml — should be only the dashboard."
    )
    # And confirm the dashboard IS there:
    assert "../.agent/git.md" in rendered


def test_local_and_inherited_both_present_together(tmp_path: Path):
    """A service-repo manifest renders BOTH local and inherited entries —
    it's a single unified navigation index."""
    paths = _fixture_paths(tmp_path)
    rendered = render_manifest(paths, tier=TIER_SERVICE_REPO)
    # Local
    assert ".agent/project/modules/<id>/cycles/<NN>/contract.md" in rendered
    # Inherited
    assert "../.agent/project/plan.yaml" in rendered
