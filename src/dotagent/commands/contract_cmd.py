"""`dotagent project contract` subcommand group.

Verbs: init, validate, round, diff, freeze, show.

The actual logic lives in `dotagent.project.contract`; this module is the
thin Click wrapper. Exits:
- `validate` exits 2 on schema violations (0 on pass).
- `freeze` exits 1 on non-convergence without `--force`.
- All others exit 0 on success.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from ..paths import Paths, find_repo_root
from ..project import contract as ct
from ..project.contract import ACTOR_DEV, ACTOR_QA, KNOWN_ACTORS
from ..project.model import save_module
from ..project.operations import require_project


def _paths() -> Paths:
    repo = find_repo_root()
    paths = Paths(repo=repo)
    if not paths.agent.exists():
        raise click.ClickException("No .agent/ in this repo. Run `dotagent init` first.")
    return paths


def _module_or_die(paths: Paths, module_id: str):
    project = require_project(paths)
    if module_id not in project.modules:
        raise click.ClickException(f"unknown module {module_id!r}")
    return project, project.modules[module_id]


@click.group(name="contract", help="Per-cycle pre-build contract: init / validate / round / diff / freeze / show.")
def contract_group() -> None:
    pass


# ---- init ------------------------------------------------------------------

@contract_group.command(name="init", help="Render the cycle's contract.md template from the module's plan.")
@click.argument("module_id")
def cmd_init(module_id: str) -> None:
    paths = _paths()
    _, module = _module_or_die(paths, module_id)
    try:
        contract = ct.init_contract(paths, module)
    except (FileExistsError, PermissionError, ValueError) as e:
        raise click.ClickException(str(e))
    save_module(paths, module)
    click.echo(f"✓ contract initialized → {contract.path}")
    click.echo(f"  status={contract.status} round={contract.round}/{contract.rounds_max}")
    click.echo(f"  proposal_hash={contract.proposal_hash}")


# ---- validate --------------------------------------------------------------

@contract_group.command(name="validate", help="Schema-check the contract.md. Exits 2 on violations.")
@click.argument("module_id")
def cmd_validate(module_id: str) -> None:
    paths = _paths()
    _, module = _module_or_die(paths, module_id)
    if not module.current_cycle or not module.current_cycle.contract:
        raise click.ClickException(
            f"no contract on cycle of {module_id} — run `dotagent project contract init` first"
        )
    path = paths.repo / module.current_cycle.contract.path
    result = ct.validate_contract(path)
    if result.ok:
        click.echo(f"✓ contract OK ({path.relative_to(paths.repo)})")
        return
    click.echo(f"✗ contract failed validation ({len(result.violations)} violation(s)):", err=True)
    for i, v in enumerate(result.violations, 1):
        click.echo(f"  {i}. {v}", err=True)
    sys.exit(2)


# ---- round ----------------------------------------------------------------

@contract_group.command(name="round", help="Record an agent's write. Advances round if actor differs from previous.")
@click.argument("module_id")
@click.option("--as", "actor_side", type=click.Choice(list(KNOWN_ACTORS)), required=True,
              help="Which agent just wrote the contract: claude (dev) or codex (QA).")
def cmd_round(module_id: str, actor_side: str) -> None:
    paths = _paths()
    _, module = _module_or_die(paths, module_id)
    try:
        contract = ct.advance_round(paths, module, actor_side=actor_side)
    except (FileNotFoundError, PermissionError, ValueError) as e:
        raise click.ClickException(str(e))
    save_module(paths, module)
    click.echo(f"✓ round recorded: actor={actor_side}, round={contract.round}/{contract.rounds_max}, "
               f"status={contract.status}")
    label = "proposal_hash" if actor_side == ACTOR_DEV else "counter_hash"
    h = contract.proposal_hash if actor_side == ACTOR_DEV else contract.counter_hash
    click.echo(f"  {label}={h}")


# ---- diff ------------------------------------------------------------------

@contract_group.command(name="diff", help="Print convergence status. Always exits 0; caller parses JSON.")
@click.argument("module_id")
def cmd_diff(module_id: str) -> None:
    """Emit `{path, round, hash, converged, reason}` as JSON.

    Integrator note: the `hash` field is the full-file sha256 of contract.md
    (stable id for the current on-disk state). The `converged` field is
    computed from CONTENT hashes — the body before the negotiation-log
    anchor — and is what callers (coda) should branch on. Comparing `hash`
    values across rounds will always show drift because dotagent appends to
    the log on every `round` call; that is by design.
    """
    paths = _paths()
    _, module = _module_or_die(paths, module_id)
    result = ct.diff_contract(paths, module)
    click.echo(json.dumps(result.to_dict(), indent=2))


# ---- freeze ----------------------------------------------------------------

@contract_group.command(name="freeze", help="Freeze the contract (must be converged unless --force).")
@click.argument("module_id")
@click.option("--force", is_flag=True, help="Freeze even if the contract has not converged.")
def cmd_freeze(module_id: str, force: bool) -> None:
    paths = _paths()
    _, module = _module_or_die(paths, module_id)
    try:
        snapshot = ct.freeze_contract(paths, module, force=force)
    except (FileNotFoundError, PermissionError, ValueError) as e:
        # PermissionError from non-convergence is the user-facing common case;
        # exit 1 with the diagnostic.
        click.echo(f"✗ freeze refused: {e}", err=True)
        sys.exit(1)
    save_module(paths, module)
    rel = snapshot.relative_to(paths.repo)
    contract = module.current_cycle.contract
    click.echo(f"✓ frozen — snapshot at {rel}")
    click.echo(f"  frozen_at={contract.frozen_at} frozen_by={contract.frozen_by}")


# ---- show ------------------------------------------------------------------

@contract_group.command(name="show", help="Pretty-print contract status + body.")
@click.argument("module_id")
def cmd_show(module_id: str) -> None:
    paths = _paths()
    _, module = _module_or_die(paths, module_id)
    if not module.current_cycle or not module.current_cycle.contract:
        click.echo(f"(no contract on current cycle of {module_id})")
        return
    c = module.current_cycle.contract
    click.echo(f"=== contract for {module.id} cycle {module.current_cycle.n} ===")
    click.echo(f"path:           {c.path}")
    click.echo(f"status:         {c.status}")
    click.echo(f"round:          {c.round} / {c.rounds_max}")
    click.echo(f"last actor:     {c.last_actor or '(none)'}")
    click.echo(f"proposal hash:  {c.proposal_hash or '(none)'}")
    click.echo(f"counter hash:   {c.counter_hash or '(none)'}")
    if c.frozen_at:
        click.echo(f"frozen at:      {c.frozen_at}")
        click.echo(f"frozen by:      {c.frozen_by}")
    body_path = paths.repo / c.path
    if body_path.exists():
        click.echo("\n--- contract.md body ---")
        click.echo(body_path.read_text())
    else:
        click.echo(f"\n(contract.md missing at {body_path})")
