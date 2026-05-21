"""Tests for `--from-stdin` headless primitives:

- `dotagent project brief upload --from-stdin --force`
- `dotagent project init --from-stdin`
- `dotagent project add-module --from-stdin`

All three are the dotagent-side of Coda's project-onboarding flow.
Coda gathers intent in conversation with the user, builds the JSON
payloads, and pipes them to these commands.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from dotagent.commands.brief_cmd import upload_cmd
from dotagent.commands.project_cmd import cmd_add_module, cmd_init
from dotagent.config import merge_defaults
from dotagent.paths import Paths
from dotagent.scaffold import scaffold_agent_dir
from dotagent.util import dump_yaml


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    paths = Paths(repo=repo)
    scaffold_agent_dir(paths)
    dump_yaml(paths.config, merge_defaults({"project": {"name": "TestProj"}}))
    return repo


def _invoke(repo: Path, cmd, args, stdin: str = "") -> object:
    cwd = os.getcwd()
    os.chdir(repo)
    try:
        return CliRunner().invoke(cmd, args, input=stdin, catch_exceptions=False)
    finally:
        os.chdir(cwd)


# ---------------------------------------------------------------------------
# brief upload --from-stdin
# ---------------------------------------------------------------------------

_BRIEF_MD = """# Project brief: Aigent

**Last reviewed:** 2026-05-20  ·  **Brief version:** 1  ·  **Owner:** alice  ·  **Stage:** seed

## Vision (one sentence)
Multi-tenant AI customer-service platform.

## Business objectives
- **OBJ-01**: Ship JWT auth with tenant claims by 2026-Q3.
- **OBJ-02**: Sub-300ms p99 on chat responses by 2026-Q4.

## Features

### FEAT-01 · Auth
**Serves:** OBJ-01
**Expected outcome:** Token rotation works under load.
**What it must do:**
- JWT with tenant id

