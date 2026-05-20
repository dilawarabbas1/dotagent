"""`dotagent project contracts` — view + rebuild the contracts dashboard."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from ..paths import Paths, find_repo_root
from ..project.contracts_index import build_index, regenerate, render_markdown


def _load_project_or_die():
    repo = find_repo_root()
    paths = Paths(repo=repo)
    try:
        from ..project.model import load_project
    except ImportError:
        click.echo("project module not available", err=True)
        sys.exit(1)
    project = load_project(paths)
    if project is None:
        click.echo("no project initialized. run `dotagent project init` first.", err=True)
        sys.exit(1)
    return repo, paths, project


@click.group(
    name="contracts",
    help="View the auto-generated per-repo CONTRACTS.md (`.agent/project/CONTRACTS.md`).",
)
def contracts_group() -> None:
    pass


@contracts_group.command(name="show", help="Print the current dashboard.")
@click.option("--format", "fmt", type=click.Choice(["text", "json", "markdown"]), default="text")
@click.option("--open", "only_open", is_flag=True, help="Only open cycles.")
@click.option("--frozen", "only_frozen", is_flag=True, help="Only frozen cycles.")
@click.option("--module", "filter_module", default=None, help="Filter by module ID.")
def show_cmd(fmt: str, only_open: bool, only_frozen: bool, filter_module: str | None) -> None:
    _, _, project = _load_project_or_die()
    index = build_index(project)

    if filter_module:
        index.sections = [s for s in index.sections if s.module_id == filter_module]
    if only_open:
        for s in index.sections:
            s.rows = [r for r in s.rows if r.state == "open"]
    if only_frozen:
        for s in index.sections:
            s.rows = [r for r in s.rows if r.state == "frozen"]

    if fmt == "json":
        click.echo(json.dumps(index.to_dict(), indent=2))
        return
    if fmt == "markdown":
        click.echo(render_markdown(index))
        return

    # text
    click.echo(f"project:      {index.project_name}")
    click.echo(f"generated:    {index.generated_at}")
    click.echo(f"open total:   {index.total_open}")
    click.echo(f"frozen total: {index.total_frozen}")
    click.echo("")
    for section in index.sections:
        click.echo(f"# {section.module_id} ({section.state})")
        if section.implements_features:
            click.echo(f"  implements: {', '.join(section.implements_features)}")
        if section.cross_module:
            click.echo(f"  cross-module: {section.cross_module}")
        if not section.rows:
            click.echo("  (no cycles)")
            continue
        for r in section.rows:
            click.echo(
                f"  cycle {r.cycle_n:02d}  {r.state:6}  round {r.round}  "
                f"by {r.last_actor or '?'}  ({r.last_touched or 'no timestamp'})"
            )
        click.echo("")


@contracts_group.command(name="rebuild", help="Regenerate .agent/project/CONTRACTS.md (or cross-repo rollup with --all-repos).")
@click.option("--all-repos", is_flag=True,
              help="Walk repos[] manifest and regenerate Project-Root/contracts.md instead.")
def rebuild_cmd(all_repos: bool) -> None:
    repo, paths, project = _load_project_or_die()
    if all_repos:
        from ..project.contracts_rollup import regenerate as regen_rollup
        target = regen_rollup(paths)
        click.echo(f"✓ wrote {target.relative_to(repo)}")
        return
    target = regenerate(paths, project)
    click.echo(f"✓ wrote {target.relative_to(repo)}")


@contracts_group.command(name="rollup", help="Print the cross-repo contracts rollup (Tier 1).")
@click.option("--format", "fmt", type=click.Choice(["text", "json", "markdown"]), default="text")
def rollup_cmd(fmt: str) -> None:
    from ..project.contracts_rollup import build_rollup, render_markdown
    _, paths, _ = _load_project_or_die()
    rollup = build_rollup(paths)
    if fmt == "json":
        click.echo(json.dumps(rollup.to_dict(), indent=2))
        return
    if fmt == "markdown":
        click.echo(render_markdown(rollup))
        return
    click.echo(f"project:      {rollup.project_name}")
    click.echo(f"generated:    {rollup.generated_at}")
    click.echo(f"open total:   {rollup.total_open}")
    click.echo(f"frozen total: {rollup.total_frozen}")
    click.echo("")
    if not rollup.repos:
        click.echo("no repos[] manifest declared.")
        return
    for r in rollup.repos:
        click.echo(f"  {r.id:20s}  role={r.role or '—':12s}  open={r.open}  frozen={r.frozen}")
        if r.error:
            click.echo(f"      error: {r.error}")
