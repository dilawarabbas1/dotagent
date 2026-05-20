"""parent: field + layered context tests."""

from __future__ import annotations

from pathlib import Path

from dotagent.context import AgentSources
from dotagent.layered import (
    MAX_PARENT_DEPTH,
    merge_agent_sources,
    resolve_parent_chain,
)
from dotagent.paths import Paths


def _scaffold_agent(repo: Path, *, parent: str | None = None,
                    arch: str = "", rules: str = "") -> None:
    agent = repo / ".agent"
    agent.mkdir(parents=True, exist_ok=True)
    cfg_lines = ["name: demo"]
    if parent is not None:
        cfg_lines.append(f"parent: {parent}")
    (agent / "config.yaml").write_text("\n".join(cfg_lines) + "\n")
    if arch:
        (agent / "architecture.md").write_text(arch)
    if rules:
        (agent / "rules.md").write_text(rules)


def test_no_parent_field_returns_empty_chain(tmp_path: Path):
    _scaffold_agent(tmp_path, parent=None, arch="local arch\n")
    chain = resolve_parent_chain(Paths(repo=tmp_path))
    assert chain.repos == []


def test_parent_resolves_relative_path(tmp_path: Path):
    project_root = tmp_path / "project"
    service = tmp_path / "project" / "backend"
    project_root.mkdir()
    service.mkdir()

    _scaffold_agent(project_root, arch="ROOT arch\n")
    _scaffold_agent(service, parent="..", arch="service arch\n")

    chain = resolve_parent_chain(Paths(repo=service))
    assert len(chain.repos) == 1
    assert chain.repos[0] == project_root.resolve()


def test_missing_parent_path_returns_empty_chain(tmp_path: Path):
    _scaffold_agent(tmp_path, parent="../nonexistent", arch="x\n")
    chain = resolve_parent_chain(Paths(repo=tmp_path))
    assert chain.repos == []


def test_parent_without_agent_dir_skipped(tmp_path: Path):
    project_root = tmp_path / "project"
    service = tmp_path / "project" / "backend"
    project_root.mkdir()  # NO .agent/ here
    service.mkdir()
    _scaffold_agent(service, parent="..", arch="x\n")
    chain = resolve_parent_chain(Paths(repo=service))
    assert chain.repos == []


def test_cycle_detected(tmp_path: Path):
    """A → B → A should not loop."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    _scaffold_agent(a, parent="../b", arch="A\n")
    _scaffold_agent(b, parent="../a", arch="B\n")

    chain = resolve_parent_chain(Paths(repo=a))
    # Goes A → B; then B's parent is A which is already visited → stop.
    assert len(chain.repos) == 1
    assert chain.repos[0] == b.resolve()


def test_depth_capped(tmp_path: Path):
    """Chain longer than MAX_PARENT_DEPTH is truncated."""
    # Build N+2 deep chain
    chain_dirs = [tmp_path / f"d{i}" for i in range(MAX_PARENT_DEPTH + 2)]
    for d in chain_dirs:
        d.mkdir()
    # d0 → d1 → d2 → d3 → d4
    for i, d in enumerate(chain_dirs):
        parent = f"../d{i+1}" if i + 1 < len(chain_dirs) else None
        _scaffold_agent(d, parent=parent, arch=f"layer {i}\n")

    chain = resolve_parent_chain(Paths(repo=chain_dirs[0]))
    assert len(chain.repos) <= MAX_PARENT_DEPTH


def test_merge_overlays_parent_above_local(tmp_path: Path):
    project_root = tmp_path / "p"
    service = tmp_path / "p" / "svc"
    project_root.mkdir()
    service.mkdir()
    _scaffold_agent(project_root, arch="PROJECT arch\n", rules="PROJECT rules\n")
    _scaffold_agent(service, parent="..", arch="SERVICE arch\n", rules="SERVICE rules\n")

    paths = Paths(repo=service)
    chain = resolve_parent_chain(paths)
    local = AgentSources(
        architecture=(service / ".agent" / "architecture.md").read_text(),
        rules=(service / ".agent" / "rules.md").read_text(),
    )
    merged = merge_agent_sources(local, chain, paths)

    assert "PROJECT arch" in merged.architecture
    assert "SERVICE arch" in merged.architecture
    # Parent block appears BEFORE local
    assert merged.architecture.index("PROJECT") < merged.architecture.index("SERVICE")
    assert "inherited from parent" in merged.architecture


def test_merge_inherits_when_local_empty(tmp_path: Path):
    project_root = tmp_path / "p"
    service = tmp_path / "p" / "svc"
    project_root.mkdir()
    service.mkdir()
    _scaffold_agent(project_root, arch="PROJECT only\n")
    _scaffold_agent(service, parent="..")  # no local arch

    paths = Paths(repo=service)
    chain = resolve_parent_chain(paths)
    local = AgentSources()  # all empty
    merged = merge_agent_sources(local, chain, paths)
    assert "PROJECT only" in merged.architecture


def test_no_chain_passthrough_unchanged(tmp_path: Path):
    _scaffold_agent(tmp_path, arch="just me\n")
    paths = Paths(repo=tmp_path)
    chain = resolve_parent_chain(paths)
    assert chain.repos == []
    local = AgentSources(architecture="just me\n")
    merged = merge_agent_sources(local, chain, paths)
    assert merged.architecture == "just me\n"
