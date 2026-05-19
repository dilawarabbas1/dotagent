"""`freeze` refuses on a migration-bearing contract with S10=0 unless --force."""

from __future__ import annotations

from pathlib import Path

import pytest

from dotagent.project.contract import (
    ACTOR_DEV,
    ACTOR_QA,
    advance_round,
    freeze_contract,
    init_contract,
)

from ._helpers import make_project_with_module, setup_repo


def _force_convergence(paths, module):
    """Drive the contract to converged so freeze's convergence gate passes;
    the rollback gate is what we're isolating in these tests."""
    init_contract(paths, module)
    contract_path = paths.repo / module.current_cycle.contract.path
    body = contract_path.read_text()
    anchor = "<!-- anchor: negotiation-log -->"
    idx = body.find(anchor)
    contract_path.write_text(body[:idx] + "\n<!-- codex substantive counter -->\n" + body[idx:])
    advance_round(paths, module, actor_side=ACTOR_QA)
    advance_round(paths, module, actor_side=ACTOR_DEV)


def _inject_migration_no_rollback(paths, module):
    """After convergence, edit the contract so doc-surfaces names a migration
    and rollback-plan stays empty. This is the S10=0 with migration-trigger
    case the rollback gate is supposed to catch. Re-advances rounds so the
    contract remains converged after the edit — we want freeze's rollback
    gate to fire, not its convergence gate."""
    contract_path = paths.repo / module.current_cycle.contract.path
    text = contract_path.read_text()

    text = text.replace(
        "<!-- anchor: doc-surfaces -->\n## Doc surfaces to update\n",
        "<!-- anchor: doc-surfaces -->\n## Doc surfaces to update\n\n"
        "- `migrations/2026_06_jwt_keys.sql` — alembic migration\n",
        1,
    )
    contract_path.write_text(text)

    # Restore convergence: both sides accept the new body unchanged.
    advance_round(paths, module, actor_side=ACTOR_QA)
    advance_round(paths, module, actor_side=ACTOR_DEV)


def test_freeze_refuses_when_migration_present_and_no_rollback(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    _force_convergence(paths, module)
    _inject_migration_no_rollback(paths, module)

    with pytest.raises(PermissionError, match="S10"):
        freeze_contract(paths, module)


def test_force_overrides_the_rollback_gate(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    _force_convergence(paths, module)
    _inject_migration_no_rollback(paths, module)

    snapshot = freeze_contract(paths, module, force=True)

    assert snapshot.exists()
    # the snapshot header notes the forced freeze
    head = snapshot.read_text().splitlines()[0]
    assert "(forced)" in head


def test_freeze_passes_when_migration_present_with_real_rollback(tmp_path: Path):
    """Sanity: with a real rollback plan, the gate does not fire."""
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    _force_convergence(paths, module)
    # Edit the converged contract: add a migration AND a real rollback plan.
    contract_path = paths.repo / module.current_cycle.contract.path
    text = contract_path.read_text()
    text = text.replace(
        "<!-- anchor: doc-surfaces -->\n## Doc surfaces to update\n",
        "<!-- anchor: doc-surfaces -->\n## Doc surfaces to update\n\n"
        "- `migrations/2026_06_jwt_keys.sql` — alembic migration\n",
    )
    text = text.replace(
        "<!-- anchor: rollback-plan -->\n## Rollback plan\n",
        "<!-- anchor: rollback-plan -->\n## Rollback plan\n\n"
        "- `alembic downgrade -1` reverts the 2026_06 migration; smoke test "
        "`auth_smoke.test.py::test_post_revert_health` asserts post-revert "
        "audit log writes\n",
    )
    contract_path.write_text(text)
    # Re-advance rounds so convergence still holds after our edits.
    advance_round(paths, module, actor_side=ACTOR_QA)
    advance_round(paths, module, actor_side=ACTOR_DEV)

    snapshot = freeze_contract(paths, module)
    assert snapshot.exists()
    assert "(forced)" not in snapshot.read_text().splitlines()[0]


def test_freeze_unaffected_when_no_migration_trigger(tmp_path: Path):
    """If the contract has no migration trigger at all, the rollback gate is silent."""
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    _force_convergence(paths, module)
    # The baseline contract from make_project_with_module has no migration in
    # its (placeholder) doc-surfaces. Freezing it must not raise.
    snapshot = freeze_contract(paths, module)
    assert snapshot.exists()
