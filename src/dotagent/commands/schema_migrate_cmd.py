"""`dotagent migrate` — schema-version migration for a dotagent project.

Distinct from `dotagent migrate-cco` (which imports Claude-Code-Optimization
repos). This command upgrades the `.agent/` schema in-place.

Three modes detected automatically:

- **FRESH** / **MID_PROJECT** — print "run `dotagent init`" and exit.
- **PRE_V0_4** / **UPGRADE** — show the plan; prompt for confirmation;
  apply; log every step.
- **CURRENT** — no-op.

Always reversible via `dotagent migrate --rollback`.
"""

from __future__ import annotations

import json
import sys

import click

from ..migration import (
    Mode,
    MigrationStep,
    apply_plan,
    build_plan,
)
from ..migration.log import read_last_log
from ..migration.v0_3_to_v0_4 import rollback_step
from ..paths import Paths, find_repo_root


@click.command(help="Upgrade the .agent/ schema to the current version.")
@click.option("--plan", "plan_only", is_flag=True, help="Show what would change; do nothing.")
@click.option("--rollback", is_flag=True, help="Reverse the most recent migration.")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompts.")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
def migrate(plan_only: bool, rollback: bool, yes: bool, fmt: str) -> None:
    repo = find_repo_root()

    if rollback:
        _do_rollback(repo, yes=yes, fmt=fmt)
        return

    plan = build_plan(repo)

    if fmt == "json":
        click.echo(json.dumps(plan.to_dict(), indent=2))
        if plan.mode in (Mode.FRESH, Mode.MID_PROJECT):
            sys.exit(1)
        return

    _print_plan_text(plan)

    if plan.mode is Mode.CURRENT:
        return
    if plan.mode in (Mode.FRESH, Mode.MID_PROJECT):
        sys.exit(1)
    if not plan.steps:
        click.echo("nothing to migrate.")
        return
    if plan_only:
        click.echo("\n[--plan] nothing was written.")
        return

    if not yes:
        click.confirm(
            f"\napply these {len(plan.steps)} change(s)?",
            abort=True,
        )

    executed = apply_plan(repo, plan)
    click.echo(f"\n✓ applied {len(executed)} change(s). "
               f"see .agent/.migration-log.md for the rollback record.")


def _print_plan_text(plan) -> None:
    click.echo(f"detected mode:  {plan.mode.value}")
    click.echo(f"from version:   {plan.from_version or '(none)'}")
    click.echo(f"to version:     {plan.to_version}")
    if plan.notes:
        click.echo("")
        for note in plan.notes:
            click.echo(f"note: {note}")
    if plan.steps:
        click.echo("")
        click.echo(f"planned changes ({len(plan.steps)}):")
        for step in plan.steps:
            click.echo(f"  {step.to_log_line()}")


def _do_rollback(repo, *, yes: bool, fmt: str) -> None:
    log = read_last_log(repo)
    if log is None:
        if fmt == "json":
            click.echo(json.dumps({"error": "no migration log found"}, indent=2))
        else:
            click.echo("no migration log to roll back.")
        sys.exit(1)

    if fmt == "json":
        click.echo(json.dumps({
            "rollback": {
                "timestamp": log.timestamp,
                "from_version": log.from_version,
                "to_version": log.to_version,
                "steps": [s.to_dict() for s in log.steps],
            }
        }, indent=2))
    else:
        click.echo(f"rolling back: {log.timestamp}")
        click.echo(f"  was: v{log.from_version or 'pre-0.4'} → v{log.to_version}")
        click.echo(f"  steps to reverse: {len(log.steps)}")
        for step in log.steps:
            click.echo(f"  {step.to_log_line()}")

    if not yes:
        click.confirm("\nreverse these changes?", abort=True)

    failures: list[str] = []
    for step in reversed(log.steps):
        if not rollback_step(repo, step):
            failures.append(step.path)

    if failures:
        click.echo(f"\n✗ {len(failures)} step(s) failed to roll back:")
        for p in failures:
            click.echo(f"  - {p}")
        sys.exit(1)
    click.echo(f"\n✓ rolled back {len(log.steps)} step(s).")
