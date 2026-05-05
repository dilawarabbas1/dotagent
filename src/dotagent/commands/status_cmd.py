from __future__ import annotations

import click

from ..config import Config
from ..identity import resolve
from ..paths import Paths, find_repo_root


@click.command(help="Summary: identity, adapters, memory state.")
def status() -> None:
    repo = find_repo_root()
    paths = Paths(repo=repo)
    if not paths.agent.exists():
        raise click.ClickException("No .agent/ in this repo. Run `dotagent init`.")
    cfg = Config.load(paths)
    identity = resolve(repo)
    click.echo(f"repo:     {repo}")
    click.echo(f"actor:    {identity.id} <{', '.join(identity.emails) or 'no email'}>")
    click.echo(f"adapters: {', '.join(cfg.adapters_enabled) or '(none)'}")
    epi_count = sum(1 for _ in paths.episodic.rglob("*.jsonl")) if paths.episodic.exists() else 0
    sem_count = sum(1 for _ in paths.semantic.rglob("*.md")) if paths.semantic.exists() else 0
    dream_g = sum(1 for _ in (paths.dream / "graduated").glob("*.md")) if (paths.dream / "graduated").exists() else 0
    dream_c = sum(1 for _ in (paths.dream / "candidates").glob("*.md")) if (paths.dream / "candidates").exists() else 0
    click.echo(f"episodic: {epi_count} session files")
    click.echo(f"semantic: {sem_count} graduated entries")
    click.echo(f"dream:    {dream_c} candidates / {dream_g} graduated")
