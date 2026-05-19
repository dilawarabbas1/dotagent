"""Shared test fixtures for the contract subcommand suite."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from dotagent.config import merge_defaults
from dotagent.paths import Paths
from dotagent.project.model import (
    Cycle,
    Module,
    ModulePlan,
    Project,
    save_module,
)
from dotagent.project.operations import add_module, init_project
from dotagent.scaffold import scaffold_agent_dir
from dotagent.util import dump_yaml


GOOD_CRITERIA = [
    "POST /auth/login returns 200 and a signed JWT for valid creds",
    "POST /auth/login returns 401 when password matches but user is disabled",
    "JWT verify matches the issuer's public key fingerprint",
]


def setup_repo(tmp_path: Path) -> Paths:
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    dump_yaml(paths.config, merge_defaults({"project": {"name": "demo"}}))
    return paths


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def make_project_with_module(
    paths: Paths,
    *,
    module_id: str = "01-auth",
    criteria: list[str] | None = None,
    purpose: str = "JWT issuance",
    in_scope: list[str] | None = None,
    out_of_scope: list[str] | None = None,
) -> tuple[Project, Module]:
    """Initialize a project + add a module with a populated ModulePlan + an active cycle."""
    project = Project(
        name="Demo Portal",
        goal="Ship JWT",
        created_at=now(),
        tools={
            "development": {"tool": "claude_code", "model": ""},
            "qa":          {"tool": "claude_code", "model": ""},
            "review":      {"tool": "claude_code", "model": ""},
            "planning":    {"tool": "claude_code", "model": ""},
        },
    )
    init_project(paths, project)
    plan = ModulePlan(
        purpose=purpose,
        in_scope=in_scope if in_scope is not None else ["login endpoint", "verify endpoint"],
        out_of_scope=out_of_scope if out_of_scope is not None else ["mobile SSO"],
        acceptance_criteria=criteria if criteria is not None else list(GOOD_CRITERIA),
        technical_approach="RS256 + Redis cache",
    )
    module = Module(id=module_id, name="Auth Service", plan=plan, created_at=now())
    add_module(paths, project, module)
    # Open a cycle 1 — the contract attaches to an active cycle.
    module.cycles.append(Cycle(n=1, started_at=now(), start_sha=""))
    save_module(paths, module)
    return project, module
