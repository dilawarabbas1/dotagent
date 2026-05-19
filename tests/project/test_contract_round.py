"""`dotagent project contract round` — round advancement on actor switch."""

from __future__ import annotations

from pathlib import Path

import pytest

from dotagent.project.contract import (
    ACTOR_DEV,
    ACTOR_QA,
    advance_round,
    init_contract,
)
from dotagent.project.model import ContractStatus

from ._helpers import make_project_with_module, setup_repo


def _initialized(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    init_contract(paths, module)
    return paths, module


def _edit_body(path: Path, marker: str) -> None:
    """Insert a substantive-body change above the negotiation-log anchor.

    Appending to EOF would land inside the log section and not move the
    content hash — that's by design for the convergence semantic.
    """
    body = path.read_text()
    anchor = "<!-- anchor: negotiation-log -->"
    idx = body.find(anchor)
    assert idx > 0
    path.write_text(body[:idx] + f"\n<!-- {marker} -->\n" + body[idx:])


def test_invalid_actor_side_raises(tmp_path: Path):
    paths, module = _initialized(tmp_path)
    with pytest.raises(ValueError):
        advance_round(paths, module, actor_side="opus")


def test_same_actor_resave_does_not_advance_round(tmp_path: Path):
    paths, module = _initialized(tmp_path)
    # init() already recorded round 1 for ACTOR_DEV with last_actor=claude.
    # A second write by Claude is a refinement — same round.
    _edit_body(paths.repo / module.current_cycle.contract.path, "claude tweak")
    contract = advance_round(paths, module, actor_side=ACTOR_DEV)

    assert contract.round == 1
    assert contract.status == ContractStatus.PROPOSED  # never flipped to counter
    assert contract.last_actor == ACTOR_DEV


def test_different_actor_advances_round(tmp_path: Path):
    paths, module = _initialized(tmp_path)
    # Codex writes a counter (substantive body edit)
    _edit_body(paths.repo / module.current_cycle.contract.path, "codex counter")
    contract = advance_round(paths, module, actor_side=ACTOR_QA)

    assert contract.round == 2
    assert contract.status == ContractStatus.COUNTER
    assert contract.last_actor == ACTOR_QA


def test_hashes_refresh_per_actor_side(tmp_path: Path):
    paths, module = _initialized(tmp_path)
    cp = paths.repo / module.current_cycle.contract.path
    original_proposal = module.current_cycle.contract.proposal_hash

    # Codex writes a counter — counter_hash gets set, proposal_hash unchanged.
    _edit_body(cp, "codex round")
    contract = advance_round(paths, module, actor_side=ACTOR_QA)
    counter_hash_after_codex = contract.counter_hash
    assert contract.proposal_hash == original_proposal
    assert counter_hash_after_codex
    assert counter_hash_after_codex != original_proposal

    # Claude refines — proposal_hash updates, counter_hash stays.
    _edit_body(cp, "claude refinement")
    contract = advance_round(paths, module, actor_side=ACTOR_DEV)
    assert contract.proposal_hash != original_proposal
    assert contract.counter_hash == counter_hash_after_codex


def test_round_appends_to_negotiation_log(tmp_path: Path):
    paths, module = _initialized(tmp_path)
    cp = paths.repo / module.current_cycle.contract.path

    _edit_body(cp, "codex counter")
    advance_round(paths, module, actor_side=ACTOR_QA)

    body = cp.read_text()
    assert "Round 2 counter by Codex" in body


def test_round_refuses_on_frozen_contract(tmp_path: Path):
    paths, module = _initialized(tmp_path)
    module.current_cycle.contract.status = ContractStatus.FROZEN
    with pytest.raises(PermissionError):
        advance_round(paths, module, actor_side=ACTOR_DEV)


def test_round_refuses_when_contract_file_missing(tmp_path: Path):
    paths, module = _initialized(tmp_path)
    (paths.repo / module.current_cycle.contract.path).unlink()
    with pytest.raises(FileNotFoundError):
        advance_round(paths, module, actor_side=ACTOR_DEV)
