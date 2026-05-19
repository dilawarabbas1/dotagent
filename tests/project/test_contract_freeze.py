"""`dotagent project contract freeze` — freeze gate + snapshot."""

from __future__ import annotations

from pathlib import Path

import pytest

from dotagent.project.contract import (
    ACTOR_DEV,
    ACTOR_QA,
    advance_round,
    freeze_contract,
    frozen_snapshot_path,
    init_contract,
)
from dotagent.project.model import ContractStatus

from ._helpers import make_project_with_module, setup_repo


def test_freeze_without_convergence_refuses(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    init_contract(paths, module)
    # round 1 only — not converged
    with pytest.raises(PermissionError):
        freeze_contract(paths, module)


def test_freeze_with_force_succeeds_even_without_convergence(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    init_contract(paths, module)

    snapshot = freeze_contract(paths, module, force=True)

    assert snapshot.exists()
    assert module.current_cycle.contract.status == ContractStatus.FROZEN
    assert "(forced)" in snapshot.read_text().splitlines()[0]


def test_freeze_after_convergence_writes_snapshot_and_sets_state(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    init_contract(paths, module)
    cp = paths.repo / module.current_cycle.contract.path

    # codex edits the substantive body (above the negotiation-log anchor)
    body = cp.read_text()
    anchor = "<!-- anchor: negotiation-log -->"
    idx = body.find(anchor)
    cp.write_text(body[:idx] + "\n<!-- codex substantive counter -->\n" + body[idx:])
    advance_round(paths, module, actor_side=ACTOR_QA)
    advance_round(paths, module, actor_side=ACTOR_DEV)  # claude accepts unchanged

    snapshot = freeze_contract(paths, module)

    assert snapshot.exists()
    assert snapshot == frozen_snapshot_path(paths, module.id, module.current_cycle.n)
    body = snapshot.read_text()
    assert body.splitlines()[0].startswith("<!-- frozen at ")
    contract = module.current_cycle.contract
    assert contract.status == ContractStatus.FROZEN
    assert contract.frozen_at
    assert contract.frozen_by
    # NOT a `(forced)` freeze — the prefix should be the plain "frozen at ... by ..."
    assert "(forced)" not in body.splitlines()[0]


def test_freeze_snapshot_is_read_only(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    init_contract(paths, module)

    snapshot = freeze_contract(paths, module, force=True)

    mode = snapshot.stat().st_mode & 0o777
    # Best-effort permission; some sandbox filesystems strip the bit, so we
    # tolerate that — but if any writable bit is set, the freeze is broken.
    if mode != 0:
        assert mode & 0o222 == 0, f"snapshot is writable (mode={oct(mode)})"


def test_freeze_refuses_on_validate_failure(tmp_path: Path):
    """A contract that fails `validate` cannot be frozen — even after
    convergence. --force still overrides."""
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    init_contract(paths, module)
    cp = paths.repo / module.current_cycle.contract.path

    # Drive to convergence so the convergence gate would otherwise pass.
    body = cp.read_text()
    anchor = "<!-- anchor: negotiation-log -->"
    idx = body.find(anchor)
    cp.write_text(body[:idx] + "\n<!-- codex substantive counter -->\n" + body[idx:])
    advance_round(paths, module, actor_side=ACTOR_QA)
    advance_round(paths, module, actor_side=ACTOR_DEV)

    # Break the schema: strip the rollback-plan anchor → validate fails.
    broken = cp.read_text().replace("<!-- anchor: rollback-plan -->", "")
    cp.write_text(broken)

    with pytest.raises(PermissionError, match="rollback-plan"):
        freeze_contract(paths, module)

    # --force overrides validate (and every other gate).
    snapshot = freeze_contract(paths, module, force=True)
    assert snapshot.exists()
    assert module.current_cycle.contract.status == ContractStatus.FROZEN


def test_freeze_is_idempotent(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    init_contract(paths, module)

    snapshot_a = freeze_contract(paths, module, force=True)
    first_frozen_at = module.current_cycle.contract.frozen_at

    snapshot_b = freeze_contract(paths, module)  # already frozen; no-op

    assert snapshot_a == snapshot_b
    assert module.current_cycle.contract.frozen_at == first_frozen_at
