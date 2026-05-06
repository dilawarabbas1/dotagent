from __future__ import annotations

import click

from ..paths import Paths, find_repo_root
from ..watchers.cursor_watcher import run_cursor_watch, watchdog_available


@click.group(name="watch", help="Foreground watchers for tools without native hooks.")
def watch_group() -> None:
    pass


@watch_group.command(name="cursor", help="File-watcher fallback for Cursor < 0.40.")
def cmd_cursor() -> None:
    repo = find_repo_root()
    paths = Paths(repo=repo)
    if not paths.agent.exists():
        raise click.ClickException("No .agent/ in this repo. Run `dotagent init` first.")
    if not watchdog_available():
        raise click.ClickException(
            "watchdog not installed. Run: pip install 'dotagent[watch]'"
        )
    click.echo(f"watching {paths.repo} for Cursor edits — Ctrl-C to stop.")
    run_cursor_watch(paths)