## Hard rules
- **RULE-01 · Tenant isolation** — _why: data leaks are existential; how: tenant id in every token claim_
"""


def test_brief_upload_from_stdin_writes_file(project_root: Path):
    result = _invoke(
        project_root, upload_cmd, ["--from-stdin", "--force"], stdin=_BRIEF_MD,
    )
    assert result.exit_code == 0, result.output
    target = project_root / ".agent" / "project_brief.md"
    assert target.exists()
    assert "OBJ-01" in target.read_text()
    assert "FEAT-01" in target.read_text()


def test_brief_upload_from_stdin_json_receipt(project_root: Path):
    result = _invoke(
        project_root, upload_cmd,
        ["--from-stdin", "--force", "--format", "json"],
        stdin=_BRIEF_MD,
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["path"] == ".agent/project_brief.md"
    assert payload["source"] == "<stdin>"
    assert payload["parsed"]["objectives"] == 2
    assert payload["parsed"]["features"] == 1
    assert payload["parsed"]["hard_rules"] == 1
    assert payload["name"] == "Aigent"


def test_brief_upload_from_stdin_refuses_without_force_when_exists(
    project_root: Path,
):
    target = project_root / ".agent" / "project_brief.md"
    target.write_text("existing")
    result = _invoke(
        project_root, upload_cmd, ["--from-stdin"], stdin=_BRIEF_MD,
    )
    assert result.exit_code != 0
    assert "--force" in result.output


def test_brief_upload_rejects_both_path_and_stdin(project_root: Path, tmp_path: Path):
    f = tmp_path / "x.md"
    f.write_text("y")
    result = _invoke(
        project_root, upload_cmd, [str(f), "--from-stdin", "--force"], stdin="z",
    )
    assert result.exit_code == 2
    assert "mutually exclusive" in result.output


def test_brief_upload_rejects_neither_path_nor_stdin(project_root: Path):
    result = _invoke(project_root, upload_cmd, ["--force"])
    assert result.exit_code == 2
    assert "PATH or --from-stdin" in result.output


# ---------------------------------------------------------------------------
# project init --from-stdin
# ---------------------------------------------------------------------------

def test_project_init_from_stdin_writes_plan(project_root: Path):
    payload = {
        "name": "Aigent",
        "goal": "AI customer-service platform",
        "description": "Multi-tenant agent platform",
        "success_criteria": ["p99 < 300ms", "tenant isolation 100%"],
        "stakeholders": ["alice", "bob"],
    }
    result = _invoke(
        project_root, cmd_init,
        ["--from-stdin", "--format", "json"],
        stdin=json.dumps(payload),
    )
    assert result.exit_code == 0, result.output
    receipt = json.loads(result.output)
    assert receipt["ok"] is True
    assert receipt["name"] == "Aigent"
    assert (project_root / ".agent" / "project" / "plan.yaml").exists()
    assert (project_root / ".agent" / "project" / "SCOPE.md").exists()


def test_project_init_from_stdin_requires_name(project_root: Path):
    result = _invoke(
        project_root, cmd_init, ["--from-stdin"], stdin="{}",
    )
    assert result.exit_code == 2
    assert "name" in result.output


def test_project_init_from_stdin_invalid_json(project_root: Path):
    result = _invoke(
        project_root, cmd_init, ["--from-stdin"], stdin="this is not json",
    )
    assert result.exit_code == 2
    assert "invalid JSON" in result.output


def test_project_init_from_stdin_refuses_when_already_initialized(project_root: Path):
    payload = {"name": "Aigent"}
    _invoke(project_root, cmd_init, ["--from-stdin"], stdin=json.dumps(payload))
    # Second call must refuse
    result = _invoke(
        project_root, cmd_init,
        ["--from-stdin", "--format", "json"],
        stdin=json.dumps(payload),
    )
    assert result.exit_code != 0
    receipt = json.loads(result.output)
    assert receipt["ok"] is False
    assert receipt["error"] == "already-initialized"


# ---------------------------------------------------------------------------
# project add-module --from-stdin
# ---------------------------------------------------------------------------

def _init_project(project_root: Path):
    _invoke(
        project_root, cmd_init,
        ["--from-stdin"],
        stdin=json.dumps({"name": "Aigent", "goal": "test"}),
    )


def test_add_module_from_stdin_writes_module_and_plan(project_root: Path):
    _init_project(project_root)
    payload = {
        "name": "Auth",
        "implements_features": ["FEAT-01"],
        "plan": {
            "purpose": "JWT auth with tenant claims",
            "in_scope": ["login", "logout", "refresh"],
            "out_of_scope": ["password reset"],
            "acceptance_criteria": [
                "tenant id in every claim",
                "refresh rotates",
                "session expiry honored",
            ],
            "dependencies": [],
            "technical_approach": "JWT signed by KMS",
            "risks": ["token replay"],
        },
    }
    result = _invoke(
        project_root, cmd_add_module,
        ["--from-stdin", "--format", "json"],
        stdin=json.dumps(payload),
    )
    assert result.exit_code == 0, result.output
    receipt = json.loads(result.output)
    assert receipt["ok"] is True
    assert receipt["id"] == "01-auth"
    assert receipt["state"] == "planned"
    assert receipt["implements_features"] == ["FEAT-01"]
    assert receipt["acceptance_criteria_count"] == 3
    assert (project_root / ".agent" / "project" / "modules" / "01-auth" / "module.yaml").exists()
    assert (project_root / ".agent" / "project" / "modules" / "01-auth" / "PLAN.md").exists()


def test_add_module_from_stdin_minimum_payload(project_root: Path):
    _init_project(project_root)
    # Bare minimum — just a name
    result = _invoke(
        project_root, cmd_add_module,
        ["--from-stdin", "--format", "json"],
        stdin=json.dumps({"name": "Quickstart"}),
    )
    assert result.exit_code == 0, result.output
    receipt = json.loads(result.output)
    assert receipt["id"] == "01-quickstart"
    assert receipt["acceptance_criteria_count"] == 0


def test_add_module_from_stdin_supports_cross_module(project_root: Path):
    _init_project(project_root)
    payload = {
        "name": "AuthSlice",
        "cross_module": "auth-shared",
        "plan": {"purpose": "slice of cross-service auth"},
    }
    result = _invoke(
        project_root, cmd_add_module,
        ["--from-stdin", "--format", "json"],
        stdin=json.dumps(payload),
    )
    assert result.exit_code == 0
    receipt = json.loads(result.output)
    assert receipt["cross_module"] == "auth-shared"


def test_add_module_from_stdin_requires_name(project_root: Path):
    _init_project(project_root)
    result = _invoke(
        project_root, cmd_add_module, ["--from-stdin"], stdin="{}",
    )
    assert result.exit_code == 2
    assert "name" in result.output


def test_add_module_from_stdin_explicit_id_overrides_default(project_root: Path):
    _init_project(project_root)
    payload = {
        "id": "99-custom",
        "name": "Custom",
    }
    result = _invoke(
        project_root, cmd_add_module,
        ["--from-stdin", "--format", "json"],
        stdin=json.dumps(payload),
    )
    assert result.exit_code == 0
    receipt = json.loads(result.output)
    assert receipt["id"] == "99-custom"


# ---------------------------------------------------------------------------
# End-to-end Coda-style onboarding
# ---------------------------------------------------------------------------

def test_full_onboarding_flow(project_root: Path):
    """The complete sequence Coda would run: brief upload → project init →
    add-module. Verify the receipts wire together cleanly."""
    # 1. Brief
    r1 = _invoke(
        project_root, upload_cmd,
        ["--from-stdin", "--force", "--format", "json"],
        stdin=_BRIEF_MD,
    )
    assert r1.exit_code == 0
    brief_receipt = json.loads(r1.output)
    assert brief_receipt["name"] == "Aigent"
    assert brief_receipt["parsed"]["objectives"] == 2

    # 2. Project
    r2 = _invoke(
        project_root, cmd_init,
        ["--from-stdin", "--format", "json"],
        stdin=json.dumps({
            "name": brief_receipt["name"],
            "goal": brief_receipt["vision"],
            "brief": ".agent/project_brief.md",
            "brief_version": 1,
            "brief_objectives_covered": ["OBJ-01", "OBJ-02"],
            "brief_features_covered": ["FEAT-01"],
        }),
    )
    assert r2.exit_code == 0, r2.output
    project_receipt = json.loads(r2.output)
    assert project_receipt["ok"] is True

    # 3. First module
    r3 = _invoke(
        project_root, cmd_add_module,
        ["--from-stdin", "--format", "json"],
        stdin=json.dumps({
            "name": "Auth",
            "implements_features": ["FEAT-01"],
            "plan": {
                "purpose": "JWT with tenant id",
                "acceptance_criteria": ["RULE-01 enforced"],
            },
        }),
    )
    assert r3.exit_code == 0, r3.output
    module_receipt = json.loads(r3.output)
    assert module_receipt["id"] == "01-auth"

    # All three artifacts exist on disk
    assert (project_root / ".agent" / "project_brief.md").exists()
    assert (project_root / ".agent" / "project" / "plan.yaml").exists()
    assert (project_root / ".agent" / "project" / "modules" / "01-auth" / "PLAN.md").exists()
