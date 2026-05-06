"""Emit the commit trailer for the prepare-commit-msg hook."""

from __future__ import annotations

import click

from ..identity import resolve
from ..memory import WorkingMemory
from ..paths import Paths, find_repo_root


@click.command(help="Print the dotagent attribution trailer (used by prepare-commit-msg hook).")
def trailer() -> None:
    repo = find_repo_root()
    paths = Paths(repo=repo)
    if not paths.agent.exists():
        return
    identity = resolve(repo)
    state = WorkingMemory(paths, identity.id).load_current()
    tool = state.tool or identity.default_tool or "human"
    click.echo(f"Co-authored-by: dotagent <dotagent@local> "
               f"trailer-actor={identity.id} trailer-tool={tool}")
