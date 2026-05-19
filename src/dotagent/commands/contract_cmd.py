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


# ---- score -----------------------------------------------------------------

@contract_group.command(name="score", help="Grade the contract against the 10-signal rubric (max 30).")
@click.argument("module_id", required=False, default="")
@click.option("--json", "as_json", is_flag=True, help="Emit ContractScore as JSON to stdout.")
@click.option("--report", "as_report", is_flag=True, help="Emit a per-signal markdown report to stdout.")
@click.option("--min", "min_total", type=int, default=0,
              help="Exit non-zero (code 2) if total < min. Default 0 (always exits 0).")
@click.option("--no-color", is_flag=True, help="Disable ANSI colors in --report mode.")
def cmd_score(module_id: str, as_json: bool, as_report: bool, min_total: int, no_color: bool) -> None:
    """Score the active module's current-cycle contract (or one named explicitly).

    Default (no flags): a one-line human summary including total/band and the
    two lowest-scoring signals' fix hints — Coda's preferred terse output.
    """
    paths = _paths()
    project = require_project(paths)
    if not module_id:
        # resolve from project state: prefer the first non-shipped, non-blocked module
        # with an active contract on its current cycle.
        from ..project.model import ModuleState
        candidate_states = (
            ModuleState.IN_PROGRESS, ModuleState.DEV_COMPLETE, ModuleState.QA_PASSED,
        )
        for mid in project.module_ids:
            m = project.modules.get(mid)
            if m and m.state in candidate_states and m.current_cycle and m.current_cycle.contract:
                module_id = mid
                break
        if not module_id:
            raise click.ClickException(
                "no active module with a contract found — pass <module-id> explicitly"
            )
    if module_id not in project.modules:
        raise click.ClickException(f"unknown module {module_id!r}")
    module = project.modules[module_id]
    if not module.current_cycle or not module.current_cycle.contract:
        raise click.ClickException(
            f"no contract on cycle of {module_id} — run `dotagent project contract init` first"
        )
    body_path = paths.repo / module.current_cycle.contract.path
    if not body_path.exists():
        raise click.ClickException(f"contract.md missing at {body_path}")

    # Score against the substantive body (negotiation log excluded).
    from ..project.contract_rubric import score_contract
    full = body_path.read_text()
    anchor = "<!-- anchor: negotiation-log -->"
    idx = full.find(anchor)
    substantive = full if idx < 0 else full[:idx]
    result = score_contract(substantive)

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
    elif as_report:
        click.echo(_render_score_report(result, use_color=(sys.stdout.isatty() and not no_color)))
    else:
        lowest = result.lowest(2)
        bits = ", ".join(f"{s.id} {s.name} ({s.score}/{s.max})" for s in lowest if s.score < s.max)
        if bits:
            click.echo(f"Contract: {result.total}/{result.max} ({result.band} band). Lowest signals: {bits}.")
        else:
            click.echo(f"Contract: {result.total}/{result.max} ({result.band} band). All signals at max.")
    if min_total and result.total < min_total:
        sys.exit(2)


_REPORT_COLOR_BY_BAND = {
    "ready":     "\033[32m",  # green
    "polish":    "\033[33m",  # yellow
    "rework":    "\033[35m",  # magenta
    "not_ready": "\033[31m",  # red
}
_RESET = "\033[0m"


def _render_score_report(result, *, use_color: bool) -> str:
    """Per-signal markdown report. Color used only when use_color is True."""
    band_color = _REPORT_COLOR_BY_BAND.get(result.band, "") if use_color else ""
    reset = _RESET if use_color else ""
    out = [
        f"# Contract score — {band_color}{result.total}/{result.max} ({result.band}){reset}",
        "",
        "| Signal | Score | Evidence | Fix |",
        "|---|---|---|---|",
    ]
    for s in result.signals:
        score_str = f"{s.score}/{s.max}"
        if use_color and s.score < s.max:
            score_str = f"\033[33m{score_str}{_RESET}"
        evidence = s.evidence.replace("|", "\\|")
        fix = (s.fix or "—").replace("|", "\\|")
        out.append(f"| {s.id} {s.name} | {score_str} | {evidence} | {fix} |")
    return "\n".join(out)
