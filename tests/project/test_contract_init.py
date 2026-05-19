"""`dotagent project contract init` — template renders all anchors;
acceptance criteria flow through verbatim from the module's `ModulePlan`."""

from __future__ import annotations

from pathlib import Path

import pytest

from dotagent.project.contract import (
    ACTOR_DEV,
    SECTION_ANCHORS,
    contract_path,
    init_contract,
)
from dotagent.project.model import ContractStatus

from ._helpers import GOOD_CRITERIA, make_project_with_module, setup_repo


def test_init_writes_contract_with_every_required_anchor(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)

    contract = init_contract(paths, module)

    body = (paths.repo / contract.path).read_text()
    for anchor in SECTION_ANCHORS:
        assert f"<!-- anchor: {anchor} -->" in body, f"missing anchor: {anchor}"


def test_init_carries_acceptance_criteria_verbatim(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)

    contract = init_contract(paths, module)
    body = (paths.repo / contract.path).read_text()

    for i, criterion in enumerate(GOOD_CRITERIA, 1):
        assert f"{i}. {criterion}" in body, f"criterion {i} not rendered verbatim"


def test_init_writes_to_canonical_cycle_path(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)

    contract = init_contract(paths, module)

    expected = contract_path(paths, module.id, module.current_cycle.n)
    assert (paths.repo / contract.path) == expected
    assert expected.exists()


def test_init_records_proposal_hash_status_round_and_actor(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)

    contract = init_contract(paths, module)

    assert contract.status == ContractStatus.PROPOSED
    assert contract.round == 1
    assert contract.rounds_max == 3
    assert contract.proposal_hash.startswith("sha256:")
    # the hash is 64 hex chars after the prefix
    assert len(contract.proposal_hash.split(":", 1)[1]) == 64
    assert contract.counter_hash == ""
    assert contract.last_actor == ACTOR_DEV
    # the contract is now attached to the cycle on the module
    assert module.current_cycle.contract is contract


def test_init_refuses_when_contract_already_exists(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    init_contract(paths, module)

    with pytest.raises(FileExistsError):
        init_contract(paths, module)


def test_init_refuses_when_no_active_cycle(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    module.cycles = []  # drop the cycle the helper created

    with pytest.raises(ValueError):
        init_contract(paths, module)


def test_init_renders_purpose_and_in_scope_lines(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(
        paths,
        purpose="Issue and verify JWTs",
        in_scope=["a", "b", "c"],
    )

    contract = init_contract(paths, module)
    body = (paths.repo / contract.path).read_text()

    assert "Issue and verify JWTs" in body
    for item in ["a", "b", "c"]:
        assert f"- {item}" in body


def test_init_negotiation_log_starts_with_round_1_proposal(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)

    contract = init_contract(paths, module)
    body = (paths.repo / contract.path).read_text()

    assert "<!-- anchor: negotiation-log -->" in body
    assert "Round 1 proposal by Claude" in body
