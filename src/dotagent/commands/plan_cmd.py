"""`dotagent project plan` — plan negotiation primitives.

Data-layer only. Orchestrators (Coda, scripts, humans) decide who writes
what; dotagent records the writes, computes convergence, and freezes.
"""

from __future__ import annotations

import json
import sys

import click

from ..paths import Paths, find_repo_root
from ..project.plan_negotiation import (
    current_session_n,
    diff as plan_diff,
    freeze as plan_freeze,
    is_converged as plan_is_converged,
    read_state,
    write_draft,
)


def _paths():
    repo = find_repo_root()
    return Paths(repo=repo), repo


@click.group(name="plan", help="Plan negotiation primitives (draft/review/freeze).")
def plan_group() -> None:
    pass


@plan_group.command(
    name="write-draft",
    help="Write a new plan draft. Reads YAML from stdin (or --content).",
)
@click.option("--actor", required=True, help="Opaque actor identifier.")
@click.option("--from-stdin", is_flag=True, help="Read draft body from stdin.")
@click.option("--content", default=None, help="Inline draft body (small).")
def write_draft_cmd(actor: str, from_stdin: bool, content: str | None) -> None:
    if not from_stdin and content is None:
        click.echo("provide --from-stdin or --content", err=True)
        sys.exit(1)
    body = content if content is not None else click.get_text_stream("stdin").read()
    paths, _ = _paths()
    try:
        state = write_draft(paths, actor=actor, content=body, is_review=False)
    except ValueError as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)
    click.echo(f"✓ round {state.current_round} by {state.last_actor} written.")


@plan_group.command(
    name="write-review",
    help="Write a review counter-proposal. Requires --rationale.",
)
@click.option("--actor", required=True)
@click.option("--rationale", required=True, help="Why this counter (non-empty).")
@click.option("--from-stdin", is_flag=True)
@click.option("--content", default=None)
def write_review_cmd(actor: str, rationale: str, from_stdin: bool, content: str | None) -> None:
    if not from_stdin and content is None:
        click.echo("provide --from-stdin or --content", err=True)
        sys.exit(1)
    body = content if content is not None else click.get_text_stream("stdin").read()
    paths, _ = _paths()
    try:
        state = write_draft(paths, actor=actor, content=body,
                            rationale=rationale, is_review=True)
    except ValueError as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)
    click.echo(f"✓ round {state.current_round} review by {state.last_actor} written.")


@plan_group.command(name="show", help="Print state of the current session.")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
@click.option("--draft", is_flag=True, help="Print the draft YAML instead of state.")
def show_cmd(fmt: str, draft: bool) -> None:
    paths, _ = _paths()
    n = current_session_n(paths)
    if draft:
        target = paths.plan_draft_path(n)
        if not target.exists():
            click.echo("no draft yet", err=True)
            sys.exit(1)
        click.echo(target.read_text())
        return
    state = read_state(paths, n)
    if fmt == "json":
        click.echo(json.dumps(state.to_dict(), indent=2))
        return
    click.echo(f"session:        {state.session_n}")
    click.echo(f"current round:  {state.current_round}")
    click.echo(f"last actor:     {state.last_actor or '(none)'}")
    click.echo(f"last hash:      {state.last_hash or '(none)'}")
    click.echo(f"converged:      {state.converged} ({state.converged_reason})")
    click.echo(f"rounds:         {len(state.rounds)}")


@plan_group.command(name="diff", help="Show change between the last two rounds.")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
def diff_cmd(fmt: str) -> None:
    paths, _ = _paths()
    result = plan_diff(paths)
    if fmt == "json":
        click.echo(json.dumps(result, indent=2))
        return
    click.echo(f"status: {result['status']}")
    if result["status"] == "ok":
        click.echo(f"  from round {result['from']['n']} by {result['from']['actor']} ({result['from']['content_hash']})")
        click.echo(f"  to   round {result['to']['n']} by {result['to']['actor']} ({result['to']['content_hash']})")
        click.echo(f"  hash_match: {result['hash_match']}")


@plan_group.command(name="converged", help="Exit 0 if converged, 1 otherwise.")
def converged_cmd() -> None:
    paths, _ = _paths()
    sys.exit(0 if plan_is_converged(paths) else 1)


@plan_group.command(name="freeze", help="Promote draft to plan.yaml + snapshot.")
@click.option("--force", is_flag=True, help="Force freeze on non-converged (requires --rationale).")
@click.option("--rationale", default="", help="Explanation when --force is used.")
def freeze_cmd(force: bool, rationale: str) -> None:
    paths, repo = _paths()
    try:
        path = plan_freeze(paths, force=force, rationale=rationale)
    except (PermissionError, ValueError, FileNotFoundError) as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)
    click.echo(f"✓ frozen → {path.relative_to(repo)}")


@plan_group.command(name="log", help="Print the negotiation log for the current session.")
def log_cmd() -> None:
    paths, _ = _paths()
    n = current_session_n(paths)
    log_path = paths.plan_negotiation_log(n)
    if not log_path.exists():
        click.echo("no negotiation log yet")
        return
    click.echo(log_path.read_text())
