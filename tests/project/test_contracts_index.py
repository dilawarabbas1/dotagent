"""Tests for the Tier-2 contracts index (`.agent/project/CONTRACTS.md`)."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from dotagent.paths import Paths
from dotagent.project.contract import advance_round, freeze_contract, init_contract
from dotagent.project.contracts_index import (
    build_index,
    regenerate,
    render_markdown,
)
from dotagent.project.model import ContractStatus

from ._helpers import make_project_with_module, setup_repo


def test_empty_project_renders_no_modules_message(tmp_path: Path):
    paths = setup_repo(tmp_path)
    project, _ = make_project_with_module(paths)
    # Don't actually create any contracts; module exists but its cycle has no contract
    index = build_index(project)
    md = render_markdown(index)
    assert "Contracts in" in md
    assert "01-auth" in md  # module section header appears
    # Contract count is zero
    assert index.total_open == 0
    assert index.total_frozen == 0


def test_open_contract_appears_in_index(tmp_path: Path):
    paths = setup_repo(tmp_path)
    project, module = make_project_with_module(paths)
    init_contract(paths, module)

    index = build_index(project)
    assert index.total_open == 1
    assert index.total_frozen == 0
    section = index.sections[0]
    assert section.module_id == module.id
    assert len(section.rows) == 1
    assert section.rows[0].state == "open"


def test_frozen_contract_marked_frozen(tmp_path: Path):
    paths = setup_repo(tmp_path)
    project, module = make_project_with_module(paths)
    init_contract(paths, module)

    snapshot = freeze_contract(paths, module, force=True)
    assert snapshot.exists()

    index = build_index(project)
    assert index.total_open == 0
    assert index.total_frozen == 1
    row = index.sections[0].rows[0]
    assert row.state == "frozen"


def test_regenerate_writes_file(tmp_path: Path):
    paths = setup_repo(tmp_path)
    project, module = make_project_with_module(paths)
    init_contract(paths, module)

    target = regenerate(paths, project)
    assert target.exists()
    assert target.name == "CONTRACTS.md"
    body = target.read_text()
    assert body.startswith("<!-- GENERATED")
    assert "Contracts in" in body
    assert module.id in body


def test_index_to_dict_has_stable_shape(tmp_path: Path):
    paths = setup_repo(tmp_path)
    project, module = make_project_with_module(paths)
    init_contract(paths, module)

    payload = build_index(project).to_dict()
    assert set(payload.keys()) == {
        "project_name", "generated_at",
        "total_open", "total_frozen", "sections",
    }
    assert payload["total_open"] == 1
    assert payload["sections"][0]["module_id"] == module.id


def test_contracts_md_auto_regenerated_on_init_contract(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    target = paths.project_dir / "CONTRACTS.md"
    # PR #10 onwards: CONTRACTS.md is generated at add_module too.
    # Empty (no cycles yet) state present.
    assert target.exists()
    before = target.read_text()
    assert "0 open" in before

    init_contract(paths, module)
    after = target.read_text()
    assert "1 open" in after
    assert "Contracts in" in after


def test_contracts_md_updates_on_freeze(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    init_contract(paths, module)
    freeze_contract(paths, module, force=True)

    body = (paths.project_dir / "CONTRACTS.md").read_text()
    assert "frozen" in body
