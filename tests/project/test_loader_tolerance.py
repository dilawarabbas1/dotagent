"""Loader-tolerance regression tests.

Reported case: a plan.yaml with the layered-tier shape
(`brief_features_covered`, `features_to_modules`, `modules`, `repos`) but
no top-level `name:` key crashed `dotagent project contracts rebuild` with
KeyError: 'name'. These tests pin the tolerance so that doesn't recur.
"""

from __future__ import annotations

from dotagent.project.model import Module, ModulePlan, Project


def test_project_from_dict_tolerates_missing_name():
    """plan.yaml without `name:` should parse, not KeyError."""
    d = {
        # No name. New layered-tier shape.
        "goal": "",
        "brief_features_covered": ["FEAT-01", "FEAT-02"],
        "features_to_modules": {"FEAT-01": ["M01"]},
        "modules": {},
        "repos": [
            {"id": "backend", "path": "./backend",
             "remote": "git@x:y/z.git", "default_branch": "main", "role": "api"},
        ],
    }
    project = Project.from_dict(d)
    assert project.name == ""
    assert project.brief_features_covered == ["FEAT-01", "FEAT-02"]
    assert len(project.repos) == 1


def test_project_from_dict_explicit_name_still_works():
    """Backward compat: an explicit name is still preserved verbatim."""
    project = Project.from_dict({"name": "Aigent", "goal": "ship"})
    assert project.name == "Aigent"
    assert project.goal == "ship"


def test_project_to_dict_preserves_empty_name():
    """Round-trip: empty name stays empty, not None."""
    project = Project.from_dict({"goal": "x"})
    payload = project.to_dict()
    assert payload["name"] == ""
    re_loaded = Project.from_dict(payload)
    assert re_loaded.name == ""


def test_module_from_dict_tolerates_missing_name():
    """Same defensiveness for Module — name falls back to id."""
    d = {
        "id": "M01-auth",
        # No name.
        "state": "planned",
        "plan": {},
        "cycles": [],
    }
    mod = Module.from_dict(d)
    assert mod.id == "M01-auth"
    # Falls back to id rather than KeyError
    assert mod.name == "M01-auth"


def test_module_from_dict_tolerates_missing_id_and_name():
    """Both id and name missing → both empty, not crash."""
    mod = Module.from_dict({"state": "planned"})
    assert mod.id == ""
    assert mod.name == ""


def test_module_from_dict_explicit_name_wins():
    """Backward compat for modules with explicit name."""
    mod = Module.from_dict({
        "id": "M01", "name": "Auth service",
        "state": "planned", "plan": {}, "cycles": [],
    })
    assert mod.id == "M01"
    assert mod.name == "Auth service"


def test_project_from_dict_with_repos_and_modules_and_no_name():
    """Full layered-tier shape — the exact reported failure case."""
    d = {
        "brief_features_covered": ["FEAT-01", "FEAT-02", "FEAT-03"],
        "features_to_modules": {
            "FEAT-01": ["M01"],
            "FEAT-02": ["M02"],
        },
        "modules": {
            "M01": {"id": "M01", "repo": "backend", "owner": "alice", "state": "planned"},
            "M02": {"id": "M02", "repo": "backend", "owner": "alice", "state": "in_progress"},
        },
        "repos": [
            {"id": "backend", "path": "./backend",
             "remote": "git@github.com:org/be.git",
             "default_branch": "main", "role": "api"},
        ],
    }
    # Must not raise
    project = Project.from_dict(d)
    assert project.name == ""
    assert len(project.repos) == 1
    assert "FEAT-01" in project.features_to_modules
