from __future__ import annotations

import click

from ..backup import MANAGED_FILES, list_backups, restore_all, restore_one
from ..paths import Paths, find_repo_root


def _paths() -> Paths:
    repo = find_repo_root()
    paths = Paths(repo=repo)
    if not paths.agent.exists():
        raise click.ClickException("No .agent/ in this repo. Run `dotagent init` first.")
    return paths


@click.command(name="restore-original",
               help="Restore a pre-dotagent AI-tool config from its .agent/.imported/ backup.")
@click.option("--name", type=click.Choice(sorted(MANAGED_FILES.keys())),
              help="Which file to restore. Omit to restore all available backups.")
@click.option("--list", "show_list", is_flag=True, help="List available backups and exit.")
def restore_original(name: str | None, show_list: bool) -> None:
    paths = _paths()
    backups = list_backups(paths)
    if show_list or (not name and not backups):
        if not backups:
            click.echo("(no backups in .agent/.imported/)")
            return
        click.echo("available backups:")
        for b in backups:
            click.echo(f"  · {b.relative_to(paths.repo)}")
        return

    if name:
        try:
            target = restore_one(paths, name)
        except FileNotFoundError as e:
            raise click.ClickException(str(e))
        click.echo(f"restored {target.relative_to(paths.repo)}")
        return

    restored = restore_all(paths)
    if not restored:
        click.echo("(nothing to restore)")
        return
    for p in restored:
        click.echo(f"restored {p.relative_to(paths.repo)}")
    click.echo(
        "\nNote: these files are still listed as managed adapters in .agent/config.yaml. "
        "Disable the ones you don't want regenerated, or dotagent will recreate them on the next `sync`."
    )
