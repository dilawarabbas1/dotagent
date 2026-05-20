"""Cross-repo contracts rollup (Tier 1) tests."""

from __future__ import annotations

from pathlib import Path

from dotagent.config import merge_defaults
from dotagent.paths import Paths
from dotagent.project.contract import freeze_contract, init_contract
from dotagent.project.contracts_rollup import (
    build_rollup,
    regenerate,
    render_markdown,
)
from dotagent.project.model import Project, save_module, save_project
from dotagent.scaffold import scaffold_agent_dir
from dotagent.util import dump_yaml

from ._helpers import make_project_with_module, setup_repo


def _setup_project_root_with_manifest(tmp_path: Path, repos: list[dict]) -> Paths:
    """A project-root repo with a `repos:` manifest pointing at sibling dirs."""
    root = tmp_path / "root"
    root.mkdir()
    paths = Paths(repo=root)
    scaffold_agent_dir(paths)
    dump_yaml(paths.config, merge_defaults({"project": {"name": "Demo"}}))
    project = Project(name="Demo", repos=repos)
    save_project(paths, project)
    return paths


def test_no_repos_manifest_returns_empty_rollup(tmp_path: Path):
    paths = _setup_project_root_with_manifest(tmp_path, [])
    rollup = build_rollup(paths)
    assert rollup.repos == []
    assert rollup.total_open == 0


def test_missing_repo_path_marked_error(tmp_path: Path):
    paths = _setup_project_root_with_manifest(tmp_path, [
        {"id": "phantom", "path": "./does-not-exist", "role": "api"},
    ])
    rollup = build_rollup(paths)
    assert len(rollup.repos) == 1
    assert rollup.repos[0].id == "phantom"
    assert "path missing" in rollup.repos[0].error


def test_rollup_walks_real_sibling_repo(tmp_path: Path):
    paths = _setup_project_root_with_manifest(tmp_path, [
        {"id": "backend", "path": "./backend", "role": "api"},
    ])
    # Create the sibling repo with a project + module + open contract
    backend = paths.repo / "backend"
    backend.mkdir()
    backend_paths = setup_repo(backend)
    _, mod = make_project_with_module(backend_paths)
    init_contract(backend_paths, mod)
    save_module(backend_paths, mod)

    rollup = build_rollup(paths)
    assert len(rollup.repos) == 1
    repo = rollup.repos[0]
    assert repo.id == "backend"
    assert repo.role == "api"
    assert repo.error == ""
    assert repo.open == 1
    assert repo.frozen == 0
    assert "CONTRACTS.md" in repo.contracts_index_path


def test_rollup_aggregates_across_multiple_repos(tmp_path: Path):
    paths = _setup_project_root_with_manifest(tmp_path, [
        {"id": "a", "path": "./a", "role": "api"},
        {"id": "b", "path": "./b", "role": "frontend"},
    ])
    # a: 1 open
    a = paths.repo / "a"
    a.mkdir()
    a_paths = setup_repo(a)
    _, ma = make_project_with_module(a_paths)
    init_contract(a_paths, ma)
    save_module(a_paths, ma)
    # b: 1 frozen
    b = paths.repo / "b"
    b.mkdir()
    b_paths = setup_repo(b)
    _, mb = make_project_with_module(b_paths, module_id="01-billing")
    init_contract(b_paths, mb)
    freeze_contract(b_paths, mb, force=True)
    save_module(b_paths, mb)

    rollup = build_rollup(paths)
    assert len(rollup.repos) == 2
    assert rollup.total_open == 1
    assert rollup.total_frozen == 1


def test_render_markdown_no_repos_message(tmp_path: Path):
    paths = _setup_project_root_with_manifest(tmp_path, [])
    md = render_markdown(build_rollup(paths))
    assert "No `repos:`" in md
    assert "GENERATED" in md


def test_render_markdown_with_repos_table(tmp_path: Path):
    paths = _setup_project_root_with_manifest(tmp_path, [
        {"id": "backend", "path": "./backend", "role": "api"},
    ])
    backend = paths.repo / "backend"
    backend.mkdir()
    backend_paths = setup_repo(backend)
    _, mod = make_project_with_module(backend_paths)
    init_contract(backend_paths, mod)
    save_module(backend_paths, mod)

    md = render_markdown(build_rollup(paths))
    assert "| Repo | Role |" in md
    assert "backend" in md
    assert "api" in md


def test_regenerate_writes_to_root_contracts_md(tmp_path: Path):
    paths = _setup_project_root_with_manifest(tmp_path, [])
    target = regenerate(paths)
    assert target == paths.repo / "contracts.md"
    assert target.exists()
    assert target.read_text().startswith("<!-- GENERATED")
