"""Regression tests for the layered-tier plan.yaml schema.

Reported case: a plan.yaml with inline `modules:` (dict shape, no
top-level `name:`, no `module_ids:`) and `repos:` with `alias:`
fallback key — the contracts loader was producing empty dashboards
instead of populating them with the actual data.

These tests pin the read + write round-trip plus the rollup tolerance.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from dotagent.config import merge_defaults
from dotagent.paths import Paths
from dotagent.project.contracts_index import build_index, render_markdown
from dotagent.project.contracts_rollup import build_rollup
from dotagent.project.model import Module, Project, save_project, load_project
from dotagent.scaffold import scaffold_agent_dir
from dotagent.util import dump_yaml


# ---- read-side ----------------------------------------------------------

def test_inline_modules_dict_populates_project_modules():
    """plan.yaml with `modules: {M01: {...}, M02: {...}}` populates
    project.modules — previously ignored."""
    d = {
        "modules": {
            "M01": {"state": "planned",
                    "implements_features": ["FEAT-01"]},
            "M02": {"state": "in_progress",
                    "implements_features": ["FEAT-02"]},
        },
    }
    project = Project.from_dict(d)
    assert set(project.modules.keys()) == {"M01", "M02"}
    assert project.modules["M01"].state == "planned"
    assert project.modules["M01"].implements_features == ["FEAT-01"]
    assert project.modules["M02"].state == "in_progress"
    # module_ids is derived from inline modules
    assert "M01" in project.module_ids
    assert "M02" in project.module_ids


def test_inline_modules_list_shape_also_works():
    """plan.yaml with `modules: [{id: M01, ...}, ...]` (list shape)."""
    d = {
        "modules": [
            {"id": "M01", "state": "planned"},
            {"id": "M02", "state": "shipped"},
        ],
    }
    project = Project.from_dict(d)
    assert set(project.modules.keys()) == {"M01", "M02"}


def test_inline_modules_with_explicit_module_ids_unions_ordered():
    """If both module_ids and inline modules are present, module_ids ordering
    wins for ids it lists; inline-only entries are appended."""
    d = {
        "module_ids": ["M-second", "M-first"],
        "modules": {
            "M-first": {"state": "planned"},
            "M-second": {"state": "in_progress"},
            "M-third": {"state": "shipped"},      # not in module_ids
        },
    }
    project = Project.from_dict(d)
    assert project.module_ids == ["M-second", "M-first", "M-third"]


def test_extra_fields_in_inline_module_preserved_in_tools_inline():
    """Fields not on the Module dataclass (repo, owner, deps, integrations)
    are stashed in module.tools['_inline'] so they survive round-trip."""
    d = {
        "modules": {
            "M01": {
                "state": "planned",
                "repo": "backend",
                "owner": "alice",
                "deps": ["M00"],
                "integrations": ["stripe"],
            },
        },
    }
    project = Project.from_dict(d)
    inline = project.modules["M01"].tools.get("_inline") or {}
    assert inline.get("repo") == "backend"
    assert inline.get("owner") == "alice"
    assert inline.get("deps") == ["M00"]
    assert inline.get("integrations") == ["stripe"]


def test_thin_inline_module_gets_defaults():
    """A bare {state: planned} entry produces a valid Module without crashing."""
    d = {"modules": {"M01": {"state": "planned"}}}
    project = Project.from_dict(d)
    mod = project.modules["M01"]
    assert mod.id == "M01"
    assert mod.name == "M01"   # falls back to id
    assert mod.state == "planned"
    assert mod.cycles == []


def test_no_inline_modules_doesnt_break_old_shape():
    """Backward compat: a plan.yaml with module_ids but no inline modules:
    still works exactly as before."""
    d = {"name": "x", "module_ids": ["M01", "M02"]}
    project = Project.from_dict(d)
    assert project.module_ids == ["M01", "M02"]
    assert project.modules == {}


# ---- write-side / round-trip --------------------------------------------

def test_to_dict_emits_inline_modules():
    """save_project must round-trip the inline modules block, otherwise the
    layered-tier shape gets clobbered on the first save."""
    d = {
        "modules": {
            "M01": {"state": "planned", "implements_features": ["FEAT-01"]},
        },
    }
    project = Project.from_dict(d)
    payload = project.to_dict()
    assert "modules" in payload
    assert "M01" in payload["modules"]
    assert payload["modules"]["M01"]["state"] == "planned"
    assert payload["modules"]["M01"]["implements_features"] == ["FEAT-01"]


def test_full_roundtrip_preserves_inline_modules(tmp_path: Path):
    """Load → save → load → modules still there."""
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    dump_yaml(paths.config, merge_defaults({"project": {"name": "x"}}))

    initial = {
        "modules": {
            "M01": {"state": "planned", "implements_features": ["FEAT-01"],
                    "repo": "backend"},
            "M02": {"state": "shipped"},
        },
        "repos": [{"id": "backend", "path": "./backend",
                   "remote": "git@x:y.git", "default_branch": "main", "role": "api"}],
    }
    dump_yaml(paths.project_plan, initial)

    project = load_project(paths)
    assert "M01" in project.modules
    save_project(paths, project)

    project_after = load_project(paths)
    assert "M01" in project_after.modules
    assert project_after.modules["M01"].implements_features == ["FEAT-01"]
    assert "M02" in project_after.modules


# ---- contracts dashboards --------------------------------------------

def test_contracts_index_shows_inline_modules(tmp_path: Path):
    """build_index() now picks up inline modules — previously empty."""
    project = Project.from_dict({
        "name": "Aigent",
        "modules": {
            "M01-auth": {"state": "planned"},
            "M02-billing": {"state": "in_progress"},
        },
    })
    index = build_index(project)
    assert len(index.sections) == 2
    module_ids = {s.module_id for s in index.sections}
    assert module_ids == {"M01-auth", "M02-billing"}
    md = render_markdown(index)
    assert "M01-auth" in md
    assert "M02-billing" in md


# ---- rollup --------------------------------------------

def test_rollup_accepts_alias_as_id_fallback(tmp_path: Path):
    """repos[] entries using `alias:` instead of `id:` still produce rows."""
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    dump_yaml(paths.config, merge_defaults({"project": {"name": "Aigent"}}))
    dump_yaml(paths.project_plan, {
        "name": "Aigent",
        "repos": [
            # Two shapes that should both work:
            {"id": "backend", "path": "./backend", "role": "api"},
            {"alias": "portal", "path": "./portal", "role": "frontend"},
        ],
    })
    (paths.repo / "backend").mkdir()
    (paths.repo / "portal").mkdir()

    rollup = build_rollup(paths)
    repo_ids = {r.id for r in rollup.repos}
    assert "backend" in repo_ids
    assert "portal" in repo_ids
